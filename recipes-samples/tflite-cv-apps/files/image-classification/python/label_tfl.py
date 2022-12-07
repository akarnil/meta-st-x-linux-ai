#!/usr/bin/python3
#
# Author: Maxence Guilhin <maxence.guilhin@st.com> for STMicroelectronics.
#
# Copyright (c) 2020 STMicroelectronics. All rights reserved.
#
# This software component is licensed by ST under BSD 3-Clause license,
# the "License"; You may not use this file except in compliance with the
# License. You may obtain a copy of the License at:
#
# http://www.opensource.org/licenses/BSD-3-Clause

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gst', '1.0')
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import GdkPixbuf
from gi.repository import Gst

import numpy as np
import argparse
import signal
import os
import random
import json
import subprocess
import re
import os.path
from os import path
import cv2
from PIL import Image
import tflite_runtime.interpreter as tflr
from timeit import default_timer as timer

#init gstreamer
Gst.init(None)
Gst.init_check(None)
#init gtk
Gtk.init(None)
Gtk.init_check(None)

#path definition
LIBTPU_STD_PATH = "/usr/lib/libedgetpu-std.so.2"
LIBTPU_MAX_PATH = "/usr/lib/libedgetpu-max.so.2"
RESOURCES_DIRECTORY = os.path.abspath(os.path.dirname(__file__)) + "/resources/"

class NeuralNetwork:
    """
    Class that handles Neural Network inference
    """

    def __init__(self, model_file, label_file, input_mean, input_std, edgetpu, perf, ext_delegate):
        """
        :param model_path: .tflite model to be executedname of file containing labels")
        :param label_file:  name of file containing labels
        :param input_mean: input_mean
        :param input_std: input standard deviation
        """

        if args.num_threads == None :
            if os.cpu_count() <= 1:
                self.number_threads = 1
            else :
                self.number_threads = os.cpu_count()
        else :
           self.number_threads = int(args.num_threads)

        self._selected_delegate = None

        def load_labels(filename):
            my_labels = []
            input_file = open(filename, 'r')
            for l in input_file:
                my_labels.append(l.strip())
            return my_labels

        self._model_file = model_file
        self._label_file = label_file
        self._input_mean = input_mean
        self._input_std = input_std
        self._floating_model = False

        if edgetpu is True:
            #Check if the Edge TPU is connected
            edge_tpu = False
            device_re = re.compile(".+?ID\s(?P<id>\w+)", re.I)
            lsusb = subprocess.check_output("lsusb").decode("utf-8")
            for i in lsusb.split('\n'):
                if i:
                    info = device_re.match(i)
                    if info:
                        d = info.groupdict()
                        if '1a6e' in d.values() or '18d1' in d.values():
                            edge_tpu = True

            if not edge_tpu:
                print("Edge TPU is not plugged!")
                print("Please connect the Edge TPU and try again.")
                os._exit(1)

            if perf == 'std':
                if path.exists(LIBTPU_STD_PATH):
                    self._selected_delegate = LIBTPU_STD_PATH
                else :
                    print("No delegate ",LIBTPU_STD_PATH, "found fall back on CPU mode")
            elif perf == 'max':
                if path.exists(LIBTPU_MAX_PATH):
                    self._selected_delegate = LIBTPU_MAX_PATH
                else :
                    print("No delegate ",LIBTPU_MAX_PATH, "found fall back on CPU mode")

        elif ext_delegate is not None :
            if path.exists(ext_delegate):
                self._selected_delegate = ext_delegate
            else :
                print("No delegate ",ext_delegate, "found fall back on CPU mode")

        if self._selected_delegate is not None:
            print('Loading external delegate from {}'.format(self._selected_delegate))
            print("number of threads used in tflite interpreter : ",self.number_threads)
            self._interpreter = tflr.Interpreter(model_path=self._model_file,
                                                 num_threads = self.number_threads,
                                                 experimental_delegates=[tflr.load_delegate(self._selected_delegate)])
        else :
            print("no delegate to use, CPU mode activated")
            self._interpreter = tflr.Interpreter(model_path=self._model_file,
                                                 num_threads = self.number_threads)

        self._interpreter.allocate_tensors()
        self._input_details = self._interpreter.get_input_details()
        self._output_details = self._interpreter.get_output_details()

        # check the type of the input tensor
        if self._input_details[0]['dtype'] == np.float32:
            self._floating_model = True
            print("Floating point Tensorflow Lite Model")

        self._labels = load_labels(self._label_file)

    def __getstate__(self):
        return (self._model_file, self._label_file, self._input_mean,
                self._input_std, self._floating_model, self._selected_delegate, self.number_threads, \
                self._input_details, self._output_details, self._labels)

    def __setstate__(self, state):
        self._model_file, self._label_file, self._input_mean, \
                self._input_std, self._floating_model, self._selected_delegate, self.number_threads, \
                self._input_details, self._output_details, self._labels = state

        if self._selected_delegate is not None:
            self._interpreter = tflr.Interpreter(model_path=self._model_file,
                                                 num_threads = self.number_threads,
                                                 experimental_delegates=[tflr.load_delegate(self._selected_delegate)])
        else :
            self._interpreter = tflr.Interpreter(model_path=self._model_file,
                                                 num_threads = self.number_threads)
        self._interpreter.allocate_tensors()

    def get_labels(self):
        return self._labels

    def get_img_size(self):
        """
        :return: size of NN input image size
        """
        # NxHxWxC, H:1, W:2, C:3
        return (int(self._input_details[0]['shape'][1]),
                int(self._input_details[0]['shape'][2]),
                int(self._input_details[0]['shape'][3]))

    def launch_inference(self, img):
        """
        This method launches inference using the invoke call
        :param img: the image to be inferenced
        """
        # add N dim
        input_data = np.expand_dims(img, axis=0)

        if self._floating_model:
            input_data = (np.float32(input_data) - self._input_mean) / self._input_std

        self._interpreter.set_tensor(self._input_details[0]['index'], input_data)
        self._interpreter.invoke()

    def get_results(self):
         """
         This method can print and return the top_k results of the inference
         """
         output_data = self._interpreter.get_tensor(self._output_details[0]['index'])
         results = np.squeeze(output_data)

         top_k = results.argsort()[-5:][::-1]

         if self._floating_model:
             return (results[top_k[0]], top_k[0])
         else:
             return (results[top_k[0]]/255.0, top_k[0])

