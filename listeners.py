'''
Classes that listen for user input
'''

import logging, os, sys, stat
from threading import Timer
from exceptionThreading import ExceptionThread
from evdev import InputDevice, ecodes
from select import select
from auxilary import waitForPath
import stateMachine

logger = logging.getLogger(__name__)

class KeypadListener:
	'''
	Interface for standard numpad device. Capabilities include:
	- accepting numeric input
	- volume control
	- arm/disarm the stateMachine
	
	This launches two daemon threads:
	- input listener that accepts events and reacts in fun ways
	- countdown timer to reset the input buffer after 30 seconds of inactivity
	'''
	def __init__(self, stateMachine, callbackDisarm, callbackArm, passwd):
		
		ctrlKeys = { 69: 'NUML', 98: '/', 14: 'BS', 96: 'ENTER'}
		
		volKeys = { 55: '*', 74: '-', 78: '+'}
		
		numKeys = {
			71: '7', 72: '8', 73: '9',
			75: '4', 76: '5', 77: '6',
			79: '1', 80: '2', 81: '3',
			82: '0', 83: '.'
		}
		
		soundLib = stateMachine.soundLib
		
		numKeySound = soundLib.soundEffects['numKey']
		ctrlKeySound = soundLib.soundEffects['ctrlKey']
		wrongPassSound = soundLib.soundEffects['wrongPass']
		backspaceSound = soundLib.soundEffects['backspace']
		
		def getInput():
			while 1:
				select([self._dev], [], [])
				for event in self._dev.read():
					if event.type == 1 and event.value == 1:
						
						# numeral input
						if event.code in numKeys:
							if stateMachine.currentState != stateMachine.states.disarmed:
								self._buf = self._buf + numKeys[event.code]
								self._startResetTimer()
							numKeySound.play()

						# ctrl input
						elif event.code in ctrlKeys:
							val = ctrlKeys[event.code]
							
							# disarm if correct passwd
							if val=='ENTER':
								if stateMachine.currentState == stateMachine.states.disarmed:
									ctrlKeySound.play()
								else:
									if self._buf == '':
										ctrlKeySound.play()
									elif self._buf == passwd:
										self.resetBuffer()
										callbackDisarm()
									else:
										self.resetBuffer()
										wrongPassSound.play()
							
							# arm
							elif val == 'NUML':
								self.resetBuffer()
								callbackArm()
								ctrlKeySound.play()
								
							# delete last char in buffer
							elif val == 'BS':
								self._buf = self._buf[:-1]
								if self._buf == '':
									self._stopResetTimer()
								else:
									self._startResetTimer()
								backspaceSound.play()
							
							# reset buffer
							elif val == '/':
								self.resetBuffer()
								backspaceSound.play()
						
						# volume input
						elif event.code in volKeys:
							val = volKeys[event.code]
								
							if val == '+':
								soundLib.changeVolume(10)
								
							elif val == '-':
								soundLib.changeVolume(-10)
								
							elif val == '*':
								soundLib.mute()

							ctrlKeySound.play()
							self._dev.set_led(ecodes.LED_NUML, 0 if soundLib.volume > 0 else 1)
		
		self._listener = ExceptionThread(target=getInput, daemon=True)
		self._clearBuffer()
		
	def start(self):
		devPath = '/dev/input/by-id/usb-04d9_1203-event-kbd'
		
		waitForPath(devPath, logger)

		self._dev = InputDevice(devPath)
		self._dev.grab()
		
		self._listener.start()
		logger.debug('Started keypad listener')
		
	def stop(self):
		try:
			self._dev.ungrab()
			self._dev = None
			logger.debug('Released keypad device')
		except IOError:
			logger.error('Failed to release keypad device')
		except AttributeError:
			pass
		
	def resetBuffer(self):
		self._stopResetTimer()
		self._clearBuffer()

	def _startResetTimer(self):
		self._resetTimer = t = Timer(30, self._clearBuffer)
		t.daemon = True
		t.start()
		
	def _stopResetTimer(self):
		try:
			self._resetTimer.cancel()
		except AttributeError:
			pass
		
	def _clearBuffer(self):
		self._buf = ''
		
	def __del__(self):
		self.stop()
			
class PipeListener(ExceptionThread):
	'''
	Creates a pipe in the /tmp directory and listens for input. Primarily
	meant as a receiver for ssh sessions to echo messages to the stateMachine
	(aka secrets) that trigger a signal
	'''
	def __init__(self, callback, name):
		self._path = os.path.join('/tmp', name)

		pipeMode = 0o0777
		
		if not os.path.exists(self._path):
			os.mkfifo(self._path)
			os.chmod(self._path, pipeMode)
		else:
			st_mode = os.stat(self._path).st_mode
			if not stat.S_ISFIFO(st_mode):
				os.remove(self._path)
				os.mkfifo(self._path)
				os.chmod(self._path, pipeMode)
			elif st_mode % 0o10000 != pipeMode:
				os.chmod(self._path, pipeMode)
		
		def listen():
			while 1:
				with open(self._path, 'r') as f:
					msg = f.readline()[:-1]
					callback(msg, logger)
		
		super().__init__(target=listen, daemon=True)
		
	def start(self):
		ExceptionThread.start(self)
		logger.debug('Started pipe listener at path %s', self._path)
		
	def stop(self):
		try:
			os.remove(self._path)
			logger.debug('Cleaned up pipe listener at path %s', self._path)
		except FileNotFoundError:
			pass

	def __del__(self):
		self.stop()

