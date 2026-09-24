from libs.PipeLine import PipeLine
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from libs.Utils import *
import os,sys,ujson,gc,math
from media.media import *
import nncase_runtime as nn
import ulab.numpy as np
import image
import aicube

# 自定义分类任务类
class ClassificationApp(AIBase):
    def __init__(self,kmodel_path,labels,model_input_size=[224,224],confidence_threshold=0.7,rgb888p_size=[224,224],display_size=[1920,1080],debug_mode=0):
        super().__init__(kmodel_path,model_input_size,rgb888p_size,debug_mode)
        self.kmodel_path=kmodel_path
        # 分类标签
        self.labels=labels
        # 模型输入分辨率
        self.model_input_size=model_input_size
        # 分类阈值
        self.confidence_threshold=confidence_threshold
        # sensor给到AI的图像分辨率,宽16字节对齐
        self.rgb888p_size=[ALIGN_UP(rgb888p_size[0],16),rgb888p_size[1]]
        # 显示分辨率，宽16字节对齐
        self.display_size=[ALIGN_UP(display_size[0],16),display_size[1]]
        self.debug_mode=debug_mode
        # Ai2d实例，用于实现模型预处理
        self.ai2d=Ai2d(debug_mode)
        # 设置Ai2d的输入输出格式和类型
        self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,nn.ai2d_format.NCHW_FMT,np.uint8, np.uint8)

    # 配置预处理操作，这里使用了resize，Ai2d支持crop/shift/pad/resize/affine，具体代码请打开/sdcard/app/libs/AI2D.py查看
    def config_preprocess(self,input_image_size=None):
        with ScopedTiming("set preprocess config",self.debug_mode > 0):
            # 初始化ai2d预处理配置，默认为sensor给到AI的尺寸，您可以通过设置input_image_size自行修改输入尺寸
            ai2d_input_size=input_image_size if input_image_size else self.rgb888p_size
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            # build参数包含输入shape和输出shape
            self.ai2d.build([1,3,ai2d_input_size[1],ai2d_input_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])

    # 自定义当前任务的后处理，results是模型输出的array列表
    def postprocess(self,results):
        with ScopedTiming("postprocess",self.debug_mode > 0):
            softmax_res=self.softmax(results[0][0])
            res_idx=np.argmax(softmax_res)
            gc.collect()
            # 如果类别分数大于阈值，返回当前类别和分数
            if softmax_res[res_idx]>self.confidence_threshold:
                return self.labels[res_idx],softmax_res[res_idx]
            else:
                return "", 0.0

    # 将结果绘制到屏幕上
    def draw_result(self,pl,res,score):
        with ScopedTiming("draw result",self.debug_mode > 0):
            if res!="":
                pl.osd_img.clear()
                mes=res+" "+str(round(score,3))
                pl.osd_img.draw_string_advanced(5,5,32,mes,color=(0,255,0))
            else:
                pl.osd_img.clear()

    # softmax函数
    def softmax(self,x):
        exp_x = np.exp(x - np.max(x))
        return exp_x / np.sum(exp_x)


if __name__=="__main__":
    # auto按开发板选择默认驱动；可手动覆盖为hdmi/lcd/st7701等模式
    display_mode="auto"
    # None使用SDK默认分辨率；更换屏幕时可指定[640, 480]等尺寸
    display_size=None
    # 模型路径，需要用户自行拷贝到开发板的目录下
    kmodel_path="/sdcard/examples/ai_test_kmodel/veg_cls.kmodel"
    # 根据数据集设置，在线训练平台和AICube部署包的deploy_config.json文件中包含该字段
    labels=["菠菜","长茄子","红苋菜","胡萝卜","西红柿","西蓝花"]
    # 初始化PipeLine，rgb888p_size为传给AI的图像分辨率，display_size为显示分辨率
    pl=PipeLine(rgb888p_size=[1280,720],display_mode=display_mode, display_size=display_size)
    # 创建PipeLine，可按需传入sensor_id选择摄像头，例如pl.create(sensor_id=2)
    pl.create()
    display_size=pl.get_display_size()
    # 初始化自定义分类器
    cls=ClassificationApp(kmodel_path,labels,rgb888p_size=[1280,720],display_size=display_size,debug_mode=0)
    # 配置分类任务的预处理
    cls.config_preprocess()
    while True:
        with ScopedTiming("total",1):
            # 获取当前帧数据
            img=pl.get_frame()
            # 推理当前帧
            res,score=cls.run(img)
            # 绘制结果到PipeLine的osd图像
            cls.draw_result(pl,res,score)
            # 显示当前的绘制结果
            pl.show_image()
            gc.collect()
    cls.deinit()
    pl.destroy()

