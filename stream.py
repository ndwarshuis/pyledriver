#! /bin/python

from auxilary import async

import gi, time
gi.require_version('Gst', '1.0')

from gi.repository import Gst

Gst.init(None)

pipe = Gst.Pipeline.new("streamer")
bus = pipe.get_bus()

vidSrc = Gst.ElementFactory.make("v4l2src", "vidSrc")
vidConv = Gst.ElementFactory.make("videoconvert", "vidConv")
vidScale = Gst.ElementFactory.make("videoscale", "vidScale")
vidClock = Gst.ElementFactory.make("clockoverlay", "vidClock")
vidEncode = Gst.ElementFactory.make("omxh264enc", "vidEncode")
vidParse = Gst.ElementFactory.make("h264parse", "vidParse")
mux = Gst.ElementFactory.make("mp4mux", "mux")
#~ sink = Gst.ElementFactory.make("tcpserversink", "sink")
sink = Gst.ElementFactory.make("filesink", "sink")

vidSrc.set_property('device', '/dev/video0')
#~ sink.set_property('host', '0.0.0.0')
#~ sink.set_property('port', 8080)
sink.set_property('location', '/home/alarm/testicle.mp4')

vidRawCaps = Gst.Caps.from_string('video/x-raw,width=320,height=240,framerate=30/1')
parseCaps = Gst.Caps.from_string('video/x-h264,stream-format=avc')

pipe.add(vidSrc, vidConv, vidScale, vidClock, vidEncode, vidParse, mux, sink)

print(vidSrc.link(vidConv))
print(vidConv.link(vidScale))
print(vidScale.link_filtered(vidClock, vidRawCaps))
print(vidClock.link(vidEncode))
print(vidEncode.link(vidParse))
print(vidParse.link_filtered(mux, parseCaps))
print(mux.link(sink))

pipe.set_state(Gst.State.PLAYING)

#~ signal.signal(signal.SIGTERM, exit())

def terminate():
	pipe.set_state(Gst.State.NULL)
	exit()

@async(daemon=True)
def errorHandler():
	while 1:
		msg = bus.timed_pop_filtered(1e18, Gst.MessageType.ERROR)
		print('howdy')
		print(msg.parse_error())
		terminate()
		
@async(daemon=True)
def eosHandler():
	while 1:
		msg = bus.timed_pop_filtered(1e18, Gst.MessageType.EOS)
		print('EOS reached')
		terminate()

try:
	errorHandler()
	eosHandler()
	
	while 1:
		time.sleep(3600)
	
except KeyboardInterrupt:
	pass


