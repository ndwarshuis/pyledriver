"""
this entire module is lovingly based on the gst-launch tool kindly provided
by the gstreamer wizards themselves...with unecessary crap cut out

we make the following assumptions here and optimize as such
- all streams are "live"
- will not need EOS (no mp4s)
- will not require SIGINT (this entire program won't understand them anyways)
- no tags or TOCs

From a logging an error handling standpoint, all 'errors' here are logged as
'critical' which will shut down the entire program and send an email.
"""

import gi, time, os, logging
from datetime import datetime
from threading import Lock, Event

from auxilary import waitForPath, mkdirSafe
from exceptionThreading import async
from sharedLogging import gluster

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

gi.require_version('Gst', '1.0')
gi.require_version('GObject', '2.0')

from gi.repository import Gst, GObject

class GstException(Exception):
	pass

def _gstPrintMsg(pName, frmt, *args, level=logging.DEBUG, sName=None):
	if sName:
		logger.log(level, '[{}] [{}] '.format(pName, sName) + frmt.format(*args))
	else:
		logger.log(level, '[{}] '.format(pName) + frmt.format(*args))
	if level == logging.ERROR:
		raise GstException
	
def _processErrorMessage(pName, sName, msg):
	error, debug = msg.parse_error()
	if debug:
		_gstPrintMsg(pName, '{} - Additional debug info: {}', error.message, debug,
			level=logging.ERROR, sName=sName)
	else:
		_gstPrintMsg(pName, error.message, level=logging.ERROR, sName=sName)

def _linkElements(e1, e2, caps=None):
	if caps:
		if not e1.link_filtered(e2, caps):
			logger.error('cannot link \"%s\" to \"%s\" with caps %s',
				e1.get_name(), e2.get_name(), caps.to_string())
			raise SystemExit
	else:
		if not e1.link(e2):
			logger.error('cannot link \%s\" to \"%s\"', e1.get_name(), e2.get_name())
			raise SystemExit

