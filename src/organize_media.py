from pathlib import Path

from database import connect_database
from media_manager import organize_media


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent

    database_path = (
        project_root
        / "database"
        / "operations_archive.db"
    )

    media_root = project_root / "media"

    if not database_path.exists():
        print("Database was not found.")
        print("Run import_archive.py first.")
        return

    connection = connect_database(database_path)

    try:
        results = organize_media(
            connection=connection,
            media_root=media_root,
        )

        print("\nMedia organization summary")
        print("-" * 40)
        print(
            f"New files copied: {results['copied']}"
        )
        print(
            f"Existing files reused: {results['reused']}"
        )
        print(
            f"Missing attachments: {results['missing']}"
        )
        print(
            f"Errors: {results['errors']}"
        )
        print(f"Media saved under: {media_root}")

    finally:
        connection.close()


if __name__ == "__main__":
    main()