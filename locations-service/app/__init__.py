from flask import Flask
from dotenv import load_dotenv


def create_app():
    load_dotenv()
    app = Flask(__name__)
    from app.locations import locations_bp
    app.register_blueprint(locations_bp)
    return app