class ThreadedPipeline:
	'''
	Launches a Gst Pipeline in a separate thread. Note that the 'threaded'
	aspect is impimented via and async decorator around the mainLoop below
	'''
	def __init__(self, pName):
		self._pipeline = Gst.Pipeline.new(pName)
		self._stopper = Event()
		
	def start(self, play=True):
		pName = self._pipeline.get_name()
		stateChange = self._pipeline.set_state(Gst.State.PAUSED)
		_gstPrintMsg(pName, 'Setting to PAUSED', level=logging.INFO)
		
		if stateChange == Gst.StateChangeReturn.FAILURE:
			_gstPrintMsg(pName, 'Cannot set to PAUSE', level=logging.INFO)
			self._eventLoop(block=False, doProgress=False, targetState=Gst.State.VOID_PENDING)
		# we should always end up here because live
		elif stateChange == Gst.StateChangeReturn.NO_PREROLL:
			_gstPrintMsg(pName, 'Live and does not need preroll')
		elif stateChange == Gst.StateChangeReturn.ASYNC:
			_gstPrintMsg(pName, 'Prerolling')
			try:
				_eventLoop(block=True, doProgress=True, targetState=Gst.State.PAUSED)
			except GstException:
				_gstPrintMsg(pName, 'Does not want to preroll', level=logging.ERROR)
				raise SystemExit
		elif stateChange == Gst.StateChangeReturn.SUCCESS:
			_gstPrintMsg(pName, 'Is prerolled')
		
		# this should always succeed...
		try:
			self._eventLoop(block=False, doProgress=True, targetState=Gst.State.PLAYING)
		except GstException:
			_gstPrintMsg(pName, 'Does not want to preroll', level=logging.ERROR)
			raise SystemExit
		# ...and end up here
		else:
			if play:
				_gstPrintMsg(pName, 'Setting to PLAYING', level=logging.INFO)
			
				# ...and since this will ALWAYS be successful...
				if self._pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
					_gstPrintMsg(pName, 'Cannot set to PLAYING', level=logging.ERROR)
					err = self._pipeline.get_bus().pop_filtered(Gst.MessageType.Error)
					_processErrorMessage(pName, msgSrcName, err)
			
			# ...we end up here and loop until Tool releases their next album
			try:
				self._mainLoop()
			except:
				raise GstException
	
	# TODO: this might not all be necessary
	def stop(self):
		self._stopper.set()
		self._pipeline.set_state(Gst.State.NULL)
		logger.debug('Shut down gstreamer pipeline: %s', self._pipeline.get_name())
		
	def __del__(self):
		self.stop()
		
	# TODO: make it clearer which pipeline everything comes from
	def _eventLoop(self, block=True, doProgress=False, targetState=Gst.State.PLAYING):
		'''
		This is the main loop that processes information on the bus and decides
		how the pipeline should react. Sometimes this entails spitting out
		messages, others it involves changing state or some other manipulation.
		'''
		buffering = False
		inProgress = False
		prerolled = targetState != Gst.State.PAUSED
		
		pName = self._pipeline.get_name()
		bus = self._pipeline.get_bus()
		
		while not self._stopper.isSet():
			# TODO: if we actually want to stop the pipeline asyncronously we
			# need to post a message on the bus that tells it to stop. Otherwise
			# it will wait here forever (or will be terminated as a daemon
			# thread by its parent)
			msg = bus.timed_pop(1e18 if block else 0)

			if not msg:
				return
				
			msgSrc = msg.src
			msgSrcName = msgSrc.get_name()
			
			msgType = msg.type
			msgTypeName = Gst.MessageType.get_name(msgType)

			# messages that involve manipulating the pipeline
			if msgType == Gst.MessageType.REQUEST_STATE:
				state = msg.parse_request_state()

				logger.info('Setting state to %s as requested by %s',
					state.value_name, msgSrcName)
				
				self._pipeline.set_state(state)
				
			elif msgType == Gst.MessageType.CLOCK_LOST:
				logger.debug('Clock lost. Getting new one.')
				self._pipeline.set_state(Gst.State.PAUSED)
				self._pipeline.set_state(Gst.State.PLAYING)
				
			elif msgType == Gst.MessageType.LATENCY:
				_gstPrintMsg(pName, 'Redistributing latency', sName=msgSrcName)
				self._pipeline.recalculate_latency()
			
			# messages that do not require pipeline manipulation	
			elif msgType == Gst.MessageType.BUFFERING:
				_gstPrintMsg(pName, 'Buffering: {}', msg.parse_buffering(), sName=msgSrcName)
				
			elif msgType == Gst.MessageType.NEW_CLOCK:
				clock = msg.parse_new_clock()
				clock = clock.get_name() if clock else 'NULL'
				_gstPrintMsg(pName, 'New clock: {}', clock)
				
			elif msgType == Gst.MessageType.INFO:
				error, debug = msg.parse_info()
				
				if debug:
					_gstPrintMsg(pName, debug, level=logging.INFO, sName=msgSrcName)
					
			elif msgType == Gst.MessageType.WARNING:
				error, debug = msg.parse_warning()
				
				if debug:
					_gstPrintMsg(pName, '{} - Additional debug info: {}', error.message,
						debug, level=logging.WARNING, sName=msgSrcName)
				else:
					_gstPrintMsg(pName, error.message, level=logging.WARNING, sName=msgSrcName)
				
			elif msgType == Gst.MessageType.ERROR:
				_processErrorMessage(pName, msgSrcName, msg)
				
			elif msgType == Gst.MessageType.STATE_CHANGED:
				# we only care about pipeline level state changes
				if msgSrc == self._pipeline:
					old, new, pending = msg.parse_state_changed()
					
					# we only care if we reach the final target state
					if targetState == Gst.State.PAUSED and new == Gst.State.PAUSED:
						prerolled = True
						
						if buffering:
							_gstPrintMsg(pName, 'Prerolled, waiting for buffering to finish',
								level=logging.INFO)
							continue
							
						if inProgress:
							_gstPrintMsg(pName, 'Prerolled, waiting for progress to finish',
								level=logging.INFO)
							continue
							
						return
			
			elif msgType == Gst.MessageType.PROGRESS:
				progressType, code, text = msg.parse_progress()
				
				if (progressType == Gst.ProgressType.START or 
				  progressType == Gst.ProgressType.CONTINUE):
					if doProgress:
						inProgress = True
						block = True
				elif (progressType == Gst.ProgressType.COMPLETE or 
				  progressType == Gst.ProgressType.CANCELLED or 
				  progressType == Gst.ProgressType.ERROR):
					inProgress = False
				
				_gstPrintMsg(pName, 'Progress: ({}) {}', code, text, sName=msgSrcName)
				
				if doProgress and not inProgress and not buffering and prerolled:
					return					

			elif msgType == Gst.MessageType.HAVE_CONTEXT:
				context = msg.parse_have_context()
				_gstPrintMsg(
					pName,
					'Got context: {}={}',
					context.get_context_type(),
					context.get_structure().to_string(),
					sName = msgSrcName
				)

			elif msgType == Gst.MessageType.PROPERTY_NOTIFY:
				obj, propName, val = msg.parse_property_notify()
				
				valStr = '(no value)'
				
				if val:
					if GObject.type_check_value_holds(val, GObject.TYPE_STRING):
						valStr = val.dup_string()
						
					elif val.g_type.is_a(Gst.Caps.__gtype__):
						valStr = val.get_boxed().to_string()
						
					else: 
						valStr = Gst.value_serialize(val)
					
				_gstPrintMsg(pName, '{}: {} = {}', obj.get_name(), propName,
					valStr, sName=msgSrcName)
				
			# these are things I might not need...
			elif msgType == Gst.MessageType.STREAM_START:
				if msgSrc == self._pipeline:
					_gstPrintMsg(pName, 'Started stream', level=logging.INFO)

			elif msgType == Gst.MessageType.QOS:
				frmt, processed, dropped = msg.parse_qos_stats()
				jitter, proportion, quality = msg.parse_qos_values()

				_gstPrintMsg(
					pName,
					'QOS stats: jitter={} dropped={}',
					jitter,
					'-' if frmt == Gst.Format.UNDEFINED else dropped,
					sName = msgSrcName
				)
					
			elif msgType == Gst.MessageType.ELEMENT:
				_gstPrintMsg(pName, 'Unknown message ELEMENT', sName=msgSrcName)

			elif msgType == Gst.MessageType.UNKNOWN:
				_gstPrintMsg(pName, 'Unknown message', sName=msgSrcname)
		
	@async(daemon=True)
	def _mainLoop(self):
		self._eventLoop(block=True, doProgress=False, targetState=Gst.State.PLAYING)

