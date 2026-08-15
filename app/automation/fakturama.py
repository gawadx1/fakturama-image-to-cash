"""Fakturama application automation facade."""

from __future__ import annotations

import logging
from pathlib import Path

from pywinauto.application import Application
from pywinauto.base_wrapper import BaseWrapper

from app.automation.debtor import DebtorAutomation
from app.automation.invoices import InvoiceAutomation
from app.automation.orders import OrderAutomation
from app.automation.payment_methods import PaymentMethodAutomation
from app.automation.products import ProductAutomation
from app.automation.ui_helpers import UIHelpers
from app.automation.vat import VatAutomation
from app.config import Settings
from app.models.order import OrderData, PaymentStatus

logger = logging.getLogger("fakturama_automation")


class FakturamaAutomation:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.ui = UIHelpers(timeout=settings.ui_timeout)
        self.app: Application | None = None
        self.main_window: BaseWrapper | None = None
        self.screenshots_dir = settings.screenshots_dir
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

        self.orders = OrderAutomation(self)
        self.debtors = DebtorAutomation(self)
        self.payment_methods = PaymentMethodAutomation(self)
        self.vat = VatAutomation(self)
        self.products = ProductAutomation(self)
        self.invoices = InvoiceAutomation(self)

    @property
    def window(self) -> BaseWrapper:
        if self.main_window is None:
            raise RuntimeError("Fakturama is not connected")
        return self.main_window

    def connect(self) -> None:
        logger.info("Opening Fakturama")
        self.app, self.main_window = self.ui.connect_or_launch(self.settings.fakturama_path)
        self._screenshot("02_new_order.png")

    def _screenshot(self, filename: str) -> None:
        path = self.screenshots_dir / filename
        self.ui.capture_screenshot(self.window, str(path))

    def inspect_ui(self, max_depth: int = 4) -> str:
        self.connect()
        return self.ui.dump_tree(self.window, max_depth=max_depth)

    def process_order(self, order: OrderData) -> dict[str, str]:
        self.connect()
        logger.info("Creating New Order")
        order_editor = self.orders.open_new_order(order)
        self._screenshot("02_new_order.png")

        logger.info("Resolving Debtor: %s", order.customer_display_name)
        self.debtors.resolve_or_create(order, order_editor)
        self._screenshot("03_debtor.png")

        payment_method = self.payment_methods.ensure_available(order.payment.payment_method)
        self.debtors.set_payment_method_on_order(order_editor, payment_method)

        for item in order.items:
            logger.info("Resolving Product: %s", item.sku)
            self.vat.ensure_vat(item.vat_percentage)
            self.products.resolve_or_create(item, order_editor)

        self._screenshot("04_products.png")
        self.orders.complete_order(order, order_editor)

        logger.info("Saving Order")
        order_number = self.orders.save_order(order_editor)
        self._screenshot("05_saved_order.png")

        logger.info("Order verified")
        self.orders.verify_saved_order(order, order_number)

        logger.info("Creating linked Invoice")
        invoice_editor = self.invoices.create_from_order(order_editor)
        self._screenshot("06_invoice.png")

        self.invoices.complete_invoice(order, invoice_editor, payment_method)
        logger.info("Applying %s status", order.payment.payment_status.value)
        self.invoices.apply_payment_status(order, invoice_editor)

        logger.info("Saving Invoice")
        invoice_number = self.invoices.save_invoice(invoice_editor)
        self.invoices.verify_saved_invoice(order, invoice_number, order_number)
        self._screenshot("07_final_verification.png")

        return {
            "order_number": order_number,
            "invoice_number": invoice_number,
            "payment_status": order.payment.payment_status.value,
            "total": str(order.totals.gross_total or ""),
            "currency": order.currency or "EUR",
        }
