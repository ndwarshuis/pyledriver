#! /bin/python

import sys, os, time, signal, traceback
import RPi.GPIO as GPIO
from queue import Queue
from multiprocessing.managers import BaseManager, DictProxy

def clean():
	GPIO.cleanup()

	try:
		stateMachine.__del__()
	except NameError:
		pass
		
	try:
		webInterface.stop() # Kill process 1
	except NameError:
		pass
		
	try:
		logger.info('Terminated root process - PID: %s', os.getpid())
		logger.stop()
	except NameError:
		pass

	try:
		manager.__del__() # kill process 2
	except NameError:
		pass

def sigtermHandler(signum, stackFrame):
	logger.info('Caught SIGTERM')
	clean()
	exit()

class ResourceManager(BaseManager):
	def __init__(self):
		super().__init__()
		
		from camera import Camera
		from microphone import Microphone
		self.register('Camera', Camera)
		self.register('Queue', Queue)
		self.register('Dict', dict, DictProxy)
		
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
		camera = manager.Camera(loggerQueue)
		stateDict = manager.Dict() # used to hold state info
		ttsQueue = manager.Queue() # used as buffer for TTS Engine
		
		from sharedLogging import MasterLogger
		logger = MasterLogger(__name__, 'DEBUG', loggerQueue)

		from notifier import criticalError

		from stateMachine import StateMachine
		stateMachine = StateMachine(camera, ttsQueue, stateDict)
		
		from webInterface import WebInterface
		webInterface = WebInterface(camera, stateDict, ttsQueue, loggerQueue)
		webInterface.start() # Child process 2
		
		signal.signal(signal.SIGTERM, sigtermHandler)

		while 1:
			time.sleep(31536000)

	except Exception:
		t = 'Exception caught:\n' + traceback.format_exc()

		try:
			criticalError(t)
		except NameError:
			pass
			
		try:
			logger.critical(t)
		except NameError:
			print('[__main__] [CRITICAL] Logger not initialized, using print for console output:\n' + t)
			
		clean()
