"""
app/__init__.py

Flask application factory for the Tropicana Guide app.
"""
import os

from flask import Flask
from dotenv import load_dotenv


def create_app():
    """Create and configure the Flask application."""
    load_dotenv()  # loads ANTHROPIC_API_KEY from .env if present, no error if missing

    app = Flask(
        __name__,
        static_folder="../static",
        template_folder="../templates",
    )
    app.config["SECRET_KEY"] = "tropicana-guide-secret-change-in-prod"

    from app.locations import locations_bp
    from app.assistant import assistant_bp

    app.register_blueprint(locations_bp)
    app.register_blueprint(assistant_bp)

    from flask import render_template

    @app.route("/")
    def index():
        return render_template("index.html")

    return app