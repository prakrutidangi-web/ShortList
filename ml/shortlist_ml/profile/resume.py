"""Resume text extraction. IN MEMORY ONLY: bytes in, text out, nothing written to disk or logged.

Supported: text-based PDF and pasted text. No OCR (a scanned PDF is rejected with a clear message).
Safety limits: size cap, `%PDF-` magic bytes, page cap, and a wall-clock timeout around the parser.
"""

import io
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

MAX_PDF_BYTES = 5 * 1024 * 1024
MAX_PAGES = 10
MAX_TEXT_CHARS = 60_000
MIN_TEXT_CHARS = 200  # fewer extracted characters than this => assume a scanned/image PDF
PARSE_TIMEOUT_S = 15.0


class ResumeError(Exception):
    """User-facing, PII-free error. `code` is stable for the UI and tests."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _extract(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted and not reader.decrypt(""):
        raise ResumeError(
            "encrypted", "This PDF is password-protected. Remove the password or paste your text."
        )
    parts = [(page.extract_text() or "") for page in reader.pages[:MAX_PAGES]]
    return "\n".join(parts)


def extract_pdf_text(data: bytes) -> str:
    if len(data) > MAX_PDF_BYTES:
        raise ResumeError("too_large", f"File is larger than {MAX_PDF_BYTES // (1024 * 1024)} MB.")
    if not data.startswith(b"%PDF-"):
        raise ResumeError(
            "not_pdf", "That does not look like a PDF file. Upload a PDF or paste your text."
        )
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        text = pool.submit(_extract, data).result(timeout=PARSE_TIMEOUT_S)
    except FutureTimeout as exc:
        raise ResumeError(
            "timeout", "Reading the PDF took too long. Paste your text instead."
        ) from exc
    except ResumeError:
        raise
    except Exception as exc:
        raise ResumeError(
            "unreadable", "Could not read this PDF. Paste your text instead."
        ) from exc
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    text = clean_text(text)
    if len(text) < MIN_TEXT_CHARS:
        raise ResumeError(
            "no_text_layer",
            "No readable text found. This looks like a scanned/image PDF; OCR is not supported. Paste your text instead.",
        )
    return text


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:MAX_TEXT_CHARS]


def pasted_text(text: str) -> str:
    cleaned = clean_text(text)
    if len(cleaned) < 30:
        raise ResumeError("too_short", "Paste more of your resume text (at least a few lines).")
    return cleaned