class Camera(ThreadedPipeline):
	'''
	Class for usb camera. The 'video' and 'audio' flags are meant for testing.
	
	Makes two independent stream that share the same pipeline, and thus share a
	clock for syncronization. Video uses the hardware-accelarated OMX extensions
	for H264 encoding. Audio has no hardware accelaration (and thus is likely
	the most resource hungry thing in this program) and encodes using Opus. Both
	send their stream to two UDP ports (900X for video, 800X for audio, where 
	X = 1 is used by the Janus WebRTC interface and X = 2 is used by the
	FileDump class below.
	'''
	_vPath = '/dev/video0'
	_aPath = 'hw:1,0'
	
	def __init__(self, video=True, audio=True):
		super().__init__('camera')
		
		if video:
			vSource = Gst.ElementFactory.make("v4l2src", "videoSource")
			vConvert = Gst.ElementFactory.make("videoconvert", "videoConvert")
			vScale = Gst.ElementFactory.make("videoscale", "videoScale")
			vClock = Gst.ElementFactory.make("clockoverlay", "videoClock")
			vEncode = Gst.ElementFactory.make("omxh264enc", "videoEncoder")
			vRTPPay = Gst.ElementFactory.make("rtph264pay", "videoRTPPayload")
			vRTPSink = Gst.ElementFactory.make("multiudpsink", "videoRTPSink")
		
			vSource.set_property('device', self._vPath)
			vRTPPay.set_property('config-interval', 1)
			vRTPPay.set_property('pt', 96)
			vRTPSink.set_property('clients', '127.0.0.1:9001,127.0.0.1:9002')
		
			vCaps = Gst.Caps.from_string('video/x-raw,width=640,height=480,framerate=30/1')
			
			self._pipeline.add(vSource, vConvert, vScale, vClock, vEncode, vRTPPay, vRTPSink)
			
			_linkElements(vSource, vConvert)
			_linkElements(vConvert, vScale)
			_linkElements(vScale, vClock, vCaps)
			_linkElements(vClock, vEncode)
			_linkElements(vEncode, vRTPPay)
			_linkElements(vRTPPay, vRTPSink)
		
		if audio:
			aSource = Gst.ElementFactory.make("alsasrc", "audioSource")
			aConvert = Gst.ElementFactory.make("audioconvert", "audioConvert")
			aScale = Gst.ElementFactory.make("audioresample", "audioResample")
			aEncode = Gst.ElementFactory.make("opusenc", "audioEncode")
			aRTPPay = Gst.ElementFactory.make("rtpopuspay", "audioRTPPayload")
			aRTPSink = Gst.ElementFactory.make("multiudpsink", "audioRTPSink")

			aSource.set_property('device', self._aPath)
			aRTPSink.set_property('clients', '127.0.0.1:8001,127.0.0.1:8002')

			aCaps = Gst.Caps.from_string('audio/x-raw,rate=48000,channels=1')

			self._pipeline.add(aSource, aConvert, aScale, aEncode, aRTPPay, aRTPSink)

			_linkElements(aSource, aConvert)
			_linkElements(aConvert, aScale)
			_linkElements(aScale, aEncode, aCaps)
			_linkElements(aEncode, aRTPPay)
			_linkElements(aRTPPay, aRTPSink)
			
	def start(self):
		# video is on usb, so wait until it comes back after we hard reset the bus
		waitForPath(self._vPath)
		ThreadedPipeline.start(self, play=False)
		
