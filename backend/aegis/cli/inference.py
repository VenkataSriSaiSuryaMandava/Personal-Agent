import argparse
import os

from aegis.schemas.inference import InferenceRequest

from aegis.security.prompts import PromptId

from aegis.security.gateway import (
    GatewayDenied,
    ProviderUnavailable,
)

from aegis.security.rate_limit import (
    RateLimitExceeded,
    UsageStorageUnavailable,
)

from aegis.services.inference import (
    ALLOWED_MODEL,
    run_inference,
)


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
        default=ALLOWED_MODEL,
        choices=[ALLOWED_MODEL],
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

    try:

        result = run_inference(
            InferenceRequest(
                prompt_id=PromptId(args.prompt),
                approved=True,
            ),
            requested_model=args.model,
        )

        safe_output = "".join(
            char
            if char.isprintable() or char == "\n"
            else repr(char)[1:-1]
            for char in result.message
        )

        print(safe_output)

        return 0

    except RateLimitExceeded:

        print("Inference usage limit reached.")
        return 1

    except UsageStorageUnavailable:

        print("Secure usage storage unavailable.")
        return 1

    except (
        GatewayDenied,
        ProviderUnavailable,
        ValueError,
    ):

        print("Inference blocked or unavailable.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
