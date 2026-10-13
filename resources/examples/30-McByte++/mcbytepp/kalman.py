# mcbytepp/kalman.py - ByteTrack's constant-velocity Kalman filter.
#
# State is (x, y, a, h, vx, vy, va, vh): box centre, aspect ratio, height, and
# their velocities.  Measurements are (x, y, a, h).  Identical in structure and
# noise weighting to ByteTrack's KalmanFilterXYAH, but every matrix is 2-D so
# that ulab's np.dot is only ever asked to do a plain matrix product -- ulab's
# handling of mixed 1-D/2-D operands is not something to rely on here.

import ulab.numpy as np
from ulab.numpy import linalg as la

NDIM = 4


def _zeros(r, c):
    return np.zeros((r, c))


def _diag_sq(values):
    """diag(v_i^2) -- the process/measurement noise covariances."""
    n = len(values)
    m = np.zeros((n, n))
    for i in range(n):
        m[i, i] = values[i] * values[i]
    return m


class KalmanFilterXYAH:
    def __init__(self):
        dt = 1.0
        self._motion_mat = np.eye(2 * NDIM)
        for i in range(NDIM):
            self._motion_mat[i, NDIM + i] = dt
        self._motion_mat_t = self._motion_mat.transpose()

        self._update_mat = _zeros(NDIM, 2 * NDIM)
        for i in range(NDIM):
            self._update_mat[i, i] = 1.0
        self._update_mat_t = self._update_mat.transpose()

        # Uncertainty scales with the target's height, as in ByteTrack.
        self._std_weight_position = 1.0 / 20
        self._std_weight_velocity = 1.0 / 160

    def initiate(self, measurement):
        """measurement: (x, y, a, h) -> (mean (1,8), covariance (8,8))"""
        x, y, a, h = measurement
        mean = np.array([[x, y, a, h, 0.0, 0.0, 0.0, 0.0]])
        std = [
            2 * self._std_weight_position * h,
            2 * self._std_weight_position * h,
            1e-2,
            2 * self._std_weight_position * h,
            10 * self._std_weight_velocity * h,
            10 * self._std_weight_velocity * h,
            1e-5,
            10 * self._std_weight_velocity * h,
        ]
        return mean, _diag_sq(std)

    def predict(self, mean, covariance):
        h = mean[0, 3]
        std = [
            self._std_weight_position * h,
            self._std_weight_position * h,
            1e-2,
            self._std_weight_position * h,
            self._std_weight_velocity * h,
            self._std_weight_velocity * h,
            1e-5,
            self._std_weight_velocity * h,
        ]
        motion_cov = _diag_sq(std)
        mean = np.dot(mean, self._motion_mat_t)
        covariance = np.dot(np.dot(self._motion_mat, covariance),
                            self._motion_mat_t) + motion_cov
        return mean, covariance

    def project(self, mean, covariance):
        h = mean[0, 3]
        std = [
            self._std_weight_position * h,
            self._std_weight_position * h,
            1e-1,
            self._std_weight_position * h,
        ]
        innovation_cov = _diag_sq(std)
        projected_mean = np.dot(mean, self._update_mat_t)
        projected_cov = np.dot(np.dot(self._update_mat, covariance),
                               self._update_mat_t) + innovation_cov
        return projected_mean, projected_cov

    def update(self, mean, covariance, measurement):
        projected_mean, projected_cov = self.project(mean, covariance)
        kalman_gain = np.dot(np.dot(covariance, self._update_mat_t),
                             la.inv(projected_cov))          # (8, 4)
        innovation = np.array([[
            measurement[0] - projected_mean[0, 0],
            measurement[1] - projected_mean[0, 1],
            measurement[2] - projected_mean[0, 2],
            measurement[3] - projected_mean[0, 3],
        ]])                                                   # (1, 4)
        new_mean = mean + np.dot(innovation, kalman_gain.transpose())
        new_cov = covariance - np.dot(np.dot(kalman_gain, projected_cov),
                                      kalman_gain.transpose())
        return new_mean, new_cov
