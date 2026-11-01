import asyncio
import os
import json
import re
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Dict, Any

app = FastAPI(title="ARWallet Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ACCOUNTS_FILE = "accounts_session.json"
CONFIG_FILE = "last_configs.json"
active_sessions: Dict[str, Dict[str, Any]] = {}
system_logs = []

def log_event(message: str):
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = f"[{timestamp}] {message}"
    system_logs.append(entry)
    if len(system_logs) > 100:
        system_logs.pop(0)

class StartRequest(BaseModel):
    phone: str
    tab: str = "OTP-UPI"
    range_val: str = "2001-2999"
    payment_app: str = "PhonePe"

@app.get("/api/logs")
def get_logs():
    return {"logs": system_logs}

async def dismiss_all_popups(page):
    for _ in range(4):
        try:
            clicked = await page.evaluate(r"""
                () => {
                    let hit = false;
                    const all = Array.from(document.querySelectorAll('button, div, span, a, i, svg'));
                    for (let el of all) {
                        const t = (el.innerText || '').trim();
                        if (t === 'Close' || t === 'Go buy' || t === 'Confirm' || t === 'IKnow') {
                            const r = el.getBoundingClientRect();
                            if (r.width > 20 && r.height > 15 && r.height < 90) {
                                el.click();
                                hit = true;
                            }
                        }
                    }
                    return hit;
                }
            """)
            await asyncio.sleep(0.4)
            if not clicked:
                break
        except Exception:
            break

async def background_matching_worker(phone: str, tab: str, range_val: str, payment_app: str):
    from playwright.async_api import async_playwright
    
    s_key = phone
    active_sessions[s_key] = {"running": True, "tab": tab, "range": range_val, "app": payment_app}
    log_event(f"Task Started: {phone} [{tab} | {range_val} | {payment_app}]")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-blink-features=AutomationControlled"]
            )
            context = await browser.new_context(
                viewport={"width": 390, "height": 844},
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
                has_touch=True
            )
            page = await context.new_page()

            # Load sessions if stored
            accounts = {}
            if os.path.exists(ACCOUNTS_FILE):
                try:
                    with open(ACCOUNTS_FILE, "r") as f:
                        accounts = json.load(f)
                except Exception:
                    accounts = {}
            
            session_data = accounts.get(phone, {})
            base_url = "https://clbsk.paywivo.com"
            try:
                await page.goto(base_url, timeout=25000)
            except Exception:
                base_url = "https://arbpay.ai"
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
                log_event("Session loaded into browser.")

            await page.goto(f"{base_url}/#/buy/arb", timeout=30000)
            await asyncio.sleep(2.5)
            await dismiss_all_popups(page)
            log_event(f"Buy ARB Page Open. Starting Auto Match for {phone}...")

            round_num = 1
            while active_sessions.get(s_key, {}).get("running", False):
                try:
                    body_text = await page.inner_text("body")
                    if any(k in body_text for k in ["Countdown to Expiry", "Use Mobile Scan code", "Matched, pending payment"]):
                        log_event(f"🚨 ORDER MATCH HO GAYA on {phone}! Payment ready!")
                        break

                    # Match Again button click
                    clicked = await page.evaluate(r"""
                        () => {
                            const btns = Array.from(document.querySelectorAll('button, div, span')).filter(
                                el => (el.innerText || '').trim() === 'Match Again' && el.offsetParent !== null
                            );
                            if (btns.length > 0) {
                                btns[0].click();
                                return true;
                            }
                            return false;
                        }
                    """)
                    if clicked:
                        log_event(f"Round #{round_num} Match Triggered...")
                        round_num += 1
                        await asyncio.sleep(12)
                    else:
                        await asyncio.sleep(2.5)
                except Exception:
                    await asyncio.sleep(2)

            await browser.close()
            log_event(f"Session Stopped for {phone}")
    except Exception as e:
        log_event(f"Error ({phone}): {str(e)}")
    finally:
        if s_key in active_sessions:
            del active_sessions[s_key]

@app.post("/api/start")
def start_task(req: StartRequest, background_tasks: BackgroundTasks):
    if req.phone in active_sessions and active_sessions[req.phone].get("running"):
        raise HTTPException(status_code=400, detail="Matching already active for this number.")
    background_tasks.add_task(background_matching_worker, req.phone, req.tab, req.range_val, req.payment_app)
    return {"status": "started", "phone": req.phone}

@app.post("/api/stop/{phone}")
def stop_task(phone: str):
    if phone in active_sessions:
        active_sessions[phone]["running"] = False
        log_event(f"Stop signal received for {phone}")
        return {"status": "stopping"}
    return {"status": "not_running"}

if os.path.exists("public"):
    app.mount("/", StaticFiles(directory="public", html=True), name="static")
