"""
Script: kpu_run_fps.py
脚本名称：kpu_run_fps.py

Description:
    This script benchmarks the inference frame rate (FPS) of a YOLOv8 KPU model 
    on an embedded system. It reads an input image, resizes it using Ai2d to match 
    the model input size, runs inference repeatedly, and prints the resulting FPS.

    The script uses the nncase_runtime KPU and Ai2d APIs to perform preprocessing 
    and inference, enabling evaluation of real-time performance in a deployed scenario.

脚本说明：
    本脚本用于在嵌入式系统上测试 YOLOv8 KPU 模型的推理帧率（FPS）。
    它读取一张图像，使用 Ai2d 工具调整为模型所需分辨率，然后循环运行推理并输出帧率。

    脚本依赖 nncase_runtime 的 KPU 和 Ai2d 接口，完成图像预处理与推理，适用于部署环境下的性能评估。

Author: Canaan Developer
作者：Canaan 开发者
"""


import os
import ujson
import nncase_runtime as nn
import ulab.numpy as np
import image
import sys
import gc
import time

# 加载kmodel
kmodel_path="/sdcard/examples/kmodel/fruit_det_yolov8n_320.kmodel"
input_w=320
input_h=320

# 初始化kpu
kpu=nn.kpu()
kpu.load_kmodel(kmodel_path)

# 创建一个空的输入tensor,并将其设置为模型的第0个输入
input_data = np.ones((1,3,input_h,input_w),dtype=np.uint8)
kpu_input_tensor = nn.from_numpy(input_data)
kpu.set_input_tensor(0, kpu_input_tensor)

# 读取一张图片，并将其transpose成chw数据
img_path="/sdcard/examples/utils/test_fruit.jpg"
img_data = image.Image(img_path).to_rgb888()
img_hwc=img_data.to_numpy_ref()
shape=img_hwc.shape
img_tmp = img_hwc.reshape((shape[0] * shape[1], shape[2]))
img_tmp_trans = img_tmp.transpose().copy()
img_chw=img_tmp_trans.reshape((shape[2],shape[0],shape[1]))

# 初始化ai2d预处理，并配置ai2d resize预处理，预处理输入分辨率为图片分辨率，输出分辨率模型输入的需求分辨率，实现image->preprocess->model的过程
ai2d=nn.ai2d()
ai2d.set_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT, np.uint8, np.uint8)
ai2d.set_resize_param(True,nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
ai2d_builder = ai2d.build([1,3,img_chw.shape[1],img_chw.shape[2]], [1,3,input_h,input_w])
ai2d_input_tensor = nn.from_numpy(img_chw)
# 运行ai2d，将输出直接送到kpu_input_tensor
ai2d_builder.run(ai2d_input_tensor, kpu_input_tensor)

# 测试推理帧率
fps = time.clock()
while True:
    os.exitpoint()
    try:
        fps.tick()
        kpu.run()
        print(fps.fps())
    except KeyboardInterrupt as e:
        print("user stop: ", e)
        break
    except BaseException as e:
        import sys
        sys.print_exception(e)
        raise
