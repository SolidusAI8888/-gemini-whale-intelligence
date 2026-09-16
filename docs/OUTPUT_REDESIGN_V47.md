# V47 Report Output Redesign

## Reference review

The redesign uses `smart-money-fomo.vercel.app` as a product reference, not as a visual template.

Useful patterns adopted:

- A clear working hierarchy: global navigation, current signal state, then evidence.
- Ticker/person-first discovery instead of forcing a linear read through every table.
- Persistent section navigation for moving among flows, political activity, and holdings.
- Consistent action colors and compact, comparable rows.
- A single workspace that keeps summary and source evidence close together.

Patterns deliberately not copied:

- The three-column terminal layout, which is too dense for email and narrow screens.
- Overlapping notification cards and repeated upgrade prompts that obscure evidence.
- Live-price/K-line behavior, because this report is based on delayed statutory disclosures.
- Hidden evidence or paywall-driven information hierarchy.
- Brand language, typography, assets, and proprietary content from the reference site.

## Implementation principles

- Progressive enhancement: the saved HTML adds sticky navigation and report-wide search, while the email remains readable when scripts are removed.
- Evidence remains intact: existing tables, source links, amounts, dates, and methodology sections are preserved.
- Release gates remain authoritative: V47 does not change collection, classification, universe construction, or delivery workflows.
- Responsive by default: dense tables scroll horizontally on small screens; charts collapse to single-column rows.
- Print-safe: navigation and search controls are removed from print output and tables return to print layout.

## Protected regressions

- Large accepted political BUY records for UBER, MSFT, and INTC must remain visible in the active-buy radar.
- OGE semantic junk remains blocked by the existing quality gate.
- Universe loading and fallback validation are unchanged.
- Report generation still passes the release quality checks before save or email delivery.
