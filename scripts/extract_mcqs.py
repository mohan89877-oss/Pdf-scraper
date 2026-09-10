import time
import json
import sys
import os
from pathlib import Path
from llm_clients import call_gemini, call_mistral
from quota_manager import QuotaManager

# Configuration constants
GEMINI_MODEL = "gemini-2.0-flash-lite"
MISTRAL_MODEL = "mistral-large-latest"
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds


def call_with_retry(api_call_fn, model_name, *args, **kwargs):
    """Retry API calls with exponential backoff on rate limit errors."""
    for attempt in range(MAX_RETRIES):
        try:
            return api_call_fn(*args, **kwargs)
        except Exception as e:
            error_msg = str(e)
            # Check if it's a rate limit error (429)
            if "429" in error_msg or "rate_limit" in error_msg.lower():
                if attempt < MAX_RETRIES - 1:
                    wait_time = RETRY_DELAY * (2 ** attempt)  # exponential backoff
                    print(f"Rate limit hit for {model_name}. Retrying in {wait_time}s... (attempt {attempt + 1}/{MAX_RETRIES})")
                    time.sleep(wait_time)
                    continue
            raise


def extract_mcqs_from_text(pages, state_dir, pdf_stem):
    """
    Extract MCQs using Gemini and Mistral APIs (both REQUIRED).
    Saves results to state/{stem}/extracted.json and creates flagged/accepted lists.
    """
    gemini_key = os.environ.get("GEMINI_API_KEY")
    mistral_key = os.environ.get("MISTRAL_API_KEY")
    
    # Check that BOTH keys are present (mandatory)
    if not gemini_key:
        print("ERROR: GEMINI_API_KEY not set in environment")
        return False
    
    if not mistral_key:
        print("ERROR: MISTRAL_API_KEY not set in environment (REQUIRED)")
        return False
    
    qm = QuotaManager()
    
    # Combine all page text
    full_text = "\n\n".join([p["text"] for p in pages])
    
    print(f"Extracting MCQs from {len(pages)} pages ({len(full_text)} chars)...")
    
    gemini_results = []
    mistral_results = []
    
    # Call Gemini (REQUIRED)
    if qm.can_call(GEMINI_MODEL):
        if qm.register_call(GEMINI_MODEL):
            try:
                print(f"Calling {GEMINI_MODEL}...")
                gemini_results = call_with_retry(
                    call_gemini, GEMINI_MODEL,
                    GEMINI_MODEL, full_text, gemini_key
                )
                print(f"  → Extracted {len(gemini_results)} questions from Gemini")
            except Exception as e:
                print(f"ERROR calling Gemini: {e}")
                return False
    else:
        print(f"Gemini quota exhausted for today")
        return False
    
    # Call Mistral (REQUIRED - NOT OPTIONAL)
    if qm.can_call(MISTRAL_MODEL):
        if qm.register_call(MISTRAL_MODEL):
            try:
                print(f"Calling {MISTRAL_MODEL}...")
                mistral_results = call_with_retry(
                    call_mistral, MISTRAL_MODEL,
                    MISTRAL_MODEL, full_text, mistral_key
                )
                print(f"  → Extracted {len(mistral_results)} questions from Mistral")
            except Exception as e:
                print(f"ERROR calling Mistral: {e}")
                return False
    else:
        print(f"Mistral quota exhausted for today")
        return False
    
    # Merge results: if both extractors found the same question (by q_no), flag it for review
    # Otherwise accept it as-is
    accepted = []
    flagged = []
    
    # Index by q_no for comparison
    gemini_by_qno = {q["q_no"]: q for q in gemini_results}
    mistral_by_qno = {q["q_no"]: q for q in mistral_results}
    
    all_qnos = set(gemini_by_qno.keys()) | set(mistral_by_qno.keys())
    
    for q_no in sorted(all_qnos):
        g = gemini_by_qno.get(q_no)
        m = mistral_by_qno.get(q_no)
        
        if g and m:
            # Both found it — check if they agree
            if g == m:
                accepted.append(g)
            else:
                # Disagreement — flag for manual review via knowledge_check.py
                flagged.append({"q_no": q_no, "gemini": g, "mistral": m})
        elif g:
            accepted.append(g)
        elif m:
            accepted.append(m)
    
    # Save results
    extracted_file = state_dir / "extracted.json"
    extracted_file.write_text(json.dumps({
        "gemini": gemini_results,
        "mistral": mistral_results,
    }, indent=2))
    print(f"Saved extraction results to {extracted_file}")
    
    accepted_file = state_dir / "accepted.json"
    accepted_file.write_text(json.dumps(accepted, indent=2))
    print(f"Saved {len(accepted)} accepted questions to {accepted_file}")
    
    flagged_file = state_dir / "flagged.json"
    flagged_file.write_text(json.dumps(flagged, indent=2))
    print(f"Saved {len(flagged)} flagged questions to {flagged_file}")
    
    # Initialize resolve progress
    progress_file = state_dir / "resolve_progress.json"
    progress_file.write_text(json.dumps({"resolved_idx": []}, indent=2))
    
    return True


def main():
    """Main entry point for MCQ extraction"""
    if len(sys.argv) < 2:
        print("Usage: python extract_mcqs.py <pdf_stem>")
        sys.exit(1)
    
    stem = sys.argv[1]
    state_dir = Path("state") / stem
    
    # Read extracted pages
    pages_file = state_dir / "pages.json"
    if not pages_file.exists():
        print(f"ERROR: {pages_file} not found. Run extract_text.py first.")
        sys.exit(1)
    
    pages = json.loads(pages_file.read_text())
    print(f"Loaded {len(pages)} pages from {pages_file}")
    
    # Extract MCQs
    success = extract_mcqs_from_text(pages, state_dir, stem)
    
    # Mark extraction as complete
    extract_flag = state_dir / "extract_complete.flag"
    extract_flag.write_text("1" if success else "0")
    print(f"Extraction complete: {extract_flag}")


if __name__ == "__main__":
    main()
