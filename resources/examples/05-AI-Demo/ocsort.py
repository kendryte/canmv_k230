from libs.PipeLine import PipeLine
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from libs.Utils import *
import gc
import os
from media.media import *
import nncase_runtime as nn
import ulab.numpy as np
import aidemo
import mot


# 自定义YOLOv8行人检测类
class PersonDetectionApp(AIBase):
    def __init__(self,kmodel_path,labels,model_input_size,max_boxes_num,confidence_threshold=0.5,nms_threshold=0.6,rgb888p_size=[1280,720],display_size=[1920,1080],debug_mode=0):
        super().__init__(kmodel_path,model_input_size,rgb888p_size,debug_mode)
        self.kmodel_path=kmodel_path
        self.labels=labels
        self.model_input_size=model_input_size
        self.max_boxes_num=max_boxes_num
        self.confidence_threshold=confidence_threshold
        self.nms_threshold=nms_threshold
        self.rgb888p_size=[ALIGN_UP(rgb888p_size[0],16),rgb888p_size[1]]
        self.display_size=[ALIGN_UP(display_size[0],16),display_size[1]]
        self.debug_mode=debug_mode
        self.color=get_colors(1)[0]
        self.ai2d=Ai2d(debug_mode)
        self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,nn.ai2d_format.NCHW_FMT,np.uint8,np.uint8)

    # 配置YOLOv8的letterbox预处理
    def config_preprocess(self,input_image_size=None):
        with ScopedTiming("set preprocess config",self.debug_mode > 0):
            ai2d_input_size=input_image_size if input_image_size else self.rgb888p_size
            top,bottom,left,right,self.scale=letterbox_pad_param(self.rgb888p_size,self.model_input_size)
            self.ai2d.pad([0,0,0,0,top,bottom,left,right],0,[128,128,128])
            self.ai2d.resize(nn.interp_method.tf_bilinear,nn.interp_mode.half_pixel)
            self.ai2d.build([1,3,ai2d_input_size[1],ai2d_input_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])

    # YOLOv8后处理，并只保留COCO person类别
    def postprocess(self,results):
        with ScopedTiming("postprocess",self.debug_mode > 0):
            new_result=results[0][0].transpose()
            det_res=aidemo.yolov8_det_postprocess(new_result.copy(),[self.rgb888p_size[1],self.rgb888p_size[0]],[self.model_input_size[1],self.model_input_size[0]],[self.rgb888p_size[1],self.rgb888p_size[0]],len(self.labels),self.confidence_threshold,self.nms_threshold,self.max_boxes_num)
            person_res=[[],[],[]]
            if det_res:
                for i in range(len(det_res[0])):
                    if int(det_res[1][i]) == 0:
                        person_res[0].append(list(det_res[0][i]))
                        person_res[1].append(0)
                        person_res[2].append(float(det_res[2][i]))
            return person_res

    # 绘制跟踪框和轨迹ID
    def draw_result(self,pl,tracks):
        with ScopedTiming("display_draw",self.debug_mode > 0):
            pl.osd_img.clear()
            x_factor=float(self.display_size[0])/self.rgb888p_size[0]
            y_factor=float(self.display_size[1])/self.rgb888p_size[1]
            for track in tracks:
                x,y,w,h=track["bbox"]
                x=int(round(x*x_factor))
                y=int(round(y*y_factor))
                w=int(round(w*x_factor))
                h=int(round(h*y_factor))
                if w <= 0 or h <= 0:
                    continue
                pl.osd_img.draw_rectangle(x,y,w,h,color=self.color,thickness=4)
                text="person #%d %.2f"%(track["track_id"],track["score"])
                pl.osd_img.draw_string_advanced(x,max(0,y-40),28,text,color=self.color)



def update_tracker(tracker,dets):
    boxes=dets[0]
    if not boxes:
        return tracker.update([],[],[])
    scores=dets[2]
    class_ids=[0]*len(boxes)
    return tracker.update(boxes,scores,class_ids)


