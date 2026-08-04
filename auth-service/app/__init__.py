from flask import Flask
from dotenv import load_dotenv


def create_app():
    load_dotenv()
    app = Flask(__name__)
    from app.auth import auth_bp
    app.register_blueprint(auth_bp)
    return app
