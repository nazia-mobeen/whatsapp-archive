from pathlib import Path


def find_chat_files(incoming_directory: Path) -> list[Path]:
    return list(incoming_directory.rglob("_chat.txt"))


def inspect_chat_file(chat_file: Path, preview_lines: int = 20) -> None:
    print("=" * 80)
    print(f"Chat file: {chat_file}")
    print(f"File size: {chat_file.stat().st_size:,} bytes")
    print("=" * 80)

    encodings = ["utf-8-sig", "utf-16", "latin-1"]

    for encoding in encodings:
        try:
            with chat_file.open("r", encoding=encoding) as file:
                for line_number, line in enumerate(file, start=1):
                    print(f"{line_number:>4}: {line.rstrip()}")

                    if line_number >= preview_lines:
                        break

            print(f"\nSuccessfully read using: {encoding}")
            return

        except UnicodeDecodeError:
            continue

    print("Could not read the file using the supported encodings.")


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    incoming_directory = project_root / "incoming"

    chat_files = find_chat_files(incoming_directory)

    if not chat_files:
        print("No _chat.txt file was found.")
        print(f"Place the complete exported folder inside: {incoming_directory}")
        return

    print(f"Found {len(chat_files)} WhatsApp export(s).\n")

    for chat_file in chat_files:
        inspect_chat_file(chat_file)


if __name__ == "__main__":
    main()
    