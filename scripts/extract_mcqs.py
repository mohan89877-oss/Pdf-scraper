import sys
import json
from pathlib import Path
from quota_manager import QuotaManager
from llm_clients import call_gemini, call_mistral
import os

CHARS_PER_CHUNK = 12000   # ~3-4k tokens, keeps things comfortably safe
OVERLAP_PAGES = 2

GEMINI_MODEL = "gemini-3.5-flash-lite"
MISTRAL_MODEL = "mistral-small"
MISTRAL_MODEL_ID = "mistral-small-latest"


def build_chunks(pages):
    chunks = []
    current, current_len, start_idx = [], 0, 0
    for i, p in enumerate(pages):
        current.append(p)
        current_len += len(p["text"])
        if current_len >= CHARS_PER_CHUNK:
            chunks.append(current)
            # overlap: carry last OVERLAP_PAGES pages into next chunk
            current = current[-OVERLAP_PAGES:]
            current_len = sum(len(p["text"]) for p in current)
    if current:
        chunks.append(current)
    return chunks


def normalize(q):
    return {
        "q_no": q.get("q_no"),
        "question": (q.get("question") or "").strip().lower(),
        "options": {k: (v or "").strip().lower() for k, v in q.get("options", {}).items()},
        "answer": (q.get("answer") or "").strip().lower(),
    }


def diff_and_merge(gemini_qs, mistral_qs, accepted, flagged):
    by_no_g = {q["q_no"]: q for q in gemini_qs if q.get("q_no") is not None}
    by_no_m = {q["q_no"]: q for q in mistral_qs if q.get("q_no") is not None}
    all_nos = set(by_no_g) | set(by_no_m)

    for no in all_nos:
        g, m = by_no_g.get(no), by_no_m.get(no)
        if g and m and normalize(g) == normalize(m):
            accepted.append(g)
        elif g and m:
            flagged.append({"q_no": no, "gemini": g, "mistral": m})
        else:
            # only one model found it at all — not a verified match, flag it
            flagged.append({"q_no": no, "gemini": g, "mistral": m})


def main(pdf_stem):
    state_dir = Path("state") / pdf_stem
    pages = json.loads((state_dir / "pages.json").read_text())
    chunks = build_chunks(pages)

    progress_file = state_dir / "extract_progress.json"
    progress = json.loads(progress_file.read_text()) if progress_file.exists() else {"done_chunks": []}

    accepted_file = state_dir / "accepted.json"
    flagged_file = state_dir / "flagged.json"
    accepted = json.loads(accepted_file.read_text()) if accepted_file.exists() else []
    flagged = json.loads(flagged_file.read_text()) if flagged_file.exists() else []

    qm = QuotaManager()
    gemini_key = os.environ["GEMINI_API_KEY"]
    mistral_key = os.environ["MISTRAL_API_KEY"]

    for idx, chunk in enumerate(chunks):
        if idx in progress["done_chunks"]:
            continue
        if not qm.can_call(GEMINI_MODEL) or not qm.can_call(MISTRAL_MODEL):
            print("Quota budget reached for today — stopping cleanly, will resume next run.")
            break

        text = "\n".join(f"[page {p['page']}]\n{p['text']}" for p in chunk)

        if not qm.register_call(GEMINI_MODEL):
            break
        gemini_qs = call_gemini(GEMINI_MODEL, text, gemini_key)

        if not qm.register_call(MISTRAL_MODEL):
            break
        mistral_qs = call_mistral(MISTRAL_MODEL_ID, text, mistral_key)

        diff_and_merge(gemini_qs, mistral_qs, accepted, flagged)

        progress["done_chunks"].append(idx)
        progress_file.write_text(json.dumps(progress, indent=2))
        accepted_file.write_text(json.dumps(accepted, indent=2))
        flagged_file.write_text(json.dumps(flagged, indent=2))
        print(f"Chunk {idx+1}/{len(chunks)} done. Accepted so far: {len(accepted)}, flagged: {len(flagged)}")

    is_complete = len(progress["done_chunks"]) == len(chunks)
    (state_dir / "extract_complete.flag").write_text("1" if is_complete else "0")


if __name__ == "__main__":
    main(sys.argv[1])
