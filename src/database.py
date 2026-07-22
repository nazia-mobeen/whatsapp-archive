from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable

from parser import WhatsAppMessage


def create_message_hash(
    property_name: str,
    group_name: str,
    message: WhatsAppMessage,
) -> str:
    """
    Create a stable unique identifier for duplicate prevention.
    """
    raw_value = "|".join(
        [
            property_name.strip().lower(),
            group_name.strip().lower(),
            message.timestamp.isoformat(),
            (message.sender or "").strip().lower(),
            message.message_text.strip(),
            (message.attachment_filename or "").strip().lower(),
            message.message_type.strip().lower(),
        ]
    )

    return hashlib.sha256(
        raw_value.encode("utf-8")
    ).hexdigest()


def connect_database(database_path: Path) -> sqlite3.Connection:
    """
    Open the SQLite database and return a connection.
    """
    database_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row

    connection.execute(
        "PRAGMA foreign_keys = ON;"
    )

    return connection


def initialize_database(
    connection: sqlite3.Connection,
) -> None:
    """
    Create the database tables if they do not already exist.
    """
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_hash TEXT NOT NULL UNIQUE,
            property_name TEXT NOT NULL,
            group_name TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            message_date TEXT NOT NULL,
            message_time TEXT NOT NULL,
            sender TEXT,
            message_text TEXT,
            attachment_filename TEXT,
            media_type TEXT NOT NULL,
            media_path TEXT,
            is_system_message INTEGER NOT NULL DEFAULT 0,
            source_file TEXT NOT NULL,
            imported_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_messages_property
        ON messages(property_name);

        CREATE INDEX IF NOT EXISTS idx_messages_group
        ON messages(group_name);

        CREATE INDEX IF NOT EXISTS idx_messages_date
        ON messages(message_date);

        CREATE INDEX IF NOT EXISTS idx_messages_timestamp
        ON messages(timestamp);

        CREATE INDEX IF NOT EXISTS idx_messages_sender
        ON messages(sender);
        """
    )

    connection.commit()


def insert_messages(
    connection: sqlite3.Connection,
    messages: Iterable[WhatsAppMessage],
    property_name: str,
    group_name: str,
) -> dict[str, int]:
    """
    Insert messages and skip records already stored.
    """
    imported_count = 0
    duplicate_count = 0
    error_count = 0

    imported_at = datetime.now().isoformat(
        sep=" ",
        timespec="seconds",
    )

    for message in messages:
        message_hash = create_message_hash(
            property_name=property_name,
            group_name=group_name,
            message=message,
        )

        try:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO messages (
                    message_hash,
                    property_name,
                    group_name,
                    timestamp,
                    message_date,
                    message_time,
                    sender,
                    message_text,
                    attachment_filename,
                    media_type,
                    media_path,
                    is_system_message,
                    source_file,
                    imported_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_hash,
                    property_name.strip(),
                    group_name.strip(),
                    message.timestamp.isoformat(
                        sep=" ",
                        timespec="seconds",
                    ),
                    message.timestamp.date().isoformat(),
                    message.timestamp.time().isoformat(
                        timespec="seconds"
                    ),
                    message.sender,
                    message.message_text,
                    message.attachment_filename,
                    message.message_type,
                    None,
                    int(message.is_system_message),
                    message.source_file,
                    imported_at,
                ),
            )

            if cursor.rowcount == 1:
                imported_count += 1
            else:
                duplicate_count += 1

        except sqlite3.Error as error:
            error_count += 1
            print(
                "Database error while importing "
                f"{message.timestamp}: {error}"
            )

    connection.commit()

    return {
        "imported": imported_count,
        "duplicates": duplicate_count,
        "errors": error_count,
    }


def count_messages(
    connection: sqlite3.Connection,
) -> int:
    """
    Return the total number of stored messages.
    """
    result = connection.execute(
        "SELECT COUNT(*) AS total FROM messages"
    ).fetchone()

    return int(result["total"])


def get_date_range(
    connection: sqlite3.Connection,
) -> tuple[str | None, str | None]:
    """
    Return the earliest and latest archived dates.
    """
    result = connection.execute(
        """
        SELECT
            MIN(message_date) AS earliest_date,
            MAX(message_date) AS latest_date
        FROM messages
        """
    ).fetchone()

    return (
        result["earliest_date"],
        result["latest_date"],
    )