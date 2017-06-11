import RPi.GPIO as GPIO
import time, logging, enum, os
from threading import Lock
from functools import partial
from collections import namedtuple

from exceptionThreading import ExceptionThread
from config import stateFile
from sensors import startDoorSensor, startMotionSensor
from gmail import intruderAlert
from listeners import KeypadListener, PipeListener
from blinkenLights import Blinkenlights
from soundLib import SoundLib
from webInterface import startWebInterface
from stream import Camera, FileDump

logger = logging.getLogger(__name__)

class _SIGNALS(enum.Enum):
	ARM = enum.auto()
	INSTANT_ARM = enum.auto()
	DISARM = enum.auto()
	TIMOUT = enum.auto()
	TRIGGER = enum.auto()
	
class _CountdownTimer(ExceptionThread):
	'''
	Launches thread which self terminates after some time (given in seconds).
	Termination triggers some action (a function). Optionally, a sound can be
	assigned to each 'tick'
	'''
	def __init__(self, countdownSeconds, action, sound=None):
		self._stopper = Event()

		def countdown():
			for i in range(countdownSeconds, 0, -1):
				if self._stopper.isSet():
					return None
				if sound and i < countdownSeconds:
					sound.play()
				time.sleep(1)
			action()

		super().__init__(target=countdown, daemon=True)
		self.start()

	def stop(self):
		self._stopper.set()

	def __del__(self):
		self.stop()
		
def _resetUSBDevice(device):
	'''
	Resets a USB device using the de/reauthorization method. This is really
	crude but works beautifully
	'''
	devpath = os.path.join('/sys/bus/usb/devices/' + device + '/authorized')
	with open(devpath, 'w') as f:
		f.write('0')
	with open(devpath, 'w') as f:
		f.write('1')
	logger.debug('Reset USB device: %s', devpath)

class _State:
	def __init__(self, name, entryCallbacks=[], exitCallbacks=[], sound=None):
		self.name = name
		self.entryCallbacks = entryCallbacks
		self.exitCallbacks = exitCallbacks
		self._transTbl = {}
		
		self._sound = sound
		
	def entry(self):
		logger.info('entering ' + self.name)
		if self._sound:
			self._sound.play()
		for c in self.entryCallbacks:
			c()
		
	def exit(self):
		logger.info('exiting ' + self.name)
		if self._sound:
			self._sound.stop()
		for c in self.exitCallbacks:
			c()

	def next(self, signal):
		if signal in _SIGNALS:
			return self if signal not in self._transTbl else self._transTbl[signal]
		else:
			raise Exception('Illegal signal')
			
	def addTransition(self, signal, state):
		self._transTbl[signal] = state
	
	def __str__(self):
		return self.name
	
	def __eq__(self, other):
		return self.name == other
		
	def __hash__(self):
		return hash(self.name)

