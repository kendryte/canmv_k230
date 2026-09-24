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


# 自定义行人ReID特征提取类
class FeatureExtractionApp(AIBase):
    def __init__(self,kmodel_path,model_input_size,feature_dim,rgb888p_size=[1280,720],debug_mode=0):
        super().__init__(kmodel_path,model_input_size,rgb888p_size,debug_mode)
        self.kmodel_path=kmodel_path
        self.model_input_size=model_input_size
        self.feature_dim=feature_dim
        self.rgb888p_size=[ALIGN_UP(rgb888p_size[0],16),rgb888p_size[1]]
        self.debug_mode=debug_mode
        self.ai2d=None
        try:
            self.ai2d=Ai2d(debug_mode)
            self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,nn.ai2d_format.NCHW_FMT,np.uint8,np.uint8)
            self.ai2d.resize(nn.interp_method.tf_bilinear,nn.interp_mode.half_pixel)
            self._validate_model()
        except BaseException:
            self.deinit()
            raise

    # 检查feature.kmodel是否与跟踪器配置匹配
    def _validate_model(self):
        if self.kpu.inputs_size() != 1 or self.kpu.outputs_size() != 1:
            raise ValueError("feature.kmodel must have one input and one output")
        input_desc=self.kpu.inputs_desc(0)
        output_desc=self.kpu.outputs_desc(0)
        input_bytes=3*self.model_input_size[0]*self.model_input_size[1]
        if input_desc["tensor_datatype"] != "dt_uint8" or input_desc["tensor_size"] != input_bytes:
            raise ValueError("feature.kmodel input must be uint8 NCHW")
        if output_desc["tensor_datatype"] != "dt_float32" or output_desc["tensor_size"] != self.feature_dim*4:
            raise ValueError("feature.kmodel output dimension mismatch")

    # 裁剪ROI并限制在sensor图像范围内
    def get_crop_param(self,det_box):
        x1=max(0,int(round(det_box[0])))
        y1=max(0,int(round(det_box[1])))
        x2=min(self.rgb888p_size[0],int(round(det_box[0]+det_box[2])))
        y2=min(self.rgb888p_size[1],int(round(det_box[1]+det_box[3])))
        if x2 <= x1 or y2 <= y1:
            raise ValueError("invalid person ROI")
        return [x1,y1,x2-x1,y2-y1]

    # 对单个行人框提取ReID特征
    def run_feature(self,input_np,det_box):
        with ScopedTiming("feature preprocess",self.debug_mode > 0):
            crop_x,crop_y,crop_w,crop_h=self.get_crop_param(det_box)
            self.ai2d.crop(crop_x,crop_y,crop_w,crop_h)
            self.ai2d.build([1,3,self.rgb888p_size[1],self.rgb888p_size[0]],[1,3,self.model_input_size[1],self.model_input_size[0]])
            input_tensor=self.ai2d.run(input_np)
        results=self.inference([input_tensor])
        feature=list(results[0].flatten())
        if len(feature) != self.feature_dim:
            raise ValueError("unexpected feature dimension: %d"%len(feature))
        self.results.clear()
        return feature


def update_tracker(tracker,dets,feature_app,img):
    boxes=dets[0]
    if not boxes:
        return tracker.update([],[],[])
    scores=dets[2]
    class_ids=[0]*len(boxes)
    if feature_app is None:
        return tracker.update(boxes,scores,class_ids)
    features=[]
    for det_box in boxes:
        features.append(feature_app.run_feature(img,det_box))
    return tracker.update(boxes,scores,class_ids,features)


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
    confidence_threshold=0.5
    nms_threshold=0.6
    max_boxes_num=30
    # ReID特征模型配置
    feature_kmodel_path="/sdcard/examples/kmodel/feature.kmodel"
    feature_model_input_size=[64,128]
    feature_dim=512
    # DeepSORT参数
    max_cosine_distance=0.3
    nn_budget=300
    max_iou_distance=0.7
    max_age=30
    n_init=3

    pl=None
    person_det=None
    feature_app=None
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
        # 初始化ReID特征提取
        feature_app=FeatureExtractionApp(feature_kmodel_path,model_input_size=feature_model_input_size,feature_dim=feature_dim,rgb888p_size=rgb888p_size,debug_mode=0)
        # 初始化多目标跟踪器
        tracker=mot.DeepSort(feature_dim=feature_dim,max_cosine_distance=max_cosine_distance,nn_budget=nn_budget,max_iou_distance=max_iou_distance,max_age=max_age,n_init=n_init,class_aware=True,bbox_format="xywh")

        while True:
            os.exitpoint()
            with ScopedTiming("total",1):
                # 获取当前帧数据
                img=pl.get_frame()
                # YOLOv8检测，仅保留person
                dets=person_det.run(img)
                # 更新多目标跟踪器
                tracks=update_tracker(tracker,dets,feature_app,img)
                # 绘制跟踪结果
                person_det.draw_result(pl,tracks)
                pl.show_image()
                gc.collect()
    except KeyboardInterrupt:
        print("DeepSort stopped")
    except Exception as error:
        if "IDE interrupt" in str(error):
            print("DeepSort stopped")
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
            print("DeepSort cleanup tracker failed:", error)
        tracker=None
        try:
            if feature_app is not None:
                feature_app.deinit()
        except BaseException as error:
            print("DeepSort cleanup feature model failed:", error)
        feature_app=None
        try:
            if person_det is not None:
                person_det.deinit()
        except BaseException as error:
            print("DeepSort cleanup detector failed:", error)
        person_det=None
        try:
            if pl is not None:
                pl.destroy()
        except BaseException as error:
            print("DeepSort cleanup pipeline failed:", error)
        pl=None
        gc.collect()


if __name__=="__main__":
    main()
