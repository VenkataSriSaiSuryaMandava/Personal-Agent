"""Explicit execution of bounded, local workflow capabilities."""

from threading import BoundedSemaphore

from pydantic import ValidationError

from aegis.services.agents.permissions import (
    CapabilityDenied,
    authorize_local_capability,
)
from aegis.services.agents.registry import resolve_capability
from aegis.storage import workflows as storage
from aegis.storage.settings import load_settings


EXECUTION_SLOT = BoundedSemaphore(1)


class WorkflowBusy(Exception):
    pass


def execute_workflow(
    user_id,
    run_id,
    path,
    *,
    reauthorize,
    handlers,
):
    """Execute using trusted server-provided handlers.

    The caller must supply a current identity check and
    a server-selected database path. Neither is supplied
    by a model or an untrusted request payload.
    """

    if not EXECUTION_SLOT.acquire(blocking=False):
        raise WorkflowBusy()

    try:
        reauthorize()

        run = storage.get_workflow(
            user_id, run_id, path,
        )

        if run["status"] in storage.TERMINAL_STATES:
            return run

        if (
            run["definition_version"] != 1
            or len(run["steps"]) != 1
        ):
            raise CapabilityDenied(
                "Unsupported workflow definition"
            )

        expected = storage.WORKFLOW_CAPABILITIES.get(
            run["workflow_type"]
        )

        step = run["steps"][0]

        if expected != step["capability"]:
            raise CapabilityDenied(
                "Invalid workflow capability"
            )

        capability = authorize_local_capability(
            expected,
            emergency_stop=load_settings(path)
                .settings.emergency_stop,
            scoped_grant=True,
        )

        if (
            capability.version != step["capability_version"]
            or not capability.retry_safe
            or expected not in handlers
        ):
            raise CapabilityDenied(
                "Capability unavailable"
            )

        reauthorize()

        claimed = storage.claim_workflow(
            user_id, run_id, path,
        )

        if claimed is None:
            return storage.get_workflow(
                user_id, run_id, path,
            )

        output = None
        error = None

        try:
            reauthorize()

            authorize_local_capability(
                expected,
                emergency_stop=load_settings(path)
                    .settings.emergency_stop,
                scoped_grant=True,
            )

            current = resolve_capability(
                claimed["capability"]
            )

            if (
                current.name != expected
                or current.version
                    != claimed["capability_version"]
            ):
                raise CapabilityDenied(
                    "Capability changed"
                )

            parameters = current.input_model.model_validate_json(
                claimed["input_payload"]
            )

            input_field = (
                "source_id"
                if expected == "career.company_summary"
                else "listing_id"
            )

            if str(getattr(parameters, input_field)) != run["target_id"]:
                raise CapabilityDenied(
                    "Invalid workflow target"
                )

            raw = handlers[expected](
                user_id, parameters, path,
            )

            result = current.output_model.model_validate(raw)

            output = result.model_dump(mode="json")

            try:
                storage.encode_payload(output)
            except ValueError:
                output = None
                error = "result_limit"

        except CapabilityDenied:
            output = None
            error = "permission_denied"

        except ValidationError:
            output = None
            error = "invalid_contract"

        except LookupError:
            output = None
            error = "target_unavailable"

        except Exception:
            output = None
            error = "operation_failed"

        # A revoked or expired session cannot persist a
        # successful result. Its lease can be recovered later.
        reauthorize()

        try:
            authorize_local_capability(
                expected,
                emergency_stop=load_settings(path)
                    .settings.emergency_stop,
                scoped_grant=True,
            )

        except CapabilityDenied:
            output = None
            error = "permission_denied"

        storage.finish_workflow(
            user_id,
            run_id,
            claimed["id"],
            claimed["lease_token"],
            path,
            output=output,
            error_code=error,
        )

        return storage.get_workflow(
            user_id, run_id, path,
        )

    finally:
        EXECUTION_SLOT.release()