class GstWidget(Gtk.Box):
    """
    Class that handles Gstreamer pipeline using gtkwaylandsink and appsink
    """
    def __init__(self, app, nn):
         super().__init__()
         # connect the gtkwidget with the realize callback
         self.connect('realize', self._on_realize)
         self.instant_fps = 0
         self.app = app
         self.nn = nn

    def _on_realize(self, widget):
            """
            creation of the gstreamer pipeline when gstwidget is created
            """
            # gstreamer pipeline creation
            self.pipeline = Gst.Pipeline()

            # creation of the source v4l2src
            self.v4lsrc1 = Gst.ElementFactory.make("v4l2src", "source")
            video_device = "/dev/" + str(self.app.video_device)
            self.v4lsrc1.set_property("device", video_device)

            #creation of the v4l2src caps
            caps = str(self.app.camera_caps) + ", width=" + str(args.frame_width) +",height=" + str(args.frame_height) + ", framerate=" + str(args.framerate)+ "/1"
            print("Camera pipeline configuration : ",caps)
            camera1caps = Gst.Caps.from_string(caps)
            self.camerafilter1 = Gst.ElementFactory.make("capsfilter", "filter1")
            self.camerafilter1.set_property("caps", camera1caps)

            # creation of the videoconvert elements
            self.videoformatconverter1 = Gst.ElementFactory.make("videoconvert", "video_convert1")
            self.videoformatconverter2 = Gst.ElementFactory.make("videoconvert", "video_convert2")

            self.tee = Gst.ElementFactory.make("tee", "tee")

            # creation and configuration of the queue elements
            self.queue1 = Gst.ElementFactory.make("queue", "queue-1")
            self.queue2 = Gst.ElementFactory.make("queue", "queue-2")
            self.queue1.set_property("max-size-buffers", 1)
            self.queue1.set_property("leaky", 2)
            self.queue2.set_property("max-size-buffers", 1)
            self.queue2.set_property("leaky", 2)

            # creation and configuration of the appsink element
            self.appsink = Gst.ElementFactory.make("appsink", "appsink")
            nn_caps = "video/x-raw, format = RGB, width=" + str(self.app.nn_input_width) + ",height=" + str(self.app.nn_input_height)
            nncaps = Gst.Caps.from_string(nn_caps)
            self.appsink.set_property("caps", nncaps)
            self.appsink.set_property("emit-signals", True)
            self.appsink.set_property("sync", False)
            self.appsink.set_property("max-buffers", 1)
            self.appsink.set_property("drop", True)
            self.appsink.connect("new-sample", self.new_sample)

            # creation of the gtkwaylandsink element to handle the gestreamer video stream
            self.gtkwaylandsink = Gst.ElementFactory.make("gtkwaylandsink")
            self.pack_start(self.gtkwaylandsink.props.widget, True, True, 0)
            self.gtkwaylandsink.props.widget.show()

            # creation and configuration of the fpsdisplaysink element to measure display fps
            self.fps_disp_sink = Gst.ElementFactory.make("fpsdisplaysink", "fpsmeasure1")
            self.fps_disp_sink.set_property("signal-fps-measurements", True)
            self.fps_disp_sink.set_property("fps-update-interval", 2000)
            self.fps_disp_sink.set_property("text-overlay", False)
            self.fps_disp_sink.set_property("video-sink", self.gtkwaylandsink)
            self.fps_disp_sink.connect("fps-measurements",self.get_fps_display)

            # creation of the video rate and video scale elements
            self.video_rate = Gst.ElementFactory.make("videorate", "video-rate")
            self.video_scale = Gst.ElementFactory.make("videoscale", "video-scale")

            # Add all elements to the pipeline
            self.pipeline.add(self.v4lsrc1)
            self.pipeline.add(self.camerafilter1)
            self.pipeline.add(self.videoformatconverter1)
            self.pipeline.add(self.videoformatconverter2)
            self.pipeline.add(self.tee)
            self.pipeline.add(self.queue1)
            self.pipeline.add(self.queue2)
            self.pipeline.add(self.appsink)
            self.pipeline.add(self.fps_disp_sink)
            self.pipeline.add(self.video_rate)
            self.pipeline.add(self.video_scale)

            # linking elements together
            #                              -> queue 1 -> videoconvert -> fpsdisplaysink
            # v4l2src -> video rate -> tee
            #                              -> queue 2 -> videoconvert -> video scale -> appsink
            self.v4lsrc1.link(self.video_rate)
            self.video_rate.link(self.camerafilter1)
            self.camerafilter1.link(self.tee)
            self.queue1.link(self.videoformatconverter1)
            self.videoformatconverter1.link(self.fps_disp_sink)
            self.queue2.link(self.videoformatconverter2)
            self.videoformatconverter2.link(self.video_scale)
            self.video_scale.link(self.appsink)
            self.tee.link(self.queue1)
            self.tee.link(self.queue2)

            # set pipeline playing mode
            self.pipeline.set_state(Gst.State.PLAYING)
            # getting pipeline bus
            self.bus = self.pipeline.get_bus()
            self.bus.add_signal_watch()
            self.bus.connect('message::error', self.msg_error_cb)
            self.bus.connect('message::eos', self.msg_eos_cb)
            self.bus.connect('message::info', self.msg_info_cb)
            self.bus.connect('message::application', self.msg_application_cb)
            self.bus.connect('message::state-changed', self.msg_state_changed_cb)

    def msg_eos_cb(self, bus, message):
        print('eos message -> {}'.format(message))

    def msg_info_cb(self, bus, message):
        print('info message -> {}'.format(message))

    def msg_error_cb(self, bus, message):
        print('error message -> {}'.format(message.parse_error()))

    def msg_state_changed_cb(self, bus, message):
        oldstate,newstate,pending = message.parse_state_changed()
        if (oldstate == Gst.State.NULL) and (newstate == Gst.State.READY):
            Gst.debug_bin_to_dot_file(self.pipeline, Gst.DebugGraphDetails.ALL,"pipeline_py_NULL_READY")
            
    def msg_application_cb(self, bus, message):
        if message.get_structure().get_name() == 'inference-done':
            self.app.update_ui();

    def gst_to_opencv(self,sample):
        """
        convertion of the gstreamer frame buffer into numpy array
        """
        buf = sample.get_buffer()
        caps = sample.get_caps()
        arr = np.ndarray(
            (caps.get_structure(0).get_value('height'),
             caps.get_structure(0).get_value('width'),
             3),
            buffer=buf.extract_dup(0, buf.get_size()),
            dtype=np.uint8)
        return arr

    def new_sample(self,*data):
        """
        recover video frame from appsink
        and run inference
        """
        global image_arr
        sample = self.appsink.emit("pull-sample")
        arr = self.gst_to_opencv(sample)
        if arr is not None :
            start_time = timer()
            self.nn.launch_inference(arr)
            stop_time = timer()
            self.app.nn_inference_time = stop_time - start_time
            self.app.nn_inference_fps = (1000/(self.app.nn_inference_time*1000))
            self.app.nn_result_accuracy,self.app.nn_result_label = self.nn.get_results()
            struc = Gst.Structure.new_empty("inference-done")
            msg = Gst.Message.new_application(None, struc)
            self.bus.post(msg)
        return Gst.FlowReturn.OK

    def get_fps_display(self,fpsdisplaysink,fps,droprate,avgfps):
        """
        measure and recover display fps
        """
        self.instant_fps = fps
        return self.instant_fps
    
