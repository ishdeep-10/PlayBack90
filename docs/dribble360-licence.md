# Dribble360 licence: what is permitted (record kept 2026-10-28)

Governing document: Terms of Service at https://dribble360.com/terms (last updated 1 September 2026), Sections 6, 7, 8.
Keep a dated copy of the terms and the reply below: the page can change, and a price change needs 30 days' notice (Section 4).

## Vendor reply (Dribble360, in answer to my email of 2026-10-28)

1. **Paywall:** covered. The Pro plan carries the commercial licence; building and selling a product on the data is permitted (Section 8). Boundary: the licence covers my product and its analysis; it does not pass the raw data to my subscribers.
2. **Terms:** Sections 6 (raw-data redistribution), 7 (data is sourced from Opta under licence), 8 (commercial use on BigQuery Pro).
3. **Derived metrics:** permitted (own xG, xA, passing models; published summaries). PDF reports with derived metrics, aggregates and summaries are fine. A report that embeds or makes downloadable the raw event rows is redistribution and needs a signed data-licence addendum.
4. **Attribution:** not required. I may say publicly that PlayBack90 uses Dribble data, in the app and in PDF reports. Suggested wording: "Data by Dribble (dribble360.com)". **Do not use their logo** (Section 7: name or logo needs prior written permission).

## Rules this puts on the product

- No CSV / JSON / row downloads of event data, no event rows inside PDF reports. Today the only downloads are PNG images of visuals and generated PDF reports.
- Raw-data redistribution (resale, sublicensing, exposing bulk rows) needs a signed addendum first.
- API keys are personal and non-transferable; plan request limits apply across all keys.
- Violations can mean immediate suspension without refund.

## Follow-up reply (Dribble360, 2026-10-28): chart data in the browser is covered

Data my server sends to a logged-in subscriber's browser so PlayBack90 can display the chart in front of them is display within the product, not redistribution (dashboards and apps are named permitted products on Pro). Anything that makes the data itself the product needs the signed data-licence addendum: an API or feed of the underlying data, row exports or downloads, bulk delivery, or giving subscribers rights to reuse the raw data outside PlayBack90. Tip from them: send each visual only the figures it needs (aggregates and derived values where the chart allows).

## Safeguards I told them about: status as of 2026-10-28

| Commitment | Status |
|---|---|
| Data behind login | Implemented: Clerk auth middleware (`app/auth.py`) gates every route except health/docs/asset paths when `AUTH_REQUIRED=true`. The production example env has it on; **verify the live server** (the code default is off). |
| Rate-limited | **Partial.** `enforce_rate_limit` covers only PNG/PDF rendering and imports. The data endpoints (matches, analysis views, season stats) have no limit. To do before the paywall. |
| My own terms forbid scraping and automated access | **Not done.** The web app has `/privacy` only; there is no terms-of-service page. To do before the paywall. |

## Still to do

- Add "Data by Dribble (dribble360.com)" to the PNG downloads if wanted (done for the app footer and PDF reports).
- Review which API responses send more rows than their visual needs, and aggregate server-side where the chart allows.
