from flask import Flask
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

    @app.route('/health')
    def health_check():
        return {'status': 'healthy', 'app': 'ScanWise'}, 200

    return app
