import logging, os
from subprocess import run, PIPE, CalledProcessError
from logging.handlers import TimedRotatingFileHandler

# formats console output depending on whether we have gluster
def _formatConsole(gluster = False):
	c = '' if gluster else '[CONSOLE ONLY] '
	fmt = logging.Formatter('[%(name)s] [%(levelname)s] ' + c + '%(message)s')
	console.setFormatter(fmt)	

# init console, but don't expect gluster to be here yet
console = logging.StreamHandler()
_formatConsole(gluster = False)

rootLogger = logging.getLogger()
rootLogger.setLevel(logging.DEBUG)
rootLogger.addHandler(console)

logger = logging.getLogger(__name__)

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
			logger.critical('%s is present but is a file (vs a directory). ' \
				'Please (re)move this file to prevent data loss', logdest)
			raise SystemExit
		
		self._mount()
			
		super().__init__(logdest + '/pyledriver-log', when='midnight')

		fmt = logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s')
		self.setFormatter(fmt)

	def _mount(self):
		if os.path.ismount(self._mountpoint):
			# NOTE: this assumes that the already-mounted device is the one intended
			logger.warning('Device already mounted at {}'.format(self._mountpoint))
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
			logger.critical(stderr)
			raise SystemExit
			
	def close(self):
		TimedRotatingFileHandler.close(self) # must close file stream before unmounting
		self._unmount()

# ...now activate gluster
gluster = GlusterFSHandler(
	server = '192.168.11.39',
	volume = 'pyledriver',
	mountpoint = '/mnt/glusterfs/pyledriver',
	options = 'backupvolfile-server=192.168.11.48'
)

_formatConsole(gluster = True)
rootLogger.addHandler(gluster)

# this should only be called at the end to clean up
def unmountGluster():
	rootLogger.removeHandler(gluster)
	_formatConsole(gluster = False)
