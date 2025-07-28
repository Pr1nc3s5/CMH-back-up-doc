#!/usr/bin/env python3
"""
Physical security monitoring with GPIO tamper detection
"""
import os
import sys
import time
import logging

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    print("Warning: GPIO not available - running in simulation mode")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.emergency_wipe import crypto_shred

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TamperDetection:
    """Monitor physical tamper switches"""
    
    TAMPER_PIN = 21  # GPIO21 for tamper switch
    LED_PIN = 20     # Status LED
    
    def __init__(self):
        if GPIO_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.TAMPER_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
            GPIO.setup(self.LED_PIN, GPIO.OUT)
            
            # Set up interrupt
            GPIO.add_event_detect(
                self.TAMPER_PIN,
                GPIO.RISING,
                callback=self.tamper_detected,
                bouncetime=2000
            )
            
            # Blink LED to show active
            self.blink_led(3)
            logger.info("Tamper detection initialized")
    
    def tamper_detected(self, channel):
        """Handle tamper detection event"""
        logger.critical("TAMPER DETECTED! Initiating emergency wipe...")
        
        # Flash LED rapidly
        for _ in range(10):
            GPIO.output(self.LED_PIN, GPIO.HIGH)
            time.sleep(0.1)
            GPIO.output(self.LED_PIN, GPIO.LOW)
            time.sleep(0.1)
        
        # Trigger emergency wipe
        crypto_shred()
    
    def blink_led(self, count):
        """Blink status LED"""
        if GPIO_AVAILABLE:
            for _ in range(count):
                GPIO.output(self.LED_PIN, GPIO.HIGH)
                time.sleep(0.5)
                GPIO.output(self.LED_PIN, GPIO.LOW)
                time.sleep(0.5)
    
    def run(self):
        """Main monitoring loop"""
        logger.info("Physical security monitoring active")
        try:
            while True:
                # Heartbeat LED
                GPIO.output(self.LED_PIN, GPIO.HIGH)
                time.sleep(0.1)
                GPIO.output(self.LED_PIN, GPIO.LOW)
                time.sleep(4.9)
                
        except KeyboardInterrupt:
            logger.info("Monitoring stopped")
        finally:
            if GPIO_AVAILABLE:
                GPIO.cleanup()

if __name__ == '__main__':
    monitor = TamperDetection()
    monitor.run()