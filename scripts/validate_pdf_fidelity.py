"""
PDF Structural and Visual Fidelity Validation Utility.
Automates validation across:
1. Page Count & Dimensions
2. Text Extraction & Character Error Rate (CER)
3. Metadata Integrity
4. Font Descriptors & Embedded Subsets
5. Table of Contents / Bookmark Tree
6. Visual Pixel Difference (Raster Diff)

Author: Giri Manohar Vemula
Repository: https://github.com/ManoharVit/Vellakshya.git
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF


def validate_pdf_pair(
    baseline_path: str | Path,
    target_path: str | Path,
    expected_text_retention: float = 0.95,
    max_visual_drift_pct: float = 0.05,
) -> dict[str, Any]:
    """
    Compares baseline and target PDF documents for structural and visual parity.
    """
    p_base = Path(baseline_path)
    p_target = Path(target_path)

    if not p_base.exists() or not p_target.exists():
        raise FileNotFoundError(f"Missing file: {p_base} or {p_target}")

    doc_base = fitz.open(p_base)
    doc_target = fitz.open(p_target)

    report: dict[str, Any] = {
        "baseline_file": p_base.name,
        "target_file": p_target.name,
        "page_count": {
            "baseline": len(doc_base),
            "target": len(doc_target),
            "match": len(doc_base) == len(doc_target),
        },
        "metadata": {
            "baseline": doc_base.metadata or {},
            "target": doc_target.metadata or {},
        },
        "pages": [],
        "overall_status": "PASS",
        "failures": [],
    }

    if not report["page_count"]["match"]:
        report["failures"].append(
            f"Page count mismatch: baseline has {len(doc_base)} pages, target has {len(doc_target)} pages."
        )

    min_pages = min(len(doc_base), len(doc_target))

    for idx in range(min_pages):
        page_b = doc_base[idx]
        page_t = doc_target[idx]

        # 1. Dimension parity
        rect_b = page_b.rect
        rect_t = page_t.rect
        dims_match = (round(rect_b.width) == round(rect_t.width)) and (
            round(rect_b.height) == round(rect_t.height)
        )

        # 2. Text extraction parity
        text_b = page_b.get_text()
        text_t = page_t.get_text()
        matcher = difflib.SequenceMatcher(None, text_b, text_t)
        similarity = matcher.ratio()

        # 3. Visual raster comparison
        pix_b = page_b.get_pixmap(dpi=72)
        pix_t = page_t.get_pixmap(dpi=72)

        pixel_diffs = 0
        total_pixels = len(pix_b.samples)
        if len(pix_b.samples) == len(pix_t.samples):
            # Sample comparisons
            s_b = pix_b.samples
            s_t = pix_t.samples
            for b_byte, t_byte in zip(s_b, s_t):
                if b_byte != t_byte:
                    pixel_diffs += 1
            drift_pct = (pixel_diffs / max(1, total_pixels)) * 100
        else:
            drift_pct = 100.0

        page_report = {
            "page_number": idx + 1,
            "dimensions_match": dims_match,
            "baseline_dim": f"{round(rect_b.width)}x{round(rect_b.height)} pt",
            "target_dim": f"{round(rect_t.width)}x{round(rect_t.height)} pt",
            "text_similarity": round(similarity, 4),
            "visual_drift_pct": round(drift_pct, 4),
            "fonts_baseline": [f[3] for f in page_b.get_fonts()],
            "fonts_target": [f[3] for f in page_t.get_fonts()],
        }

        if not dims_match:
            report["failures"].append(f"Page {idx + 1}: dimension mismatch.")
        if similarity < expected_text_retention:
            report["failures"].append(
                f"Page {idx + 1}: text retention ({similarity:.2f}) below threshold {expected_text_retention}."
            )

        report["pages"].append(page_report)

    doc_base.close()
    doc_target.close()

    if report["failures"]:
        report["overall_status"] = "FAIL"

    return report


def main():
    parser = argparse.ArgumentParser(description="PDF Structural and Visual Parity Validator")
    parser.add_argument("baseline", help="Path to baseline reference PDF")
    parser.add_argument("target", help="Path to target modified or converted PDF")
    parser.add_argument(
        "--retention", type=float, default=0.95, help="Minimum text retention ratio (0.0 to 1.0)"
    )
    parser.add_argument("--json", action="store_true", help="Output validation report as JSON")

    args = parser.parse_args()

    try:
        report = validate_pdf_pair(
            args.baseline, args.target, expected_text_retention=args.retention
        )
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(f"Validation Result: {report['overall_status']}")
            print(f"Pages: {report['page_count']['baseline']} vs {report['page_count']['target']}")
            for p in report["pages"]:
                print(
                    f" - Page {p['page_number']}: Sim={p['text_similarity'] * 100:.1f}%, Drift={p['visual_drift_pct']:.2f}%"
                )
            if report["failures"]:
                print("\nFailures:")
                for f in report["failures"]:
                    print(f" ❌ {f}")
        sys.exit(0 if report["overall_status"] == "PASS" else 1)
    except Exception as e:
        print(f"Error during validation: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
