"""Voice note -> saved entry (type is auto-detected).
Usage: python parse_voice.py "recording.mp3"
"""
from _cli import run

if __name__ == "__main__":
    run("Standard recording 1.mp3", "Auto-Detect", is_audio=True)
