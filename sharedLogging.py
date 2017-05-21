import logging
from logging.handlers import TimedRotatingFileHandler, QueueListener, QueueHandler

def SlaveLogger(name, level, queue):
	logger = logging.getLogger(name)
	logger.setLevel(getattr(logging, level))
	logger.addHandler(QueueHandler(queue))
	logger.propagate = False
	return logger

#TODO: need to add mounting code here for gluster. since this app is the only
# gluster user, (un)mounting should be handled here instead of by systemd

class MasterLogger():
	def __init__(self, name, level, queue):
		consoleFormat = logging.Formatter('[%(name)s] [%(levelname)s] %(message)s')
		fileFormat = logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s')
		
		console = logging.StreamHandler()
		console.setFormatter(consoleFormat)
		
		rotatingFile = TimedRotatingFileHandler('/mnt/glusterfs/pyledriver/logs/pyledriver-log', when='midnight')
		rotatingFile.setFormatter(fileFormat)
		
		logging.basicConfig(level=getattr(logging, level), handlers=[QueueHandler(queue)])
		logger = logging.getLogger(name)
		
		# since the logger module sucks and doesn't allow me to init
		# a logger in a subclass, need to "fake" object inheritance
		for i in ['debug', 'info', 'warning', 'error', 'critical']:
			setattr(self, i, getattr(logger, i))
		
		self.queListener = QueueListener(queue, console, rotatingFile)
		self.queListener.start()

	def stop(self):
		self.queListener.stop()