class MainWindow(Gtk.Window):
    """
    This class handles all the functions necessary
    to display video stream in GTK GUI or still
    pictures using OpenCVS
    """ 
 
    def __init__(self,args,app):
        """
        Setup instances of class and shared variables
        usefull for the application
        """
        Gtk.Window.__init__(self)
        self.app = app
        self.main_ui_creation(args)
       
    def set_ui_param(self):
        """
        Setup all the UI parameter depending
        on the screen size
        """
        self.ui_cairo_font_size_label = 35;
        self.ui_cairo_font_size = 20;
        self.ui_icon_exit_width = '50';
        self.ui_icon_exit_height = '50';
        self.ui_icon_st_width = '130';
        self.ui_icon_st_height = '160';
        if self.screen_height <= 272:
               # Display 480x272 */
               self.ui_cairo_font_size_label = 15;
               self.ui_cairo_font_size = 7;
               self.ui_icon_exit_width = '25';
               self.ui_icon_exit_height = '25';
               self.ui_icon_st_width = '42';
               self.ui_icon_st_height = '52';
        elif self.screen_height <= 480:
               #Display 800x480 */
               self.ui_cairo_font_size_label = 25;
               self.ui_cairo_font_size = 13;
               self.ui_icon_exit_width = '50';
               self.ui_icon_exit_height = '50';
               self.ui_icon_st_width = '65';
               self.ui_icon_st_height = '80';  

    def main_ui_creation(self,args):
        """
        Setup the Gtk UI of the main window
        """
        # remove the title bar
        self.set_decorated(False)

        self.first_drawing_call = True
        GdkDisplay = Gdk.Display.get_default()
        monitor = Gdk.Display.get_monitor(GdkDisplay, 0)
        workarea = Gdk.Monitor.get_workarea(monitor)

        GdkScreen = Gdk.Screen.get_default()
        provider = Gtk.CssProvider()
        css_path = RESOURCES_DIRECTORY + "py_widgets.css"
        self.set_name("main_window")
        provider.load_from_path(css_path)
        Gtk.StyleContext.add_provider_for_screen(GdkScreen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.maximize()
        self.screen_width = workarea.width
        self.screen_height = workarea.height

        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect('destroy', Gtk.main_quit)
        self.set_ui_param()
        # setup info_box containing inference results
        if self.app.enable_camera_preview == True:
            # camera preview mode
            self.info_box = Gtk.VBox()
            self.info_box.set_name("gui_main_stbox")
            if  args.edgetpu is False :
                self.st_icon_path = RESOURCES_DIRECTORY + 'st_icon_' + self.ui_icon_st_width + 'x' + self.ui_icon_st_height + '.png'
            else :
                self.st_icon_path = RESOURCES_DIRECTORY + 'st_icon_tpu_' + self.ui_icon_st_width + 'x' + self.ui_icon_st_height + '.png'
            self.st_icon = Gtk.Image.new_from_file(self.st_icon_path)
            self.st_icon_event = Gtk.EventBox()
            self.st_icon_event.add(self.st_icon)
            self.info_box.pack_start(self.st_icon_event,False,False,2)
            self.label_disp = Gtk.Label()
            self.label_disp.set_justify(Gtk.Justification.LEFT)
            self.label_disp.set_markup("<span font=\'%d\' color='#FFFFFFFF'><b>disp.fps:    \n</b></span>" % self.ui_cairo_font_size)
            self.info_box.pack_start(self.label_disp,True,False,2)
            self.disp_fps = Gtk.Label()
            self.disp_fps.set_justify(Gtk.Justification.FILL)
            self.info_box.pack_start(self.disp_fps,True,False,2)
            self.label_inf_fps = Gtk.Label()
            self.label_inf_fps.set_justify(Gtk.Justification.LEFT)
            self.label_inf_fps.set_markup("<span font=\'%d\' color='#FFFFFFFF'><b>inf.fps:\n</b></span>" % self.ui_cairo_font_size)
            self.info_box.pack_start(self.label_inf_fps,True,False,2)
            self.inf_fps = Gtk.Label()
            self.inf_fps.set_justify(Gtk.Justification.FILL)
            self.info_box.pack_start(self.inf_fps,True,False,2)
            self.label_inftime = Gtk.Label()
            self.label_inftime.set_justify(Gtk.Justification.LEFT)
            self.label_inftime.set_markup("<span font=\'%d\' color='#FFFFFFFF'><b>inf.time:\n</b></span>" % self.ui_cairo_font_size)
            self.info_box.pack_start(self.label_inftime,True,False,2)
            self.inf_time = Gtk.Label()
            self.inf_time.set_justify(Gtk.Justification.FILL)
            self.info_box.pack_start(self.inf_time,True,False,2)
        else :
            # still picture mode
            self.info_box = Gtk.VBox()
            self.info_box.set_name("gui_main_stbox")
            if  args.edgetpu is False :
                self.st_icon_path = RESOURCES_DIRECTORY + 'st_icon_next_inference_' + self.ui_icon_st_width + 'x' + self.ui_icon_st_height + '.png'
            else :
                self.st_icon_path = RESOURCES_DIRECTORY + 'st_icon_tpu_next_inference_' + self.ui_icon_st_width + 'x' + self.ui_icon_st_height + '.png'
            self.st_icon = Gtk.Image.new_from_file(self.st_icon_path)
            self.st_icon_event = Gtk.EventBox()
            self.st_icon_event.add(self.st_icon)
            self.info_box.pack_start(self.st_icon_event,False,False,20)
            self.label_inftime = Gtk.Label()
            self.label_inftime.set_justify(Gtk.Justification.LEFT)
            self.label_inftime.set_markup("<span font=\'%d\' color='#FFFFFFFF'><b>inf.time:\n</b></span>" % self.ui_cairo_font_size)
            self.info_box.pack_start(self.label_inftime,False,False,20)
            self.inf_time = Gtk.Label()
            self.inf_time.set_justify(Gtk.Justification.FILL)
            self.info_box.pack_start(self.inf_time,False,False,20)

        # setup video box containing gst stream in camera preview mode
        # and a openCV picture in still picture mode
        self.video_box = Gtk.HBox()
        self.video_box.set_name("gui_main_video")
        if self.app.enable_camera_preview == True:
            # camera preview => gst stream
            self.video_widget = self.app.gst_widget
            self.video_widget.set_app_paintable(True)
            self.video_box.pack_start(self.video_widget, True, True, 0)
        else :
            # still picture => openCV picture
            self.image = Gtk.Image()
            self.video_box.pack_start(self.image, True, True, 0)
        # setup the exit box which contains the exit button
        self.exit_box = Gtk.VBox()
        self.exit_box.set_name("gui_main_exit")
        self.exit_icon_path = RESOURCES_DIRECTORY + 'exit_' + self.ui_icon_exit_width + 'x' + self.ui_icon_exit_height + '.png'
        self.exit_icon = Gtk.Image.new_from_file(self.exit_icon_path)
        self.exit_icon_event = Gtk.EventBox()
        self.exit_icon_event.add(self.exit_icon)
        self.exit_box.pack_start(self.exit_icon_event,False,False,2)

        # setup main box which group the three previous boxes
        self.main_box =  Gtk.HBox()
        self.exit_box.set_name("gui_main")
        self.main_box.pack_start(self.info_box,False,False,0)
        self.main_box.pack_start(self.video_box,True,True,0)
        self.main_box.pack_start(self.exit_box,False,False,0)
        self.add(self.main_box)
        return True
    
    def update_frame(self, frame):
        """
        update frame in still picture mode
        """
        img = Image.fromarray(frame)
        data = img.tobytes()
        data = GLib.Bytes.new(data)
        pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(data,
                                                 GdkPixbuf.Colorspace.RGB,
                                                 False,
                                                 8,
                                                 frame.shape[1],
                                                 frame.shape[0],
                                                 frame.shape[2] * frame.shape[1])
        self.image.set_from_pixbuf(pixbuf.copy())

class OverlayWindow(Gtk.Window):
    """
    This class handles all the functions necessary
    to display overlayed information on top of the 
    video stream and in side information boxes of
    the GUI
    """    
    
    def __init__(self,args,app):
        """
        Setup instances of class and shared variables
        usefull for the application
        """
        Gtk.Window.__init__(self)
        self.app = app
        self.overlay_ui_creation(args)
    
    def exit_icon_cb(self,eventbox, event):
        """
        Exit callback to close application
        """
        self.destroy()
        Gtk.main_quit()
        
    def update_label_still(self, label, accuracy, inference_time):
        """
        update inference results in still picture mode
        """
        str_accuracy = str("{0:.2f}".format(accuracy))
        str_inference_time = str("{0:0.1f}".format(inference_time))

        self.inf_time.set_markup("<span font=\'%d\' color='#FFFFFFFF'><b>%sms\n</b></span>" % (self.ui_cairo_font_size,str_inference_time))
        self.acc.set_markup("<span font=\'%d\' color='#FFFFFFFF'><b>%s&#37;\n\n</b></span>" % (self.ui_cairo_font_size,str_accuracy))
        self.app.label_to_display = label

    def set_ui_param(self):
        """
        Setup all the UI parameter depending
        on the screen size
        """
        self.ui_cairo_font_size_label = 35;
        self.ui_cairo_font_size = 20;
        self.ui_icon_exit_width = '50';
        self.ui_icon_exit_height = '50';
        self.ui_icon_st_width = '130';
        self.ui_icon_st_height = '160';
        if self.screen_height <= 272:
               # Display 480x272 */
               self.ui_cairo_font_size_label = 15;
               self.ui_cairo_font_size = 7;
               self.ui_icon_exit_width = '25';
               self.ui_icon_exit_height = '25';
               self.ui_icon_st_width = '42';
               self.ui_icon_st_height = '52';
        elif self.screen_height <= 480:
               #Display 800x480 */
               self.ui_cairo_font_size_label = 25;
               self.ui_cairo_font_size = 13;
               self.ui_icon_exit_width = '50';
               self.ui_icon_exit_height = '50';
               self.ui_icon_st_width = '65';
               self.ui_icon_st_height = '80';
    
    def overlay_ui_creation(self,args):
        """
        Setup the Gtk UI of the overlay window
        """
        # remove the title bar
        self.set_decorated(False)

        self.first_drawing_call = True
        GdkDisplay = Gdk.Display.get_default()
        monitor = Gdk.Display.get_monitor(GdkDisplay, 0)
        workarea = Gdk.Monitor.get_workarea(monitor)

        GdkScreen = Gdk.Screen.get_default()
        provider = Gtk.CssProvider()
        css_path = RESOURCES_DIRECTORY + "py_widgets.css"
        self.set_name("overlay_window")
        provider.load_from_path(css_path)
        Gtk.StyleContext.add_provider_for_screen(GdkScreen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.maximize()
        self.screen_width = workarea.width
        self.screen_height = workarea.height

        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect('destroy', Gtk.main_quit)
        self.set_ui_param()

        # setup info_box containing inference results and ST_logo which is a
        # "next inference" button in still picture mode
        if self.app.enable_camera_preview == True:
            # camera preview mode
            self.info_box = Gtk.VBox()
            self.info_box.set_name("gui_overlay_stbox")
            if  args.edgetpu is False :
                self.st_icon_path = RESOURCES_DIRECTORY + 'st_icon_' + self.ui_icon_st_width + 'x' + self.ui_icon_st_height + '.png'
            else :
                self.st_icon_path = RESOURCES_DIRECTORY + 'st_icon_tpu_' + self.ui_icon_st_width + 'x' + self.ui_icon_st_height + '.png'
            self.st_icon = Gtk.Image.new_from_file(self.st_icon_path)
            self.st_icon_event = Gtk.EventBox()
            self.st_icon_event.add(self.st_icon)
            self.info_box.pack_start(self.st_icon_event,False,False,2)
            self.label_disp = Gtk.Label()
            self.label_disp.set_justify(Gtk.Justification.LEFT)
            self.label_disp.set_markup("<span font=\'%d\' color='#FFFFFFFF'><b>disp.fps:    \n</b></span>" % self.ui_cairo_font_size)
            self.info_box.pack_start(self.label_disp,True,False,2)
            self.disp_fps = Gtk.Label()
            self.disp_fps.set_justify(Gtk.Justification.FILL)
            self.info_box.pack_start(self.disp_fps,True,False,2)
            self.label_inf_fps = Gtk.Label()
            self.label_inf_fps.set_justify(Gtk.Justification.LEFT)
            self.label_inf_fps.set_markup("<span font=\'%d\' color='#FFFFFFFF'><b>inf.fps:\n</b></span>" % self.ui_cairo_font_size)
            self.info_box.pack_start(self.label_inf_fps,True,False,2)
            self.inf_fps = Gtk.Label()
            self.inf_fps.set_justify(Gtk.Justification.FILL)
            self.info_box.pack_start(self.inf_fps,True,False,2)
            self.label_inftime = Gtk.Label()
            self.label_inftime.set_justify(Gtk.Justification.LEFT)
            self.label_inftime.set_markup("<span font=\'%d\' color='#FFFFFFFF'><b>inf.time:\n</b></span>" % self.ui_cairo_font_size)
            self.info_box.pack_start(self.label_inftime,True,False,2)
            self.inf_time = Gtk.Label()
            self.inf_time.set_justify(Gtk.Justification.FILL)
            self.info_box.pack_start(self.inf_time,True,False,2)
        else :
            # still picture mode
            self.info_box = Gtk.VBox()
            self.info_box.set_name("gui_overlay_stbox")
            if args.edgetpu is False :
                self.st_icon_path = RESOURCES_DIRECTORY + 'st_icon_next_inference_' + self.ui_icon_st_width + 'x' + self.ui_icon_st_height + '.png'
            else :
                self.st_icon_path = RESOURCES_DIRECTORY + 'st_icon_tpu_next_inference_' + self.ui_icon_st_width + 'x' + self.ui_icon_st_height + '.png'
            self.st_icon = Gtk.Image.new_from_file(self.st_icon_path)
            self.st_icon_event = Gtk.EventBox()
            self.st_icon_event.add(self.st_icon)
            self.st_icon_event.connect("button_press_event",self.still_picture)
            self.info_box.pack_start(self.st_icon_event,True,False,2)
            self.label_inftime = Gtk.Label()
            self.label_inftime.set_justify(Gtk.Justification.LEFT)
            self.label_inftime.set_markup("<span font=\'%d\' color='#FFFFFFFF'><b>inf.time:\n</b></span>" % self.ui_cairo_font_size)
            self.info_box.pack_start(self.label_inftime,True,False,2)
            self.inf_time = Gtk.Label()
            self.inf_time.set_justify(Gtk.Justification.FILL)
            self.info_box.pack_start(self.inf_time,True,False,2)
            self.label_acc = Gtk.Label()
            self.label_acc.set_justify(Gtk.Justification.LEFT)
            self.label_acc.set_markup("<span font=\'%d\' color='#FFFFFFFF'><b>accuracy:\n</b></span>" % self.ui_cairo_font_size)
            self.info_box.pack_start(self.label_acc,True,False,2)
            self.acc = Gtk.Label()
            self.acc.set_justify(Gtk.Justification.FILL)
            self.info_box.pack_start(self.acc,True,False,2)

        # setup video box containing a transparent drawing area
        # to draw over the video stream
        self.video_box = Gtk.HBox()
        self.video_box.set_name("gui_overlay_video")
        self.video_box.set_app_paintable(True)
        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.connect("draw", self.drawing)
        self.drawing_area.set_name("overlay_draw")
        self.drawing_area.set_app_paintable(True)
        self.video_box.pack_start(self.drawing_area, True, True, 0)
        
        # setup the exit box which contains the exit button
        self.exit_box = Gtk.VBox()
        self.exit_box.set_name("gui_overlay_exit")
        self.exit_icon_path = RESOURCES_DIRECTORY + 'exit_' + self.ui_icon_exit_width + 'x' + self.ui_icon_exit_height + '.png'
        self.exit_icon = Gtk.Image.new_from_file(self.exit_icon_path)
        self.exit_icon_event = Gtk.EventBox()
        self.exit_icon_event.add(self.exit_icon)
        self.exit_icon_event.connect("button_press_event",self.exit_icon_cb)
        self.exit_box.pack_start(self.exit_icon_event,False,False,2)

        # setup main box which group the three previous boxes
        self.main_box =  Gtk.HBox()
        self.exit_box.set_name("gui_overlay")
        self.main_box.pack_start(self.info_box,False,False,0)
        self.main_box.pack_start(self.video_box,True,True,0)
        self.main_box.pack_start(self.exit_box,False,False,0)
        self.add(self.main_box)
        return True

    def drawing(self, widget, cr):
        """
        Drawing callback used to draw with cairo on
        the drawing area
        """
        if self.app.first_drawing_call :
            self.app.first_drawing_call = False
            self.drawing_width = widget.get_allocated_width()
            self.drawing_height = widget.get_allocated_height()
            cr.set_font_size(self.ui_cairo_font_size_label)
            self.label_printed = True
            if self.app.enable_camera_preview == False :
                self.app.still_picture_next = True
                if args.validation:
                    GLib.idle_add(self.app.process_picture)
                else:
                    self.app.process_picture()
            return False
        if (self.app.label_to_display == ""):
            # waiting screen
            text = "Load nn_model"
            cr.set_font_size(self.ui_cairo_font_size_label)
            xbearing, ybearing, width, height, xadvance, yadvance = cr.text_extents(text)
            cr.move_to((self.drawing_width/2-width/2),(self.drawing_height/2))
            cr.text_path(text)
            cr.set_source_rgb(0.235, 0.71, 0.90)
            cr.fill_preserve()
            cr.set_source_rgb(0.012, 0.137, 0.294)
            cr.set_line_width(1)
            cr.stroke()
            return True
        else :
            cr.set_font_size(self.ui_cairo_font_size_label)
            self.label_printed = True
            if args.validation:
                self.app.still_picture_next = True
            # running screen
            xbearing, ybearing, width, height, xadvance, yadvance = cr.text_extents(self.app.label_to_display)
            cr.move_to((self.drawing_width/2-width/2),((9/10)*self.drawing_height))
            cr.text_path(self.app.label_to_display)
            cr.set_source_rgb(1, 1, 1)
            cr.fill_preserve()
            cr.set_source_rgb(0, 0, 0)
            cr.set_line_width(0.7)
            cr.stroke()
            return True
    
    # Updating the labels and the inference infos displayed on the GUI interface - camera input
    def update_label_preview(self):
        """
        Updating the labels and the inference infos displayed on the GUI interface - camera input
        """
        inference_time = self.app.nn_inference_time * 1000
        inference_fps = self.app.nn_inference_fps
        display_fps = self.app.gst_widget.instant_fps
        labels = self.app.nn.get_labels()
        label = labels[self.app.nn_result_label]
        
        if (args.validation) and (inference_time != 0) and (self.app.valid_draw_count > 5):
            self.app.valid_preview_fps.append(round(self.app.gst_widget.instant_fps))
            self.app.valid_inference_time.append(round(self.app.nn_inference_time * 1000, 4))
        
        str_inference_time = str("{0:0.1f}".format(inference_time))
        str_display_fps = str("{0:.1f}".format(display_fps))
        str_inference_fps = str("{0:.1f}".format(inference_fps))

        self.inf_time.set_markup("<span font=\'%d\' color='#FFFFFFFF'><b>%sms\n</b></span>" % (self.ui_cairo_font_size,str_inference_time))
        self.inf_fps.set_markup("<span font=\'%d\' color='#FFFFFFFF'><b>%sfps\n</b></span>" % (self.ui_cairo_font_size,str_inference_fps))
        self.disp_fps.set_markup("<span font=\'%d\' color='#FFFFFFFF'><b>%sfps\n</b></span>" % (self.ui_cairo_font_size,str_display_fps))
        self.app.label_to_display = label


        if args.validation:
            # reload the timeout
            GLib.source_remove(self.app.valid_timeout_id)
            self.app.valid_timeout_id = GLib.timeout_add(10000,
                                                     self.app.valid_timeout_callback)

            self.app.valid_draw_count = self.app.valid_draw_count + 1
            # stop the application after 150 draws
            if self.app.valid_draw_count > 150:
                avg_prev_fps = sum(self.app.valid_preview_fps) / len(self.app.valid_preview_fps)
                avg_inf_time = sum(self.app.valid_inference_time) / len(self.app.valid_inference_time)
                avg_inf_fps = (1000/avg_inf_time)
                print("avg display fps= " + str(avg_prev_fps))
                print("avg inference fps= " + str(avg_inf_fps))
                print("avg inference time= " + str(avg_inf_time) + " ms")
                GLib.source_remove(self.app.valid_timeout_id)
                self.destroy()
                Gtk.main_quit()    
    
    def still_picture(self,  widget, event):
        """
        ST icon cb which trigger a new inference
        """
        self.app.still_picture_next = True
        return self.app.process_picture()
    
class Application:
    """
    Class that handles the whole application 
    """
    def __init__(self, args):
        #init variables uses :
        self.exit_app = False
        self.dcmipp_camera = False
        self.first_drawing_call = True
        self.first_call = True
        #if args.image is empty -> camera preview mode else still picture
        if args.image == "":
            print("camera preview mode activate")
            self.enable_camera_preview = True
            #Test if a camera is connected
            check_camera_cmd = RESOURCES_DIRECTORY + "check_camera_preview.sh"
            check_camera = subprocess.run(check_camera_cmd)
            if check_camera.returncode==1:
                print("no camera connected")
                exit(1)
            self.video_device,self.camera_caps=self.setup_camera()
        else:
            print("still picture mode activate")
            self.enable_camera_preview = False
            self.still_picture_next = False
        # initialize the list of the file to be processed (used with the
        # --image parameter)
        self.files = []
        # initialize the list of inference/display time to process the average
        # (used with the --validation parameter)
        self.valid_inference_time = []
        self.valid_inference_fps = []
        self.valid_preview_fps = []
        self.valid_draw_count = 0
        
        #instantiate the Neural Network class
        self.nn = NeuralNetwork(args.model_file, args.label_file, float(args.input_mean), float(args.input_std), args.edgetpu, args.perf, args.ext_delegate)
        self.shape = self.nn.get_img_size()
        self.nn_input_width = self.shape[1]
        self.nn_input_height = self.shape[0]
        self.nn_input_channel = self.shape[2]
        self.nn_inference_time = 0.0
        self.nn_inference_fps = 0.0
        self.nn_result_accuracy = 0.0
        self.nn_result_label = 0
        self.label_to_display = ""
        
        #instantiate the Gstreamer pipeline
        self.gst_widget = GstWidget(self,self.nn) 
        #instantiate the main window
        self.main_window = MainWindow(args,self)
        #instantiate the overlay window
        self.overlay_window = OverlayWindow(args,self)
        self.main()
   
    def setup_camera(self):
        width = str(args.frame_width)
        height = str(args.frame_height)
        framerate = str(args.framerate)
        device = str(args.video_device)
        config_camera = RESOURCES_DIRECTORY + "setup_camera.sh " + width + " " + height + " " + framerate + " " + device
        x = subprocess.check_output(config_camera,shell=True)
        x = x.decode("utf-8")
        x = x.split("\n")
        for i in x :
            if "V4L_DEVICE" in i:     
                video_device = i.lstrip('V4L_DEVICE=')
            if "V4L2_CAPS" in i:
                camera_caps = i.lstrip('V4L2_CAPS=')
        return video_device, camera_caps
    
    def valid_timeout_callback(self):
        """
        if timeout occurs that means that camera preview and the gtk is not
        behaving as expected
        """
        print("Timeout: camera preview and/or gtk is not behaving has expected\n");
        Gtk.main_quit()
        os._exit(1)

    # get random file in a directory
    def getRandomFile(self, path):
        """
        Returns a random filename, chosen among the files of the given path.
        """
        if len(self.files) == 0:
            self.files = os.listdir(path)

        if len(self.files) == 0:
            return '';

        # remove .json file
        item_to_remove = []
        for item in self.files:
            if item.endswith(".json"):
                item_to_remove.append(item)

        for item in item_to_remove:
            self.files.remove(item)

        index = random.randrange(0, len(self.files))
        file_path = self.files[index]
        self.files.pop(index)
        return file_path
    
    def load_valid_results_from_json_file(self, json_file):
        """
        Load json files containing expected results for the validation mode
        """
        json_file = json_file + '.json'
        name = []
        x0 = []
        y0 = []
        x1 = []
        y1 = []
        with open(args.image + "/" + json_file) as json_file:
            data = json.load(json_file)
            for obj in data['objects_info']:
                name.append(obj['name'])
                x0.append(obj['x0'])
                y0.append(obj['y0'])
                x1.append(obj['x1'])
                y1.append(obj['y1'])

        return name, x0, y0, x1, y1  
    
    def process_picture(self):
        """
        Still picture inference function
        Load the frame, launch inference and
        call functions to refresh UI
        """
        if self.exit_app:
            Gtk.main_quit()
            return False

        if self.still_picture_next and self.overlay_window.label_printed:
            # get randomly a picture in the directory
            rfile = self.getRandomFile(args.image)
            img = Image.open(args.image + rfile)
            picture_width, picture_height = img.size

            # display the picture in the screen
            frame_ratio = picture_width/picture_height
            frame_height = self.main_window.screen_height - 32
            frame_width = int(frame_ratio * frame_height)

            # trying to keep aspect ratio of the image if possible but
            # if not fill the drawing space as possible
            if (frame_width > self.overlay_window.drawing_width):
                frame_width = self.overlay_window.drawing_width
            prev_frame = cv2.resize(np.array(img), (frame_width, frame_height))

            # update the preview frame
            self.main_window.update_frame(prev_frame)
            self.overlay_window.label_printed = False

            # execute the inference
            nn_frame = cv2.resize(np.array(img), (self.nn_input_width, self.nn_input_height))
            start_time = timer()
            self.nn.launch_inference(nn_frame)
            stop_time = timer()
            self.still_picture_next = False;
            self.nn_inference_time = stop_time - start_time
            self.nn_inference_fps = (1000/(self.nn_inference_time*1000))
            self.nn_result_accuracy, self.nn_result_label = self.nn.get_results()

            # write information onf the GTK UI
            labels = self.nn.get_labels()
            label = labels[self.nn_result_label]
            accuracy = self.nn_result_accuracy * 100
            inference_time = self.nn_inference_time * 1000

            if args.validation and inference_time != 0:
                # reload the timeout
                GLib.source_remove(self.valid_timeout_id)
                self.valid_timeout_id = GLib.timeout_add(10000,
                                                         self.valid_timeout_callback)
                # get file name
                file_name = os.path.basename(rfile)
                # remove the extension
                file_name = os.path.splitext(file_name)[0]
                # remove eventual '_'
                file_name = file_name.rsplit('_')[0]
                # store the inference time in a list so that we can compute the
                # average later on
                if self.first_call :
                    #skip first inference time to avoid warmup time in EdgeTPU mode
                    self.first_call = False
                else :
                    self.valid_inference_time.append(round(self.nn_inference_time * 1000, 4))
                print("name extract from the picture file: {0:32} label {1}".format(file_name, str(label)))
                if file_name != str(label):
                    print("Inference result mismatch the file name")
                    self.destroy()
                    os._exit(1);
                # process all the file
                if len(self.files) == 0:
                    avg_inf_time = sum(self.valid_inference_time) / len(self.valid_inference_time)
                    avg_inf_time = round(avg_inf_time,4)
                    print("avg inference time= " + str(avg_inf_time) + " ms")
                    self.exit_app = True
            #update label
            self.overlay_window.update_label_still(str(label), accuracy, inference_time)
            self.overlay_window.queue_draw()
            return True
        else :
            return False

    def update_ui(self):
        self.overlay_window.update_label_preview()
        self.overlay_window.queue_draw()
     
    def main(self):
    
        self.main_window.connect("delete-event", Gtk.main_quit)
        self.main_window.show_all()
        self.overlay_window.connect("delete-event", Gtk.main_quit)
        self.overlay_window.show_all()
        # start a timeout timer in validation process to close application if
        # timeout occurs
        if args.validation:
            self.valid_timeout_id = GLib.timeout_add(35000,
                                                     self.valid_timeout_callback)
        return True

if __name__ == '__main__':
    # add signal to catch CRTL+C
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    #Tensorflow Lite NN intitalisation
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--image", default="", help="image directory with image to be classified")
    parser.add_argument("-v", "--video_device", default="", help="video device ex: video0")
    parser.add_argument("--frame_width", default=640, help="width of the camera frame (default is 640)")
    parser.add_argument("--frame_height", default=480, help="height of the camera frame (default is 480)")
    parser.add_argument("--framerate", default=15, help="framerate of the camera (default is 15fps)")
    parser.add_argument("-m", "--model_file", default="", help=".tflite model to be executed")
    parser.add_argument("-l", "--label_file", default="", help="name of file containing labels")
    parser.add_argument("-e", "--ext_delegate",default = None, help="external_delegate_library path")
    parser.add_argument("-p", "--perf", default='std', choices= ['std', 'max'], help="[EdgeTPU ONLY] Select the performance of the Coral EdgeTPU")
    parser.add_argument("--edgetpu", action='store_true', help="enable Coral EdgeTPU acceleration")
    parser.add_argument("--input_mean", default=127.5, help="input mean")
    parser.add_argument("--input_std", default=127.5, help="input standard deviation")
    parser.add_argument("--validation", action='store_true', help="enable the validation mode")
    parser.add_argument("--num_threads", default=None, help="Select the number of threads used by tflite interpreter to run inference")
    args = parser.parse_args()

    try:
        application = Application(args)

    except Exception as exc:
        print("Main Exception: ", exc )

    Gtk.main()
    print("gtk main finished")
    print("application exited properly")
    os._exit(0)
 
    