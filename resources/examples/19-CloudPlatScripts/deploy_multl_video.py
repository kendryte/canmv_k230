# -*- coding: utf-8 -*-
'''
Script: deploy_multl_video.py
脚本名称：deploy_multl_video.py

Description:
    This script runs a real-time multi-label classification application on an embedded device.
    It uses a pipeline to capture video frames, performs inference using a pre-trained Kmodel,
    and displays the classification results on screen.

    The model configuration is retrieved from the Canaan online training platform via a JSON config file.

脚本说明：
    本脚本在嵌入式设备上运行实时多标签分类应用。它通过捕获视频帧，使用预训练的 Kmodel 进行推理，并在屏幕上显示分类结果。

    模型配置文件通过 Canaan 在线训练平台从 JSON 文件获取。

Author: Canaan Developer
作者：Canaan 开发者
'''


import os, gc
from libs.PlatTasks import MultiLabelClassificationApp
from libs.PipeLine import PipeLine
from libs.Utils import *

# Set display mode: options are 'hdmi', 'lcd', 'lt9611', 'st7701', 'hx8399'
# auto按开发板选择默认驱动；可手动覆盖为hdmi/lcd/st7701等模式
display_mode="auto"
# None使用SDK默认分辨率；更换屏幕时可指定[640, 480]等尺寸
display_size=None

# Define the input size for the RGB888P video frames
rgb888p_size = [1280, 720]

# Set root directory path for model and config
root_path = "/sdcard/mp_deployment_source/"

# Load deployment configuration
deploy_conf = read_json(root_path + "/deploy_config.json")
kmodel_path = root_path + deploy_conf["kmodel_path"]               # KModel path
labels = deploy_conf["categories"]                                 # Label list
confidence_threshold = deploy_conf["confidence_threshold"]         # Confidence threshold for classification
model_input_size = deploy_conf["img_size"]                         # Model input size
inference_mode = "video"                                           # Inference mode: 'video'
debug_mode = 0                                                     # Debug mode flag

# Initialize the PipeLine. rgb888p_size is the AI input resolution and display_size is the display resolution
pl = PipeLine(rgb888p_size=rgb888p_size, display_mode=display_mode, display_size=display_size)
# Create the PipeLine. Pass sensor_id to select a camera when needed, for example pl.create(sensor_id=2)
pl.create()
display_size = pl.get_display_size()

# Initialize multi-label classification application
multl_app = MultiLabelClassificationApp(inference_mode,kmodel_path,labels,model_input_size,confidence_threshold,rgb888p_size,display_size,debug_mode=debug_mode)

multl_app.config_preprocess()

# Main loop: capture, run inference, display results
while True:
    with ScopedTiming("total", 1):
        img = pl.get_frame()                          # Capture current frame
        res = multl_app.run(img)                      # Run inference
        multl_app.draw_result(pl.osd_img, res)        # Draw classification results
        pl.show_image()                               # Show final image on display
        gc.collect()                                  # Run garbage collection to free memory

# Cleanup: These lines will only run if the loop is interrupted (e.g., by an IDE break or external interruption)
multl_app.deinit()                                    # De-initialize multi-label classification application
pl.destroy()                                          # Destroy pipeline instance
