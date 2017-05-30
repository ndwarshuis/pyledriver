#! /bin/python

# this entire module is lovingly based on the gst-launch tool kindly provided
# by the gstreamer wizards themselves...with unecessary crap cut out

# we make the following assumptions here and optimize as such
# - all streams are "live"
# - will not need EOS (no mp4s)
# - will not require SIGINT (this entire program won't understand them anyways)
# - no tags or TOCs

from auxilary import async, waitForPath
from threading import Thread

import gi, time, logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

gi.require_version('Gst', '1.0')
gi.require_version('GObject', '2.0')

from gi.repository import Gst, GObject

class GstException(Exception):
	pass
	
def gstPrintMsg(pName, frmt, *args, level=logging.DEBUG, sName=None):
	if sName:
		logger.log(level, '[{}] [{}] '.format(pName, sName) + frmt.format(*args))
	else:
		logger.log(level, '[{}] '.format(pName) + frmt.format(*args))
	
def processErrorMessage(pName, sName, msg, level=logging.DEBUG):
	error, debug = msg.parse_error()
	if debug:
		gstPrintMsg(pName, '{} - Additional debug info: {}', error.message, debug, level=level, sName=sName)
	else:
		gstPrintMsg(pName, error.message, level=level, sName=sName)
	raise GstException(error)
	
def linkElements(e1, e2, caps=None):
	if caps:
		if not e1.link_filtered(e2, caps):
			raise GstException('cannot link \"{}\" to \"{}\" with caps {}'.format(e1.get_name(), e2.get_name(), caps.to_string()))
	else:
		if not e1.link(e2):
			raise GstException('cannot link \"{}\" to \"{}\"'.format(e1.get_name(), e2.get_name()))

def linkTee(tee, *args):
	i = 0
	for e in args:
		teePad = tee.get_request_pad('src_{}'.format(i))
		ePad  = e.get_static_pad('sink')
		teePad.link(ePad)
		i += 1

