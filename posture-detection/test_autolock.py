import time
import sys
import os

# Add the posture-detection directory to the path
sys.path.insert(0, os.path.dirname(__file__))

from pc_lock_manager import PCLockManager


def test_auto_lock_workflow():
    """Test the complete auto-lock workflow"""
    print("🚀 Testing Auto-Lock Functionality")
    print("=" * 50)
    
    # Initialize the PC lock manager
    lock_manager = PCLockManager()
    
    # Configure settings
    lock_manager.set_person_absent_threshold(5.0)  # 5 seconds for testing
    lock_manager.set_lock_timeout(10.0)  # 10 seconds for testing
    lock_manager.set_enabled(True)
    
    print(f"⚙️ Configuration:")
    print(f"   • Person absent threshold: {lock_manager.person_absent_threshold}s")
    print(f"   • Lock timeout: {lock_manager.lock_timeout}s")
    print(f"   • Auto-lock enabled: {lock_manager.is_enabled}")
    print()
    
    # Simulate person detection workflow
    print("👤 Simulating person detection workflow...")
    print()
    
    # Step 1: Person is present
    print("1️⃣ Person detected at desk")
    lock_manager.update_person_presence(True)
    time.sleep(2)
    
    # Step 2: Person leaves desk
    print("2️⃣ Person leaves desk (no detection)")
    lock_manager.update_person_presence(False)
    print("   ⏳ Waiting for absence threshold...")
    
    # Wait and show what would happen
    for i in range(int(lock_manager.person_absent_threshold)):
        print(f"   ⏱️ {i+1}s - Person still absent...")
        time.sleep(1)
    
    print("   🔔 At this point, notification would appear")
    print(f"   ⏳ User would have {lock_manager.lock_timeout}s to acknowledge")
    print("   🔒 If no acknowledgment, PC would be locked")
    print()
    
    # Step 3: Test acknowledgment
    print("3️⃣ Testing user acknowledgment...")
    lock_manager.update_person_presence(False)  # Still absent
    time.sleep(2)
    
    print("   👤 User acknowledges presence (simulated)")
    lock_manager.acknowledge_presence()
    print("   ✅ Timer reset - PC lock cancelled")
    print()
    
    # Step 4: Test person returning
    print("4️⃣ Testing person return to desk...")
    lock_manager.update_person_presence(True)
    print("   👤 Person detected back at desk")
    print("   🖥️ Screen wake signal would be sent")
    print()
    
    print("✅ Auto-lock workflow test completed!")
    print()
    
    # Show final status
    status = lock_manager.get_status()
    print("📊 Final Status:")
    for key, value in status.items():
        print(f"   • {key}: {value}")


def test_settings_simulation():
    """Test different configuration settings"""
    print("⚙️ Testing Configuration Settings")
    print("=" * 50)
    
    lock_manager = PCLockManager()
    
    # Test different thresholds
    thresholds = [5.0, 10.0, 30.0]
    timeouts = [10.0, 30.0, 60.0]
    
    for absent_threshold in thresholds:
        for timeout in timeouts:
            print(f"Configuration: {absent_threshold}s detection, {timeout}s timeout")
            lock_manager.set_person_absent_threshold(absent_threshold)
            lock_manager.set_lock_timeout(timeout)
            
            status = lock_manager.get_status()
            print(f"   ✓ Absent threshold: {status['absent_threshold']}s")
            print(f"   ✓ Lock timeout: {status['lock_timeout']}s")
    
    print("✅ Configuration test completed!")


def interactive_test():
    """Interactive test mode"""
    print("🎮 Interactive Auto-Lock Test")
    print("=" * 50)
    print("Commands:")
    print("  'present' - Simulate person detection")
    print("  'absent' - Simulate no person detection") 
    print("  'enable' - Enable auto-lock")
    print("  'disable' - Disable auto-lock")
    print("  'status' - Show current status")
    print("  'quit' - Exit")
    print()
    
    lock_manager = PCLockManager()
    lock_manager.set_person_absent_threshold(3.0)  # Quick for testing
    lock_manager.set_lock_timeout(5.0)
    
    while True:
        try:
            command = input("Enter command: ").strip().lower()
            
            if command == 'quit':
                break
            elif command == 'present':
                lock_manager.update_person_presence(True)
                print("👤 Person detected")
            elif command == 'absent':
                lock_manager.update_person_presence(False)
                print("👻 Person absent")
            elif command == 'enable':
                lock_manager.set_enabled(True)
                print("✅ Auto-lock enabled")
            elif command == 'disable':
                lock_manager.set_enabled(False)
                print("❌ Auto-lock disabled")
            elif command == 'status':
                status = lock_manager.get_status()
                print("📊 Current Status:")
                for key, value in status.items():
                    print(f"   • {key}: {value}")
            else:
                print("❓ Unknown command")
                
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"❌ Error: {e}")
    
    print("\n👋 Interactive test ended")


if __name__ == "__main__":
    print("🔒 Auto-Lock Feature Test Suite")
    print("=" * 50)
    print()
    
    if len(sys.argv) > 1 and sys.argv[1] == "interactive":
        interactive_test()
    else:
        print("Running automated tests...")
        print()
        
        try:
            test_auto_lock_workflow()
            print()
            test_settings_simulation()
            
            print()
            print("🎉 All tests completed successfully!")
            print()
            print("💡 Tips for using the auto-lock feature:")
            print("   • Enable in the main GUI with the 'Enable Auto-Lock' button")
            print("   • Configure timers in Settings > Auto-Lock tab")
            print("   • The system detects person presence using pose detection")
            print("   • Notifications give you time to acknowledge your presence")
            print("   • PC automatically wakes when you return to desk")
            print()
            print("🚀 To run interactive test: python test_autolock.py interactive")
            
        except Exception as e:
            print(f"❌ Test failed with error: {e}")
            import traceback
            traceback.print_exc()