import asyncio
import os
import json
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Dict, Any

app = FastAPI(title="AR Terminal API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ACCOUNTS_FILE = "accounts_session.json"
active_sessions: Dict[str, Dict[str, Any]] = {}
system_logs = []

def log_event(message: str):
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = f"[{timestamp}] {message}"
    system_logs.append(entry)
    if len(system_logs) > 200:
        system_logs.pop(0)

class StartMatchingRequest(BaseModel):
    phone: str
    tab: str = "OTP-UPI"
    range_val: str = "2001-2999"
    payment_app: str = "PhonePe"

@app.get("/api/logs")
def get_logs():
    return {"logs": system_logs}

async def background_automation_worker(phone: str, tab: str, range_val: str, payment_app: str):
    from playwright.async_api import async_playwright

    s_key = phone
    active_sessions[s_key] = {"running": True, "tab": tab, "range": range_val, "app": payment_app}
    log_event(f"Task started for {phone} [{tab} | {range_val} | {payment_app}]")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
            )
            context = await browser.new_context(
                viewport={"width": 390, "height": 844},
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
            )
            page = await context.new_page()

            accounts = {}
            if os.path.exists(ACCOUNTS_FILE):
                with open(ACCOUNTS_FILE, "r") as f:
                    accounts = json.load(f)

            session_data = accounts.get(phone, {})
            base_url = "https://clbsk.paywivo.com"

            log_event("Opening portal...")
            await page.goto(base_url, timeout=30000)

            if session_data:
                await page.evaluate(r"""
                    (storageMap) => {
                        for (let k in storageMap) {
                            const val = typeof storageMap[k] === 'object' ? JSON.stringify(storageMap[k]) : storageMap[k];
                            localStorage.setItem(k, val);
                        }
                    }
                """, session_data)
                log_event("Session storage injected.")

            await page.goto(f"{base_url}/#/buy/arb", timeout=30000)
            await asyncio.sleep(2)
            log_event(f"Automation active for {phone}...")

            while active_sessions.get(s_key, {}).get("running", False):
                await asyncio.sleep(3)

            await browser.close()
            log_event(f"Session closed for {phone}")
    except Exception as e:
        log_event(f"Error ({phone}): {str(e)}")
    finally:
        if s_key in active_sessions:
            del active_sessions[s_key]

@app.post("/api/start")
def start_task(req: StartMatchingRequest, background_tasks: BackgroundTasks):
    if req.phone in active_sessions and active_sessions[req.phone].get("running"):
        raise HTTPException(status_code=400, detail="Task already running.")
    background_tasks.add_task(background_automation_worker, req.phone, req.tab, req.range_val, req.payment_app)
    return {"status": "started", "phone": req.phone}

@app.post("/api/stop/{phone}")
def stop_task(phone: str):
    if phone in active_sessions:
        active_sessions[phone]["running"] = False
        log_event(f"Stopping task for {phone}...")
        return {"status": "stopping"}
    return {"status": "not_running"}

if os.path.exists("public"):
    app.mount("/", StaticFiles(directory="public", html=True), name="static")
