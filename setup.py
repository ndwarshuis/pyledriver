from setuptools import setup

setup(name='pyledriver',
      version='0.1',
      description='Pyledriver Home Security System',
      url='http://github.com/ndwarshuis/pyledriver',
      author='Nathan Dwarshuis',
      author_email='natedwrshuis@gmail.com',
      license='GPLv3',
      packages=['pyledriver'],
	  install_requires=['Flask', 'evdev', 'Flask-WTF', 'numpy',
						'psutil', 'pyaudio', 'pygame', 'pyinotify',
						'RPi.GPIO', 'requests', 'yaml'],
      zip_safe=False)