class FileDump(ThreadedPipeline):
	'''
	Pipeline that takes audio and input from two udp ports, muxes them, and
	dumps the result to a file. Intended to work with the Camera above. Will
	init to a paused state, then will transition to a playing state (which will
	dump the file) when at least one initiator registers with the class.
	
	Initiators are represented by unique identifiers held in a list. The current
	use case is that each identifier is for the pin of the IR sensor that
	detects motion, and thus adding a pin number to the list signifies that
	video/audio should be recorded
	'''
	def __init__(self):
		self._initiators = []
		self._lock = Lock()
		
		if not gluster.isMounted:
			logger.error('Attempting to init FileDump without gluster mounted. Aborting')
			raise SystemExit
			
		self._savePath = os.path.join(gluster.mountpoint, 'video')

		mkdirSafe(self._savePath, logger)

		super().__init__('filedump')
		
		aSource = Gst.ElementFactory.make('udpsrc', 'audioSource')
		aJitBuf = Gst.ElementFactory.make('rtpjitterbuffer', 'audioJitterBuffer')
		aDepay = Gst.ElementFactory.make('rtpopusdepay', 'audioDepay')
		aQueue = Gst.ElementFactory.make('queue', 'audioQueue')
		
		aCaps = Gst.Caps.from_string('application/x-rtp,encoding-name=OPUS,payload=96')
		
		vSource = Gst.ElementFactory.make('udpsrc', 'videoSource')
		vJitBuf = Gst.ElementFactory.make('rtpjitterbuffer', 'videoJitterBuffer')
		vDepay = Gst.ElementFactory.make('rtph264depay', 'videoDepay')
		vParse = Gst.ElementFactory.make('h264parse', 'videoParse')
		vQueue = Gst.ElementFactory.make('queue', 'videoQueue')
		
		vCaps = Gst.Caps.from_string('application/x-rtp,encoding-name=H264,payload=96')
		
		mux = Gst.ElementFactory.make('matroskamux', 'mux')
		
		self.sink = Gst.ElementFactory.make('filesink', 'sink')
		self.sink.set_property('location', '/dev/null')
		
		aSource.set_property('port', 8002)
		vSource.set_property('port', 9002)
		
		self._pipeline.add(aSource, aJitBuf, aDepay, aQueue,
			vSource, vJitBuf, vDepay, vParse, vQueue, mux, self.sink)
	
		_linkElements(aSource, aJitBuf, aCaps)
		_linkElements(aJitBuf, aDepay)
		_linkElements(aDepay, aQueue)
		_linkElements(aQueue, mux)
		
		_linkElements(vSource, vJitBuf, vCaps)
		_linkElements(vJitBuf, vDepay)
		_linkElements(vDepay, vParse)
		_linkElements(vParse, vQueue)
		_linkElements(vQueue, mux)
		
		_linkElements(mux, self.sink)
	
	def start(self):
		# TODO: there is probably a better way to init than starting up to PAUSE
		# and then dropping back down to NULL
		ThreadedPipeline.start(self, play=False)
		self._pipeline.post_message(Gst.Message.new_request_state(self._pipeline, Gst.State.NULL))
		
	def addInitiator(self, identifier):
		with self._lock:
			if identifier in self._initiators:
				logger.warn('Identifier \'%s\' already in FileDump initiator list', identifier)
			else:
				self._initiators.append(identifier)
				
			if self._pipeline.get_state(Gst.CLOCK_TIME_NONE).state == Gst.State.NULL:
				filePath = os.path.join(self._savePath, '{}.mkv'.format(datetime.now()))
				self.sink.set_property('location', filePath)
				# TODO: cannot post messages from null to change state, is this bad?
				self._pipeline.set_state(Gst.State.PLAYING)
		
	def removeInitiator(self, identifier):
		with self._lock:
			try:
				self._initiators.remove(identifier)
			except ValueError:
				logger.warn('Attempted to remove nonexistant identifier \'%s\'', identifier)
				
			if len(self._initiators) == 0:
				self._pipeline.set_state(Gst.State.NULL)
		
Gst.init(None)
