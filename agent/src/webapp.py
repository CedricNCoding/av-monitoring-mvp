import os
import threading
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.storage import load_config, save_config
from src.collector import run_forever

CONFIG_PATH = os.getenv("AGENT_CONFIG", "/agent/config/config.json")

app = FastAPI(title="AV Agent - Local Admin")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

_stop_flag = {"stop": True}
_thread: threading.Thread | None = None

def collector_running() -> bool:
    return _thread is not None and _thread.is_alive() and not _stop_flag["stop"]

def ensure_collector_running() -> None:
    global _thread
    if collector_running():
        return
    _stop_flag["stop"] = False
    _thread = threading.Thread(target=run_forever, args=(_stop_flag,), daemon=True)
    _thread.start()

def stop_collector() -> None:
    _stop_flag["stop"] = True

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    cfg = load_config(CONFIG_PATH)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "cfg": cfg,
            "running": collector_running(),
        },
    )

@app.post("/settings")
def update_settings(
    site_name: str = Form(...),
    site_token: str = Form(...),
    api_url: str = Form(...),
):
    cfg = load_config(CONFIG_PATH)
    cfg["site_name"] = site_name.strip()
    cfg["site_token"] = site_token.strip()
    cfg["api_url"] = api_url.strip()
    save_config(CONFIG_PATH, cfg)
    return RedirectResponse("/", status_code=303)

@app.post("/devices/add")
def add_device(
    ip: str = Form(...),
    device_type: str = Form("unknown"),
    driver: str = Form("ping"),
):
    cfg = load_config(CONFIG_PATH)
    cfg.setdefault("devices", [])

    ip = ip.strip()
    if ip and all(d.get("ip") != ip for d in cfg["devices"]):
        cfg["devices"].append({"ip": ip, "type": device_type.strip(), "driver": driver.strip()})

    save_config(CONFIG_PATH, cfg)
    return RedirectResponse("/", status_code=303)

@app.post("/devices/delete")
def delete_device(ip: str = Form(...)):
    cfg = load_config(CONFIG_PATH)
    ip = ip.strip()
    cfg["devices"] = [d for d in cfg.get("devices", []) if d.get("ip") != ip]
    save_config(CONFIG_PATH, cfg)
    return RedirectResponse("/", status_code=303)

@app.post("/collector/start")
def start_collector():
    ensure_collector_running()
    return RedirectResponse("/", status_code=303)

@app.post("/collector/stop")
def stop_collector_route():
    stop_collector()
    return RedirectResponse("/", status_code=303)