"""
Synthetic & Anonymized Test Data Generator for Vellakshya PDF Workstation.

STRICT DATA PRIVACY & COMPLIANCE NOTICE:
Do not upload real customer PDFs, private keys, signing certificates,
production database dumps, or confidential documents into AI tools.
All data produced by this generator is 100% synthetic, procedural, or anonymized.

Author: Giri Manohar Vemula
Repository: https://github.com/ManoharVit/Vellakshya.git
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

TEST_DATA_DIR = Path(__file__).resolve().parent.parent / "test-data"
SYNTHETIC_DIR = TEST_DATA_DIR / "synthetic"
SYNTHETIC_DIR.mkdir(parents=True, exist_ok=True)


def generate_metadata_suite() -> dict[str, dict[str, str]]:
    """
    Generates varied metadata profiles across enterprise personas.
    """
    profiles = {
        "corporate_report": {
            "title": "Synthetic Q3 Financial Performance Evaluation",
            "author": "Lead Architect Giri Manohar Vemula",
            "subject": "Enterprise Auditing & Performance Metrics",
            "keywords": "finance;synthetic;audit;performance;q3",
            "creator": "Vellakshya PDF Studio",
            "producer": "PyMuPDF High-Fidelity Engine",
        },
        "legal_contract": {
            "title": "Master Services Agreement (Template)",
            "author": "Corporate Legal Department",
            "subject": "Confidential Non-Disclosure and IP Rights",
            "keywords": "legal;agreement;contract;nda;intellectual-property",
            "creator": "Vellakshya Contract Author",
            "producer": "PyMuPDF Crypto Signer",
        },
        "multilingual_spec": {
            "title": "Global Architecture Specification (Internationalized)",
            "author": "Systems Engineering Council",
            "subject": "Internationalization, RTL Text, CJK Character Encodings",
            "keywords": "i18n;unicode;cjk;rtl;bidi;typography",
            "creator": "Vellakshya Multilingual Core",
            "producer": "PyMuPDF Font Engine",
        },
    }
    with open(SYNTHETIC_DIR / "metadata_profiles.json", "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2)
    return profiles


def generate_multilingual_pdf(output_path: Path) -> Path:
    """
    Generates a PDF containing diverse Unicode scripts: Latin, Devanagari,
    Cyrillic, Arabic (RTL), and Japanese (CJK) to test platform-independent typography.
    """
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    page.insert_text(
        fitz.Point(72, 72), "Vellakshya International Unicode & Typography Test", fontsize=16
    )
    page.insert_text(
        fitz.Point(72, 110),
        "English: High fidelity visual layout across all platforms.",
        fontsize=11,
    )
    page.insert_text(
        fitz.Point(72, 140),
        "Hindi (Devanagari): उच्च-विश्वसनीयता वाला पीडीएफ दस्तावेज़ इंजन।",
        fontsize=11,
    )
    page.insert_text(
        fitz.Point(72, 170),
        "Spanish: Diseño visual exacto e independiente de la plataforma.",
        fontsize=11,
    )
    page.insert_text(
        fitz.Point(72, 200),
        "Cyrillic: Точное визуальное отображение документов на всех устройствах.",
        fontsize=11,
    )
    page.insert_text(
        fitz.Point(72, 230),
        "Japanese (CJK): すべてのデバイスで崩れない正確なPDFレイアウト。",
        fontsize=11,
    )
    page.insert_text(
        fitz.Point(72, 260),
        "Arabic (RTL): تصميم مستندات ثابت ومستقل عن المنصة بدون أي تشويه.",
        fontsize=11,
    )

    meta = {
        "title": "Vellakshya International Unicode Benchmark",
        "author": "Giri Manohar Vemula",
        "subject": "Multilingual Layout Fidelity",
        "keywords": "unicode;i18n;multilingual;hindi;arabic;japanese;cyrillic",
    }
    doc.set_metadata(meta)
    doc.save(output_path, deflate=True)
    doc.close()
    return output_path


def generate_edge_case_filenames() -> list[str]:
    """
    Generates hazardous, multi-byte, whitespace, and symbol-dense filenames
    to verify safe sanitization and upload handling.
    """
    filenames = [
        "standard_report_2026.pdf",
        "spaces in file name test.pdf",
        "symbols_#$&%@!()_+=-[]{};,.pdf",
        "dot.separated.multi.extension.draft.pdf",
        "日本語_ドキュメント_契約書.pdf",
        "تقرير_المبيعات_الافتراضي_2026.pdf",
        "документ_налоговой_отчетности.pdf",
        f"very_long_filename_{'a' * 180}.pdf",
    ]
    with open(SYNTHETIC_DIR / "edge_case_filenames.json", "w", encoding="utf-8") as f:
        json.dump(filenames, f, indent=2)
    return filenames


def generate_user_roles_matrix() -> dict[str, Any]:
    """
    Defines synthetic user roles, permission matrices, and token mocks.
    """
    roles = {
        "roles": {
            "admin": {
                "permissions": [
                    "view",
                    "upload",
                    "edit",
                    "annotate",
                    "convert",
                    "sign",
                    "download",
                    "delete",
                    "manage_users",
                ],
                "can_download_restricted": True,
                "can_edit_restricted": True,
            },
            "editor": {
                "permissions": [
                    "view",
                    "upload",
                    "edit",
                    "annotate",
                    "convert",
                    "sign",
                    "download",
                ],
                "can_download_restricted": True,
                "can_edit_restricted": True,
            },
            "viewer": {
                "permissions": ["view", "render"],
                "can_download_restricted": False,
                "can_edit_restricted": False,
            },
            "external_auditor": {
                "permissions": ["view", "inspect", "audit_signatures"],
                "can_download_restricted": False,
                "can_edit_restricted": False,
            },
        },
        "synthetic_test_users": [
            {"email": "admin.synth@vellakshya.test", "role": "admin"},
            {"email": "editor.synth@vellakshya.test", "role": "editor"},
            {"email": "viewer.restricted@vellakshya.test", "role": "viewer"},
            {"email": "auditor.external@vellakshya.test", "role": "external_auditor"},
        ],
    }
    with open(SYNTHETIC_DIR / "user_roles_matrix.json", "w", encoding="utf-8") as f:
        json.dump(roles, f, indent=2)
    return roles


def generate_structured_table_pdf(output_path: Path) -> Path:
    """
    Generates a PDF containing a multi-row, multi-column financial table with headers.
    """
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)

    page.insert_text(
        fitz.Point(72, 72),
        "Consolidated Corporate Statement",
        fontsize=16,
        fontname="Helvetica-Bold",
    )

    # Table layout parameters
    start_x = 72
    start_y = 120
    row_h = 24
    col_w = [180, 100, 100, 90]

    headers = ["Department / Cost Center", "Budget (USD)", "Actual (USD)", "Variance"]
    data = [
        ["Core Infrastructure Engineering", "$1,450,000", "$1,380,000", "-4.8%"],
        ["Quality Assurance Automation", "$620,000", "$595,000", "-4.0%"],
        ["Security & Cryptographic Audit", "$480,000", "$480,000", "0.0%"],
        ["Document Rendering Systems", "$950,000", "$910,000", "-4.2%"],
        ["Client Experience & UI/UX", "$350,000", "$340,000", "-2.8%"],
    ]

    # Draw table header background
    page.draw_rect(
        fitz.Rect(start_x, start_y, start_x + sum(col_w), start_y + row_h),
        color=(0.2, 0.4, 0.8),
        fill=(0.9, 0.94, 1.0),
    )
    curr_x = start_x
    for i, h in enumerate(headers):
        page.insert_text(
            fitz.Point(curr_x + 6, start_y + 16),
            h,
            fontsize=10,
            fontname="Helvetica-Bold",
            color=(0.1, 0.2, 0.6),
        )
        curr_x += col_w[i]

    # Draw data rows
    for r_idx, row in enumerate(data):
        y = start_y + (r_idx + 1) * row_h
        page.draw_rect(
            fitz.Rect(start_x, y, start_x + sum(col_w), y + row_h), color=(0.85, 0.85, 0.85)
        )
        c_x = start_x
        for c_idx, val in enumerate(row):
            page.insert_text(fitz.Point(c_x + 6, y + 16), val, fontsize=9, color=(0.15, 0.15, 0.15))
            c_x += col_w[c_idx]

    doc.save(output_path, deflate=True)
    doc.close()
    return output_path


def main():
    print(f"Generating synthetic test suite in {SYNTHETIC_DIR}...")
    generate_metadata_suite()
    generate_multilingual_pdf(SYNTHETIC_DIR / "synthetic_multilingual.pdf")
    generate_structured_table_pdf(SYNTHETIC_DIR / "synthetic_table.pdf")
    generate_edge_case_filenames()
    generate_user_roles_matrix()
    print("Synthetic test data generation complete (100% anonymized, zero customer data).")


if __name__ == "__main__":
    main()
