import io
import json
import subprocess

from email.message import Message

import pytest

from aegis.schemas.discovery import JobSourceInput

from aegis.services import (
    job_fetcher,
    job_fetch_worker,
)


SOURCE = JobSourceInput(
    provider="greenhouse",
    board="synthetic",
    company="Private local label",
)


class FakeResponse:
    def __init__(
        self,
        status=200,
        body=b'{"jobs":[]}',
        headers=None,
    ):
        self.status = status
        self.stream = io.BytesIO(body)
        self.headers = Message()

        if headers is None:
            headers = [
                ("Content-Type", "application/json"),
                ("Content-Length", str(len(body))),
            ]

        for name, value in headers:
            self.headers[name] = value

    def read(self, size):
        return self.stream.read(size)


def mock_connection(monkeypatch, response):
    calls = {}

    class Connection:
        def __init__(self, host, **kwargs):
            calls["host"] = host
            calls["options"] = kwargs

        def request(self, method, target, headers):
            calls["method"] = method
            calls["target"] = target
            calls["headers"] = headers

        def getresponse(self):
            return response

        def close(self):
            calls["closed"] = True

    monkeypatch.setattr(
        job_fetch_worker.http.client,
        "HTTPSConnection",
        Connection,
    )

    return calls


@pytest.mark.parametrize("provider,host,target", [
    (
        "greenhouse",
        "boards-api.greenhouse.io",
        "/v1/boards/synthetic/jobs?content=true",
    ),
    (
        "lever",
        "api.lever.co",
        "/v0/postings/synthetic?mode=json",
    ),
    (
        "ashby",
        "api.ashbyhq.com",
        "/posting-api/job-board/synthetic",
    ),
])
def test_fixed_https_transport(
    monkeypatch, provider, host, target,
):
    calls = mock_connection(
        monkeypatch,
        FakeResponse(),
    )

    source = JobSourceInput(
        provider=provider,
        board="synthetic",
        company="Synthetic",
    )

    assert job_fetch_worker.download(
        source
    ) == b'{"jobs":[]}'

    assert calls["host"] == host
    assert calls["target"] == target
    assert calls["method"] == "GET"
    assert calls["options"]["port"] == 443

    context = calls["options"]["context"]

    assert context.check_hostname
    assert context.verify_mode != 0

    assert "Authorization" not in calls["headers"]
    assert "Cookie" not in calls["headers"]
    assert calls["headers"]["Accept-Encoding"] == "identity"
    assert calls["closed"]


@pytest.mark.parametrize("status", [
    301, 302, 307, 308, 401, 403,
    404, 429, 500, 503,
])
def test_non_success_rejected(
    monkeypatch, status,
):
    calls = mock_connection(
        monkeypatch,
        FakeResponse(status=status),
    )

    with pytest.raises(
        job_fetch_worker.TransportRejected,
    ):
        job_fetch_worker.download(SOURCE)

    assert calls["closed"]


@pytest.mark.parametrize("headers", [
    [],
    [("Content-Type", "text/html")],
    [
        ("Content-Type", "application/json"),
        ("Content-Type", "application/json"),
    ],
    [
        ("Content-Type", "application/json"),
        ("Content-Encoding", "gzip"),
    ],
    [
        ("Content-Type", "application/json"),
        ("Content-Length", "999999999"),
    ],
    [
        ("Content-Type", "application/json"),
        ("Content-Length", "-1"),
    ],
    [
        ("Content-Type", "application/json"),
        ("Content-Length", "1"),
        ("Content-Length", "2"),
    ],
    [
        ("Content-Type", "application/json"),
        ("Content-Length", "11"),
        ("Transfer-Encoding", "chunked"),
    ],
])
def test_invalid_response_headers(
    monkeypatch, headers,
):
    mock_connection(
        monkeypatch,
        FakeResponse(headers=headers),
    )

    with pytest.raises(
        job_fetch_worker.TransportRejected,
    ):
        job_fetch_worker.download(SOURCE)


