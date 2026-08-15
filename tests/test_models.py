"""Pydantic model tests."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.order import OrderData, OrderItem, PaymentStatus


def test_order_item_decimal_coercion():
    item = OrderItem(
        sku="CHR-ERG-01",
        quantity="2",
        unit_net_price="120.50",
        vat_percentage=19,
        discount_percentage="5",
    )
    assert item.quantity == Decimal("2")
    assert item.unit_net_price == Decimal("120.50")
    assert item.discount_percentage == Decimal("5")


def test_order_data_payment_status_normalization():
    order = OrderData.model_validate(
        {
            "items": [
                {
                    "sku": "A1",
                    "quantity": 1,
                    "unit_net_price": 10,
                    "vat_percentage": 19,
                }
            ],
            "customer": {"company": "Acme GmbH"},
            "payment": {"payment_status": "paid"},
        }
    )
    assert order.payment.payment_status == PaymentStatus.PAID


def test_order_requires_items():
    with pytest.raises(ValidationError):
        OrderData.model_validate({"customer": {"company": "Acme"}})


def test_order_date_parsing():
    order = OrderData.model_validate(
        {
            "order_date": "14.07.2026",
            "items": [
                {
                    "sku": "A1",
                    "quantity": 1,
                    "unit_net_price": 10,
                    "vat_percentage": 19,
                }
            ],
            "customer": {"company": "Acme"},
        }
    )
    assert order.order_date == date(2026, 7, 14)
