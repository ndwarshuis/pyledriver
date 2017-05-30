import logging
from subprocess import check_output, CalledProcessError
from flask import Flask, render_template, Response, Blueprint, redirect, url_for
from flask_wtf import FlaskForm
from wtforms.fields import StringField, SubmitField
from wtforms.validators import InputRequired

from auxilary import async

logger = logging.getLogger(__name__)

# gag the flask logger unless it has something useful to say
werkzeug = logging.getLogger('werkzeug')
werkzeug.setLevel(logging.ERROR)

class TTSForm(FlaskForm):
	tts = StringField(validators=[InputRequired()])
	submitTTS = SubmitField('Speak')

# TODO: fix random connection fails (might be an nginx thing)

@async(daemon=True)
def _runApp(a):
	logger.info('Starting web interface')
	a.run(debug=False, threaded=True)

def initWebInterface(stateMachine):
	siteRoot = Blueprint('siteRoot', __name__, static_folder='static', static_url_path='')

	@siteRoot.route('/', methods=['GET', 'POST'])
	@siteRoot.route('/index', methods=['GET', 'POST'])
	def index():
		ttsForm = TTSForm()
		
		if ttsForm.validate_on_submit() and ttsForm.submitTTS.data:
			stateMachine.soundLib.speak(ttsForm.tts.data)
			return redirect(url_for('siteRoot.index'))

		return render_template(
			'index.html',
			ttsForm=ttsForm,
			state=stateMachine.currentState
		)

	try:
		check_output(['pidof', 'janus'])
	except CalledProcessError:
		logger.error('Janus not running. Aborting')
		raise SystemExit

	app = Flask(__name__)
	app.secret_key = '3276d68dac56985bea352325125641ff'
	app.register_blueprint(siteRoot, url_prefix='/pyledriver')
	
	_runApp(app)
