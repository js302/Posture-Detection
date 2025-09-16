import time
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional
import ctypes
from ctypes import wintypes
import os
from logger_config import get_logger


class PCLockManager:
    """Manages automatic PC locking based on user presence detection"""

    def __init__(self):
        self.logger = get_logger("pc_lock_manager")

        self.is_enabled = False
        self.person_absent_threshold = 10.0  # seconds before showing notification
        self.lock_timeout = 30.0  # seconds for user to acknowledge before locking

        self.person_present = True
        self.last_person_detected = time.time()
        self.notification_shown = False
        self.notification_window = None
        self.lock_timer_active = False
        self.countdown_callback = None
        self.timer_thread = None
        self.pc_locked = False
        self.testing_mode = False

        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32

        self.LockWorkStation = self.user32.LockWorkStation

    def set_enabled(self, enabled: bool):
        """Enable or disable auto-lock functionality"""
        self.is_enabled = enabled
        if not enabled:
            self.logger.info("Auto-lock disabled")
            self.pc_locked = False
            self.reset_timer()
            if hasattr(self, "_last_person_detected_state"):
                delattr(self, "_last_person_detected_state")

    def set_person_absent_threshold(self, seconds: float):
        """Set threshold for person absence detection"""
        self.person_absent_threshold = max(1.0, seconds)

    def set_lock_timeout(self, seconds: float):
        """Set timeout for user acknowledgment"""
        self.lock_timeout = max(1.0, seconds)

    def update_person_presence(self, person_detected: bool):
        """Update person presence status"""
        current_time = time.time()

        self.check_windows_lock_status()

        if (
            hasattr(self, "_last_person_detected_state")
            and self._last_person_detected_state == person_detected
        ):
            return
        self._last_person_detected_state = person_detected

        if person_detected:
            if not self.person_present:
                self.logger.info("Person returned to desk")
                self.wake_screen_mouse_only()

            self.person_present = True
            self.last_person_detected = current_time
            self.pc_locked = False

            if self.lock_timer_active:
                self.logger.info("Resetting active timer due to person detection")
                self.reset_timer()
        else:
            if self.person_present:
                self.logger.info("Person absence detected")
                self.person_present = False

                if (
                    self.is_enabled
                    and not self.lock_timer_active
                    and not self.notification_shown
                    and not self.pc_locked
                ):
                    self.start_absence_timer()

    def start_absence_timer(self):
        """Start timer for person absence detection"""
        if self.timer_thread and self.timer_thread.is_alive():
            return

        if (
            not self.is_enabled
            or self.person_present
            or self.pc_locked
            or self.lock_timer_active
            or self.notification_shown
        ):
            return

        self.lock_timer_active = True
        self.timer_thread = threading.Thread(
            target=self._absence_timer_thread, daemon=True
        )
        self.timer_thread.start()

    def _absence_timer_thread(self):
        """Thread function for handling absence timer"""
        try:
            start_time = time.time()
            while (
                time.time() - start_time < self.person_absent_threshold
                and self.lock_timer_active
            ):

                self.check_windows_lock_status()

                if self.person_present or self.pc_locked:
                    if self.person_present:
                        self.logger.debug(
                            "Person detected during absence timer, cancelling"
                        )
                    else:
                        self.logger.info("PC locked externally, cancelling timer")
                    return

                time.sleep(0.1)

            if not self.lock_timer_active:
                return
            if self.person_present:
                return
            if self.pc_locked:
                return

            self.logger.info(
                f"Person absent for {self.person_absent_threshold}s, showing notification"
            )
            self.show_acknowledgment_notification()

            countdown_start = time.time()
            while (
                time.time() - countdown_start < self.lock_timeout
                and self.lock_timer_active
                and self.notification_shown
            ):
                remaining = self.lock_timeout - (time.time() - countdown_start)
                if self.countdown_callback:
                    self.countdown_callback(int(remaining))
                time.sleep(1.0)

            if self.lock_timer_active and self.notification_shown:
                self.logger.warning("No acknowledgment received, locking PC")
                self.lock_pc()

        except Exception as e:
            self.logger.error(f"Error in absence timer: {e}")
        finally:
            self.lock_timer_active = False
            self.close_notification()

    def show_acknowledgment_notification(self):
        """Show notification asking user to acknowledge presence"""
        if self.notification_window:
            return

        if self.testing_mode:
            self.notification_shown = True
            self.countdown_callback = lambda seconds: None
            return

        try:
            self.notification_window = tk.Toplevel()
            self.notification_window.title("Presence Check")
            self.notification_window.geometry("400x250")
            self.notification_window.resizable(False, False)

            self.notification_window.attributes("-topmost", True)
            self.notification_window.grab_set()

            self.notification_window.update_idletasks()
            x = (self.notification_window.winfo_screenwidth() // 2) - 200
            y = (self.notification_window.winfo_screenheight() // 2) - 125
            self.notification_window.geometry(f"+{x}+{y}")

            main_frame = ttk.Frame(self.notification_window, padding="20")
            main_frame.pack(fill=tk.BOTH, expand=True)

            title_frame = ttk.Frame(main_frame)
            title_frame.pack(fill=tk.X, pady=(0, 15))

            ttk.Label(title_frame, text="⚠️", font=("Arial", 24)).pack(side=tk.LEFT)
            ttk.Label(
                title_frame, text="Auto-Lock Warning", font=("Arial", 14, "bold")
            ).pack(side=tk.LEFT, padx=(10, 0))

            message = (
                "No person detected at the desk.\n\n"
                "Click 'I'm Here' if you're present.\n"
                "Otherwise, PC will be locked automatically."
            )
            ttk.Label(main_frame, text=message, justify=tk.CENTER, wraplength=350).pack(
                pady=(0, 20)
            )

            self.countdown_var = tk.StringVar()
            self.countdown_label = ttk.Label(
                main_frame,
                textvariable=self.countdown_var,
                font=("Arial", 12, "bold"),
                foreground="red",
            )
            self.countdown_label.pack(pady=(0, 20))

            button_frame = ttk.Frame(main_frame)
            button_frame.pack(fill=tk.X)

            ttk.Button(
                button_frame, text="I'm Here", command=self.acknowledge_presence
            ).pack(side=tk.LEFT, padx=(0, 10))
            ttk.Button(
                button_frame, text="Lock Now", command=self.lock_pc_immediate
            ).pack(side=tk.LEFT)
            ttk.Button(
                button_frame, text="Disable Auto-Lock", command=self.disable_autolock
            ).pack(side=tk.RIGHT)

            self.notification_shown = True

            self.countdown_callback = self.update_countdown_display

        except Exception as e:
            self.logger.error(f"Error showing notification: {e}")

    def update_countdown_display(self, seconds_remaining: int):
        """Update countdown display in notification"""
        try:
            if hasattr(self, "countdown_var") and self.countdown_var:
                self.countdown_var.set(f"Auto-lock in {seconds_remaining} seconds...")
        except Exception as e:
            self.logger.error(f"Error updating countdown: {e}")

    def acknowledge_presence(self):
        """User acknowledged they are present"""
        self.logger.info("User acknowledged presence")
        self.reset_timer()
        self.close_notification()

    def lock_pc_immediate(self):
        """Lock PC immediately upon user request"""
        self.logger.info("User requested immediate lock")
        self.lock_pc()

    def disable_autolock(self):
        """Disable auto-lock feature"""
        self.logger.info("Auto-lock disabled by user")
        self.set_enabled(False)
        self.close_notification()

    def close_notification(self):
        """Close the acknowledgment notification"""
        try:
            if self.notification_window:
                self.notification_window.destroy()
                self.notification_window = None
            self.notification_shown = False
            self.countdown_callback = None
        except Exception as e:
            self.logger.error(f"Error closing notification: {e}")

    def reset_timer(self):
        """Reset the absence timer"""
        was_active = self.lock_timer_active
        self.lock_timer_active = False
        self.close_notification()

        if was_active and self.timer_thread and self.timer_thread.is_alive():
            time.sleep(0.2)

    def lock_pc(self):
        """Lock the PC using Windows API"""
        try:
            self.logger.info("Locking PC...")
            self.pc_locked = True
            self.reset_timer()

            result = self.LockWorkStation()
            if result:
                self.logger.info("PC locked successfully")
            else:
                self.logger.warning("Failed to lock PC")
                self.simulate_win_l()

        except Exception as e:
            self.logger.error(f"Error locking PC: {e}")
            self.simulate_win_l()

    def simulate_win_l(self):
        """Simulate Windows+L key combination as fallback"""
        try:
            import subprocess

            subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], check=True)
            self.logger.info("PC locked using rundll32")
        except Exception as e:
            self.logger.error(f"Failed to lock PC with rundll32: {e}")

    def wake_screen(self):
        """Wake the screen when person returns"""
        try:
            current_pos = ctypes.wintypes.POINT()
            self.user32.GetCursorPos(ctypes.byref(current_pos))

            self.user32.SetCursorPos(current_pos.x + 1, current_pos.y)
            time.sleep(0.1)
            self.user32.SetCursorPos(current_pos.x, current_pos.y)

            VK_SPACE = 0x20
            self.user32.keybd_event(VK_SPACE, 0, 0, 0)
            self.user32.keybd_event(VK_SPACE, 0, 2, 0)

        except Exception as e:
            self.logger.error(f"Error waking screen: {e}")

    def wake_screen_mouse_only(self):
        """Wake screen using only mouse movement (no keyboard)"""
        try:
            current_pos = wintypes.POINT()
            self.user32.GetCursorPos(ctypes.byref(current_pos))

            self.user32.SetCursorPos(current_pos.x + 1, current_pos.y)
            time.sleep(0.05)
            self.user32.SetCursorPos(current_pos.x, current_pos.y)

        except Exception as e:
            self.logger.error(f"Error waking screen with mouse: {e}")

    def is_workstation_locked(self) -> bool:
        """Check if Windows workstation is currently locked"""
        try:
            hWnd = self.user32.GetForegroundWindow()

            hDesk = self.user32.OpenInputDesktop(0, False, 0x0100)
            if hDesk:
                self.user32.CloseDesktop(hDesk)
                return False
            else:
                return True

        except Exception as e:
            self.logger.error(f"Error checking workstation lock status: {e}")
            return False

    def check_windows_lock_status(self):
        """Check Windows lock status and update pc_locked flag accordingly"""
        try:
            windows_locked = self.is_workstation_locked()

            if windows_locked and not self.pc_locked:
                self.logger.info(
                    "Windows workstation detected as locked, updating status"
                )
                self.pc_locked = True
                if self.lock_timer_active:
                    self.reset_timer()

            elif not windows_locked and self.pc_locked:
                self.logger.info(
                    "Windows workstation detected as unlocked, resetting status"
                )
                self.pc_locked = False

        except Exception as e:
            self.logger.error(f"Error checking Windows lock status: {e}")

    def get_status(self) -> dict:
        """Get current status of the lock manager"""
        return {
            "enabled": self.is_enabled,
            "person_present": self.person_present,
            "last_detected": self.last_person_detected,
            "timer_active": self.lock_timer_active,
            "notification_shown": self.notification_shown,
            "pc_locked": self.pc_locked,
            "absent_threshold": self.person_absent_threshold,
            "lock_timeout": self.lock_timeout,
        }
