"""Debtor resolution and creation automation."""

from __future__ import annotations

import logging

from pywinauto.base_wrapper import BaseWrapper

from app.exceptions import ManualReviewRequired
from app.models.order import AddressData, OrderData
from app.verification.validators import exact_match, map_payment_method, normalize_text

logger = logging.getLogger("fakturama_automation")


class DebtorAutomation:
    def __init__(self, fakturama) -> None:
        self.f = fakturama
        self.ui = fakturama.ui

    def resolve_or_create(self, order: OrderData, order_editor: BaseWrapper) -> None:
        search_name = order.customer_display_name
        found = self._search_debtor(order_editor, order, search_name)
        if found:
            logger.info("Existing Debtor found")
            self._verify_addresses(order_editor, order)
            return

        logger.info("Creating new Debtor: %s", search_name)
        self._create_debtor(order)
        found = self._search_debtor(order_editor, order, search_name)
        if not found:
            raise ManualReviewRequired(
                reason=f"Newly created debtor {search_name!r} could not be selected",
                stage="Debtor Resolution",
            )
        self._verify_addresses(order_editor, order)

    def _search_debtor(self, order_editor: BaseWrapper, order: OrderData, search_name: str) -> bool:
        self._open_contact_selector(order_editor)
        dialog = self.ui.wait_for_window(".*Contact.*|.*Debtor.*|.*Customer.*", timeout=self.ui.timeout)

        def debtor_match(row: list[str]) -> bool:
            row_text = " ".join(row)
            company = order.customer.company or ""
            first = order.customer.first_name or ""
            last = order.customer.last_name or ""
            zip_code = order.customer.billing_address.zip or ""
            city = order.customer.billing_address.city or ""
            checks = [
                normalize_text(company) in normalize_text(row_text) if company else True,
                normalize_text(first) in normalize_text(row_text) if first else True,
                normalize_text(last) in normalize_text(row_text) if last else True,
                normalize_text(zip_code) in normalize_text(row_text) if zip_code else True,
                normalize_text(city) in normalize_text(row_text) if city else True,
            ]
            return all(checks)

        try:
            self.ui.search_and_select_single_row(
                dialog,
                search_text=search_name,
                stage="Debtor Resolution",
                match_fn=debtor_match,
            )
            return True
        except ManualReviewRequired:
            raise
        except Exception:
            self.ui.click_button(dialog, title_re="Cancel|Close")
            return False

    def _open_contact_selector(self, order_editor: BaseWrapper) -> None:
        for label in ("Contact", "Debtor", "Customer"):
            try:
                self.ui.click_button(order_editor, title_re=label)
                return
            except Exception:  # noqa: BLE001
                continue
        selector = self.ui.require_control(
            order_editor,
            stage="Debtor Resolution",
            title_re=".*Contact.*|.*Debtor.*",
            control_type="Button",
        )
        self.ui.click_control(selector)

    def _create_debtor(self, order: OrderData) -> None:
        window = self.f.window
        try:
            self.ui.click_menu_path(window, ["Data", "Contacts", "New contact"])
        except Exception:
            self.ui.click_menu_path(window, ["Data", "Contacts"])
            self.ui.click_button(window, title_re="New contact|New Contact")

        editor = self.ui.wait_for_window(".*Contact.*|.*Debtor.*", timeout=self.ui.timeout)
        customer = order.customer
        billing = customer.billing_address
        delivery = customer.delivery_address

        self._set_field(editor, "Company", customer.company or "")
        self._set_field(editor, "First name", customer.first_name or "")
        self._set_field(editor, "Last name", customer.last_name or "")
        self._set_field(editor, "Street", billing.street or "")
        self._set_field(editor, "ZIP", billing.zip or "")
        self._set_field(editor, "City", billing.city or "")
        self._set_field(editor, "Country", billing.country or "")
        self._set_field(editor, "E-Mail", customer.email or "")
        self._set_field(editor, "Telephone", customer.telephone or "")
        self._set_field(editor, "Alias", customer.alias or "")

        self._assign_address_role(editor, "Invoice address")
        if self._addresses_equal(billing, delivery):
            self._assign_address_role(editor, "Delivery address")

        payment_method = map_payment_method(order.payment.payment_method)
        self._set_combo(editor, "Payment", payment_method)
        self._set_field(editor, "Discount", "0")
        self._set_combo(editor, "Net/Gross", "Net")

        self.ui.click_button(editor, title_re="^Save$")
        self.ui.wait_until(lambda: not editor.is_visible(), timeout=self.ui.timeout)

    def _set_field(self, editor: BaseWrapper, label: str, value: str) -> None:
        if not value:
            return
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

    def _assign_address_role(self, editor: BaseWrapper, role: str) -> None:
        try:
            checkbox = self.ui.find_checkbox_near_label(editor, role)
            if not checkbox.get_toggle_state():
                self.ui.click_control(checkbox)
        except Exception:  # noqa: BLE001
            logger.debug("Could not assign address role %s via checkbox", role)

    def _addresses_equal(self, a: AddressData, b: AddressData) -> bool:
        return exact_match(
            (a.street, b.street),
            (a.zip, b.zip),
            (a.city, b.city),
            (a.country, b.country),
        )

    def _verify_addresses(self, order_editor: BaseWrapper, order: OrderData) -> None:
        billing = order.customer.billing_address
        delivery = order.customer.delivery_address
        editor_text = self.ui.get_text(order_editor)
        for field in (billing.street, billing.zip, billing.city):
            if field and normalize_text(field) not in normalize_text(editor_text):
                logger.warning("Billing address field not visible on order: %s", field)
        if not self._addresses_equal(billing, delivery):
            for field in (delivery.street, delivery.zip, delivery.city):
                if field and normalize_text(field) not in normalize_text(editor_text):
                    logger.warning("Delivery address field not visible on order: %s", field)

    def set_payment_method_on_order(self, order_editor: BaseWrapper, payment_method: str) -> None:
        try:
            self._set_combo(order_editor, "Payment", payment_method)
        except Exception as exc:  # noqa: BLE001
            raise ManualReviewRequired(
                reason=f"Payment method {payment_method!r} unavailable on order: {exc}",
                stage="Payment Method",
            ) from exc
