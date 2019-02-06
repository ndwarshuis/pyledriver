'''
Various helper functions and classes
'''

import time, os

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

def waitForPath(path, logger, timeout=30):
	'''
	Waits for a path to appear. Useful for procfs and sysfs where devices
	regularly (dis)appear. Timeout given in seconds
	'''
	for i in range(0, timeout):
		if os.path.exists(path):
			return
		time.sleep(1)
	logger.error('Could not find %s after %s seconds', path, timeout)
	raise SystemExit
