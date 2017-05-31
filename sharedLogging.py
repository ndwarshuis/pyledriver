import logging, os
from subprocess import run, PIPE, CalledProcessError
from logging.handlers import TimedRotatingFileHandler, SMTPHandler

'''
Logger conventions
- CRITICAL: for things that cause crashes. only level with gmail
- ERROR: for things that cause startup/shutdown issues
- WARNING: for recoverable issues that may cause future problems
- INFO: state changes and sensor readings
- DEBUG: all extraneous crap

Init order (very essential)
1) init console output (this will go to journald) and format as console only
2) init the module level logger so we can log anything that happens as we build
   the other loggers
3) mount glusterfs, any errors here will go to console output
4) once gluster is mounted, add to root logger and remove "console only" warning
   from console
5) import gmail, this must come here as it uses loggers for some of its setup
6) init gmail handler
'''

def _formatConsole(gluster = False):
	'''
	formats console output depending on whether we have gluster
	'''
	c = '' if gluster else '[CONSOLE ONLY] '
	fmt = logging.Formatter('[%(name)s] [%(levelname)s] ' + c + '%(message)s')
	console.setFormatter(fmt)	

class GlusterFSHandler(TimedRotatingFileHandler):
	'''
	Logic to mount timed rotating file within a gluster volume. Note that this
	class will mount itself automatically. Note that the actual filepaths for
		logging are hardcoded here
	'''
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
			logger.error('%s is present but is a file (vs a directory). ' \
				'Please (re)move this file to prevent data loss', logdest)
			raise SystemExit
		
		self._mount()
			
		super().__init__(logdest + '/pyledriver-log', when='midnight')

		fmt = logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s')
		self.setFormatter(fmt)

	def _mount(self):
		if os.path.ismount(self._mountpoint):
			# this assumes that the already-mounted device is the one intended
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
			stderr = e.stderr.decode('ascii').rstrip()
			logger.error(stderr)
			raise SystemExit
			
	def close(self):
		'''
		Close file and dismount (must be in this order). Called when
		'removeHandler' is invoked
		'''
		TimedRotatingFileHandler.close(self)
		self._unmount()

'''
Init sequence (see above)
'''
# 1
console = logging.StreamHandler()
_formatConsole(gluster = False)

rootLogger = logging.getLogger()
rootLogger.setLevel(logging.DEBUG)
rootLogger.addHandler(console)

# 2
logger = logging.getLogger(__name__)

# 3
gluster = GlusterFSHandler(
	server = '192.168.11.39',
	volume = 'pyledriver',
	mountpoint = '/mnt/glusterfs/pyledriver',
	options = 'backupvolfile-server=192.168.11.48'
)

# 4
_formatConsole(gluster = True)
rootLogger.addHandler(gluster)

# 5
from gmail import gmail, GmailHandler

# 6
gmail = GmailHandler(gmail['username'], gmail['passwd'], gmail['recipientList'],
	'harrison4hegemon - critical error')
gmail.setLevel(logging.CRITICAL)
rootLogger.addHandler(gmail)

'''
Clean up
'''
def unmountGluster():
	rootLogger.removeHandler(gluster)
	_formatConsole(gluster = False)
