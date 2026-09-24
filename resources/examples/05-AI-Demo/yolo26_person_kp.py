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

# 自定义人体关键点检测类
class YOLO26PersonKeyPointApp(AIBase):
    def __init__(self,kmodel_path,model_input_size,labels,kp_num,kp_dim=3,confidence_threshold=0.2,rgb888p_size=[1280,720],display_size=[1920,1080],debug_mode=0):
        super().__init__(kmodel_path,model_input_size,rgb888p_size,debug_mode)
        self.kmodel_path=kmodel_path
        # 模型输入分辨率
        self.model_input_size=model_input_size
        self.labels=labels
        self.kp_num=kp_num
        self.kp_dim=kp_dim
        self.max_box_cnt=30
        # 置信度阈值设置
        self.confidence_threshold=confidence_threshold
        # sensor给到AI的图像分辨率
        self.rgb888p_size=[ALIGN_UP(rgb888p_size[0],16),rgb888p_size[1]]
        # 显示分辨率
        self.display_size=[ALIGN_UP(display_size[0],16),display_size[1]]
        self.debug_mode=debug_mode
        #关键点颜色，共17个
        self.colors = get_colors(self.kp_num)

        # Ai2d实例，用于实现模型预处理
        self.ai2d=Ai2d(debug_mode)
        # 设置Ai2d的输入输出格式和类型
        self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,nn.ai2d_format.NCHW_FMT,np.uint8, np.uint8)

    # 配置预处理操作，这里使用了pad和resize，Ai2d支持crop/shift/pad/resize/affine，具体代码请打开/sdcard/app/libs/AI2D.py查看
    def config_preprocess(self,input_image_size=None):
        with ScopedTiming("set preprocess config",self.debug_mode > 0):
            # 初始化ai2d预处理配置，默认为sensor给到AI的尺寸，您可以通过设置input_image_size自行修改输入尺寸
            ai2d_input_size=input_image_size if input_image_size else self.rgb888p_size
            top,bottom,left,right,_=center_pad_param(self.rgb888p_size,self.model_input_size)
            self.ai2d.pad([0,0,0,0,top,bottom,left,right], 0, [0,0,0])
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            self.ai2d.build([1,3,ai2d_input_size[1],ai2d_input_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])

    def preprocess(self,input_np):
        with ScopedTiming("preprocess",self.debug_mode > 0):
            return [nn.from_numpy(input_np)]

    # 自定义当前任务的后处理
    def postprocess(self,results):
        with ScopedTiming("postprocess",self.debug_mode > 0):
            # 这里使用了aidemo库的person_kp_postprocess接口
            results = aidemo.yolo26_pose_postprocess(results[0][0],[self.rgb888p_size[1],self.rgb888p_size[0]],self.model_input_size,[self.display_size[1],self.display_size[0]],len(self.labels),self.kp_num,self.kp_dim,self.confidence_threshold,self.max_box_cnt)
            return results

    #绘制结果，绘制人体关键点
    def draw_result(self,pl,res):
        with ScopedTiming("display_draw",self.debug_mode >0):
            if res[0]:
                pl.osd_img.clear()
                boxes=res[0]
                index=res[1]
                scores=res[2]
                kps = res[3]
                for i in range(len(kps)):
                    for k in range(self.kp_num):
                        x=kps[i][k*self.kp_dim+0]
                        y=kps[i][k*self.kp_dim+1]
                        pl.osd_img.draw_circle(int(x),int(y),5,self.colors[k],fill=True)
                        x_, y_, w_, h_ = map(lambda x: int(round(x, 0)), boxes[i])
                        pl.osd_img.draw_rectangle(x_,y_, w_, h_, color=self.colors[index[i]],thickness=4)
                        pl.osd_img.draw_string_advanced( x_ , y_-50,32," " + self.labels[index[i]] + " {0:.3f}".format(res[2][i]) , color=self.colors[res[1][i]])
                    gc.collect()
            else:
                pl.osd_img.clear()

if __name__=="__main__":
    # auto按开发板选择默认驱动；可手动改为hdmi/lcd/st7701/nt35516等模式
    display_mode="auto"
    # None使用SDK默认分辨率；更换屏幕规格时手动指定，如[640, 480]
    display_size=None
    # k230保持不变，k230d可调整为[640,360]
    rgb888p_size = [320, 320]
    # 模型路径
    kmodel_path="/sdcard/examples/kmodel/yolo26n-pose.kmodel"
    # 其它参数设置
    confidence_threshold = 0.5
    kp_num=17
    kp_dim=3
    labels=["person"]
    model_input_size=[320,320]
    # 初始化PipeLine
    pl=PipeLine(rgb888p_size=rgb888p_size,display_mode=display_mode,display_size=display_size)
    pl.create()
    display_size=pl.get_display_size()
    # 初始化自定义人体关键点检测实例
    person_kp=YOLO26PersonKeyPointApp(kmodel_path,model_input_size=model_input_size,labels=labels,kp_num=kp_num,kp_dim=kp_dim,confidence_threshold=confidence_threshold,rgb888p_size=rgb888p_size,display_size=display_size,debug_mode=0)
    person_kp.config_preprocess()
    while True:
        with ScopedTiming("total",1):
            # 获取当前帧数据
            img=pl.get_frame()
            # 推理当前帧
            res=person_kp.run(img)
            # 绘制结果到PipeLine的osd图像
            person_kp.draw_result(pl,res)
            # 显示当前的绘制结果
            pl.show_image()
            gc.collect()
    person_kp.deinit()
    pl.destroy()

