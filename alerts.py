"""
alerts.py
One alert function for everything: prints, and sends to Discord if DISCORD_WEBHOOK_URL is set in .env.
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()


def alert(text: str):
    print(text, flush=True)
    url = os.getenv("DISCORD_WEBHOOK_URL")
    if not url:
        return
    try:
        requests.post(url, json={"content": text[:1900]}, timeout=10)  # Discord limit is 2000 chars
    except Exception as e:
        print(f"alert failed: {e}", flush=True)