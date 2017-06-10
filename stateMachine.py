import RPi.GPIO as GPIO
import time, logging, enum, weakref
from threading import Lock
from functools import partial
from collections import namedtuple

from auxilary import CountdownTimer, resetUSBDevice
from config import stateFile
from sensors import startDoorSensor, startMotionSensor
from gmail import intruderAlert
from listeners import KeypadListener, PipeListener
from blinkenLights import Blinkenlights
from soundLib import SoundLib
from webInterface import startWebInterface
from stream import Camera, FileDump

logger = logging.getLogger(__name__)

class SIGNALS(enum.Enum):
	ARM = enum.auto()
	INSTANT_ARM = enum.auto()
	DISARM = enum.auto()
	TIMOUT = enum.auto()
	TRIGGER = enum.auto()

class State:
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
		if signal in SIGNALS:
			return self if signal not in self._transTbl else self._transTbl[signal]
		else:
			raise Exception('Illegal signal')
			
	def addTransition(self, signal, state):
		self._transTbl[signal] = weakref.ref(state)
	
	def __str__(self):
		return self.name
	
	def __eq__(self, other):
		return self.name == other
		
	def __hash__(self):
		return hash(self.name)

class StateMachine:
	def __init__(self):
		self._lock = Lock()
		
		self.soundLib = SoundLib()
		self.LED = Blinkenlights(17)
		self.camera = Camera()
		self.fileDump = FileDump()
		
		# add signals to self to avoid calling partial every time
		for s in SIGNALS:
			setattr(self, s.name, partial(self.selectState, s))
		
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
	
		self.secretListener = PipeListener(callback=secretCallback, name= 'secret')

		self.keypadListener = KeypadListener(
			stateMachine = self,
			callbackDisarm = self.DISARM,
			callbackArm = self.ARM,
			soundLib = self.soundLib,
			passwd = '5918462'
		)
		
		def startTimer(t, sound):
			self._timer = CountdownTimer(t, self.TIMOUT, sound)
			
		def stopTimer():
			if self._timer.is_alive():
				self._timer.stop()
				self._timer = None

		blinkingLED = partial(self.LED.setBlink, True)
		sfx = self.soundLib.soundEffects

		stateObjs = [
			State(
				name = 'disarmed',
				entryCallbacks = [partial(self.LED.setBlink, False)],
				sound = sfx['disarmed']
			),
			State(
				name = 'disarmedCountdown',
				entryCallbacks = [blinkingLED, partial(startTimer, 30, sfx['disarmedCountdown'])],
				exitCallbacks = [stopTimer],
				sound = sfx['disarmedCountdown']
			),
			State(
				name = 'armed',
				entryCallbacks = [blinkingLED],
				sound = sfx['armed']
			),
			State(
				name = 'armedCountdown',
				entryCallbacks = [blinkingLED, partial(startTimer, 30, sfx['armedCountdown'])],
				exitCallbacks = [stopTimer],
				sound = sfx['armedCountdown']
			),
			State(
				name = 'triggered',
				entryCallbacks = [blinkingLED, intruderAlert],
				sound = sfx['triggered']
			)
		]
		
		for s in stateObjs:
			s.entryCallbacks.append(self.keypadListener.resetBuffer)
		
		self.states = s = namedtuple('States', [s.name for s in stateObjs])(*stateObjs)

		s.disarmed.addTransition(			SIGNALS.ARM, 			s.disarmedCountdown)
		s.disarmed.addTransition(			SIGNALS.INSTANT_ARM, 	s.armed)
		
		s.disarmedCountdown.addTransition(	SIGNALS.DISARM, 		s.disarmed)
		s.disarmedCountdown.addTransition(	SIGNALS.TIMOUT, 		s.armed)
		s.disarmedCountdown.addTransition(	SIGNALS.INSTANT_ARM, 	s.armed)
		
		s.armed.addTransition(				SIGNALS.DISARM, 		s.disarmed)
		s.armed.addTransition(				SIGNALS.TRIGGER, 		s.armedCountdown)
		
		s.armedCountdown.addTransition(		SIGNALS.DISARM, 		s.disarmed)
		s.armedCountdown.addTransition(		SIGNALS.TIMOUT, 		s.triggered)
		s.armedCountdown.addTransition(		SIGNALS.ARM, 			s.armed)
		s.armedCountdown.addTransition(		SIGNALS.INSTANT_ARM, 	s.armed)
		
		s.triggered.addTransition(			SIGNALS.DISARM, 		s.disarmed)
		s.triggered.addTransition(			SIGNALS.ARM, 			s.armed)
		s.triggered.addTransition(			SIGNALS.INSTANT_ARM, 	s.armed)
		
		self.currentState = getattr(self.states, stateFile['state'])
		
	def __enter__(self):
		resetUSBDevice('1-1', logger)
		
		self.soundLib.start()
		self.LED.start()
		self.keypadListener.start()
		self.secretListener.start()
		self.camera.start()
		self.fileDump.start()
		
		def action():
			if self.currentState == self.states.armed:
				self.selectState(SIGNALS.TRIGGER)
		
		sensitiveStates = (self.states.armed, self.states.armedCountdown, self.states.triggered)

		def actionVideo(pin):
			if self.currentState in sensitiveStates:
				self.selectState(SIGNALS.TRIGGER)
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
		for i in ['LED', 'camera', 'fileDump', 'soundLib', 'secretListener', 'keypadListener']:
			try:
				getattr(self, i).stop()
			except AttributeError:
				pass
		for i in ['LED', 'camera', 'fileDump', 'soundLib', 'secretListener', 'keypadListener']:
			try:
				getattr(self, i).__del__()
			except AttributeError:
				pass

	def selectState(self, signal):
		with self._lock:
			nextState = self.currentState.next(signal)
			if nextState != self.currentState:
				self.currentState.exit()
				self.currentState = nextState
				self.currentState.entry()
			
			stateFile['state'] = self.currentState.name
