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

# New-style "AQ." keys are rejected on some accounts (401 ACCESS_TOKEN_TYPE_UNSUPPORTED).
# If that happens to you, try GEMINI_USE_VERTEX=true in .env to send the key through Google's Vertex AI route.
USE_VERTEX = os.getenv("GEMINI_USE_VERTEX", "").strip().lower() in ("1", "true", "yes")
gemini = genai.Client(vertexai=True, api_key=GEMINI_API_KEY) if USE_VERTEX else genai.Client(api_key=GEMINI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def clean_json_text(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    return re.sub(r"\s*```$", "", text)


AUDIO_MIME = {"mp3": "audio/mp3", "wav": "audio/wav", "m4a": "audio/aac", "aac": "audio/aac",
              "ogg": "audio/ogg", "flac": "audio/flac"}
MAX_AUDIO_BYTES = 15 * 1024 * 1024


def audio_part(path: str):
    """Send the audio inside the request itself. The separate Files API needs a different kind of
    credential than a normal API key, and a short voice note doesn't need it."""
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if ext not in AUDIO_MIME:
        raise ValueError(f"Unsupported audio type '.{ext}'. Use mp3, wav, aac, ogg or flac.")
    if os.path.getsize(path) > MAX_AUDIO_BYTES:
        raise ValueError("This voice note is too large (limit 15 MB). Record a shorter one.")
    with open(path, "rb") as f:
        return types.Part.from_bytes(data=f.read(), mime_type=AUDIO_MIME[ext])


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
    if "ACCESS_TOKEN_TYPE_UNSUPPORTED" in str(last_err):
        raise RuntimeError(
            "Google rejected the Gemini API key (401 ACCESS_TOKEN_TYPE_UNSUPPORTED). This is a key or account problem, "
            "not a problem with your receipt. Update google-genai, create a fresh key in a NEW project in AI Studio, "
            "or try GEMINI_USE_VERTEX=true."
        )
    raise RuntimeError(f"Gemini couldn't read this file ({type(last_err).__name__}: {last_err})")