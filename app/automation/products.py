"""Product resolution and creation."""

from __future__ import annotations

import logging

from pywinauto.base_wrapper import BaseWrapper

from app.exceptions import ManualReviewRequired
from app.models.order import OrderItem
from app.verification.validators import calculate_gross_unit_price, normalize_text, vat_name

logger = logging.getLogger("fakturama_automation")


class ProductAutomation:
    def __init__(self, fakturama) -> None:
        self.f = fakturama
        self.ui = fakturama.ui

    def resolve_or_create(self, item: OrderItem, order_editor: BaseWrapper) -> None:
        if self._select_existing(item.sku, order_editor):
            return

        logger.info("Product not found")
        logger.info("Creating Product: %s", item.sku)
        self._create_product(item)
        if not self._select_existing(item.sku, order_editor):
            raise ManualReviewRequired(
                reason=f"Newly created product {item.sku!r} could not be selected",
                stage="Product Resolution",
            )
        logger.info("Product created")

    def select_product_on_order(self, order_editor: BaseWrapper, sku: str) -> None:
        if not self._select_existing(sku, order_editor):
            raise ManualReviewRequired(
                reason=f"Product {sku!r} not available on order",
                stage="Order Completion",
            )

    def _select_existing(self, sku: str, order_editor: BaseWrapper) -> bool:
        self._open_product_selector(order_editor)
        dialog = self.ui.wait_for_window(".*Product.*|.*Item.*", timeout=self.ui.timeout)

        def sku_match(row: list[str]) -> bool:
            return any(normalize_text(sku) == normalize_text(cell) for cell in row)

        try:
            self.ui.search_and_select_single_row(
                dialog,
                search_text=sku,
                stage="Product Resolution",
                match_fn=sku_match,
            )
            return True
        except ManualReviewRequired:
            raise
        except Exception:
            self.ui.click_button(dialog, title_re="Cancel|Close")
            return False

    def _open_product_selector(self, order_editor: BaseWrapper) -> None:
        for label in ("Product", "Item", "Article"):
            try:
                self.ui.click_button(order_editor, title_re=label)
                return
            except Exception:  # noqa: BLE001
                continue
        selector = self.ui.require_control(
            order_editor,
            stage="Product Resolution",
            title_re=".*Product.*|.*Item.*",
            control_type="Button",
        )
        self.ui.click_control(selector)

    def _create_product(self, item: OrderItem) -> None:
        window = self.f.window
        try:
            self.ui.click_menu_path(window, ["Data", "Products", "New product"])
        except Exception:
            self.ui.click_menu_path(window, ["Data", "Products"])
            self.ui.click_button(window, title_re="New product|New Product")

        editor = self.ui.wait_for_window(".*Product.*", timeout=self.ui.timeout)
        gross_price = calculate_gross_unit_price(item.unit_net_price, item.vat_percentage)
        description = item.description or item.sku

        self._set_field(editor, "Item Number", item.sku)
        self._set_field(editor, "Name", description)
        self._set_field(editor, "Description", description)
        self._set_field(editor, "Price", str(gross_price))
        self._set_field(editor, "Cost price", "0.00")
        self._set_combo(editor, "VAT", vat_name(item.vat_percentage))
        self._set_field(editor, "Stock", "0.00")

        self.ui.click_button(editor, title_re="^Save$")
        self.ui.wait_until(lambda: not editor.is_visible(), timeout=self.ui.timeout)

    def _set_field(self, editor: BaseWrapper, label: str, value: str) -> None:
        control = self.ui.find_edit_near_label(editor, label)
        self.ui.set_text(control, value)

    def _set_combo(self, editor: BaseWrapper, label: str, value: str) -> None:
        combos = [c.wrapper_object() for c in editor.descendants(control_type="ComboBox")]
        for combo in combos:
            parent_text = " ".join(
                self.ui.get_text(t.wrapper_object())
                for t in combo.parent().descendants(control_type="Text")
            )
            if label.lower() in parent_text.lower():
                self.ui.select_combo(combo, value)
                return
