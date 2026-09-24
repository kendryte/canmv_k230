# face_lite.py - Lite face detector, embedding model, and feature database

import math
import os
import aidemo
import nncase_runtime as nn
import ulab.numpy as np
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from libs.Utils import letterbox_pad_param
from media.media import ALIGN_UP


# The face_recognition_mobile.kmodel shipped by the current SDK produces a
# 512-element float embedding.  Do not confuse the lite model's smaller model
# size with its output embedding dimension.
FEATURE_SIZE = 512
MAX_DATABASE_FACES = 100


class FaceDetectorLite(AIBase):
    """RetinaFace detector returning both boxes and five-point landmarks."""

    def __init__(self, kmodel_path, rgb_size, anchors,
                 confidence_threshold=0.5, nms_threshold=0.2):
        try:
            self.model_size = [320, 320]
            self.rgb_size = [ALIGN_UP(rgb_size[0], 16), rgb_size[1]]
            super().__init__(kmodel_path, self.model_size, self.rgb_size, 0)
            self.anchors = anchors
            self.confidence_threshold = confidence_threshold
            self.nms_threshold = nms_threshold
            self.ai2d = Ai2d(0)
            self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,
                                     nn.ai2d_format.NCHW_FMT,
                                     np.uint8, np.uint8)
        except BaseException:
            # The caller cannot own this model until construction returns.
            try:
                self.deinit()
            except Exception as error:
                print("model constructor cleanup failed:", error)
            raise

    def config_preprocess(self):
        top, bottom, left, right, _ = letterbox_pad_param(
            self.rgb_size, self.model_size)
        self.ai2d.pad([0, 0, 0, 0, top, bottom, left, right],
                      0, [104, 117, 123])
        self.ai2d.resize(nn.interp_method.tf_bilinear,
                         nn.interp_mode.half_pixel)
        self.ai2d.build([1, 3, self.rgb_size[1], self.rgb_size[0]],
                        [1, 3, self.model_size[1], self.model_size[0]])

    def postprocess(self, results):
        res = aidemo.face_det_post_process(
            self.confidence_threshold, self.nms_threshold,
            self.model_size[0], self.anchors, self.rgb_size, results)
        if len(res) == 0:
            return [], []
        return res[0], res[1]


