"""Extraction parsing tests."""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.extraction.groq_extractor import GroqOrderExtractor, _parse_llm_json
from app.models.order import OrderData


SAMPLE_PAYLOAD = {
    "order_date": "2026-07-14",
    "external_reference": "WEB-2026-0714-A17",
    "currency": "EUR",
    "customer": {
        "company": "Northstar Office GmbH",
        "first_name": "Anna",
        "last_name": "Keller",
        "billing_address": {
            "street": "Hauptstrasse 12",
            "zip": "10115",
            "city": "Berlin",
            "country": "Germany",
        },
        "delivery_address": {
            "street": "Hauptstrasse 12",
            "zip": "10115",
            "city": "Berlin",
            "country": "Germany",
        },
    },
    "payment": {
        "payment_method": "Bank Transfer",
        "payment_status": "PAID",
        "payment_date": "2026-07-14",
    },
    "items": [
        {
            "sku": "CHR-ERG-01",
            "description": "Ergonomic Chair",
            "quantity": 2,
            "unit_net_price": 120.5,
            "vat_percentage": 19,
            "discount_percentage": 0,
            "source_total": 241.0,
        }
    ],
    "totals": {"net_total": 570, "vat_total": 108.3, "gross_total": 678.3},
}


def test_parse_llm_json_with_markdown_fence():
    raw = "```json\n" + json.dumps(SAMPLE_PAYLOAD) + "\n```"
    parsed = _parse_llm_json(raw)
    assert parsed["external_reference"] == "WEB-2026-0714-A17"


@patch("app.extraction.groq_extractor.Groq")
def test_extract_order_data_success(mock_groq):
    mock_client = MagicMock()
    mock_groq.return_value = mock_client
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content=json.dumps(SAMPLE_PAYLOAD)))
    ]
    mock_client.chat.completions.create.return_value = mock_response

    extractor = GroqOrderExtractor(
        settings=MagicMock(
            groq_api_key="test",
            groq_model="test-model",
            groq_max_retries=1,
        )
    )
    order = extractor.extract_order_data("ocr text")
    assert isinstance(order, OrderData)
    assert order.external_reference == "WEB-2026-0714-A17"
    assert order.items[0].sku == "CHR-ERG-01"
