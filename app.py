from __future__ import annotations

import re
import sqlite3
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from src.s3_storage import upload_file_to_s3, verify_s3_object

import streamlit as st


# ============================================================
# Project paths and imports
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent
DATABASE_PATH = PROJECT_ROOT / "database" / "operations_archive.db"
MEDIA_ROOT = PROJECT_ROOT / "media"
INCOMING_ROOT = PROJECT_ROOT / "incoming"
SRC_DIRECTORY = PROJECT_ROOT / "src"

if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from database import (  # noqa: E402
    connect_database as connect_archive_database,
    initialize_database,
    insert_messages,
)
from media_manager import organize_media  # noqa: E402
from parser import parse_whatsapp_chat  # noqa: E402


# ============================================================
# Streamlit configuration
# ============================================================

st.set_page_config(
    page_title="Waves Property Operations Archive",
    page_icon="📁",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ============================================================
# Constants
# ============================================================

MONTH_NAMES = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}


# ============================================================
# Database reading functions
# ============================================================

def connect_view_database() -> sqlite3.Connection:
    """
    Open the permanent SQLite archive for reading.
    """
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def get_properties(search_text: str = "") -> list[str]:
    """
    Return all property names matching the optional search text.
    """
    connection = connect_view_database()

    try:
        if search_text.strip():
            rows = connection.execute(
                """
                SELECT DISTINCT property_name
                FROM messages
                WHERE property_name LIKE ?
                ORDER BY property_name
                """,
                (f"%{search_text.strip()}%",),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT DISTINCT property_name
                FROM messages
                ORDER BY property_name
                """
            ).fetchall()

        return [str(row["property_name"]) for row in rows]

    finally:
        connection.close()


def get_years(property_name: str) -> list[int]:
    """
    Return all archived years for a property.
    """
    connection = connect_view_database()

    try:
        rows = connection.execute(
            """
            SELECT DISTINCT substr(message_date, 1, 4) AS year
            FROM messages
            WHERE property_name = ?
            ORDER BY year DESC
            """,
            (property_name,),
        ).fetchall()

        return [int(row["year"]) for row in rows if row["year"]]

    finally:
        connection.close()


def get_months(
    property_name: str,
    year: int,
) -> list[int]:
    """
    Return all archived months for a selected property and year.
    """
    connection = connect_view_database()

    try:
        rows = connection.execute(
            """
            SELECT DISTINCT substr(message_date, 6, 2) AS month
            FROM messages
            WHERE property_name = ?
              AND substr(message_date, 1, 4) = ?
            ORDER BY month
            """,
            (property_name, str(year)),
        ).fetchall()

        return [int(row["month"]) for row in rows if row["month"]]

    finally:
        connection.close()


def get_dates(
    property_name: str,
    year: int,
    month: int,
) -> list[str]:
    """
    Return all available dates for a property, year and month.
    """
    connection = connect_view_database()

    try:
        year_month = f"{year:04d}-{month:02d}"

        rows = connection.execute(
            """
            SELECT DISTINCT message_date
            FROM messages
            WHERE property_name = ?
              AND substr(message_date, 1, 7) = ?
            ORDER BY message_date DESC
            """,
            (property_name, year_month),
        ).fetchall()

        return [str(row["message_date"]) for row in rows]

    finally:
        connection.close()


def get_messages(
    property_name: str,
    selected_date: str,
    search_text: str = "",
) -> list[sqlite3.Row]:
    """
    Return messages for a selected property and date.
    """
    connection = connect_view_database()

    try:
        if search_text.strip():
            search_pattern = f"%{search_text.strip()}%"

            rows = connection.execute(
                """
                SELECT *
                FROM messages
                WHERE property_name = ?
                  AND message_date = ?
                  AND (
                        message_text LIKE ?
                        OR sender LIKE ?
                        OR attachment_filename LIKE ?
                      )
                ORDER BY timestamp ASC, id ASC
                """,
                (
                    property_name,
                    selected_date,
                    search_pattern,
                    search_pattern,
                    search_pattern,
                ),
            ).fetchall()

        else:
            rows = connection.execute(
                """
                SELECT *
                FROM messages
                WHERE property_name = ?
                  AND message_date = ?
                ORDER BY timestamp ASC, id ASC
                """,
                (property_name, selected_date),
            ).fetchall()

        return rows

    finally:
        connection.close()


def get_daily_summary(
    property_name: str,
    selected_date: str,
) -> sqlite3.Row:
    """
    Return summary statistics for one property and date.
    """
    connection = connect_view_database()

    try:
        return connection.execute(
            """
            SELECT
                COUNT(*) AS message_count,

                COUNT(
                    DISTINCT CASE
                        WHEN sender IS NOT NULL
                             AND sender != ''
                        THEN sender
                    END
                ) AS employee_count,

                GROUP_CONCAT(
                    DISTINCT CASE
                        WHEN sender IS NOT NULL
                             AND sender != ''
                        THEN sender
                    END
                ) AS employees,

                SUM(
                    CASE
                        WHEN media_type = 'photo'
                        THEN 1
                        ELSE 0
                    END
                ) AS photo_count,

                SUM(
                    CASE
                        WHEN media_type = 'video'
                        THEN 1
                        ELSE 0
                    END
                ) AS video_count,

                MIN(message_time) AS opening_activity,
                MAX(message_time) AS last_activity

            FROM messages
            WHERE property_name = ?
              AND message_date = ?
            """,
            (property_name, selected_date),
        ).fetchone()

    finally:
        connection.close()


# ============================================================
# Formatting functions
# ============================================================

def format_full_date(date_text: str) -> str:
    """
    Convert 2026-07-15 to Wednesday, July 15, 2026.
    """
    parsed_date = datetime.strptime(date_text, "%Y-%m-%d")
    return parsed_date.strftime("%A, %B %d, %Y")


def format_time(time_text: str | None) -> str:
    """
    Convert 18:10:46 to 6:10 PM.
    """
    if not time_text:
        return "Not available"

    try:
        parsed_time = datetime.strptime(time_text, "%H:%M:%S")
        return parsed_time.strftime("%I:%M %p").lstrip("0")
    except ValueError:
        return time_text


def safe_count(value: Any) -> int:
    """
    Safely convert a SQLite aggregate value to an integer.
    """
    return int(value or 0)


def clean_employee_names(employee_text: str | None) -> str:
    """
    Return readable employee names from SQLite GROUP_CONCAT output.
    """
    if not employee_text:
        return "No employee names recorded"

    names = [
        name.strip()
        for name in employee_text.split(",")
        if name.strip()
    ]

    return ", ".join(names)


def sanitize_folder_name(value: str) -> str:
    """
    Convert a property name into a safe folder name.

    Example:
        Opal Grand Resort -> Opal_Grand_Resort
    """
    cleaned = re.sub(
        r"[^A-Za-z0-9 _-]+",
        "",
        value.strip(),
    )

    cleaned = re.sub(r"\s+", "_", cleaned)

    return cleaned or "Unknown_Property"


# ============================================================
# ZIP upload and import functions
# ============================================================

def safely_extract_zip(
    zip_path: Path,
    destination_directory: Path,
) -> None:
    """
    Extract a ZIP file while preventing unsafe file paths.
    """
    destination_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination_root = destination_directory.resolve()

    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            destination_path = (
                destination_directory / member.filename
            ).resolve()

            if (
                destination_path != destination_root
                and destination_root not in destination_path.parents
            ):
                raise ValueError(
                    f"Unsafe ZIP entry detected: {member.filename}"
                )

        archive.extractall(destination_directory)


def find_chat_file(extracted_directory: Path) -> Path:
    """
    Find the WhatsApp _chat.txt file inside an extracted ZIP.
    """
    exact_matches = list(
        extracted_directory.rglob("_chat.txt")
    )

    if exact_matches:
        return exact_matches[0]

    text_files = list(
        extracted_directory.rglob("*.txt")
    )

    if len(text_files) == 1:
        return text_files[0]

    raise FileNotFoundError(
        "The uploaded ZIP does not contain a recognizable "
        "WhatsApp _chat.txt file."
    )


def save_uploaded_zip(
    uploaded_file: Any,
    destination_path: Path,
) -> None:
    """
    Save the uploaded ZIP permanently to the local archive.
    """
    destination_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with destination_path.open("wb") as output_file:
        output_file.write(uploaded_file.getbuffer())


def import_uploaded_archive(
    uploaded_file: Any,
    property_name: str,
) -> dict[str, Any]:
    """
    Save, extract, parse, import and organize one WhatsApp archive.
    """
    cleaned_property_name = property_name.strip()

    if not cleaned_property_name:
        raise ValueError(
            "Enter a property name before importing."
        )

    timestamp_label = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    safe_property_name = sanitize_folder_name(
        cleaned_property_name
    )

    import_directory = (
        INCOMING_ROOT
        / safe_property_name
        / timestamp_label
    )

    original_directory = import_directory / "original"
    extracted_directory = import_directory / "extracted"

    uploaded_filename = (
        Path(uploaded_file.name).name
        if uploaded_file.name
        else "whatsapp_export.zip"
    )

    zip_path = original_directory / uploaded_filename

    # Upload the original WhatsApp ZIP to permanent AWS S3 storage first.
    uploaded_file.seek(0)

    s3_object_key = upload_file_to_s3(
        file_object=uploaded_file,
        filename=uploaded_filename,
        property_name=cleaned_property_name,
        content_type=getattr(uploaded_file, "type", None),
    )

    # Verify that AWS received the complete file.
    s3_verification = verify_s3_object(s3_object_key)
    expected_size = len(uploaded_file.getbuffer())
    stored_size = int(s3_verification["ContentLength"])

    if stored_size != expected_size:
        raise RuntimeError(
            "The AWS backup could not be verified because the uploaded "
            "file size does not match the stored file size."
        )

    # Reset the uploaded file before saving a temporary local processing copy.
    uploaded_file.seek(0)

    save_uploaded_zip(
        uploaded_file=uploaded_file,
        destination_path=zip_path,
    )

    safely_extract_zip(
        zip_path=zip_path,
        destination_directory=extracted_directory,
    )

    chat_file = find_chat_file(extracted_directory)

    messages = parse_whatsapp_chat(chat_file)

    if not messages:
        raise ValueError(
            "No WhatsApp messages were found in the export."
        )

    archive_connection = connect_archive_database(
        DATABASE_PATH
    )

    try:
        initialize_database(archive_connection)

        import_results = insert_messages(
            connection=archive_connection,
            messages=messages,
            property_name=cleaned_property_name,
            group_name=cleaned_property_name,
        )

        media_results = organize_media(
            connection=archive_connection,
            media_root=MEDIA_ROOT,
        )

    finally:
        archive_connection.close()

    return {
        "property_name": cleaned_property_name,
        "parsed": len(messages),
        "imported": import_results["imported"],
        "duplicates": import_results["duplicates"],
        "database_errors": import_results["errors"],
        "media_copied": media_results["copied"],
        "media_reused": media_results["reused"],
        "media_missing": media_results["missing"],
        "media_errors": media_results["errors"],
        "import_directory": str(import_directory),
        "s3_object_key": s3_object_key,
        "s3_size_bytes": stored_size,
    }


# ============================================================
# Navigation state
# ============================================================

def initialize_navigation() -> None:
    defaults = {
        "page": "properties",
        "selected_property": None,
        "selected_year": None,
        "selected_month": None,
        "selected_date": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def go_to_properties() -> None:
    st.session_state.page = "properties"
    st.session_state.selected_property = None
    st.session_state.selected_year = None
    st.session_state.selected_month = None
    st.session_state.selected_date = None


def go_to_years(property_name: str) -> None:
    st.session_state.page = "years"
    st.session_state.selected_property = property_name
    st.session_state.selected_year = None
    st.session_state.selected_month = None
    st.session_state.selected_date = None


def go_to_months(year: int) -> None:
    st.session_state.page = "months"
    st.session_state.selected_year = year
    st.session_state.selected_month = None
    st.session_state.selected_date = None


def go_to_dates(month: int) -> None:
    st.session_state.page = "dates"
    st.session_state.selected_month = month
    st.session_state.selected_date = None


def go_to_timeline(date_text: str) -> None:
    st.session_state.page = "timeline"
    st.session_state.selected_date = date_text


# ============================================================
# General interface helpers
# ============================================================

def show_breadcrumbs() -> None:
    parts = ["Properties"]

    if st.session_state.selected_property:
        parts.append(st.session_state.selected_property)

    if st.session_state.selected_year:
        parts.append(str(st.session_state.selected_year))

    if st.session_state.selected_month:
        parts.append(
            MONTH_NAMES.get(
                st.session_state.selected_month,
                str(st.session_state.selected_month),
            )
        )

    if st.session_state.selected_date:
        parts.append(
            format_full_date(st.session_state.selected_date)
        )

    st.caption("  ›  ".join(parts))


def show_back_button(target_page: str) -> None:
    if st.button("← Back"):
        st.session_state.page = target_page
        st.rerun()


def display_media(message: sqlite3.Row) -> None:
    """
    Display archived media attached to a message.
    """
    media_path = message["media_path"]
    media_type = message["media_type"]
    attachment_filename = message["attachment_filename"]

    if not attachment_filename:
        return

    if not media_path:
        st.warning(
            f"Attachment unavailable: {attachment_filename}"
        )
        return

    file_path = Path(media_path)

    if not file_path.exists():
        st.warning(
            f"Archived file not found: {attachment_filename}"
        )
        return

    if media_type == "photo":
        with st.expander("📷 View photo"):
            st.image(
                str(file_path),
                caption=attachment_filename,
                use_container_width=True,
            )

    elif media_type == "video":
        with st.expander("🎥 View video"):
            st.video(str(file_path))

    elif media_type == "audio":
        with st.expander("🔊 Play audio"):
            st.audio(str(file_path))

    elif media_type == "document":
        st.markdown(
            f"📄 **Document:** `{attachment_filename}`"
        )

    else:
        st.markdown(
            f"📎 **Attachment:** `{attachment_filename}`"
        )


def display_message(message: sqlite3.Row) -> None:
    """
    Display one message in the chronological daily timeline.
    """
    sender = message["sender"] or "System update"
    message_text = message["message_text"] or ""
    time_label = format_time(message["message_time"])

    with st.container(border=True):
        st.markdown(f"### {time_label}")
        st.markdown(f"**{sender}**")

        if message_text:
            st.write(message_text)

        display_media(message)


# ============================================================
# Upload interface
# ============================================================

def show_upload_section() -> None:
    """
    Display the WhatsApp ZIP upload and automatic import area.
    """
    with st.expander(
        "➕ Import a WhatsApp property archive",
        expanded=False,
    ):
        st.markdown(
            """
Upload one WhatsApp ZIP export and enter the property name.

The system will automatically:

- create the property archive;
- extract the WhatsApp files;
- import messages into the permanent database;
- organize photos, videos and other attachments;
- skip duplicate messages;
- display the property on the home page.
"""
        )

        upload_columns = st.columns([2, 3])

        with upload_columns[0]:
            uploaded_property_name = st.text_input(
                "Property name",
                placeholder="Example: Opal Grand",
                key="uploaded_property_name",
            )

        with upload_columns[1]:
            uploaded_archive = st.file_uploader(
                "WhatsApp ZIP export",
                type=["zip"],
                key="uploaded_archive",
                help=(
                    "Upload the ZIP containing _chat.txt "
                    "and the exported media files."
                ),
            )

        import_button = st.button(
            "Import Archive",
            type="primary",
            use_container_width=True,
            disabled=uploaded_archive is None,
        )

        if import_button:
            if not uploaded_property_name.strip():
                st.error("Enter the property name.")

            elif uploaded_archive is None:
                st.error("Select a WhatsApp ZIP export.")

            else:
                try:
                    with st.spinner(
                        "Importing messages and organizing media..."
                    ):
                        results = import_uploaded_archive(
                            uploaded_file=uploaded_archive,
                            property_name=uploaded_property_name,
                        )

                    st.success(
                        f"{results['property_name']} "
                        "was imported successfully."
                    )

                    st.success(
                        "✅ Original WhatsApp ZIP backed up and verified in AWS S3."
                    )

                    st.caption(
                        f"AWS backup size: "
                        f"{results['s3_size_bytes'] / (1024 * 1024):.2f} MB"
                    )

                    with st.expander("AWS backup details"):
                        st.code(results["s3_object_key"])

                    result_columns = st.columns(4)

                    result_columns[0].metric(
                        "Messages parsed",
                        results["parsed"],
                    )

                    result_columns[1].metric(
                        "New messages",
                        results["imported"],
                    )

                    result_columns[2].metric(
                        "Duplicates skipped",
                        results["duplicates"],
                    )

                    result_columns[3].metric(
                        "Media copied",
                        results["media_copied"],
                    )

                    if results["media_reused"]:
                        st.info(
                            f"{results['media_reused']} existing "
                            "media file(s) were reused."
                        )

                    if results["media_missing"]:
                        st.warning(
                            f"{results['media_missing']} referenced "
                            "attachment(s) were not included in the ZIP."
                        )

                    total_errors = (
                        results["database_errors"]
                        + results["media_errors"]
                    )

                    if total_errors:
                        st.error(
                            f"The import completed with "
                            f"{total_errors} error(s)."
                        )

                    st.session_state.uploaded_property_name = ""
                    st.rerun()

                except zipfile.BadZipFile:
                    st.error(
                        "The selected file is not a valid ZIP archive."
                    )

                except Exception as error:
                    st.error(f"Import failed: {error}")

        st.caption(
            "Do not clear the WhatsApp group until the imported "
            "messages and media have been verified."
        )


# ============================================================
# Page: properties
# ============================================================

def show_properties_page() -> None:
    st.title("📁 Waves Property Operations Archive")

    st.caption(
        "Select a property to review its archived daily operations."
    )

    show_upload_section()

    st.divider()

    property_search = st.text_input(
        "Search properties",
        placeholder=(
            "Search Opal Grand, Delray Pool, "
            "H2O Waterpark..."
        ),
        key="property_search",
    )

    properties = get_properties(property_search)

    if not properties:
        st.info("No matching properties were found.")
        return

    columns_per_row = 3

    for start_index in range(
        0,
        len(properties),
        columns_per_row,
    ):
        row_properties = properties[
            start_index:start_index + columns_per_row
        ]

        columns = st.columns(columns_per_row)

        for column, property_name in zip(
            columns,
            row_properties,
        ):
            with column:
                with st.container(border=True):
                    st.markdown("## 📁")
                    st.markdown(f"### {property_name}")
                    st.caption("Open property archive")

                    if st.button(
                        "Open property",
                        key=f"property-{property_name}",
                        use_container_width=True,
                    ):
                        go_to_years(property_name)
                        st.rerun()


# ============================================================
# Page: years
# ============================================================

def show_years_page() -> None:
    show_back_button("properties")
    show_breadcrumbs()

    property_name = st.session_state.selected_property

    st.title(property_name)
    st.subheader("Select a year")

    years = get_years(property_name)

    if not years:
        st.info("No archived years were found.")
        return

    columns = st.columns(4)

    for index, year in enumerate(years):
        with columns[index % 4]:
            with st.container(border=True):
                st.markdown("## 📁")
                st.markdown(f"### {year}")

                if st.button(
                    "Open year",
                    key=f"year-{year}",
                    use_container_width=True,
                ):
                    go_to_months(year)
                    st.rerun()


# ============================================================
# Page: months
# ============================================================

def show_months_page() -> None:
    show_back_button("years")
    show_breadcrumbs()

    property_name = st.session_state.selected_property
    selected_year = st.session_state.selected_year

    st.title(f"{property_name} — {selected_year}")
    st.subheader("Select a month")

    months = get_months(
        property_name=property_name,
        year=selected_year,
    )

    if not months:
        st.info("No archived months were found.")
        return

    columns = st.columns(4)

    for index, month in enumerate(months):
        month_name = MONTH_NAMES.get(month, str(month))

        with columns[index % 4]:
            with st.container(border=True):
                st.markdown("## 📁")
                st.markdown(f"### {month_name}")

                if st.button(
                    "Open month",
                    key=f"month-{month}",
                    use_container_width=True,
                ):
                    go_to_dates(month)
                    st.rerun()


# ============================================================
# Page: dates
# ============================================================

def show_dates_page() -> None:
    show_back_button("months")
    show_breadcrumbs()

    property_name = st.session_state.selected_property
    selected_year = st.session_state.selected_year
    selected_month = st.session_state.selected_month

    month_name = MONTH_NAMES.get(
        selected_month,
        str(selected_month),
    )

    st.title(
        f"{property_name} — {month_name} {selected_year}"
    )

    st.subheader("Select a date")

    date_search = st.text_input(
        "Search dates",
        placeholder="Example: 2024-11-16 or November 16",
    )

    dates = get_dates(
        property_name=property_name,
        year=selected_year,
        month=selected_month,
    )

    if date_search.strip():
        search_value = date_search.strip().lower()

        dates = [
            date_text
            for date_text in dates
            if (
                search_value in date_text.lower()
                or search_value
                in format_full_date(date_text).lower()
            )
        ]

    if not dates:
        st.info("No matching dates were found.")
        return

    columns = st.columns(4)

    for index, date_text in enumerate(dates):
        parsed_date = datetime.strptime(
            date_text,
            "%Y-%m-%d",
        )

        with columns[index % 4]:
            with st.container(border=True):
                st.markdown(
                    f"### {parsed_date.strftime('%B %d')}"
                )

                st.caption(
                    parsed_date.strftime("%A")
                )

                if st.button(
                    "View daily timeline",
                    key=f"date-{date_text}",
                    use_container_width=True,
                ):
                    go_to_timeline(date_text)
                    st.rerun()


# ============================================================
# Page: daily timeline
# ============================================================

def show_timeline_page() -> None:
    show_back_button("dates")
    show_breadcrumbs()

    property_name = st.session_state.selected_property
    selected_date = st.session_state.selected_date

    summary = get_daily_summary(
        property_name=property_name,
        selected_date=selected_date,
    )

    st.title(property_name)
    st.subheader(format_full_date(selected_date))

    employees = clean_employee_names(
        summary["employees"]
    )

    st.markdown(
        f"""
**Opening activity:** {format_time(summary["opening_activity"])}  
**Last recorded activity:** {format_time(summary["last_activity"])}  
**Employees active:** {employees}  
**Photos:** {safe_count(summary["photo_count"])}  
**Videos:** {safe_count(summary["video_count"])}  
**Messages:** {safe_count(summary["message_count"])}
"""
    )

    st.divider()

    st.header("Daily Timeline")

    message_search = st.text_input(
        "Search this day",
        placeholder=(
            "Search employee, message or attachment"
        ),
    )

    messages = get_messages(
        property_name=property_name,
        selected_date=selected_date,
        search_text=message_search,
    )

    if not messages:
        st.info(
            "No messages matched the selected date "
            "and search."
        )
        return

    for message in messages:
        display_message(message)


# ============================================================
# Main application
# ============================================================

def main() -> None:
    initialize_navigation()

    DATABASE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    MEDIA_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    INCOMING_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not DATABASE_PATH.exists():
        connection = connect_archive_database(
            DATABASE_PATH
        )

        try:
            initialize_database(connection)
        finally:
            connection.close()

    page = st.session_state.page

    if page == "properties":
        show_properties_page()

    elif page == "years":
        show_years_page()

    elif page == "months":
        show_months_page()

    elif page == "dates":
        show_dates_page()

    elif page == "timeline":
        show_timeline_page()

    else:
        go_to_properties()
        st.rerun()


if __name__ == "__main__":
    main()