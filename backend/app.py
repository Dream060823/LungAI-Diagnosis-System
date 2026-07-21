from flask import Flask, jsonify
from flask_cors import CORS

from api import api_bp
from config import Config, ensure_data_dirs


def create_app() -> Flask:
    ensure_data_dirs()

    app = Flask(__name__)
    app.config.from_object(Config)

    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})
    app.register_blueprint(api_bp)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "lung-nodule-backend"})

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
