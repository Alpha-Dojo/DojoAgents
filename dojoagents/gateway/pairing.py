import json
import secrets
import string
import time
from pathlib import Path
from typing import Any

class PairingStore:
    def __init__(self, filepath: str = "~/.dojo/gateway/pairing.json") -> None:
        self.filepath = Path(filepath).expanduser()
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self.data: dict[str, Any] = {
            "approved": {},
            "pending": [],
            "failures": 0,
            "last_code_request": {},
        }
        self.load()

    def load(self) -> None:
        if self.filepath.exists():
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                pass
        # Ensure correct structure
        self.data.setdefault("approved", {})
        self.data.setdefault("pending", [])
        self.data.setdefault("failures", 0)
        self.data.setdefault("last_code_request", {})

    def save(self) -> None:
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def generate_code(self, platform: str, user_id: str, user_name: str) -> str:
        # Enforce rate limit (1 code request per 10 minutes)
        now = time.time()
        key = f"{platform}:{user_id}"
        last_req = self.data["last_code_request"].get(key, 0.0)
        if now - last_req < 600:  # 10 minutes
            raise ValueError("Rate limit exceeded. Try again in 10 minutes.")

        # Generate a cryptographically random 8-character code
        alphabet = string.ascii_uppercase + string.digits
        code = "".join(secrets.choice(alphabet) for _ in range(8))

        # Check if code already exists, regenerate if so
        existing_codes = {p["code"] for p in self.data["pending"]}
        while code in existing_codes:
            code = "".join(secrets.choice(alphabet) for _ in range(8))

        # Remove any existing pending requests for this user on this platform
        self.data["pending"] = [
            p for p in self.data["pending"]
            if not (p["platform"] == platform and p["user_id"] == user_id)
        ]

        # Add new pending request
        self.data["pending"].append({
            "platform": platform,
            "user_id": user_id,
            "user_name": user_name,
            "code": code,
            "created_at": now,
        })
        self.data["last_code_request"][key] = now
        self.save()
        return code

    def approve_code(self, platform: str, code: str) -> bool:
        if self.data.get("failures", 0) >= 5:
            raise ValueError("Lockout: Too many failed validation attempts.")

        # Find code in pending for the platform
        pending_item = None
        for item in self.data["pending"]:
            if item["platform"] == platform and item["code"] == code:
                pending_item = item
                break

        if pending_item is None:
            self.data["failures"] = self.data.get("failures", 0) + 1
            self.save()
            if self.data["failures"] >= 5:
                raise ValueError("Lockout: Too many failed validation attempts.")
            return False

        # Reset failures on successful validation
        self.data["failures"] = 0

        # Approve user
        user_id = pending_item["user_id"]
        approved_list = self.data["approved"].setdefault(platform, [])
        if user_id not in approved_list:
            approved_list.append(user_id)

        # Remove code from pending
        self.data["pending"] = [
            p for p in self.data["pending"]
            if not (p["platform"] == platform and p["code"] == code)
        ]
        self.save()
        return True

    def deny_code(self, platform: str, code: str) -> bool:
        original_len = len(self.data["pending"])
        self.data["pending"] = [
            p for p in self.data["pending"]
            if not (p["platform"] == platform and p["code"] == code)
        ]
        self.save()
        return len(self.data["pending"]) < original_len

    def is_approved(self, platform: str, user_id: str) -> bool:
        approved_list = self.data["approved"].get(platform, [])
        return user_id in approved_list

    def list_pending(self, platform: str | None = None) -> list[dict]:
        if platform:
            return [p for p in self.data["pending"] if p["platform"] == platform]
        return self.data["pending"]
