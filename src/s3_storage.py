from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

import boto3
import streamlit as st
from botocore.exceptions import BotoCoreError, ClientError


def get_s3_client():
    """Create an authenticated S3 client using Streamlit secrets."""
    return boto3.client(
        "s3",
        aws_access_key_id=st.secrets["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=st.secrets["AWS_SECRET_ACCESS_KEY"],
        region_name=st.secrets["AWS_REGION"],
    )


def sanitize_name(value: str) -> str:
    """Convert names into safe S3 path components."""
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip())
    return cleaned.strip("-").lower() or "unknown"


def build_object_key(property_name: str, filename: str) -> str:
    """Create a unique and organized S3 object key."""
    safe_property = sanitize_name(property_name)
    safe_filename = Path(filename).name.replace(" ", "_")
    upload_date = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    unique_id = uuid.uuid4().hex

    return (
        f"properties/{safe_property}/original-uploads/"
        f"{upload_date}/{unique_id}_{safe_filename}"
    )


def upload_file_to_s3(
    file_object: BinaryIO,
    filename: str,
    property_name: str,
    content_type: str | None = None,
) -> str:
    """
    Upload a Streamlit file to the private S3 bucket.

    Returns the S3 object key.
    """
    bucket_name = st.secrets["S3_BUCKET"]
    object_key = build_object_key(property_name, filename)

    extra_args: dict[str, object] = {
        "ServerSideEncryption": "AES256",
        "Metadata": {
            "property": sanitize_name(property_name),
            "original-filename": Path(filename).name,
        },
    }

    if content_type:
        extra_args["ContentType"] = content_type

    try:
        file_object.seek(0)

        get_s3_client().upload_fileobj(
            Fileobj=file_object,
            Bucket=bucket_name,
            Key=object_key,
            ExtraArgs=extra_args,
        )

        return object_key

    except (ClientError, BotoCoreError, OSError) as exc:
        raise RuntimeError(f"Could not upload the archive to S3: {exc}") from exc


def verify_s3_object(object_key: str) -> dict:
    """Verify that an uploaded object exists and return its metadata."""
    bucket_name = st.secrets["S3_BUCKET"]

    try:
        return get_s3_client().head_object(
            Bucket=bucket_name,
            Key=object_key,
        )
    except (ClientError, BotoCoreError) as exc:
        raise RuntimeError(f"Could not verify the S3 upload: {exc}") from exc


def create_presigned_url(object_key: str, expires_in: int = 900) -> str:
    """Generate a temporary URL for viewing or downloading a private object."""
    bucket_name = st.secrets["S3_BUCKET"]

    try:
        return get_s3_client().generate_presigned_url(
            ClientMethod="get_object",
            Params={
                "Bucket": bucket_name,
                "Key": object_key,
            },
            ExpiresIn=expires_in,
        )
    except (ClientError, BotoCoreError) as exc:
        raise RuntimeError(f"Could not generate a secure link: {exc}") from exc