"""Extraction validation helpers."""

from __future__ import annotations

from app.exceptions import ManualReviewRequired
from app.models.order import OrderData


def validate_extraction(order: OrderData) -> None:
    """Ensure extracted order has minimum required fields for automation."""
    missing: list[str] = []

    if order.order_date is None:
        missing.append("order_date")
    if not order.external_reference:
        missing.append("external_reference")
    if not order.customer_display_name:
        missing.append("customer name")
    if not order.payment.payment_method:
        missing.append("payment_method")

    for idx, item in enumerate(order.items, start=1):
        if not item.sku:
            missing.append(f"items[{idx}].sku")
        if item.quantity <= 0:
            missing.append(f"items[{idx}].quantity")
        if item.unit_net_price < 0:
            missing.append(f"items[{idx}].unit_net_price")

    if missing:
        raise ManualReviewRequired(
            reason=f"Missing required extracted fields: {', '.join(missing)}",
            stage="Extraction Validation",
            suggested_action="Improve OCR quality or verify the source image contains all fields.",
        )
