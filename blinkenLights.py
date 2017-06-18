'''
Controls an LED using a GPIO pin
'''
import RPi.GPIO as GPIO
import time, logging
from threading import Event
from exceptionThreading import ExceptionThread
from itertools import chain

logger = logging.getLogger(__name__)

class Blinkenlights(ExceptionThread):
	def __init__(self, pin, cyclePeriod=2):
		self._stopper = Event()
		self._blink = Event()
		self._linear = Event()
		
		# number of pwm adjustments madeper duty cycle, note stepsize is in half
		# because we spend first half of period decreasing duty cycle and the
		# second half increasing (between 0 and 100)
		self._steps = 40
		self._stepsize = int(100/(self._steps/2))
	
		self._pin = pin
		
		self.setCyclePeriod(cyclePeriod) #cyclePeriod is length of one blink cycle in seconds
		
		GPIO.setup(pin, GPIO.OUT)
		pwm = GPIO.PWM(self._pin, 60)
		
		def linearLoop():
			for dc in chain(range(100, -1, -self._stepsize), range(0, 101, self._stepsize)):
				t = (self._linear.is_set(), self._blink.is_set())
				if t == (True, True):
					pwm.ChangeDutyCycle(dc)
					time.sleep(self._sleeptime)
				else:
					return t
			return (True, True)
		
		def blinkLights():
			pwm.start(0)
			while not self._stopper.isSet():
				if self._blink.is_set():
					linearSet, blinkSet = linearLoop()
					
					if not blinkSet:
						continue
					elif not linearSet:
						t = self._sleeptime*self._steps/2
					
						pwm.ChangeDutyCycle(100)
						self._linear.wait(timeout=t)
						
						if self._linear.is_set() or not self._blink.is_set():
							continue
							
						pwm.ChangeDutyCycle(0)
						self._linear.wait(timeout=t)
				else:
					pwm.ChangeDutyCycle(100)
					self._blink.wait()			
			pwm.stop() # required to avoid core dumps when process terminates

		super().__init__(target=blinkLights, daemon=True)
		
	def start(self):
		ExceptionThread.start(self)
		logger.debug('Starting LED on pin %s', self._pin)

	def stop(self):
		if self.is_alive():
			self._stopper.set()
			self._blink.set()
			self._linear.set()
			logger.debug('Stopping LED on pin %s', self._pin)

	def setCyclePeriod(self, cyclePeriod):
		self._sleeptime = cyclePeriod/self._steps
			
	def setLinear(self, toggle):
		if toggle:
			self._linear.set()
		else:
			self._linear.clear()

	def setBlink(self, toggle):
		if toggle:
			self._blink.set()
			# unblock the _linear Event if threads are waiting on it
			if not self._linear.is_set():
				self._linear.set()
				self._linear.clear()
		else:
			self._blink.clear()
		
	def __del__(self):
		self.stop()
