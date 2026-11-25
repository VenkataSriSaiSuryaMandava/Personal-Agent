"""Construct fixed public provider endpoints.

This module does not execute network requests.
"""

from aegis.schemas.discovery import JobSourceInput


def source_endpoint(source: JobSourceInput) -> str:
    source = JobSourceInput.model_validate(
        source.model_dump()
    )

    board = source.board

    if source.provider == "greenhouse":
        return (
            "https://boards-api.greenhouse.io"
            "/v1/boards/" + board + "/jobs?content=true"
        )

    if source.provider == "lever":
        return (
            "https://api.lever.co"
            "/v0/postings/" + board + "?mode=json"
        )

    if source.provider == "ashby":
        return (
            "https://api.ashbyhq.com"
            "/posting-api/job-board/" + board
        )

    raise ValueError("Unsupported job provider")
