from model_cleanup import deinit_with_retry
# demo_face_mesh.py - 3D face mesh demo

import gc
import ulab.numpy as np
import nncase_runtime as nn
import image
import aidemo
import config
import app_visual as visual
import demo_common
from media.sensor import *
from media.display import Display
from app_contract import Application
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from media.media import ALIGN_UP
from libs.Utils import *


class _FaceMeshAlignModel(AIBase):
    def __init__(self, kmodel_path, model_input_size, rgb_size, disp_size):
        try:
            super().__init__(kmodel_path, model_input_size, rgb_size, 0)
            self.model_input_size = model_input_size
            self.rgb888p_size = [ALIGN_UP(rgb_size[0], 16), rgb_size[1]]
            self.display_size = [ALIGN_UP(disp_size[0], 16), disp_size[1]]
            self.ai2d = Ai2d(0)
            self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT, np.uint8, np.uint8)
            self.param_mean = np.array([0.0003492636315058917,2.52790130161884e-07,-6.875197868794203e-07,60.1679573059082,-6.295513230725192e-07,0.0005757200415246189,-5.085391239845194e-05,74.2781982421875,5.400917189035681e-07,6.574138387804851e-05,0.0003442012530285865,-66.67157745361328,-346603.6875,-67468.234375,46822.265625,-15262.046875,4350.5888671875,-54261.453125,-18328.033203125,-1584.328857421875,-84566.34375,3835.960693359375,-20811.361328125,38094.9296875,-19967.85546875,-9241.3701171875,-19600.71484375,13168.08984375,-5259.14404296875,1848.6478271484375,-13030.662109375,-2435.55615234375,-2254.20654296875,-14396.5615234375,-6176.3291015625,-25621.919921875,226.39447021484375,-6326.12353515625,-10867.2509765625,868.465087890625,-5831.14794921875,2705.123779296875,-3629.417724609375,2043.9901123046875,-2446.6162109375,3658.697021484375,-7645.98974609375,-6674.45263671875,116.38838958740234,7185.59716796875,-1429.48681640625,2617.366455078125,-1.2070955038070679,0.6690792441368103,-0.17760828137397766,0.056725528091192245,0.03967815637588501,-0.13586315512657166,-0.09223993122577667,-0.1726071834564209,-0.015804484486579895,-0.1416848599910736],dtype=np.float)
            self.param_std  = np.array([0.00017632152594160289,6.737943476764485e-05,0.00044708489440381527,26.55023193359375,0.0001231376954820007,4.493021697271615e-05,7.923670636955649e-05,6.982563018798828,0.0004350444069132209,0.00012314890045672655,0.00017400001524947584,20.80303955078125,575421.125,277649.0625,258336.84375,255163.125,150994.375,160086.109375,111277.3046875,97311.78125,117198.453125,89317.3671875,88493.5546875,72229.9296875,71080.2109375,50013.953125,55968.58203125,47525.50390625,49515.06640625,38161.48046875,44872.05859375,46273.23828125,38116.76953125,28191.162109375,32191.4375,36006.171875,32559.892578125,25551.1171875,24267.509765625,27521.3984375,23166.53125,21101.576171875,19412.32421875,19452.203125,17454.984375,22537.623046875,16174.28125,14671.640625,15115.6884765625,13870.0732421875,13746.3125,12663.1337890625,1.5870834589004517,1.5077009201049805,0.5881357789039612,0.5889744758605957,0.21327851712703705,0.2630201280117035,0.2796429395675659,0.38030216097831726,0.16162841022014618,0.2559692859649658],dtype=np.float)
        except BaseException:
            # The caller cannot own this model until construction returns.
            try:
                self.deinit()
            except Exception as error:
                print("model constructor cleanup failed:", error)
            raise

    def parse_roi(self, bbox):
        x1, y1, w, h = map(lambda v: int(round(v, 0)), bbox[:4])
        old_size = (w + h) / 2
        cx = x1 + w / 2
        cy = y1 + h / 2 + old_size * 0.14
        size = int(old_size * 1.58)
        x0 = cx - size / 2
        y0 = cy - size / 2
        x0 = max(0, min(x0, self.rgb888p_size[0]))
        y0 = max(0, min(y0, self.rgb888p_size[1]))
        x1n = max(0, min(x0 + size, self.rgb888p_size[0]))
        y1n = max(0, min(y0 + size, self.rgb888p_size[1]))
        return (int(x0), int(y0), int(x1n - x0), int(y1n - y0))

    def config_preprocess(self, det, input_size=None):
        s = input_size if input_size else self.rgb888p_size
        roi = self.parse_roi(det)
        self.ai2d.crop(int(roi[0]), int(roi[1]), int(roi[2]), int(roi[3]))
        self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
        self.ai2d.build([1, 3, s[1], s[0]], [1, 3, self.model_input_size[1], self.model_input_size[0]])
        return roi

    def postprocess(self, results):
        return results[0] * self.param_std + self.param_mean