class StateMachine:
	def __init__(self):
		self._lock = Lock()
		self._managed = []
		
		self.soundLib = self._addManaged(SoundLib())
		self.fileDump = self._addManaged(FileDump())
		
		self._addManaged(Camera())
		
		# add signals to self to avoid calling partial every time
		for sig in _SIGNALS:
			setattr(self, sig.name, partial(self.selectState, sig))
		
		secretTable = {
			'dynamoHum': self.DISARM,
			'zombyWoof': self.ARM,
			'imTheSlime': self.INSTANT_ARM
		}
		
		def secretCallback(secret, logger):
			if secret in secretTable:
				secretTable[secret]()
				logger.debug('Secret pipe listener received: \"%s\"', secret)
			elif logger:
				logger.debug('Secret pipe listener received invalid secret')
	
		self._addManaged(PipeListener(callback=secretCallback, name= 'secret'))

		keypadListener = self._addManaged(
			KeypadListener(
				stateMachine = self,
				callbackDisarm = self.DISARM,
				callbackArm = self.ARM,
				passwd = '5918462'
			)
		)
		
		def startTimer(t, sound):
			self._timer = _CountdownTimer(t, self.TIMOUT, sound)
			
		def stopTimer():
			if self._timer.is_alive():
				self._timer.stop()
				self._timer = None

		LED = self._addManaged(Blinkenlights(17))
		blinkingLED = partial(LED.setBlink, True)
		sfx = self.soundLib.soundEffects

		stateObjs = [
			_State(
				name = 'disarmed',
				entryCallbacks = [partial(LED.setBlink, False)],
				sound = sfx['disarmed']
			),
			_State(
				name = 'disarmedCountdown',
				entryCallbacks = [blinkingLED, partial(startTimer, 30, sfx['disarmedCountdown'])],
				exitCallbacks = [stopTimer],
				sound = sfx['disarmedCountdown']
			),
			_State(
				name = 'armed',
				entryCallbacks = [blinkingLED],
				sound = sfx['armed']
			),
			_State(
				name = 'armedCountdown',
				entryCallbacks = [blinkingLED, partial(startTimer, 30, sfx['armedCountdown'])],
				exitCallbacks = [stopTimer],
				sound = sfx['armedCountdown']
			),
			_State(
				name = 'triggered',
				entryCallbacks = [blinkingLED, intruderAlert],
				sound = sfx['triggered']
			)
		]
		
		for obj in stateObjs:
			obj.entryCallbacks.append(keypadListener.resetBuffer)
		
		self.states = st = namedtuple('States', [obj.name for obj in stateObjs])(*stateObjs)

		st.disarmed.addTransition(			_SIGNALS.ARM, 			st.disarmedCountdown)
		st.disarmed.addTransition(			_SIGNALS.INSTANT_ARM, 	st.armed)
		
		st.disarmedCountdown.addTransition(	_SIGNALS.DISARM, 		st.disarmed)
		st.disarmedCountdown.addTransition(	_SIGNALS.TIMOUT, 		st.armed)
		st.disarmedCountdown.addTransition(	_SIGNALS.INSTANT_ARM, 	st.armed)
		
		st.armed.addTransition(				_SIGNALS.DISARM, 		st.disarmed)
		st.armed.addTransition(				_SIGNALS.TRIGGER, 		st.armedCountdown)
		
		st.armedCountdown.addTransition(	_SIGNALS.DISARM, 		st.disarmed)
		st.armedCountdown.addTransition(	_SIGNALS.TIMOUT, 		st.triggered)
		st.armedCountdown.addTransition(	_SIGNALS.ARM, 			st.armed)
		st.armedCountdown.addTransition(	_SIGNALS.INSTANT_ARM, 	st.armed)
		
		st.triggered.addTransition(			_SIGNALS.DISARM, 		st.disarmed)
		st.triggered.addTransition(			_SIGNALS.ARM, 			st.armed)
		st.triggered.addTransition(			_SIGNALS.INSTANT_ARM, 	st.armed)
		
		self.currentState = getattr(self.states, stateFile['state'])
		
	def __enter__(self):
		_resetUSBDevice('1-1')
		
		self._startManaged()
		
		def action():
			if self.currentState == self.states.armed:
				self.selectState(_SIGNALS.TRIGGER)
		
		sensitiveStates = (self.states.armed, self.states.armedCountdown, self.states.triggered)

		def actionVideo(pin):
			if self.currentState in sensitiveStates:
				self.selectState(_SIGNALS.TRIGGER)
				self.fileDump.addInitiator(pin)
				while GPIO.input(pin) and self.currentState in sensitiveStates:
					time.sleep(0.1)
				self.fileDump.removeInitiator(pin)

		startMotionSensor(5, 'Nate\'s room', action)
		startMotionSensor(19, 'front door', action)
		startMotionSensor(26, 'Laura\'s room', action)
		startMotionSensor(6, 'deck window', partial(actionVideo, 6))
		startMotionSensor(13, 'kitchen bar', partial(actionVideo, 13))
		
		startDoorSensor(22, action, self.soundLib.soundEffects['door'])
		
		startWebInterface(self)
		
		self.currentState.entry()

	def __exit__(self, exception_type, exception_value, traceback):
		self._stopManaged()

	def selectState(self, signal):
		with self._lock:
			nextState = self.currentState.next(signal)
			if nextState != self.currentState:
				self.currentState.exit()
				self.currentState = nextState
				self.currentState.entry()
			
			stateFile['state'] = self.currentState.name
			
	def _addManaged(self, obj):
		self._managed.append(obj)
		return obj

	def _startManaged(self):
		for m in self._managed:
			m.start()
	
	def _stopManaged(self):
		for m in self._managed:
			m.stop()
