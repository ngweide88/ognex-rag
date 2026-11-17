"""Development entry point: ``python run.py``."""

from ognex.backend import create_app
from ognex.config import settings

app = create_app()

if __name__ == "__main__":
    app.run(host=settings.host, port=settings.port, debug=settings.debug, threaded=True)