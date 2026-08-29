from app.server import app
from condo_gpt.config import get_settings
import os

if __name__ == "__main__":
    settings = get_settings()
    app.run(debug=settings.flask_debug, port=int(os.getenv("PORT", "5000")))
