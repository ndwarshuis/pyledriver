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
	'''
	Controls one LED on a GPIO pin. LED brightness can be control via
	pulse-width modulation (pwm) and can be set to a constant brightness or 
	fluctuate as a triangle wave or square wave, each with varying periods.
	'''
	def __init__(self, pin, cyclePeriod=2):
		self._stopper = Event()
		self._blink = Event()
		self._triangle = Event()
		
		# number of pwm adjustments madeper duty cycle, note stepsize is in half
		# because we spend first half of period decreasing duty cycle and the
		# second half increasing (between 0 and 100)
		self._steps = 40
		self._stepsize = int(100/(self._steps/2))
	
		self._pin = pin
		
		self.setCyclePeriod(cyclePeriod) #cyclePeriod is length of one blink cycle in seconds
		
		GPIO.setup(pin, GPIO.OUT)
		pwm = GPIO.PWM(self._pin, 60)
		
		def triangleLoop():
			'''
			Controls the brightness in triangle-wave mode. Note that this will
			exit as soon as _triangle or _blink events are cleared...this may
			seem convoluted but is necessary to ensure clean response times
			when the mode is changed
			'''
			for dc in chain(range(100, -1, -self._stepsize), range(0, 101, self._stepsize)):
				t = (self._triangle.is_set(), self._blink.is_set())
				if t == (True, True):
					pwm.ChangeDutyCycle(dc)
					time.sleep(self._sleeptime)
				else:
					return t
			return (True, True)
		
		def blinkLights():
			'''
			Uses mode to control brightness. This function has three phases in
			its lifetime:
			1) start PWM on the GPIO pin
			2) brightness control loop, which exits on setting _stopper event
			3) stop PWM (if this doesn't happen we segfault)
			
			Within the brightness control loop, flow is controled by events,
			which ensure good response times when we transition b/t states as
			well as high cpu efficiency (no busy waits).
			'''
			pwm.start(0)
			while not self._stopper.isSet():
				if self._blink.is_set():
					triangleSet, blinkSet = triangleLoop()
					
					if not blinkSet:
						continue
					elif not triangleSet:
						t = self._sleeptime*self._steps/2
					
						pwm.ChangeDutyCycle(100)
						self._triangle.wait(timeout=t)
						
						if self._triangle.is_set() or not self._blink.is_set():
							continue
							
						pwm.ChangeDutyCycle(0)
						self._triangle.wait(timeout=t)
				else:
					pwm.ChangeDutyCycle(100)
					self._blink.wait()			
			pwm.stop()

		super().__init__(target=blinkLights, daemon=True)
		
	def start(self):
		ExceptionThread.start(self)
		logger.debug('Starting LED on pin %s', self._pin)

	def stop(self):
		if self.is_alive():
			self._stopper.set()
			self._blink.set()
			self._triangle.set()
			logger.debug('Stopping LED on pin %s', self._pin)

	def setCyclePeriod(self, cyclePeriod):
		self._sleeptime = cyclePeriod/self._steps
			
	def setTriangle(self, toggle):
		if toggle:
			self._triangle.set()
		else:
			self._triangle.clear()

	def setBlink(self, toggle):
		if toggle:
			self._blink.set()
			# unblock the _triangle Event if threads are waiting on it
			if not self._triangle.is_set():
				self._triangle.set()
				self._triangle.clear()
		else:
			self._blink.clear()
		
	def __del__(self):
		self.stop()
