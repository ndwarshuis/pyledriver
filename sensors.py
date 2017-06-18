'''
IR and magnetic sensors
'''
import RPi.GPIO as GPIO
import logging, time
from functools import partial
from threading import Timer

logger = logging.getLogger(__name__)

# this importantly controls which sensor events get logged. DEBUG logs
# everything, INFO logs only events that occur when state machine in
# "sensitive states" (armed, trippedCountdown, tripped)
logger.setLevel(logging.INFO)

# delay GPIO init to avoid false positive during powerup
INIT_DELAY = 60

def _lowPassFilter(pin, targetVal, period=0.001):
	'''
	Crude implementation of an LPF for a binary signal. This exists to filter
	out voltage spikes that are induced by mains current fuctuations.
	
	Basically uses a timed loop to determine if a pin is changing within a
	given period. If a change occurs within period, this is considered 'high
	frequency' and the function returns False. If not, the pin is evaluated with
	a target value, which returns a boolean	result that can be used elsewhere
	'''
	divisions = 10
	sleepTime = period/divisions
	
	for i in range(0, divisions):
		time.sleep(sleepTime)
		if GPIO.input(pin) != targetVal:
			return False

	return GPIO.input(pin) == targetVal

def _initGPIO(name, pin, GPIOEvent, callback):
	logger.debug('starting \"%s\" on pin %s', name, pin)
	GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
	GPIO.add_event_detect(pin, GPIOEvent, callback=callback, bouncetime=500)

def startMotionSensor(pin, location, action):
	name = 'MotionSensor@' + location

	def trip(channel):
		if _lowPassFilter(pin, 1):
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
			if _lowPassFilter(pin, val):
				closed = val
				action(closed, logger)
	
	_initGPIO('DoorSensor', pin, GPIO.BOTH, trip)
	closed = GPIO.input(pin)
