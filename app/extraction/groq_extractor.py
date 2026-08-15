"""Groq LLM structured extraction service."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from groq import Groq
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.models.order import OrderData

logger = logging.getLogger("fakturama_automation")

EXTRACTION_SYSTEM_PROMPT = """You are a data extraction engine for sales orders.
Extract ONLY information explicitly present in the OCR text.
Do NOT invent, infer, or hallucinate missing values.
Use null for unavailable fields.
Normalize dates to YYYY-MM-DD.
Normalize numbers to plain decimals without currency symbols.
Preserve exact SKU values and exact company/customer names.
Extract every line item.
Return JSON only, no markdown fences, no commentary.
Do not calculate totals unless they appear in the source text.
Preserve source totals exactly when present.
"""

ORDER_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "order_date": {"type": ["string", "null"]},
        "external_reference": {"type": ["string", "null"]},
        "currency": {"type": ["string", "null"]},
        "customer": {
            "type": "object",
            "properties": {
                "company": {"type": ["string", "null"]},
                "first_name": {"type": ["string", "null"]},
                "last_name": {"type": ["string", "null"]},
                "alias": {"type": ["string", "null"]},
                "email": {"type": ["string", "null"]},
                "telephone": {"type": ["string", "null"]},
                "billing_address": {
                    "type": "object",
                    "properties": {
                        "street": {"type": ["string", "null"]},
                        "zip": {"type": ["string", "null"]},
                        "city": {"type": ["string", "null"]},
                        "country": {"type": ["string", "null"]},
                    },
                },
                "delivery_address": {
                    "type": "object",
                    "properties": {
                        "street": {"type": ["string", "null"]},
                        "zip": {"type": ["string", "null"]},
                        "city": {"type": ["string", "null"]},
                        "country": {"type": ["string", "null"]},
                    },
                },
            },
        },
        "payment": {
            "type": "object",
            "properties": {
                "payment_method": {"type": ["string", "null"]},
                "payment_status": {"type": ["string", "null"]},
                "payment_date": {"type": ["string", "null"]},
            },
        },
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string"},
                    "description": {"type": ["string", "null"]},
                    "quantity": {"type": ["number", "string"]},
                    "unit_net_price": {"type": ["number", "string"]},
                    "vat_percentage": {"type": ["number", "string"]},
                    "discount_percentage": {"type": ["number", "string", "null"]},
                    "source_total": {"type": ["number", "string", "null"]},
                },
                "required": ["sku", "quantity", "unit_net_price", "vat_percentage"],
            },
        },
        "totals": {
            "type": "object",
            "properties": {
                "net_total": {"type": ["number", "string", "null"]},
                "vat_total": {"type": ["number", "string", "null"]},
                "gross_total": {"type": ["number", "string", "null"]},
            },
        },
    },
    "required": ["items"],
}


def _extract_json_block(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in LLM response")
    return text[start : end + 1]


def _repair_json(text: str) -> str:
    repaired = _extract_json_block(text)
    repaired = repaired.replace("\u201c", '"').replace("\u201d", '"')
    repaired = repaired.replace("'", '"')
    repaired = re.sub(r",\s*}", "}", repaired)
    repaired = re.sub(r",\s*]", "]", repaired)
    return repaired


def _parse_llm_json(raw: str) -> dict[str, Any]:
    try:
        return json.loads(_extract_json_block(raw))
    except (json.JSONDecodeError, ValueError):
        return json.loads(_repair_json(raw))


class GroqOrderExtractor:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = Groq(api_key=self.settings.groq_api_key)

    def _build_user_prompt(self, ocr_text: str) -> str:
        return (
            "Extract structured order data from the OCR text below.\n"
            "Rules:\n"
            "- Extract only values present in OCR text\n"
            "- Use null for missing values\n"
            "- Return JSON only matching the provided schema\n"
            "- Preserve exact SKUs and customer/company names\n"
            "- Include every item line\n\n"
            f"JSON schema:\n{json.dumps(ORDER_JSON_SCHEMA, indent=2)}\n\n"
            f"OCR text:\n{ocr_text}"
        )

    def extract_order_data(self, ocr_text: str) -> OrderData:
        last_error: Exception | None = None
        for attempt in range(1, self.settings.groq_max_retries + 1):
            try:
                logger.info(
                    "Requesting structured extraction from Groq (attempt %s)",
                    attempt,
                )
                response = self.client.chat.completions.create(
                    model=self.settings.groq_model,
                    temperature=0,
                    messages=[
                        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                        {"role": "user", "content": self._build_user_prompt(ocr_text)},
                    ],
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content or ""
                payload = _parse_llm_json(content)
                order = OrderData.model_validate(payload)
                logger.info(
                    "Extracted order %s with %s item(s)",
                    order.external_reference or "(no reference)",
                    len(order.items),
                )
                return order
            except (ValidationError, json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                logger.warning("LLM output validation failed on attempt %s: %s", attempt, exc)
        raise ValueError(f"Failed to extract valid order data after retries: {last_error}")


def extract_order_data(ocr_text: str, settings: Settings | None = None) -> OrderData:
    return GroqOrderExtractor(settings=settings).extract_order_data(ocr_text)
