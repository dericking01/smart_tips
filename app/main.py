from fastapi import FastAPI
from app.database.init_schema import init_schema

app = FastAPI(title="Smart Health Tips")

@app.on_event("startup")
def startup():
    init_schema()

@app.get("/")
def health():
    return {"status": "running"}