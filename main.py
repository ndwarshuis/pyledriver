#! /bin/python

import os, time, signal, traceback
import RPi.GPIO as GPIO

from auxilary import fallbackLogger
from sharedLogging import MasterLogger

logger = MasterLogger(__name__, 'DEBUG')

def printTrace(t):
	fallbackLogger(__name__, 'CRITICAL', '\n' + t)

def clean():
	GPIO.cleanup()

	try:
		stateMachine.__del__()
	except NameError:
		pass

	try:
		logger.info('Terminated root process - PID: %s', os.getpid())
		logger.unmountGluster()
	except NameError:
		pass
	except Exception:
		printTrace(traceback.format_exc())

def sigtermHandler(signum, stackFrame):
	logger.info('Caught SIGTERM')
	raise SystemExit

if __name__ == '__main__':
	try:
		os.chdir(os.path.dirname(os.path.realpath(__file__)))
		
		GPIO.setwarnings(False)
		GPIO.setmode(GPIO.BCM)

		logger.mountGluster()
		
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
