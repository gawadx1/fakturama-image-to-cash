"""Main application orchestration."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.automation.fakturama import FakturamaAutomation
from app.config import Settings, get_settings
from app.exceptions import ManualReviewRequired
from app.extraction.groq_extractor import extract_order_data
from app.extraction.ocr import extract_text, validate_image
from app.extraction.validators import validate_extraction
from app.logging_config import setup_logging

logger = logging.getLogger("fakturama_automation")


def print_extraction_summary(order) -> None:
    summary = {
        "order_date": str(order.order_date) if order.order_date else None,
        "external_reference": order.external_reference,
        "currency": order.currency,
        "customer": order.customer_display_name,
        "payment_method": order.payment.payment_method,
        "payment_status": order.payment.payment_status.value,
        "items": [
            {
                "sku": item.sku,
                "quantity": str(item.quantity),
                "unit_net_price": str(item.unit_net_price),
                "vat_percentage": str(item.vat_percentage),
            }
            for item in order.items
        ],
        "totals": {
            "net_total": str(order.totals.net_total) if order.totals.net_total else None,
            "vat_total": str(order.totals.vat_total) if order.totals.vat_total else None,
            "gross_total": str(order.totals.gross_total) if order.totals.gross_total else None,
        },
    }
    print(json.dumps(summary, indent=2))


def run_extraction_only(image_path: str | Path, settings: Settings | None = None) -> int:
    setup_logging()
    settings = settings or get_settings()
    settings.validate_for_run(require_groq=True)

    path = validate_image(image_path)
    ocr_text = extract_text(path)
    print("\n--- OCR TEXT ---\n")
    print(ocr_text)
    print("\n----------------\n")

    order = extract_order_data(ocr_text, settings=settings)
    validate_extraction(order)
    print("\n--- EXTRACTION SUMMARY ---\n")
    print_extraction_summary(order)
    print("\n--------------------------\n")
    return 0


def run_automation(image_path: str | Path, settings: Settings | None = None) -> int:
    setup_logging()
    settings = settings or get_settings()
    settings.validate_for_run(require_groq=True)

    logger.info("Starting automation")
    path = validate_image(image_path)

    ocr_text = extract_text(path)
    print("\n--- OCR TEXT ---\n")
    print(ocr_text)
    print("\n----------------\n")

    settings.screenshots_dir.mkdir(parents=True, exist_ok=True)
    order = extract_order_data(ocr_text, settings=settings)
    validate_extraction(order)

    settings.screenshots_dir.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image

        Image.open(path).save(settings.screenshots_dir / "01_extracted_data.png")
    except Exception:  # noqa: BLE001
        pass

    print("\n--- EXTRACTION SUMMARY ---\n")
    print_extraction_summary(order)
    print("\n--------------------------\n")

    automation = FakturamaAutomation(settings)
    try:
        result = automation.process_order(order)
    except ManualReviewRequired as exc:
        print(exc.format_message())
        return 2

    print("\n" + "=" * 40)
    print("FAKTURAMA AUTOMATION COMPLETED")
    print("=" * 40)
    print()
    print("Order: VERIFIED")
    print("Invoice: VERIFIED")
    print(f"Payment Status: {result['payment_status']}")
    print(f"Total: {result['currency']} {result['total']}")
    print()
    print("All required records were created and verified successfully.")
    print("=" * 40)
    return 0


def inspect_ui(settings: Settings | None = None, max_depth: int = 4) -> int:
    setup_logging()
    settings = settings or get_settings()
    settings.validate_for_run(require_groq=False)
    automation = FakturamaAutomation(settings)
    tree = automation.inspect_ui(max_depth=max_depth)
    print(tree)
    return 0