class FaceEmbeddingLite(AIBase):
    """Mobile 112x112 face embedding model used by registration/recognition."""

    REFERENCE_POINTS = [
        38.2946, 51.6963,
        73.5318, 51.5014,
        56.0252, 71.7366,
        41.5493, 92.3655,
        70.7299, 92.2041,
    ]

    def __init__(self, kmodel_path, rgb_size):
        try:
            self.model_size = [112, 112]
            self.rgb_size = [ALIGN_UP(rgb_size[0], 16), rgb_size[1]]
            super().__init__(kmodel_path, self.model_size, self.rgb_size, 0)
            self.ai2d = Ai2d(0)
            self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT,
                                     nn.ai2d_format.NCHW_FMT,
                                     np.uint8, np.uint8)
        except BaseException:
            # The caller cannot own this model until construction returns.
            try:
                self.deinit()
            except Exception as error:
                print("model constructor cleanup failed:", error)
            raise

    def config_preprocess(self, landmarks):
        matrix = self._affine_matrix(landmarks)
        self.ai2d.affine(nn.interp_method.cv2_bilinear,
                         0, 0, 127, 1, matrix)
        self.ai2d.build([1, 3, self.rgb_size[1], self.rgb_size[0]],
                        [1, 3, self.model_size[1], self.model_size[0]])

    def postprocess(self, results):
        return results[0][0]

    @staticmethod
    def _svd22(a):
        s = [0.0, 0.0]
        u = [0.0, 0.0, 0.0, 0.0]
        v = [0.0, 0.0, 0.0, 0.0]
        s[0] = (math.sqrt((a[0] - a[3]) ** 2 +
                          (a[1] + a[2]) ** 2) +
                math.sqrt((a[0] + a[3]) ** 2 +
                          (a[1] - a[2]) ** 2)) / 2
        s[1] = abs(s[0] - math.sqrt((a[0] - a[3]) ** 2 +
                                    (a[1] + a[2]) ** 2))
        if s[0] > s[1]:
            v[2] = math.sin(math.atan2(
                2 * (a[0] * a[1] + a[2] * a[3]),
                a[0] ** 2 - a[1] ** 2 + a[2] ** 2 - a[3] ** 2) / 2)
        else:
            v[2] = 0
        v[0] = math.sqrt(1 - v[2] ** 2)
        v[1] = -v[2]
        v[3] = v[0]
        if s[0] != 0:
            u[0] = -(a[0] * v[0] + a[1] * v[2]) / s[0]
            u[2] = -(a[2] * v[0] + a[3] * v[2]) / s[0]
        else:
            u[0], u[2] = 1, 0
        if s[1] != 0:
            u[1] = (a[0] * v[1] + a[1] * v[3]) / s[1]
            u[3] = (a[2] * v[1] + a[3] * v[3]) / s[1]
        else:
            u[1], u[3] = -u[2], u[0]
        v[0] = -v[0]
        v[2] = -v[2]
        return u, s, v

    def _umeyama_112(self, src):
        count = 5
        src_mean = [0.0, 0.0]
        dst_mean = [0.0, 0.0]
        dst = self.REFERENCE_POINTS
        for i in range(0, count * 2, 2):
            src_mean[0] += src[i]
            src_mean[1] += src[i + 1]
            dst_mean[0] += dst[i]
            dst_mean[1] += dst[i + 1]
        src_mean[0] /= count
        src_mean[1] /= count
        dst_mean[0] /= count
        dst_mean[1] /= count

        src_demean = [[0.0, 0.0] for _ in range(count)]
        dst_demean = [[0.0, 0.0] for _ in range(count)]
        for i in range(count):
            src_demean[i][0] = src[2 * i] - src_mean[0]
            src_demean[i][1] = src[2 * i + 1] - src_mean[1]
            dst_demean[i][0] = dst[2 * i] - dst_mean[0]
            dst_demean[i][1] = dst[2 * i + 1] - dst_mean[1]

        a = [[0.0, 0.0], [0.0, 0.0]]
        for row in range(2):
            for col in range(2):
                for i in range(count):
                    a[row][col] += dst_demean[i][row] * \
                                   src_demean[i][col]
                a[row][col] /= count

        transform = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        u, singular, v = self._svd22(
            [a[0][0], a[0][1], a[1][0], a[1][1]])
        transform[0][0] = u[0] * v[0] + u[1] * v[2]
        transform[0][1] = u[0] * v[1] + u[1] * v[3]
        transform[1][0] = u[2] * v[0] + u[3] * v[2]
        transform[1][1] = u[2] * v[1] + u[3] * v[3]

        variance = [0.0, 0.0]
        for i in range(count):
            variance[0] += src_demean[i][0] * src_demean[i][0]
            variance[1] += src_demean[i][1] * src_demean[i][1]
        variance[0] /= count
        variance[1] /= count
        variance_sum = variance[0] + variance[1]
        scale = (singular[0] + singular[1]) / variance_sum \
            if variance_sum != 0 else 1.0

        transform[0][2] = dst_mean[0] - scale * (
            transform[0][0] * src_mean[0] +
            transform[0][1] * src_mean[1])
        transform[1][2] = dst_mean[1] - scale * (
            transform[1][0] * src_mean[0] +
            transform[1][1] * src_mean[1])
        transform[0][0] *= scale
        transform[0][1] *= scale
        transform[1][0] *= scale
        transform[1][1] *= scale
        return transform

    def _affine_matrix(self, landmarks):
        matrix = self._umeyama_112(landmarks)
        return [matrix[0][0], matrix[0][1], matrix[0][2],
                matrix[1][0], matrix[1][1], matrix[1][2]]