class _FaceMeshPostModel(AIBase):
    def __init__(self, kmodel_path, model_input_size, rgb_size, disp_size):
        try:
            super().__init__(kmodel_path, model_input_size, rgb_size, 0)
            self.model_input_size = model_input_size
            self.rgb888p_size = [ALIGN_UP(rgb_size[0], 16), rgb_size[1]]
            self.display_size = [ALIGN_UP(disp_size[0], 16), disp_size[1]]
            self.ai2d = Ai2d(0)
            self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT, np.uint8, np.uint8)
        except BaseException:
            # The caller cannot own this model until construction returns.
            try:
                self.deinit()
            except Exception as error:
                print("model constructor cleanup failed:", error)
            raise

    def preprocess(self, param):
        param = param[0]
        trans_dim, shape_dim, exp_dim = 12, 40, 10
        R_ = param[:trans_dim].copy().reshape((3, -1))
        R = R_[:, :3].copy()
        offset = R_[:, 3].copy().reshape((3, 1))
        alpha_shp = param[trans_dim:trans_dim + shape_dim].copy().reshape((-1, 1))
        alpha_exp = param[trans_dim + shape_dim:].copy().reshape((-1, 1))
        return [nn.from_numpy(R), nn.from_numpy(offset), nn.from_numpy(alpha_shp), nn.from_numpy(alpha_exp)]

    def postprocess(self, results, roi):
        x, y, w, h = map(lambda v: int(round(v, 0)), roi[:4])
        x = x * self.display_size[0] // self.rgb888p_size[0]
        y = y * self.display_size[1] // self.rgb888p_size[1]
        w = w * self.display_size[0] // self.rgb888p_size[0]
        h = h * self.display_size[1] // self.rgb888p_size[1]
        roi_array = np.array([x, y, w, h], dtype=np.float)
        aidemo.face_mesh_post_process(roi_array, results[0])
        return results[0]


