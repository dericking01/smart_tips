import logging
from pathlib import Path
from pythonjsonlogger import jsonlogger

LOG_DIR = Path(__file__).resolve().parents[2] / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / 'app.log'

logger = logging.getLogger('smart_health_tips')
logger.setLevel(logging.INFO)
logger.propagate = False

if not logger.handlers:
    handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)