import os
import json 
import requests

def alert(text):
    """Print, and send to Discord if a webhook is set."""
    print(text)
    url=os.getenv("DISCORD_WEBHOOK_URL")
    if url:
        try:
            requests.post(url,json={"content":text[:1900]},timeout=10)  # Discord limit is 2000 chars
        except Exception as e:
            print(f"alert failed: {e}")