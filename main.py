#! /bin/python

import os, time, signal, traceback, logging
import RPi.GPIO as GPIO

from sharedLogging import unmountGluster # this should be first program module
from stateMachine import StateMachine

logger = logging.getLogger(__name__)

def clean():
	GPIO.cleanup()

	try:
		stateMachine.__del__()
	except NameError:
		pass

	try:
		logger.info('Terminated root process - PID: %s', os.getpid())
		unmountGluster()
	except Exception:
		logger.critical(traceback.format_exc())

def sigtermHandler(signum, stackFrame):
	logger.info('Caught SIGTERM')
	raise SystemExit

if __name__ == '__main__':
	try:
		os.chdir(os.path.dirname(os.path.realpath(__file__)))
		
		GPIO.setwarnings(False)
		GPIO.setmode(GPIO.BCM)

		stateMachine = StateMachine()

		# TODO: segfaults are annoying :(
		#~ signal.signal(signal.SIGSEGV, sig_handler)
		signal.signal(signal.SIGTERM, sigtermHandler)

		while 1:
			time.sleep(31536000)

	except Exception:
		logger.critical(traceback.format_exc())
	
	finally:
		clean()
