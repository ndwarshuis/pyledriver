'''
Implementation of exception-aware threads, including a listener to be put in
the top-level thread
'''

import queue
from threading import Thread, Event

# Killswitch for exception queue listener. Pass this to top-level thread so it
# can be called as part of clean up code
excStopper = Event()

# queue to shuttle exceptions from children to top-level thread
_excQueue = queue.Queue()

def excChildListener():
	'''
	Queue listener to intercept exceptions thrown in child threads that are
	exception-aware
	'''
	while not excStopper.isSet():
		try:
			raise _excQueue.get(True)
			_excQueue.task_done()
		except queue.Empty:
			pass
	while 1:
		try:
			raise _excQueue.get(False)
			_excQueue.task_done()
		except queue.Empty:
			break

class ExceptionThread(Thread):
	'''
	Thread that passes exceptions to a queue, which is handled by
	excChildListener in top-level thread
	'''
	def __init__(self, group=None, target=None, name=None, args=(), kwargs=None, *, daemon=None):
		super().__init__(group, target, name, args, kwargs, daemon=daemon)
		self._queue = _excQueue

	def run(self):
		try:
			Thread.run(self)
		except BaseException as e:
			self._queue.put(e)

class async:
	'''
	Wraps any function in an exception-aware thread and starts the thread.
	Intended to be used as a decorator
	'''
	def __init__(self, daemon=False):
		self._daemon = daemon

	def __call__(self, f):
		def wrapper(*args, **kwargs):
			t = ExceptionThread(target=f, daemon=self._daemon, args=args, kwargs=kwargs)
			t.start()
		return wrapper
