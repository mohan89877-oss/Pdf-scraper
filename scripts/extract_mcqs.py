import time
import json
import sys
from pathlib import Path

# Configuration constants
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds
GEMINI_MODEL = "gemini-2.0-flash"
MISTRAL_MODEL = "mistral-large-latest"
MISTRAL_MODEL_ID = "mistral-large-latest"

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

def call_gemini(model, text, api_key):
    """Call Gemini API to extract MCQs"""
    # TODO: Implement Gemini API call
    pass

def call_mistral(model_id, text, api_key):
    """Call Mistral API to extract MCQs"""
    # TODO: Implement Mistral API call
    pass

def main():
    """Main entry point for MCQ extraction"""
    if len(sys.argv) < 2:
        print("Usage: python extract_mcqs.py <pdf_stem>")
        sys.exit(1)
    
    stem = sys.argv[1]
    state_dir = Path("state") / stem
    
    # TODO: Implement the main extraction logic here
    # 1. Read extracted text from state/stem/text.txt
    # 2. Call Gemini and Mistral APIs with retry logic
    # 3. Save MCQs to output
    # 4. Create state/stem/extract_complete.flag with content "1"
    
    extract_flag = state_dir / "extract_complete.flag"
    extract_flag.write_text("1")

if __name__ == "__main__":
    main()
