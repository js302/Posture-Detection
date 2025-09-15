import time
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional
import ctypes
from ctypes import wintypes
import os


class PCLockManager:
    """Manages automatic PC locking based on user presence detection"""
    
    def __init__(self):
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
        
        # Windows API constants
        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32
        
        # Lock workstation API
        self.LockWorkStation = self.user32.LockWorkStation
        
    def set_enabled(self, enabled: bool):
        """Enable or disable auto-lock functionality"""
        self.is_enabled = enabled
        if not enabled:
            self.reset_timer()
            
    def set_person_absent_threshold(self, seconds: float):
        """Set threshold for person absence detection"""
        self.person_absent_threshold = max(1.0, seconds)
        
    def set_lock_timeout(self, seconds: float):
        """Set timeout for user acknowledgment"""
        self.lock_timeout = max(5.0, seconds)
        
    def update_person_presence(self, person_detected: bool):
        """Update person presence status"""
        current_time = time.time()
        
        if person_detected:
            if not self.person_present:
                print(f"Person returned to desk at {time.strftime('%H:%M:%S')}")
                self.wake_screen()
                
            self.person_present = True
            self.last_person_detected = current_time
            self.reset_timer()
        else:
            self.person_present = False
            
        # Start absence timer if enabled and person just became absent
        if (self.is_enabled and not person_detected and 
            not self.lock_timer_active and not self.notification_shown):
            self.start_absence_timer()
            
    def start_absence_timer(self):
        """Start timer for person absence detection"""
        if self.timer_thread and self.timer_thread.is_alive():
            return
            
        self.lock_timer_active = True
        self.timer_thread = threading.Thread(target=self._absence_timer_thread, daemon=True)
        self.timer_thread.start()
        
    def _absence_timer_thread(self):
        """Thread function for handling absence timer"""
        try:
            # Wait for absence threshold
            start_time = time.time()
            while (time.time() - start_time < self.person_absent_threshold and 
                   self.lock_timer_active and not self.person_present):
                time.sleep(0.5)
                
            # Check if person is still absent and timer is still active
            if not self.lock_timer_active or self.person_present:
                return
                
            print(f"Person absent for {self.person_absent_threshold}s, showing notification")
            self.show_acknowledgment_notification()
            
            # Wait for acknowledgment or timeout
            countdown_start = time.time()
            while (time.time() - countdown_start < self.lock_timeout and 
                   self.lock_timer_active and self.notification_shown):
                remaining = self.lock_timeout - (time.time() - countdown_start)
                if self.countdown_callback:
                    self.countdown_callback(int(remaining))
                time.sleep(1.0)
                
            # Lock PC if timer expired and no acknowledgment
            if self.lock_timer_active and self.notification_shown:
                print("No acknowledgment received, locking PC")
                self.lock_pc()
                
        except Exception as e:
            print(f"Error in absence timer: {e}")
        finally:
            self.lock_timer_active = False
            self.close_notification()
            
    def show_acknowledgment_notification(self):
        """Show notification asking user to acknowledge presence"""
        if self.notification_window:
            return
            
        try:
            # Create notification window
            self.notification_window = tk.Toplevel()
            self.notification_window.title("Presence Check")
            self.notification_window.geometry("400x250")
            self.notification_window.resizable(False, False)
            
            # Make it always on top and grab focus
            self.notification_window.attributes('-topmost', True)
            self.notification_window.grab_set()
            
            # Center on screen
            self.notification_window.update_idletasks()
            x = (self.notification_window.winfo_screenwidth() // 2) - 200
            y = (self.notification_window.winfo_screenheight() // 2) - 125
            self.notification_window.geometry(f"+{x}+{y}")
            
            # Content
            main_frame = ttk.Frame(self.notification_window, padding="20")
            main_frame.pack(fill=tk.BOTH, expand=True)
            
            # Warning icon and title
            title_frame = ttk.Frame(main_frame)
            title_frame.pack(fill=tk.X, pady=(0, 15))
            
            ttk.Label(title_frame, text="⚠️", font=("Arial", 24)).pack(side=tk.LEFT)
            ttk.Label(title_frame, text="Auto-Lock Warning", 
                     font=("Arial", 14, "bold")).pack(side=tk.LEFT, padx=(10, 0))
            
            # Message
            message = ("No person detected at the desk.\n\n"
                      "Click 'I'm Here' if you're present.\n"
                      "Otherwise, PC will be locked automatically.")
            ttk.Label(main_frame, text=message, justify=tk.CENTER, 
                     wraplength=350).pack(pady=(0, 20))
            
            # Countdown display
            self.countdown_var = tk.StringVar()
            self.countdown_label = ttk.Label(main_frame, textvariable=self.countdown_var,
                                           font=("Arial", 12, "bold"),
                                           foreground="red")
            self.countdown_label.pack(pady=(0, 20))
            
            # Buttons
            button_frame = ttk.Frame(main_frame)
            button_frame.pack(fill=tk.X)
            
            ttk.Button(button_frame, text="I'm Here", 
                      command=self.acknowledge_presence).pack(side=tk.LEFT, padx=(0, 10))
            ttk.Button(button_frame, text="Lock Now", 
                      command=self.lock_pc_immediate).pack(side=tk.LEFT)
            ttk.Button(button_frame, text="Disable Auto-Lock", 
                      command=self.disable_autolock).pack(side=tk.RIGHT)
                      
            self.notification_shown = True
            
            # Set countdown callback
            self.countdown_callback = self.update_countdown_display
            
        except Exception as e:
            print(f"Error showing notification: {e}")
            
    def update_countdown_display(self, seconds_remaining: int):
        """Update countdown display in notification"""
        try:
            if hasattr(self, 'countdown_var') and self.countdown_var:
                self.countdown_var.set(f"Auto-lock in {seconds_remaining} seconds...")
        except Exception as e:
            print(f"Error updating countdown: {e}")
            
    def acknowledge_presence(self):
        """User acknowledged they are present"""
        print("User acknowledged presence")
        self.reset_timer()
        self.close_notification()
        
    def lock_pc_immediate(self):
        """Lock PC immediately upon user request"""
        print("User requested immediate lock")
        self.lock_pc()
        
    def disable_autolock(self):
        """Disable auto-lock feature"""
        print("Auto-lock disabled by user")
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
            print(f"Error closing notification: {e}")
            
    def reset_timer(self):
        """Reset the absence timer"""
        self.lock_timer_active = False
        self.close_notification()
        
    def lock_pc(self):
        """Lock the PC using Windows API"""
        try:
            print("Locking PC...")
            # Reset timer state
            self.reset_timer()
            
            # Lock workstation
            result = self.LockWorkStation()
            if result:
                print("PC locked successfully")
            else:
                print("Failed to lock PC")
                # Fallback: simulate Win+L
                self.simulate_win_l()
                
        except Exception as e:
            print(f"Error locking PC: {e}")
            # Fallback to Win+L simulation
            self.simulate_win_l()
            
    def simulate_win_l(self):
        """Simulate Windows+L key combination as fallback"""
        try:
            import subprocess
            subprocess.run(['rundll32.exe', 'user32.dll,LockWorkStation'], check=True)
            print("PC locked using rundll32")
        except Exception as e:
            print(f"Failed to lock PC with rundll32: {e}")
            
    def wake_screen(self):
        """Wake the screen when person returns"""
        try:
            # Move mouse slightly to wake screen
            current_pos = ctypes.wintypes.POINT()
            self.user32.GetCursorPos(ctypes.byref(current_pos))
            
            # Move mouse and return to original position
            self.user32.SetCursorPos(current_pos.x + 1, current_pos.y)
            time.sleep(0.1)
            self.user32.SetCursorPos(current_pos.x, current_pos.y)
            
            # Send a key press to wake screen (Space key)
            VK_SPACE = 0x20
            self.user32.keybd_event(VK_SPACE, 0, 0, 0)  # Key down
            self.user32.keybd_event(VK_SPACE, 0, 2, 0)  # Key up
            
            print("Screen wake signal sent")
            
        except Exception as e:
            print(f"Error waking screen: {e}")
            
    def get_status(self) -> dict:
        """Get current status of the lock manager"""
        return {
            'enabled': self.is_enabled,
            'person_present': self.person_present,
            'last_detected': self.last_person_detected,
            'timer_active': self.lock_timer_active,
            'notification_shown': self.notification_shown,
            'absent_threshold': self.person_absent_threshold,
            'lock_timeout': self.lock_timeout
        }