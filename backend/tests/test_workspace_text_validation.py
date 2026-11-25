import pytest

from aegis.schemas.workspaces import (
    WorkspaceRecord,
    validate_record,
)


@pytest.mark.parametrize("notes", [
    "First line\nSecond line",
    "First line\r\nSecond line",
    "Column one\tColumn two",
    "Ordinary notes",
])
def test_valid_workspace_notes(notes):
    record = WorkspaceRecord(
        title="Synthetic application",
        status="saved",
        notes=notes,
    )

    result = validate_record("jobs", record)

    assert result.notes == notes


@pytest.mark.parametrize("separator", [
    "\n",
    "\r",
    "\t",
])
def test_multiline_titles_rejected(separator):
    record = WorkspaceRecord(
        title=f"First{separator}Second",
        status="saved",
    )

    with pytest.raises(
        ValueError,
        match="Title must be single-line",
    ):
        validate_record("jobs", record)


@pytest.mark.parametrize("character", [
    "\x00",
    "\x01",
    "\x07",
    "\x0b",
    "\x0c",
    "\x1b",
    "\x7f",
    "\x85",
])
def test_unsafe_control_characters_rejected(character):
    record = WorkspaceRecord(
        title="Synthetic application",
        status="saved",
        notes=f"Before{character}After",
    )

    with pytest.raises(
        ValueError,
        match="Invalid text character",
    ):
        validate_record("jobs", record)


def test_literal_backslash_text_preserved():
    notes = r"Example literal \n and \t text"

    record = WorkspaceRecord(
        title=r"Example \n notation",
        status="saved",
        notes=notes,
    )

    assert validate_record(
        "jobs", record,
    ).notes == notes
