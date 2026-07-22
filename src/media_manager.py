from __future__ import annotations

import hashlib
import shutil
import sqlite3
from pathlib import Path
from typing import Optional


MEDIA_FOLDER_NAMES = {
    "photo": "Photos",
    "video": "Videos",
    "audio": "Audio",
    "document": "Documents",
    "other": "Other",
}


def sanitize_name(value: str) -> str:
    """
    Convert a property or group name into a safe folder name.
    """
    safe_characters = []

    for character in value.strip():
        if character.isalnum() or character in {" ", "-", "_"}:
            safe_characters.append(character)
        else:
            safe_characters.append("_")

    cleaned = "".join(safe_characters)
    cleaned = "_".join(cleaned.split())

    return cleaned or "Unknown"


def calculate_file_hash(file_path: Path) -> str:
    """
    Calculate SHA-256 for duplicate-file detection.
    """
    sha256 = hashlib.sha256()

    with file_path.open("rb") as file:
        while True:
            chunk = file.read(1024 * 1024)

            if not chunk:
                break

            sha256.update(chunk)

    return sha256.hexdigest()


def find_attachment_file(
    attachment_filename: str,
    source_chat_file: str,
) -> Optional[Path]:
    """
    Look for an attachment in the same export folder as _chat.txt.
    """
    chat_file = Path(source_chat_file)
    export_folder = chat_file.parent

    direct_match = export_folder / attachment_filename

    if direct_match.exists() and direct_match.is_file():
        return direct_match

    filename_lower = attachment_filename.lower()

    for candidate in export_folder.iterdir():
        if (
            candidate.is_file()
            and candidate.name.lower() == filename_lower
        ):
            return candidate

    return None


def build_destination_path(
    media_root: Path,
    property_name: str,
    message_date: str,
    media_type: str,
    attachment_filename: str,
) -> Path:
    """
    Build:

    media/
      Family_Test/
        2024/
          November/
            2024-11-16/
              Photos/
                filename.jpg
    """
    year, month_number, _ = message_date.split("-")

    month_names = {
        "01": "January",
        "02": "February",
        "03": "March",
        "04": "April",
        "05": "May",
        "06": "June",
        "07": "July",
        "08": "August",
        "09": "September",
        "10": "October",
        "11": "November",
        "12": "December",
    }

    month_name = month_names.get(
        month_number,
        month_number,
    )

    media_folder = MEDIA_FOLDER_NAMES.get(
        media_type,
        "Other",
    )

    safe_property_name = sanitize_name(property_name)

    return (
        media_root
        / safe_property_name
        / year
        / month_name
        / message_date
        / media_folder
        / attachment_filename
    )


def create_media_files_table(
    connection: sqlite3.Connection,
) -> None:
    """
    Store one record for each unique archived file.
    """
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS media_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_hash TEXT NOT NULL UNIQUE,
            original_filename TEXT NOT NULL,
            archived_path TEXT NOT NULL,
            file_size_bytes INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    connection.commit()


def get_existing_archived_path(
    connection: sqlite3.Connection,
    file_hash: str,
) -> Optional[str]:
    """
    Return the path of a file already archived with the same hash.
    """
    result = connection.execute(
        """
        SELECT archived_path
        FROM media_files
        WHERE file_hash = ?
        """,
        (file_hash,),
    ).fetchone()

    if result is None:
        return None

    return str(result["archived_path"])


def register_media_file(
    connection: sqlite3.Connection,
    file_hash: str,
    original_filename: str,
    archived_path: str,
    file_size_bytes: int,
) -> None:
    """
    Record an archived media file.
    """
    connection.execute(
        """
        INSERT OR IGNORE INTO media_files (
            file_hash,
            original_filename,
            archived_path,
            file_size_bytes
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            file_hash,
            original_filename,
            archived_path,
            file_size_bytes,
        ),
    )


def update_message_media_path(
    connection: sqlite3.Connection,
    message_id: int,
    media_path: str,
) -> None:
    """
    Link the archived file path to the original message.
    """
    connection.execute(
        """
        UPDATE messages
        SET media_path = ?
        WHERE id = ?
        """,
        (
            media_path,
            message_id,
        ),
    )


def organize_media(
    connection: sqlite3.Connection,
    media_root: Path,
) -> dict[str, int]:
    """
    Process all messages that reference attachments but do not yet
    have a permanent media path.
    """
    create_media_files_table(connection)

    rows = connection.execute(
        """
        SELECT
            id,
            property_name,
            message_date,
            media_type,
            attachment_filename,
            source_file
        FROM messages
        WHERE attachment_filename IS NOT NULL
          AND attachment_filename != ''
          AND (
                media_path IS NULL
                OR media_path = ''
              )
        ORDER BY timestamp
        """
    ).fetchall()

    copied_count = 0
    reused_count = 0
    missing_count = 0
    error_count = 0

    for row in rows:
        message_id = int(row["id"])
        property_name = str(row["property_name"])
        message_date = str(row["message_date"])
        media_type = str(row["media_type"])
        attachment_filename = str(
            row["attachment_filename"]
        )
        source_file = str(row["source_file"])

        source_path = find_attachment_file(
            attachment_filename=attachment_filename,
            source_chat_file=source_file,
        )

        if source_path is None:
            print(
                f"Missing attachment: {attachment_filename}"
            )
            missing_count += 1
            continue

        try:
            file_hash = calculate_file_hash(source_path)

            existing_path = get_existing_archived_path(
                connection=connection,
                file_hash=file_hash,
            )

            if existing_path:
                update_message_media_path(
                    connection=connection,
                    message_id=message_id,
                    media_path=existing_path,
                )

                reused_count += 1
                continue

            destination_path = build_destination_path(
                media_root=media_root,
                property_name=property_name,
                message_date=message_date,
                media_type=media_type,
                attachment_filename=attachment_filename,
            )

            destination_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            if not destination_path.exists():
                shutil.copy2(
                    source_path,
                    destination_path,
                )

            archived_path = str(
                destination_path.resolve()
            )

            register_media_file(
                connection=connection,
                file_hash=file_hash,
                original_filename=attachment_filename,
                archived_path=archived_path,
                file_size_bytes=source_path.stat().st_size,
            )

            update_message_media_path(
                connection=connection,
                message_id=message_id,
                media_path=archived_path,
            )

            copied_count += 1

        except Exception as error:
            error_count += 1
            print(
                f"Media processing error for "
                f"{attachment_filename}: {error}"
            )

    connection.commit()

    return {
        "copied": copied_count,
        "reused": reused_count,
        "missing": missing_count,
        "errors": error_count,
    }