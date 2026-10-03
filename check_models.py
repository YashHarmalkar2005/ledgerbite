"""List the Gemini models your API key can use. Put the names you want in .env as GEMINI_MODELS=a,b"""
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
key = (os.getenv("GEMINI_API_KEY") or "").strip()
if not key:
    raise SystemExit("GEMINI_API_KEY is missing from .env")

client = genai.Client(api_key=key)
print("Available models on your API key:\n")
for m in client.models.list():
    print(f" - {(m.name or str(m)).replace('models/', '')}")
