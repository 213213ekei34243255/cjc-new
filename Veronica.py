"""
Veronica.py - compatibility shim.

The answering logic now lives in the `noah` package (noah/brain.py): Gemini is the main model and
Qwen is the backup. This module keeps the old names alive so nothing that imported them breaks:

    get_veronica_response(user_question, session_id, knowledge_base=None) -> str
    load_knowledge_base(path) / save_knowledge_base(path, data)

Run `python Veronica.py` for a quick console chat.
"""

import json
from typing import Dict, Optional


def load_knowledge_base(file_path: str) -> dict:
    try:
        with open(file_path, "r", encoding="utf-8-sig") as file:
            text = file.read()
        return json.loads(text) if text.strip() else {"questions": []}     # the shipped file is empty
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
    except json.JSONDecodeError:
        print(f"Error: Unable to parse JSON file '{file_path}'.")
    return {"questions": []}


def save_knowledge_base(file_path: str, data: dict) -> None:
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def get_veronica_response(user_question: str, session_id: str, knowledge_base: Optional[Dict] = None) -> str:
    # `knowledge_base` is accepted only for backward compatibility and is ignored.
    from noah import brain
    return brain.respond(brain.Ctx(text=user_question, sid=session_id)).answer


if __name__ == "__main__":
    while True:
        q = input("You: ")
        if q.lower() == "quit":
            break
        print("Noah:", get_veronica_response(q, session_id="test-session"))
