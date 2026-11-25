"""Bounded public job-board HTTPS transport."""

import http.client
import json
import ssl
import sys

from urllib.parse import urlsplit

from aegis.schemas.discovery import (
    JobSourceInput,
    MAX_RESPONSE_BYTES,
    REQUEST_TIMEOUT,
)

from aegis.services.job_sources import source_endpoint


class TransportRejected(Exception):
    pass


ALLOWED_HOSTS = frozenset({
    "boards-api.greenhouse.io",
    "api.lever.co",
    "api.ashbyhq.com",
})


def download(source):
    endpoint = urlsplit(source_endpoint(source))

    if (
        endpoint.scheme != "https"
        or endpoint.netloc not in ALLOWED_HOSTS
        or endpoint.fragment
        or endpoint.port is not None
    ):
        raise TransportRejected()

    target = endpoint.path

    if endpoint.query:
        target += "?" + endpoint.query

    connection = http.client.HTTPSConnection(
        endpoint.hostname,
        port=443,
        timeout=REQUEST_TIMEOUT,
        context=ssl.create_default_context(),
    )

    try:
        connection.request(
            "GET",
            target,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "User-Agent": "AegisAI/JobDiscovery",
                "Connection": "close",
            },
        )

        response = connection.getresponse()

        # Redirects are deliberately not followed.
        if response.status != 200:
            raise TransportRejected()

        content_types = response.headers.get_all(
            "Content-Type", [],
        )

        if len(content_types) != 1:
            raise TransportRejected()

        media = content_types[0].split(
            ";", 1,
        )[0].strip().lower()

        if media != "application/json":
            raise TransportRejected()

        encodings = response.headers.get_all(
            "Content-Encoding", [],
        )

        if encodings and encodings != ["identity"]:
            raise TransportRejected()

        lengths = response.headers.get_all(
            "Content-Length", [],
        )

        declared = None

        if lengths:
            if (
                len(lengths) != 1
                or not lengths[0].isascii()
                or not lengths[0].isdecimal()
                or len(lengths[0]) > 10
            ):
                raise TransportRejected()

            declared = int(lengths[0])

            if not 1 <= declared <= MAX_RESPONSE_BYTES:
                raise TransportRejected()

        transfers = response.headers.get_all(
            "Transfer-Encoding", [],
        )

        if transfers and (
            lengths
            or len(transfers) != 1
            or transfers[0].strip().lower() != "chunked"
        ):
            raise TransportRejected()

        body = bytearray()

        while True:
            remaining = MAX_RESPONSE_BYTES - len(body)

            chunk = response.read(
                min(65536, remaining + 1)
            )

            if not chunk:
                break

            body.extend(chunk)

            if len(body) > MAX_RESPONSE_BYTES:
                raise TransportRejected()

        if not body:
            raise TransportRejected()

        if declared is not None and len(body) != declared:
            raise TransportRejected()

        return bytes(body)

    finally:
        connection.close()


def main():
    try:
        raw = sys.stdin.buffer.read(4097)

        if not 1 <= len(raw) <= 4096:
            return 1

        payload = json.loads(raw)

        if (
            not isinstance(payload, dict)
            or set(payload) != {"provider", "board"}
        ):
            return 1

        source = JobSourceInput(
            provider=payload["provider"],
            board=payload["board"],
            company="Public employer",
        )

        result = download(source)

        sys.stdout.buffer.write(result)
        sys.stdout.buffer.flush()

        return 0

    except Exception:
        # Provider error bodies and network details are not exposed.
        return 1


if __name__ == "__main__":
    sys.exit(main())
