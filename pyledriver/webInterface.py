import logging
from subprocess import check_output, CalledProcessError, run, PIPE
from flask import Flask, render_template, Response, Blueprint, redirect, url_for
from flask_wtf import FlaskForm
from wtforms.fields import StringField, SubmitField
from wtforms.validators import InputRequired

from exceptionThreading import async

logger = logging.getLogger(__name__)

# gag the flask logger unless it has something useful to say
werkzeug = logging.getLogger('werkzeug')
werkzeug.setLevel(logging.ERROR)

class TTSForm(FlaskForm):
	tts = StringField(validators=[InputRequired()])
	submitTTS = SubmitField('Speak')
	
class JanusRestart(FlaskForm):
	submitRestart = SubmitField('Restart Janus')

# TODO: fix random connection fails (might be an nginx thing)

def janusRunning():
	try:
		check_output(['pidof', 'janus'])
	except CalledProcessError:
		logger.warning('Janus not running')
		return False
	else:
		return True

@async(daemon=True)
def startWebInterface(stateMachine):
	siteRoot = Blueprint('siteRoot', __name__, static_folder='static', static_url_path='')

	@siteRoot.route('/', methods=['GET', 'POST'])
	@siteRoot.route('/index', methods=['GET', 'POST'])
	def index():
		ttsForm = TTSForm()
		janusRestart = JanusRestart()
		
		if ttsForm.validate_on_submit() and ttsForm.submitTTS.data:
			stateMachine.soundLib.speak(ttsForm.tts.data)
			return redirect(url_for('siteRoot.index'))
		elif janusRestart.validate_on_submit():
			logger.info('Restarting Janus')
			run(['systemctl', 'restart', 'janus'], stdout=PIPE, stderr=PIPE)
			return redirect(url_for('siteRoot.index'))

		return render_template(
			'index.html',
			ttsForm=ttsForm,
			state=stateMachine.currentState,
			janusRunning=janusRunning(),
			janusRestart=janusRestart
		)
		
	janusRunning()

	app = Flask(__name__)
	app.secret_key = '3276d68dac56985bea352325125641ff'
	app.register_blueprint(siteRoot, url_prefix='/pyledriver')
	
	logger.info('Starting web interface')
	app.run(debug=False, threaded=True)