def test_streaming_response_limit(monkeypatch):
    monkeypatch.setattr(
        job_fetch_worker,
        "MAX_RESPONSE_BYTES",
        16,
    )

    mock_connection(
        monkeypatch,
        FakeResponse(
            body=b"x" * 17,
            headers=[
                ("Content-Type", "application/json"),
            ],
        ),
    )

    with pytest.raises(
        job_fetch_worker.TransportRejected,
    ):
        job_fetch_worker.download(SOURCE)


def test_truncated_response(monkeypatch):
    mock_connection(
        monkeypatch,
        FakeResponse(headers=[
            ("Content-Type", "application/json"),
            ("Content-Length", "100"),
        ]),
    )

    with pytest.raises(
        job_fetch_worker.TransportRejected,
    ):
        job_fetch_worker.download(SOURCE)


def test_chunked_response(monkeypatch):
    mock_connection(
        monkeypatch,
        FakeResponse(headers=[
            ("Content-Type", "application/json"),
            ("Transfer-Encoding", "chunked"),
        ]),
    )

    assert job_fetch_worker.download(
        SOURCE
    ) == b'{"jobs":[]}'


def test_subprocess_privacy(monkeypatch):
    captured = {}

    monkeypatch.setenv(
        "AEGIS_GATEWAY_TOKEN",
        "synthetic-test-value",
    )

    def run(command, **kwargs):
        captured.update(kwargs)

        assert command[1:] == [
            "-I",
            "-m",
            "aegis.services.job_fetch_worker",
        ]

        return subprocess.CompletedProcess(
            command,
            0,
            stdout=b'{"jobs":[]}',
        )

    monkeypatch.setattr(
        job_fetcher.subprocess,
        "run",
        run,
    )

    assert job_fetcher.fetch_jobs(SOURCE) == []

    assert json.loads(captured["input"]) == {
        "provider": "greenhouse",
        "board": "synthetic",
    }

    assert captured["timeout"] == 15

    assert captured["env"] == {
        "PYTHONIOENCODING": "utf-8",
    }


def test_timeout_releases_slot(monkeypatch):
    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(
            command, kwargs["timeout"],
        )

    monkeypatch.setattr(
        job_fetcher.subprocess,
        "run",
        timeout,
    )

    with pytest.raises(
        job_fetcher.SourceFetchFailed,
    ):
        job_fetcher.fetch_jobs(SOURCE)

    acquired = 0

    try:
        for _ in range(3):
            assert job_fetcher.FETCH_SLOTS.acquire(
                blocking=False,
            )
            acquired += 1

    finally:
        for _ in range(acquired):
            job_fetcher.FETCH_SLOTS.release()


def test_concurrency_limit():
    acquired = 0

    try:
        for _ in range(3):
            assert job_fetcher.FETCH_SLOTS.acquire(
                blocking=False,
            )
            acquired += 1

        with pytest.raises(
            job_fetcher.SourceFetchBusy,
        ):
            job_fetcher.fetch_jobs(SOURCE)

    finally:
        for _ in range(acquired):
            job_fetcher.FETCH_SLOTS.release()


@pytest.mark.parametrize("code,output", [
    (1, b""),
    (0, b""),
    (0, b"invalid JSON"),
    (0, b'{"jobs":[null]}'),
])
def test_worker_failure_rejected(
    monkeypatch, code, output,
):
    monkeypatch.setattr(
        job_fetcher.subprocess,
        "run",
        lambda command, **kwargs:
            subprocess.CompletedProcess(
                command, code, stdout=output,
            ),
    )

    with pytest.raises(
        job_fetcher.SourceFetchFailed,
    ):
        job_fetcher.fetch_jobs(SOURCE)


def test_disabled_source_does_not_fetch(
    monkeypatch,
):
    def unexpected(*args, **kwargs):
        pytest.fail("Unexpected network request")

    monkeypatch.setattr(
        job_fetcher.subprocess,
        "run",
        unexpected,
    )

    disabled = SOURCE.model_copy(
        update={"enabled": False},
    )

    with pytest.raises(
        job_fetcher.SourceFetchFailed,
    ):
        job_fetcher.fetch_jobs(disabled)
