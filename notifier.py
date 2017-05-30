import logging, time
from auxilary import async, ConfigFile
from smtplib import SMTP
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text  import MIMEText 

logger = logging.getLogger(__name__)

COMMASPACE=', '

RECIPIENT_LIST=ConfigFile('config.yaml')['recipientList']

GMAIL_USER='natedwarshuis@gmail.com'
GMAIL_PWD='bwsasfxqjbookmed'

def getNextDate():
	m = datetime.now().month + 1
	y = datetime.now().year
	y = y + 1 if m > 12 else y
	return datetime(year=y, month=m%12, day=1, hour=12, minute=0)

@async(daemon=True)
def scheduleAction(action):
	while 1:
		nextDate = getNextDate()
		sleepTime = nextDate - datetime.today()
		logger.info('Next monthly test scheduled at %s (%s)', nextDate, sleepTime)
		time.sleep(sleepTime.days * 86400 + sleepTime.seconds)
		action()

# probably an easier way to do this in logging module
@async(daemon=False)
def sendEmail(subject, body):
	msg = MIMEMultipart()
	msg['Subject'] =  subject
	msg['From'] = GMAIL_USER
	msg['To'] = COMMASPACE.join(RECIPIENT_LIST)
	msg.attach(MIMEText(body, 'plain'))

	s = SMTP('smtp.gmail.com', 587)
	s.starttls()
	s.login(GMAIL_USER, GMAIL_PWD)
	s.send_message(msg)
	s.quit()

def monthlyTest():
	subject = 'harrison4hegemon - automated monthly test'
	body = 'this is an automated message - please do not reply\n\nin the future this may have useful information'
	sendEmail(subject, body)
	logger.info('Sending monthly test to email list')
	
def intruderAlert():
	subject = 'harrison4hegemon - intruder detected'
	body = 'intruder detected - alarm was tripped on ' + time.strftime("%H:%M:%S - %d/%m/%Y")
	sendEmail(subject, body)
	logger.info('Sending intruder alert to email list')
	
def criticalError(err):
	subject = 'harrison4hegemon - critical error'
	sendEmail(subject, err)
	logger.info('Sending critical error to email list')

scheduleAction(monthlyTest)
