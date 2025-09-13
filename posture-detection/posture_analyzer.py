import numpy as np
import math
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from collections import deque
import time


@dataclass
class PostureMetrics:
    neck_tilt_angle: float
    head_pitch: float
    torso_lean: float
    shoulder_asymmetry: float
    timestamp: float


@dataclass
class PostureThresholds:
    neck_tilt_threshold: float = 20.0
    head_pitch_threshold: float = 30.0
    torso_lean_threshold: float = 15.0
    shoulder_asymmetry_threshold: float = 8.0
    bad_posture_duration_threshold: float = 3.0
    good_posture_required_duration: float = 5.0


class PostureAnalyzer:
    NOSE = 0
    LEFT_EYE_INNER = 1
    LEFT_EYE = 2
    LEFT_EYE_OUTER = 3
    RIGHT_EYE_INNER = 4
    RIGHT_EYE = 5
    RIGHT_EYE_OUTER = 6
    LEFT_EAR = 7
    RIGHT_EAR = 8
    MOUTH_LEFT = 9
    MOUTH_RIGHT = 10
    LEFT_SHOULDER = 11
    RIGHT_SHOULDER = 12
    LEFT_ELBOW = 13
    RIGHT_ELBOW = 14
    LEFT_WRIST = 15
    RIGHT_WRIST = 16
    LEFT_HIP = 23
    RIGHT_HIP = 24

    def __init__(self, window_size: int = 150, fps: int = 30):
        self.window_size = window_size
        self.fps = fps
        self.metrics_window = deque(maxlen=window_size)
        self.thresholds = PostureThresholds()
        self.last_bad_posture_time = 0
        self.last_notification_time = 0
        self.cooldown_duration = 300.0

    def calculate_angle(self, p1: np.ndarray, p2: np.ndarray, p3: np.ndarray) -> float:
        """Calculate angle between three points"""
        v1 = p1 - p2
        v2 = p3 - p2

        cos_angle = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
        cos_angle = np.clip(cos_angle, -1.0, 1.0)
        angle = np.arccos(cos_angle)
        return np.degrees(angle)

    def calculate_neck_tilt_angle(self, keypoints: np.ndarray) -> float:
        """Calculate neck tilt angle using ear and shoulder positions"""
        try:
            left_ear = keypoints[self.LEFT_EAR][:2]
            right_ear = keypoints[self.RIGHT_EAR][:2]
            left_shoulder = keypoints[self.LEFT_SHOULDER][:2]
            right_shoulder = keypoints[self.RIGHT_SHOULDER][:2]

            ear_center = (left_ear + right_ear) / 2
            shoulder_center = (left_shoulder + right_shoulder) / 2

            neck_vector = ear_center - shoulder_center
            vertical_vector = np.array([0, -1])

            dot_product = np.dot(neck_vector, vertical_vector)
            norms = np.linalg.norm(neck_vector) * np.linalg.norm(vertical_vector)

            if norms == 0:
                return 0

            cos_angle = dot_product / norms
            cos_angle = np.clip(cos_angle, -1.0, 1.0)
            angle = np.arccos(cos_angle)

            return np.degrees(angle)
        except (IndexError, ValueError):
            return 0

    def calculate_head_pitch(self, keypoints: np.ndarray) -> float:
        """Calculate head pitch using nose and ear positions"""
        try:
            nose = keypoints[self.NOSE][:2]
            left_ear = keypoints[self.LEFT_EAR][:2]
            right_ear = keypoints[self.RIGHT_EAR][:2]

            ear_center = (left_ear + right_ear) / 2
            head_vector = nose - ear_center

            # horizontal_vector = np.array([1, 0])

            # dot_product = np.dot(head_vector, horizontal_vector)
            # norms = np.linalg.norm(head_vector) * np.linalg.norm(horizontal_vector)

            # if norms == 0:
            #     return 0

            # cos_angle = dot_product / norms
            # cos_angle = np.clip(cos_angle, -1.0, 1.0)
            # angle = np.arccos(cos_angle)

            # pitch = np.degrees(angle) - 90
            # return abs(pitch)

            
            # Calculate the angle of head looking down
            # Positive Y means looking down (nose below ear level)
            head_vector = nose - ear_center
            
            # If nose is significantly below ears, it's looking down
            if head_vector[1] > 0:
                # Calculate angle from horizontal
                angle = np.degrees(np.arctan2(abs(head_vector[1]), abs(head_vector[0])))
                return angle
            else:
                return 0

        except (IndexError, ValueError):
            return 0

    def calculate_torso_lean(self, keypoints: np.ndarray) -> float:
        """Calculate torso lean angle"""
        try:
            left_shoulder = keypoints[self.LEFT_SHOULDER][:2]
            right_shoulder = keypoints[self.RIGHT_SHOULDER][:2]
            left_hip = keypoints[self.LEFT_HIP][:2]
            right_hip = keypoints[self.RIGHT_HIP][:2]

            shoulder_center = (left_shoulder + right_shoulder) / 2
            hip_center = (left_hip + right_hip) / 2

            torso_vector = shoulder_center - hip_center
            vertical_vector = np.array([0, -1])

            dot_product = np.dot(torso_vector, vertical_vector)
            norms = np.linalg.norm(torso_vector) * np.linalg.norm(vertical_vector)

            if norms == 0:
                return 0

            cos_angle = dot_product / norms
            cos_angle = np.clip(cos_angle, -1.0, 1.0)
            angle = np.arccos(cos_angle)

            return np.degrees(angle)
        except (IndexError, ValueError):
            return 0

    def calculate_shoulder_asymmetry(self, keypoints: np.ndarray) -> float:
        """Calculate shoulder height asymmetry in pixels"""
        try:
            left_shoulder = keypoints[self.LEFT_SHOULDER][:2]
            right_shoulder = keypoints[self.RIGHT_SHOULDER][:2]

            height_diff = abs(left_shoulder[1] - right_shoulder[1])
            return height_diff
        except (IndexError, ValueError):
            return 0

    def analyze_keypoints(self, keypoints: np.ndarray) -> PostureMetrics:
        """Analyze posture from MediaPipe keypoints"""
        neck_tilt = self.calculate_neck_tilt_angle(keypoints)
        head_pitch = self.calculate_head_pitch(keypoints)
        torso_lean = self.calculate_torso_lean(keypoints)
        shoulder_asymmetry = self.calculate_shoulder_asymmetry(keypoints)

        metrics = PostureMetrics(
            neck_tilt_angle=neck_tilt,
            head_pitch=head_pitch,
            torso_lean=torso_lean,
            shoulder_asymmetry=shoulder_asymmetry,
            timestamp=time.time(),
        )

        self.metrics_window.append(metrics)
        return metrics

    def is_bad_posture(self, metrics: PostureMetrics) -> Dict[str, bool]:
        """Check if current posture metrics indicate bad posture"""
        violations = {
            "neck_tilt": metrics.neck_tilt_angle > self.thresholds.neck_tilt_threshold,
            "head_pitch": metrics.head_pitch > self.thresholds.head_pitch_threshold,
            "torso_lean": metrics.torso_lean > self.thresholds.torso_lean_threshold,
            "shoulder_asymmetry": metrics.shoulder_asymmetry
            > self.thresholds.shoulder_asymmetry_threshold,
        }

        # Debug output
        if any(violations.values()):
            active_violations = [k for k, v in violations.items() if v]
            print(f"Debug: Violations detected: {active_violations}")
            print(
                f"  Neck: {metrics.neck_tilt_angle:.1f} > {self.thresholds.neck_tilt_threshold}"
            )
            print(
                f"  Head: {metrics.head_pitch:.1f} > {self.thresholds.head_pitch_threshold}"
            )
            print(
                f"  Torso: {metrics.torso_lean:.1f} > {self.thresholds.torso_lean_threshold}"
            )
            print(
                f"  Shoulder: {metrics.shoulder_asymmetry:.1f} > {self.thresholds.shoulder_asymmetry_threshold}"
            )

        return violations

    def should_trigger_alert(self) -> Tuple[bool, Dict[str, float]]:
        """Check if bad posture has persisted long enough to trigger alert"""
        if len(self.metrics_window) < self.fps * 2:
            return False, {}

        current_time = time.time()
        threshold_time = current_time - self.thresholds.bad_posture_duration_threshold

        recent_metrics = [
            m for m in self.metrics_window if m.timestamp >= threshold_time
        ]

        if not recent_metrics:
            return False, {}

        violation_counts = {
            "neck_tilt": 0,
            "head_pitch": 0,
            "torso_lean": 0,
            "shoulder_asymmetry": 0,
        }

        total_samples = len(recent_metrics)

        for metrics in recent_metrics:
            violations = self.is_bad_posture(metrics)
            for key, is_violation in violations.items():
                if is_violation:
                    violation_counts[key] += 1

        violation_percentages = {
            key: (count / total_samples) * 100
            for key, count in violation_counts.items()
        }

        should_alert = any(
            percentage >= 60 for percentage in violation_percentages.values()
        )

        if (
            should_alert
            and (current_time - self.last_notification_time) > self.cooldown_duration
        ):
            self.last_bad_posture_time = current_time
            self.last_notification_time = current_time
            return True, violation_percentages

        return False, violation_percentages

    def is_good_posture_sustained(self) -> bool:
        """Check if good posture has been maintained for required duration"""
        if len(self.metrics_window) < self.fps * 2:
            return False

        current_time = time.time()
        threshold_time = current_time - self.thresholds.good_posture_required_duration

        recent_metrics = [
            m for m in self.metrics_window if m.timestamp >= threshold_time
        ]

        if not recent_metrics:
            return False

        good_posture_count = 0
        for metrics in recent_metrics:
            violations = self.is_bad_posture(metrics)
            if not any(violations.values()):
                good_posture_count += 1

        good_posture_percentage = (good_posture_count / len(recent_metrics)) * 100
        return good_posture_percentage >= 80

    def get_current_posture_summary(self) -> Dict:
        """Get summary of current posture state"""
        if not self.metrics_window:
            return {}

        recent_metrics = list(self.metrics_window)[-30:]

        avg_metrics = {
            "neck_tilt": np.mean([m.neck_tilt_angle for m in recent_metrics]),
            "head_pitch": np.mean([m.head_pitch for m in recent_metrics]),
            "torso_lean": np.mean([m.torso_lean for m in recent_metrics]),
            "shoulder_asymmetry": np.mean(
                [m.shoulder_asymmetry for m in recent_metrics]
            ),
        }

        return {
            "average_metrics": avg_metrics,
            "total_samples": len(self.metrics_window),
            "window_duration": len(self.metrics_window) / self.fps,
        }
