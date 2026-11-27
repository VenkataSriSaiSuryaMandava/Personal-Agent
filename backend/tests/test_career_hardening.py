import io
import sqlite3
import subprocess
import zipfile

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)

from aegis.schemas.career import ResumeMetadata
from aegis.services import resume_parser
from aegis.storage import career
from aegis.storage.database import connect
from aegis.storage.migrations import initialize_database

META = ResumeMetadata(
    title="Synthetic resume",
    media_type="text/plain",
)

DOCX = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.document"
)


def test_pdf_extracts_real_text():
    writer = PdfWriter()
    page = writer.add_blank_page(
        width=612, height=792,
    )

    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })

    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({
            NameObject("/F1"): font,
        }),
    })

    stream = DecodedStreamObject()

    stream.set_data(
        b"BT /F1 12 Tf 72 720 Td "
        b"(Synthetic Python developer) Tj ET"
    )

    page[NameObject("/Contents")] = stream

    buffer = io.BytesIO()
    writer.write(buffer)

    result = resume_parser.parse_resume(
        buffer.getvalue(), "application/pdf",
    )

    assert "Synthetic Python developer" in result


def test_parser_timeout_releases_slot(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd="synthetic-parser",
            timeout=15,
        )

    with monkeypatch.context() as patch:
        patch.setattr(
            resume_parser.subprocess,
            "run",
            timeout,
        )

        with pytest.raises(
            resume_parser.DocumentRejected
        ):
            resume_parser.parse_resume(
                b"Synthetic document",
                "text/plain",
            )

    assert resume_parser.parse_resume(
        b"Synthetic document",
        "text/plain",
    ) == "Synthetic document"


def test_parser_busy():
    assert resume_parser.PARSER_SLOT.acquire(
        blocking=False,
    )

    try:
        with pytest.raises(
            resume_parser.ParserBusy
        ):
            resume_parser.parse_resume(
                b"Synthetic document",
                "text/plain",
            )
    finally:
        resume_parser.PARSER_SLOT.release()


@pytest.mark.parametrize("entry", [
    "../unsafe.xml",
    "word/vbaProject.bin",
    "/absolute.xml",
])
def test_unsafe_docx_structure(entry):
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "[Content_Types].xml", "<Types/>"
        )
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/'
            'wordprocessingml/2006/main"/>',
        )
        archive.writestr(entry, "Synthetic")

    with pytest.raises(
        resume_parser.DocumentRejected
    ):
        resume_parser.parse_resume(
            buffer.getvalue(), DOCX,
        )


def test_concurrent_resume_edits(
    authenticated_environment,
):
    _, _, _, path, _ = authenticated_environment

    saved = career.create_resume(
        1, META, b"Synthetic original", path,
    )

    barrier = Barrier(2)

    def update(text):
        barrier.wait(timeout=5)

        try:
            career.update_resume_text(
                1,
                saved["id"],
                text,
                path,
                expected_revision=1,
            )
            return "saved"

        except career.CareerConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            update,
            ["First edit", "Second edit"],
        ))

    assert sorted(results) == [
        "conflict", "saved",
    ]

    current = career.get_resume(
        1, saved["id"], path,
    )

    assert current["revision"] == 2

    with pytest.raises(career.CareerConflict):
        career.delete_resume(
            1,
            saved["id"],
            path,
            expected_revision=1,
        )


def test_activation_invalidates_old_revision(
    authenticated_environment,
):
    _, _, _, path, _ = authenticated_environment

    first = career.create_resume(
        1, META, b"First synthetic resume", path,
    )

    second = career.create_resume(
        1, META, b"Second synthetic resume", path,
    )

    career.activate_resume(
        1,
        second["id"],
        path,
        expected_revision=1,
    )

    old = career.get_resume(
        1, first["id"], path,
    )

    assert old["is_active"] == 0
    assert old["revision"] == 2

    with pytest.raises(career.CareerConflict):
        career.activate_resume(
            1,
            first["id"],
            path,
            expected_revision=1,
        )


def test_migration_failure_rolls_back(
    authenticated_environment,
):
    _, _, _, path, _ = authenticated_environment

    with connect(path) as c:
        c.execute("DROP TABLE job_application_links")
        c.execute("DROP TABLE job_listings")
        c.execute("DROP TABLE job_sources")
        c.execute("DROP TABLE career_audit_events")
        c.execute("DROP TABLE career_profiles")

        # Keep resume_versions to simulate a schema
        # collision midway through migration.
        # Remove schema 9 tables from historical test fixture.
        c.execute("DROP TABLE workflow_events")
        c.execute("DROP TABLE workflow_steps")
        c.execute("DROP TABLE workflow_runs")
        c.execute("PRAGMA user_version = 6")

    with pytest.raises(sqlite3.OperationalError):
        initialize_database(path)

    with connect(path) as c:
        assert c.execute(
            "PRAGMA user_version"
        ).fetchone()[0] == 6

        assert c.execute("""
            SELECT COUNT(*) FROM sqlite_master
            WHERE name = 'career_profiles'
        """).fetchone()[0] == 0

        assert c.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0] == "ok"

        assert c.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0] == 1


def test_document_integrity_failure(
    authenticated_environment,
):
    _, _, _, path, _ = authenticated_environment

    saved = career.create_resume(
        1, META, b"Synthetic original", path,
    )

    with connect(path) as c:
        c.execute("""
            UPDATE resume_versions
            SET sha256 = ?
            WHERE id = ?
        """, ("0" * 64, saved["id"]))

    with pytest.raises(RuntimeError):
        career.download_resume(
            1, saved["id"], path,
        )


@pytest.mark.parametrize("method,endpoint", [
    ("GET", "profile"),
    ("PATCH", "profile"),
    ("GET", "resumes"),
    ("POST", "resumes"),
    ("GET", "resume"),
    ("POST", "resume"),
    ("GET", "download"),
])
def test_public_career_requires_authentication(
    method, endpoint, monkeypatch,
):
    from fastapi.testclient import TestClient
    from aegis.main import app

    monkeypatch.setenv("AEGIS_RUNTIME_MODE", "public")
    monkeypatch.setenv("AEGIS_GATEWAY_TOKEN", "a" * 64)

    with TestClient(app) as client:
        assert client.request(
            method,
            "/api/v1/career/" + endpoint,
            headers={"x-aegis-gateway-token": "a" * 64},
        ).status_code == 401
