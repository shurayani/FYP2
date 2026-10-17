"""Wrapper for every call to the Gemini AI API (Section 5.3 / 5.6.3 / 5.6.8).
Uses the public REST endpoint through `requests`, HTTPS only. The key comes from the environment."""
import base64
import json
import re

import requests

from utils.config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_TIMEOUT

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class NetworkError(Exception):
    pass


class QuotaError(Exception):
    pass


class ParseError(Exception):
    pass


def is_configured() -> bool:
    return bool(GEMINI_API_KEY)


def _call(parts, json_mode=False, timeout=None):
    if not GEMINI_API_KEY:
        raise NetworkError("GEMINI_API_KEY is not set")
    body = {"contents": [{"parts": parts}]}
    if json_mode:
        body["generationConfig"] = {"responseMimeType": "application/json", "temperature": 0}
    try:
        r = requests.post(ENDPOINT.format(model=GEMINI_MODEL), json=body,
                          headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
                          timeout=timeout or GEMINI_TIMEOUT)
    except (requests.ConnectionError, requests.Timeout) as e:
        raise NetworkError(str(e))
    if r.status_code in (429, 403):
        raise QuotaError(f"HTTP {r.status_code}")
    if r.status_code != 200:
        raise NetworkError(f"HTTP {r.status_code}")
    try:
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, ValueError):
        raise ParseError("Unexpected Gemini response")


def extract_receipt_fields(jpeg_bytes: bytes) -> dict:
    """Send the (resized, compressed) receipt image and get merchant / date / total back as JSON."""
    prompt = ("You are reading a Malaysian retail receipt. Return ONLY a JSON object with keys: "
              '"merchant" (store name, string), "date" (YYYY-MM-DD), "amount" (grand total paid in MYR, number). '
              "Use null for anything you cannot read.")
    parts = [{"text": prompt},
             {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(jpeg_bytes).decode()}}]
    text = _call(parts, json_mode=True)
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        data = json.loads(text)
    except ValueError:
        raise ParseError("Gemini returned invalid JSON")
    if not isinstance(data, dict):
        raise ParseError("Gemini returned unexpected JSON")
    return data


def generate_insights(summary: dict, language: str = "English") -> str:
    """Optional written spending insights / budget tips from the forecast summary (FR11)."""
    prompt = (f"You are a friendly personal-finance coach for a Malaysian university student. Reply in {language}. "
              "Based on this JSON spending summary (amounts in MYR) give 3-5 short bullet points: key insight, "
              "categories likely to exceed budget next month, and one practical budget tip. "
              "No preamble.\n\n" + json.dumps(summary))
    return _call([{"text": prompt}], timeout=max(GEMINI_TIMEOUT, 20)).strip()
