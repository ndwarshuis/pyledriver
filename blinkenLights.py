import RPi.GPIO as GPIO
import time, logging
from threading import Event
from exceptionThreading import ExceptionThread
from itertools import chain

logger = logging.getLogger(__name__)

class Blinkenlights(ExceptionThread):
	def __init__(self, pin, cyclePeriod=2):
		self._stopper = Event()
		self._pin = pin
		
		self._blink = False
		self.setCyclePeriod(cyclePeriod) #cyclePeriod is length of one blink cycle in seconds
		
		GPIO.setup(pin, GPIO.OUT)
		pwm = GPIO.PWM(self._pin, 60)
		
		def blinkLights():
			pwm.start(0)
			while not self._stopper.isSet():
				t = self._sleeptime
				if self._blink:
					for dc in chain(range(100, -1, -5), range(0, 101, 5)):
						pwm.ChangeDutyCycle(dc)
						time.sleep(t)
				else:
					pwm.ChangeDutyCycle(100)
					time.sleep(t)
			pwm.stop() # required to avoid core dumps when process terminates

		super().__init__(target=blinkLights, daemon=True)
		
	def start(self):
		ExceptionThread.start(self)
		logger.debug('Starting LED on pin %s', self._pin)

	def stop(self):
		if self.is_alive():
			self._stopper.set()
			logger.debug('Stopping LED on pin %s', self._pin)

	def setCyclePeriod(self, cyclePeriod):
		self._sleeptime = cyclePeriod/20/2
		
	def setBlink(self, toggle):
		self._blink = toggle
		
	def __del__(self):
		self.stop()
