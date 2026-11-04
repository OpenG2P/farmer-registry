"""Shared /documents/upload_documents helpers -- used by any write flow that
can hit a documents_required=True section (intake_create, cr_create). One
on-disk file is uploaded repeatedly under fresh random filenames rather than
building distinct fixtures per flow.
"""

from __future__ import annotations

import io
import os
import random
import string

# staff-api/section-document.jpg, resolved from this file's location so it
# doesn't depend on which flow's directory is the caller's cwd.
_SECTION_DOCUMENT_PATH = os.path.join(os.path.dirname(__file__), "..", "staff-api", "section-document.jpg")
with open(_SECTION_DOCUMENT_PATH, "rb") as _f:
    SECTION_DOCUMENT_BYTES = _f.read()

DOCUMENTS_PER_SECTION = 3


def _random_document_filename(extension: str = "jpg") -> str:
    stem = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{stem}.{extension}"


def build_document_upload_files(count: int = DOCUMENTS_PER_SECTION) -> list[tuple]:
    """files= list for /documents/upload_documents: `count` copies of the same
    on-disk file content as separate multipart parts (each a fresh BytesIO over
    the bytes read once at import time, not re-read from disk per call), each
    given its own random 6-char filename so uploads are distinguishable."""
    return [
        ("documents", (_random_document_filename(), io.BytesIO(SECTION_DOCUMENT_BYTES), "image/jpeg"))
        for _ in range(count)
    ]


def extract_document_ids(upload_response_json: dict) -> list[str]:
    payload = (upload_response_json or {}).get("response_body", {}).get("response_payload") or {}
    documents = payload.get("documents") or []
    return [doc["document_id"] for doc in documents if doc.get("document_id")]


def build_document_attachments(document_ids: list[str], label: str = "section-document") -> list[dict]:
    """DocumentAttachment list -- consumed by save_intake_form_submission's and
    create_change_request['s/_for_core_data]'s `documents` field alike."""
    return [{"document_id": document_id, "label": label} for document_id in document_ids]
