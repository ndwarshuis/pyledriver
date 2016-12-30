import RPi.GPIO as GPIO
import logging, time
from functools import partial
from auxilary import CountdownTimer

logger = logging.getLogger(__name__)

# this should never be higher than INFO or motion will never be logged
logger.setLevel(logging.DEBUG)

# delay GPIO init to avoid false positive during powerup
INIT_DELAY = 60

def lowPassFilter(pin, targetVal, period=0.001):
	divisions = 10
	sleepTime = period/divisions
	
	for i in range(0, divisions):
		time.sleep(sleepTime)
		if GPIO.input(pin) != targetVal:
			return False

	return GPIO.input(pin) == targetVal

def setupGPIO(name, pin, GPIOEvent, callback):
	logger.info('setting up \"%s\" on pin %s', name, pin)
	GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
	GPIO.add_event_detect(pin, GPIOEvent, callback=callback, bouncetime=500)

def setupMotionSensor(pin, location, action):
	name = 'MotionSensor@' + location

	def trip(channel):
		if lowPassFilter(pin, 1):
			logger.info('detected motion: ' + location)
			action()
	
	logger.debug('waiting %s for %s to power on', INIT_DELAY, name)
	CountdownTimer(INIT_DELAY, partial(setupGPIO, name, pin, GPIO.RISING, trip))

def setupDoorSensor(pin, action, sound=None):
	def trip(channel):
		nonlocal closed
		val = GPIO.input(pin)
		
		if val != closed:
			if lowPassFilter(pin, val):
				closed = val
				if closed:
					logger.info('door closed')
					if sound:
						sound.play()
				else:
					logger.info('door opened')
					if sound:
						sound.play()
					action()
	
	setupGPIO('DoorSensor', pin, GPIO.BOTH, trip)
	closed = GPIO.input(pin)
