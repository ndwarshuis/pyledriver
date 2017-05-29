import logging, os
from subprocess import run, PIPE, CalledProcessError
from logging.handlers import TimedRotatingFileHandler

from auxilary import fallbackLogger

class GlusterFS():
	def __init__(self, server, volume, mountpoint, options=None):
		if not os.path.exists(mountpoint):
			raise FileNotFoundError
			
		self.mountpoint = mountpoint
		self.server = server
		self.volume = volume
		self.options = options
	
	def mount(self):
		if os.path.ismount(self.mountpoint):
			# NOTE: this assumes that the already-mounted device is the one intended
			fallbackLogger(__name__, 'WARNING', 'Device already mounted at {}'.format(self.mountpoint))
		else:
			dst = self.server + ':/' + self.volume
			cmd = ['mount', '-t', 'glusterfs', dst, self.mountpoint]
			if self.options:
				cmd[1:1] = ['-o', self.options]
			self._run(cmd)
	
	def unmount(self):
		self._run(['umount', self.mountpoint])
			
	def _run(self, cmd):
		try:
			run(cmd, check=True, stdout=PIPE, stderr=PIPE)
		except CalledProcessError as e:
			# we assume that this will only get thrown when the logger is not
			# active, so use fallback to get the explicit mount errors
			stderr=e.stderr.decode('ascii').rstrip()
			fallbackLogger(__name__, 'CRITICAL', stderr)
			raise SystemExit

class MasterLogger():
	def __init__(self, name, level):
		mountpoint = '/mnt/glusterfs/pyledriver'
		
		self.fs = GlusterFS('192.168.11.39', 'pyledriver', mountpoint, 'backupvolfile-server=192.168.11.48')
		self.fs.mount()
		
		consoleFormat = logging.Formatter('[%(name)s] [%(levelname)s] %(message)s')
		fileFormat = logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s')
		
		console = logging.StreamHandler()
		console.setFormatter(consoleFormat)
		
		logdest = mountpoint + '/logs'
		
		if not os.path.exists(logdest):
			os.mkdir(logdest)
		elif os.path.isfile(logdest):
			fallbackLogger(__name__, 'CRITICAL', '{} is present but is a file (vs a directory). ' \
				'Please (re)move this file to prevent data loss'.format(logdest))
			raise SystemExit
		
		self.rotatingFile = TimedRotatingFileHandler(logdest + '/pyledriver-log', when='midnight')
		self.rotatingFile.setFormatter(fileFormat)
		
		logging.basicConfig(level=getattr(logging, level), handlers=[console, self.rotatingFile])
		logger = logging.getLogger(name)
		
		# since the logger module sucks and doesn't allow me to init
		# a logger in a subclass, need to "fake" object inheritance
		for i in ['debug', 'info', 'warning', 'error', 'critical']:
			setattr(self, i, getattr(logger, i))

	def stop(self):
		self.rotatingFile.close() # must close file stream before unmounting
		self.fs.unmount()
