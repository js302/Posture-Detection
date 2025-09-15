import cv2
import threading
import time
from typing import Optional, Dict
import tkinter as tk
from tkinter import ttk, messagebox
import numpy as np
from PIL import Image, ImageTk

from camera_manager import PostureCameraManager
from posture_agent import PostureAgent
from posture_analyzer import PostureMetrics


class PostureMonitorGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Posture Monitor")
        self.root.geometry("1000x700")

        self.camera_manager = PostureCameraManager()
        self.agent = PostureAgent()

        self.is_monitoring = False
        self.video_label = None
        self.current_photo = None

        # Add frame update throttling
        self.last_frame_update = 0
        self.frame_update_interval = 100  # milliseconds
        self.pending_frame_update = False
        
        # Auto-lock status variable for settings window
        self.autolock_status_var = tk.StringVar()

        self.setup_ui()
        self.setup_callbacks()

    def setup_ui(self):
        """Setup the GUI components"""
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(1, weight=1)

        # Control panel
        control_frame = ttk.LabelFrame(main_frame, text="Controls", padding="10")
        control_frame.grid(
            row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10)
        )

        # Start/Stop button
        self.start_button = ttk.Button(
            control_frame, text="Start Monitoring", command=self.toggle_monitoring
        )
        self.start_button.pack(side=tk.LEFT, padx=(0, 10))

        # Status label
        self.status_label = ttk.Label(
            control_frame, text="Status: Stopped", foreground="red"
        )
        self.status_label.pack(side=tk.LEFT, padx=(0, 10))

        # Disable button
        self.disable_button = ttk.Button(
            control_frame, text="Disable for 30 min", command=self.disable_temporarily
        )
        self.disable_button.pack(side=tk.LEFT, padx=(0, 10))

        # Auto-lock toggle button
        self.autolock_button = ttk.Button(
            control_frame, text="Enable Auto-Lock", command=self.toggle_autolock
        )
        self.autolock_button.pack(side=tk.LEFT, padx=(0, 10))

        # Auto-lock status
        self.autolock_status_label = ttk.Label(
            control_frame, text="Auto-Lock: Disabled", foreground="gray"
        )
        self.autolock_status_label.pack(side=tk.LEFT, padx=(0, 10))

        # Video feed
        video_frame = ttk.LabelFrame(main_frame, text="Camera Feed", padding="10")
        video_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 10))

        self.video_label = ttk.Label(
            video_frame, text="Camera feed will appear here", anchor="center"
        )
        self.video_label.pack(expand=True, fill="both")

        # Info panel
        info_frame = ttk.LabelFrame(
            main_frame, text="Posture Information", padding="10"
        )
        info_frame.grid(row=1, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Current metrics
        metrics_frame = ttk.LabelFrame(info_frame, text="Current Metrics", padding="5")
        metrics_frame.pack(fill="x", pady=(0, 10))

        self.neck_tilt_var = tk.StringVar(value="Neck Tilt: -- °")
        self.head_pitch_var = tk.StringVar(value="Head Pitch: -- °")
        self.torso_lean_var = tk.StringVar(value="Torso Lean: -- °")
        self.shoulder_asym_var = tk.StringVar(value="Shoulder Asymmetry: -- px")

        ttk.Label(metrics_frame, textvariable=self.neck_tilt_var).pack(anchor="w")
        ttk.Label(metrics_frame, textvariable=self.head_pitch_var).pack(anchor="w")
        ttk.Label(metrics_frame, textvariable=self.torso_lean_var).pack(anchor="w")
        ttk.Label(metrics_frame, textvariable=self.shoulder_asym_var).pack(anchor="w")

        # Current status
        status_frame = ttk.LabelFrame(info_frame, text="Posture Status", padding="5")
        status_frame.pack(fill="x", pady=(0, 10))

        self.posture_status_var = tk.StringVar(value="Status: Good Posture")
        self.posture_status_label = ttk.Label(
            status_frame, textvariable=self.posture_status_var
        )
        self.posture_status_label.pack(anchor="w")

        self.violations_var = tk.StringVar(value="No violations detected")
        ttk.Label(
            status_frame, textvariable=self.violations_var, foreground="green"
        ).pack(anchor="w")

        # Session stats
        session_frame = ttk.LabelFrame(
            info_frame, text="Session Statistics", padding="5"
        )
        session_frame.pack(fill="x", pady=(0, 10))

        self.session_duration_var = tk.StringVar(value="Session Duration: 0:00:00")
        self.bad_posture_time_var = tk.StringVar(value="Bad Posture Time: 0:00:00")
        self.warnings_count_var = tk.StringVar(value="Warnings: 0")

        ttk.Label(session_frame, textvariable=self.session_duration_var).pack(
            anchor="w"
        )
        ttk.Label(session_frame, textvariable=self.bad_posture_time_var).pack(
            anchor="w"
        )
        ttk.Label(session_frame, textvariable=self.warnings_count_var).pack(anchor="w")

        # Action buttons
        action_frame = ttk.LabelFrame(info_frame, text="Actions", padding="5")
        action_frame.pack(fill="x")

        ttk.Button(
            action_frame, text="View Daily Summary", command=self.show_daily_summary
        ).pack(fill="x", pady=(0, 5))
        ttk.Button(action_frame, text="Export Data", command=self.export_data).pack(
            fill="x", pady=(0, 5)
        )
        ttk.Button(action_frame, text="Settings", command=self.show_settings).pack(
            fill="x"
        )

    def setup_callbacks(self):
        """Setup camera and agent callbacks"""
        self.camera_manager.set_frame_callback(self.update_video_feed)
        self.camera_manager.set_posture_callback(self.update_posture_info)
        self.camera_manager.set_person_detection_callback(self.agent.update_person_presence)

    def toggle_monitoring(self):
        """Start or stop posture monitoring"""
        if not self.is_monitoring:
            # Check power status before starting to avoid unnecessary loading
            if not self.agent.should_be_active():
                if self.agent.require_ac_power and not self.agent.check_power_status():
                    messagebox.showwarning(
                        "Power Required",
                        "AC power is required for monitoring. Please connect your charger.",
                    )
                    return
                elif not (
                    self.agent.work_hours[0]
                    <= time.localtime().tm_hour
                    <= self.agent.work_hours[1]
                ):
                    messagebox.showinfo(
                        "Outside Work Hours",
                        f"Monitoring is only active during work hours ({self.agent.work_hours[0]}:00 - {self.agent.work_hours[1]}:00)",
                    )
                    return
                else:
                    messagebox.showinfo(
                        "Monitoring Disabled",
                        "Monitoring is temporarily disabled or outside configured conditions.",
                    )
                    return

            if self.camera_manager.start():
                self.is_monitoring = True
                self.start_button.config(text="Stop Monitoring")
                self.status_label.config(text="Status: Running", foreground="green")
                self.start_update_timer()
            else:
                messagebox.showerror("Error", "Failed to start camera or load models")
        else:
            self.camera_manager.stop()

            # Try to end session, but don't let exceptions prevent GUI state update
            try:
                self.agent.end_session()
            except Exception as e:
                print(f"Error ending session: {e}")

            self.is_monitoring = False
            self.start_button.config(text="Start Monitoring")
            self.status_label.config(text="Status: Stopped", foreground="red")

            # Reset session stats display when stopped
            self.session_duration_var.set("Session Duration: 0:00:00")
            self.bad_posture_time_var.set("Bad Posture Time: 0:00:00")
            self.warnings_count_var.set("Warnings: 0")

    def toggle_autolock(self):
        """Toggle auto-lock functionality"""
        current_enabled = self.agent.auto_lock_enabled
        self.agent.set_auto_lock_enabled(not current_enabled)
        self.update_autolock_ui()
        
        if self.agent.auto_lock_enabled:
            messagebox.showinfo(
                "Auto-Lock Enabled", 
                f"Auto-lock is now enabled.\n\n"
                f"• PC will lock if no person detected for {self.agent.person_absent_threshold}s\n"
                f"• You'll have {self.agent.lock_timeout}s to acknowledge your presence\n"
                f"• Configure timers in Settings"
            )
        else:
            messagebox.showinfo("Auto-Lock Disabled", "Auto-lock functionality is now disabled.")

    def update_autolock_ui(self):
        """Update auto-lock UI elements"""
        if self.agent.auto_lock_enabled:
            self.autolock_button.config(text="Disable Auto-Lock")
            self.autolock_status_label.config(text="Auto-Lock: Enabled", foreground="green")
        else:
            self.autolock_button.config(text="Enable Auto-Lock")
            self.autolock_status_label.config(text="Auto-Lock: Disabled", foreground="gray")

    def disable_temporarily(self):
        """Temporarily disable monitoring"""
        if self.is_monitoring:
            self.agent.manually_disable(30)
            messagebox.showinfo(
                "Disabled", "Posture monitoring disabled for 30 minutes"
            )

    def update_video_feed(self, frame: np.ndarray):
        """Update video feed in GUI with throttling to reduce flickering"""
        current_time = time.time() * 1000  # Convert to milliseconds

        # Throttle updates to reduce flickering
        if current_time - self.last_frame_update < self.frame_update_interval:
            return

        try:
            # Resize frame for display
            height, width = frame.shape[:2]
            target_width = 480
            target_height = int(height * target_width / width)

            resized_frame = cv2.resize(frame, (target_width, target_height))

            # Convert to PIL Image
            rgb_frame = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(rgb_frame)

            photo = ImageTk.PhotoImage(pil_image)

            # Schedule update in main thread
            self.root.after_idle(self._update_video_label, photo)
            self.last_frame_update = current_time

        except Exception as e:
            print(f"Error updating video feed: {e}")

    def _update_video_label(self, photo):
        """Update video label in main thread"""
        try:
            if self.video_label and photo:
                self.current_photo = (
                    photo  # Keep reference to prevent garbage collection
                )
                self.video_label.config(image=photo, text="")
        except Exception as e:
            print(f"Error in video label update: {e}")

    def update_posture_info(self, metrics: PostureMetrics, violations: Dict[str, bool]):
        """Update posture information display"""
        try:
            # Schedule update in main thread to avoid threading issues
            self.root.after_idle(self._update_posture_info_safe, metrics, violations)
        except Exception as e:
            print(f"Error scheduling posture info update: {e}")

    def _update_posture_info_safe(
        self, metrics: PostureMetrics, violations: Dict[str, bool]
    ):
        """Safely update posture information in main thread"""
        try:
            # Update metrics
            self.neck_tilt_var.set(f"Neck Tilt: {metrics.neck_tilt_angle:.1f}°")
            self.head_pitch_var.set(f"Head Pitch: {metrics.head_pitch:.1f}°")
            self.torso_lean_var.set(f"Torso Lean: {metrics.torso_lean:.1f}°")
            self.shoulder_asym_var.set(
                f"Shoulder Asymmetry: {metrics.shoulder_asymmetry:.1f}px"
            )

            # Update status
            if any(violations.values()):
                self.posture_status_var.set("Status: Poor Posture Detected")
                violation_list = [
                    k.replace("_", " ").title() for k, v in violations.items() if v
                ]
                self.violations_var.set(f"Issues: {', '.join(violation_list)}")
            else:
                self.posture_status_var.set("Status: Good Posture")
                self.violations_var.set("No violations detected")

            # Process through agent (do this in background to avoid blocking GUI)
            threading.Thread(
                target=self._process_agent_update,
                args=(metrics, violations),
                daemon=True,
            ).start()

        except Exception as e:
            print(f"Error updating posture info: {e}")

    def _process_agent_update(
        self, metrics: PostureMetrics, violations: Dict[str, bool]
    ):
        """Process agent update in background thread"""
        try:
            notification = self.agent.process_posture_update(metrics, violations)
            if notification:
                # Schedule notification in main thread
                self.root.after_idle(self.show_notification, notification)
        except Exception as e:
            print(f"Error processing agent update: {e}")

    def start_update_timer(self):
        """Start timer for updating session statistics"""
        if self.is_monitoring:
            self.update_session_stats()
            self.update_autolock_ui()  # Update auto-lock UI periodically
            self.root.after(1000, self.start_update_timer)  # Update every second

    def update_session_stats(self):
        """Update session statistics display"""
        # Safety check - if monitoring stopped, don't continue
        if not self.is_monitoring:
            return

        # Check power status and stop if unpowered
        if self.is_monitoring and self.agent.force_stop_if_unpowered():
            self.toggle_monitoring()  # This will stop monitoring
            messagebox.showwarning(
                "Power Disconnected",
                "AC power disconnected. Monitoring stopped as per settings.",
            )
            return

        if self.agent.current_session:
            current_time = time.time()
            duration = current_time - self.agent.current_session.start_time

            hours = int(duration // 3600)
            minutes = int((duration % 3600) // 60)
            seconds = int(duration % 60)

            self.session_duration_var.set(
                f"Session Duration: {hours:02d}:{minutes:02d}:{seconds:02d}"
            )

            bad_duration = self.agent.bad_posture_accumulator
            if self.agent.current_state.value == "bad":
                bad_duration += current_time - self.agent.last_state_change

            bad_hours = int(bad_duration // 3600)
            bad_minutes = int((bad_duration % 3600) // 60)
            bad_seconds = int(bad_duration % 60)

            self.bad_posture_time_var.set(
                f"Bad Posture Time: {bad_hours:02d}:{bad_minutes:02d}:{bad_seconds:02d}"
            )
            self.warnings_count_var.set(
                f"Warnings: {self.agent.current_session.total_warnings}"
            )

    def show_notification(self, message: str):
        """Show posture notification"""
        # Create a temporary notification window
        notification = tk.Toplevel(self.root)
        notification.title("Posture Alert")
        notification.geometry("400x200")
        notification.grab_set()  # Make it modal

        # Center the notification
        notification.transient(self.root)
        notification.geometry(
            "+%d+%d" % (self.root.winfo_rootx() + 50, self.root.winfo_rooty() + 50)
        )

        # Content
        ttk.Label(
            notification, text="⚠ Posture Alert", font=("Arial", 14, "bold")
        ).pack(pady=10)

        message_label = ttk.Label(notification, text=message, wraplength=350)
        message_label.pack(pady=10)

        # Buttons
        button_frame = ttk.Frame(notification)
        button_frame.pack(pady=10)

        ttk.Button(
            button_frame,
            text="Got it!",
            command=lambda: self.close_notification(notification, True),
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            button_frame,
            text="Not helpful",
            command=lambda: self.close_notification(notification, False),
        ).pack(side=tk.LEFT, padx=5)

        # Auto-close after 10 seconds
        notification.after(10000, lambda: self.close_notification(notification, None))

    def close_notification(self, notification: tk.Toplevel, helpful: Optional[bool]):
        """Close notification and record feedback"""
        if helpful is not None:
            self.agent.record_feedback("posture_alert", helpful)

        try:
            notification.destroy()
        except:
            pass

    def show_daily_summary(self):
        """Show daily posture summary"""
        summary = self.agent.get_daily_summary()

        summary_window = tk.Toplevel(self.root)
        summary_window.title("Daily Summary")
        summary_window.geometry("400x300")

        content = f"""
Daily Posture Summary - {summary['date']}

Work Sessions: {summary['session_count']}
Total Work Time: {summary['total_work_time']/3600:.1f} hours
Bad Posture Time: {summary['total_bad_duration']/60:.1f} minutes
Total Warnings: {summary['total_warnings']}
Posture Score: {summary['posture_score']:.1f}%

{'Excellent posture today!' if summary['posture_score'] > 90 else 
 'Good posture overall' if summary['posture_score'] > 75 else
 'Room for improvement in posture'}
        """

        ttk.Label(summary_window, text=content, justify="left").pack(pady=20)
        ttk.Button(summary_window, text="Close", command=summary_window.destroy).pack(
            pady=10
        )

    def export_data(self):
        """Export posture data"""
        try:
            data = self.agent.export_session_data(days=7)

            import os

            data_dir = os.path.join(os.path.dirname(__file__), "data")
            os.makedirs(data_dir, exist_ok=True)

            filename = os.path.join(data_dir, f"posture_data_{int(time.time())}.json")

            import json

            with open(filename, "w") as f:
                json.dump(data, f, indent=2, default=str)

            messagebox.showinfo("Export Complete", f"Data exported to {filename}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export data: {e}")

    def show_settings(self):
        """Show settings window"""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Settings")
        settings_window.geometry("500x500")
        settings_window.resizable(False, False)

        # Create notebook for tabbed settings
        notebook = ttk.Notebook(settings_window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # General settings tab
        general_frame = ttk.Frame(notebook)
        notebook.add(general_frame, text="General")

        ttk.Label(general_frame, text="General Settings", font=("Arial", 14, "bold")).pack(
            pady=(10, 20)
        )

        # Work hours setting
        hours_frame = ttk.Frame(general_frame)
        hours_frame.pack(pady=10, fill=tk.X, padx=20)

        ttk.Label(hours_frame, text="Work Hours:").pack(anchor=tk.W)

        hours_input_frame = ttk.Frame(hours_frame)
        hours_input_frame.pack(anchor=tk.W, pady=(5, 0))

        start_hour = tk.IntVar(value=self.agent.work_hours[0])
        end_hour = tk.IntVar(value=self.agent.work_hours[1])

        ttk.Label(hours_input_frame, text="From:").pack(side=tk.LEFT)
        start_spinbox = ttk.Spinbox(
            hours_input_frame, from_=0, to=23, textvariable=start_hour, width=5
        )
        start_spinbox.pack(side=tk.LEFT, padx=(5, 10))

        ttk.Label(hours_input_frame, text="To:").pack(side=tk.LEFT)
        end_spinbox = ttk.Spinbox(
            hours_input_frame, from_=0, to=23, textvariable=end_hour, width=5
        )
        end_spinbox.pack(side=tk.LEFT, padx=5)

        # AC power requirement
        ac_power_var = tk.BooleanVar(value=self.agent.require_ac_power)
        ttk.Checkbutton(
            general_frame, text="Require AC Power for monitoring", variable=ac_power_var
        ).pack(pady=10, anchor=tk.W, padx=20)

        # Auto-lock settings tab
        autolock_frame = ttk.Frame(notebook)
        notebook.add(autolock_frame, text="Auto-Lock")

        ttk.Label(autolock_frame, text="Auto-Lock Settings", font=("Arial", 14, "bold")).pack(
            pady=(10, 20)
        )

        # Enable auto-lock
        auto_lock_var = tk.BooleanVar(value=self.agent.auto_lock_enabled)
        auto_lock_checkbox = ttk.Checkbutton(
            autolock_frame, 
            text="Enable automatic PC locking when person leaves desk", 
            variable=auto_lock_var
        )
        auto_lock_checkbox.pack(pady=10, anchor=tk.W, padx=20)

        # Person absent threshold
        absent_frame = ttk.Frame(autolock_frame)
        absent_frame.pack(pady=10, fill=tk.X, padx=20)

        ttk.Label(absent_frame, text="Person absence detection threshold:").pack(anchor=tk.W)
        
        absent_input_frame = ttk.Frame(absent_frame)
        absent_input_frame.pack(anchor=tk.W, pady=(5, 0))

        absent_threshold = tk.DoubleVar(value=self.agent.person_absent_threshold)
        absent_spinbox = ttk.Spinbox(
            absent_input_frame, 
            from_=1.0, 
            to=300.0, 
            increment=1.0,
            textvariable=absent_threshold, 
            width=8
        )
        absent_spinbox.pack(side=tk.LEFT)
        ttk.Label(absent_input_frame, text="seconds").pack(side=tk.LEFT, padx=(5, 0))

        # Lock timeout
        timeout_frame = ttk.Frame(autolock_frame)
        timeout_frame.pack(pady=10, fill=tk.X, padx=20)

        ttk.Label(timeout_frame, text="Acknowledgment timeout (before auto-lock):").pack(anchor=tk.W)
        
        timeout_input_frame = ttk.Frame(timeout_frame)
        timeout_input_frame.pack(anchor=tk.W, pady=(5, 0))

        lock_timeout = tk.DoubleVar(value=self.agent.lock_timeout)
        timeout_spinbox = ttk.Spinbox(
            timeout_input_frame, 
            from_=5.0, 
            to=300.0, 
            increment=5.0,
            textvariable=lock_timeout, 
            width=8
        )
        timeout_spinbox.pack(side=tk.LEFT)
        ttk.Label(timeout_input_frame, text="seconds").pack(side=tk.LEFT, padx=(5, 0))

        # Auto-lock status display
        status_frame = ttk.LabelFrame(autolock_frame, text="Current Status", padding=10)
        status_frame.pack(pady=(20, 10), fill=tk.X, padx=20)

        self.autolock_status_var = tk.StringVar()
        ttk.Label(status_frame, textvariable=self.autolock_status_var, justify=tk.LEFT).pack(anchor=tk.W)
        
        # Update status initially
        self.update_autolock_status_display()

        # Save button
        button_frame = ttk.Frame(settings_window)
        button_frame.pack(pady=20)

        def save_settings():
            self.agent.work_hours = (start_hour.get(), end_hour.get())
            self.agent.require_ac_power = ac_power_var.get()
            
            # Auto-lock settings
            self.agent.set_auto_lock_enabled(auto_lock_var.get())
            self.agent.set_person_absent_threshold(absent_threshold.get())
            self.agent.set_lock_timeout(lock_timeout.get())
            
            messagebox.showinfo("Settings", "Settings saved successfully!")
            settings_window.destroy()

        def update_status():
            self.update_autolock_status_display()
            settings_window.after(2000, update_status)  # Update every 2 seconds

        update_status()  # Start status updates

        ttk.Button(button_frame, text="Save Settings", command=save_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=settings_window.destroy).pack(side=tk.LEFT, padx=5)

    def update_autolock_status_display(self):
        """Update the auto-lock status display"""
        try:
            status = self.agent.get_auto_lock_status()
            status_text = f"Auto-lock: {'Enabled' if status['enabled'] else 'Disabled'}\n"
            status_text += f"Person present: {'Yes' if status['person_present'] else 'No'}\n"
            if status['timer_active']:
                status_text += "⚠️ Absence timer active\n"
            if status['notification_shown']:
                status_text += "🔔 Notification shown\n"
            
            self.autolock_status_var.set(status_text)
        except Exception as e:
            self.autolock_status_var.set(f"Status update error: {e}")

    def show_settings_old(self):
        """Show old simple settings window (kept for reference)"""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Settings")
        settings_window.geometry("400x300")

        ttk.Label(settings_window, text="Settings", font=("Arial", 14, "bold")).pack(
            pady=10
        )

        # Work hours setting
        hours_frame = ttk.Frame(settings_window)
        hours_frame.pack(pady=10)

        ttk.Label(hours_frame, text="Work Hours:").pack(side=tk.LEFT)

        start_hour = tk.IntVar(value=self.agent.work_hours[0])
        end_hour = tk.IntVar(value=self.agent.work_hours[1])

        start_spinbox = ttk.Spinbox(
            hours_frame, from_=0, to=23, textvariable=start_hour, width=5
        )
        start_spinbox.pack(side=tk.LEFT, padx=5)

        ttk.Label(hours_frame, text="to").pack(side=tk.LEFT)

        end_spinbox = ttk.Spinbox(
            hours_frame, from_=0, to=23, textvariable=end_hour, width=5
        )
        end_spinbox.pack(side=tk.LEFT, padx=5)

        # AC power requirement
        ac_power_var = tk.BooleanVar(value=self.agent.require_ac_power)
        ttk.Checkbutton(
            settings_window, text="Require AC Power", variable=ac_power_var
        ).pack(pady=10)

        # Save button
        def save_settings():
            self.agent.work_hours = (start_hour.get(), end_hour.get())
            self.agent.require_ac_power = ac_power_var.get()
            messagebox.showinfo("Settings", "Settings saved successfully!")
            settings_window.destroy()

        ttk.Button(settings_window, text="Save", command=save_settings).pack(pady=20)

    def run(self):
        """Run the GUI application"""
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.mainloop()

    def on_closing(self):
        """Handle application closing"""
        if self.is_monitoring:
            self.camera_manager.stop()
            self.agent.end_session()

        self.root.destroy()


if __name__ == "__main__":
    app = PostureMonitorGUI()
    app.run()
