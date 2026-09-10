import json
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

STATE_FILE = Path("state/quota.json")

# ---- Confirmed from AI Studio rate-limit dashboard / Mistral help center, Sep 2026. ----
# Re-check periodically — these values can change without notice.
SAFETY_MARGIN = 0.8

LIMITS = {
    "gemini-2.0-flash": {"rpm": 10, "rpd": 500},
    "gemini-2.0-flash-lite": {"rpm": 10, "rpd": 500},
    "gemini-2.5-flash-lite": {"rpm": 10, "rpd": 20},
    "gemini-3.5-flash-lite": {"rpm": 10, "rpd": 500},
    "mistral-large-latest": {"rpm": 50, "rpd": 2000},
    "mistral-small":         {"rpm": 50, "rpd": 2000},
}


def _today_key():
    # Provider daily quotas reset at midnight US Pacific.
    return datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")


class QuotaManager:
    def __init__(self, path=STATE_FILE):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.state = self._load()
        self._last_call_ts = {}

    def _load(self):
        if self.path.exists():
            data = json.loads(self.path.read_text())
        else:
            data = {}
        today = _today_key()
        if data.get("date") != today:
            data = {"date": today, "used": {}}
        return data

    def _save(self):
        self.path.write_text(json.dumps(self.state, indent=2))

    def can_call(self, model):
        limit = LIMITS[model]
        cap = int(limit["rpd"] * SAFETY_MARGIN)
        used = self.state["used"].get(model, 0)
        return used < cap

    def register_call(self, model):
        """Call this right before making an API call. Paces RPM and records usage.
        Returns False if today's safety-margin budget is exhausted (caller should stop)."""
        if not self.can_call(model):
            return False

        limit = LIMITS[model]
        min_gap = 60.0 / (limit["rpm"] * SAFETY_MARGIN)
        last = self._last_call_ts.get(model, 0)
        wait = min_gap - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
        self._last_call_ts[model] = time.time()

        self.state["used"][model] = self.state["used"].get(model, 0) + 1
        self._save()
        return True

    def remaining(self, model):
        cap = int(LIMITS[model]["rpd"] * SAFETY_MARGIN)
        return cap - self.state["used"].get(model, 0)
