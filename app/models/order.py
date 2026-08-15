"""Pydantic models for structured order extraction."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator


class PaymentStatus(str, Enum):
  PAID = "PAID"
  UNPAID = "UNPAID"
  PARTIAL = "PARTIAL"
  UNKNOWN = "UNKNOWN"


class AddressData(BaseModel):
  street: str | None = None
  zip: str | None = None
  city: str | None = None
  country: str | None = None


class CustomerData(BaseModel):
  company: str | None = None
  first_name: str | None = None
  last_name: str | None = None
  alias: str | None = None
  email: str | None = None
  telephone: str | None = None
  billing_address: AddressData = Field(default_factory=AddressData)
  delivery_address: AddressData = Field(default_factory=AddressData)


class PaymentData(BaseModel):
  payment_method: str | None = None
  payment_status: PaymentStatus = PaymentStatus.UNKNOWN
  payment_date: date | None = None


class OrderItem(BaseModel):
  sku: str
  description: str | None = None
  quantity: Decimal
  unit_net_price: Decimal
  vat_percentage: Decimal
  discount_percentage: Decimal = Decimal("0")
  source_total: Decimal | None = None

  @field_validator("quantity", "unit_net_price", "vat_percentage", mode="before")
  @classmethod
  def coerce_decimal(cls, value: object) -> Decimal:
    if value is None:
      raise ValueError("numeric field cannot be null")
    return Decimal(str(value))

  @field_validator("discount_percentage", mode="before")
  @classmethod
  def coerce_discount(cls, value: object) -> Decimal:
    if value is None:
      return Decimal("0")
    return Decimal(str(value))


class OrderTotals(BaseModel):
  net_total: Decimal | None = None
  vat_total: Decimal | None = None
  gross_total: Decimal | None = None

  @field_validator("net_total", "vat_total", "gross_total", mode="before")
  @classmethod
  def coerce_optional_decimal(cls, value: object) -> Decimal | None:
    if value is None or value == "":
      return None
    return Decimal(str(value))


class OrderData(BaseModel):
  order_date: date | None = None
  external_reference: str | None = None
  currency: str | None = None
  customer: CustomerData = Field(default_factory=CustomerData)
  payment: PaymentData = Field(default_factory=PaymentData)
  items: list[OrderItem] = Field(default_factory=list)
  totals: OrderTotals = Field(default_factory=OrderTotals)
  order_level_discount_percentage: Decimal | None = None
  shipping_cost: Decimal | None = None

  @field_validator("order_date", mode="before")
  @classmethod
  def parse_date(cls, value: object) -> date | None:
    if value is None or value == "":
      return None
    if isinstance(value, date):
      return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y"):
      try:
        from datetime import datetime

        return datetime.strptime(text, fmt).date()
      except ValueError:
        continue
    raise ValueError(f"unsupported date format: {value}")

  @field_validator("payment", mode="before")
  @classmethod
  def normalize_payment_status(cls, value: object) -> object:
    if isinstance(value, dict) and value.get("payment_status") is not None:
      status = str(value["payment_status"]).strip().upper()
      if status in {"PAID", "PAYED", "SETTLED"}:
        value["payment_status"] = PaymentStatus.PAID
      elif status in {"UNPAID", "OPEN", "OUTSTANDING"}:
        value["payment_status"] = PaymentStatus.UNPAID
      elif status in {"PARTIAL", "PARTIALLY_PAID"}:
        value["payment_status"] = PaymentStatus.PARTIAL
      else:
        value["payment_status"] = PaymentStatus.UNKNOWN
    return value

  @model_validator(mode="after")
  def validate_minimum_fields(self) -> Self:
    if not self.items:
      raise ValueError("order must contain at least one item")
    if not any(
      [
        self.customer.company,
        self.customer.first_name,
        self.customer.last_name,
      ]
    ):
      raise ValueError("customer must include company or first/last name")
    return self

  @property
  def customer_display_name(self) -> str:
    if self.customer.company:
      return self.customer.company
    parts = [self.customer.first_name or "", self.customer.last_name or ""]
    return " ".join(part for part in parts if part).strip()
