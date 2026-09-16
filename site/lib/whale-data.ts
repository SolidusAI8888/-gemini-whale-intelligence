export type ActionKind = 'BUY' | 'SELL' | 'NEW' | 'ADD' | 'REDUCE' | 'EXIT';

export type CoreAsset = {
  ticker: string; name: string; kind: 'Equity' | 'Crypto'; price: number;
  change: number; signals: number; spark: number[];
};

export type TradeEvent = {
  id: string; ticker: string; actor: string; organization: string; role: string;
  action: ActionKind; amount: string; instrument: string; occurredAt: string;
  publishedAt: string; lagDays: number;
  source: 'Congress PTR' | 'SEC 13F' | 'SEC Form 4' | 'OGE'; evidence: 'A' | 'B';
};

export const coreAssets: CoreAsset[] = [
  { ticker: 'BTC', name: 'Bitcoin', kind: 'Crypto', price: 114820, change: 1.82, signals: 4, spark: [92, 98, 96, 103, 108, 105, 114] },
  { ticker: 'MSTR', name: 'Strategy', kind: 'Equity', price: 352.61, change: 2.41, signals: 5, spark: [72, 76, 74, 81, 79, 86, 92] },
  { ticker: 'NVDA', name: 'NVIDIA', kind: 'Equity', price: 184.77, change: 0.96, signals: 12, spark: [63, 66, 70, 68, 74, 78, 81] },
  { ticker: 'TSLA', name: 'Tesla', kind: 'Equity', price: 409.38, change: -1.13, signals: 8, spark: [86, 82, 84, 78, 81, 75, 73] },
  { ticker: 'SPCX', name: 'SpaceX', kind: 'Equity', price: 142.18, change: 3.06, signals: 3, spark: [48, 51, 54, 53, 60, 64, 69] },
  { ticker: 'GOOG', name: 'Alphabet', kind: 'Equity', price: 238.56, change: 0.41, signals: 7, spark: [73, 72, 76, 79, 77, 80, 82] },
  { ticker: 'PLTR', name: 'Palantir', kind: 'Equity', price: 192.24, change: 1.47, signals: 9, spark: [54, 59, 57, 63, 67, 72, 76] },
  { ticker: 'ORCL', name: 'Oracle', kind: 'Equity', price: 291.47, change: -0.32, signals: 6, spark: [81, 84, 82, 86, 83, 82, 81] },
  { ticker: 'HOOD', name: 'Robinhood', kind: 'Equity', price: 124.08, change: 2.18, signals: 7, spark: [44, 49, 47, 54, 58, 62, 66] },
  { ticker: 'INTC', name: 'Intel', kind: 'Equity', price: 38.71, change: 0.68, signals: 10, spark: [67, 64, 66, 62, 65, 68, 70] },
  { ticker: 'MU', name: 'Micron', kind: 'Equity', price: 216.35, change: 1.21, signals: 8, spark: [57, 61, 65, 63, 69, 71, 75] },
  { ticker: 'AAPL', name: 'Apple', kind: 'Equity', price: 244.63, change: -0.18, signals: 6, spark: [80, 82, 81, 84, 83, 82, 82] },
  { ticker: 'AMZN', name: 'Amazon', kind: 'Equity', price: 236.11, change: 0.77, signals: 5, spark: [69, 71, 70, 74, 73, 76, 78] },
  { ticker: 'AMD', name: 'AMD', kind: 'Equity', price: 228.42, change: 1.64, signals: 11, spark: [56, 58, 63, 61, 66, 72, 75] },
  { ticker: 'GLW', name: 'Corning', kind: 'Equity', price: 82.19, change: 0.28, signals: 3, spark: [73, 71, 72, 75, 74, 76, 77] },
  { ticker: 'MRVL', name: 'Marvell', kind: 'Equity', price: 92.84, change: -0.74, signals: 5, spark: [75, 78, 76, 73, 75, 72, 70] },
  { ticker: 'MSFT', name: 'Microsoft', kind: 'Equity', price: 518.93, change: 0.52, signals: 13, spark: [65, 68, 70, 69, 72, 74, 76] },
  { ticker: 'UBER', name: 'Uber', kind: 'Equity', price: 96.72, change: 1.09, signals: 9, spark: [58, 61, 59, 64, 67, 69, 72] },
  { ticker: 'AVGO', name: 'Broadcom', kind: 'Equity', price: 371.66, change: 0.89, signals: 8, spark: [60, 64, 63, 68, 71, 73, 76] },
  { ticker: 'RKLB', name: 'Rocket Lab', kind: 'Equity', price: 72.11, change: 2.72, signals: 5, spark: [42, 48, 46, 53, 57, 62, 68] },
  { ticker: 'PURR', name: 'Purr', kind: 'Equity', price: 31.48, change: -0.61, signals: 2, spark: [61, 64, 62, 60, 63, 59, 58] },
];

export const tradeEvents: TradeEvent[] = [
  { id: 'pelosi-intc-2026', ticker: 'INTC', actor: 'Paul Pelosi', organization: 'U.S. House disclosure', role: 'Spouse of Member of Congress', action: 'BUY', amount: '$1.0M–$5.0M', instrument: 'Call options', occurredAt: '2026-05-29', publishedAt: '2026-06-23', lagDays: 25, source: 'Congress PTR', evidence: 'A' },
  { id: 'pelosi-uber-2026', ticker: 'UBER', actor: 'Paul Pelosi', organization: 'U.S. House disclosure', role: 'Spouse of Member of Congress', action: 'BUY', amount: '$500K–$1.0M', instrument: 'Call options', occurredAt: '2026-05-29', publishedAt: '2026-06-23', lagDays: 25, source: 'Congress PTR', evidence: 'A' },
  { id: 'pershing-uber-q1', ticker: 'UBER', actor: 'Pershing Square', organization: 'Pershing Square Capital Management', role: 'Institutional manager', action: 'ADD', amount: '$2.15B position', instrument: 'Common stock', occurredAt: '2026-03-31', publishedAt: '2026-05-15', lagDays: 45, source: 'SEC 13F', evidence: 'B' },
  { id: 'pelosi-msft-2026', ticker: 'MSFT', actor: 'Paul Pelosi', organization: 'U.S. House disclosure', role: 'Spouse of Member of Congress', action: 'BUY', amount: '$1.0M–$5.0M', instrument: 'Call options', occurredAt: '2026-05-29', publishedAt: '2026-06-23', lagDays: 25, source: 'Congress PTR', evidence: 'A' },
  { id: 'oge-msft-sale', ticker: 'MSFT', actor: 'Executive branch filer', organization: 'U.S. Executive Branch', role: 'Cabinet-level disclosure', action: 'SELL', amount: '$5.0M–$25.0M', instrument: 'Common stock', occurredAt: '2026-02-02', publishedAt: '2026-03-18', lagDays: 44, source: 'OGE', evidence: 'A' },
];

export const concentration = [
  { ticker: 'MSFT', score: 92, buyers: 6, groups: 3, net: '$18.4M+' },
  { ticker: 'INTC', score: 88, buyers: 5, groups: 3, net: '$12.7M+' },
  { ticker: 'UBER', score: 84, buyers: 4, groups: 2, net: '$8.6M+' },
  { ticker: 'NVDA', score: 79, buyers: 7, groups: 2, net: '$6.2M+' },
  { ticker: 'AMD', score: 73, buyers: 4, groups: 2, net: '$4.8M+' },
];
