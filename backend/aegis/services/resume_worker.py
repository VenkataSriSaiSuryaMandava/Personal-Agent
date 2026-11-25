"""Offline document extraction subprocess."""

import io
import json
import resource
import sys
import zipfile

from defusedxml.ElementTree import fromstring
from pypdf import PdfReader

from aegis.schemas.career import (
    MAX_DOCUMENT_BYTES,
    MAX_EXTRACTED_TEXT,
    clean_text,
)

PDF = "application/pdf"
DOCX = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.document"
)

MAX_XML_BYTES = 4 * 1024 * 1024
WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def extract_pdf(data):
    if not data.startswith(b"%PDF-"):
        raise ValueError("Invalid PDF")

    reader = PdfReader(io.BytesIO(data), strict=True)

    if reader.is_encrypted:
        raise ValueError("Encrypted PDF")

    if len(reader.pages) > 30:
        raise ValueError("Too many PDF pages")

    parts = []
    total = 0

    for page in reader.pages:
        text = page.extract_text() or ""
        total += len(text) + 1

        if total > MAX_EXTRACTED_TEXT:
            raise ValueError("Extracted text too large")

        parts.append(text)

    return "\n".join(parts)


def extract_docx(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()

        if len(entries) > 500:
            raise ValueError("Too many document entries")

        names = [item.filename for item in entries]

        if len(set(names)) != len(names):
            raise ValueError("Duplicate document entries")

        if sum(item.file_size for item in entries) > 30 * 1024 * 1024:
            raise ValueError("Expanded document too large")

        for item in entries:
            name = item.filename.replace("\\", "/")

            if (
                name.startswith("/")
                or ".." in name.split("/")
                or item.flag_bits & 1
                or "vbaproject" in name.lower()
            ):
                raise ValueError("Unsupported document structure")

        if "[Content_Types].xml" not in names:
            raise ValueError("Invalid DOCX")

        info = archive.getinfo("word/document.xml")

        if info.file_size > MAX_XML_BYTES:
            raise ValueError("Document XML too large")

        with archive.open(info) as stream:
            content = stream.read(MAX_XML_BYTES + 1)

        if len(content) > MAX_XML_BYTES:
            raise ValueError("Document XML too large")

        root = fromstring(
            content,
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        )

        if root.tag != WORD_NS + "document":
            raise ValueError("Invalid document root")

        parts = []
        total = 0

        for paragraph in root.iter(WORD_NS + "p"):
            text = "".join(
                element.text or ""
                for element in paragraph.iter(WORD_NS + "t")
            )

            total += len(text) + 1

            if total > MAX_EXTRACTED_TEXT:
                raise ValueError("Extracted text too large")

            parts.append(text)

        return "\n".join(parts)


def extract(data, media_type):
    if not data or len(data) > MAX_DOCUMENT_BYTES:
        raise ValueError("Invalid document size")

    if media_type == PDF:
        text = extract_pdf(data)
    elif media_type == DOCX:
        text = extract_docx(data)
    elif media_type == "text/plain":
        text = data.decode("utf-8-sig", errors="strict")
    else:
        raise ValueError("Unsupported document type")

    text = clean_text(text)

    if len(text) > MAX_EXTRACTED_TEXT:
        raise ValueError("Extracted text too large")

    return text


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (8, 9))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    if sys.platform.startswith("linux"):
        memory = 384 * 1024 * 1024
        resource.setrlimit(
            resource.RLIMIT_AS, (memory, memory)
        )

    try:
        data = sys.stdin.buffer.read(
            MAX_DOCUMENT_BYTES + 1
        )

        text = extract(data, sys.argv[1])

        sys.stdout.write(json.dumps(
            {"text": text},
            ensure_ascii=True,
        ))

    except Exception:
        # Never return parser diagnostics or document content.
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