class FaceFeatureDatabase:
    """Filesystem database shared by the two apps, without shared runtime state."""

    INVALID_FILENAME_CHARS = '/\\:*?"<>|'

    def __init__(self, directory, max_faces=MAX_DATABASE_FACES):
        self.directory = directory if directory.endswith('/') \
            else directory + '/'
        self.max_faces = max_faces
        self.names = []
        self.features = []
        self._ensure_directory()

    def _ensure_directory(self):
        try:
            os.stat(self.directory)
        except OSError:
            os.mkdir(self.directory[:-1])

    @classmethod
    def sanitize_name(cls, name):
        name = name.strip()
        chars = []
        for char in name:
            if char in cls.INVALID_FILENAME_CHARS or ord(char) < 32:
                chars.append('_')
            else:
                chars.append(char)
        safe = ''.join(chars).strip(' .')
        if len(safe) > 24:
            safe = safe[:24]
        if not safe:
            raise ValueError('invalid face name')
        return safe

    @staticmethod
    def normalize(feature):
        norm = np.linalg.norm(feature)
        if norm <= 0:
            raise ValueError('empty face feature')
        return feature / norm

    def save(self, name, feature):
        safe_name = self.sanitize_name(name)
        if feature is None or len(feature) != FEATURE_SIZE:
            raise ValueError('invalid face feature size: %d' %
                             (len(feature) if feature is not None else 0))
        path = self.directory + safe_name + '.bin'
        exists = True
        try:
            os.stat(path)
        except OSError:
            exists = False
        if not exists:
            count = 0
            for filename in os.listdir(self.directory):
                if filename.endswith('.bin'):
                    count += 1
            if count >= self.max_faces:
                raise ValueError('face database is full')

        # Keep exactly the same on-disk format as 05-AI-Demo: the model's raw
        # 512-dimensional float output.  Normalization belongs to matching,
        # not persistence.  Besides retaining compatibility with databases
        # produced by that example, this avoids ulab creating a temporary
        # result with a different dtype on some firmware versions.
        data = feature.tobytes()
        with open(path, 'wb') as file:
            file.write(data)

        # File close already flushes the stream.  sync() is only an additional
        # best-effort SD-card flush and must not turn a completed registration
        # into a UI failure on firmware/filesystems that do not support it.
        sync = getattr(os, 'sync', None)
        if sync:
            try:
                sync()
            except Exception as error:
                print('Face database: sync warning:', error)

        # Validate the file using stat rather than allocating another 2048-byte
        # read buffer immediately after inference.  st_size is tuple item 6 in
        # MicroPython's os.stat result.
        saved_size = os.stat(path)[6]
        if saved_size != len(data):
            raise OSError('face feature write size %d, expected %d' %
                          (saved_size, len(data)))
        print('Face database: saved %s (%d bytes) to %s' %
              (safe_name, len(data), path))
        return safe_name

    def list_names(self):
        """Return valid registered identities without loading embeddings."""
        names = []
        try:
            files = os.listdir(self.directory)
        except OSError:
            return names
        files.sort()
        # Derive the ulab float width used by this firmware instead of
        # assuming a host-Python dtype size.
        expected_size = FEATURE_SIZE * len(
            np.array([0.0], dtype=np.float).tobytes())
        for filename in files:
            if not filename.endswith('.bin'):
                continue
            try:
                if os.stat(self.directory + filename)[6] != expected_size:
                    continue
                names.append(filename[:-4])
            except OSError as error:
                print('Face database: query failed %s: %s' %
                      (filename, error))
        return names

    def clear(self):
        """Delete every face feature file and clear any in-memory cache."""
        removed = 0
        failed = 0
        try:
            files = os.listdir(self.directory)
        except OSError:
            files = []
        for filename in files:
            if not filename.endswith('.bin'):
                continue
            try:
                os.remove(self.directory + filename)
                removed += 1
            except OSError as error:
                failed += 1
                print('Face database: remove failed %s: %s' %
                      (filename, error))
        self.names = []
        self.features = []
        sync = getattr(os, 'sync', None)
        if sync:
            try:
                sync()
            except Exception as error:
                print('Face database: sync warning:', error)
        if failed:
            raise OSError('failed to remove %d face(s)' % failed)
        print('Face database: removed %d face(s)' % removed)
        return removed

    def load(self):
        self.names = []
        self.features = []
        try:
            files = os.listdir(self.directory)
        except OSError:
            return 0
        for filename in files:
            if not filename.endswith('.bin'):
                continue
            if len(self.names) >= self.max_faces:
                break
            try:
                with open(self.directory + filename, 'rb') as file:
                    feature = np.frombuffer(file.read(), dtype=np.float)
                if len(feature) != FEATURE_SIZE:
                    print('Face database: skip invalid feature', filename)
                    continue
                self.features.append(self.normalize(feature))
                self.names.append(filename[:-4])
            except Exception as error:
                print('Face database: failed to load %s: %s' %
                      (filename, error))
        print('Face database: loaded %d face(s) from %s' %
              (len(self.names), self.directory))
        return len(self.names)

    def search(self, feature, threshold=0.75):
        if not self.features:
            return 'unknown', 0.0
        normalized = self.normalize(feature)
        best_index = -1
        best_score = 0.0
        for index in range(len(self.features)):
            score = float(np.dot(normalized, self.features[index]) / 2 + 0.5)
            if score > best_score:
                best_score = score
                best_index = index
        if best_index < 0 or best_score < threshold:
            return 'unknown', best_score
        return self.names[best_index], best_score
