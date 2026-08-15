# Fakturama Image-to-Cash Automation — Design Document

**Part 1: Design**  
**Author:** Abdullah Abdel-Gawad  
**Date:** August 2026

---

## 1. Overview and Objective

The goal of this system is to automate the end-to-end processing of a single sales-order image into verified financial records inside the Fakturama desktop application. The order image is the **only** input. No manual data entry should be required for the happy path.

The system must execute a continuous, **order-first** workflow:

```text
Order Image
  → Extract structured data
  → Use Fakturama UI
  → Resolve/Create Debtor
  → Resolve/Create Products
  → Resolve/Create VAT
  → Resolve/Create Payment Method (when needed)
  → Build Order
  → Save and verify Order
  → Create linked Invoice
  → Apply extracted payment status
  → Save and verify Invoice
```

A **New Order** is opened first and remains open while missing master data (Debtor, Payment Method, VAT, Products) is resolved or created. This preserves context, avoids duplicate records, and mirrors how a human operator would work in Fakturama.

The automation must **not** rely on hardcoded screen coordinates or a fixed UI layout. All desktop interaction is grounded in Microsoft UI Automation (UIA) through semantic control discovery. When data or UI state is ambiguous, the system stops safely for manual review rather than guessing.

---

## 2. High-Level Architecture

The system is organized as a linear pipeline with a clear separation between **data extraction**, **validation**, **UI automation**, and **verification**.

```text
                 Order Image
                      │
                      ▼
             Image Preprocessing
                      │
                      ▼
                Tesseract OCR
                      │
                      ▼
                 OCR Text
                      │
                      ▼
                 Groq LLM
                      │
                      ▼
          Structured OrderData
                      │
                      ▼
             Pydantic Validation
                      │
                      ▼
        Microsoft UI Automation
             via pywinauto/UIA
                      │
                      ▼
                  Fakturama
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
   Master Data             Order / Invoice
 Resolution & Creation        Processing
          │                       │
          └───────────┬───────────┘
                      ▼
                Verification
```

| Component | Responsibility |
|-----------|----------------|
| **Image preprocessing + Tesseract** | Convert the input image into machine-readable text locally. |
| **Groq LLM** | Normalize OCR text into structured order fields. Does not control the UI. |
| **Pydantic validation** | Enforce schema, reject malformed output, ensure missing fields stay null. |
| **pywinauto / UIA** | Discover and interact with Fakturama controls without fixed coordinates. |
| **Fakturama** | Target desktop ERP for master data, orders, and invoices. |
| **Verification** | Confirm persisted records after each critical mutation. |

The guiding principle is: **Extract → Validate → Ground → Act → Verify**.

---

## 3. Image Extraction Strategy

### Tesseract OCR

Tesseract performs **local** optical character recognition. Before OCR, the image may be preprocessed (grayscale, upscale, contrast enhancement, thresholding, denoising) to improve accuracy on photographed or scanned orders. Multiple preprocessing variants and Tesseract page-segmentation modes can be evaluated; the best-scoring result becomes the intermediate **OCR text**.

The OCR text is preserved as the canonical intermediate representation. The LLM receives text, not the raw image, which keeps the pipeline debuggable and avoids coupling extraction to a vision API.

### Groq LLM

Groq receives the OCR text and returns a JSON document matching a predefined order schema. The LLM is instructed to:

- Extract **only** information present in the OCR text
- Normalize dates and numeric values
- Preserve exact SKUs and customer/company names
- Use `null` for unavailable fields
- **Not invent** missing values

**Fields to extract** include: Order Date, External Reference, currency (if present), debtor/customer details (company, first/last name, alias, email, telephone), billing and delivery addresses, Payment Method, Payment Status, Payment Date, and for each line item — SKU, Description, Quantity, Unit Net Price, VAT percentage, Discount, and source line totals, plus order-level Net/VAT/Gross totals.

### Pydantic validation

Structured output is validated against Pydantic models before any UI automation begins. This layer:

- Rejects malformed or incomplete JSON
- Coerces types safely (e.g., dates, decimals)
- Blocks hallucinated or unsafe data from reaching Fakturama
- Supports retry/repair on invalid LLM responses

---

## 4. Fakturama UI Automation / Grounding Strategy

Automation uses **pywinauto** with the **Microsoft UI Automation (UIA)** backend:

```text
pywinauto + backend="uia"
```

### Why UIA over coordinates

| Approach | Problem |
|----------|---------|
| `click(x, y)` / fixed coordinates | Breaks across resolutions, DPI scaling, window position, and UI layout changes. |
| **UIA grounding** | Interacts with controls by semantic properties; more resilient and maintainable. |

