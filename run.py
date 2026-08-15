#!/usr/bin/env python
"""CLI entry point for Fakturama image-to-cash automation."""

from __future__ import annotations

import argparse
import sys

from app.config import Settings, get_settings
from app.main import inspect_ui, run_automation, run_extraction_only


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract order data from an image and automate Fakturama."
    )
    parser.add_argument("--image", help="Path to the order image")
    parser.add_argument(
        "--fakturama-path",
        help="Path to Fakturama.exe (overrides FAKTURAMA_PATH)",
    )
    parser.add_argument(
        "--inspect-ui",
        action="store_true",
        help="Print Fakturama UIA tree for debugging",
    )
    parser.add_argument(
        "--extract-only",
        action="store_true",
        help="Run OCR and Groq extraction without launching Fakturama",
    )
    parser.add_argument(
        "--ui-depth",
        type=int,
        default=4,
        help="Depth for --inspect-ui output",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    settings = get_settings()
    if args.fakturama_path:
        settings = Settings(
            groq_api_key=settings.groq_api_key,
            groq_model=settings.groq_model,
            fakturama_path=args.fakturama_path,
            ocr_lang=settings.ocr_lang,
            ui_timeout=settings.ui_timeout,
            tesseract_cmd=settings.tesseract_cmd,
            screenshots_dir=settings.screenshots_dir,
            groq_max_retries=settings.groq_max_retries,
        )

    if args.inspect_ui:
        return inspect_ui(settings=settings, max_depth=args.ui_depth)

    if not args.image:
        parser.error("--image is required unless --inspect-ui is used")

    if args.extract_only:
        return run_extraction_only(args.image, settings=settings)

    return run_automation(args.image, settings=settings)


if __name__ == "__main__":
    sys.exit(main())
