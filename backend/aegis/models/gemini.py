import json
import re
import urllib.request

from aegis.security.runtime_policy import ai_enabled


class RejectRedirects(urllib.request.HTTPRedirectHandler):

    def redirect_request(self, req, fp, code, msg,
                         headers, newurl):
        raise RuntimeError("Provider redirect rejected")


class GeminiProvider:

    BASE_URL = (
        "https://generativelanguage.googleapis.com/v1beta/models"
    )

    def __init__(self, api_key: str, model: str):

        if not api_key.strip():
            raise ValueError("Gemini API key is required")

        if not re.fullmatch(r"gemini-[a-zA-Z0-9.-]+", model):
            raise ValueError("Invalid Gemini model identifier")

        self._api_key = api_key
        self._model = model

        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            RejectRedirects(),
        )

    def complete(self, prompt: str) -> str:

        if not ai_enabled():
            raise RuntimeError(
                "AI is disabled in this deployment"
            )

        url = f"{self.BASE_URL}/{self._model}:generateContent"

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 1024,
            },
        }

        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self._api_key,
            },
            method="POST",
        )

        with self._opener.open(
            request,
            timeout=20,
        ) as response:

            raw = response.read(1_048_577)

        if len(raw) > 1_048_576:
            raise RuntimeError("Provider response too large")

        data = json.loads(raw)

        candidates = data.get("candidates", [])

        if not candidates:
            raise RuntimeError("No model response")

        parts = candidates[0].get(
            "content", {}
        ).get("parts", [])

        text = "\n".join(
            part["text"]
            for part in parts
            if isinstance(part.get("text"), str)
            and not part.get("thought", False)
        )

        if not text.strip():
            raise RuntimeError("Empty model response")

        return text
