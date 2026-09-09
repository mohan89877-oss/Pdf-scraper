import sys
import json
from pathlib import Path
from quota_manager import QuotaManager
from llm_clients import call_gemini_resolve
import os

MODEL = "gemini-2.5-flash-lite"
MODEL_ID = "gemini-2.5-flash-lite"


def main(pdf_stem):
    state_dir = Path("state") / pdf_stem
    flagged = json.loads((state_dir / "flagged.json").read_text())
    accepted_file = state_dir / "accepted.json"
    accepted = json.loads(accepted_file.read_text())

    progress_file = state_dir / "resolve_progress.json"
    progress = json.loads(progress_file.read_text()) if progress_file.exists() else {"resolved_idx": []}

    review_log = Path("review.log")
    qm = QuotaManager()
    gemini_key = os.environ["GEMINI_API_KEY"]

    for i, item in enumerate(flagged):
        if i in progress["resolved_idx"]:
            continue
        if not qm.can_call(MODEL):
            print("Knowledge-check quota reached for today — stopping, will resume next run.")
            break
        if not qm.register_call(MODEL):
            break

        g, r = item.get("gemini"), item.get("groq")
        if g and r:
            result = call_gemini_resolve(MODEL_ID, g, r, gemini_key)
            if result["choice"] == "A":
                accepted.append(g)
            elif result["choice"] == "B":
                accepted.append(r)
            else:
                with review_log.open("a") as f:
                    f.write(f"[{pdf_stem}] q_no {item['q_no']}: unresolved — {result['reason']}\n"
                            f"  gemini: {json.dumps(g)}\n  groq: {json.dumps(r)}\n\n")
        else:
            only = g or r
            with review_log.open("a") as f:
                f.write(f"[{pdf_stem}] q_no {item['q_no']}: only found by one extractor, needs check\n"
                        f"  reading: {json.dumps(only)}\n\n")

        progress["resolved_idx"].append(i)
        progress_file.write_text(json.dumps(progress, indent=2))
        accepted_file.write_text(json.dumps(accepted, indent=2))

    is_complete = len(progress["resolved_idx"]) == len(flagged)
    (state_dir / "resolve_complete.flag").write_text("1" if is_complete else "0")


if __name__ == "__main__":
    main(sys.argv[1])
