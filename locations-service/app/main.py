import os
from app import create_app
from app.db import sync_pois_from_json

app = create_app()

with app.app_context():
    sync_pois_from_json()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False)
