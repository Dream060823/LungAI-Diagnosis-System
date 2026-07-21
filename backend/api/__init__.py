from flask import Blueprint

api_bp = Blueprint("api", __name__, url_prefix="/api")

from api import analyze, history, upload  # noqa: E402, F401
