'''
Sets up root logger for whole program, including console, gluster, and gmail

Logger conventions
- CRITICAL: for things that cause crashes. only level with gmail
- ERROR: for things that cause startup/shutdown issues
- WARNING: for recoverable issues that may cause future problems
- INFO: state changes and sensor readings
- DEBUG: all extraneous crap
'''

import logging, os
from subprocess import run, PIPE, CalledProcessError
from logging.handlers import TimedRotatingFileHandler, SMTPHandler
from auxilary import mkdirSafe

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
			
		self.mountpoint = mountpoint
		self._server = server
		self._volume = volume
		self._options = options
		
		self._mount()
		
		logdest = mountpoint + '/logs'
		mkdirSafe(logdest, logger)
			
		super().__init__(logdest + '/pyledriver-log', when='midnight')

		fmt = logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s')
		self.setFormatter(fmt)

	def _mount(self):
		if os.path.ismount(self.mountpoint):
			# this assumes that the already-mounted device is the one intended
			logger.warning('Device already mounted at {}'.format(self.mountpoint))
		else:
			dst = self._server + ':/' + self._volume
			cmd = ['mount', '-t', 'glusterfs', dst, self.mountpoint]
			if self._options:
				cmd[1:1] = ['-o', self._options]
			self._run(cmd)
		self.isMounted = True
	
	def _unmount(self):
		self._run(['umount', self.mountpoint])
		self.isMounted = False
			
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
Init sequence (order is very essential)
'''
# 1) init console output (this will go to journald) and format as console only
console = logging.StreamHandler()
_formatConsole(gluster = False)

rootLogger = logging.getLogger()
rootLogger.setLevel(logging.DEBUG)
rootLogger.addHandler(console)

# 2) init the module level logger so we can log anything that happens as we build the other loggers
logger = logging.getLogger(__name__)

# 3) init glusterfs, any errors here will go to console output
from config import configFile
glusterConf = configFile['gluster']

if glusterConf['server'] != 'example.com':
	gluster = GlusterFSHandler(**glusterConf)
	rootLogger.addHandler(gluster)
	_formatConsole(gluster = True)
else:
	logger.error('Gluster not configured. Please update config/pyledriver.yaml')
	raise SystemExit

# 4) import gmail, this must come here as it uses loggers for some of its setup
from gmail import gmail, GmailHandler

# 5) init gmail handler
gmail = GmailHandler(gmail['username'], gmail['passwd'], gmail['recipientList'],
	'harrison4hegemon - critical error')
gmail.setLevel(logging.CRITICAL)
rootLogger.addHandler(gmail)

'''
Clean up
'''
def unmountGluster():
	try:
		rootLogger.removeHandler(gluster)
		_formatConsole(gluster = False)
	except NameError:
		pass
