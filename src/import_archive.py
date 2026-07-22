from pathlib import Path

from database import (
    connect_database,
    count_messages,
    get_date_range,
    initialize_database,
    insert_messages,
)
from parser import parse_whatsapp_chat


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent

    incoming_directory = project_root / "incoming"
    database_path = (
        project_root
        / "database"
        / "operations_archive.db"
    )

    chat_files = list(
        incoming_directory.rglob("_chat.txt")
    )

    if not chat_files:
        print("No _chat.txt file was found.")
        return

    # Temporary testing values.
    # Later, these will come from the property configuration.
    property_name = "Test Property"
    group_name = "Family Test Group"

    connection = connect_database(database_path)

    try:
        initialize_database(connection)

        for chat_file in chat_files:
            print("=" * 80)
            print(f"Importing: {chat_file}")
            print(f"Property: {property_name}")
            print(f"Group: {group_name}")
            print("=" * 80)

            messages = parse_whatsapp_chat(chat_file)

            print(
                f"Messages parsed: {len(messages)}"
            )

            results = insert_messages(
                connection=connection,
                messages=messages,
                property_name=property_name,
                group_name=group_name,
            )

            print(
                f"New messages imported: "
                f"{results['imported']}"
            )
            print(
                f"Duplicates skipped: "
                f"{results['duplicates']}"
            )
            print(
                f"Errors: {results['errors']}"
            )

        total_messages = count_messages(connection)
        earliest_date, latest_date = get_date_range(
            connection
        )

        print("\nArchive summary")
        print("-" * 40)
        print(
            f"Total stored messages: {total_messages}"
        )
        print(f"Earliest date: {earliest_date}")
        print(f"Latest date: {latest_date}")
        print(f"Database saved at: {database_path}")

    finally:
        connection.close()


if __name__ == "__main__":
    main()