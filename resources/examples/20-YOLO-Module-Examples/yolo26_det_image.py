from libs.YOLO import YOLO26
from libs.Utils import *
import os,sys,gc
import ulab.numpy as np
import image

if __name__=="__main__":
    # 这里仅为示例，自定义场景请修改为您自己的测试图片、模型路径、标签名称、模型输入大小
    img_path="/sdcard/examples/utils/test_fruit.jpg"
    kmodel_path="/sdcard/examples/kmodel/fruit_det_yolo26n_320.kmodel"
    labels = ["apple","banana","orange"]
    model_input_size=[320,320]

    confidence_threshold = 0.5
    img,img_ori=read_image(img_path)
    rgb888p_size=[img.shape[2],img.shape[1]]
    # 初始化 YOLO26 模型
    yolo=YOLO26(task_type="detect",mode="image",kmodel_path=kmodel_path,labels=labels,rgb888p_size=rgb888p_size,model_input_size=model_input_size,conf_thresh=confidence_threshold,max_boxes_num=50,debug_mode=0)
    yolo.config_preprocess()
    res=yolo.run(img)
    print(res)
    yolo.draw_result(res,img_ori)
    yolo.deinit()
    gc.collect()
