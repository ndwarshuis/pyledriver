'''
Presents an interface for yaml files as a dict-like object
'''

import yaml
from threading import Lock

class _ConfigFile():
	def __init__(self, path):
		self._path = path
		self._lock = Lock()
		with open(self._path, 'r') as f:
			self._dict = yaml.safe_load(f)

	def __getitem__(self, key):
		return self._dict[key]
	
	def __setitem__(self, key, value):
		with self._lock:
			self._dict[key] = value
			self._sync()
		
	def _sync(self):
		with open(self._path, 'w') as f:
			yaml.dump(self._dict, f, default_flow_style=False)

configFile = _ConfigFile('config.yaml')
