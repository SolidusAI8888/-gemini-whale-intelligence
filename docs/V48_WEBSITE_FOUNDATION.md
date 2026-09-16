# V48 Website Foundation

V48 changes the primary product from a generated email/report into a multi-page website. The existing collectors, normalization rules, data-quality gates, WIS calculations, and release workflows remain the evidence pipeline beneath the website.

## Product rules

1. Actions only. Interviews, social posts, predictions, opinions, and media narratives are excluded unless an underlying transaction is independently disclosed.
2. Entity attribution is explicit. An institutional filing belongs to the institution; a chairman, CEO, CFO, CIO, portfolio manager, or other key person is relationship context and is never relabeled as the personal buyer without a personal disclosure.
3. Public-date mode is the default. The chart places a signal on the first public disclosure date. Occurrence-date mode is available only as a clearly labeled research view.
4. A purchase is not automatically a new position, and a sale is not automatically a full exit. `NEW`, `ADD`, `REDUCE`, and `EXIT` require position-history evidence.
5. UBER, MSFT, and INTC political transactions remain mandatory regression examples.

## Initial site surface

- Action radar home page
- The 21 fixed core assets
- Per-asset detail routes under `/assets/{ticker}`
- Price/action timeline with public-date and occurrence-date modes
- Evidence ledger with actor, organization, role, source, disclosure delay, and evidence grade
- Cross-group concentration preview

## Data handoff

Run `python -m app.site_data` after a scan to create `site/public/data/site-data.json`. The payload contains the fixed core universe, evidence-gated transactions, derived 13F snapshot changes, source URLs, public dates, occurrence dates, disclosure lag, and institution/person attribution fields.

The current local site uses historical regression fixtures when a production database is not present. It labels that state as a product preview and does not present the fixture values as a live feed.
