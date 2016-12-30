import pyaudio

CHUNK = 4096

class Microphone:
	def __init__(self):
		print('aloha bra')
		self._pa = pyaudio.PyAudio()

		self._stream = self._pa.open(
			format = pyaudio.paInt16,
			channels = 1,
			rate = 48000,
			input = True,
			frames_per_buffer = CHUNK
		)
		
	def getFrame(self):
		frame = self._stream.read(CHUNK)
		print(len(frame))
		return frame
		
	def __del__(self):
		try:
			self._stream.stop_stream()
			self._stream.close()
		except AttributeError:
			pass
			
		try:
			self._pa.terminate()
		except AttributeError:
			pass
