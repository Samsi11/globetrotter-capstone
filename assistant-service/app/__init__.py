from flask import Flask
from dotenv import load_dotenv


def create_app():
    load_dotenv()
    app = Flask(__name__)
    from app.assistant import assistant_bp
    app.register_blueprint(assistant_bp)
    return app
