import base64
import io

import pytest

from pypdf import PdfWriter

from aegis.services.resume_parser import (
    parse_resume, DocumentRejected,
)
from aegis.storage import career
from aegis.storage.database import connect

BASE = "/api/v1/career"


def upload(client, data=b"Synthetic resume experience"):
    return client.post(
        BASE + "/resumes",
        json={
            "title": "Synthetic resume",
            "media_type": "text/plain",
            "document": base64.b64encode(data).decode(),
        },
    )


def test_profile_api(authenticated_environment):
    client, _, _, _, _ = authenticated_environment

    initial = client.get(BASE + "/profile")
    assert initial.status_code == 200

    snapshot = initial.json()
    assert snapshot["revision"] == 0

    payload = {
        **snapshot["profile"],
        "full_name": "Synthetic Candidate",
        "skills": ["Python", "SQL"],
        "expected_revision": 0,
    }

    saved = client.patch(BASE + "/profile", json=payload)

    assert saved.status_code == 200
    assert saved.json()["revision"] == 1

    assert client.patch(
        BASE + "/profile", json=payload,
    ).status_code == 409

    assert client.get(
        BASE + "/profile",
    ).json() == saved.json()


def test_document_api(authenticated_environment):
    client, _, _, _, _ = authenticated_environment

    result = upload(client)

    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"

    document = result.json()
    identifier = document["id"]

    assert document["revision"] == 1
    assert document["extracted_text"] == (
        "Synthetic resume experience"
    )

    assert upload(client).status_code == 409

    listing = client.get(BASE + "/resumes").json()

    assert len(listing["resumes"]) == 1
    assert "document" not in listing["resumes"][0]
    assert "extracted_text" not in listing["resumes"][0]

    assert client.get(
        BASE + "/resume",
        params={"id": identifier},
    ).json() == document

    action = {
        "id": identifier,
        "action": "edit",
        "expected_revision": 1,
        "extracted_text": "Reviewed synthetic text",
    }

    edited = client.post(BASE + "/resume", json=action)

    assert edited.status_code == 200
    assert edited.json()["revision"] == 2

    assert client.post(
        BASE + "/resume", json=action,
    ).status_code == 409

    downloaded = client.get(
        BASE + "/download",
        params={"id": identifier},
    )

    assert downloaded.status_code == 200
    assert downloaded.content == b"Synthetic resume experience"
    assert downloaded.headers["cache-control"] == "no-store"
    assert downloaded.headers["content-type"] == (
        "application/octet-stream"
    )
    assert downloaded.headers["content-disposition"] == (
        'attachment; filename="resume.txt"'
    )

    removal = {
        "id": identifier,
        "action": "delete",
        "expected_revision": 2,
    }

    assert client.post(
        BASE + "/resume", json=removal,
    ).status_code == 200

    assert client.get(
        BASE + "/download",
        params={"id": identifier},
    ).status_code == 404


@pytest.mark.parametrize("method,path", [
    ("GET", "/profile"),
    ("PATCH", "/profile"),
    ("GET", "/resumes"),
    ("POST", "/resumes"),
    ("GET", "/resume"),
    ("POST", "/resume"),
    ("GET", "/download"),
])
def test_career_requires_session(
    authenticated_environment, method, path,
):
    client, _, _, _, _ = authenticated_environment

    response = client.request(
        method,
        BASE + path,
        headers={"Authorization": ""},
    )

    assert response.status_code == 401


@pytest.mark.parametrize("method,path", [
    ("GET", "/profile"),
    ("PATCH", "/profile"),
    ("POST", "/resumes"),
    ("POST", "/resume"),
    ("GET", "/download"),
])
def test_career_rejects_origin(
    authenticated_environment, method, path,
):
    client, _, _, _, _ = authenticated_environment

    assert client.request(
        method,
        BASE + path,
        headers={"Origin": "https://example.invalid"},
    ).status_code == 403


def test_invalid_documents(authenticated_environment):
    client, _, _, path, _ = authenticated_environment

    for data in ("not base64", "AA=="):
        response = client.post(
            BASE + "/resumes",
            json={
                "title": "Synthetic",
                "media_type": "text/plain",
                "document": data,
            },
        )

        assert response.status_code == 422

    assert career.list_resumes(1, path) == []


def test_invalid_queries(authenticated_environment):
    client, _, _, _, _ = authenticated_environment

    for path in (
        "/profile?unexpected=1",
        "/resumes?unexpected=1",
        "/resume?id=invalid",
        "/download?id=invalid",
        "/download?id=invalid&id=invalid",
    ):
        assert client.get(BASE + path).status_code == 422


def test_duplicate_json_rejected(authenticated_environment):
    client, _, _, _, _ = authenticated_environment

    assert client.patch(
        BASE + "/profile",
        content='{"expected_revision":0,"expected_revision":1}',
        headers={"Content-Type": "application/json"},
    ).status_code == 422


def test_profile_body_limit(authenticated_environment):
    client, _, _, _, _ = authenticated_environment

    assert client.patch(
        BASE + "/profile",
        content=b"x" * (2 * 1024 * 1024 + 1),
        headers={"Content-Type": "application/json"},
    ).status_code == 413


def test_upload_revocation_during_parse(
    authenticated_environment, monkeypatch,
):
    client, service, token, path, _ = authenticated_environment

    def parse_and_revoke(data, media):
        service.logout(token)
        return "Synthetic"

    monkeypatch.setattr(
        career, "parse_resume", parse_and_revoke,
    )

    assert upload(client).status_code == 401
    assert career.list_resumes(1, path) == []


def test_pdf_parse():
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)

    buffer = io.BytesIO()
    writer.write(buffer)

    assert parse_resume(
        buffer.getvalue(), "application/pdf",
    ) == ""


def test_encrypted_pdf_rejected():
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("synthetic-document-password")

    buffer = io.BytesIO()
    writer.write(buffer)

    with pytest.raises(DocumentRejected):
        parse_resume(
            buffer.getvalue(), "application/pdf",
        )


def test_audit_failure_rolls_back_resume(
    authenticated_environment,
):
    client, _, _, path, _ = authenticated_environment

    with connect(path) as c:
        c.execute("""
            CREATE TRIGGER reject_career_audit
            BEFORE INSERT ON career_audit_events
            BEGIN
                SELECT RAISE(ABORT, 'Synthetic failure');
            END
        """)

    assert upload(client).status_code == 503
    assert career.list_resumes(1, path) == []
