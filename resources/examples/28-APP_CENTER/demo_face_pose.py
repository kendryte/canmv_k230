from model_cleanup import deinit_with_retry
# demo_face_pose.py - Face pose estimation (3D head orientation cube)

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


class _FacePoseModel(AIBase):
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

    def get_affine_matrix(self, bbox):
        x1, y1, w, h = map(lambda x: int(round(x, 0)), bbox[:4])
        if w <= 0 or h <= 0:
            return [1.0, 0, 0, 0, 1.0, 0]
        edge_size = self.model_input_size[1]
        trans_distance = edge_size / 2.0
        center_x = x1 + w / 2.0
        center_y = y1 + h / 2.0
        maximum_edge = 2.7 * (h if h > w else w)
        scale = edge_size * 2.0 / maximum_edge
        cx = trans_distance - scale * center_x
        cy = trans_distance - scale * center_y
        return [scale, 0, cx, 0, scale, cy]

    def rotation_matrix_to_euler_angles(self, R):
        sy = np.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2)
        if sy < 1e-6:
            pitch = np.arctan2(-R[1, 2], R[1, 1]) * 180 / np.pi
            yaw = np.arctan2(-R[2, 0], sy) * 180 / np.pi
            roll = 0
        else:
            pitch = np.arctan2(R[2, 1], R[2, 2]) * 180 / np.pi
            yaw = np.arctan2(-R[2, 0], sy) * 180 / np.pi
            roll = np.arctan2(R[1, 0], R[0, 0]) * 180 / np.pi
        return [pitch, yaw, roll]

    def config_preprocess(self, det, input_size=None):
        s = input_size if input_size else self.rgb888p_size
        matrix_dst = self.get_affine_matrix(det)
        self.ai2d.affine(nn.interp_method.cv2_bilinear, 0, 0, 127, 1, matrix_dst)
        self.ai2d.build([1, 3, s[1], s[0]], [1, 3, self.model_input_size[1], self.model_input_size[0]])

    def postprocess(self, results):
        data = results[0][0]
        R = data[:3, :3].copy()
        euler = self.rotation_matrix_to_euler_angles(R)
        return R, euler


class FacePoseDemo(Application):
    name = "人脸姿态"
    model_path = demo_common.FACE_DET_KMODEL
    rgb_size = [1280, 720]
    required_files = [
        demo_common.FACE_ANCHOR_FILE,
        config.KMODEL_DIR + "face_pose.kmodel",
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
        self.face_pose = None
        try:
            self.face_det = demo_common.FaceDetSubModel(self.rgb_size,
                                                        self.display_size)
            self.face_det.config_preprocess()
            self.face_pose = _FacePoseModel(
                config.KMODEL_DIR + "face_pose.kmodel", [120, 120],
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
                print("FacePoseDemo: video layer disable failed:", e)
            self._video_bound = False
        if sensor is not None:
            try:
                sensor.stop()
            except Exception as e:
                print("FacePoseDemo: sensor stop failed:", e)

    def _release_owned_resources(self):
        self._osd_img = None

    def _build_projection_matrix(self, det):
        x1, y1, w, h = map(lambda x: int(round(x, 0)), det[:4])
        center_x = x1 + w / 2.0
        center_y = y1 + h / 2.0
        rear_width = 0.5 * w
        rear_height = 0.5 * h
        factor = np.sqrt(2.0)
        front_width = factor * rear_width
        front_height = factor * rear_height
        front_depth = factor * rear_width
        temp = [
            [-rear_width, -rear_height, 0],
            [-rear_width, rear_height, 0],
            [rear_width, rear_height, 0],
            [rear_width, -rear_height, 0],
            [-front_width, -front_height, front_depth],
            [-front_width, front_height, front_depth],
            [front_width, front_height, front_depth],
            [front_width, -front_height, front_depth]
        ]
        return np.array(temp), (center_x, center_y)

    def run(self, input_np):
        det_boxes = self.face_det.run(input_np)
        pose_res = []
        for det_box in det_boxes:
            self.face_pose.config_preprocess(det_box)
            R, euler = self.face_pose.run(input_np)
            pose_res.append((R, euler))
        return det_boxes, pose_res

    def draw_result(self, img, result):
        dets, pose_res = result
        count = len(dets) if dets else 0
        if dets and pose_res:
            for i, det in enumerate(dets):
                R, euler = pose_res[i]
                # R may contain NaN/Inf from noisy KPU output; skip this face
                if not np.all(np.isfinite(R)):
                    continue
                projections, center_point = self._build_projection_matrix(det)
                first_points = []
                second_points = []
                for pp in range(8):
                    sum_x, sum_y = 0.0, 0.0
                    for cc in range(3):
                        sum_x += projections[pp][cc] * R[cc][0]
                        sum_y += projections[pp][cc] * (-R[cc][1])
                    cx, cy = center_point[0], center_point[1]
                    x = (sum_x + cx) / self.rgb_size[0] * self.display_size[0]
                    y = (sum_y + cy) / self.rgb_size[1] * self.display_size[1]
                    if pp < 4:
                        first_points.append((x, y))
                    else:
                        second_points.append((x, y))
                visual.draw_polygon(img, first_points, color=visual.BLUE)
                visual.draw_polygon(img, second_points, color=visual.CYAN)
                for ll in range(4):
                    x0, y0 = int(first_points[ll][0]), int(first_points[ll][1])
                    x1, y1 = int(second_points[ll][0]), int(second_points[ll][1])
                    visual.draw_skeleton_line(
                        img, x0, y0, x1, y1,
                        color=visual.VIOLET, thickness=3)
            visual.draw_mode_badge(img, "HEAD POSE", visual.BLUE)
        return count

    def deinit(self):
        for model in (self.face_det, self.face_pose):
            if model is None:
                continue
            try:
                deinit_with_retry(model)
            except Exception as e:
                print("FacePoseDemo: model deinit failed:", e)
        gc.collect()
