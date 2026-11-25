import io
import zipfile

import pytest

from aegis.schemas.career import (
    CareerProfile,
    ResumeMetadata,
)

from aegis.services.resume_parser import (
    DocumentRejected,
    parse_resume,
)

from aegis.storage import career
from aegis.storage.database import connect

DOCX = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.document"
)

META = ResumeMetadata(
    title="Synthetic resume",
    media_type="text/plain",
)


def test_profile_lifecycle(authenticated_environment):
    _, _, _, path, _ = authenticated_environment

    assert career.get_profile(1, path)["revision"] == 0

    profile = CareerProfile(
        full_name="Synthetic Candidate",
        skills=["Python", "SQL", "Python"],
    )

    saved = career.save_profile(1, profile, 0, path)

    assert saved["revision"] == 1
    assert saved["profile"]["skills"] == ["Python", "SQL"]
    assert career.get_profile(1, path) == saved

    assert career.save_profile(
        1, profile, 1, path
    ) == saved

    with pytest.raises(career.CareerConflict):
        career.save_profile(1, profile, 0, path)

    assert career.get_profile(2, path)["revision"] == 0


def test_invalid_salary():
    with pytest.raises(ValueError):
        CareerProfile(salary_min=100, salary_max=50)


def test_text_parser():
    assert parse_resume(
        b"Synthetic Python experience",
        "text/plain",
    ) == "Synthetic Python experience"


def test_docx_parser():
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/'
            'wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>Synthetic resume</w:t>'
            '</w:r></w:p></w:body></w:document>',
        )

    assert parse_resume(
        buffer.getvalue(), DOCX
    ) == "Synthetic resume"


@pytest.mark.parametrize("data,media_type", [
    (b"invalid", "application/pdf"),
    (b"invalid", DOCX),
    (b"\xff\xfe\x00", "text/plain"),
    (b"invalid\x00text", "text/plain"),
    (b"", "text/plain"),
    (b"example", "application/octet-stream"),
    (b"x" * 100001, "text/plain"),
])
def test_invalid_documents(data, media_type):
    with pytest.raises(DocumentRejected):
        parse_resume(data, media_type)


def test_docx_rejects_external_entity():
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(
            "word/document.xml",
            '<!DOCTYPE x [<!ENTITY example "Synthetic">]>'
            '<x>&example;</x>',
        )

    with pytest.raises(DocumentRejected):
        parse_resume(buffer.getvalue(), DOCX)


def test_resume_lifecycle(authenticated_environment):
    _, _, _, path, _ = authenticated_environment

    first = career.create_resume(
        1, META, b"First synthetic resume", path
    )

    second = career.create_resume(
        1, META, b"Second synthetic resume", path
    )

    assert first["is_active"] == 1
    assert second["is_active"] == 0

    selected = career.activate_resume(
        1, second["id"], path
    )

    assert selected["is_active"] == 1

    assert career.get_resume(
        1, first["id"], path
    )["is_active"] == 0

    edited = career.update_resume_text(
        1, second["id"], "Reviewed text", path
    )

    assert edited["extracted_text"] == "Reviewed text"

    original, media = career.download_resume(
        1, second["id"], path
    )

    assert original == b"Second synthetic resume"
    assert media == "text/plain"

    assert all(
        "document" not in row
        and "extracted_text" not in row
        for row in career.list_resumes(1, path)
    )

    with pytest.raises(career.CareerConflict):
        career.create_resume(
            1, META, original, path
        )

    career.delete_resume(1, second["id"], path)

    assert len(career.list_resumes(1, path)) == 1

    with pytest.raises(career.CareerNotFound):
        career.get_resume(1, second["id"], path)


def test_resume_owner_isolation(
    authenticated_environment,
):
    _, _, _, path, _ = authenticated_environment

    saved = career.create_resume(
        1, META, b"Synthetic private document", path
    )

    assert career.list_resumes(2, path) == []

    for action in (
        career.get_resume,
        career.download_resume,
        career.activate_resume,
        career.delete_resume,
    ):
        with pytest.raises(career.CareerNotFound):
            action(2, saved["id"], path)

    with pytest.raises(career.CareerNotFound):
        career.update_resume_text(
            2, saved["id"], "Denied", path
        )


def test_resume_limit(
    authenticated_environment, monkeypatch,
):
    _, _, _, path, _ = authenticated_environment

    monkeypatch.setattr(
        career, "parse_resume",
        lambda data, media: data.decode(),
    )

    for index in range(20):
        career.create_resume(
            1, META,
            f"Synthetic version {index}".encode(),
            path,
        )

    with pytest.raises(career.CareerConflict):
        career.create_resume(
            1, META, b"Version 21", path
        )

    assert len(career.list_resumes(1, path)) == 20


def test_audit_contains_no_private_content(
    authenticated_environment,
):
    _, _, _, path, _ = authenticated_environment

    career.create_resume(
        1, META, b"Private synthetic text", path
    )

    with connect(path) as c:
        rows = [
            dict(row)
            for row in c.execute(
                "SELECT * FROM career_audit_events"
            )
        ]

    assert len(rows) == 1
    assert rows[0]["event_type"] == "created"
    assert "Private synthetic text" not in str(rows)
    assert "Synthetic resume" not in str(rows)
