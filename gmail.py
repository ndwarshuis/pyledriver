import logging, time
from auxilary import async, ConfigFile
from smtplib import SMTP
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text  import MIMEText 

logger = logging.getLogger(__name__)

gmail = ConfigFile('config.yaml')['gmail']

def _getNextDate():
	m = datetime.now().month + 1
	y = datetime.now().year
	y = y + 1 if m > 12 else y
	return datetime(year=y, month=m%12, day=1, hour=12, minute=0)

@async(daemon=True)
def _scheduleAction(action):
	while 1:
		nextDate = _getNextDate()
		sleepTime = nextDate - datetime.today()
		logger.info('Next monthly test scheduled at %s (%s)', nextDate, sleepTime)
		time.sleep(sleepTime.days * 86400 + sleepTime.seconds)
		action()

@async(daemon=False)
def _sendToGmail(username, passwd, recipiantList, subject, body, server='smtp.gmail.com', port=587):
	msg = MIMEMultipart()
	msg['Subject'] =  subject
	msg['From'] = username
	msg['To'] = ', '.join(recipiantList)
	msg.attach(MIMEText(body, 'plain'))

	s = SMTP(server, port)
	s.starttls()
	s.login(username, passwd)
	s.send_message(msg)
	s.quit()

def monthlyTest():
	subject = 'harrison4hegemon - automated monthly test'
	body = 'this is an automated message - please do not reply\n\nin the future this may have useful information'
	sendEmail(gmail['username'], gmail['passwd'], gmail['recipientList'], subject, body)
	logger.debug('Sending monthly test to email list')
	
def intruderAlert():
	subject = 'harrison4hegemon - intruder detected'
	body = 'intruder detected - alarm was tripped on ' + time.strftime("%H:%M:%S - %d/%m/%Y")
	sendEmail(gmail['username'], gmail['passwd'], gmail['recipientList'], subject, body)
	logger.info('intruder detected')
	logger.debug('Sending intruder alert to email list')

class GmailHandler(logging.Handler):
	'''
	Logging handler that sends records to gmail. This is almost like the
	SMTPHandler except that the username and fromaddr are the same and
	credentials are mandatory
	'''
	def __init__(self, username, passwd, recipientList, subject):
		super().__init__()
		self.username = username
		self.passwd = passwd
		self.recipientList = recipientList
		self.subject = subject
		
	def emit(self, record):
		try:
			_sendToGmail(self.username, self.passwd, self.recipientList,
				self.subject, self.format(record))
		except:
			self.handleError(record)

_scheduleAction(monthlyTest)
