"""Shared setup: env loading, Gemini + Supabase clients, retrying JSON generation."""
import json
import os
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from google import genai
from google.genai import types
from supabase import create_client

load_dotenv()

# Servers (e.g. Streamlit Cloud) usually run in UTC, which gives the wrong date late at night in India.
TZ = ZoneInfo(os.getenv("APP_TIMEZONE", "Asia/Kolkata"))

# Override with GEMINI_MODELS="model-a,model-b" in .env. Run check_models.py to see what your key can use.
MODELS = [m.strip() for m in os.getenv("GEMINI_MODELS", "gemini-3.8-flash,gemini-3.5-flash-lite").split(",") if m.strip()]

RETRYABLE = ("429", "500", "503", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "INTERNAL", "DEADLINE")


def now_local() -> datetime:
    return datetime.now(TZ)


def _require(name: str) -> str:
    value = (os.getenv(name) or "").strip().strip('"').strip("'")
    if not value:
        raise RuntimeError(f"{name} is missing. Add it to your .env file.")
    return value


GEMINI_API_KEY = _require("GEMINI_API_KEY")
SUPABASE_URL = _require("SUPABASE_URL").rstrip("/")
SUPABASE_KEY = _require("SUPABASE_KEY")

gemini = genai.Client(api_key=GEMINI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def clean_json_text(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    return re.sub(r"\s*```$", "", text)


def upload_media(path: str):
    """Upload an audio file and wait until Gemini has finished processing it."""
    f = gemini.files.upload(file=path)
    for _ in range(30):
        state = getattr(getattr(f, "state", None), "name", None)
        if state != "PROCESSING":
            break
        time.sleep(2)
        f = gemini.files.get(name=f.name)
    if getattr(getattr(f, "state", None), "name", None) == "FAILED":
        raise RuntimeError("Gemini could not process the audio file.")
    return f


def delete_media(f) -> None:
    try:
        gemini.files.delete(name=f.name)
    except Exception:
        pass


def generate_json(contents: list, prompt: str) -> dict:
    """Try each model in turn. Retry only on temporary errors; surface the real error if all fail."""
    last_err = None
    for model in MODELS:
        for attempt in range(1, 4):
            try:
                resp = gemini.models.generate_content(
                    model=model,
                    contents=[*contents, prompt],
                    config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0),
                )
                data = json.loads(clean_json_text(resp.text))
                if isinstance(data, list):
                    data = data[0] if data and isinstance(data[0], dict) else {}
                if not isinstance(data, dict) or not data:
                    raise ValueError("Model did not return a JSON object")
                return data
            except json.JSONDecodeError as err:
                last_err = err  # malformed output: just ask again
            except Exception as err:
                last_err = err
                if any(tok in str(err) for tok in RETRYABLE):
                    time.sleep(attempt * 3)
                    continue
                break  # bad model name, bad key, bad request: retrying won't help, try the next model
    raise RuntimeError(f"Gemini couldn't read this file ({type(last_err).__name__}: {last_err})")
