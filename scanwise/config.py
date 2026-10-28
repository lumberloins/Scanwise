import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'scanwise-dev-secret-key-2026')
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    HOST = os.environ.get('SCANWISE_HOST', '0.0.0.0')
    PORT = int(os.environ.get('SCANWISE_PORT', 5000))
    DEFAULT_PROFILE = 'epic_emr'
