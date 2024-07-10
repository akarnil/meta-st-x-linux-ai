#!/bin/sh
weston_user=$(ps aux | grep '/usr/bin/weston '|grep -v 'grep'|awk '{print $1}')
echo $weston_user
dbus_obj_name="org.freedesktop.IOTC.AIServer"
conf_string="<!DOCTYPE busconfig PUBLIC \
          \"-//freedesktop//DTD D-BUS Bus Configuration 1.0//EN\" \
          \"http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd\"> \
<busconfig> \
  <!-- Only root or user weston can own this service --> \
  <policy user=\"${weston_user}\"> \
    <allow own=\"${dbus_obj_name}\"/> \
  </policy> \
  <policy user=\"root\"> \
    <allow own=\"${dbus_obj_name}\"/> \
  </policy> \
 \
  <policy user=\"${weston_user}\"> \
    <allow send_destination=\"${dbus_obj_name}\"/> \
    <allow receive_sender=\"${dbus_obj_name}\"/> \
  </policy> \
  <policy user=\"root\"> \
    <allow send_destination=\"${dbus_obj_name}\"/> \
    <allow receive_sender=\"${dbus_obj_name}\"/> \
  </policy> \
</busconfig>"""
echo $conf_string
service_conf_file="/etc/dbus-1/system.d/${dbus_obj_name}.conf"
if [ ! -f service_conf_file ];
then
    echo $conf_string > $service_conf_file
fi
source /usr/local/demo-ai/computer-vision/tflite-object-detection/python/resources/config_board.sh
cmd="python3 /usr/local/demo-ai/computer-vision/tflite-object-detection/python/objdetect_tfl.py -m /usr/local/demo-ai/computer-vision/models/coco_ssd_mobilenet/detect.tflite -l /usr/local/demo-ai/computer-vision/models/coco_ssd_mobilenet/labels.txt --framerate $DFPS --frame_width $DWIDTH --frame_height $DHEIGHT $COMPUTE_ENGINE --dbus_obj $dbus_obj_name"
if [ "$weston_user" != "root" ]; then
	echo "user : "$weston_user
	script -qc "su -l $weston_user -c '$cmd'"
else
	$cmd
fi
