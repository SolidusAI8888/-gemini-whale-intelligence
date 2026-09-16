# V40 Foundation Requirements

## Purpose

This document freezes the confirmed product requirements for the next report version of the U.S. political and business whale intelligence system. It is the acceptance baseline for implementation on `feature/v40-foundation`.

## 1. Today-vs-yesterday change summary

The report must begin with a concise section titled:

> 今日新增内容总览

This section summarizes every item that is new or materially changed compared with the previous report, so the reader can scan the daily delta before reading the full report.

The summary must distinguish at least:

- newly discovered disclosures or transactions;
- material changes to previously known records;
- newly available actor, amount, date, asset-description, or source details;
- newly generated or materially changed intelligence signals.

Do not classify unchanged historical rows as new merely because they are re-collected.

## 2. Orange highlighting of changed rows

Every complete row that is new or materially changed compared with yesterday must be highlighted in orange in the HTML report.

Requirements:

- highlight the entire row, not an individual cell;
- apply the same visual rule consistently across all report sections;
- preserve readability and sufficient text contrast;
- unchanged rows must retain their normal styling;
- the comparison result must be driven by stable record identity and material-field comparison, not table position.

Recommended normalized flags:

```text
is_new_today
is_changed_today
change_fields
```

## 3. Main transaction section

The first main transaction section must be labeled:

> 主动买入雷达（P/BUY，按去重买入金额）

Requirements:

- include only real purchase transactions that qualify as `P/BUY`;
- aggregate and rank by deduplicated purchase amount;
- clearly identify who made each transaction;
- retain transaction date, filing/source date, amount or amount range, ticker/asset, source type, and source link where available;
- remove the legacy field or wording `净信号=减持...` from this section;
- do not mix passive holdings, portfolio snapshots, or non-transaction asset disclosures into this ranking.

## 4. Executive-branch / Cabinet OGE asset radar

Add or preserve a dedicated section titled:

> 部长 / Cabinet OGE 披露雷达

The purpose is to show the latest publicly disclosed investment targets and financial interests of key executive-branch figures. This section is not limited to U.S. listed equities.

Supported asset coverage includes, when available:

- stocks;
- ETFs, mutual funds, and other funds;
- bonds and fixed-income instruments;
- private companies, LLCs, partnerships, and private funds;
- trusts;
- real estate and business interests;
- crypto assets;
- other reportable financial assets.

Minimum displayed fields:

- person / office;
- asset or transaction target;
- concise asset description;
- amount or disclosed value range;
- transaction date or disclosure date;
- disclosure type;
- source link;
- a short factual note when the public record supports one.

Do not force non-listed assets into a U.S. stock ticker.

## 5. Separation of transactions and holdings

The following record categories must not enter the main transaction signal category:

```text
OGE_EXECUTIVE_ASSET
HOLDING
```

They may appear in the dedicated executive-branch asset radar or other holdings/disclosure sections, but they must not be counted as active buy/sell transactions and must not distort transaction-based rankings.

This exclusion must occur before:

- main transaction aggregation;
- P/BUY ranking;
- transaction signal scoring;
- transaction counts shown in report summaries.

## 6. Evidence and identity requirements

Every displayed political or business whale transaction must make the actor identifiable.

Preferred identity fields:

```text
actor_name
actor_role
actor_organization
source_identity
```

Every material claim must retain traceability to the original public disclosure. Parsed or normalized rows must preserve source provenance and should not replace the raw evidence record.

## 7. Deduplication

Deduplication must prevent the same public disclosure or transaction from being counted multiple times due to:

- repeated collection runs;
- mirrored or alternate URLs;
- amended filings;
- multiple parsers reading the same source;
- amount-range normalization differences;
- ticker versus non-ticker asset naming differences.

The implementation should use a stable normalized fingerprint based on the strongest available combination of actor, source document, transaction date, asset identity, transaction type, and amount/value range.

## 8. Acceptance checks

V40 foundation is accepted only when automated or reproducible checks demonstrate that:

1. `OGE_EXECUTIVE_ASSET` and `HOLDING` rows cannot enter the main transaction radar.
2. The active-buy table contains only `P/BUY` records.
3. Deduplicated buy totals are not inflated by duplicate source rows.
4. Every active-buy row contains an identifiable actor.
5. Non-ticker executive assets remain representable and visible.
6. New or materially changed rows receive the orange row class.
7. The front summary contains all and only the report's new/materially changed items.
8. Unchanged rows are not highlighted.
9. The legacy `净信号=减持...` field no longer appears in the report.

## 9. Suggested implementation order

1. Normalize record categories and actor/source identity fields.
2. Add pre-scoring transaction eligibility filters.
3. Implement stable deduplication fingerprints.
4. Build today-vs-yesterday comparison output.
5. Add report-wide orange row styling.
6. Add `今日新增内容总览`.
7. Refactor the active-buy section.
8. Build the broad-asset Cabinet OGE radar.
9. Add regression tests for all acceptance checks.
