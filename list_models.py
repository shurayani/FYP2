import os
import requests
from dotenv import load_dotenv

load_dotenv()
r = requests.get("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
                 headers={"x-goog-api-key": os.getenv("GEMINI_API_KEY", "")}, timeout=20)
for m in r.json().get("models", []):
    if "generateContent" in m.get("supportedGenerationMethods", []):
        print(m["name"].replace("models/", ""))