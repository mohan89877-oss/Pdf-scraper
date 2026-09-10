import time
import json
from pathlib import Path

# Add at the top of the file
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

# Then update the main function (lines 85 and 89):
if not qm.register_call(GEMINI_MODEL):
    break
gemini_qs = call_with_retry(call_gemini, GEMINI_MODEL, GEMINI_MODEL, text, gemini_key)

if not qm.register_call(MISTRAL_MODEL):
    break
mistral_qs = call_with_retry(call_mistral, MISTRAL_MODEL, MISTRAL_MODEL_ID, text, mistral_key)
