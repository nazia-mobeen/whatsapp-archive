from pathlib import Path

from parser import parse_whatsapp_chat


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    incoming_directory = project_root / "incoming"

    chat_files = list(
        incoming_directory.rglob("_chat.txt")
    )

    if not chat_files:
        print("No _chat.txt file was found.")
        return

    for chat_file in chat_files:
        print("=" * 80)
        print(f"Parsing: {chat_file}")
        print("=" * 80)

        try:
            messages = parse_whatsapp_chat(chat_file)
        except Exception as error:
            print(f"Parser failed: {error}")
            continue

        print(f"Total messages parsed: {len(messages)}")

        text_count = sum(
            message.message_type == "text"
            for message in messages
        )

        photo_count = sum(
            message.message_type == "photo"
            for message in messages
        )

        video_count = sum(
            message.message_type == "video"
            for message in messages
        )

        audio_count = sum(
            message.message_type == "audio"
            for message in messages
        )

        document_count = sum(
            message.message_type == "document"
            for message in messages
        )

        system_count = sum(
            message.is_system_message
            for message in messages
        )

        print(f"Text messages: {text_count}")
        print(f"Photos: {photo_count}")
        print(f"Videos: {video_count}")
        print(f"Audio files: {audio_count}")
        print(f"Documents: {document_count}")
        print(f"System messages: {system_count}")

        print("\nFirst 10 parsed records:\n")

        for index, message in enumerate(
            messages[:10],
            start=1,
        ):
            print("-" * 80)
            print(f"Record: {index}")
            print(f"Timestamp: {message.timestamp}")
            print(f"Sender: {message.sender}")
            print(f"Type: {message.message_type}")
            print(
                f"Attachment: "
                f"{message.attachment_filename}"
            )
            print(f"Message: {message.message_text}")


if __name__ == "__main__":
    main()