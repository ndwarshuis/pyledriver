import time, psutil, yaml, os
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
		
def waitForPath(path, logger=None, timeout=30):
	for i in range(0, timeout):
		if os.path.exists(path):
			return
		time.sleep(1)
	if logger:
		logger.error('Could not find %s after %s seconds', path, timeout)
	raise SystemExit

# crude way to reset USB device, pretty rough but works
def resetUSBDevice(device):
	devpath = os.path.join('/sys/bus/usb/devices/' + device + '/authorized')
	with open(devpath, 'w') as f:
		f.write('0')
	with open(devpath, 'w') as f:
		f.write('1')
