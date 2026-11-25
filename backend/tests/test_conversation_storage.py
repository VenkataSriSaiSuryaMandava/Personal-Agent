import pytest

from aegis.storage.database import connect
from aegis.storage.migrations import initialize_database
from aegis.storage.settings import (
    load_settings,
    save_settings,
)
from aegis.storage.conversations import (
    ConversationConflict,
    ConversationNotFound,
    RetentionDisabled,
    save_turn,
    list_conversations,
    get_conversation,
    rename_conversation,
    delete_conversation,
)


@pytest.fixture
def db(tmp_path):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)

    path = directory / "test.sqlite3"

    initialize_database(path)

    with connect(path) as connection:
        connection.execute(
            """
            INSERT INTO users (
                id, username, password_hash, created_at
            )
            VALUES (1, 'test-owner', 'synthetic', 1)
            """
        )

    return path


def set_retention(db, enabled):
    current = load_settings(db)

    updated = current.settings.model_copy(
        update={"retain_conversations": enabled}
    )

    save_settings(
        updated,
        current.revision,
        db,
    )


def create_chat(db):
    set_retention(db, True)

    return save_turn(
        1,
        "Explain binary search",
        "Synthetic response",
        path=db,
    )


def test_retention_disabled_by_default(db):
    with pytest.raises(RetentionDisabled):
        save_turn(
            1, "Question", "Answer", path=db
        )

    assert list_conversations(1, path=db) == []


def test_create_and_retrieve(db):
    conversation_id = create_chat(db)

    chat = get_conversation(
        1, conversation_id, db
    )

    assert chat["title"] == "Explain binary search"
    assert len(chat["turns"]) == 1
    assert chat["turns"][0]["assistant"] == (
        "Synthetic response"
    )


def test_append_turn(db):
    conversation_id = create_chat(db)

    save_turn(
        1,
        "Another question",
        "Another answer",
        conversation_id,
        1,
        db,
    )

    chat = get_conversation(
        1, conversation_id, db
    )

    assert len(chat["turns"]) == 2


def test_conflicting_append_rejected(db):
    conversation_id = create_chat(db)

    with pytest.raises(ConversationConflict):
        save_turn(
            1,
            "Question",
            "Answer",
            conversation_id,
            0,
            db,
        )

    assert len(
        get_conversation(
            1, conversation_id, db
        )["turns"]
    ) == 1


def test_rename(db):
    conversation_id = create_chat(db)

    rename_conversation(
        1, conversation_id, "Algorithms", db
    )

    assert get_conversation(
        1, conversation_id, db
    )["title"] == "Algorithms"


def test_delete_cascades_to_turns(db):
    conversation_id = create_chat(db)

    delete_conversation(
        1, conversation_id, db
    )

    assert list_conversations(1, path=db) == []

    with connect(db) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM conversation_turns"
        ).fetchone()[0]

    assert count == 0


def test_owner_scope(db):
    conversation_id = create_chat(db)

    assert list_conversations(2, path=db) == []

    with pytest.raises(ConversationNotFound):
        get_conversation(
            2, conversation_id, db
        )

    with pytest.raises(ConversationNotFound):
        rename_conversation(
            2, conversation_id, "Unauthorized", db
        )

    with pytest.raises(ConversationNotFound):
        delete_conversation(
            2, conversation_id, db
        )

    with pytest.raises(ConversationNotFound):
        save_turn(
            2,
            "Question",
            "Answer",
            conversation_id,
            1,
            db,
        )


def test_disable_retention_preserves_existing_history(db):
    conversation_id = create_chat(db)

    set_retention(db, False)

    with pytest.raises(RetentionDisabled):
        save_turn(
            1,
            "Question",
            "Answer",
            conversation_id,
            1,
            db,
        )

    assert len(
        get_conversation(
            1, conversation_id, db
        )["turns"]
    ) == 1

    delete_conversation(
        1, conversation_id, db
    )


def test_migration_preserves_owner_and_settings(db):
    # Reconstruct the previous schema using test data.
    with connect(db) as connection:
        connection.execute("DROP TABLE career_audit_events")
        connection.execute("DROP TABLE resume_versions")
        connection.execute("DROP TABLE career_profiles")
        connection.execute("DROP TABLE workspace_records")
        connection.execute("DROP TABLE workspace_audit_events")
        connection.execute(
            "DROP TABLE conversation_turns"
        )
        connection.execute(
            "DROP TABLE conversations"
        )
        connection.execute(
            "PRAGMA user_version = 3"
        )

    previous = load_settings(db)

    initialize_database(db)
    initialize_database(db)

    assert load_settings(db) == previous

    with connect(db) as connection:
        version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]

        owner_count = connection.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]

    assert version == 7
    assert owner_count == 1


@pytest.mark.parametrize("title", ["", " ", "x" * 121])
def test_invalid_title_rejected(db, title):
    conversation_id = create_chat(db)

    with pytest.raises(ValueError):
        rename_conversation(
            1, conversation_id, title, db
        )
