# Changelog

## V39.1 — 2026-07-23

### Fixed
- Removed `missing source = 50` scoring behavior.
- Prevented unavailable pillars from diluting or inflating WIS.
- Replaced inverse-WIS risk with an independent downside-risk calculation.
- Preserved bullish/bearish direction in resonance and exposed conflicts.
- Prevented ordinary one-source signals from entering the opportunity Top 10.
- Stopped known AMD/ASML/LRCX CUSIPs from appearing as unresolved identifiers.

### Added
- Coverage count/ratio/label and effective source list.
- Signal count, freshness days/label, confidence, and Low Coverage flag.
- Signed resonance score, direction, and source composition.
- V39.1 HTML columns and explicit `N/A` rendering.
- V39.1 regression tests and upgrade/rollback documentation.