### Preferred control discovery

Controls are located using stable UIA properties:

- Control type (Button, Edit, ComboBox, Table, etc.)
- Visible name / title
- Automation ID
- Class name
- Parent/child hierarchy

Reusable helper functions encapsulate: finding controls, condition-based waits, clicking buttons, entering text, selecting combo boxes, reading values, handling dialogs, and dumping the UI tree for debugging.

Waits are **condition-based** (control exists, visible, enabled, dialog appeared) — not arbitrary `sleep()` calls.

### Fakturama-specific consideration

Fakturama is built on Eclipse/SWT. UIA trees can be deep, inconsistently labeled, or version-dependent. A UI inspection utility (`--inspect-ui`) is used to discover actual control properties on the installed version and tune selectors accordingly. Label-proximity heuristics (finding an Edit near a Text label) may supplement automation IDs when necessary, but coordinate clicking is avoided.

---

## 5. Order-First Workflow

### Step 1 — Open New Order

Navigate to **Order → New Order**. Leave the auto-generated Order No. unchanged. Set:

- **Date** = extracted Order Date
- **Cust.Ref.** = extracted External Reference
- **Price mode** = Net
- **VAT mode** = With VAT

The Order editor remains open for all subsequent master-data resolution.

### Step 2 — Resolve Debtor

Use the Order's contact selector. Search by company/customer name. An **exact match** requires agreement on visible fields: Company, First Name, Last Name, ZIP, and City.

```text
Exact match         → Select → OK → Verify addresses
No exact match      → Create Debtor → Save → Return to Order → Search → Select
Ambiguous/conflict  → Manual Review
```

Debtor creation sets company/name, main address (street, ZIP, city, country, email, telephone), assigns Invoice address (and Delivery address if identical to billing), alias, discount 0%, Net pricing, and the extracted Payment Method.

### Step 3 — Resolve Payment Method

Search for an exact Payment Method name. If missing, create via **Data → Terms of payment** using the assignment mapping (e.g., Bank Transfer → Credit transfer). If multiple conflicting rows exist, stop for manual review. Return to the open Order/Debtor flow after creation.

### Step 4 — Resolve VAT

For each product's VAT rate, search **Data → VATs** for `VAT {percentage}%` with matching value and standard VAT code (`S`). Create if missing. Conflicting configurations trigger manual review.

### Step 5 — Resolve Products

For every extracted item, in source order:

```text
Search exact SKU
      │
      ├── Found (exactly one) → Select
      ├── Not found → Ensure VAT exists → Create Product → Save → Return to Order → Search again
      └── Ambiguous/conflicting → Manual Review
```

Product master price uses gross price derived from unit net price and VAT. Transaction-line discounts are **not** baked into the product master price.

---

## 6. Order Completion and Validation

After master data is resolved, each order line is completed with extracted Quantity, Unit Net Price, VAT, and Discount. Financial calculations use **`Decimal` arithmetic**, not floating point, for deterministic monetary results.

Before saving, the automation verifies:

| Category | Checks |
|----------|--------|
| Header | Debtor, invoice address, delivery address |
| Line items | Product, quantity, unit price, VAT, discount, line total |
| Totals | Net total, VAT total, gross total against extracted source values |
| Defaults | Order-level discount 0%, shipping free/0.00 unless source specifies otherwise |

Material total mismatches trigger manual review. The system does not silently overwrite source data.

---

## 7. Save and Verify Order

The Order is saved **once**. Verification opens **Data → Documents** and confirms a row exists with the expected generated Order number, Date, Cust.Ref., open state, and Total.

Verification matters because UI actions can appear successful (dialog closes, no error shown) while data was not actually persisted or was saved with incorrect values.

---

## 8. Linked Invoice

The Invoice is created from the saved Order via **Create a follow-up document → Invoice** — not from a standalone top-level Invoice action. This preserves the Order → Invoice document relationship.

After the Invoice editor opens, verify copied fields: Cust.Ref., invoice/delivery addresses, Order Date, VAT mode, item lines, and totals. Confirm the Payment Method matches the extracted value.

---

## 9. Payment Status

| Extracted status | Action |
|------------------|--------|
| **PAID** | Check Paid, set Payment Date from extraction, set Value to full Invoice total |
| **Not PAID** | Leave Paid unchecked; do not invent payment date or amount |

---

## 10. Verification and Safety

**Never assume a UI operation succeeded. Verify it.**

Verification occurs after: Debtor creation/selection, Product creation/selection, VAT/Payment Method creation, Order save, Invoice save, and final document checks.

Safe stopping examples:

