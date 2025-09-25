import os

DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
HOST = os.environ.get('HOST', '0.0.0.0')
PORT = int(os.environ.get('PORT', 5000))

DEFAULT_OCR_CONFIG = {
    'use_gpu': True,
    'use_lite': False,
    'output_format': 'json'
}