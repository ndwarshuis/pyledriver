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
		try:
			self._load()
		except FileNotFoundError:
			logger.warn('File %s not found. Attempting to copy example', self._path)
			defaultPath = self._path + '.default'
			
			try:
				shutil.copy(defaultPath, self._path)
			except FileNotFoundError:
				logger.error('Example file %s not found', defaultPath)
				raise SystemExit
				
			self._path = defaultPath
			self._load()
		except yaml.parser.ParserError as e:
			logger.error(e)
			raise SystemExit
			
	def __getitem__(self, key):
		return self._dict[key]
		
	def _load(self):
		with open(self._path, 'r') as f:
			self._dict = yaml.safe_load(f)
	
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

configFile = _ReadOnlyFile('config/pyledriver.yaml')
stateFile = _ReadWriteFile('config/state.yaml')