# TODO: make it clearer which pipeline everything comes from
def eventLoop(pipeline, block=True, doProgress=False, targetState=Gst.State.PLAYING):
	buffering = False
	inProgress = False
	prerolled = targetState != Gst.State.PAUSED
	
	pName = pipeline.get_name()
	bus = pipeline.get_bus()
	
	while 1:
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
				Gst.Element.get_state_name(state), msgSrcName)
			
			pipeline.set_state(state)
			
		elif msgType == Gst.MessageType.CLOCK_LOST:
			logger.debug('Clock lost. Getting new one.')
			pipeline.set_state(Gst.State.PAUSED)
			pipeline.set_state(Gst.State.PLAYING)
			
		elif msgType == Gst.MessageType.LATENCY:
			gstPrintMsg(pName, 'Redistributing latency', sName=msgSrcName)
			pipeline.recalculate_latency()
		
		# messages that do not require pipeline manipulation	
		elif msgType == Gst.MessageType.BUFFERING:
			gstPrintMsg(pName, 'Buffering: {}', msg.parse_buffering(), sName=msgSrcName)
			
		elif msgType == Gst.MessageType.NEW_CLOCK:
			clock = msg.parse_new_clock()
			clock = clock.get_name() if clock else 'NULL'
			gstPrintMsg(pName, 'New clock: {}', clock)
			
		elif msgType == Gst.MessageType.INFO:
			error, debug = msg.parse_info()
			
			if debug:
				gstPrintMsg(pName, debug, level=logging.INFO, sName=msgSrcName)
				
		elif msgType == Gst.MessageType.WARNING:
			error, debug = msg.parse_warning()
			
			if debug:
				gstPrintMsg(pName, '{} - Additional debug info: {}', error.message,
					debug, level=logging.INFO, sName=msgSrcName)
			else:
				gstPrintMsg(pName, error.message, level=logging.INFO, sName=msgSrcName)
			
		elif msgType == Gst.MessageType.ERROR:
			processErrorMessage(pName, msgSrcName, msg, logging.ERROR)
			
		elif msgType == Gst.MessageType.STATE_CHANGED:
			# we only care about pipeline level state changes
			if msgSrc == pipeline:
				old, new, pending = msg.parse_state_changed()
				
				# we only care if we reach the final target state
				if targetState == Gst.State.PAUSED and new == Gst.State.PAUSED:
					prerolled = True
					
					if buffering:
						gstPrintMsg(pName, 'Prerolled, waiting for buffering to finish',
							level=logging.INFO)
						continue
						
					if inProgress:
						gstPrintMsg(pName, 'Prerolled, waiting for progress to finish',
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
			
			gstPrintMsg(pName, 'Progress: ({}) {}', code, text, sName=msgSrcName)
			
			if doProgress and not inProgress and not buffering and prerolled:
				return					

		elif msgType == Gst.MessageType.HAVE_CONTEXT:
			context = msg.parse_have_context()
			gstPrintMsg(
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
				
			gstPrintMsg(pName, '{}: {} = {}', obj.get_name(), propName, valStr, sName=msgSrcName)
			
		# these are things I might not need...
		elif msgType == Gst.MessageType.STREAM_START:
			if msgSrc == pipeline:
				gstPrintMsg(pName, 'Started stream', level=logging.INFO)

		elif msgType == Gst.MessageType.QOS:
			frmt, processed, dropped = msg.parse_qos_stats()
			jitter, proportion, quality = msg.parse_qos_values()

			gstPrintMsg(
				pName,
				'QOS stats: jitter={} dropped={}',
				jitter,
				'-' if frmt == Gst.Format.UNDEFINED else dropped,
				sName = msgSrcName
			)
				
		elif msgType == Gst.MessageType.ELEMENT:
			gstPrintMsg(pName, 'Unknown message ELEMENT', sName=msgSrcName)

		elif msgType == Gst.MessageType.UNKNOWN:
			gstPrintMsg(pName, 'Unknown message', sName=msgSrcname)
		
@async(daemon=True)	
def startPipeline(pipeline, play=True):
	pName = pipeline.get_name()
	stateChange = pipeline.set_state(Gst.State.PAUSED)
	gstPrintMsg(pName, 'Setting to PAUSED', level=logging.INFO)
	
	if stateChange == Gst.StateChangeReturn.FAILURE:
		gstPrintMsg(pName, 'Cannot set to PAUSE', level=logging.INFO)
		eventLoop(pipeline, block=False, doProgress=False, targetState=Gst.State.VOID_PENDING)
	# we should always end up here because live
	elif stateChange == Gst.StateChangeReturn.NO_PREROLL:
		gstPrintMsg(pName, 'Live and does not need preroll')
	elif stateChange == Gst.StateChangeReturn.ASYNC:
		gstPrintMsg(pName, 'Prerolling')
		try:
			eventLoop(pipeline, block=True, doProgress=True, targetState=Gst.State.PAUSED)
		except GstException:
			gstPrintMsg(pName, 'Does not want to preroll', level=logging.ERROR)
			# some cleanup here?
			raise
	elif stateChange == Gst.StateChangeReturn.SUCCESS:
		gstPrintMsg(pName, 'Is prerolled')
	
	# this should always succeed...
	try:
		eventLoop(pipeline, block=False, doProgress=True, targetState=Gst.State.PLAYING)
	except GstException:
		gstPrintMsg(pName, 'Does not want to preroll', level=logging.ERROR)
		# some cleanup here?
		raise
	# ...and end up here
	else:
		if play:
			gstPrintMsg(pName, 'Setting to PLAYING', level=logging.INFO)
		
			# and since this will ALWAYS be successful (maybe)...
			if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
				gstPrintMsg(pName, 'Cannot set to PLAYING', level=logging.ERROR)
				err = pipeline.get_bus().pop_filtered(Gst.MessageType.Error)
				processErrorMessage(pName, msgSrcName, err, logging.ERROR)
		
		# ...we and end up here and loop until Tool releases their next album
		try:
			eventLoop(pipeline, block=True, doProgress=False, targetState=Gst.State.PLAYING)
		except:
			# cleanup or recover
			raise

def initCamera(video=True, audio=True):
	pipeline = Gst.Pipeline.new("camera")
	
	vPath = '/dev/video0'
	
	if video:
		vSource = Gst.ElementFactory.make("v4l2src", "videoSource")
		vConvert = Gst.ElementFactory.make("videoconvert", "videoConvert")
		vScale = Gst.ElementFactory.make("videoscale", "videoScale")
		vClock = Gst.ElementFactory.make("clockoverlay", "videoClock")
		vEncode = Gst.ElementFactory.make("omxh264enc", "videoEncoder")
		vRTPPay = Gst.ElementFactory.make("rtph264pay", "videoRTPPayload")
		vRTPSink = Gst.ElementFactory.make("multiudpsink", "videoRTPSink")
	
		vSource.set_property('device', vPath)
		vRTPPay.set_property('config-interval', 1)
		vRTPPay.set_property('pt', 96)
		vRTPSink.set_property('clients', '127.0.0.1:9001,127.0.0.1:9002')
	
		vCaps = Gst.Caps.from_string('video/x-raw,width=640,height=480,framerate=30/1')
		
		pipeline.add(vSource, vConvert, vScale, vClock, vEncode, vRTPPay, vRTPSink)
		
		linkElements(vSource, vConvert)
		linkElements(vConvert, vScale)
		linkElements(vScale, vClock, vCaps)
		linkElements(vClock, vEncode)
		linkElements(vEncode, vRTPPay)
		linkElements(vRTPPay, vRTPSink)
	
	if audio:
		aSource = Gst.ElementFactory.make("alsasrc", "audioSource")
		aConvert = Gst.ElementFactory.make("audioconvert", "audioConvert")
		aScale = Gst.ElementFactory.make("audioresample", "audioResample")
		aEncode = Gst.ElementFactory.make("opusenc", "audioEncode")
		aRTPPay = Gst.ElementFactory.make("rtpopuspay", "audioRTPPayload")
		aRTPSink = Gst.ElementFactory.make("multiudpsink", "audioRTPSink")

		aSource.set_property('device', 'hw:1,0')
		aRTPSink.set_property('clients', '127.0.0.1:8001,127.0.0.1:8002')

		aCaps = Gst.Caps.from_string('audio/x-raw,rate=48000,channels=1')

		pipeline.add(aSource, aConvert, aScale, aEncode, aRTPPay, aRTPSink)

		linkElements(aSource, aConvert)
		linkElements(aConvert, aScale)
		linkElements(aScale, aEncode, aCaps)
		linkElements(aEncode, aRTPPay)
		linkElements(aRTPPay, aRTPSink)
		
	waitForPath(vPath) # video is on usb, so wait until it comes back after we hard reset the bus
	
	startPipeline(pipeline)

class FileDump:
	def __init__(self):
		self.pipeline = Gst.Pipeline.new('filedump')
		
		aSource = Gst.ElementFactory.make('udpsrc', 'audioSource')
		aParse = Gst.ElementFactory.make('opusparse', 'audioParse')
		aQueue = Gst.ElementFactory.make('queue', 'audioQueue')
		
		vSource = Gst.ElementFactory.make('udpsrc', 'videoSource')
		vParse = Gst.ElementFactory.make('h264parse', 'videoParse')
		vQueue = Gst.ElementFactory.make('queue', 'videoQueue')
		
		mux = Gst.ElementFactory.make('matroskamux', 'mux')
		
		self.sink = Gst.ElementFactory.make('filesink', 'sink')
		self.sink.set_property('location', '/dev/null')
		
		aSource.set_property('port', 8000)
		vSource.set_property('port', 9000)
		
		self.pipeline.add(aSource, aParse, aQueue, vSource, vParse, vQueue, mux, self.sink)
		
		linkElements(vSource, vParse)
		linkElements(vParse, vQueue)
		linkElements(vQueue, mux)
		
		linkElements(aSource, aParse)
		linkElements(aParse, aQueue)
		linkElements(aQueue, mux)
		
		linkElements(mux, self.sink)
		
		startPipeline(self.pipeline, play=False)	
		
	def setPath(self, path):
		self.sink.set_property('location', path)
		
	def play(self):
		self.pipeline.set_state(Gst.State.PLAYING)
		
	def pause(self):
		self.pipeline.set_state(Gst.State.PAUSED)
		
Gst.init(None)

# this works for file dump
# gst-launch-1.0 -v udpsrc port=8001 ! application/x-rtp,encoding-name=OPUS,payload=96 ! 
# rtpjitterbuffer ! rtpopusdepay ! queue ! matroskamux name=mux ! filesink location=testicle.mkv \
# udpsrc port=9001 ! application/x-rtp,encoding-name=H264,payload=96 ! rtpjitterbuffer ! \
# rtph264depay ! h264parse ! queue ! mux.
