# modules/utils.py

import streamlit as st
import requests
from PIL import Image
import io
import time
import json
from typing import List
from constants import SITE_DOMAINS

# Use Streamlit secrets if deployed, otherwise use local config file
if hasattr(st, 'secrets'):
    AZURE_ENDPOINT = st.secrets["AZURE_ENDPOINT"]
    AZURE_KEY = st.secrets["AZURE_KEY"]
else:
    from config import AZURE_ENDPOINT, AZURE_KEY


def extract_text_from_image(image_file):
    """Performs OCR on an uploaded image using Azure Vision."""
    img = Image.open(image_file).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    headers = {
        "Ocp-Apim-Subscription-Key": AZURE_KEY,
        "Content-Type": "application/octet-stream"
    }
    resp = requests.post(f"{AZURE_ENDPOINT}/vision/v3.2/read/analyze",
                         headers=headers, data=buf.getvalue())
    if resp.status_code != 202:
        st.error("🛑 OCR submission failed.")
        return []
    op_url = resp.headers["Operation-Location"]
    for _ in range(15):
        r2 = requests.get(op_url, headers={"Ocp-Apim-Subscription-Key": AZURE_KEY}).json()
        if r2.get("status") == "succeeded":
            break
        time.sleep(1)
    lines = r2.get("analyzeResult", {}).get("readResults", [{}])[0].get("lines", [])
    return [l["text"] for l in lines]

def get_primary_domain(site_preference: str) -> str:
    """Gets the primary domain for a given site preference."""
    domain_map = {
        "walmart": "walmart.com",
        "amazon": "amazon.com",
        "target": "target.com",
        "best buy": "bestbuy.com"
    }
    return domain_map.get(site_preference.lower(), "")

def get_site_domains(site_preference: str) -> List[str]:
    """Gets all possible domains for a given site preference."""
    return SITE_DOMAINS.get(site_preference.lower(), [])