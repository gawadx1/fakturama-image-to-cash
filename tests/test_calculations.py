"""Calculation and matching tests."""

from decimal import Decimal

import pytest

from app.exceptions import ManualReviewRequired
from app.models.order import OrderData, OrderItem, OrderTotals
from app.verification.validators import (
    calculate_gross_unit_price,
    calculate_line_net,
    calculate_order_totals,
    exact_match,
    map_payment_method,
    validate_order_totals,
    vat_name,
)


def test_line_net_with_discount():
    item = OrderItem(
        sku="X",
        quantity=Decimal("2"),
        unit_net_price=Decimal("100"),
        vat_percentage=Decimal("19"),
        discount_percentage=Decimal("10"),
    )
    assert calculate_line_net(item) == Decimal("180.00")


def test_gross_unit_price():
    assert calculate_gross_unit_price(Decimal("100"), Decimal("19")) == Decimal("119.00")


def test_order_totals():
    items = [
        OrderItem(
            sku="A",
            quantity=Decimal("2"),
            unit_net_price=Decimal("50"),
            vat_percentage=Decimal("19"),
        )
    ]
    net, vat, gross = calculate_order_totals(items)
    assert net == Decimal("100.00")
    assert vat == Decimal("19.00")
    assert gross == Decimal("119.00")


def test_validate_order_totals_match():
    order = OrderData.model_validate(
        {
            "items": [
                {
                    "sku": "A",
                    "quantity": 2,
                    "unit_net_price": 50,
                    "vat_percentage": 19,
                }
            ],
            "customer": {"company": "Acme"},
            "totals": {"net_total": 100, "vat_total": 19, "gross_total": 119},
        }
    )
    validate_order_totals(order)


def test_validate_order_totals_mismatch():
    order = OrderData.model_validate(
        {
            "items": [
                {
                    "sku": "A",
                    "quantity": 2,
                    "unit_net_price": 50,
                    "vat_percentage": 19,
                }
            ],
            "customer": {"company": "Acme"},
            "totals": {"gross_total": 999},
        }
    )
    with pytest.raises(ManualReviewRequired):
        validate_order_totals(order)


def test_exact_match():
    assert exact_match(("Acme GmbH", "acme gmbh"))


def test_payment_method_mapping():
    assert map_payment_method("Bank Transfer") == "Credit transfer"


def test_vat_name():
    assert vat_name(Decimal("19")) == "VAT 19%"
