import logging, os, logging.handlers
from subprocess import run, PIPE, CalledProcessError
from logging.handlers import TimedRotatingFileHandler

from auxilary import fallbackLogger

class GlusterFSHandler(TimedRotatingFileHandler):
	def __init__(self, server, volume, mountpoint, options=None):
		if not os.path.exists(mountpoint):
			raise FileNotFoundError
			
		self._mountpoint = mountpoint
		self._server = server
		self._volume = volume
		self._options = options
		
		logdest = mountpoint + '/logs'
		
		if not os.path.exists(logdest):
			os.mkdir(logdest)
		elif os.path.isfile(logdest):
			fallbackLogger(__name__, 'CRITICAL', '{} is present but is a file (vs a directory). ' \
				'Please (re)move this file to prevent data loss'.format(logdest))
			raise SystemExit
		
		self._mount()
			
		super().__init__(logdest + '/pyledriver-log', when='midnight')

		fmt = logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s')
		self.setFormatter(fmt)

	def _mount(self):
		if os.path.ismount(self._mountpoint):
			# NOTE: this assumes that the already-mounted device is the one intended
			fallbackLogger(__name__, 'WARNING', 'Device already mounted at {}'.format(self._mountpoint))
		else:
			dst = self._server + ':/' + self._volume
			cmd = ['mount', '-t', 'glusterfs', dst, self._mountpoint]
			if self._options:
				cmd[1:1] = ['-o', self._options]
			self._run(cmd)
	
	def _unmount(self):
		self._run(['umount', self._mountpoint])
			
	def _run(self, cmd):
		try:
			run(cmd, check=True, stdout=PIPE, stderr=PIPE)
		except CalledProcessError as e:
			# we assume that this will only get thrown when the logger is not
			# active, so use fallback to get the explicit mount errors
			stderr = e.stderr.decode('ascii').rstrip()
			fallbackLogger(__name__, 'CRITICAL', stderr)
			raise SystemExit
			
	def close(self):
		TimedRotatingFileHandler.close(self) # must close file stream before unmounting
		self._unmount()

class MasterLogger():
	def __init__(self, name, level):
		self._console = logging.StreamHandler()
		self._formatConsole(False)
		
		self._rootLogger = logging.getLogger()
		self._rootLogger.addHandler(self._console)
		self._rootLogger.setLevel(getattr(logging, level))
		
		# since the logger module sucks and doesn't allow me to init
		# a logger in a subclass, need to "fake" object inheritance
		for i in ['debug', 'info', 'warning', 'error', 'critical']:
			setattr(self, i, getattr(logging.getLogger(name), i))

	def mountGluster(self):
		self._gluster = GlusterFSHandler(
			server = '192.168.11.39',
			volume = 'pyledriver',
			mountpoint = '/mnt/glusterfs/pyledriver',
			options = 'backupvolfile-server=192.168.11.48'
		)
		self._formatConsole(True)
		self._rootLogger.addHandler(self._gluster)

	def unmountGluster(self):
		self._rootLogger.removeHandler(self._gluster)
		self._formatConsole(False)
		
	def _formatConsole(self, rotatingFile=False):
		c = '' if rotatingFile else '[CONSOLE ONLY] '
		fmt = logging.Formatter('[%(name)s] [%(levelname)s] ' + c + '%(message)s')
		self._console.setFormatter(fmt)	
