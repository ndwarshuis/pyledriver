'''
Presents an interface for yaml files as a dict-like object
'''

import yaml, shutil, logging
from threading import Lock

logger = logging.getLogger(__name__)

class _ReadOnlyFile():
	'''
	Opens a yaml file for reading. Intended for config files.
	'''
	def __init__(self, path):
		self._path = path
		with open(self._path, 'r') as f:
			self._dict = yaml.safe_load(f)

	def __getitem__(self, key):
		return self._dict[key]
	
class _ReadWriteFile(_ReadOnlyFile):
	'''
	Same as above but adds write functionality. Intended for files that retain
	program state so that it may return to the same state when recovering from
	a crash (eg someone can't crash the system to disarm it)
	'''
	def __init__(self, path):
		super().__init__(path)
		self._lock = Lock()
		
	def __setitem__(self, key, value):
		with self._lock:
			self._dict[key] = value
			with open(self._path, 'w') as f:
				yaml.dump(self._dict, f, default_flow_style=False)

def _openFile(cls, path):
	try:
		return cls(path)
	except:
		logger.warn('File %s not found. Copying example', path)
		shutil.copy(path + '.default', path)
		return cls(path)

configFile = _openFile(_ReadOnlyFile, 'config/pyledriver.yaml')
stateFile = _openFile(_ReadWriteFile, 'config/state.yaml')
