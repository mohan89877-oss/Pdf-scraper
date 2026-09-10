import sys
import json
from pathlib import Path
from quota_manager import QuotaManager
from llm_clients import call_gemini_resolve
import os

# ----------------------------------------------------------------------
# Model used for the knowledge‑check (resolution) step
# ----------------------------------------------------------------------
MODEL = "gemini-2.5-flash-lite"
MODEL_ID = "gemini-2.5-flash-lite"


def main(pdf_stem):
    state_dir = Path("state") / pdf_stem

    # Load flagged items (disagreements between the two Gemini extractors)
    flagged = json.loads((state_dir / "flagged.json").read_text())
    accepted_file = state_dir / "accepted.json"
    accepted = json.loads(accepted_file.read_text())

    # Load progress (which flagged items have already been resolved)
    progress_file = state_dir / "resolve_progress.json"
    progress = (
        json.loads(progress_file.read_text())
        if progress_file.exists()
        else {"resolved_idx": []}
    )

    review_log = Path("review.log")
    qm = QuotaManager()
    gemini_key = os.environ["GEMINI_API_KEY"]

    for i, item in enumerate(flagged):
        if i in progress["resolved_idx"]:
            continue

        if not qm.can_call(MODEL):
            print(
                "Knowledge‑check quota reached for today — stopping, will resume next run."
            )
            break
        if not qm.register_call(MODEL):
            break

        # The two readings come from the two Gemini extractors
        g1 = item.get("gemini_1")
        g2 = item.get("gemini_2")

        if g1 and g2:
            # Ask Gemini to pick the better reading
            result = call_gemini_resolve(MODEL_ID, g1, g2, gemini_key)
            if result["choice"] == "A":
                accepted.append(g1)
            elif result["choice"] == "B":
                accepted.append(g2)
            else:
                # Could not decide → log for manual review
                with review_log.open("a") as f:
                    f.write(
                        f"[{pdf_stem}] q_no {item['q_no']}: unresolved — {result['reason']}\n"
                        f"  gemini_1: {json.dumps(g1)}\n  gemini_2: {json.dumps(g2)}\n\n"
                    )
        else:
            # Only one extractor produced a result (should not happen, but be safe)
            only = g1 or g2
            with review_log.open("a") as f:
                f.write(
                    f"[{pdf_stem}] q_no {item['q_no']}: only found by one extractor, needs check\n"
                    f"  reading: {json.dumps(only)}\n\n"
                )

        # Record that we have resolved this item
        progress["resolved_idx"].append(i)
        progress_file.write_text(json.dumps(progress, indent=2))
        accepted_file.write_text(json.dumps(accepted, indent=2))

    # Final flag: all flagged items resolved?
    is_complete = len(progress["resolved_idx"]) == len(flagged)
    (state_dir / "resolve_complete.flag").write_text("1" if is_complete else "0")


if __name__ == "__main__":
    main(sys.argv[1])
