# Posture Detection System

Ever notice how your neck starts aching after a long day at the computer? This real-time posture monitoring system was built to help catch those slouching habits before they become a problem. Using MediaPipe's pose estimation, it keeps an eye on your posture throughout the workday and gives you gentle reminders when it's time to sit up straight.

## What It Does

- **Watches Your Posture**: Uses your webcam and MediaPipe to track how you're sitting in real-time
- **Tracks Key Metrics**: Monitors neck tilt, head position, torso lean, and shoulder alignment
- **Smart Notifications**: Only alerts you after you've been in poor posture for a while (no annoying false alarms)
- **Auto-Lock Security**: Automatically locks your PC when you step away from your desk and wakes it when you return
- **Respects Your Schedule**: Automatically runs during work hours and stops when you're on battery power
- **Keeps Records**: Saves your posture data so you can see trends and improvements over time
- **Learns From You**: Adapts based on whether you find the alerts helpful or not

## How It Works

The system has four main parts working together:

1. **PostureAnalyzer**: Does the math to figure out your posture angles from camera data
2. **CameraManager**: Handles the webcam feed and runs pose detection
3. **PostureAgent**: Decides when to alert you and keeps track of your session data
4. **GUI Application**: The simple interface you interact with
5. **Auto-Lock Manager**: Monitors when you're away and handles PC security automatically

### The Auto-Lock Feature

One of the coolest additions is the automatic PC locking when you leave your desk. Here's how it works:

**When you step away:**
- The system notices no one is at the desk after about 10 seconds
- A friendly notification pops up asking "Are you still there?"
- You get 30 seconds to click "I'm Here" if you're just leaning back or grabbing something
- If there's no response, your PC locks automatically for security

**When you come back:**
- The camera detects you're back at your desk
- Your screen wakes up automatically
- The password screen appears so you can log right back in

It's like having a helpful assistant that locks up when you forget to, but is smart enough not to lock you out when you're just stretching or thinking.

### What Gets Measured

Based on the actual implementation, here's what the system tracks:

| Measurement        | Alert Threshold | What It Means                      |
| ------------------ | --------------- | ---------------------------------- |
| Neck Tilt          | >20°            | Head tilted too far forward        |
| Head Pitch         | >30°            | Looking down at screen too much    |
| Torso Lean         | >15°            | Leaning forward or slouching       |
| Shoulder Asymmetry | >8 pixels       | One shoulder higher than the other |

The system waits 3 seconds before considering posture "bad" to avoid false alarms from normal movement.

## Getting Started

### What You'll Need

First, it's a good idea to create a virtual environment to keep things tidy:

```bash
# Create a virtual environment
python -m venv .posture

# Activate it (Windows)
.posture\Scripts\activate

# Activate it (macOS/Linux)
source .posture/bin/activate
```

Then install the required packages:

```bash
pip install -r requirements.txt
```

The main dependencies are:

- `opencv-python` - for camera handling
- `numpy` - for the math behind posture calculations
- `pillow` and `tkinter` - for the GUI
- `psutil` - to check if you're on battery power
- MediaPipe models (should be included with the QAI Hub setup)

### Running the App

Simply run:

```bash
python main_gui.py
```

The interface will open showing your camera feed and current posture metrics. Click "Start Monitoring" to begin tracking your posture.

### Setting Up Auto-Lock (Optional)

Want your computer to lock automatically when you step away? Here's how to set it up:

1. **Enable the feature**: Click the "Enable Auto-Lock" button in the main interface
2. **Customize the timing**: Go to Settings → Auto-Lock tab to adjust:
   - How long before it notices you're gone (default: 10 seconds)
   - How long you have to respond before it locks (default: 30 seconds)
3. **Test it out**: Try stepping away from your desk to see how it works

The feature is disabled by default since everyone's workspace is different. Some people share computers, others have privacy concerns, and some work in open offices where the camera might pick up other people walking by.

## Customizing the Settings

### Work Hours

By default, the system only runs from 9 AM to 11 PM (I work late sometimes!). You can change this in the GUI settings. The auto-lock feature respects these hours too - no point locking your computer at 2 AM when you're probably not at your desk anyway.

### Auto-Lock Preferences

Everyone's work style is different, so the auto-lock feature is fully customizable:

