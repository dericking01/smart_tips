import datetime
import logging
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from pythonjsonlogger import jsonlogger

LOG_DIR = Path(__file__).resolve().parents[2] / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / 'app.log'

# Read timezone directly from env (same source as settings.TIMEZONE) so this
# module stays independent and avoids any circular-import risk.
_TIMEZONE_STR = os.environ.get('TIMEZONE', 'Africa/Dar_es_Salaam')

try:
    _TZ = ZoneInfo(_TIMEZONE_STR)
except Exception:
    _TZ = None


def _tz_converter(timestamp: float):
    """Return a time.struct_time in the configured timezone (used by logging)."""
    if _TZ:
        dt = datetime.datetime.fromtimestamp(timestamp, tz=_TZ)
        return dt.timetuple()
    return datetime.datetime.fromtimestamp(timestamp).timetuple()


logger = logging.getLogger('smart_health_tips')
logger.setLevel(logging.INFO)
logger.propagate = False

if not logger.handlers:
    handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(message)s')
    formatter.converter = _tz_converter      # all timestamps now use TIMEZONE
    handler.setFormatter(formatter)
    logger.addHandler(handler)
