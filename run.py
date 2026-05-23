import threading
import uvicorn
from app.scheduler.scheduler import start_scheduler

threading.Thread(target=start_scheduler, daemon=True).start()

uvicorn.run(
    "app.main:app",
    host="0.0.0.0",
    port=8000,
    reload=False
)