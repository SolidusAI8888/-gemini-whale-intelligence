'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, Building2, CalendarClock, ExternalLink, ShieldCheck, Users } from 'lucide-react';
import { CartesianGrid, Line, LineChart, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { coreAssets, tradeEvents, type ActionKind, type CoreAsset } from '@/lib/whale-data';

const dates = ['2026-02-02','2026-02-16','2026-03-02','2026-03-18','2026-04-01','2026-04-15','2026-05-01','2026-05-15','2026-05-29','2026-06-12','2026-06-23','2026-07-15','2026-08-15','2026-09-16'];
const actionLabels: Record<ActionKind, string> = { BUY: '买入', SELL: '卖出', NEW: '新建仓', ADD: '加仓', REDUCE: '减仓', EXIT: '清仓' };
const actionColors: Record<ActionKind, string> = { BUY: '#42d7a4', SELL: '#ff9f43', NEW: '#42d7a4', ADD: '#58d6e7', REDUCE: '#ff9f43', EXIT: '#ff6b6b' };

function interpolate(values: number[], index: number, length: number) {
  const position = (index / Math.max(1, length - 1)) * (values.length - 1);
  const left = Math.floor(position); const right = Math.min(values.length - 1, Math.ceil(position));
  const mix = position - left;
  return values[left] * (1 - mix) + values[right] * mix;
}

function buildPriceSeries(asset: CoreAsset) {
  const end = asset.price; const last = asset.spark.at(-1) || 1;
  return dates.map((date, index) => ({ date, price: Number(((interpolate(asset.spark, index, dates.length) / last) * end).toFixed(2)) }));
}

export function AssetDetail({ ticker }: { ticker: string }) {
  const asset = coreAssets.find((item) => item.ticker === ticker) || coreAssets[0];
  const [mode, setMode] = useState<'PUBLIC' | 'OCCURRED'>('PUBLIC');
  const events = tradeEvents.filter((event) => event.ticker === asset.ticker);
  const series = useMemo(() => buildPriceSeries(asset), [asset]);
  const markerEvents = events.map((event) => {
    const target = mode === 'PUBLIC' ? event.publishedAt : event.occurredAt;
    const nearest = series.reduce((best, row) => Math.abs(Date.parse(row.date) - Date.parse(target)) < Math.abs(Date.parse(best.date) - Date.parse(target)) ? row : best, series[0]);
    return { ...event, pointDate: nearest.date, pointPrice: nearest.price };
  });
  const owners = new Set(events.map((event) => event.actor)).size;
  const institutions = new Set(events.map((event) => event.organization)).size;

  return <main className="asset-page">
    <header className="asset-header">
      <Link href="/" className="back-link"><ArrowLeft size={15} />返回行动雷达</Link>
      <div className="asset-header-note"><ShieldCheck size={14} />只展示可核验行动</div>
    </header>
    <section className="asset-hero">
      <div><p className="eyebrow">CORE ASSET / {asset.kind.toUpperCase()}</p><div className="asset-title"><h1>{asset.ticker}</h1><span>{asset.name}</span></div><p>价格走势与政界、机构和公司内部人的真实行动叠加。默认按公众首次可获知日期展示。</p></div>
      <div className="asset-price"><strong>{asset.kind === 'Crypto' ? '$' : ''}{asset.price.toLocaleString('en-US')}</strong><span className={asset.change >= 0 ? 'up' : 'down'}>{asset.change >= 0 ? '+' : ''}{asset.change.toFixed(2)}%</span></div>
    </section>

    <section className="asset-layout">
      <section className="panel chart-panel">
        <div className="panel-heading chart-heading"><div><p className="kicker">PRICE × VERIFIED ACTIONS</p><h2>价格行动时间轴</h2></div><fieldset className="time-mode" aria-label="时间轴模式"><button className={mode === 'PUBLIC' ? 'selected' : ''} onClick={() => setMode('PUBLIC')}>公众获知日</button><button className={mode === 'OCCURRED' ? 'selected' : ''} onClick={() => setMode('OCCURRED')}>交易发生日</button></fieldset></div>
        <div className="bias-notice"><CalendarClock size={16} /><span>{mode === 'PUBLIC' ? '可跟随视图：事件只在披露公开后出现，避免回看偏差。' : '事实回溯视图：用于研究真实发生时间，不代表当时公众已经知情。'}</span></div>
        <div className="main-chart">
          <ResponsiveContainer width="100%" height="100%"><LineChart data={series} margin={{ top: 18, right: 24, bottom: 10, left: 2 }}>
            <CartesianGrid vertical={false} stroke="rgba(145,182,204,.10)" />
            <XAxis dataKey="date" tick={{ fill: '#6f8796', fontSize: 9 }} tickLine={false} axisLine={false} minTickGap={38} />
            <YAxis domain={['dataMin - 5', 'dataMax + 5']} orientation="right" tick={{ fill: '#6f8796', fontSize: 9 }} tickLine={false} axisLine={false} width={52} />
            <Tooltip contentStyle={{ background: '#0a1722', border: '1px solid rgba(145,182,204,.18)', borderRadius: 8, fontSize: 10 }} labelStyle={{ color: '#7891a1' }} formatter={(value) => [String(value), 'Price']} />
            <Line type="monotone" dataKey="price" stroke="#58d6e7" strokeWidth={2.2} dot={false} isAnimationActive={false} />
            {markerEvents.map((event) => <ReferenceDot key={event.id} x={event.pointDate} y={event.pointPrice} r={6} fill={actionColors[event.action]} stroke="#061019" strokeWidth={3} />)}
          </LineChart></ResponsiveContainer>
        </div>
        <div className="chart-legend"><span><i className="new-dot" />买入/新建</span><span><i className="add-dot" />确认加仓</span><span><i className="reduce-dot" />卖出/减仓</span><span><i className="exit-dot" />确认清仓</span></div>
      </section>

      <aside className="asset-sidebar">
        <section className="panel asset-stat-panel"><div><Users size={16} /><span>独立行动主体</span><strong>{owners}</strong></div><div><Building2 size={16} /><span>关联机构</span><strong>{institutions}</strong></div><div><CalendarClock size={16} /><span>最长披露延迟</span><strong>{events.length ? Math.max(...events.map((e) => e.lagDays)) : 0}天</strong></div></section>
        <section className="panel source-policy"><p className="kicker">ATTRIBUTION RULE</p><h2>归因规则</h2><p>个人申报归于实际交易人；机构 13F 归于申报机构。董事长、CEO、CFO、CIO 等关键岗位仅作为关系信息，不会被误写为个人交易。</p></section>
      </aside>
    </section>

    <section className="panel asset-events">
      <div className="panel-heading"><div><p className="kicker">EVIDENCE LEDGER</p><h2>{asset.ticker} 行动证据</h2></div><span className="window-pill">{events.length} 条记录</span></div>
      {events.length ? <div className="asset-event-list">{events.map((event) => <article key={event.id}>
        <div className="event-action" style={{ color: actionColors[event.action] }}>{actionLabels[event.action]}</div>
        <div><strong>{event.actor}</strong><p>{event.organization} · {event.role}</p></div>
        <div><strong>{event.amount}</strong><p>{event.instrument}</p></div>
        <div><strong>发生 {event.occurredAt}</strong><p>公开 {event.publishedAt} · 延迟 {event.lagDays} 天</p></div>
        <div><span className={`evidence-grade grade-${event.evidence.toLowerCase()}`}>{event.evidence}</span><button title="原始来源将在正式数据接入后打开"><ExternalLink size={14} /></button></div>
      </article>)}</div> : <div className="empty-ledger"><ShieldCheck size={24} /><strong>暂无通过证据门的行动记录</strong><p>不会用观点、传闻或无法验证的媒体推断填充空白。</p></div>}
    </section>
  </main>;
}
