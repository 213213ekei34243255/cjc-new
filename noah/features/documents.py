"""Feature 8 - personalised document checklist (the widget turns it into a printable PDF)."""

import json

from .. import config

_cache = None


def _data():
    global _cache
    if _cache is None:
        _cache = json.loads((config.DATA_DIR / "checklists.json").read_text(encoding="utf-8"))
    return _cache


def options():
    d = _data()
    return {"boards": d["boards"], "programs": [{"id": "pu", "label": "Pre-University (1st PUC)"},
                                                 {"id": "ibdp", "label": "IB Diploma (IBDP)"}]}


def checklist(program, board):
    d = _data()
    if program not in ("pu", "ibdp"):
        raise ValueError("unknown program")
    boards = {b["id"] for b in d["boards"]}
    if board not in boards:
        raise ValueError("unknown board")
    prog = d[program]
    items = [dict(i) for i in prog["items"]]
    if program == "pu" and board != "state":
        items.append(dict(prog["non_state"]))
    out = {"program": program, "board": board, "title": prog["title"], "items": items,
           "steps": prog["steps"], "footer": prog["footer"]}
    if prog.get("link_url"):
        out["link"] = {"label": prog["link_label"], "url": prog["link_url"]}
    out["board_label"] = next(b["label"] for b in d["boards"] if b["id"] == board)
    return out
