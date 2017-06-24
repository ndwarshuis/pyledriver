'''
Implements all sound functionality
'''
import logging, os, hashlib, queue, time, psutil
from threading import Event, RLock
from exceptionThreading import ExceptionThread, async
from pygame import mixer
from subprocess import call
from collections import OrderedDict

logger = logging.getLogger(__name__)

class SoundEffect(mixer.Sound):
	'''
	Represents one discrete sound effect that can be called and played at will.
	The clas wraps a mixer.Sound object which maps to one sound file on the
	disk. In addition, it implements volume and/or loops. The former sets the
	volume permanently (independent of the user-set volume) and the latter
	defines how many times to play once called. Both are optional.
	'''
	def __init__(self, path, volume=None, loops=0):
		super().__init__(path)
		self.path = path
		self.volume = volume
		if volume:
			self.set_volume(volume)
		self.loops = loops
		
	def play(self, loops=None):
		loops = loops if loops else self.loops
		mixer.Sound.play(self, loops=loops)
	
	def set_volume(self, volume, force=False):
		# Note: force only intended to be used by fader
		if not self.volume or force:
			mixer.Sound.set_volume(self, volume)

class TTSSound(SoundEffect):
	'''
	Special case of a SoundEffect wherein the sound is a speech file dynamically
	created	by espeak and stored in tmp.
	'''
	def __init__(self, path):
		super().__init__(path, volume=1.0, loops=0)
		self.size = os.path.getsize(path)

	def __del__(self):
		if os.path.exists(self.path):
			os.remove(self.path)

class TTSCache(OrderedDict):
	'''
	Manages a list of all TTSSounds stored in tmp, and remembers the order files
	have been added. Amount of data shall not exceed memLimit; once memLimit is 
	exceeded, files will be removed in FIFO manner
	'''
	def __init__(self, memLimit):
		super().__init__()
		self._memLimit = memLimit
		self._memUsed = 0
	
	def __setitem__(self, key, value):
		if type(value) != TTSSound:
			raise TypeError
		OrderedDict.__setitem__(self, key, value)
		self._memUsed += value.size
		self._maintainMemLimit()
		
	def __delitem__(self, key):
		self._memUsed -= self[key].size
		OrderedDict.__delitem__(self, key)
		
	def clear(self):
		logger.debug('Clearing TTS Cache')
		OrderedDict.clear(self)
		self._memUsed = 0
	
	def _maintainMemLimit(self):
		while self._memUsed > self._memLimit:
			OrderedDict.popitem(self, last=False)

