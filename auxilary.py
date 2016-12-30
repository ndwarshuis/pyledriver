import time, psutil, yaml
from subprocess import check_output, DEVNULL, CalledProcessError
from threading import Thread, Event

class ConfigFile():
	def __init__(self, path):
		self._path = path
		with open(self._path, 'r') as f:
			self._dict = yaml.safe_load(f)

	def __getitem__(self, key):
		return self._dict[key]
	
	def __setitem__(self, key, value):
		self._dict[key] = value
		
	def sync(self):
		with open(self._path, 'w') as f:
			yaml.dump(self._dict, f, default_flow_style=False)

def freeBusyPath(path, logger=None):
	# check if any other processes are using file path
	# if found, politely ask them to exit, else nuke them
	
	# NOTE: fuser sends diagnostic info (eg filenames and modes...which we
	# don't want) to stderr. This is weird, but let's me route to /dev/null
	# so I don't have to parse it later
	try:
		stdout = check_output(['fuser', path], universal_newlines=True, stderr=DEVNULL)
	except CalledProcessError:
		logger.debug('%s not in use. Execution may continue', path)
	else:
		# assume stdout is one PID first
		try:
			processes = [psutil.Process(int(stdout))]
		
		# else assume we have multiple PIDs separated by arbitrary space
		except ValueError:
			processes = [psutil.Process(int(s)) for s in stdout.split()]

		for p in processes:
			if logger:
				logger.warning('%s in use by PID %s. Sending SIGTERM', path, p.pid)
			p.terminate()

		dead, alive = psutil.wait_procs(processes, timeout=10)
		
		for p in alive:
			if logger:
				logger.warning('Failed to terminate PID %s. Sending SIGKILL', p.pid)
			p.kill()

class async:
	def __init__(self, daemon=False):
		self._daemon = daemon
		
	def __call__(self, f):
		def wrapper(*args, **kwargs):
			t = Thread(target=f, daemon=self._daemon, args=args, kwargs=kwargs)
			t.start()
		return wrapper

class CountdownTimer(Thread):
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
