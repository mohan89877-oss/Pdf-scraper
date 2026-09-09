import requests
import time
import json
import os

SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "q_no": {"type": "integer"},
                    "question": {"type": "string"},
                    "options": {
                        "type": "object",
                        "properties": {
                            "a": {"type": "string"}, "b": {"type": "string"},
                            "c": {"type": "string"}, "d": {"type": "string"},
                        },
                        "required": ["a", "b", "c", "d"],
                    },
                    "answer": {"type": "string", "enum": ["a", "b", "c", "d"]},
                },
                "required": ["q_no", "question", "options", "answer"],
            },
        }
    },
    "required": ["questions"],
}

EXTRACT_PROMPT = """You are extracting multiple-choice questions from raw text pulled from a PDF (may include OCR noise).

Rules:
- Find every MCQ: question number, question text, 4 options (a-d), and the correct answer.
- The correct answer may be marked inline (e.g. an asterisk next to an option) or listed separately elsewhere in this text as an answer key. Match answer-key entries to their question by number.
- Do NOT include explanations, even if present in the source text.
- If you cannot confidently determine the answer for a question, omit that question entirely rather than guessing.
- Output must be valid JSON matching the given schema. Do not invent questions not present in the text.

TEXT:
{text}
"""


def _backoff_retry(fn, max_tries=5):
    for attempt in range(max_tries):
        try:
            resp = fn()
            if resp.status_code == 429 or resp.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            return resp
        except requests.RequestException:
            time.sleep(2 ** attempt)
    raise RuntimeError("Max retries exceeded")


def call_gemini(model, text, api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    body = {
        "contents": [{"parts": [{"text": EXTRACT_PROMPT.format(text=text)}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "response_schema": SCHEMA,
            "temperature": 0,
        },
    }
    resp = _backoff_retry(lambda: requests.post(url, json=body, timeout=120))
    data = resp.json()
    raw = data["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(raw).get("questions", [])


def call_groq(model, text, api_key):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    body = {
        "model": model,
        "messages": [{"role": "user", "content": EXTRACT_PROMPT.format(text=text)
                       + "\n\nRespond with a JSON object: {\"questions\": [...]}"}],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    resp = _backoff_retry(lambda: requests.post(url, headers=headers, json=body, timeout=120))
    data = resp.json()
    raw = data["choices"][0]["message"]["content"]
    return json.loads(raw).get("questions", [])


def call_gemini_resolve(model, item_a, item_b, api_key):
    """Knowledge-based resolution for a disputed question between two extractor outputs."""
    prompt = f"""Two automated extractors read the same source text differently. Using general
subject knowledge, decide which reading (A or B) is internally coherent and has a correct
marked answer among its options. If you cannot confidently decide, say "unresolved".

Reading A: {json.dumps(item_a)}
Reading B: {json.dumps(item_b)}

Respond with JSON: {{"choice": "A" | "B" | "unresolved", "reason": "one short sentence"}}
"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0},
    }
    resp = _backoff_retry(lambda: requests.post(url, json=body, timeout=60))
    data = resp.json()
    raw = data["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(raw)
