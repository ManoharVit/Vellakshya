"""
Isolated Subprocess Worker Runner for Untrusted PDF Processing.
Executes within constrained sandbox parameters, isolated from the main web API.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Add project root to path so services can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.services import converter


def main() -> int:
    parser = argparse.ArgumentParser(description="Vellakshya Isolated Worker Task Runner")
    parser.add_argument(
        "--task", required=True, choices=["html_fixed", "html_semantic", "images_zip", "markdown"]
    )
    parser.add_argument("--input", required=True, help="Path to input PDF file")
    parser.add_argument("--output", required=True, help="Path to output artifact file")
    parser.add_argument("--params", default="{}", help="JSON string of task parameters")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        sys.stderr.write(f"Input file not found: {input_path}\n")
        return 2

    try:
        params = json.loads(args.params)
    except Exception as e:
        sys.stderr.write(f"Invalid JSON params: {e}\n")
        return 3

    start_time = time.perf_counter()
    input_bytes = input_path.read_bytes()
    input_size = len(input_bytes)
    title = params.get("title", input_path.stem)

    try:
        if args.task == "html_fixed":
            result_str = converter.pdf_to_html_fixed(input_bytes, title=title)
            output_path.write_text(result_str, encoding="utf-8")
            media_type = "text/html"

        elif args.task == "html_semantic":
            result_str = converter.pdf_to_html_semantic(input_bytes, title=title)
            output_path.write_text(result_str, encoding="utf-8")
            media_type = "text/html"

        elif args.task == "images_zip":
            dpi = int(params.get("dpi", 150))
            img_format = str(params.get("format", "png"))
            result_bytes = converter.pdf_to_images_zip(input_bytes, dpi=dpi, img_format=img_format)
            output_path.write_bytes(result_bytes)
            media_type = "application/zip"

        elif args.task == "markdown":
            result_str = converter.pdf_to_markdown(input_bytes)
            output_path.write_text(result_str, encoding="utf-8")
            media_type = "text/markdown"

        else:
            raise ValueError(f"Unsupported worker task: {args.task}")

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        output_size = output_path.stat().st_size

        metrics = {
            "status": "succeeded",
            "task": args.task,
            "duration_ms": elapsed_ms,
            "input_bytes": input_size,
            "output_bytes": output_size,
            "media_type": media_type,
            "pid": os.getpid(),
        }

        # Print structured JSON metrics to stdout for parent process parsing
        print(json.dumps(metrics))
        return 0

    except Exception as err:
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        error_info = {
            "status": "failed",
            "task": args.task,
            "duration_ms": elapsed_ms,
            "error": str(err),
            "pid": os.getpid(),
        }
        sys.stderr.write(f"Worker task error: {err}\n")
        print(json.dumps(error_info))
        return 1


if __name__ == "__main__":
    sys.exit(main())
