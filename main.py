#! /bin/python

import sys, os, time, signal, traceback
import RPi.GPIO as GPIO
from queue import Queue
from multiprocessing.managers import BaseManager

from auxilary import fallbackLogger

def printTrace(t):
	fallbackLogger(__name__, 'CRITICAL', t)

def clean():
	GPIO.cleanup()

	try:
		stateMachine.__del__()
	except NameError:
		pass

	# TODO: this part is really wordy and makes me sad
	try:
		logger.info('Terminated root process - PID: %s', os.getpid())
		logger.stop()
	except NameError:
		pass
	except Exception:
		printTrace(traceback.format_exc())

	try:
		manager.__del__() # kill process 2
	except NameError:
		pass
	except Exception:
		printTrace(traceback.format_exc())

def sigtermHandler(signum, stackFrame):
	logger.info('Caught SIGTERM')
	raise SystemExit

class ResourceManager(BaseManager):
	def __init__(self):
		super().__init__()
		
		self.register('Queue', Queue)
		
	def __del__(self):
		self.shutdown()

if __name__ == '__main__':
	try:
		os.chdir(os.path.dirname(os.path.realpath(__file__)))
		
		GPIO.setwarnings(False)
		GPIO.setmode(GPIO.BCM)

		manager = ResourceManager()
		manager.start() # Child process 1
		
		loggerQueue = manager.Queue() # used to buffer logs
		ttsQueue = manager.Queue() # used as buffer for TTS Engine
		
		from sharedLogging import MasterLogger
		logger = MasterLogger(__name__, 'DEBUG', loggerQueue)

		from notifier import criticalError
		
		from stateMachine import StateMachine
		stateMachine = StateMachine()

		# TODO: segfaults are annoying :(
		#~ signal.signal(signal.SIGSEGV, sig_handler)
		signal.signal(signal.SIGTERM, sigtermHandler)

		while 1:
			time.sleep(31536000)

	except Exception:
		t = traceback.format_exc()

		try:
			criticalError(t)
		except NameError:
			pass
			
		try:
			logger.critical(t)
		except NameError:
			printTrace(t)
	
	finally:
		clean()
