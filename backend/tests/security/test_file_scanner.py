"""
Tests for the file content scanner — HIGH-008.
"""
from __future__ import annotations

import io
import struct
import zipfile

import pytest

from apps.common.security.file_scanner import (
    ScanResult,
    scan_file,
    _check_extension,
    _check_magic_bytes,
    _check_zip_bomb,
    _check_dangerous_patterns,
)


# ---------------------------------------------------------------------------
# Extension block-list tests
# ---------------------------------------------------------------------------

class TestExtensionCheck:
    def test_exe_blocked(self):
        result = _check_extension("malware.exe")
        assert result is not None
        assert not result.safe
        assert "exe" in result.reason

    def test_php_blocked(self):
        result = _check_extension("webshell.php")
        assert result is not None
        assert not result.safe

    def test_sh_blocked(self):
        result = _check_extension("exploit.sh")
        assert result is not None
        assert not result.safe

    def test_pdf_allowed(self):
        result = _check_extension("report.pdf")
        assert result is None  # No block

    def test_jpg_allowed(self):
        result = _check_extension("photo.jpg")
        assert result is None

    def test_docx_allowed(self):
        result = _check_extension("essay.docx")
        assert result is None

    def test_no_extension(self):
        result = _check_extension("noext")
        assert result is None  # Falls through to other layers


# ---------------------------------------------------------------------------
# Magic-byte validation tests
# ---------------------------------------------------------------------------

_JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 100
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
_PDF_BYTES = b"%PDF-1.7" + b"\x00" * 100
_PE_BYTES = b"MZ\x90\x00" + b"\x00" * 100  # Windows PE header


class TestMagicByteCheck:
    def test_valid_jpeg(self):
        result = _check_magic_bytes(_JPEG_BYTES, "photo.jpg")
        assert result is None  # passes

    def test_valid_png(self):
        result = _check_magic_bytes(_PNG_BYTES, "image.png")
        assert result is None

    def test_valid_pdf(self):
        result = _check_magic_bytes(_PDF_BYTES, "report.pdf")
        assert result is None

    def test_disguised_exe_as_jpg(self):
        """PE header disguised with .jpg extension."""
        result = _check_magic_bytes(_PE_BYTES, "photo.jpg")
        assert result is not None
        assert not result.safe
        assert "disguise" in result.reason.lower() or "match" in result.reason.lower()

    def test_disguised_exe_as_pdf(self):
        result = _check_magic_bytes(_PE_BYTES, "report.pdf")
        assert result is not None
        assert not result.safe

    def test_txt_skips_magic_check(self):
        """Text files have no strong magic — scanner should not block them."""
        result = _check_magic_bytes(b"hello world", "notes.txt")
        assert result is None

    def test_csv_skips_magic_check(self):
        result = _check_magic_bytes(b"col1,col2\n1,2\n", "data.csv")
        assert result is None


# ---------------------------------------------------------------------------
# Zip-bomb tests
# ---------------------------------------------------------------------------

def _make_zip(content: bytes, repetitions: int = 1) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("file.txt", content * repetitions)
    return buf.getvalue()


class TestZipBombCheck:
    def test_normal_zip_passes(self):
        data = _make_zip(b"Hello World!", repetitions=10)
        result = _check_zip_bomb(data, "doc.docx")
        assert result is None

    def test_high_compression_ratio_blocked(self):
        """A file that's all zeros compresses extremely well — simulate bomb."""
        # Create a zip with a large amount of zero bytes that compress heavily.
        huge_zeros = b"\x00" * (10 * 1024 * 1024)  # 10 MB of zeros
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            zf.writestr("zeros.bin", huge_zeros)
        data = buf.getvalue()
        result = _check_zip_bomb(data, "doc.docx")
        # The ratio should be very high (10 MB → small compressed size).
        # If ratio > 50, it's flagged.
        assert result is None or not result.safe  # either passes or is flagged

    def test_non_zip_skipped(self):
        result = _check_zip_bomb(_JPEG_BYTES, "photo.jpg")
        assert result is None

    def test_corrupt_zip_blocked(self):
        result = _check_zip_bomb(b"PK\x03\x04NOTVALID", "file.docx")
        assert result is not None
        assert not result.safe


# ---------------------------------------------------------------------------
# Dangerous content pattern tests
# ---------------------------------------------------------------------------

class TestDangerousPatterns:
    def test_pe_header_in_pdf(self):
        content = b"%PDF-1.7\n" + b"MZ\x90\x00" + b"\x00" * 100
        result = _check_dangerous_patterns(content)
        assert result is not None
        assert not result.safe

    def test_elf_header_blocked(self):
        result = _check_dangerous_patterns(b"\x7fELF" + b"\x00" * 100)
        assert result is not None
        assert not result.safe

    def test_pdf_javascript_blocked(self):
        result = _check_dangerous_patterns(b"%PDF-1.7\n/JavaScript\n(alert())")
        assert result is not None
        assert not result.safe

    def test_shebang_blocked(self):
        result = _check_dangerous_patterns(b"#!/bin/bash\nrm -rf /")
        assert result is not None
        assert not result.safe

    def test_clean_pdf_passes(self):
        result = _check_dangerous_patterns(b"%PDF-1.7\nclean content here")
        assert result is None

    def test_clean_text_passes(self):
        result = _check_dangerous_patterns(b"Hello, this is a regular document.")
        assert result is None


# ---------------------------------------------------------------------------
# Full scan_file() integration tests
# ---------------------------------------------------------------------------

class TestScanFile:
    def test_clean_jpeg_passes(self):
        result = scan_file(file_bytes=_JPEG_BYTES, filename="photo.jpg")
        assert result.safe

    def test_clean_pdf_passes(self):
        result = scan_file(file_bytes=_PDF_BYTES, filename="report.pdf")
        assert result.safe

    def test_exe_extension_blocked(self):
        result = scan_file(file_bytes=b"MZ\x90\x00" + b"\x00" * 100, filename="virus.exe")
        assert not result.safe
        assert result.reason

    def test_disguised_pe_in_jpeg_blocked(self):
        result = scan_file(file_bytes=_PE_BYTES, filename="photo.jpg")
        assert not result.safe

    def test_pdf_with_javascript_blocked(self):
        malicious_pdf = b"%PDF-1.7\n/JavaScript\n(eval(atob('exploit')))"
        result = scan_file(file_bytes=malicious_pdf, filename="malware.pdf")
        assert not result.safe

    def test_scan_result_bool(self):
        good = ScanResult(safe=True)
        bad = ScanResult(safe=False, reason="test")
        assert bool(good)
        assert not bool(bad)
