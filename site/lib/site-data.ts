import { assetCatalog, regressionEvents, type ActionKind, type CoreAsset, type TradeEvent } from '@/lib/whale-data';

type RawEvent = { id?: string; ticker?: string; action?: string; actor?: string; organization?: string; role?: string; responsible_people?: string[]; amount_usd?: number; amount_display?: string | null; shares?: number; occurred_at?: string; published_at?: string; lag_days?: number | null; source?: string; source_url?: string; evidence_grade?: string };
type RawAsset = { ticker?: string; market?: Record<string, unknown> | null; price_history?: Array<{ date?: string; close?: number }> };
type RawConcentration = { ticker?: string; score?: number; actor_count?: number; group_count?: number; net_amount_usd?: number };
export type SitePayload = { schema_version?: number; generated_at?: string; mode?: string; core_assets?: RawAsset[]; events?: RawEvent[]; holdings?: RawEvent[]; concentration?: RawConcentration[]; holding_concentration?: Array<{ ticker?: string; holder_count?: number; source_count?: number; reported_value_usd?: number }> };
export type ConcentrationRow = { ticker: string; score: number; buyers: number; groups: number; net: string };
export type HoldingRow = { ticker: string; holderCount: number; sourceCount: number; value: string };
export type SiteViewData = { mode: 'production' | 'regression'; generatedAt: string | null; assets: CoreAsset[]; events: TradeEvent[]; concentration: ConcentrationRow[]; holdingConcentration: HoldingRow[]; holdings: TradeEvent[] };

const actions = new Set<ActionKind>(['BUY', 'SELL', 'NEW', 'ADD', 'REDUCE', 'EXIT']);
const numberValue = (value: unknown) => typeof value === 'number' && Number.isFinite(value) ? value : null;
export function formatMoney(value: number): string { const absolute = Math.abs(value); const sign = value < 0 ? '−' : ''; if (absolute >= 1_000_000_000) return `${sign}$${(absolute / 1_000_000_000).toFixed(2)}B`; if (absolute >= 1_000_000) return `${sign}$${(absolute / 1_000_000).toFixed(1)}M`; if (absolute >= 1_000) return `${sign}$${(absolute / 1_000).toFixed(0)}K`; return absolute ? `${sign}$${absolute.toLocaleString('en-US')}` : '金额未披露'; }

function mapEvent(raw: RawEvent): TradeEvent | null {
  const action = String(raw.action || '').toUpperCase() as ActionKind; const ticker = String(raw.ticker || '').toUpperCase();
  if (!actions.has(action) || !ticker) return null;
  const amountUsd = numberValue(raw.amount_usd) || 0;
  return { id: String(raw.id || `${ticker}-${raw.published_at || raw.occurred_at || 'event'}`), ticker, action, actor: String(raw.actor || 'Unknown filer'), organization: String(raw.organization || ''), role: String(raw.role || ''), responsiblePeople: Array.isArray(raw.responsible_people) ? raw.responsible_people.map(String) : [], amount: String(raw.amount_display || formatMoney(amountUsd)), amountUsd, instrument: raw.shares ? `${Number(raw.shares).toLocaleString('en-US')} shares` : '申报证券', occurredAt: String(raw.occurred_at || ''), publishedAt: String(raw.published_at || ''), lagDays: numberValue(raw.lag_days), source: String(raw.source || 'Public filing'), sourceUrl: String(raw.source_url || ''), evidence: raw.evidence_grade === 'A' ? 'A' : 'B' };
}

function regressionView(): SiteViewData {
  const counts = new Map<string, number>(); regressionEvents.forEach((event) => counts.set(event.ticker, (counts.get(event.ticker) || 0) + 1));
  return { mode: 'regression', generatedAt: null, assets: assetCatalog.map(([ticker, name, kind]) => ({ ticker, name, kind, price: null, change: null, signals: counts.get(ticker) || 0, priceHistory: [] })), events: regressionEvents, holdings: [], holdingConcentration: [], concentration: ['MSFT', 'INTC', 'UBER'].map((ticker, index) => ({ ticker, score: 40 - index * 4, buyers: 1, groups: 1, net: regressionEvents.find((event) => event.ticker === ticker)?.amount || '—' })) };
}

export function toSiteView(payload: SitePayload | null): SiteViewData {
  const events = (payload?.events || []).map(mapEvent).filter((event): event is TradeEvent => Boolean(event));
  const rawAssets = new Map((payload?.core_assets || []).map((asset) => [String(asset.ticker || '').toUpperCase(), asset]));
  const live = payload?.mode === 'production' && (events.length > 0 || (payload?.holdings || []).length > 0 || (payload?.core_assets || []).some((asset) => asset.market));
  if (!live) return regressionView();
  const counts = new Map<string, number>(); events.forEach((event) => counts.set(event.ticker, (counts.get(event.ticker) || 0) + 1));
  const assets = assetCatalog.map(([ticker, name, kind]) => { const raw = rawAssets.get(ticker); const market = raw?.market || {}; return { ticker, name, kind, price: numberValue(market.price), change: numberValue(market.change_pct), signals: counts.get(ticker) || 0, priceHistory: (raw?.price_history || []).flatMap((point) => { const close = numberValue(point.close); const date = String(point.date || ''); return close && date ? [{ date, close }] : []; }) }; });
  return { mode: 'production', generatedAt: payload?.generated_at || null, assets, events,
    holdings: (payload?.holdings || []).map((raw) => mapEvent({ ...raw, action: 'ADD' })).filter((event): event is TradeEvent => Boolean(event)),
    concentration: (payload?.concentration || []).slice(0, 8).map((row) => ({ ticker: String(row.ticker || ''), score: Number(row.score || 0), buyers: Number(row.actor_count || 0), groups: Number(row.group_count || 0), net: formatMoney(Number(row.net_amount_usd || 0)) })),
    holdingConcentration: (payload?.holding_concentration || []).slice(0, 8).map((row) => ({ ticker: String(row.ticker || ''), holderCount: Number(row.holder_count || 0), sourceCount: Number(row.source_count || 0), value: formatMoney(Number(row.reported_value_usd || 0)) })) };
}
export const regressionSiteView = regressionView();
