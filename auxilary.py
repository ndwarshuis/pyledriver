'''
Various helper functions and classes
'''

import time, os
from subprocess import check_output, DEVNULL, CalledProcessError
from threading import Event
from exceptionThreading import ExceptionThread

class CountdownTimer(ExceptionThread):
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

def mkdirSafe(path, logger):
	'''
	Makes new dir if path does not exist, and aborts program if path exists and
	path is a file not a dir. Else does nothing
	'''
	if not os.path.exists(path):
		os.mkdir(path)
	elif os.path.isfile(path):
		logger.error('%s is present but is a file (vs a directory). ' \
			'Please (re)move this file to prevent data loss', path)
		raise SystemExit

def waitForPath(path, logger=None, timeout=30):
	'''
	Waits for a path to appear. Useful for procfs and sysfs where devices
	regularly (dis)appear. Timeout given in seconds
	'''
	for i in range(0, timeout):
		if os.path.exists(path):
			return
		time.sleep(1)
	if logger:
		logger.error('Could not find %s after %s seconds', path, timeout)
	raise SystemExit

def resetUSBDevice(device):
	'''
	Resets a USB device using the de/reauthorization method. This is really
	crude but works beautifully
	'''
	devpath = os.path.join('/sys/bus/usb/devices/' + device + '/authorized')
	with open(devpath, 'w') as f:
		f.write('0')
	with open(devpath, 'w') as f:
		f.write('1')
