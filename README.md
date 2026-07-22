# WhatsApp Archive System

A Streamlit-based application developed for **Waves Property Operations** to archive, organize, and search WhatsApp chat exports from multiple resort properties.

---

## Features

- Import WhatsApp exported chats
- Automatically organize photos and videos
- Archive conversations in SQLite
- Browse archives by Property, Year, Month, and Date
- Search archived messages
- View daily activity summaries
- Media management for photos and videos

---

## Technology Stack

- Python 3
- Streamlit
- SQLite
- Git & GitHub

---

## Project Structure

```
whatsapp-archive/
│
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
│
└── src/
    ├── database.py
    ├── parser.py
    ├── media_manager.py
    ├── organize_media.py
    ├── import_archive.py
    ├── inspect_export.py
    └── test_parser.py
```

---

## Installation

Clone the repository:

```bash
git clone https://github.com/nazia-mobeen/whatsapp-archive.git
```

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Run the application:

```bash
streamlit run app.py
```

---

## Status

🚧 Under active development.

Planned improvements include:

- AI-powered search
- AI chat summarization
- Cloud storage integration
- Multi-user support
- Advanced reporting dashboard

---

## Author

**Nazia Mobeen**

Software Engineer

Waves Property Operations