import argparse
import os

from aegis.models.gemini import GeminiProvider
from aegis.security.gateway import (
    GatewayContext,
    GatewayDenied,
    OutboundGateway,
    ProviderUnavailable,
)
from aegis.security.prompts import PromptId


def main():

    parser = argparse.ArgumentParser(
        description="Aegis controlled AI inference"
    )

    parser.add_argument(
        "--prompt",
        required=True,
        choices=[item.value for item in PromptId],
    )

    parser.add_argument(
        "--model",
        required=True,
    )

    parser.add_argument(
        "--approve",
        action="store_true",
    )

    args = parser.parse_args()

    if os.getenv("AEGIS_CLOUD_ENABLED") != "1":
        print("Cloud inference is disabled.")
        return 1

    if not args.approve:
        print("Explicit approval is required.")
        return 1

    key = os.getenv("GEMINI_API_KEY", "")

    if not key.strip():
        print("Gemini API key is not configured.")
        return 1

    try:
        provider = GeminiProvider(
            api_key=key,
            model=args.model,
        )

        gateway = OutboundGateway(
            provider,
            GatewayContext(
                cloud_enabled=True,
                scoped_grant=True,
                emergency_stop=(
                    os.getenv("AEGIS_EMERGENCY_STOP") == "1"
                ),
            ),
        )

        result = gateway.complete(
            PromptId(args.prompt)
        )

        # Escape control characters before terminal display.
        safe_output = "".join(
            char if char.isprintable() or char == "\n"
            else repr(char)[1:-1]
            for char in result
        )

        print(safe_output)

        return 0

    except (
        GatewayDenied,
        ProviderUnavailable,
        ValueError,
    ):
        print("Inference blocked or unavailable.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