| Condition | Action |
|-----------|--------|
| Ambiguous Debtor or Product | Manual Review |
| Unexpected VAT configuration | Manual Review |
| Required UI control not found | Stop safely with diagnostic |
| Order totals mismatch source | Stop safely |
| Invoice payment method unavailable | Manual Review |

The automation **never** randomly selects from multiple matching records.

---

## 11. Error Handling and Recovery

| Failure type | Handling |
|--------------|----------|
| OCR errors / poor image quality | Log OCR text; extraction may fail validation → manual review |
| Malformed LLM output | JSON repair + retry; validation rejection before UI |
| Missing required extracted fields | Stop before Fakturama launch |
| UI control timeout | Diagnostic log with stage, expected control, visible windows |
| Unexpected dialogs | Detect modal; stop rather than dismiss blindly |
| Ambiguous master data | `ManualReviewRequired` with reason, stage, suggested action |
| Failed record re-selection | Stop — newly created record must be findable again |
| Verification failure | Stop with document-level diagnostic |
| Fakturama version/UI differences | UI inspection tool; selector tuning per version |

All failures produce structured, actionable logs. Secrets (API keys) are never logged. The system prioritizes **correctness over completion** for financial data.

---

## 12. Trade-offs

### Tesseract vs. vision LLM

| | Tesseract | Vision LLM |
|---|-----------|--------------|
| **Pros** | Local, deterministic text output, debuggable, no image API cost | Can read layout visually |
| **Cons** | OCR errors on poor images; layout ambiguity | Non-deterministic, harder to audit, API dependency |

**Choice:** Tesseract provides a inspectable intermediate representation. A vision LLM could be added later for low-confidence OCR fallback.

### Groq LLM

| **Pros** | Strong normalization of messy OCR; easy structured extraction |
| **Cons** | External API dependency; risk of malformed or hallucinated output |

**Mitigation:** Strict JSON schema, Pydantic validation, null-for-missing policy, retries, and explicit separation — the LLM never controls the UI.

### UIA vs. coordinates

| **Pros (UIA)** | Semantic, resolution-independent, maintainable |
| **Cons (UIA)** | SWT/Eclipse trees can be inconsistent; selectors need per-version tuning |

**Choice:** UIA with inspection tooling. Coordinates are fragile and unacceptable for a maintainable solution.

### Full automation vs. manual review

Completing every run at any cost is unsafe for invoice automation. The system intentionally stops on ambiguity. Correct persisted financial records matter more than a 100% automation rate.

---

## 13. Assumptions and Limitations

- OCR quality depends on image resolution, lighting, and skew.
- Groq extraction quality depends on OCR quality; garbage in produces unreliable structure.
- Fakturama UIA exposure may differ by version, language, and operating environment.
- UI selectors may require tuning via the inspection utility for the installed Fakturama build.
- Ambiguous source documents (duplicate SKUs, partial addresses) will require manual review.
- The assignment timebox limits exhaustive cross-version compatibility testing.
- Fakturama requires a working desktop environment (Java/runtime, display session); headless CI cannot fully validate UI automation.

Universal Fakturama compatibility is **not** claimed.

---

## 14. Why This Design

This architecture is appropriate for the assignment because it cleanly separates concerns:

```text
Extract → Validate → Ground → Act → Verify
```

- **Tesseract** produces auditable local text.
- **Groq** understands and normalizes that text into structure.
- **Pydantic** enforces safety before any desktop interaction.
- **pywinauto/UIA** controls Fakturama semantically without coordinate fragility.
- **Verification** protects against silently incorrect financial records.
- **Manual review** handles ambiguity without dangerous guesses.

The result is a system that is explainable, maintainable, and safe for financial document automation — aligned with the assignment's emphasis on reliability, exact matching, order-first flow, and verifiable outcomes.

---

## If I Had 3 More Hours

1. **Stronger OCR** – Add deskewing, language detection, and OCR confidence scoring to improve extraction reliability and automatically select the best OCR result.

2. **Selector hardening** – Capture and validate UIA trees across multiple Fakturama environments, then centralize selectors with fallbacks to improve compatibility and resilience to UI variations.

3. **Recovery flows** – Add retries for transient UI failures, restore focus to the open Order after master-data dialogs, and introduce checkpoints so interrupted runs can resume safely.

4. **Better verification** – Reopen saved Orders and Invoices and read their persisted field values directly, rather than relying primarily on document-list rows.

5. **Integration tests** – Add recorded end-to-end UI smoke tests behind a `FAKTURAMA_INTEGRATION=1` flag to validate the real Fakturama workflow without affecting normal unit-test execution.

6. **Reporting** – Add an HTML execution report containing OCR output, extracted structured data, screenshots, stage timings, and verification results for easier debugging and auditability.
