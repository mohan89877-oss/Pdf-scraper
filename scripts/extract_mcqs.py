import time
import json
import sys
import os
from pathlib import Path
from llm_clients import call_gemini
from quota_manager import QuotaManager

# ----------------------------------------------------------------------
# Configuration – we now use Gemini for *both* extractors
# ----------------------------------------------------------------------
GEMINI_MODEL = "gemini-3.5-flash-lite"
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds


def call_with_retry(api_call_fn, model_name, *args, **kwargs):
    """Retry API calls with exponential back‑off on rate‑limit errors."""
    for attempt in range(MAX_RETRIES):
        try:
            return api_call_fn(*args, **kwargs)
        except Exception as e:
            error_msg = str(e)
            # 429 or rate_limit in the message → back‑off
            if "429" in error_msg or "rate_limit" in error_msg.lower():
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_DELAY * (2 ** attempt)
                    print(
                        f"Rate limit hit for {model_name}. Retrying in {wait_time}s... "
                        f"(attempt {attempt + 1}/{MAX_RETRIES})"
                    )
                    time.sleep(wait_time)
                    continue
            raise


def extract_mcqs_from_text(pages, state_dir, pdf_stem):
    """
    Extract MCQs using **two Gemini calls** (both REQUIRED).
    Saves results to state/{stem}/extracted.json and creates accepted/flagged lists.
    """
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key:
        print("ERROR: GEMINI_API_KEY not set in environment")
        return False

    qm = QuotaManager()

    # ------------------------------------------------------------------
    # Combine all page text
    # ------------------------------------------------------------------
    full_text = "\n\n".join([p["text"] for p in pages])
    print(f"Extracting MCQs from {len(pages)} pages ({len(full_text)} chars)...")

    # ------------------------------------------------------------------
    # First Gemini call
    # ------------------------------------------------------------------
    gemini_results_1 = []
    if qm.can_call(GEMINI_MODEL):
        if qm.register_call(GEMINI_MODEL):
            try:
                print(f"Calling {GEMINI_MODEL} (call #1)…")
                gemini_results_1 = call_with_retry(
                    call_gemini, GEMINI_MODEL, GEMINI_MODEL, full_text, gemini_key
                )
                print(f"  → Extracted {len(gemini_results_1)} questions from Gemini #1")
            except Exception as e:
                print(f"ERROR calling Gemini #1: {e}")
                return False
        else:
            print("Gemini quota exhausted for today")
            return False
    else:
        print("Gemini quota exhausted for today")
        return False

    # ------------------------------------------------------------------
    # Second Gemini call
    # ------------------------------------------------------------------
    gemini_results_2 = []
    if qm.can_call(GEMINI_MODEL):
        if qm.register_call(GEMINI_MODEL):
            try:
                print(f"Calling {GEMINI_MODEL} (call #2)…")
                gemini_results_2 = call_with_retry(
                    call_gemini, GEMINI_MODEL, GEMINI_MODEL, full_text, gemini_key
                )
                print(f"  → Extracted {len(gemini_results_2)} questions from Gemini #2")
            except Exception as e:
                print(f"ERROR calling Gemini #2: {e}")
                return False
        else:
            print("Gemini quota exhausted for today")
            return False
    else:
        print("Gemini quota exhausted for today")
        return False

    # ------------------------------------------------------------------
    # Merge results: if both extractors found the same question (by q_no),
    # flag it for review; otherwise accept it as‑is.
    # ------------------------------------------------------------------
    accepted = []
    flagged = []

    # Index by q_no for quick comparison
    g1_by_qno = {q["q_no"]: q for q in gemini_results_1}
    g2_by_qno = {q["q_no"]: q for q in gemini_results_2}

    all_qnos = set(g1_by_qno.keys()) | set(g2_by_qno.keys())

    for q_no in sorted(all_qnos):
        g1 = g1_by_qno.get(q_no)
        g2 = g2_by_qno.get(q_no)

        if g1 and g2:
            # Both found it — check if they agree
            if g1 == g2:
                accepted.append(g1)
            else:
                # Disagreement — flag for manual review via knowledge_check.py
                flagged.append({"q_no": q_no, "gemini_1": g1, "gemini_2": g2})
        elif g1:
            accepted.append(g1)
        elif g2:
            accepted.append(g2)

    # ------------------------------------------------------------------
    # Save results
    # ------------------------------------------------------------------
    extracted_file = state_dir / "extracted.json"
    extracted_file.write_text(
        json.dumps(
            {"gemini_1": gemini_results_1, "gemini_2": gemini_results_2},
            indent=2,
        )
    )
    print(f"Saved extraction results to {extracted_file}")

    accepted_file = state_dir / "accepted.json"
    accepted_file.write_text(json.dumps(accepted, indent=2))
    print(f"Saved {len(accepted)} accepted questions to {accepted_file}")

    flagged_file = state_dir / "flagged.json"
    flagged_file.write_text(json.dumps(flagged, indent=2))
    print(f"Saved {len(flagged)} flagged questions to {flagged_file}")

    # Initialise resolve progress
    progress_file = state_dir / "resolve_progress.json"
    progress_file.write_text(json.dumps({"resolved_idx": []}, indent=2))

    return True


def main():
    """Entry point for the MCQ extraction step."""
    if len(sys.argv) < 2:
        print("Usage: python extract_mcqs.py <pdf_stem>")
        sys.exit(1)

    stem = sys.argv[1]
    state_dir = Path("state") / stem

    # Load the previously extracted pages
    pages_file = state_dir / "pages.json"
    if not pages_file.exists():
        print(f"ERROR: {pages_file} not found. Run extract_text.py first.")
        sys.exit(1)

    pages = json.loads(pages_file.read_text())
    print(f"Loaded {len(pages)} pages from {pages_file}")

    # Run the extraction
    success = extract_mcqs_from_text(pages, state_dir, stem)

    # Mark extraction as complete (flag = 1 on success, 0 on failure)
    extract_flag = state_dir / "extract_complete.flag"
    extract_flag.write_text("1" if success else "0")
    print(f"Extraction complete flag written to {extract_flag}")


if __name__ == "__main__":
    main()
