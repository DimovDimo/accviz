# Improvements research (v1.1)

This document has three parts: a review of the current project (v1.0.0), research on
candidate features, and the selection that goes into the plan.

## 1. Review of the current project

| # | Area | Finding | Severity |
|---|---|---|---|
| R1 | Security | `accviz dashboard` binds to `0.0.0.0` by default, so the dashboard (with the company's ledger) is reachable from the whole network and has no authentication. | High |
| R2 | Functionality | No **cash flow statement**, although cash is the most-watched figure. It was on the roadmap. | High |
| R3 | Functionality | **Accounts payable** is not analysed. Purchases are posted as one monthly lump, so there is no supplier-level aging and no AP sub-ledger reconciliation. | High |
| R4 | Functionality | No **audit analytics**. Journal-entry testing is the core of audit work, yet the journal has no `source` (manual vs system) and no anomaly checks exist. | Medium |
| R5 | Usability | No **Excel export**. Finance users work in spreadsheets and cannot take the statements out of the tool. | Medium |
| R6 | Functionality | No **forecast**. Historical statements have no outlook. | Medium |
| R7 | Functionality | The `department` column is captured but never analysed (no cost-centre view). | Low |
| R8 | Engineering | No CI workflow, no lint configuration, no coverage gate. The dashboard recomputes all analytics on every interaction (acceptable at this size). | Medium |
| R9 | Data model | An invoice has one `paid_date`, so partial payments cannot be dated. Aging is therefore approximate for partly paid invoices. | Low (deferred) |
| R10 | Scope | No VAT (Bulgarian 20 % rate) and no multi-currency. Both are large features that need their own rules and test data. | Low (deferred) |

## 2. Research

**Journal-entry (audit) analytics.** Audit practice tests the journal population with
analytical procedures rather than only with samples. Commonly used checks are:
round-amount postings, weekend postings, just-below-approval-threshold amounts, duplicate
postings, and Benford's-law first-digit tests. Open-source examples implement the same set
of checks on general-ledger data:
[journal-entry-anomaly-detector](https://github.com/ethanmanzella07/journal-entry-anomaly-detector)
(duplicate payments, round-dollar, weekend postings, Benford's law) and
[sox-controls-testing](https://github.com/avisharoni/sox-controls-testing)
(weekend and after-hours postings, round amounts, just-under-threshold entries, manual
entries by unusual users, Benford deviation). Benford's test is best treated as an
indicator: the first project above notes that recurring fixed amounts naturally deviate
from the expected distribution. Our design therefore reports Benford results as an
indicator with a plain-language explanation, and uses the `source` column (manual or system)
to focus the timing checks on manual entries.

**Direct-method cash flow.** Under the direct method, cash receipts and payments are grouped
into operating, investing and financing activities. The usual reference classification is:
collections from customers and payments to suppliers and employees are operating; purchases
and sales of fixed assets are investing; loans, repayments and share capital are financing
([KPMG Handbook Statement of cash flows](https://kpmg.com/kpmg-us/content/dam/kpmg/frv/pdf/2024/handbook-statement-cash-flows.pdf),
[LibreTexts Statement of Cash Flows, direct method](https://biz.libretexts.org/Bookshelves/Accounting/Introduction_to_Financial_Accounting_(Dauderis_and_Annand)/11:_The_Statement_of_Cash_Flows/11.05:_Appendix_B-_Statement_of_Cash_Flows__Direct_Method)).
Because every cash line sits in a balanced journal entry, the cash effect of each
counterpart line can be classified by its account, and the total must equal the change in
the cash account. That identity gives a strong reconciliation test.

**Accounts payable aging and reconciliation.** Payables are aged like receivables. Supplier
invoices form a sub-ledger that must equal the AP control account at every date.

**Forecasting.** For a short monthly series with a trend and yearly seasonality, a classical
decomposition (linear trend times a seasonal index) is transparent, needs no heavy
dependency, and can be backtested on a holdout period. It is appropriate for a small
company dashboard, and the forecast is clearly labelled as an estimate.

**Excel export.** `openpyxl` (already a dependency of pandas tooling) writes `.xlsx` files with
formatting, which lets finance users re-use the statements.

**Continuous integration.** A GitHub Actions workflow that runs lint and tests on several
Python versions is a standard addition for an open-source repository.

## 3. Selected improvements

| ID | Improvement | Addresses | Why |
|---|---|---|---|
| I-1 | Direct-method cash flow statement (monthly and period) with reconciliation to the cash ledger | R2 | Cash is the most important liquidity measure; reconciliation is a strong test |
| I-2 | Accounts payable aging from supplier invoices, with AP sub-ledger reconciliation | R3 | Completes the working-capital picture and mirrors receivables |
| I-3 | Journal audit analytics: `source` column, round-amount, weekend manual entries, threshold proximity, statistical outliers, possible duplicates, Benford test; ground-truth evaluation on a demo dataset | R4 | Core audit-analytics capability; measurable with injected anomalies |
| I-4 | Excel workbook export (multi-sheet, formatted), CLI `export` and dashboard download button | R5 | Finance users can take the numbers into spreadsheets |
| I-5 | Revenue forecast (trend and seasonality) with confidence band and holdout backtest | R6 | Gives an outlook; accuracy is measurable |
| I-6 | Cost-centre view of expenses by department and month | R7 | Uses data that is already captured |
| I-7 | Secure defaults (localhost bind), CI workflow, lint and coverage gate | R1, R8 | Safer by default, and quality is enforced automatically |

**Deferred:** R9 (multiple payments per invoice; would need a `payments.csv` and is planned for
v1.2) and R10 (VAT and multi-currency; planned as separate releases because they change the
data model and need legal rules).

## 4. Compatibility decisions

* The new `supplier_invoices.csv` is **optional**: datasets created with v1.0 still load, and
  AP aging is then empty with a warning.
* The new `source` column in `journal_entries.csv` is **optional** (default `system`).
* Analysis results keep their existing fields; new fields are added.