- **Detection sensitivity**: How long before it thinks you've left (1-300 seconds)
- **Response time**: How long you get to say "I'm still here" (5-300 seconds)  
- **Quick disable**: Toggle the whole feature on/off with one click

Pro tip: If you work in an open office or have pets that walk by the camera, you might want longer detection times to avoid false alarms.

### Alert Sensitivity

If you find the alerts too sensitive or not sensitive enough, you can adjust the thresholds in `posture_analyzer.py`. The current settings are:

```python
class PostureThresholds:
    neck_tilt_threshold: float = 20.0          # degrees
    head_pitch_threshold: float = 30.0         # degrees
    torso_lean_threshold: float = 15.0         # degrees
    shoulder_asymmetry_threshold: float = 8.0  # pixels
    bad_posture_duration_threshold: float = 3.0 # seconds
```

### Warning Schedule

The system gets more insistent over time:

- **15 seconds**: Gentle reminder to check your posture
- **45 seconds**: More direct suggestion to adjust
- **2 minutes**: Strong recommendation to take a break

## Your Data

Everything gets saved to a local SQLite database in the `data/` folder. The system tracks:

- **Work Sessions**: When you worked, how long, and overall posture quality
- **Posture Events**: Every time your posture changed from good to bad or vice versa
- **Feedback**: Whether you found alerts helpful (this helps the system learn)

You can export your data as JSON through the GUI if you want to analyze it elsewhere.

## When It Runs

The system is designed to be smart about when it's actually helpful:

- **Only during work hours** (configurable)
- **Only when plugged in** (assumes you're at a desk, not on the couch)
- **Stops if you manually disable it** (for those video calls where you need to lean in)
- **Requires camera access** (obviously!)

## Making It Your Own

### Adding New Measurements

Want to track something else? Add a new calculation method to the `PostureAnalyzer` class:

```python
def calculate_my_custom_metric(self, keypoints: np.ndarray) -> float:
    # Your calculation here
    return some_measurement
```

### Different Alert Messages

The alert messages are generated in `PostureAgent.generate_warning_message()`. Feel free to make them more encouraging, stern, or funny - whatever works for you!

### Machine Learning Potential

The system logs detailed data that could be used to train personalized models:

- Replace the rule-based detection with learned patterns
- Use the feedback data to adapt to your preferences
- Train on your specific work setup and habits

## Technical Details

For those interested in the implementation:

- **Performance**: Runs at 15-30 FPS depending on your hardware
- **Latency**: Under 100ms from camera capture to posture analysis
- **Memory Usage**: Around 500MB with all models loaded
- **Storage**: About 1MB of data per 8-hour work session

## Troubleshooting

**Camera not working?**

- Check that no other app is using your webcam
- Try changing the camera ID in the code (usually 0 for built-in cameras)
- Make sure you granted camera permissions

**Auto-lock acting weird?**

- Make sure you're the only person the camera can see (it might detect others walking by)
- Try adjusting the detection sensitivity in settings
- Check that Windows allows the app to lock the computer (some corporate policies block this)
- If it's not waking your screen when you return, check your display power settings

**Poor performance?**

- Close other heavy applications
- Try lowering the FPS in the camera manager
- Reduce video resolution if needed

**Models not loading?**

- Verify the MediaPipe models are in the right location
- Check that you have enough RAM available
- Make sure PyTorch is properly installed

## Future Ideas

Some features I'm thinking about adding:

- **AI Coaching**: Use an LLM to give personalized posture advice
- **Calendar Integration**: Automatic break reminders based on your schedule
- **Mobile Notifications**: Get alerts on your phone when away from desk
- **Smart Home Integration**: Dim lights or adjust desk height based on posture data
- **Team Dashboard**: Workplace posture analytics (anonymized, of course)
- **Wearable Support**: Integrate with fitness trackers for more complete data
- **Machine Learning**: Learn your specific patterns to reduce false alarms

The auto-lock feature could also get smarter - maybe learning your daily routine or integrating with your calendar to know when you're in meetings vs. just stepped away for coffee.

## Contributing

This started as a personal project because I was tired of neck pain from long coding sessions. If you have ideas for improvements or find bugs, feel free to contribute!

## License

BSD-3-Clause (same as the QAI Hub Models this builds on)
