from libs.PipeLine import PipeLine
from libs.YOLO import YOLO11
from libs.Utils import *
import os,sys,gc
import ulab.numpy as np
import image

if __name__=="__main__":
    # 这里仅为示例，自定义场景请修改为您自己的模型路径、标签名称、模型输入大小,关键点数量和关键点维度
    kmodel_path="/sdcard/examples/kmodel/yolo11n-pose.kmodel"
    labels = ["person"]
    model_input_size=[320,320]
    kp_num=17
    kp_dim=3

    # auto按开发板选择默认驱动；可手动覆盖为hdmi/lcd/st7701等模式
    display_mode="auto"
    # None使用SDK默认分辨率；更换屏幕时可指定[640, 480]等尺寸
    display_size=None
    rgb888p_size=[320,320]
    confidence_threshold = 0.5
    nms_threshold=0.45
    pl=PipeLine(rgb888p_size=rgb888p_size,display_mode=display_mode,display_size=display_size)
    pl.create()
    display_size=pl.get_display_size()
    # 初始化YOLO11实例
    yolo=YOLO11(task_type="pose",mode="video",kmodel_path=kmodel_path,labels=labels,rgb888p_size=rgb888p_size,model_input_size=model_input_size,display_size=display_size,kp_num=kp_num,kp_dim=kp_dim,conf_thresh=confidence_threshold,nms_thresh=nms_threshold,max_boxes_num=50,debug_mode=0)
    yolo.config_preprocess()
    while True:
        with ScopedTiming("total",1):
            img=pl.get_frame()
            res=yolo.run(img)
            yolo.draw_result(res,pl.osd_img)
            pl.show_image()
            gc.collect()
    yolo.deinit()
    pl.destroy()