def main():
    # auto按开发板选择默认驱动；可手动改为hdmi/lcd/st7701/nt35516等模式
    display_mode="auto"
    # None使用SDK默认分辨率；更换屏幕规格时手动指定，如[640,480]
    display_size=None
    # sensor给到AI的图像分辨率
    rgb888p_size=[1280,720]
    # YOLOv8检测模型配置
    kmodel_path="/sdcard/examples/kmodel/yolov8n_320.kmodel"
    model_input_size=[320,320]
    labels=["person","bicycle","car","motorcycle","airplane","bus","train","truck","boat","traffic light","fire hydrant","stop sign","parking meter","bench","bird","cat","dog","horse","sheep","cow","elephant","bear","zebra","giraffe","backpack","umbrella","handbag","tie","suitcase","frisbee","skis","snowboard","sports ball","kite","baseball bat","baseball glove","skateboard","surfboard","tennis racket","bottle","wine glass","cup","fork","knife","spoon","bowl","banana","apple","sandwich","orange","broccoli","carrot","hot dog","pizza","donut","cake","chair","couch","potted plant","bed","dining table","toilet","tv","laptop","mouse","remote","keyboard","cell phone","microwave","oven","toaster","sink","refrigerator","book","clock","vase","scissors","teddy bear","hair drier","toothbrush"]
    confidence_threshold=0.1
    nms_threshold=0.6
    max_boxes_num=30
    # OC-SORT参数
    det_thresh=0.3
    max_age=30
    min_hits=3
    iou_threshold=0.3
    delta_t=3
    inertia=0.2
    use_byte=True

    pl=None
    person_det=None
    tracker=None
    img=None
    dets=None
    tracks=None
    os.exitpoint(os.EXITPOINT_ENABLE)
    try:
        # 初始化PipeLine
        pl=PipeLine(rgb888p_size=rgb888p_size,display_mode=display_mode,display_size=display_size)
        pl.create()
        display_size=pl.get_display_size()
        # 初始化YOLOv8行人检测
        person_det=PersonDetectionApp(kmodel_path,labels=labels,model_input_size=model_input_size,max_boxes_num=max_boxes_num,confidence_threshold=confidence_threshold,nms_threshold=nms_threshold,rgb888p_size=rgb888p_size,display_size=display_size,debug_mode=0)
        person_det.config_preprocess()

        # 初始化多目标跟踪器
        tracker=mot.OCSort(det_thresh=det_thresh,max_age=max_age,min_hits=min_hits,iou_threshold=iou_threshold,delta_t=delta_t,inertia=inertia,use_byte=use_byte,class_aware=True,bbox_format="xywh")

        while True:
            os.exitpoint()
            with ScopedTiming("total",1):
                # 获取当前帧数据
                img=pl.get_frame()
                # YOLOv8检测，仅保留person
                dets=person_det.run(img)
                # 更新多目标跟踪器
                tracks=update_tracker(tracker,dets)
                # 绘制跟踪结果
                person_det.draw_result(pl,tracks)
                pl.show_image()
                gc.collect()
    except KeyboardInterrupt:
        print("OCSort stopped")
    except Exception as error:
        if "IDE interrupt" in str(error):
            print("OCSort stopped")
        else:
            raise
    finally:
        os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
        img=None
        dets=None
        tracks=None
        try:
            if tracker is not None:
                tracker.close()
        except BaseException as error:
            print("OCSort cleanup tracker failed:", error)
        tracker=None
        try:
            if person_det is not None:
                person_det.deinit()
        except BaseException as error:
            print("OCSort cleanup detector failed:", error)
        person_det=None
        try:
            if pl is not None:
                pl.destroy()
        except BaseException as error:
            print("OCSort cleanup pipeline failed:", error)
        pl=None
        gc.collect()


if __name__=="__main__":
    main()
