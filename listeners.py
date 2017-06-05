import logging, os, sys, stat
from exceptionThreading import ExceptionThread
from evdev import InputDevice, ecodes
from select import select
from auxilary import CountdownTimer, waitForPath
import stateMachine

logger = logging.getLogger(__name__)

class KeypadListener(ExceptionThread):
	def __init__(self, stateMachine, callbackDisarm, callbackArm, soundLib, passwd):
		
		ctrlKeys = { 69: 'NUML', 98: '/', 14: 'BS', 96: 'ENTER'}
		
		volKeys = { 55: '*', 74: '-', 78: '+'}
		
		numKeys = {
			71: '7', 72: '8', 73: '9',
			75: '4', 76: '5', 77: '6',
			79: '1', 80: '2', 81: '3',
			82: '0', 83: '.'
		}
		
		devPath = '/dev/input/by-id/usb-04d9_1203-event-kbd'
		
		waitForPath(devPath, logger)

		self._dev = InputDevice(devPath)
		self._dev.grab()
		
		numKeySound = soundLib.soundEffects['numKey']
		ctrlKeySound = soundLib.soundEffects['ctrlKey']
		wrongPassSound = soundLib.soundEffects['wrongPass']
		backspaceSound = soundLib.soundEffects['backspace']
		
		self._clearBuffer()
		
		def getInput():
			while 1:
				r, w, x = select([self._dev], [], [])
				for event in self._dev.read():
					if event.type == 1 and event.value == 1:
						
						# numeral input
						if event.code in numKeys:
							if stateMachine.currentState != stateMachine.states.disarmed:
								self._buf = self._buf + numKeys[event.code]
								self._startResetCountdown()
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
										callbackDisarm()
									else:
										self.resetBuffer()
										wrongPassSound.play()
							
							# arm
							elif val == 'NUML':
								callbackArm()
								ctrlKeySound.play()
								
							# delete last char in buffer
							elif val == 'BS':
								self._buf = self._buf[:-1]
								if self._buf == '':
									self._stopResetCountdown()
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

		self._resetCountdown = None
		
		self._listener = ExceptionThread(target=getInput, daemon=True)
		self._listener.start()
		logger.debug('Started keypad device')

	def _startResetCountdown(self):
		print('hey')
		self._resetCountdown = CountdownTimer(30, self._clearBuffer)
		
	def _stopResetCountdown(self):
		print('ho')
		if self._resetCountdown is not None and self._resetCountdown.is_alive():
			self._resetCountdown.stop()
		self._resetCountdown = None

	def resetBuffer(self):
		self._stopResetCountdown
		self._clearBuffer()
		
	def _clearBuffer(self):
		self._buf = ''
		
	def __del__(self):
		try:
			self._dev.ungrab()
			logger.debug('Released keypad device')
		except IOError:
			logger.error('Failed to release keypad device')
		except AttributeError:
			pass
			
class PipeListener(ExceptionThread):
	
	_rootDir = '/tmp'
	_pipeMode = 0o0777
	
	def __init__(self, callback, name):
		self._path = os.path.join(self._rootDir, name)
		
		if not os.path.exists(self._path):
			os.mkfifo(self._path, mode=self._pipeMode)
		else:
			st_mode = os.state(self._path).st_mode
			if not stat.S_ISFIFO(st_mode):
				os.remove(self._path)
				os.mkfifo(self._path, mode=self._pipeMode)
			elif st_mode % 0o10000 != self._pipeMode:
				os.chmod(self._path, self._pipeMode)
		
		def listenForSecret():
			while 1:
				with open(self._path, 'r') as f:
					msg = f.readline()[:-1]
					callback(msg, logger)
		
		super().__init__(target=listenForSecret, daemon=True)
		self.start()
		logger.debug('Started pipe listener at path %s', self._path)
		
	def __del__(self):
		try:
			os.remove(self._path)
		except FileNotFoundError:
			pass
		logger.debug('Cleaned up pipe listener at path %s', self._path)
