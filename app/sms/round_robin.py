from itertools import cycle
from app.config.settings import settings

PORTS = settings.SMS_PORTS.split(",")
PORT_CYCLE = cycle(PORTS)

def get_next_port():
    return next(PORT_CYCLE)