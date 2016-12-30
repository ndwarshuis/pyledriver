import RPi.GPIO as GPIO
import time, logging
from threading import Thread, Event
from itertools import chain

logger = logging.getLogger(__name__)

class Blinkenlights(Thread):
	def __init__(self, pin, cyclePeriod=2):
		self._stopper = Event()
		self._pin = pin
		
		self.blink = False
		self.setCyclePeriod(cyclePeriod) #cyclePeriod is length of one blink cycle in seconds
		
		GPIO.setup(pin, GPIO.OUT)
		pwm = GPIO.PWM(self._pin, 60)
		
		def blinkLights():
			pwm.start(0)
			while not self._stopper.isSet():
				t = self._sleeptime
				if self.blink:
					for dc in chain(range(100, -1, -5), range(0, 101, 5)):
						pwm.ChangeDutyCycle(dc)
						time.sleep(t)
				else:
					pwm.ChangeDutyCycle(100)
					time.sleep(t)
			pwm.stop() # required to avoid core dumps when process terminates

		super().__init__(target=blinkLights, daemon=True)
		self.start()
		logger.debug('Starting LED on pin %s', self._pin)

	def setCyclePeriod(self, cyclePeriod):
		self._sleeptime = cyclePeriod/20/2
		
	def stop(self):
		self._stopper.set()
		logger.debug('Stopping LED on pin %s', self._pin)
		
	def __del__(self):
		self.stop()
