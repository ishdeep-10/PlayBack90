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

## Open

- **Data sent to the browser to draw charts:** the terms do not address it and the reply did not answer it. Ask: "is chart data delivered to the subscriber's browser for display covered?" Meanwhile: keep the API behind login, rate-limit it, forbid scraping in the PlayBack90 terms, and send aggregates where a visual does not need rows.
- Model training on Pro data: the reply covers "models" generally; the earlier plan item stays closed only because the product does not train models.
- Add "Data by Dribble (dribble360.com)" to the app footer and the PDF report template before the data goes live and before any public post.
