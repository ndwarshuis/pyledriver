import logging, os, hashlib, queue, time, psutil
from threading import Event
from exceptionThreading import ExceptionThread, async
from pygame import mixer
from subprocess import call
from collections import OrderedDict

logger = logging.getLogger(__name__)

# TODO: figure out why we have buffer underruns
# TODO: why does the mixer segfault? (at least I think that's the cuprit)

class SoundEffect(mixer.Sound):
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
	def __init__(self, path):
		super().__init__(path, volume=1.0, loops=0)
		self.size = os.path.getsize(path)

	def __del__(self):
		if os.path.exists(self.path):
			os.remove(self.path)

class TTSCache(OrderedDict):
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
	
	_sentinel = None
	
	def __init__(self):
		mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=1024)
		mixer.init()
		
		self.soundEffects = {
			'disarmedCountdown':	SoundEffect(path='soundfx/smb_coin.wav'),
			'disarmed':				SoundEffect(path='soundfx/smb_pause.wav'),
			'armed':				SoundEffect(path='soundfx/smb_powerup.wav'),
			'armedCountdown':		SoundEffect(path='soundfx/smb_jump-small.wav'),
			'triggered':			SoundEffect(path='soundfx/alarms/burgler_alarm.ogg', volume=1.0, loops=-1),
			'door':					SoundEffect(path='soundfx/smb_pipe.wav'),
			'numKey':				SoundEffect(path='soundfx/smb_bump.wav'),
			'ctrlKey':				SoundEffect(path='soundfx/smb_fireball.wav'),
			'wrongPass':			SoundEffect(path='soundfx/smb_fireworks.wav'),
			'backspace':			SoundEffect(path='soundfx/smb_breakblock.wav'),
		}

		self._ttsSounds = TTSCache(psutil.virtual_memory().total * 0.001)
		
		self.volume = 100
		self._applyVolumesToSounds(self.volume)
		
		self._ttsQueue = queue.Queue()
		self._stop = Event()
		self._startMonitor()

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
		alarm = self.soundEffects['triggered']
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
		self.volume = volume
		v = volume/100
		s = self.soundEffects
		for name, sound in s.items():
			sound.set_volume(v)

	# TODO: maybe could simply now that we are not using MP for TTS
	def _ttsMonitor(self):
		q = self._ttsQueue
		has_task_done = hasattr(q, 'task_done')
		while not self._stop.isSet():
			try:
				text = self._ttsQueue.get(True)
				if text is self._sentinel:
					break
				self._playSpeech(text)
				if has_task_done:
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
				if has_task_done:
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
		self._stop.set()
		self._ttsQueue.put_nowait(self._sentinel)
		self._thread.join()
		self._thread = None
		logger.debug('Stopping TTS Queue Monitor')

	def __del__(self):
		mixer.quit()
		self._stopMonitor()
		self._ttsSounds.clear()
