'use client';

import { useMemo, useState } from 'react';
import { Activity, BarChart3, CalendarClock, ExternalLink, Search, ShieldCheck, TrendingDown, TrendingUp } from 'lucide-react';
import { useSiteData } from '@/lib/use-site-data';
import type { ActionKind, TradeEvent } from '@/lib/whale-data';
import { CandlestickChart } from '@/components/candlestick-chart';

const labels: Record<ActionKind, string> = { BUY: '买入', SELL: '卖出', NEW: '新建仓', ADD: '加仓', REDUCE: '减仓', EXIT: '清仓' };
const colors: Record<ActionKind, string> = { BUY: '#12b886', SELL: '#f59f00', NEW: '#12b886', ADD: '#228be6', REDUCE: '#f59f00', EXIT: '#fa5252' };
const positive = new Set<ActionKind>(['BUY', 'NEW', 'ADD']);

function dateOnly(value: string | null) { return value ? value.slice(0, 10) : '等待更新'; }

function EventCard({ event, highlighted = false }: { event: TradeEvent; highlighted?: boolean }) {
  const isPositive = positive.has(event.action);
  return <article id={`event-${event.id}`} className={`terminal-event ${isPositive ? 'positive' : 'negative'} ${highlighted ? 'highlighted' : ''}`}>
    <div className="terminal-event-head"><time>{event.publishedAt || event.occurredAt || '日期未知'}</time><span style={{ color: colors[event.action] }}>{labels[event.action]}</span></div>
    <div className="terminal-event-title"><span className="event-direction">{isPositive ? <TrendingUp size={15} /> : <TrendingDown size={15} />}</span><strong>{event.actor}</strong><b>{event.amount}</b></div>
    <p>{event.organization || event.role || event.source}</p>
    <div className="terminal-event-meta"><span>发生 {event.occurredAt || '未披露'}</span><span>延迟 {event.lagDays === null ? '未知' : `${event.lagDays}天`}</span><em>{event.evidence}级证据</em>{event.sourceUrl && <a href={event.sourceUrl} target="_blank" rel="noreferrer" aria-label="打开原始披露"><ExternalLink size={13} /></a>}</div>
  </article>;
}

