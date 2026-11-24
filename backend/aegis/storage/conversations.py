"""Private, owner-scoped conversation persistence."""

import time
import uuid

from pathlib import Path

from aegis.storage.database import DATABASE_PATH, connect
from aegis.storage.settings import _read_settings


class ConversationNotFound(RuntimeError):
    pass


class ConversationConflict(RuntimeError):
    pass


class RetentionDisabled(RuntimeError):
    pass


def validate_owner(user_id):
    if type(user_id) is not int or user_id < 1:
        raise ValueError("Invalid owner")


def validate_title(title):
    if not isinstance(title, str):
        raise ValueError("Invalid title")

    title = title.strip()

    if not title or len(title) > 120:
        raise ValueError("Invalid title")

    return title


def validate_message(message, maximum):
    if (
        not isinstance(message, str)
        or not message.strip()
        or len(message) > maximum
    ):
        raise ValueError("Invalid message")


def require_retention(connection):
    if not _read_settings(
        connection
    ).settings.retain_conversations:
        raise RetentionDisabled(
            "Conversation retention is disabled"
        )


def require_conversation(
    connection,
    user_id,
    conversation_id,
):
    row = connection.execute(
        """
        SELECT id, title, created_at, updated_at
        FROM conversations
        WHERE id = ? AND user_id = ?
        """,
        (conversation_id, user_id),
    ).fetchone()

    if row is None:
        raise ConversationNotFound(
            "Conversation not found"
        )

    return dict(row)


def save_turn(
    user_id: int,
    user_message: str,
    assistant_message: str,
    conversation_id: str | None = None,
    expected_turn_count: int = 0,
    path: Path = DATABASE_PATH,
):
    validate_owner(user_id)
    validate_message(user_message, 4000)
    validate_message(assistant_message, 20000)

    if (
        type(expected_turn_count) is not int
        or expected_turn_count < 0
    ):
        raise ValueError("Invalid turn count")

    now = int(time.time())

    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")

        # Enforce the current privacy preference inside
        # the same transaction as the message write.
        require_retention(connection)

        if conversation_id is None:
            if expected_turn_count != 0:
                raise ConversationConflict(
                    "Invalid conversation state"
                )

            conversation_id = str(uuid.uuid4())

            title = " ".join(
                user_message.split()
            )[:120]

            connection.execute(
                """
                INSERT INTO conversations (
                    id, user_id, title,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    user_id,
                    title,
                    now,
                    now,
                ),
            )
        else:
            require_conversation(
                connection,
                user_id,
                conversation_id,
            )

        count = connection.execute(
            """
            SELECT COUNT(*)
            FROM conversation_turns
            WHERE conversation_id = ?
            """,
            (conversation_id,),
        ).fetchone()[0]

        if count != expected_turn_count:
            raise ConversationConflict(
                "Conversation changed; reload before saving"
            )

        connection.execute(
            """
            INSERT INTO conversation_turns (
                conversation_id,
                user_message,
                assistant_message,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                conversation_id,
                user_message,
                assistant_message,
                now,
            ),
        )

        connection.execute(
            """
            UPDATE conversations
            SET updated_at = MAX(updated_at, ?)
            WHERE id = ? AND user_id = ?
            """,
            (now, conversation_id, user_id),
        )

        return conversation_id


def list_conversations(
    user_id: int,
    limit: int = 100,
    offset: int = 0,
    path: Path = DATABASE_PATH,
):
    validate_owner(user_id)

    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Invalid limit")

    if type(offset) is not int or offset < 0:
        raise ValueError("Invalid offset")

    with connect(path) as connection:
        rows = connection.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM conversations
            WHERE user_id = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, limit, offset),
        ).fetchall()

        return [dict(row) for row in rows]


def get_conversation(
    user_id: int,
    conversation_id: str,
    path: Path = DATABASE_PATH,
):
    validate_owner(user_id)

    with connect(path) as connection:
        connection.execute("BEGIN")

        result = require_conversation(
            connection,
            user_id,
            conversation_id,
        )

        rows = connection.execute(
            """
            SELECT
                user_message AS user,
                assistant_message AS assistant,
                created_at
            FROM conversation_turns
            WHERE conversation_id = ?
            ORDER BY id ASC
            """,
            (conversation_id,),
        ).fetchall()

        result["turns"] = [
            dict(row) for row in rows
        ]

        return result


def rename_conversation(
    user_id: int,
    conversation_id: str,
    title: str,
    path: Path = DATABASE_PATH,
):
    validate_owner(user_id)
    title = validate_title(title)

    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")

        require_conversation(
            connection,
            user_id,
            conversation_id,
        )

        connection.execute(
            """
            UPDATE conversations
            SET title = ?,
                updated_at = MAX(updated_at, ?)
            WHERE id = ? AND user_id = ?
            """,
            (
                title,
                int(time.time()),
                conversation_id,
                user_id,
            ),
        )

        return require_conversation(
            connection,
            user_id,
            conversation_id,
        )


def delete_conversation(
    user_id: int,
    conversation_id: str,
    path: Path = DATABASE_PATH,
):
    validate_owner(user_id)

    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")

        require_conversation(
            connection,
            user_id,
            conversation_id,
        )

        connection.execute(
            """
            DELETE FROM conversations
            WHERE id = ? AND user_id = ?
            """,
            (conversation_id, user_id),
        )
