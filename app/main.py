from fastapi import FastAPI
from cua_runner import run_cua

app = FastAPI()

@app.get("/")
def root():
    return {"status": "alive"}

@app.get("/run")
def run():
    run_cua()
    return {"status": "finished"}
