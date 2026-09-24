from libs.PipeLine import PipeLine
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from libs.Utils import *
import os,sys,ujson,gc,math
from media.media import *
import nncase_runtime as nn
import ulab.numpy as np
import image
import aidemo

# 自定义YOLOv8 Obb类
class ObbDetectionApp(AIBase):
    def __init__(self,kmodel_path,labels,model_input_size,max_boxes_num,confidence_threshold=0.5,nms_threshold=0.2,rgb888p_size=[224,224],display_size=[1920,1080],debug_mode=0):
        super().__init__(kmodel_path,model_input_size,rgb888p_size,debug_mode)
        self.kmodel_path=kmodel_path
        self.labels=labels
        self.d = {i: 0 for i in range(len(self.labels))}
        # 模型输入分辨率
        self.model_input_size=model_input_size
        # 阈值设置
        self.confidence_threshold=confidence_threshold
        self.nms_threshold=nms_threshold
        self.max_boxes_num=max_boxes_num
        # sensor给到AI的图像分辨率
        self.rgb888p_size=[rgb888p_size[0],rgb888p_size[1]]
        # 显示分辨率
        self.display_size=[display_size[0],display_size[1]]
        self.debug_mode=debug_mode
        # 检测框预置颜色值
        self.color_four=get_colors(len(self.labels))
        self.scale=1.0
        # Ai2d实例，用于实现模型预处理
        self.ai2d=Ai2d(debug_mode)
        # 设置Ai2d的输入输出格式和类型
        self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,nn.ai2d_format.NCHW_FMT,np.uint8, np.uint8)


    # 配置预处理操作，这里使用了resize，Ai2d支持crop/shift/pad/resize/affine，具体代码请打开/sdcard/app/libs/AI2D.py查看
    def config_preprocess(self,input_image_size=None):
        with ScopedTiming("set preprocess config",self.debug_mode > 0):
            # 初始化ai2d预处理配置，默认为sensor给到AI的尺寸，您可以通过设置input_image_size自行修改输入尺寸
            ai2d_input_size=input_image_size if input_image_size else self.rgb888p_size
            top,bottom,left,right,self.scale=letterbox_pad_param(self.rgb888p_size,self.model_input_size)
            # 配置padding预处理
            self.ai2d.pad([0,0,0,0,top,bottom,left,right], 0, [128,128,128])
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            self.ai2d.build([1,3,ai2d_input_size[1],ai2d_input_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])

    # 自定义当前任务的后处理
    def postprocess(self,results):
        with ScopedTiming("postprocess",self.debug_mode > 0):
            new_result=results[0][0].transpose()
            obb_res = aidemo.yolo_obb_postprocess(new_result.copy(),[self.rgb888p_size[1],self.rgb888p_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self.display_size[1],self.display_size[0]],len(self.labels),self.confidence_threshold,self.nms_threshold,self.max_boxes_num)
            return obb_res

    # 绘制结果
    def draw_result(self,pl,dets):
        with ScopedTiming("display_draw",self.debug_mode >0):
            pl.osd_img.clear()
            if dets:
                for i in range(len(dets[0])):
                    x1, y1, x2,y2,x3,y3,x4,y4 = map(lambda x: int(round(x, 0)), dets[0][i])
                    pl.osd_img.draw_line(int(x1),int(y1),int(x2),int(y2),color=self.color_four[dets[1][i]],thickness=4)
                    pl.osd_img.draw_line(int(x2),int(y2),int(x3),int(y3),color=self.color_four[dets[1][i]],thickness=4)
                    pl.osd_img.draw_line(int(x3),int(y3),int(x4),int(y4),color=self.color_four[dets[1][i]],thickness=4)
                    pl.osd_img.draw_line(int(x4),int(y4),int(x1),int(y1),color=self.color_four[dets[1][i]],thickness=4)
                    pl.osd_img.draw_string_advanced(x1, y1,24,str(dets[1][i]) , color=self.color_four[dets[1][i]])
                    self.d[dets[1][i]]+=1
                text=""
                for j in range(len(self.labels)):
                    if self.d[j]!=0:
                        text+=self.labels[j]+": "+str(self.d[j])+";  "
                        self.d[j]=0
                pl.osd_img.draw_string_advanced(50, 50,24,text, color=[0,255,0])


if __name__=="__main__":
    # auto按开发板选择默认驱动；可手动改为hdmi/lcd/st7701/nt35516等模式
    display_mode="auto"
    # None使用SDK默认分辨率；更换屏幕规格时手动指定，如[640, 480]
    display_size=None
    rgb888p_size=[1280,720]
    # 模型路径
    kmodel_path="/sdcard/examples/kmodel/yolov8n-obb.kmodel"
    labels = ['plane','ship','storage tank','baseball diamond','tennis court','basketball court','ground track field','harbor','bridge','large vehicle','small vehicle','helicopter','roundabout','soccer ball field','swimming pool']
    # 其它参数设置
    confidence_threshold = 0.1
    nms_threshold = 0.6
    max_boxes_num = 100
    # 初始化PipeLine，rgb888p_size为传给AI的图像分辨率，display_size为显示分辨率
    pl=PipeLine(rgb888p_size=rgb888p_size,display_mode=display_mode, display_size=display_size)
    # 创建PipeLine，可按需传入sensor_id选择摄像头，例如pl.create(sensor_id=2)
    pl.create()
    display_size=pl.get_display_size()
    # 初始化自定义旋转目标检测实例
    obb_det=ObbDetectionApp(kmodel_path,labels=labels,model_input_size=[320,320],max_boxes_num=max_boxes_num,confidence_threshold=confidence_threshold,nms_threshold=nms_threshold,rgb888p_size=rgb888p_size,display_size=display_size,debug_mode=0)
    obb_det.config_preprocess()
    while True:
        with ScopedTiming("total",1):
            # 获取当前帧数据
            img=pl.get_frame()
            # 推理当前帧
            res=obb_det.run(img)
            # 绘制结果到PipeLine的osd图像
            obb_det.draw_result(pl,res)
            # 显示当前的绘制结果
            pl.show_image()
            gc.collect()
    obb_det.deinit()
    pl.destroy()

