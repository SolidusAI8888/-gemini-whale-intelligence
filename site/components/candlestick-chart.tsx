'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import type { PricePoint, TradeEvent } from '@/lib/whale-data';

type Marker = TradeEvent & { pointDate: string; pointPrice: number };
type Hover = { x: number; y: number; marker?: Marker; candle?: PricePoint } | null;

const actionLabel: Record<TradeEvent['action'], string> = { BUY: '买入', SELL: '卖出', NEW: '新建仓', ADD: '加仓', REDUCE: '减仓', EXIT: '清仓' };
const positive = new Set<TradeEvent['action']>(['BUY', 'NEW', 'ADD']);
const chartPadding = { left: 14, right: 72, top: 28, bottom: 34 } as const;

export function CandlestickChart({ series, markers, onMarkerHover }: { series: PricePoint[]; markers: Marker[]; onMarkerHover?: (id: string | null) => void }) {
  const host = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(900);
  const [hover, setHover] = useState<Hover>(null);
  const [windowSize, setWindowSize] = useState(series.length);
  const [endIndex, setEndIndex] = useState(series.length);
  const height = 460;
  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(360, entry.contentRect.width)));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  useEffect(() => { setWindowSize(series.length); setEndIndex(series.length); }, [series]);
  const visibleSeries = useMemo(() => series.slice(Math.max(0, endIndex - windowSize), endIndex), [series, windowSize, endIndex]);
  const visibleStart = Math.max(0, endIndex - windowSize);
  const visibleDates = useMemo(() => new Set(visibleSeries.map((point) => point.date)), [visibleSeries]);
  const visibleMarkers = useMemo(() => markers.filter((marker) => visibleDates.has(marker.pointDate)), [markers, visibleDates]);
  const setPreset = (days: number | null) => { const next = days === null ? series.length : Math.min(series.length, days); setWindowSize(Math.max(5, next)); setEndIndex(series.length); setHover(null); };
  const zoom = (factor: number) => { const next = Math.max(10, Math.min(series.length, Math.round(windowSize * factor))); setWindowSize(next); setEndIndex(Math.max(next, Math.min(series.length, endIndex))); setHover(null); };
  const pan = (direction: number) => { const step = Math.max(1, Math.round(windowSize * .35)); setEndIndex((current) => Math.max(windowSize, Math.min(series.length, current + direction * step))); setHover(null); };
  const model = useMemo(() => {
    const lows = visibleSeries.map((point) => point.low);
    const highs = visibleSeries.map((point) => point.high);
    const rawMin = Math.min(...lows);
    const rawMax = Math.max(...highs);
    const margin = Math.max((rawMax - rawMin) * 0.06, rawMax * 0.005);
    const min = rawMin - margin;
    const max = rawMax + margin;
    const plotWidth = width - chartPadding.left - chartPadding.right;
    const plotHeight = height - chartPadding.top - chartPadding.bottom;
    const x = (index: number) => chartPadding.left + (index + 0.5) * plotWidth / Math.max(1, visibleSeries.length);
    const y = (value: number) => chartPadding.top + (max - value) / Math.max(0.0001, max - min) * plotHeight;
    return { min, max, plotWidth, plotHeight, x, y, candleWidth: Math.max(1, Math.min(12, plotWidth / Math.max(1, visibleSeries.length) * 0.72)) };
  }, [visibleSeries, width]);
  const indexByDate = useMemo(() => new Map(visibleSeries.map((point, index) => [point.date, index])), [visibleSeries]);
  const allMonthTicks = visibleSeries.flatMap((point, index) => index === 0 || point.date.slice(0, 7) !== visibleSeries[index - 1].date.slice(0, 7) ? [{ point, index }] : []);
  const monthStep = Math.max(1, Math.ceil(allMonthTicks.length / Math.max(5, Math.floor(width / 120))));
  const monthTicks = allMonthTicks.filter((_, index) => index % monthStep === 0 || index === allMonthTicks.length - 1);
  const yTicks = Array.from({ length: 6 }, (_, index) => model.min + (model.max - model.min) * index / 5);

  return <div className="candle-host" ref={host} onMouseLeave={() => { setHover(null); onMarkerHover?.(null); }}>
    <div className="candle-controls" aria-label="图表缩放与平移"><span>{visibleSeries[0]?.date} — {visibleSeries.at(-1)?.date}</span><div><button onClick={() => pan(-1)} disabled={visibleStart === 0} aria-label="向前平移">‹</button><button onClick={() => zoom(.65)} disabled={windowSize <= 10} aria-label="放大">＋</button><button onClick={() => zoom(1.55)} disabled={windowSize >= series.length} aria-label="缩小">−</button><button onClick={() => pan(1)} disabled={endIndex >= series.length} aria-label="向后平移">›</button>{[[22, '1月'], [66, '3月'], [132, '6月']].map(([days, label]) => <button key={label} onClick={() => setPreset(Number(days))}>{label}</button>)}<button onClick={() => setPreset(null)}>全部</button></div></div>
    <svg viewBox={`0 0 ${width} ${height}`} aria-label={`${visibleSeries[0]?.date} 至 ${visibleSeries.at(-1)?.date} 的 ${visibleSeries.length} 根日线蜡烛及巨鲸行动标记`}>
      {yTicks.map((value) => <g key={value}><line x1={chartPadding.left} x2={width - chartPadding.right} y1={model.y(value)} y2={model.y(value)} className="candle-grid" /><text x={width - chartPadding.right + 9} y={model.y(value) + 4} className="candle-axis">${value.toLocaleString('en-US', { maximumFractionDigits: value < 10 ? 2 : 0 })}</text></g>)}
      {monthTicks.map(({ point, index }) => <text key={point.date} x={model.x(index)} y={height - 10} className="candle-axis month">{point.date.slice(0, 7)}</text>)}
      {visibleSeries.map((point, index) => { const up = point.close >= point.open; const x = model.x(index); const top = model.y(Math.max(point.open, point.close)); const bottom = model.y(Math.min(point.open, point.close)); return <g key={point.date} className="candle" onMouseEnter={() => setHover({ x, y: top, candle: point })}><line x1={x} x2={x} y1={model.y(point.high)} y2={model.y(point.low)} className={up ? 'wick up' : 'wick down'} /><rect x={x - model.candleWidth / 2} y={top} width={model.candleWidth} height={Math.max(1, bottom - top)} className={up ? 'body up' : 'body down'} /></g>; })}
      {visibleMarkers.map((marker, markerIndex) => { const index = indexByDate.get(marker.pointDate); if (index === undefined) return null; const x = model.x(index); const base = model.y(marker.pointPrice); const isPositive = positive.has(marker.action); const lane = markerIndex % 4; const y = Math.max(chartPadding.top + 10, Math.min(height - chartPadding.bottom - 10, base + (isPositive ? 17 + lane * 10 : -17 - lane * 10))); return <g key={`${marker.id}-${markerIndex}`} className={`trade-pin ${isPositive ? 'positive' : 'negative'}`} tabIndex={0} onMouseEnter={() => { setHover({ x, y, marker }); onMarkerHover?.(marker.id); }} onFocus={() => { setHover({ x, y, marker }); onMarkerHover?.(marker.id); }}><line x1={x} x2={x} y1={base} y2={y} /><path d={isPositive ? `M ${x} ${y - 7} L ${x - 6} ${y + 4} L ${x + 6} ${y + 4} Z` : `M ${x} ${y + 7} L ${x - 6} ${y - 4} L ${x + 6} ${y - 4} Z`} /><circle cx={x} cy={y} r={10} className="pin-hit" /></g>; })}
    </svg>
    {hover?.marker && <div className="candle-tooltip marker" style={{ left: Math.min(width - 282, Math.max(8, hover.x + 12)), top: Math.max(8, hover.y - 105) }}><strong>{hover.marker.actor}</strong><span><b>{actionLabel[hover.marker.action]}</b>{hover.marker.amount}</span><span>交易日期 {hover.marker.occurredAt || '未披露'}</span><span>披露日期 {hover.marker.publishedAt || '未披露'}</span></div>}
    {hover?.candle && !hover.marker && <div className="candle-tooltip" style={{ left: Math.min(width - 220, Math.max(8, hover.x + 10)), top: Math.max(8, hover.y - 92) }}><strong>{hover.candle.date}</strong><span>开 {hover.candle.open.toFixed(2)}　高 {hover.candle.high.toFixed(2)}</span><span>低 {hover.candle.low.toFixed(2)}　收 {hover.candle.close.toFixed(2)}</span></div>}
  </div>;
}
