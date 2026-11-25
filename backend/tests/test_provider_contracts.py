import json

import pytest

from aegis.schemas.discovery import JobSourceInput
from aegis.services.job_adapters import (
    normalize_response,
    greenhouse_description,
    normalize_ashby,
    SourceResponseRejected,
)


@pytest.mark.parametrize("content", [
    "<p>Python developer</p>",
    "&lt;p&gt;Python developer&lt;/p&gt;",
    "&amp;lt;p&amp;gt;Python developer&amp;lt;/p&amp;gt;",
])
def test_greenhouse_encoded_description(content):
    assert greenhouse_description(content) == "Python developer"


def test_encoded_script_content_removed():
    assert greenhouse_description(
        "&lt;script&gt;unsafe&lt;/script&gt;"
        "&lt;p&gt;Safe description&lt;/p&gt;"
    ) == "Safe description"


@pytest.mark.parametrize("total", [
    1, -1, True, "0", None,
])
def test_incomplete_greenhouse_snapshot(total):
    source = JobSourceInput(
        provider="greenhouse",
        board="synthetic",
        company="Synthetic",
    )

    raw = json.dumps({
        "jobs": [],
        "meta": {"total": total},
    }).encode()

    with pytest.raises(SourceResponseRejected):
        normalize_response(source, raw)


@pytest.mark.parametrize("workplace,expected", [
    ("Remote", "remote"),
    ("Hybrid", "hybrid"),
    ("OnSite", "onsite"),
    (None, "unknown"),
])
def test_ashby_workplace_classification(
    workplace, expected,
):
    listing = normalize_ashby({
        "id": "synthetic",
        "title": "Software Engineer",
        "jobUrl": "https://jobs.ashbyhq.com/example/synthetic",
        "isRemote": True,
        "workplaceType": workplace,
    })

    assert listing.work_mode == expected
