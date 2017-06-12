#! /usr/bin/env python3

import os, time, signal, traceback, logging
import RPi.GPIO as GPIO

from sharedLogging import unmountGluster # this should be first program module
from stateMachine import StateMachine
from exceptionThreading import excChildListener, excStopper

logger = logging.getLogger(__name__)

def clean():
	GPIO.cleanup()

	try:
		logger.info('Terminated root process - PID: %s', os.getpid())
		unmountGluster()
	except Exception:
		logger.critical(traceback.format_exc())

def sigtermHandler(signum, stackFrame):
	excStopper.set()
	logger.info('Caught SIGTERM')
	raise SystemExit

if __name__ == '__main__':
	try:
		os.chdir(os.path.dirname(os.path.realpath(__file__)))
		
		GPIO.setwarnings(False)
		GPIO.setmode(GPIO.BCM)
		
		signal.signal(signal.SIGTERM, sigtermHandler)
		
		with StateMachine() as stateMachine:
			excChildListener()

	except Exception:
		logger.critical(traceback.format_exc())
	
	finally:
		clean()