export function WhaleDashboard({ initialTicker = 'UBER' }: { initialTicker?: string }) {
  const { data, loading, failed } = useSiteData();
  const [selectedTicker, setSelectedTicker] = useState(initialTicker);
  const [query, setQuery] = useState('');
  const [timeMode, setTimeMode] = useState<'PUBLIC' | 'OCCURRED'>('PUBLIC');
  const [actionFilter, setActionFilter] = useState<'ALL' | 'POSITIVE' | 'NEGATIVE'>('ALL');
  const [rightTab, setRightTab] = useState<'EVENTS' | 'HOLDINGS'>('EVENTS');
  const [hoveredEvent, setHoveredEvent] = useState<string | null>(null);

  const asset = data.assets.find((item) => item.ticker === selectedTicker) || data.assets[0];
  const filteredAssets = useMemo(() => { const text = query.trim().toUpperCase(); return text ? data.assets.filter((item) => item.ticker.includes(text) || item.name.toUpperCase().includes(text)) : data.assets; }, [data.assets, query]);
  const allEvents = data.events.filter((event) => event.ticker === asset.ticker);
  const visibleEvents = allEvents.filter((event) => actionFilter === 'ALL' || (actionFilter === 'POSITIVE' ? positive.has(event.action) : !positive.has(event.action)));
  const holdings = data.holdings.filter((event) => event.ticker === asset.ticker);
  const series = asset.priceHistory;
  const markers = series.length ? visibleEvents.flatMap((event) => { const target = timeMode === 'PUBLIC' ? event.publishedAt : event.occurredAt; if (!target || target < series[0].date || target > series[series.length - 1].date) return []; const nearest = series.reduce((best, row) => Math.abs(Date.parse(row.date) - Date.parse(target)) < Math.abs(Date.parse(best.date) - Date.parse(target)) ? row : best, series[0]); return [{ ...event, pointDate: nearest.date, pointPrice: nearest.close }]; }) : [];

  function selectTicker(ticker: string) {
    setSelectedTicker(ticker);
    if (typeof window !== 'undefined') window.history.replaceState({}, '', `/assets/${ticker}`);
  }

  return <main className="terminal-shell">
    <header className="terminal-header">
      <div className="terminal-brand"><span><Activity size={17} /></span><div><strong>WHALE INTELLIGENCE</strong><small>只看行动，不看观点</small></div></div>
      <div className="terminal-header-asset"><strong>{asset.ticker}</strong><span>{asset.name}</span><b>{asset.price === null ? '行情待接入' : `$${asset.price.toLocaleString('en-US')}`}</b>{asset.change !== null && <em className={asset.change >= 0 ? 'up' : 'down'}>{asset.change >= 0 ? '+' : ''}{asset.change.toFixed(2)}%</em>}</div>
      <div className="terminal-status"><span className={data.mode === 'production' ? '' : 'sample'} /><div><strong>{data.mode === 'production' ? '生产数据' : '回归样本'}</strong><small>更新 {dateOnly(data.generatedAt)}</small></div></div>
    </header>

    <section className="terminal-workspace">
      <aside className="terminal-left">
        <a className="analysis-entry" href="/analysis"><BarChart3 size={16} /><span><strong>集中度分析</strong><small>行动 × 持仓交叉视图</small></span><b>→</b></a>
        <div className="terminal-left-title"><span>核心标的</span><b>{data.assets.length}</b></div>
        <label className="terminal-search"><Search size={14} /><input aria-label="搜索核心标的" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索标的" /></label>
        <nav className="ticker-list" aria-label="核心标的列表">{filteredAssets.map((item) => <button aria-label={`查看 ${item.ticker} 价格与巨鲸行动`} className={item.ticker === asset.ticker ? 'selected' : ''} onClick={() => selectTicker(item.ticker)} key={item.ticker}><span><strong>{item.ticker}</strong><small>{item.name}</small></span><span className="ticker-side"><b>{item.signals}</b><small>{item.kind}</small></span></button>)}</nav>
        <div className="terminal-left-foot"><ShieldCheck size={13} /><span>仅收录可验证行动</span></div>
      </aside>

      <section className="terminal-center">
        <div className="chart-toolbar">
          <div><p>PRICE × VERIFIED ACTIONS</p><h1>{asset.ticker} 价格行动图</h1></div>
          <div className="toolbar-controls"><div className="segmented"><button className={timeMode === 'PUBLIC' ? 'active' : ''} onClick={() => setTimeMode('PUBLIC')}>公众获知日</button><button className={timeMode === 'OCCURRED' ? 'active' : ''} onClick={() => setTimeMode('OCCURRED')}>交易发生日</button></div></div>
        </div>
        <div className="market-strip"><div><small>现价</small><strong>{asset.price === null ? '—' : `$${asset.price.toLocaleString('en-US')}`}</strong></div><div><small>今日涨跌</small><strong className={(asset.change || 0) >= 0 ? 'up' : 'down'}>{asset.change === null ? '—' : `${asset.change >= 0 ? '+' : ''}${asset.change.toFixed(2)}%`}</strong></div><div><small>日线蜡烛</small><strong>{series.length ? `${series.length} 日` : '待接入'}</strong></div><div><small>可验证行动</small><strong>{allEvents.length} 条</strong></div><span>{loading ? '正在读取最新数据…' : failed ? '数据读取失败' : `${series[0]?.date || '—'} → ${series.at(-1)?.date || '—'}`}</span></div>
        <div className="chart-filter-row"><div className="action-legend"><span><i className="buy" />买入/新建</span><span><i className="add" />加仓</span><span><i className="sell" />卖出/减仓</span><span><i className="exit" />清仓</span></div><div className="segmented compact"><button className={actionFilter === 'ALL' ? 'active' : ''} onClick={() => setActionFilter('ALL')}>全部</button><button className={actionFilter === 'POSITIVE' ? 'active' : ''} onClick={() => setActionFilter('POSITIVE')}>买入</button><button className={actionFilter === 'NEGATIVE' ? 'active' : ''} onClick={() => setActionFilter('NEGATIVE')}>卖出</button></div></div>
        <div className="terminal-chart">{series.length > 1 ? <CandlestickChart series={series} markers={markers} onMarkerHover={(id) => { setHoveredEvent(id); if (id) setRightTab('EVENTS'); }} /> : <div className="terminal-chart-empty"><CalendarClock size={30} /><strong>暂无可验证历史价格</strong><p>不会使用模拟曲线。真实行情接入后，巨鲸行动会自动钉在对应日期。</p></div>}</div>
        <footer className="chart-footnote"><ShieldCheck size={14} /><span>{timeMode === 'PUBLIC' ? '当前为可跟随视图：行动只在披露公开后出现，避免回看偏差。' : '当前为事实回溯视图：展示实际交易日期，不代表当时公众已经知情。'}</span></footer>
      </section>

      <aside className="terminal-right">
        <div className="right-tabs"><button className={rightTab === 'EVENTS' ? 'active' : ''} onClick={() => setRightTab('EVENTS')}>行动流水 <b>{allEvents.length}</b></button><button className={rightTab === 'HOLDINGS' ? 'active' : ''} onClick={() => setRightTab('HOLDINGS')}>当前持仓 <b>{holdings.length}</b></button></div>
        <div className="right-heading"><div><strong>{asset.ticker} 巨鲸行动</strong><small>{rightTab === 'EVENTS' ? '按公开日期倒序 · 点击证据图标查看原始披露' : '最新可见申报快照 · 不等于当天交易'}</small></div><span>{timeMode === 'PUBLIC' ? '可跟随' : '回溯'}</span></div>
        <div className="right-scroll">{rightTab === 'EVENTS' ? (visibleEvents.length ? visibleEvents.map((event) => <EventCard event={event} highlighted={hoveredEvent === event.id} key={event.id} />) : <div className="right-empty"><ShieldCheck size={24} /><strong>暂无通过证据门的行动</strong><p>不使用观点、传闻或推测填充。</p></div>) : (holdings.length ? holdings.map((event) => <EventCard event={event} key={`holding-${event.id}`} />) : <div className="right-empty"><ShieldCheck size={24} /><strong>暂无当前持仓快照</strong><p>只有通过质量校验的正式披露才会显示。</p></div>)}</div>
      </aside>
    </section>
  </main>;
}
