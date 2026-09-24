from libs.PipeLine import PipeLine
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from libs.Utils import *
import os,sys,ujson,gc
import ujson
from media.media import *
import nncase_runtime as nn
import ulab.numpy as np
import image
import aidemo

# face detect
class FaceDetectionApp(AIBase):
    def __init__(self, kmodel_path, model_input_size, confidence_threshold=0.5, nms_threshold=0.2,top_k=50, rgb888p_size=[224,224], display_size=[1920,1080], debug_mode=0):
        super().__init__(kmodel_path, model_input_size, rgb888p_size, debug_mode)
        self.kmodel_path = kmodel_path  # kmodel path
        self.model_input_size = model_input_size  # model input size
        self.confidence_threshold = confidence_threshold  # confidence threshold
        self.nms_threshold = nms_threshold  # nms threshold
        self.top_k=top_k # topk boxes
        self.rgb888p_size = [ALIGN_UP(rgb888p_size[0], 16), rgb888p_size[1]]
        self.display_size = [ALIGN_UP(display_size[0], 16), display_size[1]]
        self.scale=1.0 # process ratio
        self.debug_mode = debug_mode  # debug mode
        self.ai2d = Ai2d(debug_mode)  # init ai2d for preprocess
        self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT, np.uint8, np.uint8)

    # preprocess with pad and resize (letterbox)
    def config_preprocess(self, input_image_size=None):
        with ScopedTiming("set preprocess config", self.debug_mode > 0):
            ai2d_input_size = input_image_size if input_image_size else self.rgb888p_size
            top, bottom, left, right, self.scale = letterbox_pad_param(self.rgb888p_size,self.model_input_size)
            self.ai2d.pad([0, 0, 0, 0, top, bottom, left, right], 0, [114, 114, 114])
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            self.ai2d.build([1,3,ai2d_input_size[1],ai2d_input_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])

    # postprocess
    def postprocess(self, results):
        with ScopedTiming("postprocess", self.debug_mode > 0):
            strides=[8,16,32]
            dets_out=aidemo.yunet_postprocess(results,[self.rgb888p_size[1],self.rgb888p_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self.display_size[1],self.display_size[0]],strides,self.confidence_threshold,self.nms_threshold,self.top_k)
            return dets_out

    # 绘制结果
    def draw_result(self,pl,dets):
        with ScopedTiming("display_draw",self.debug_mode >0):
            if dets:
                pl.osd_img.clear()
                for i in range(len(dets[0])):
                    x, y, w, h = map(lambda x: int(round(x, 0)), dets[0][i])
                    pl.osd_img.draw_rectangle(x,y, w, h, color=(0,255,0),thickness=4)
            else:
                pl.osd_img.clear()

if __name__ == "__main__":
    # auto按开发板选择默认驱动；可手动改为hdmi/lcd/st7701/nt35516等模式
    display_mode="auto"
    # None使用SDK默认分辨率；更换屏幕规格时手动指定，如[640, 480]
    display_size=None
    rgb888p_size = [640, 640]
    kmodel_path = "/sdcard/examples/kmodel/yunet_640.kmodel"
    confidence_threshold = 0.6
    nms_threshold = 0.3
    top_k=50
    # 初始化PipeLine，rgb888p_size为传给AI的图像分辨率，display_size为显示分辨率
    pl = PipeLine(rgb888p_size=rgb888p_size, display_mode=display_mode, display_size=display_size)
    # 创建PipeLine，可按需传入sensor_id选择摄像头，例如pl.create(sensor_id=2)
    pl.create()
    display_size=pl.get_display_size()
    # init FaceDetectionApp
    face_det = FaceDetectionApp(kmodel_path, model_input_size=[640, 640], confidence_threshold=confidence_threshold, nms_threshold=nms_threshold, top_k=top_k,rgb888p_size=rgb888p_size, display_size=display_size, debug_mode=0)
    face_det.config_preprocess()
    while True:
        with ScopedTiming("total",1):
            img = pl.get_frame()            # get a frame
            res = face_det.run(img)         # inference
            face_det.draw_result(pl,res)    # draw result
            pl.show_image()                 # show result on display
            gc.collect()
    face_det.deinit()
    pl.destroy()

