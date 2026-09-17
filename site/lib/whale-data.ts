export type ActionKind = 'BUY' | 'SELL' | 'NEW' | 'ADD' | 'REDUCE' | 'EXIT';
export type PricePoint = { date: string; open: number; high: number; low: number; close: number; volume: number };
export type CoreAsset = { ticker: string; name: string; kind: 'Equity' | 'Crypto' | 'Private'; price: number | null; change: number | null; signals: number; priceHistory: PricePoint[] };
export type TradeEvent = {
  id: string; ticker: string; actor: string; organization: string; role: string; responsiblePeople: string[];
  action: ActionKind; amount: string; amountUsd: number; instrument: string; occurredAt: string;
  publishedAt: string; lagDays: number | null; source: string; sourceUrl: string; evidence: 'A' | 'B';
};

export const assetCatalog = [
  ['BTC', 'Bitcoin', 'Crypto'], ['MSTR', 'Strategy', 'Equity'], ['NVDA', 'NVIDIA', 'Equity'], ['TSLA', 'Tesla', 'Equity'],
  ['SPCX', 'SpaceX', 'Private'], ['GOOG', 'Alphabet', 'Equity'], ['PLTR', 'Palantir', 'Equity'], ['ORCL', 'Oracle', 'Equity'],
  ['HOOD', 'Robinhood', 'Equity'], ['INTC', 'Intel', 'Equity'], ['MU', 'Micron', 'Equity'], ['AAPL', 'Apple', 'Equity'],
  ['AMZN', 'Amazon', 'Equity'], ['AMD', 'AMD', 'Equity'], ['GLW', 'Corning', 'Equity'], ['MRVL', 'Marvell', 'Equity'],
  ['MSFT', 'Microsoft', 'Equity'], ['UBER', 'Uber', 'Equity'], ['AVGO', 'Broadcom', 'Equity'], ['RKLB', 'Rocket Lab', 'Equity'], ['PURR', 'Purr', 'Equity'],
] as const;

export const coreAssets: CoreAsset[] = assetCatalog.map(([ticker, name, kind]) => ({ ticker, name, kind, price: null, change: null, signals: 0, priceHistory: [] }));

// Regression fixtures are deliberately segregated from production data. They
// preserve UBER/MSFT/INTC visibility tests in a checkout with no production DB.
export const regressionEvents: TradeEvent[] = [
  { id: 'regression-intc', ticker: 'INTC', actor: 'Paul Pelosi', organization: 'U.S. House disclosure', role: 'Spouse of Member of Congress', responsiblePeople: [], action: 'BUY', amount: '$1.0M–$5.0M', amountUsd: 3_000_000, instrument: 'Call options', occurredAt: '2026-05-29', publishedAt: '2026-06-23', lagDays: 25, source: 'Congress PTR', sourceUrl: '', evidence: 'A' },
  { id: 'regression-uber', ticker: 'UBER', actor: 'Paul Pelosi', organization: 'U.S. House disclosure', role: 'Spouse of Member of Congress', responsiblePeople: [], action: 'BUY', amount: '$500K–$1.0M', amountUsd: 750_000, instrument: 'Call options', occurredAt: '2026-05-29', publishedAt: '2026-06-23', lagDays: 25, source: 'Congress PTR', sourceUrl: '', evidence: 'A' },
  { id: 'regression-msft', ticker: 'MSFT', actor: 'Paul Pelosi', organization: 'U.S. House disclosure', role: 'Spouse of Member of Congress', responsiblePeople: [], action: 'BUY', amount: '$1.0M–$5.0M', amountUsd: 3_000_000, instrument: 'Call options', occurredAt: '2026-05-29', publishedAt: '2026-06-23', lagDays: 25, source: 'Congress PTR', sourceUrl: '', evidence: 'A' },
];
