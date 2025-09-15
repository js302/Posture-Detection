import time
import json
import sqlite3
import threading
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import psutil

from posture_analyzer import PostureMetrics
from pc_lock_manager import PCLockManager


class PostureState(Enum):
    GOOD = "good"
    WARNING = "warning"
    BAD = "bad"


@dataclass
class PostureEvent:
    timestamp: float
    state: PostureState
    metrics: PostureMetrics
    violations: Dict[str, bool]
    duration: float = 0.0


@dataclass
class WorkSession:
    start_time: float
    end_time: Optional[float] = None
    total_bad_posture_duration: float = 0.0
    total_warnings: int = 0
    events: List[PostureEvent] = None

    def __post_init__(self):
        if self.events is None:
            self.events = []


class PostureAgent:
    def __init__(self, db_path: str = None):
        if db_path is None:
            data_dir = os.path.join(os.path.dirname(__file__), "data")
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "posture_data.db")

        self.db_path = db_path
        self.current_session = None
        self.current_state = PostureState.GOOD
        self.last_state_change = time.time()

        self.bad_posture_accumulator = 0.0
        self.warning_thresholds = [
            15,  # 15 seconds
            45,  # 45 seconds
            120,  # 2 minutes
        ]  # More frequent warnings for testing
        self.last_warning_level = -1

        self.is_active = False
        self.work_hours = (9, 23)  # 9 AM to 11 PM - temporary
        self.require_ac_power = True
        self.manual_disable_until = None

        # Auto-lock functionality
        self.pc_lock_manager = PCLockManager()
        self.auto_lock_enabled = False
        self.person_absent_threshold = 10.0  # seconds
        self.lock_timeout = 30.0  # seconds

        self.db_lock = threading.Lock()
        self.init_database()

    def init_database(self):
        """Initialize SQLite database for posture tracking"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS work_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_time REAL,
                    end_time REAL,
                    total_bad_posture_duration REAL,
                    total_warnings INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS posture_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER,
                    timestamp REAL,
                    state TEXT,
                    neck_tilt REAL,
                    head_pitch REAL,
                    torso_lean REAL,
                    shoulder_asymmetry REAL,
                    violations TEXT,
                    duration REAL,
                    FOREIGN KEY (session_id) REFERENCES work_sessions (id)
                )
            """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    feedback_type TEXT,
                    helpful BOOLEAN,
                    comments TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

    def set_auto_lock_enabled(self, enabled: bool):
        """Enable or disable auto-lock functionality"""
        self.auto_lock_enabled = enabled
        self.pc_lock_manager.set_enabled(enabled)
        print(f"Auto-lock {'enabled' if enabled else 'disabled'}")
        
    def set_person_absent_threshold(self, seconds: float):
        """Set threshold for person absence detection"""
        self.person_absent_threshold = max(1.0, seconds)
        self.pc_lock_manager.set_person_absent_threshold(seconds)
        
    def set_lock_timeout(self, seconds: float):
        """Set timeout for user acknowledgment before locking"""
        self.lock_timeout = max(5.0, seconds)
        self.pc_lock_manager.set_lock_timeout(seconds)
        
    def update_person_presence(self, person_detected: bool):
        """Update person presence for auto-lock functionality"""
        if self.auto_lock_enabled:
            self.pc_lock_manager.update_person_presence(person_detected)
            
    def get_auto_lock_status(self) -> dict:
        """Get auto-lock status information"""
        return {
            'enabled': self.auto_lock_enabled,
            'person_absent_threshold': self.person_absent_threshold,
            'lock_timeout': self.lock_timeout,
            **self.pc_lock_manager.get_status()
        }

    def should_be_active(self) -> bool:
        """Check if agent should be active based on conditions"""
        current_hour = datetime.now().hour

        # Check work hours
        if not (self.work_hours[0] <= current_hour <= self.work_hours[1]):
            return False

        # Check manual disable
        if self.manual_disable_until and time.time() < self.manual_disable_until:
            return False

        # Check AC power if required
        if self.require_ac_power:
            try:
                battery = psutil.sensors_battery()
                if battery and not battery.power_plugged:
                    return False
            except:
                pass  # If can't check battery, assume it's OK

        return True

    def start_session(self):
        """Start a new work session"""
        if self.current_session:
            self.end_session()

        self.current_session = WorkSession(start_time=time.time())
        self.bad_posture_accumulator = 0.0
        self.last_warning_level = -1
        self.is_active = True

        print(
            f"Started new posture monitoring session at {datetime.now().strftime('%H:%M:%S')}"
        )

    def end_session(self):
        """End current work session and save to database"""
        if not self.current_session:
            print("Debug: No active session to end")
            return

        self.current_session.end_time = time.time()
        self.current_session.total_bad_posture_duration = self.bad_posture_accumulator

        print(
            f"Debug: Ending session with {len(self.current_session.events)} events and {self.current_session.total_warnings} warnings"
        )

        with self.db_lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO work_sessions 
                    (start_time, end_time, total_bad_posture_duration, total_warnings)
                    VALUES (?, ?, ?, ?)
                """,
                    (
                        self.current_session.start_time,
                        self.current_session.end_time,
                        self.current_session.total_bad_posture_duration,
                        self.current_session.total_warnings,
                    ),
                )

                session_id = cursor.lastrowid
                print(f"Debug: Saved session with ID {session_id}")

                # Save events
                for event in self.current_session.events:
                    violations_json = {k: bool(v) for k, v in event.violations.items()}

                    conn.execute(
                        """
                        INSERT INTO posture_events 
                        (session_id, timestamp, state, neck_tilt, head_pitch, 
                         torso_lean, shoulder_asymmetry, violations, duration)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            session_id,
                            event.timestamp,
                            event.state.value,
                            event.metrics.neck_tilt_angle,
                            event.metrics.head_pitch,
                            event.metrics.torso_lean,
                            event.metrics.shoulder_asymmetry,
                            json.dumps(violations_json),
                            event.duration,
                        ),
                    )

        session_duration = (
            self.current_session.end_time - self.current_session.start_time
        )
        bad_posture_percentage = (
            self.bad_posture_accumulator / max(session_duration, 1)
        ) * 100

        print(
            f"Session ended. Duration: {session_duration/3600:.1f}h, "
            f"Bad posture: {bad_posture_percentage:.1f}%, "
            f"Warnings: {self.current_session.total_warnings}"
        )

        self.current_session = None
        self.is_active = False

    def process_posture_update(
        self, metrics: PostureMetrics, violations: Dict[str, bool]
    ) -> Optional[str]:
        """Process posture update and return notification message if needed"""
        if not self.should_be_active():
            if self.is_active:
                self.end_session()
            return None

        if not self.is_active:
            self.start_session()

        current_time = time.time()
        is_bad_posture = any(violations.values())

        # Determine new state
        new_state = PostureState.BAD if is_bad_posture else PostureState.GOOD

        # Debug: Show what determines the state
        if is_bad_posture:
            active_violations = [k for k, v in violations.items() if v]
            print(f"Debug: Bad posture detected with violations: {active_violations}")

        # Calculate duration in current state
        state_duration = current_time - self.last_state_change

        # Only record state changes if they've lasted at least 2 seconds to reduce noise
        min_state_duration = 2.0

        # If state changed and the previous state lasted long enough, record the event
        if new_state != self.current_state and state_duration >= min_state_duration:
            if self.current_state == PostureState.BAD:
                self.bad_posture_accumulator += state_duration

            # Create event for the completed state
            event = PostureEvent(
                timestamp=self.last_state_change,
                state=self.current_state,
                metrics=metrics,
                violations=violations,
                duration=state_duration,
            )

            if self.current_session:
                self.current_session.events.append(event)

            self.current_state = new_state
            self.last_state_change = current_time

            print(
                f"Posture state changed to {new_state.value} (was {event.state.value} for {state_duration:.1f}s)"
            )
        elif new_state != self.current_state:
            # State changed but didn't last long enough - just update the state without recording
            self.current_state = new_state
            self.last_state_change = current_time

        # Always check for warnings when in bad posture (not just on state change)
        notification_message = None
        if self.current_state == PostureState.BAD:
            current_bad_duration = self.bad_posture_accumulator + (
                current_time - self.last_state_change
            )

            print(
                f"Debug: Current bad duration: {current_bad_duration:.1f}s, Accumulated: {self.bad_posture_accumulator:.1f}s, Last warning level: {self.last_warning_level}"
            )

            for i, threshold in enumerate(self.warning_thresholds):
                if current_bad_duration >= threshold and i > self.last_warning_level:
                    self.last_warning_level = i
                    if self.current_session:
                        self.current_session.total_warnings += 1
                        print(
                            f"Debug: Warning triggered! Level {i} at {current_bad_duration:.1f}s, Total warnings: {self.current_session.total_warnings}"
                        )

                    notification_message = self.generate_warning_message(
                        i, current_bad_duration, violations
                    )
                    break
        else:
            # Reset warning level and reduce accumulated bad posture time after sustained good posture
            if self.last_warning_level >= 0:
                good_duration = current_time - self.last_state_change
                if good_duration > 10:  # 10 seconds of good posture before reset
                    print(
                        f"Debug: Good posture for {good_duration:.1f}s, resetting warning level and reducing bad posture accumulator"
                    )
                    self.last_warning_level = -1
                    # Reduce accumulated bad posture time when maintaining good posture
                    self.bad_posture_accumulator = max(
                        0, self.bad_posture_accumulator - good_duration
                    )

        return notification_message

    def generate_warning_message(
        self, warning_level: int, duration: float, violations: Dict[str, bool]
    ) -> str:
        """Generate appropriate warning message based on level and violations"""
        duration_minutes = duration / 60

        primary_issues = [k for k, v in violations.items() if v]

        messages = {
            0: f"Posture check: You've been in poor posture for {duration_minutes:.1f} minutes. "
            f"Main issues: {', '.join(primary_issues)}. Consider adjusting your position.",
            1: f"Posture reminder: {duration_minutes:.1f} minutes of poor posture detected. "
            f"Time for a quick posture reset! Focus on: {', '.join(primary_issues)}.",
            2: f"Break time: You've been slouching for {duration_minutes:.1f} minutes. "
            f"Stand up, stretch, and reset your workspace setup.",
        }

        return messages.get(
            warning_level,
            f"Extended poor posture detected: {duration_minutes:.1f} minutes",
        )

    def manually_disable(self, duration_minutes: int):
        """Manually disable monitoring for specified duration"""
        self.manual_disable_until = time.time() + (duration_minutes * 60)
        print(f"Posture monitoring disabled for {duration_minutes} minutes")

    def check_power_status(self) -> bool:
        """Check if AC power is connected (separate method for testing)"""
        if not self.require_ac_power:
            return True

        try:
            battery = psutil.sensors_battery()
            if battery:
                power_connected = battery.power_plugged
                print(f"Debug: AC Power connected: {power_connected}")
                return power_connected
            return True  # If no battery info, assume desktop/always powered
        except Exception as e:
            print(f"Debug: Error checking power status: {e}")
            return True  # Default to allowing operation if can't check

    def force_stop_if_unpowered(self) -> bool:
        """Force stop session if power requirements not met"""
        if not self.check_power_status():
            print("AC power disconnected - stopping session")
            if self.is_active:
                self.end_session()
            return True
        return False

    def record_feedback(self, feedback_type: str, helpful: bool, comments: str = ""):
        """Record user feedback for learning"""
        with self.db_lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO user_feedback (timestamp, feedback_type, helpful, comments)
                    VALUES (?, ?, ?, ?)
                """,
                    (time.time(), feedback_type, helpful, comments),
                )

    def get_daily_summary(self, date: Optional[datetime] = None) -> Dict[str, Any]:
        """Get daily posture summary"""
        if date is None:
            date = datetime.now()

        start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        with self.db_lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT 
                        SUM(total_bad_posture_duration) as total_bad_duration,
                        SUM(total_warnings) as total_warnings,
                        COUNT(*) as session_count,
                        SUM(CASE 
                            WHEN end_time IS NOT NULL THEN end_time - start_time 
                            ELSE 0 
                        END) as total_work_time
                    FROM work_sessions 
                    WHERE start_time >= ? AND start_time < ? AND end_time IS NOT NULL
                """,
                    (start_of_day.timestamp(), end_of_day.timestamp()),
                )

                result = cursor.fetchone()

                return {
                    "date": date.strftime("%Y-%m-%d"),
                    "total_bad_duration": result[0] or 0,
                    "total_warnings": result[1] or 0,
                    "session_count": result[2] or 0,
                    "total_work_time": result[3] or 0,
                    "posture_score": 100
                    - ((result[0] or 0) / max(result[3] or 1, 1)) * 100,
                }

    def get_weekly_trend(self) -> List[Dict[str, Any]]:
        """Get weekly posture trend"""
        today = datetime.now()
        week_start = today - timedelta(days=7)

        daily_summaries = []
        for i in range(7):
            day = week_start + timedelta(days=i)
            summary = self.get_daily_summary(day)
            daily_summaries.append(summary)

        return daily_summaries

    def export_session_data(self, days: int = 7) -> Dict[str, Any]:
        """Export recent session data for analysis"""
        since = time.time() - (days * 24 * 3600)

        with self.db_lock:
            with sqlite3.connect(self.db_path) as conn:
                # Get sessions
                sessions = conn.execute(
                    """
                    SELECT * FROM work_sessions 
                    WHERE start_time >= ?
                    ORDER BY start_time DESC
                """,
                    (since,),
                ).fetchall()

                # Get events
                events = conn.execute(
                    """
                    SELECT pe.*, ws.start_time as session_start
                    FROM posture_events pe
                    JOIN work_sessions ws ON pe.session_id = ws.id
                    WHERE ws.start_time >= ?
                    ORDER BY pe.timestamp DESC
                """,
                    (since,),
                ).fetchall()

                return {
                    "sessions": sessions,
                    "events": events,
                    "export_date": datetime.now().isoformat(),
                    "days_included": days,
                }