class SoundLib:
	'''
	Main wrapper for pygame.mixer, including methods for changing overall
	volume, handling TTS, and hlding the soundfx table for importation
	elsewhere. Note that the TTS listener is started as a separate thread,
	and speech bits are sent to be prcoess with a queue (which is to be passed
	to other threads)
	'''
	
	_sentinel = None
	
	def __init__(self):
		mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=1024)
		mixer.init()
		
		self.soundEffects = {
			'disarmed':				SoundEffect(path='soundfx/smb_pause.wav'),
			'armedCountdown':		SoundEffect(path='soundfx/smb_kick.wav'),
			'armed':				SoundEffect(path='soundfx/smb_powerup.wav'),
			'lockedCountdown':		SoundEffect(path='soundfx/smb_stomp.wav'),
			'locked':				SoundEffect(path='soundfx/smb_1-up.wav'),
			'trippedCountdown':		SoundEffect(path='soundfx/smb2_door_appears.wav'),
			'tripped':				SoundEffect(path='soundfx/alarms/burgler_alarm.ogg', volume=1.0, loops=-1),
			'door':					SoundEffect(path='soundfx/smb_pipe.wav'),
			'numKey':				SoundEffect(path='soundfx/smb_bump.wav'),
			'ctrlKey':				SoundEffect(path='soundfx/smb_fireball.wav'),
			'wrongPass':			SoundEffect(path='soundfx/smb_fireworks.wav'),
			'backspace':			SoundEffect(path='soundfx/smb_breakblock.wav'),
		}

		self._ttsSounds = TTSCache(psutil.virtual_memory().total * 0.001)
		self._lock = RLock()
		
		self.volume = 100
		self._applyVolumesToSounds(self.volume)
		
		self._ttsQueue = queue.Queue()
		self._stopper = Event()

	def start(self):
		self._startMonitor()
		
	def stop(self):
		self._stopMonitor()
		self._ttsSounds.clear()
		# this sometimes casues "Fatal Python error: (pygame parachute) Segmentation Fault"
		mixer.quit()

	def changeVolume(self, volumeDelta):
		newVolume = self.volume + volumeDelta
		if newVolume >= 0 and newVolume <= 100:
			self._applyVolumesToSounds(newVolume)
	
	def mute(self):
		self._applyVolumesToSounds(0)
	
	def speak(self, text):
		self._ttsQueue.put_nowait(text)
		
	@async(daemon=False)
	def _fader(self, lowerVolume, totalDuration, fadeDuration=0.2, stepSize=5):
		with self._lock:
			alarm = self.soundEffects['tripped']
			alarmVolume = alarm.volume
			alarmVolumeDelta = alarmVolume - lowerVolume
			
			masterVolume = self.volume
			masterVolumeDelta = self.volume - lowerVolume
			
			sleepFadeTime = fadeDuration / stepSize
			
			for i in range(0, stepSize):
				if alarmVolumeDelta > 0:
					alarm.set_volume(alarmVolume - alarmVolumeDelta * i / stepSize, force=True)
					
				if masterVolumeDelta > 0:
					self._applyVolumesToSounds(masterVolume - masterVolumeDelta * i / stepSize)
				
				time.sleep(sleepFadeTime)
				
			time.sleep(totalDuration - 2 * fadeDuration)
			
			for i in range(stepSize - 1, -1, -1):
				if alarmVolumeDelta > 0:
					alarm.set_volume(alarmVolume - alarmVolumeDelta * i / stepSize, force=True)
					
				if masterVolumeDelta > 0:
					self._applyVolumesToSounds(masterVolume - masterVolumeDelta * i / stepSize)
				
				time.sleep(sleepFadeTime)
	
	# will not change sounds that have preset volume
	def _applyVolumesToSounds(self, volume):
		with self._lock:
			self.volume = volume
			v = volume/100
			s = self.soundEffects
			for name, sound in s.items():
				sound.set_volume(v)

	def _ttsMonitor(self):
		q = self._ttsQueue
		while not self._stopper.isSet():
			try:
				text = self._ttsQueue.get(True)
				if text is self._sentinel:
					break
				self._playSpeech(text)
				q.task_done()
			except queue.Empty:
				pass
		# There might still be records in the queue.
		while 1:
			try:
				text = self._ttsQueue.get(False)
				if text is self._sentinel:
					break
				self._playSpeech(text)
				q.task_done()
			except queue.Empty:
				break

	def _playSpeech(self, text):
		basename = hashlib.md5(text.encode()).hexdigest()

		if basename in self._ttsSounds:
			self._ttsSounds.move_to_end(basename)
		else:
			path = '/tmp/' + basename
			call(['espeak', '-a180', '-g8', '-p75', '-w', path, text])
			self._ttsSounds[basename] = TTSSound(path)

		self._fader(
			lowerVolume=0.1,
			totalDuration=self._ttsSounds[basename].get_length()
		)
		self._ttsSounds[basename].play()
		logger.debug('TTS engine received "%s"', text)
		
	def _startMonitor(self):
		self._thread = t = ExceptionThread(target=self._ttsMonitor, daemon=True)
		t.start()
		logger.debug('Starting TTS Queue Monitor')
					
	def _stopMonitor(self):
		self._stopper.set()
		self._ttsQueue.put_nowait(self._sentinel)
		try:
			self._thread.join()
			self._thread = None
		except AttributeError:
			pass
		logger.debug('Stopping TTS Queue Monitor')

	def __del__(self):
		self.stop()
