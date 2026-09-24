# -*- coding: utf-8 -*-
'''
Script: deploy_ml_video.py
脚本名称：deploy_ml_video.py

Description:
    This script runs a real-time metric learning application on an embedded device.
    It uses a pipeline to capture video frames, performs inference using a pre-trained Kmodel,
    and displays the closest matching category from the loaded examples.

    The model configuration is retrieved from the Canaan online training platform via a JSON config file.

脚本说明：
    本脚本在嵌入式设备上运行实时度量学习应用。它通过捕获视频帧，使用预训练的 Kmodel 进行推理，并从已加载的样本中显示最接近的匹配类别。

    模型配置文件通过 Canaan 在线训练平台从 JSON 文件获取。

Author: Canaan Developer
作者：Canaan 开发者
'''


import os, gc
from libs.PlatTasks import MetricLearningApp
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
kmodel_path = root_path + deploy_conf["kmodel_path"]               # Model path
confidence_threshold = deploy_conf["confidence_threshold"]         # Confidence threshold for classification
model_input_size = deploy_conf["img_size"]                         # Model input size

# Initialize metric learning application
inference_mode = "video"                                           # Inference mode: 'video'
debug_mode = 0                                                     # Debug mode flag

# Initialize the PipeLine. rgb888p_size is the AI input resolution and display_size is the display resolution
pl = PipeLine(rgb888p_size=rgb888p_size, display_mode=display_mode, display_size=display_size)
# Create the PipeLine. Pass sensor_id to select a camera when needed, for example pl.create(sensor_id=2)
pl.create()
display_size = pl.get_display_size()

ml_app = MetricLearningApp(inference_mode, kmodel_path, model_input_size,confidence_threshold, rgb888p_size, display_size, debug_mode=debug_mode)

# Configure preprocessing for the model
ml_app.config_preprocess()

# Load example images and their category labels for comparison
ml_app.load_image("/sdcard/examples/ai_test_utils/0.jpg", "菠菜")                      # Load "Spinach" image
ml_app.load_image("/sdcard/examples/ai_test_utils/1.jpg", "菠菜")                      # Load another "Spinach" image
ml_app.load_image("/sdcard/examples/ai_test_utils/4.jpg", "长茄子")                    # Load "Eggplant" image
ml_app.load_image("/sdcard/examples/ai_test_utils/5.jpg", "长茄子")                    # Load another "Eggplant" image
ml_app.load_image("/sdcard/examples/ai_test_utils/6.jpg", "胡萝卜")                    # Load "Carrot" image
ml_app.load_image("/sdcard/examples/ai_test_utils/7.jpg", "胡萝卜")                    # Load another "Carrot" image

# Main loop: capture, run inference, display results
while True:
    with ScopedTiming("total", 1):
        img = pl.get_frame()                          # Capture current frame
        res = ml_app.run(img)                         # Run inference on the frame
        ml_app.draw_result(pl.osd_img, res)           # Draw classification result
        pl.show_image()                               # Show final image on display
        gc.collect()                                  # Run garbage collection to free memory

# Cleanup: These lines will only run if the loop is interrupted (e.g., by an IDE break or external interruption)
ml_app.deinit()                                       # De-initialize metric learning app
pl.destroy()                                          # Destroy pipeline instance
