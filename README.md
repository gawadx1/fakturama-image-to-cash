# Fakturama Image-to-Cash Automation

Windows Python application that reads a sales-order image, extracts structured data with **Tesseract OCR** and **Groq LLM**, then automates **Fakturama** through **pywinauto / Microsoft UI Automation** to create and verify an Order, linked Invoice, and payment status.

## Overview

```text
Image
  → Tesseract OCR
  → Groq structured extraction
  → Pydantic validation
  → pywinauto (UIA)
  → Fakturama desktop UI
  → Verification
```

The automation follows an **order-first** flow:

1. Open **New Order**
2. Resolve/create Debtor, Payment Method, VAT, Products while the order stays open
3. Complete and save the Order
4. Create a **linked Invoice** from the saved Order
5. Apply payment status and verify both documents

Ambiguous master data, conflicting search results, or total mismatches stop safely with `MANUAL REVIEW REQUIRED`.

## Requirements

- Windows 10/11
- Python 3.11+ (tested with 3.14)
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract)
- [Fakturama 2](https://www.fakturama.info/)
- Groq API key

## Tesseract Installation

1. Download the Windows installer from the [UB Mannheim builds](https://github.com/UB-Mannheim/tesseract/wiki).
2. Install Tesseract and note the install path, e.g. `C:\Program Files\Tesseract-OCR\tesseract.exe`.
3. Either add Tesseract to `PATH`, or set in `.env`:

```env
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

## Fakturama Installation

1. Install Fakturama 2.
2. Default path on this machine: `C:\Program Files\Fakturama2\Fakturama.exe`
3. Override if needed:

```env
FAKTURAMA_PATH=C:\Program Files\Fakturama2\Fakturama.exe
```

## Python Setup

```bash
cd fakturama-image-to-cash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Configure `.env`:

```env
GROQ_API_KEY=your_key_here
GROQ_MODEL=llama-3.3-70b-versatile
FAKTURAMA_PATH=C:\Program Files\Fakturama2\Fakturama.exe
OCR_LANG=eng
UI_TIMEOUT=15
TESSERACT_CMD=
```

## Running

```bash
python run.py --image input/order.png
```

Extraction only (no Fakturama):

```bash
python run.py --image input/order.png --extract-only
```

Optional Fakturama path override:

```bash
python run.py --image input/order.png --fakturama-path "C:\Program Files\Fakturama2\Fakturama.exe"
```

## UI Inspection

Fakturama is an Eclipse RCP application; UIA trees can vary by version. Use the inspection utility to discover stable selectors:

```bash
python run.py --inspect-ui
```

or:

```bash
python tools/inspect_fakturama.py --depth 5
```

This prints control type, title, automation id, class name, enabled, and visible flags.

## Project Structure

| Module | Responsibility |
|--------|----------------|
| `app/extraction/ocr.py` | Image preprocessing + Tesseract OCR |
| `app/extraction/groq_extractor.py` | Groq JSON extraction with retry/repair |
| `app/models/order.py` | Pydantic models |
| `app/automation/ui_helpers.py` | Reusable UIA helpers |
| `app/automation/fakturama.py` | End-to-end orchestration |
| `app/automation/orders.py` | Order editor automation |
| `app/automation/debtor.py` | Debtor resolution/creation |
| `app/automation/products.py` | Product resolution/creation |
| `app/automation/vat.py` | VAT resolution/creation |
| `app/automation/payment_methods.py` | Payment method resolution |
| `app/automation/invoices.py` | Linked invoice + payment status |
| `app/verification/validators.py` | Decimal calculations + exact matching |
| `app/exceptions.py` | `ManualReviewRequired` safety stops |

## Error Handling

The system raises `ManualReviewRequired` when:

- multiple exact matches exist
- totals are inconsistent
- required controls are missing
- newly created master data cannot be re-selected
- payment method is unavailable

Example output:

```text
========================================
MANUAL REVIEW REQUIRED
========================================

Stage: Product Resolution
Reason: Multiple conflicting products found for SKU CHR-ERG-01

Automation stopped safely.
========================================
```

## Screenshots

Milestone screenshots are written to `screenshots/` when automation runs:

- `02_new_order.png`
- `03_debtor.png`
- `04_products.png`
- `05_saved_order.png`
- `06_invoice.png`
- `07_final_verification.png`

## Testing

Unit tests do not require Fakturama or Groq credentials:

```bash
pytest
```

## Limitations

- Fakturama UIA selectors are version-dependent; use `--inspect-ui` to adapt selectors for your installation.
- OCR quality depends on image quality and Tesseract language packs.
- The automation assumes English/German Fakturama menu labels such as `Order`, `Data`, `Documents`, `New order`.
- Document list verification relies on visible table text and may need tuning per Fakturama theme/version.
- No coordinate-based clicking is used; however, label-to-edit proximity heuristics are used when `automation_id` is unavailable.

## Demo Workflow

1. Place an order image in `input/order.png`
2. Configure `.env`
3. Launch Fakturama manually or let the app start it
4. Run `python run.py --image input/order.png`
5. Review console logs, extraction summary, screenshots, and final verification output

## If I Had 3 More Hours

1. **Stronger OCR** – Add deskewing, language detection, and OCR confidence scoring to improve extraction reliability and automatically select the best OCR result.

2. **Selector hardening** – Capture and validate UIA trees across multiple Fakturama environments, then centralize selectors with fallbacks to improve compatibility and resilience to UI variations.

3. **Recovery flows** – Add retries for transient UI failures, restore focus to the open Order after master-data dialogs, and introduce checkpoints so interrupted runs can resume safely.

4. **Better verification** – Reopen saved Orders and Invoices and read their persisted field values directly, rather than relying primarily on document-list rows.

5. **Integration tests** – Add recorded end-to-end UI smoke tests behind a `FAKTURAMA_INTEGRATION=1` flag to validate the real Fakturama workflow without affecting normal unit-test execution.

6. **Reporting** – Add an HTML execution report containing OCR output, extracted structured data, screenshots, stage timings, and verification results for easier debugging and auditability.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
