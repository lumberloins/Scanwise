import traceback

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException
from scanwise.config import Config

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Register blueprints (to be implemented in later phases)
    try:
        from scanwise.routes.views import views_bp
        from scanwise.routes.api import api_bp
        app.register_blueprint(views_bp)
        app.register_blueprint(api_bp, url_prefix='/api')
    except ImportError:
        # Blueprints not yet created (Phase 1 scaffolding)
        pass

    @app.after_request
    def no_store_api(resp):
        # Analysis results contain the scanned data (possibly PHI): never let a browser or proxy cache them.
        if request.path.startswith('/api/'):
            resp.headers['Cache-Control'] = 'no-store'
            resp.headers['Pragma'] = 'no-cache'
        return resp

    @app.errorhandler(Exception)
    def log_without_data(err):
        # Exception messages can quote the scanned data; log only the type and the code location.
        if isinstance(err, HTTPException):
            return err
        tb = ''.join(traceback.format_tb(err.__traceback__))
        app.logger.error('Unhandled %s on %s %s (message withheld: may contain scan data)\n%s',
                         type(err).__name__, request.method, request.path, tb)
        return jsonify({'status': 'error', 'error': 'Internal error (details withheld)'}), 500

    @app.route('/health')
    def health_check():
        return {'status': 'healthy', 'app': 'ScanWise'}, 200

    return app
