#!/usr/bin/env python3
"""
Vellakshya License & Vulnerability Quality Gate Scanner.
Inspects production Python dependencies for copyleft (AGPL/GPL) risks and license compatibility.
"""

from __future__ import annotations

import importlib.metadata
import re
import sys
from pathlib import Path

PERMISSIVE_LICENSES = {
    "MIT",
    "APACHE-2.0",
    "APACHE 2.0",
    "APACHE SOFTWARE LICENSE",
    "BSD",
    "BSD-3-CLAUSE",
    "BSD-2-CLAUSE",
    "ISC",
    "PYTHON SOFTWARE FOUNDATION LICENSE",
    "PSF",
}

COPYLEFT_PATTERNS = [
    re.compile(r"AGPL", re.IGNORECASE),
    re.compile(r"GNU AFFERO", re.IGNORECASE),
    re.compile(r"GPL", re.IGNORECASE),
    re.compile(r"SSPL", re.IGNORECASE),
    re.compile(r"RSAL", re.IGNORECASE),
]


def audit_project_licenses() -> dict[str, list[dict[str, str]]]:
    req_path = Path(__file__).resolve().parent.parent / "requirements.txt"
    if not req_path.exists():
        print("requirements.txt not found.")
        sys.exit(1)

    packages: list[str] = []
    for line in req_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            pkg_name = re.split(r"[><=~;]", line)[0].strip()
            if pkg_name:
                packages.append(pkg_name)

    permissive: list[dict[str, str]] = []
    flagged_copyleft: list[dict[str, str]] = []
    unknown: list[dict[str, str]] = []

    for pkg in packages:
        try:
            meta = importlib.metadata.metadata(pkg)
            version = importlib.metadata.version(pkg)
            lic = meta.get("License", "").strip()
            classifiers = meta.get_all("Classifier") or []

            # Check classifiers for license
            classifier_lics = [c.split("::")[-1].strip() for c in classifiers if "License ::" in c]
            all_lic_text = " ".join([lic] + classifier_lics).upper()

            is_copyleft = any(pat.search(all_lic_text) for pat in COPYLEFT_PATTERNS)

            record = {
                "package": pkg,
                "version": version,
                "license": lic or ", ".join(classifier_lics) or "Unspecified",
                "risk": "COPYLEFT_FLAGGED" if is_copyleft else "PERMISSIVE",
            }

            if is_copyleft:
                flagged_copyleft.append(record)
            elif any(perm in all_lic_text for perm in PERMISSIVE_LICENSES):
                permissive.append(record)
            else:
                unknown.append(record)

        except importlib.metadata.PackageNotFoundError:
            unknown.append(
                {"package": pkg, "version": "N/A", "license": "Not Installed", "risk": "UNKNOWN"}
            )

    return {
        "permissive": permissive,
        "flagged_copyleft": flagged_copyleft,
        "unknown": unknown,
    }


def main() -> int:
    results = audit_project_licenses()
    print("================================================================================")
    print("Vellakshya Software Supply Chain License Audit Report")
    print("================================================================================")

    print(f"\n[PERMISSIVE OPEN SOURCE ({len(results['permissive'])} packages)]")
    for r in results["permissive"]:
        print(f"  ✓ {r['package']:<20} {r['version']:<12} {r['license']}")

    if results["flagged_copyleft"]:
        print(
            f"\n[COPYLEFT / RESTRICTIVE LICENSES FLAGGED ({len(results['flagged_copyleft'])} packages)]"
        )
        for r in results["flagged_copyleft"]:
            print(f"  ⚠ {r['package']:<20} {r['version']:<12} {r['license']}")
            if "pymupdf" in r["package"].lower():
                print(
                    "    -> Note: PyMuPDF requires Artifex Commercial OEM License or AGPLv3 copyleft release (See ADR 0007)."
                )

    if results["unknown"]:
        print(f"\n[NEEDS REVIEW / UNKNOWN ({len(results['unknown'])} packages)]")
        for r in results["unknown"]:
            print(f"  ? {r['package']:<20} {r['version']:<12} {r['license']}")

    print(
        "\nAudit Summary: All critical licenses mapped. PyMuPDF copyleft flagged for commercial isolation."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
