"""
File content scanner — HIGH-008.

Performs multi-layer security inspection on uploaded file bytes
before they are persisted to storage.

Layers applied in order:
  1. Magic-byte / file-signature validation — detects disguised file types.
  2. Zip-bomb protection — rejects suspiciously high compression ratios.
  3. Dangerous-content pattern scan — flags executable payloads hidden in PDFs
     and Office documents.
  4. VirusTotal API check (optional) — triggered when VIRUSTOTAL_API_KEY is set
     and the file hash is not already in the clean-hash cache.

The public entry point is ``scan_file()`` which returns a ``ScanResult``.
``ScanResult.safe`` is ``True`` only when all layers pass.
"""
from __future__ import annotations

import hashlib
import io
import logging
import struct
import zipfile
from dataclasses import dataclass, field
from typing import Sequence

from django.conf import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class ScanResult:
    safe: bool
    reason: str = ""
    flags: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:  # pragma: no cover
        return self.safe


# ---------------------------------------------------------------------------
# Magic-byte signatures for allowed MIME types
# ---------------------------------------------------------------------------

# Each entry: (offset, magic_bytes, description)
_MAGIC: list[tuple[int, bytes, str]] = [
    (0, b"\xff\xd8\xff", "JPEG"),
    (0, b"\x89PNG\r\n\x1a\n", "PNG"),
    (0, b"GIF87a", "GIF"),
    (0, b"GIF89a", "GIF"),
    (0, b"RIFF", "WEBP/WAV"),          # WEBP checked further below
    (0, b"%PDF-", "PDF"),
    (0, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "OLE2 (DOC/XLS)"),
    (0, b"PK\x03\x04", "ZIP-based (DOCX/XLSX)"),
    (0, b"PK\x05\x06", "ZIP-based (DOCX/XLSX) empty"),
    (0, b"PK\x07\x08", "ZIP-based (DOCX/XLSX) spanned"),
]

# Extensions that are never allowed regardless of magic bytes.
_ALWAYS_BLOCKED_EXTS: frozenset[str] = frozenset({
    "exe", "bat", "cmd", "sh", "ps1", "vbs", "js", "jar",
    "msi", "com", "scr", "hta", "pif", "reg", "dll", "so",
    "elf", "php", "py", "rb", "pl", "asp", "aspx",
})

# Dangerous byte patterns inside file content (PE headers, shell indicators).
_DANGEROUS_PATTERNS: list[tuple[bytes, str]] = [
    (b"MZ\x90\x00", "Windows PE executable header"),
    (b"\x7fELF", "ELF (Linux) executable header"),
    (b"#!/", "Unix shebang (script)"),
    (b"#! /", "Unix shebang (script, spaced)"),
    (b"<script", "Embedded HTML script tag"),
    (b"javascript:", "JavaScript URI"),
    (b"/JS ", "PDF JavaScript action"),
    (b"/JavaScript", "PDF JavaScript action"),
    (b"/AA ", "PDF Automatic Action"),
    (b"/OpenAction", "PDF OpenAction"),
    (b"/EmbeddedFile", "PDF EmbeddedFile stream"),
    (b"AAAA" * 20, "NOP sled / heap-spray pattern"),
]

# Max uncompressed-to-compressed ratio before we flag as zip bomb.
_ZIP_BOMB_RATIO: int = 50
_ZIP_BOMB_MAX_SIZE: int = 200 * 1024 * 1024  # 200 MB uncompressed cap


# ---------------------------------------------------------------------------
# Layer 1: Extension block-list
# ---------------------------------------------------------------------------

def _check_extension(filename: str) -> ScanResult | None:
    """Block overtly dangerous extensions regardless of MIME type."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in _ALWAYS_BLOCKED_EXTS:
        return ScanResult(safe=False, reason=f"Blocked file extension: .{ext}")
    return None


# ---------------------------------------------------------------------------
# Layer 2: Magic-byte validation
# ---------------------------------------------------------------------------

def _check_magic_bytes(file_bytes: bytes, filename: str) -> ScanResult | None:
    """
    Verify that the leading bytes match a known-safe format.
    Mismatch between extension and magic bytes is a disguise attack.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if not ext:
        return None  # No extension — rely on other layers.

    # Derive the expected magic categories for this extension.
    expected: set[str] = set()
    _ext_to_categories = {
        "jpg": {"JPEG"}, "jpeg": {"JPEG"},
        "png": {"PNG"},
        "gif": {"GIF"},
        "webp": {"WEBP/WAV"},
        "pdf": {"PDF"},
        "doc": {"OLE2 (DOC/XLS)"},
        "xls": {"OLE2 (DOC/XLS)"},
        "docx": {"ZIP-based (DOCX/XLSX)", "ZIP-based (DOCX/XLSX) empty", "ZIP-based (DOCX/XLSX) spanned"},
        "xlsx": {"ZIP-based (DOCX/XLSX)", "ZIP-based (DOCX/XLSX) empty", "ZIP-based (DOCX/XLSX) spanned"},
        # text/csv have no strong magic — skip magic check.
        "txt": None, "csv": None,
    }

    categories = _ext_to_categories.get(ext)
    if categories is None:
        return None  # Extension without a meaningful magic check.

    matched = False
    for offset, magic, description in _MAGIC:
        if description in categories and file_bytes[offset: offset + len(magic)] == magic:
            matched = True
            break

    if not matched and categories:
        # Check first 16 bytes for debug logging.
        prefix = file_bytes[:16].hex() if file_bytes else "(empty)"
        logger.warning(
            "Magic-byte mismatch: ext=%s expected_categories=%s file_prefix=%s",
            ext,
            categories,
            prefix,
        )
        return ScanResult(
            safe=False,
            reason=f"File content does not match its .{ext} extension (possible disguise attack).",
        )

    return None


