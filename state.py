import json
import os
from pathlib import Path
import hashlib

STATE_FILE = Path(__file__).parent / "state.json"
PROCESSED_FILE = Path(__file__).parent / "processed.json"


def save_json(file_path, data):
    temporary_file = file_path.with_suffix(f"{file_path.suffix}.tmp")

    with open(temporary_file, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)

    os.replace(temporary_file, file_path)


def load_state():
    if not STATE_FILE.exists():
        return {}

    with open(STATE_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def save_state(state):
    save_json(STATE_FILE, state)


def get_text_hash(text):
    normalized_text = " ".join(text.lower().split())
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


def load_processed():
    if not PROCESSED_FILE.exists():
        return set()

    with open(PROCESSED_FILE, "r", encoding="utf-8") as file:
        return set(json.load(file))


def save_processed(processed):
    save_json(PROCESSED_FILE, list(processed))


def mark_as_processed(text_hash):
    processed = load_processed()
    processed.add(text_hash)
    save_processed(processed)
