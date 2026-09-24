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

# 自定义分割任务类
class SegmentationApp(AIBase):
    def __init__(self,kmodel_path,num_class,model_input_size=[512,512],rgb888p_size=[512,512],display_size=[1920,1080],debug_mode=0):
        super().__init__(kmodel_path,model_input_size,rgb888p_size,debug_mode)
        # kmodel路径
        self.kmodel_path=kmodel_path
        # 分割类别数
        self.num_class=num_class
        # 模型输入分辨率
        self.model_input_size=model_input_size
        # sensor给到AI的图像分辨率，宽16字节对齐
        self.rgb888p_size=[ALIGN_UP(rgb888p_size[0],16),rgb888p_size[1]]
        # 视频输出VO分辨率，宽16字节对齐
        self.display_size=[ALIGN_UP(display_size[0],16),display_size[1]]
        # debug_mode模式
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
            # build预处理过程，参数为输入tensor的shape和输出tensor的shape
            self.ai2d.build([1,3,ai2d_input_size[1],ai2d_input_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])

    # 自定义当前任务的后处理
    def postprocess(self,input_np):
        with ScopedTiming("postprocess",self.debug_mode > 0):
            # 这里使用了aicube封装的接口seg_post_process做后处理，返回一个和display_size相同分辨率的mask图
            mask = aicube.seg_post_process(self.results[0], self.num_class, [self.results[0].shape[-3],self.results[0].shape[-2]], [self.display_size[1],self.display_size[0]])
            # 在mask数据上创建osd图像并返回
            res_mask = image.Image(self.display_size[0], self.display_size[1], image.ARGB8888,alloc=image.ALLOC_REF,data=mask)
            return res_mask

    # 绘制分割结果，将创建的mask图像copy到pl.osd_img上
    def draw_result(self,pl,res_img):
        with ScopedTiming("draw osd",self.debug_mode > 0):
            res_img.copy_to(pl.osd_img)


if __name__=="__main__":
    # auto按开发板选择默认驱动；可手动覆盖为hdmi/lcd/st7701等模式
    display_mode="auto"
    # None使用SDK默认分辨率；更换屏幕时可指定[640, 480]等尺寸
    display_size=None
    # kmodel路径
    kmodel_path="/sdcard/examples/ai_test_kmodel/ocular_seg.kmodel"
    # 分割类别数，设置类别数时必须包含背景，且背景为第一类
    num_class=2
    # 初始化PipeLine，rgb888p_size为传给AI的图像分辨率，display_size为显示分辨率
    pl=PipeLine(rgb888p_size=[512,512],display_mode=display_mode, display_size=display_size)
    # 创建PipeLine，可按需传入sensor_id选择摄像头，例如pl.create(sensor_id=2)
    pl.create()
    display_size=pl.get_display_size()
    # 分割类实例，关注模型输入分辨率，传给AI的图像分辨率，显示的分辨率
    seg=SegmentationApp(kmodel_path,num_class,model_input_size=[512,512],rgb888p_size=[512,512],display_size=display_size)
    # 配置预处理过程
    seg.config_preprocess()
    while True:
        with ScopedTiming("total",1):
            # 获取当前帧
            img=pl.get_frame()
            # 获得mask结果
            mask=seg.run(img)
            # 绘制mask结果到osd上
            seg.draw_result(pl,mask)
            # 显示绘制结果
            pl.show_image()
            gc.collect()
    seg.deinit()
    pl.destroy()
