# Sovra Verify evidence bundle — analysis 429df808d24f4433

- Generated: 2026-10-12T16:53:55+00:00
- Status: `complete`
- Provider: `cscs`
- Model: `swiss-ai/Apertus-v1.5-70B`
- Prompt version: `sovra-prompts-3`
- Credential (masked): `sk-g...1c (len=40)`

## Corpus and hashes
- `01_master_supply_agreement.txt` — sha256 `1202cdf34b4381c11435901a9bf629b35fc459cf5ba8b63e00ab69d48aa9efe1`, 1094 bytes, 1 page(s), extraction `ok`
- `02_accounts_payable_policy.txt` — sha256 `fed7c43f445118657d6506454333c7ff59ea1397b28422b92cc3550117796de6`, 779 bytes, 1 page(s), extraction `ok`
- `03_invoice_INV-2026-0417.txt` — sha256 `02b8fbc6d74d627d7ac12247d92bba2edb4724baff22caf1daa4bfbc0a76fe88`, 689 bytes, 1 page(s), extraction `ok`
- `04_amendment_2.txt` — sha256 `8701e49ff13c79df599ac7c78806480073cbfd2184ffdf42ecf324feb08e2ed1`, 510 bytes, 1 page(s), extraction `ok`

## Provider ledger
- Calls: 11 (0 failed, 0 backup)
- Prompt tokens: 9645, completion tokens: 4247, total: 13892
- Models: cscs:swiss-ai/Apertus-v1.5-70B
- Total provider latency: 68879 ms
  - `claims` cscs/swiss-ai/Apertus-v1.5-70B status=ok latency=12335 ms tokens=1906
  - `claims` cscs/swiss-ai/Apertus-v1.5-70B status=ok latency=21161 ms tokens=2511
  - `claims` cscs/swiss-ai/Apertus-v1.5-70B status=ok latency=7839 ms tokens=1432
  - `compare` cscs/swiss-ai/Apertus-v1.5-70B status=ok latency=4013 ms tokens=1003
  - `compare` cscs/swiss-ai/Apertus-v1.5-70B status=ok latency=3295 ms tokens=992
  - `compare` cscs/swiss-ai/Apertus-v1.5-70B status=ok latency=3351 ms tokens=1015
  - `compare` cscs/swiss-ai/Apertus-v1.5-70B status=ok latency=3841 ms tokens=1022
  - `compare` cscs/swiss-ai/Apertus-v1.5-70B status=ok latency=3443 ms tokens=986
  - `compare` cscs/swiss-ai/Apertus-v1.5-70B status=ok latency=3350 ms tokens=1024
  - `compare` cscs/swiss-ai/Apertus-v1.5-70B status=ok latency=3141 ms tokens=1000
  - `compare` cscs/swiss-ai/Apertus-v1.5-70B status=ok latency=3110 ms tokens=1001

## Findings and citation check
- Findings: 8
- Citation spans re-derived from canonical text: 16
- All offsets reproduce their quote: `True`
  - document `94784ae867b34b40` page 1 [239, 430] reproduces=True
    > Policy 4.1 Standard settlement period
All supplier invoices are settled within 60 days of the invoice date. Finance
Operations processes the payment run on the last working day of each month.
  - document `b703950b0a74445b` page 1 [533, 742] reproduces=True
    > Clause 7.5 Expedited freight exception
Invoices issued under the expedited freight programme described in Schedule C
are payable within 10 days of the invoice date. Clause 7.2 does not apply to
those invoices.
  - document `2b958ac3ea604fe6` page 1 [501, 615] reproduces=True
    > Payment terms: payable within 30 days of the invoice date, as stated in Clause
7.2 of the Master Supply Agreement.
  - document `b703950b0a74445b` page 1 [533, 742] reproduces=True
    > Clause 7.5 Expedited freight exception
Invoices issued under the expedited freight programme described in Schedule C
are payable within 10 days of the invoice date. Clause 7.2 does not apply to
those invoices.
  - document `9f84ec4d54d34f0c` page 1 [135, 296] reproduces=True
    > Clause 1
Clause 7.2 of the Master Supply Agreement is amended. The payment period for
undisputed invoices is changed from 30 days to 45 days of the invoice date.
  - document `b703950b0a74445b` page 1 [533, 742] reproduces=True
    > Clause 7.5 Expedited freight exception
Invoices issued under the expedited freight programme described in Schedule C
are payable within 10 days of the invoice date. Clause 7.2 does not apply to
those invoices.
  - document `b703950b0a74445b` page 1 [342, 531] reproduces=True
    > Clause 7.2 Payment terms
The Buyer shall pay each undisputed invoice within 30 days of the invoice date.
Payments shall be made in CHF by bank transfer to the account stated on the
invoice.
  - document `94784ae867b34b40` page 1 [239, 430] reproduces=True
    > Policy 4.1 Standard settlement period
All supplier invoices are settled within 60 days of the invoice date. Finance
Operations processes the payment run on the last working day of each month.
  - document `9f84ec4d54d34f0c` page 1 [298, 429] reproduces=True
    > Clause 2
Invoices issued before the effective date of this amendment remain payable
under the terms in force on their invoice date.
  - document `b703950b0a74445b` page 1 [533, 742] reproduces=True
    > Clause 7.5 Expedited freight exception
Invoices issued under the expedited freight programme described in Schedule C
are payable within 10 days of the invoice date. Clause 7.2 does not apply to
those invoices.
  - document `b703950b0a74445b` page 1 [342, 531] reproduces=True
    > Clause 7.2 Payment terms
The Buyer shall pay each undisputed invoice within 30 days of the invoice date.
Payments shall be made in CHF by bank transfer to the account stated on the
invoice.
  - document `9f84ec4d54d34f0c` page 1 [298, 429] reproduces=True
    > Clause 2
Invoices issued before the effective date of this amendment remain payable
under the terms in force on their invoice date.
  - document `b703950b0a74445b` page 1 [342, 531] reproduces=True
    > Clause 7.2 Payment terms
The Buyer shall pay each undisputed invoice within 30 days of the invoice date.
Payments shall be made in CHF by bank transfer to the account stated on the
invoice.
  - document `2b958ac3ea604fe6` page 1 [501, 615] reproduces=True
    > Payment terms: payable within 30 days of the invoice date, as stated in Clause
7.2 of the Master Supply Agreement.
  - document `b703950b0a74445b` page 1 [342, 531] reproduces=True
    > Clause 7.2 Payment terms
The Buyer shall pay each undisputed invoice within 30 days of the invoice date.
Payments shall be made in CHF by bank transfer to the account stated on the
invoice.
  - document `9f84ec4d54d34f0c` page 1 [135, 296] reproduces=True
    > Clause 1
Clause 7.2 of the Master Supply Agreement is amended. The payment period for
undisputed invoices is changed from 30 days to 45 days of the invoice date.

## Recorded failures
- none recorded in this run

## Limitations
- Prototype: results are potential inconsistencies for human review, not a factual or legal determination.
- 6 of 23 model claims could not be resolved to a validated source span and are shown as unresolved

## Credential audit of the working tree
- Files scanned: 126
- Live-credential findings: 0
- Credential file copies found inside the repository: 0

## Claims about this bundle
- Results are potential inconsistencies for human review, not a factual or legal determination.
- CSCS-hosted inference is external-network inference; a local web app calling CSCS is not air-gapped.
- This bundle contains no credential value; the credential field is a masked form only.