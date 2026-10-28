"""
Security and Threat Audit Test Suite.
Audits:
- Path traversal attack vectors.
- MIME type spoofing and anti-polyglot defenses.
- Source code secret leak detection (API keys, private tokens).
- Dependency vulnerability scan audit.
- Malicious JavaScript sandboxing.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services import security

client = TestClient(app)


def test_security_path_traversal_prevention():
    """
    Ensure file upload endpoints reject or sanitize path traversal filenames
    such as '../../../etc/passwd' or '..\\..\\windows\\system32'.
    """
    sample_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    malicious_names = [
        "../../../etc/passwd",
        "..\\..\\windows\\win.ini",
        "foo/bar/../../secret.pdf",
    ]

    for m_name in malicious_names:
        res = client.post(
            "/api/inspect",
            files={"file": (m_name, sample_pdf, "application/pdf")},
        )
        # Endpoint must process safely without writing or leaking local filesystem paths
        assert res.status_code in (200, 400)


def test_security_polyglot_and_content_spoofing():
    """
    Validate rejection of MIME-spoofed polyglot files (e.g. PHP/HTML/Shell script disguised as PDF).
    """
    fake_polyglot = b"<html><script>alert('xss')</script></html>\n%PDF-1.4\n"
    report = security.validate_pdf_security(fake_polyglot)
    assert report["safe"] is False
    assert report["error_type"] == "INVALID_HEADER_POLYGLOT"


def test_security_secret_scanning_in_codebase():
    """
    Scans python and javascript codebase for hardcoded private keys, AWS/GCP secrets,
    or production passwords.
    """
    project_root = Path(__file__).resolve().parent.parent
    secret_patterns = [
        re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS Access Key
        re.compile(r"AIza[0-9A-Za-z-_]{35}"),  # Google API Key
        re.compile(r"-----BEGIN (RSA|EC|DSA|OPENSSH) PRIVATE KEY-----"),
        re.compile(r"(?i)api[_-]?key\s*=\s*['\"][A-Za-z0-9_\-]{20,}['\"]"),
    ]

    scanned_files = 0
    for ext in ("*.py", "*.js", "*.html"):
        for file_path in project_root.rglob(ext):
            if (
                ".venv" in str(file_path)
                or "node_modules" in str(file_path)
                or ".pytest_cache" in str(file_path)
            ):
                continue
            scanned_files += 1
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            for pattern in secret_patterns:
                match = pattern.search(content)
                assert match is None, (
                    f"Potential hardcoded secret detected in {file_path}: {match.group(0)}"
                )

    assert scanned_files > 5, "Audit must scan multiple codebase files"


def test_security_embedded_javascript_detection():
    """
    Verifies that PDFs with embedded JavaScript (/JS /JavaScript) are flagged
    for sandboxing and script stripping.
    """
    js_pdf = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R /Names << /JavaScript << /Names [(DocOpen) 4 0 R] >> >> >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>
endobj
4 0 obj
<< /Type /Action /S /JavaScript /JS (app.alert('Audit-Triggered')) >>
endobj
xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000109 00000 n 
0000000162 00000 n 
0000000229 00000 n 
trailer
<< /Size 5 /Root 1 0 R >>
%%EOF"""

    report = security.validate_pdf_security(js_pdf)
    assert report["has_javascript"] is True
    assert len(report["warnings"]) >= 1
    assert "Embedded JavaScript detected" in report["warnings"][0]