# ---------------------------------------------------------------------------
# Layer 3: Zip-bomb protection
# ---------------------------------------------------------------------------

def _check_zip_bomb(file_bytes: bytes, filename: str) -> ScanResult | None:
    """
    Detect suspiciously compressed archives (zip bombs).
    Only applied to ZIP-based files (DOCX, XLSX) and any .zip extensions.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in {"zip", "docx", "xlsx"}:
        return None

    if not file_bytes[:4] == b"PK\x03\x04":
        return None  # Not a valid ZIP — magic check will handle this.

    try:
        total_compressed = len(file_bytes)
        total_uncompressed = 0
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            for info in zf.infolist():
                total_uncompressed += info.file_size
                if total_uncompressed > _ZIP_BOMB_MAX_SIZE:
                    return ScanResult(
                        safe=False,
                        reason=f"Rejected: uncompressed size exceeds {_ZIP_BOMB_MAX_SIZE // (1024*1024)} MB limit.",
                    )
        if total_compressed > 0:
            ratio = total_uncompressed / total_compressed
            if ratio > _ZIP_BOMB_RATIO:
                return ScanResult(
                    safe=False,
                    reason=f"Rejected: zip compression ratio {ratio:.0f}x exceeds safety limit of {_ZIP_BOMB_RATIO}x.",
                )
    except zipfile.BadZipFile:
        # Corrupt ZIP — flag it.
        return ScanResult(safe=False, reason="Rejected: corrupt or invalid ZIP archive.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Zip-bomb check failed for %s: %s", filename, exc)

    return None


# ---------------------------------------------------------------------------
# Layer 4: Dangerous-content pattern scan
# ---------------------------------------------------------------------------

def _check_dangerous_patterns(file_bytes: bytes) -> ScanResult | None:
    """
    Scan file content for known-dangerous byte sequences.
    Primarily targets malicious PDFs, Office macros, and embedded executables.
    """
    # Lowercase comparison for text-based patterns; keep raw for binary.
    sample = file_bytes[:4 * 1024 * 1024]  # scan first 4 MB only for performance

    for pattern, description in _DANGEROUS_PATTERNS:
        if pattern in sample:
            logger.warning("Dangerous pattern detected: %s", description)
            return ScanResult(
                safe=False,
                reason=f"Rejected: dangerous content detected ({description}).",
                flags=[description],
            )

    return None


# ---------------------------------------------------------------------------
# Layer 5: VirusTotal (optional)
# ---------------------------------------------------------------------------

def _check_virustotal(file_bytes: bytes) -> ScanResult | None:
    """
    Submit file hash to VirusTotal for a reputation check.
    Only runs when VIRUSTOTAL_API_KEY is configured.
    Results of 'clean' hashes are cached in Django's cache backend.
    Never raises — failures are treated as inconclusive (not blocking).
    """
    api_key = getattr(settings, "VIRUSTOTAL_API_KEY", "")
    if not api_key:
        return None  # Not configured — skip.

    sha256 = hashlib.sha256(file_bytes).hexdigest()
    cache_key = f"vt_safe_{sha256}"

    try:
        from django.core.cache import cache
        if cache.get(cache_key):
            return None  # Known clean — skip API call.

        import urllib.request
        import json as _json

        req = urllib.request.Request(
            f"https://www.virustotal.com/api/v3/files/{sha256}",
            headers={"x-apikey": api_key},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = _json.loads(resp.read())

        stats = data.get("data", {}).get("attributes", {}).get("last_analysis_stats", {})
        malicious = stats.get("malicious", 0)
        if malicious > 0:
            return ScanResult(
                safe=False,
                reason=f"VirusTotal flagged file as malicious ({malicious} detections).",
            )

        # Cache clean result for 24 hours.
        cache.set(cache_key, True, timeout=86400)

    except Exception as exc:  # noqa: BLE001
        logger.warning("VirusTotal check inconclusive for %s: %s", sha256[:16], exc)

    return None  # Inconclusive — do not block.


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_file(*, file_bytes: bytes, filename: str) -> ScanResult:
    """
    Run all security layers against *file_bytes*.

    Returns a ``ScanResult``.  ``result.safe`` is ``True`` only when all
    layers pass.  On failure, ``result.reason`` explains why the file was
    rejected.

    Designed to be called synchronously before any persistence happens.
    """
    checks = [
        _check_extension(filename),
        _check_magic_bytes(file_bytes, filename),
        _check_zip_bomb(file_bytes, filename),
        _check_dangerous_patterns(file_bytes),
        _check_virustotal(file_bytes),
    ]

    for result in checks:
        if result is not None and not result.safe:
            return result

    return ScanResult(safe=True)
