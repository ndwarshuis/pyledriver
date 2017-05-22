import logging, os, sys
from subprocess import run, PIPE, CalledProcessError
from logging.handlers import TimedRotatingFileHandler, QueueListener, QueueHandler

from auxilary import fallbackLogger

def SlaveLogger(name, level, queue):
	logger = logging.getLogger(name)
	logger.setLevel(getattr(logging, level))
	logger.addHandler(QueueHandler(queue))
	logger.propagate = False
	return logger

class GlusterFS():
	def __init__(self, server, volume, mountpoint):
		self.server = server
		self.volume = volume
		
		if not os.path.exists(mountpoint):
			raise FileNotFoundError
			
		self.mountpoint = mountpoint
	
	def mount(self):
		self._run(['mount', '-t', 'glusterfs', self.server + ':/' + self.volume, self.mountpoint])
	
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
			sys.exit()

class MasterLogger():
	def __init__(self, name, level, queue):
		mountpoint = '/mnt/glusterfs/pyledriver'
		
		self.fs = GlusterFS('192.168.11.39', 'pyledriver', mountpoint)
		self.fs.mount()
		
		consoleFormat = logging.Formatter('[%(name)s] [%(levelname)s] %(message)s')
		fileFormat = logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s')
		
		console = logging.StreamHandler()
		console.setFormatter(consoleFormat)
		
		# TODO: check that 'logs' actually exists in the mp
		self.rotatingFile = TimedRotatingFileHandler(mountpoint + '/logs/pyledriver-log', when='midnight')
		self.rotatingFile.setFormatter(fileFormat)
		
		logging.basicConfig(level=getattr(logging, level), handlers=[QueueHandler(queue)])
		logger = logging.getLogger(name)
		
		# since the logger module sucks and doesn't allow me to init
		# a logger in a subclass, need to "fake" object inheritance
		for i in ['debug', 'info', 'warning', 'error', 'critical']:
			setattr(self, i, getattr(logger, i))
		
		self.queListener = QueueListener(queue, console, self.rotatingFile)
		self.queListener.start()

	def stop(self):
		self.queListener.stop()
		self.rotatingFile.close() # must close file stream before unmounting
		self.fs.unmount()
