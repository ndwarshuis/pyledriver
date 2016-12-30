from multiprocessing import Process
from sharedLogging import SlaveLogger
from flask import Flask, render_template, Response, Blueprint, redirect, url_for
from flask_wtf import FlaskForm
from wtforms.fields import SelectField, StringField, SubmitField
from wtforms.validators import InputRequired

class CamForm(FlaskForm):
	fps = SelectField(choices=[(i, '%s fps' % i) for i in range(10, 31, 5)], coerce=int)
	submitFPS = SubmitField('Set')
	
class TTSForm(FlaskForm):
	tts = StringField(validators=[InputRequired()])
	submitTTS = SubmitField('Speak')

class ResetForm(FlaskForm):
	submitReset = SubmitField('Reset')
	
# TODO: fix random connection fails (might be an nginx thing)
# TODO: show camera failed status here somewhere

class WebInterface(Process):
	def __init__(self, camera, stateDict, ttsQueue, loggerQueue):
		self._moduleLogger = SlaveLogger(__name__, 'INFO', loggerQueue)
		self._flaskLogger = SlaveLogger('werkzeug', 'ERROR', loggerQueue)
		
		camPage = Blueprint('camPage', __name__, static_folder='static', template_folder='templates')

		def generateFrame():
			while 1:
				yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + camera.getFrame() + b'\r\n')
	
		@camPage.route('/', methods=['GET', 'POST'])
		@camPage.route('/index', methods=['GET', 'POST'])
		def index():
			props = camera.getProps('FPS')
			fps = int(props['FPS'])
			camForm = CamForm(fps = props['FPS'])
			ttsForm = TTSForm()
			resetForm = ResetForm()
			
			if camForm.validate_on_submit() and camForm.submitFPS.data:
				camera.setProps(FPS=camForm.fps.data)
				return redirect(url_for('camPage.index'))
				
			if ttsForm.validate_on_submit() and ttsForm.submitTTS.data:
				ttsQueue.put_nowait(ttsForm.tts.data)
				return redirect(url_for('camPage.index'))

			if resetForm.validate_on_submit() and resetForm.submitReset.data:
				camera.reset()
				return redirect(url_for('camPage.index'))

			return render_template(
				'index.html',
				camForm=camForm,
				ttsForm=ttsForm,
				resetForm=resetForm,
				fps=fps,
				state=stateDict['name']
			)

		@camPage.route('/videoFeed')
		def videoFeed():
			return Response(generateFrame(), mimetype='multipart/x-mixed-replace; boundary=frame')
			
		self._app = Flask(__name__)
		self._app.secret_key = '3276d68dac56985bea352325125641ff'
		self._app.register_blueprint(camPage, url_prefix='/pyledriver')

		super().__init__(daemon=True)
		
	def run(self):
		# TODO: not sure exactly how threaded=True works, intended to enable
		# multiple connections. May want to use something more robust w/ camera
		# see here: https://blog.miguelgrinberg.com/post/video-streaming-with-flask
		
		self._moduleLogger.info('Started web interface')
		self._app.run(debug=False, threaded=True)
	
	def stop(self):
		self.terminate()
		self.join()
		self._moduleLogger.info('Terminated web interface')
