#!/bin/sh
weston_user=$(ps aux | grep '/usr/bin/weston '|grep -v 'grep'|awk '{print $1}')
source /usr/local/demo-ai/computer-vision/onnx-object-detection/python/resources/config_board.sh
cmd="python3 /usr/local/demo-ai/computer-vision/onnx-object-detection/python/objdetect_onnx.py -m /usr/local/demo-ai/computer-vision/models/coco_ssd_mobilenet/detect.onnx -l /usr/local/demo-ai/computer-vision/models/coco_ssd_mobilenet/labels_onnx.txt --framerate $DFPS --frame_width $DWIDTH --frame_height $DHEIGHT $COMPUTE_ENGINE"
if [ "$weston_user" != "root" ]; then
	echo "user : "$weston_user
	script -qc "su -l $weston_user -c '$cmd'"
else
	$cmd
fi