class FaceMeshDemo(Application):
    name = "人脸网格"
    model_path = demo_common.FACE_DET_KMODEL
    rgb_size = [1280, 720]
    required_files = [
        demo_common.FACE_ANCHOR_FILE,
        config.KMODEL_DIR + "face_alignment.kmodel",
        config.KMODEL_DIR + "face_alignment_post.kmodel",
    ]

    SENSOR_ID = 2
    SENSOR_FPS = 60
    DISPLAY_CHANNEL = CAM_CHN_ID_0
    AI_CHANNEL = CAM_CHN_ID_2
    DISPLAY_FORMAT = Sensor.YUV420SP
    AI_FORMAT = Sensor.RGBP888
    VIDEO_LAYER = Display.LAYER_VIDEO1

    def __init__(self):
        self.rgb_size = [ALIGN_UP(self.rgb_size[0], 16), self.rgb_size[1]]
        self.display_size = [ALIGN_UP(config.CAM_WIN_W, 16), config.CAM_WIN_H]
        Application.__init__(self)
        self.sensor = None
        self._ai_img = None
        self._osd_img = None
        self._video_bound = False
        # Roll back partially-created sub-models on failure: a create() error
        # means runner never calls close(), so any KPU/AI2D already allocated
        # here must be released before re-raising.
        self.face_det = None
        self.face_mesh_align = None
        self.face_mesh_post = None
        try:
            self.face_det = demo_common.FaceDetSubModel(self.rgb_size,
                                                        self.display_size)
            self.face_det.config_preprocess()
            self.face_mesh_align = _FaceMeshAlignModel(
                config.KMODEL_DIR + "face_alignment.kmodel", [120, 120],
                self.rgb_size, self.display_size)
            self.face_mesh_post = _FaceMeshPostModel(
                config.KMODEL_DIR + "face_alignment_post.kmodel", [120, 120],
                self.rgb_size, self.display_size)
        except Exception:
            self.deinit()
            raise

    def open(self):
        if self._opened or self.stop_req:
            return
        sensor = Sensor(id=self.SENSOR_ID)
        self.sensor = sensor
        sensor.reset()
        sensor.set_framesize(w=self.display_size[0], h=self.display_size[1], chn=self.DISPLAY_CHANNEL)
        sensor.set_pixformat(self.DISPLAY_FORMAT, chn=self.DISPLAY_CHANNEL)
        sensor.set_framesize(w=self.rgb_size[0], h=self.rgb_size[1], chn=self.AI_CHANNEL)
        sensor.set_pixformat(self.AI_FORMAT, chn=self.AI_CHANNEL)
        Display.bind_layer(**sensor.bind_info(
            x=config.CAM_WIN_X, y=config.CAM_WIN_Y,
            chn=self.DISPLAY_CHANNEL), layer=self.VIDEO_LAYER)
        self._video_bound = True
        sensor.run()
        self._osd_img = image.Image(self.display_size[0], self.display_size[1], image.ARGB8888)
        if self.stop_req:
            return
        self.start()
        self._opened = True

    def run_once(self):
        self._ai_img = self.sensor.snapshot(chn=self.AI_CHANNEL)
        result = self.run(self._ai_img.to_numpy_ref())
        self._osd_img.clear()
        count = self.draw_result(self._osd_img, result)
        self.display.show(self._osd_img)
        return count if count else 0

    def stop(self):
        Application.stop(self)
        sensor = self.sensor
        self.sensor = None
        self._ai_img = None
        if self.display is not None:
            self.display.clear()
        if self._video_bound:
            try:
                Display.disable_layer(self.VIDEO_LAYER)
            except Exception as e:
                print("FaceMeshDemo: video layer disable failed:", e)
            self._video_bound = False
        if sensor is not None:
            try:
                sensor.stop()
            except Exception as e:
                print("FaceMeshDemo: sensor stop failed:", e)

    def _release_owned_resources(self):
        self._osd_img = None

    def run(self, input_np):
        det_boxes = self.face_det.run(input_np)
        mesh_res = []
        for det_box in det_boxes:
            roi = self.face_mesh_align.config_preprocess(det_box)
            param = self.face_mesh_align.run(input_np)
            tensors = self.face_mesh_post.preprocess(param)
            results = self.face_mesh_post.inference(tensors)
            res = self.face_mesh_post.postprocess(results, roi)
            mesh_res.append(res)
        return det_boxes, mesh_res

    def draw_result(self, img, result):
        dets, mesh_res = result
        count = len(dets) if dets else 0
        if mesh_res:
            osd_np = img.to_numpy_ref()
            for vertices in mesh_res:
                aidemo.face_draw_mesh(osd_np, vertices)
            visual.draw_mode_badge(img, "3D FACE MESH", visual.VIOLET)
        return count

    def deinit(self):
        for model in (self.face_det, self.face_mesh_align,
                      self.face_mesh_post):
            if model is None:
                continue
            try:
                deinit_with_retry(model)
            except Exception as e:
                print("FaceMeshDemo: model deinit failed:", e)
        gc.collect()
