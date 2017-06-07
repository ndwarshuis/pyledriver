import RPi.GPIO as GPIO
import time, logging
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

class SIGNALS:
	ARM = 1
	INSTANT_ARM = 2
	DISARM = 3
	TIMOUT = 4
	TRIGGER = 5	

class State:
	def __init__(self, stateMachine, name, entryCallbacks=[], exitCallbacks=[], blinkLED=True, sound=None):
		self.stateMachine = stateMachine
		self.name = name
		self.entryCallbacks = entryCallbacks
		self.exitCallbacks = exitCallbacks
		self.blinkLED = blinkLED
		
		if not sound and name in stateMachine.soundLib.soundEffects:
			self.sound = stateMachine.soundLib.soundEffects[name]
		else:
			self.sound = sound
		
	def entry(self):
		logger.info('entering ' + self.name)
		if self.sound:
			self.sound.play()
		self.stateMachine.LED.blink = self.blinkLED
		self.stateMachine.keypadListener.resetBuffer()
		for c in self.entryCallbacks:
			c()
		
	def exit(self):
		logger.info('exiting ' + self.name)
		if self.sound:
			self.sound.stop()
		for c in self.exitCallbacks:
			c()

	def next(self, signal):
		t = (self, signal)
		return self if t not in self.stateMachine.transitionTable else self.stateMachine.transitionTable[t]
	
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
		
		def startTimer(t, sound):
			self._timer = CountdownTimer(t, partial(self.selectState, SIGNALS.TIMOUT), sound)
			
		def stopTimer():
			if self._timer.is_alive():
				self._timer.stop()
				self._timer = None

		stateObjs = [
			State(
				self,
				name = 'disarmed',
				blinkLED = False
			),
			State(
				self,
				name='disarmedCountdown',
				entryCallbacks = [partial(startTimer, 30, self.soundLib.soundEffects['disarmedCountdown'])],
				exitCallbacks = [stopTimer]
			),
			State(
				self,
				name = 'armed'
			),
			State(
				self,
				name = 'armedCountdown',
				entryCallbacks = [partial(startTimer, 30, self.soundLib.soundEffects['armedCountdown'])],
				exitCallbacks = [stopTimer]
			),
			State(
				self,
				name = 'triggered',
				entryCallbacks = [intruderAlert]
			)
		]
		
		self.states = namedtuple('States', [s.name for s in stateObjs])(*stateObjs)

		self.currentState = getattr(self.states, stateFile['state'])
		
		self.transitionTable = {
			(self.states.disarmed, 			SIGNALS.ARM): 			self.states.disarmedCountdown,
			(self.states.disarmed, 			SIGNALS.INSTANT_ARM): 	self.states.armed,
			
			(self.states.disarmedCountdown,	SIGNALS.DISARM): 		self.states.disarmed,
			(self.states.disarmedCountdown, SIGNALS.TIMOUT):		self.states.armed,
			(self.states.disarmedCountdown, SIGNALS.INSTANT_ARM):	self.states.armed,
			
			(self.states.armed, 			SIGNALS.DISARM): 		self.states.disarmed,
			(self.states.armed, 			SIGNALS.TRIGGER): 		self.states.armedCountdown,
			
			(self.states.armedCountdown, 	SIGNALS.DISARM): 		self.states.disarmed,
			(self.states.armedCountdown, 	SIGNALS.ARM): 			self.states.armed,
			(self.states.armedCountdown, 	SIGNALS.TIMOUT):		self.states.triggered,
			
			(self.states.triggered, 		SIGNALS.DISARM):		self.states.disarmed,
			(self.states.triggered, 		SIGNALS.ARM):			self.states.armed,
		}
		
		secretTable = {
			"dynamoHum": 	partial(self.selectState, SIGNALS.DISARM),
			"zombyWoof": 	partial(self.selectState, SIGNALS.ARM),
			"imTheSlime": 	partial(self.selectState, SIGNALS.INSTANT_ARM)
		}
		
		def secretCallback(secret, logger):
			if secret in secretTable:
				secretTable[secret]()
				logger.debug('Secret pipe listener received: \"%s\"', secret)
			elif logger:
				logger.debug('Secret pipe listener received invalid secret')
	
		self.secretListener = PipeListener(
			callback = secretCallback,
			name = 'secret'
		)

		self.keypadListener = KeypadListener(
			stateMachine = self,
			callbackDisarm = partial(self.selectState, 'disarm'),
			callbackArm = partial(self.selectState, 'arm'),
			soundLib = self.soundLib,
			passwd = '5918462'
		)
		
	def start(self):
		resetUSBDevice('1-1')
		
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
		
	def selectState(self, signal):
		with self._lock:
			nextState = self.currentState.next(signal)
			if nextState != self.currentState:
				self.currentState.exit()
				self.currentState = nextState
				self.currentState.entry()
			
			stateFile['state'] = self.currentState.name
			
			logger.info('state changed to %s', self.currentState)
		
	def __del__(self):
		for i in ['LED', 'camera', 'fileDump', 'soundLib', 'secretListener', 'keypadListener']:
			try:
				getattr(self, i).__del__()
			except AttributeError:
				pass
