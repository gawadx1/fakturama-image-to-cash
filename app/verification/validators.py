"""Financial and order validation helpers."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from app.exceptions import ManualReviewRequired
from app.models.order import OrderData, OrderItem

TWOPLACES = Decimal("0.01")
TOLERANCE = Decimal("0.02")


def round_money(value: Decimal) -> Decimal:
    return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def calculate_line_net(item: OrderItem) -> Decimal:
    discount_factor = Decimal("1") - (item.discount_percentage / Decimal("100"))
    return round_money(item.quantity * item.unit_net_price * discount_factor)


def calculate_line_gross(item: OrderItem) -> Decimal:
    net = calculate_line_net(item)
    vat_factor = Decimal("1") + (item.vat_percentage / Decimal("100"))
    return round_money(net * vat_factor)


def calculate_gross_unit_price(unit_net_price: Decimal, vat_percentage: Decimal) -> Decimal:
    return round_money(unit_net_price * (Decimal("1") + vat_percentage / Decimal("100")))


def calculate_order_totals(items: list[OrderItem]) -> tuple[Decimal, Decimal, Decimal]:
    net_total = Decimal("0")
    gross_total = Decimal("0")
    for item in items:
        line_net = calculate_line_net(item)
        line_gross = calculate_line_gross(item)
        net_total += line_net
        gross_total += line_gross
    net_total = round_money(net_total)
    gross_total = round_money(gross_total)
    vat_total = round_money(gross_total - net_total)
    return net_total, vat_total, gross_total


def totals_match(expected: Decimal | None, actual: Decimal, label: str) -> None:
    if expected is None:
        return
    if abs(expected - actual) > TOLERANCE:
        raise ManualReviewRequired(
            reason=f"{label} mismatch: expected {expected}, calculated {actual}",
            stage="Order Totals Validation",
            suggested_action="Verify OCR extraction and line item values.",
        )


def validate_order_totals(order: OrderData) -> None:
    net, vat, gross = calculate_order_totals(order.items)
    totals_match(order.totals.net_total, net, "Net total")
    totals_match(order.totals.vat_total, vat, "VAT total")
    totals_match(order.totals.gross_total, gross, "Gross total")

    for idx, item in enumerate(order.items, start=1):
        if item.source_total is None:
            continue
        calculated = calculate_line_net(item)
        if abs(item.source_total - calculated) > TOLERANCE:
            raise ManualReviewRequired(
                reason=(
                    f"Line {idx} total mismatch for SKU {item.sku}: "
                    f"source {item.source_total}, calculated {calculated}"
                ),
                stage="Line Item Validation",
            )


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.strip().lower().split())


def exact_match(*pairs: tuple[str | None, str | None]) -> bool:
    return all(normalize_text(a) == normalize_text(b) for a, b in pairs)


def vat_name(percentage: Decimal) -> str:
    normalized = percentage.normalize()
    text = format(normalized, "f").rstrip("0").rstrip(".")
    return f"VAT {text}%"


PAYMENT_METHOD_MAP = {
    "bank transfer": "Credit transfer",
    "credit card": "Credit card",
    "sepa direct debit": "SEPA direct debit",
}


def map_payment_method(name: str | None) -> str:
    if not name:
        return ""
    mapped = PAYMENT_METHOD_MAP.get(normalize_text(name))
    return mapped or name.strip()
