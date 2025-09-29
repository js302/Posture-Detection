import cv2
import numpy as np
import threading
import time
from typing import Optional, Callable, Dict, Any
import sys
import os
from logger_config import get_logger

from qai_hub_models.models.mediapipe_pose.app import MediaPipePoseApp
from qai_hub_models.models.mediapipe_pose.model import MediaPipePose
from posture_analyzer import PostureAnalyzer, PostureMetrics


class PostureCameraManager:
    def __init__(self, camera_id: int = 0, fps: int = 15):
        self.logger = get_logger("camera_manager")

        self.camera_id = camera_id
        self.fps = fps
        self.cap = None
        self.is_running = False
        self.frame_thread = None
        self.current_frame = None
        self.current_metrics = None
        self.frame_lock = threading.Lock()
        self.metrics_lock = threading.Lock()

        self.pose_app = None
        self.posture_analyzer = PostureAnalyzer(fps=fps)

        self.frame_callback = None
        self.posture_callback = None
        self.person_detection_callback = None

        # Add frame skip for GUI updates to reduce flickering
        self.frame_skip_count = 0
        self.gui_update_interval = 2

        # Person detection tracking
        self.person_detected_threshold = (
            0.2  # Lowered confidence threshold for person detection
        )
        self.no_person_frames = 0  # Count consecutive frames without person
        self.person_frames = 0  # Count consecutive frames with person
        self.detection_stability_frames = 5  # Frames needed for stable detection

    def initialize_models(self):
        """Initialize MediaPipe pose detection models"""
        print("Loading MediaPipe Pose models...")
        try:
            model = MediaPipePose.from_pretrained()
            self.pose_app = MediaPipePoseApp.from_pretrained(model)
            print("Models loaded successfully")
            return True
        except Exception as e:
            print(f"Error loading models: {e}")
            return False

    def initialize_camera(self):
        """Initialize camera capture"""
        try:
            self.cap = cv2.VideoCapture(self.camera_id)
            if not self.cap.isOpened():
                raise Exception(f"Could not open camera {self.camera_id}")

            self.cap.set(cv2.CAP_PROP_FPS, self.fps)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

            print(f"Camera {self.camera_id} initialized successfully")
            return True
        except Exception as e:
            print(f"Error initializing camera: {e}")
            return False

    def set_person_detection_callback(self, callback: Callable[[bool], None]):
        """Set callback for person presence detection"""
        self.person_detection_callback = callback

    def set_frame_callback(self, callback: Callable[[np.ndarray], None]):
        """Set callback for processed frames"""
        self.frame_callback = callback

    def set_posture_callback(self, callback: Callable[[PostureMetrics, Dict], None]):
        """Set callback for posture analysis results"""
        self.posture_callback = callback

    def is_person_detected(self, keypoints: Optional[np.ndarray]) -> bool:
        """Determine if a person is detected based on keypoints quality"""
        if keypoints is None:
            self.logger.debug("Person detection: keypoints is None")
            return False

        # Debug keypoints structure
        if hasattr(self, "_debug_frame_count"):
            self._debug_frame_count += 1
        else:
            self._debug_frame_count = 0

        # Use more keypoints and be more lenient
        key_points = [
            0,  # Nose
            11,  # Left Shoulder
            12,  # Right Shoulder
            7,  # Left Ear
            8,  # Right Ear
            13,  # Left Elbow
            14,  # Right Elbow
            15,  # Left Wrist
            16,  # Right Wrist
        ]

        try:
            visible_key_points = 0
            total_checked = 0

            for point_idx in key_points:
                if point_idx < len(keypoints):
                    total_checked += 1
                    # Check if point has reasonable confidence (assuming 3rd dimension is confidence)
                    if len(keypoints[point_idx]) >= 3:
                        confidence = keypoints[point_idx][2]
                        # Much lower threshold since MediaPipe confidence values are very low
                        if confidence > -0.5:  # Accept almost any confidence above -0.5
                            visible_key_points += 1
                    else:
                        # If no confidence available, check if coordinates are reasonable
                        x, y = keypoints[point_idx][:2]
                        if x > 0 and y > 0:  # Basic validity check
                            visible_key_points += 1

            # More lenient requirement: at least 2 out of available keypoints
            # This should catch most cases where a person is present
            detected = visible_key_points >= 2

            self.logger.debug(
                f"Person detection: {visible_key_points}/{total_checked} keypoints, detected={detected}"
            )

            return detected

        except (IndexError, TypeError) as e:
            self.logger.error(f"Person detection error: {e}")
            return False

    def process_frame(
        self, frame: np.ndarray
    ) -> tuple[np.ndarray, Optional[PostureMetrics]]:
        """Process single frame for pose detection and posture analysis"""
        try:
            # Convert BGR to RGB for MediaPipe
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Get pose landmarks with raw output
            pose_results = self.pose_app.predict_landmarks_from_image(
                rgb_frame, raw_output=True
            )

            if not pose_results or len(pose_results) < 4:
                return frame, None

            # Extract components from raw output
            (
                batched_selected_boxes,
                batched_selected_keypoints,
                batched_roi_4corners,
                batched_selected_landmarks,
            ) = pose_results[:4]

            # Get annotated image for display
            annotated_results = self.pose_app.predict_landmarks_from_image(
                rgb_frame, raw_output=False
            )

            if (
                annotated_results
                and len(annotated_results) > 0
                and isinstance(annotated_results[0], np.ndarray)
            ):
                annotated_frame = annotated_results[0]
            else:
                annotated_frame = rgb_frame

            # Extract keypoints for posture analysis
            keypoints = self.extract_keypoints_from_raw_output(
                batched_selected_landmarks
            )

            # Check person detection
            person_detected = self.is_person_detected(keypoints)
            self.update_person_detection_state(person_detected)

            if keypoints is not None:
                # Analyze posture
                posture_metrics = self.posture_analyzer.analyze_keypoints(keypoints)

                # Add posture info to frame
                annotated_frame = self.add_posture_overlay(
                    annotated_frame, posture_metrics
                )

                return cv2.cvtColor(annotated_frame, cv2.COLOR_RGB2BGR), posture_metrics
            else:
                # No keypoints detected - still return the annotated frame
                return cv2.cvtColor(annotated_frame, cv2.COLOR_RGB2BGR), None

        except Exception as e:
            print(f"Error processing frame: {e}")
            return frame, None

    def update_person_detection_state(self, person_detected_current_frame: bool):
        """Update person detection state with stability checking"""
        if person_detected_current_frame:
            self.person_frames += 1
            self.no_person_frames = 0

            # Stable person detection
            if (
                self.person_frames >= self.detection_stability_frames
                and self.person_detection_callback
            ):
                print(
                    f"Person detection: STABLE PRESENT (frames: {self.person_frames})"
                )
                self.person_detection_callback(True)

        else:
            self.no_person_frames += 1
            self.person_frames = 0

            # Stable no-person detection
            if (
                self.no_person_frames >= self.detection_stability_frames
                and self.person_detection_callback
            ):
                print(
                    f"Person detection: STABLE ABSENT (frames: {self.no_person_frames})"
                )
                self.person_detection_callback(False)

    def extract_keypoints_from_raw_output(
        self, batched_landmarks
    ) -> Optional[np.ndarray]:
        """Extract keypoints from MediaPipe raw output"""
        try:
            if not batched_landmarks or len(batched_landmarks) == 0:
                return None

            # Get first batch (first image)
            batch_landmarks = batched_landmarks[0]

            if len(batch_landmarks) == 0:
                return None

            # Get first detected person
            person_landmarks = batch_landmarks[0]

            # Convert to numpy array if it's a tensor
            if hasattr(person_landmarks, "numpy"):
                keypoints = person_landmarks.numpy()
            elif hasattr(person_landmarks, "detach"):
                keypoints = person_landmarks.detach().cpu().numpy()
            else:
                keypoints = np.array(person_landmarks)

            # Ensure we have the expected shape [num_landmarks, 3]
            if len(keypoints.shape) == 2 and keypoints.shape[1] >= 2:
                return keypoints
            else:
                print(f"Unexpected keypoints shape: {keypoints.shape}")
                return None

        except Exception as e:
            print(f"Error extracting keypoints: {e}")
            return None

    def add_posture_overlay(
        self, frame: np.ndarray, metrics: PostureMetrics
    ) -> np.ndarray:
        """Add posture information overlay to frame"""
        frame_copy = frame.copy()
        height, width = frame_copy.shape[:2]

        # Add text overlay with posture metrics
        overlay_y = 30
        line_height = 25
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.6
        color = (0, 255, 0)  # Green
        thickness = 2

        # Display metrics
        metrics_text = [
            f"Neck Tilt: {metrics.neck_tilt_angle:.1f}°",
            f"Head Pitch: {metrics.head_pitch:.1f}°",
            f"Torso Lean: {metrics.torso_lean:.1f}°",
            f"Shoulder Asymmetry: {metrics.shoulder_asymmetry:.1f}px",
        ]

        # Check for violations and change color
        violations = self.posture_analyzer.is_bad_posture(metrics)
        if any(violations.values()):
            color = (0, 0, 255)  # Red for bad posture

        for i, text in enumerate(metrics_text):
            y_pos = overlay_y + i * line_height
            cv2.putText(
                frame_copy, text, (10, y_pos), font, font_scale, color, thickness
            )

        # Add violation indicators
        violation_text = []
        if violations["neck_tilt"]:
            violation_text.append("Forward Head")
        if violations["head_pitch"]:
            violation_text.append("Looking Down")
        if violations["torso_lean"]:
            violation_text.append("Slouching")
        if violations["shoulder_asymmetry"]:
            violation_text.append("Uneven Shoulders")

        if violation_text:
            for i, text in enumerate(violation_text):
                y_pos = overlay_y + (len(metrics_text) + i + 1) * line_height
                cv2.putText(
                    frame_copy,
                    text,
                    (10, y_pos),
                    font,
                    font_scale,
                    (0, 0, 255),
                    thickness,
                )

        return frame_copy

    def capture_loop(self):
        """Main camera capture loop"""
        frame_time = 1.0 / self.fps

        while self.is_running:
            start_time = time.time()

            ret, frame = self.cap.read()
            if not ret:
                print("Failed to capture frame")
                continue

            # Process frame
            processed_frame, posture_metrics = self.process_frame(frame)

            # Update current frame and metrics
            with self.frame_lock:
                self.current_frame = processed_frame

            with self.metrics_lock:
                self.current_metrics = posture_metrics

            # Only call GUI callback periodically to reduce flickering
            self.frame_skip_count += 1
            if (
                self.frame_callback
                and self.frame_skip_count >= self.gui_update_interval
            ):
                self.frame_callback(processed_frame)
                self.frame_skip_count = 0

            # Always process posture data for accurate analysis
            if self.posture_callback and posture_metrics:
                violations = self.posture_analyzer.is_bad_posture(posture_metrics)
                self.posture_callback(posture_metrics, violations)

            # Maintain FPS
            elapsed = time.time() - start_time
            sleep_time = max(0, frame_time - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def start(self):
        """Start camera capture and processing"""
        if not self.initialize_models():
            return False

        if not self.initialize_camera():
            return False

        self.is_running = True
        self.frame_thread = threading.Thread(target=self.capture_loop)
        self.frame_thread.daemon = True
        self.frame_thread.start()

        print("Camera capture started")
        return True

    def stop(self):
        """Stop camera capture"""
        self.is_running = False

        if self.frame_thread:
            self.frame_thread.join(timeout=2.0)

        if self.cap:
            self.cap.release()

        print("Camera capture stopped")

    def get_current_frame(self) -> Optional[np.ndarray]:
        """Get the current processed frame"""
        with self.frame_lock:
            return self.current_frame.copy() if self.current_frame is not None else None

    def get_current_metrics(self) -> Optional[PostureMetrics]:
        """Get the current posture metrics"""
        with self.metrics_lock:
            return self.current_metrics

    def get_posture_summary(self) -> Dict[str, Any]:
        """Get current posture analysis summary"""
        return self.posture_analyzer.get_current_posture_summary()

    def check_alert_conditions(self) -> tuple[bool, Dict]:
        """Check if posture alert should be triggered"""
        return self.posture_analyzer.should_trigger_alert()
