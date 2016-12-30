from async import async
#~ from logger import logGeneric
import socket
from ftplib import FTP
from io import BytesIO
from functools import partial

def buildUploader(host, port, user, passwd):
	
	@async(daemon=False)
	def uploader(filepath, filename, buf):
		retries = 3
		ftp = FTP()
		while retries > 0:
			try:
				ftp.connect(host=host, port=port)
				ftp.login(user=user, passwd=passwd)
				ftp.cwd(filepath)
				ftp.storbinary('STOR ' + filename, BytesIO(buf))
				break
			except IOError:
				retries =- 1
				#~ logGeneric('remoteServer: Failed to upload file. ' + str(retries) + ' retries left...', 0)
		ftp.quit()
		
	return uploader
