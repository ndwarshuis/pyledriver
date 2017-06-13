import RPi.GPIO as GPIO
import logging, time
from functools import partial
from threading import Timer

logger = logging.getLogger(__name__)

# this importantly controls which sensor events get logged. DEBUG logs
# everything, INFO logs only events that occur when state machine in
# "sensitive states" (armed, armedCountdown, triggered)
logger.setLevel(logging.INFO)

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

def _initGPIO(name, pin, GPIOEvent, callback):
	logger.info('setting up \"%s\" on pin %s', name, pin)
	GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
	GPIO.add_event_detect(pin, GPIOEvent, callback=callback, bouncetime=500)

def startMotionSensor(pin, location, action):
	name = 'MotionSensor@' + location

	def trip(channel):
		if lowPassFilter(pin, 1):
			action(location, logger)
	
	logger.debug('waiting %s for %s to power on', INIT_DELAY, name)
	t = Timer(INIT_DELAY, partial(_initGPIO, name, pin, GPIO.RISING, trip))
	t.daemon = True
	t.start()

def startDoorSensor(pin, action):
	def trip(channel):
		nonlocal closed
		val = GPIO.input(pin)
		
		if val != closed:
			if lowPassFilter(pin, val):
				closed = val
				action(closed, logger)
	
	_initGPIO('DoorSensor', pin, GPIO.BOTH, trip)
	closed = GPIO.input(pin)
