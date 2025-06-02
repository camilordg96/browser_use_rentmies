from fastapi import FastAPI, Query
from cua_runner import run_cua

app = FastAPI()

@app.get("/run")
def run(
    url: str = Query(..., description="Enlace de HubSpot"),
    first: str = "Camilo",
    last: str = "Caceres",
    mail: str = "camilo@rentmies.com",
    hour: str = "10"
):
    run_cua(url, first, last, mail, hour)
    return {"status": "started", "url": url}

