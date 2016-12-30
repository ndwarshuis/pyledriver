import cv2, time
from threading import RLock
from sharedLogging import SlaveLogger
from auxilary import freeBusyPath

class Camera:
	def __init__(self, queue):
		self._lock = RLock()
		self._index = 0
		self._logger = SlaveLogger(__name__, 'DEBUG', queue)
		
		freeBusyPath('/dev/video{}'.format(self._index), self._logger)

		# NOTE: we use 0-255 on forms instead of floats because they look nicer
		logitechProperties = {
			'FPS': 25,				# integer from 10 to 30 in multiples of 5
			'BRIGHTNESS': 127/255,	# float from 0 to 1
			'CONTRAST': 32/255,		# float from 0 to 1
			'SATURATION': 32/255,	# float from 0 to 1
			'GAIN': 64/255,			# float from 0 to 1
		}
		self._properties = {}
		self.setProps(**logitechProperties)
		
	def getProps(self, *args):
		return {prop: self._video.get(getattr(cv2, 'CAP_PROP_' + prop)) for prop in args}

	def setProps(self, *args, **kwargs):
		# silly hack, need to reset the videoCapture object every time
		# we change settings (they can only be changed once apparently)
		self._lock.acquire()
		try:
			if hasattr(self, '_video'):
				self._video.release()
			
			self._video = cv2.VideoCapture(self._index)
			
			for prop, val in kwargs.items():
				self._properties[prop] = val
				self._video.set(getattr(cv2, 'CAP_PROP_' + prop), val)
				self._logger.debug('set %s to %s', prop, val)
		finally:
			self._lock.release()

	# the reset code here could be put in seperate thread to accellarate
	def getFrame(self):
		frame = None
		self._lock.acquire()
		try:
			# will try 3 attempts to grab frame, will reset on failure
			i = 3
			while i > 0:
				if self._video.isOpened():
					success, image = self._video.read()
					ret, jpeg = cv2.imencode('.jpg', image)
					frame = jpeg.tobytes()
					break
				else:
					time.sleep(5)
					self.reset()
					i -= 1
			
			# after 3 fails return the dummy frame
			if not frame:
				with open('noimage.jpg', 'rb') as f:
					time.sleep(1)
					frame = f.read()
		finally:
			self._lock.release()

		return frame

	def reset(self):
		self.setProps(**self._properties)
		self._logger.debug('camera reset')

	def __del__(self):
		try:
			self._video.release()
			self._logger.debug('Release camera at index %s', self._index)
		except AttributeError:
			self._logger.debug('Failed to release camera at index %s', self._index)
