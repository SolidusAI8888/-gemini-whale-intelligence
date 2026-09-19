'use client';

import { useMemo, useState } from 'react';
import { Activity, CalendarClock, ExternalLink, Search, ShieldCheck, Users } from 'lucide-react';
import { useSiteData } from '@/lib/use-site-data';
import type { ActionPeriod } from '@/lib/site-data';
import type { ActionKind, TradeEvent } from '@/lib/whale-data';
import { CandlestickChart } from '@/components/candlestick-chart';

const positive = new Set<ActionKind>(['BUY', 'NEW', 'ADD']);
const periodOptions: Array<{ value: ActionPeriod; label: string }> = [{ value: 'all', label: '全部年限' }, { value: '1y', label: '一年' }, { value: '6m', label: '半年' }, { value: '3m', label: '三个月' }, { value: '1m', label: '一个月' }];
const periodLabel = (value: ActionPeriod) => periodOptions.find((option) => option.value === value)?.label || '全部年限';

function dateOnly(value: string | null) { return value ? value.slice(0, 10) : '等待更新'; }

function HoldingCard({ event }: { event: TradeEvent }) {
  return <article className="holding-card">
    <div className="holding-avatar">{event.actor.slice(0, 1).toUpperCase()}</div>
    <div><strong>{event.actor}</strong><span>{event.organization || event.role || event.source}</span><small>{event.source} · 截至 {event.publishedAt || event.occurredAt || '最新披露'}</small></div>
    <b>{event.amount}</b>
    {event.sourceUrl && <a href={event.sourceUrl} target="_blank" rel="noreferrer" aria-label="打开原始持仓披露"><ExternalLink size={14} /></a>}
  </article>;
}

export function WhaleDashboard({ initialTicker = '' }: { initialTicker?: string }) {
  const { data, loading, failed } = useSiteData();
  const [selectedTicker, setSelectedTicker] = useState(initialTicker);
  const [assetSort, setAssetSort] = useState<'increase' | 'decrease' | 'holding'>('increase');
  const [increasePeriod, setIncreasePeriod] = useState<ActionPeriod>('all');
  const [decreasePeriod, setDecreasePeriod] = useState<ActionPeriod>('all');
  const [query, setQuery] = useState('');
  const [actionFilter, setActionFilter] = useState<'ALL' | 'POSITIVE' | 'NEGATIVE'>('ALL');
  const [selectedActor, setSelectedActor] = useState<string | null>(null);

  const increaseRanks = useMemo(() => [...data.concentrationPeriods[increasePeriod]].filter((row) => row.increaseEvents > 0).sort((a, b) => b.increaseScore - a.increaseScore || b.increaseAmountUsd - a.increaseAmountUsd), [data.concentrationPeriods, increasePeriod]);
  const decreaseRanks = useMemo(() => [...data.concentrationPeriods[decreasePeriod]].filter((row) => row.decreaseEvents > 0).sort((a, b) => b.decreaseScore - a.decreaseScore || b.decreaseAmountUsd - a.decreaseAmountUsd), [data.concentrationPeriods, decreasePeriod]);
  const holdingRanks = useMemo(() => [...data.holdingConcentration].sort((a, b) => b.score - a.score || b.valueUsd - a.valueUsd), [data.holdingConcentration]);
  const lifetimeEventCounts = useMemo(() => { const counts = new Map<string, number>(); for (const event of data.events) { const ticker = event.ticker === 'GOOGL' ? 'GOOG' : event.ticker; counts.set(ticker, (counts.get(ticker) || 0) + 1); } return counts; }, [data.events]);
  const sortedAssets = useMemo(() => {
    const rows = assetSort === 'increase' ? increaseRanks : assetSort === 'decrease' ? decreaseRanks : holdingRanks;
    const rank = new Map(rows.map((row, index) => [row.ticker === 'GOOGL' ? 'GOOG' : row.ticker, index]));
    return [...data.assets].sort((a, b) => (rank.get(a.ticker) ?? Number.MAX_SAFE_INTEGER) - (rank.get(b.ticker) ?? Number.MAX_SAFE_INTEGER) || a.ticker.localeCompare(b.ticker));
  }, [assetSort, data.assets, decreaseRanks, holdingRanks, increaseRanks]);
  const asset = data.assets.find((item) => item.ticker === selectedTicker) || sortedAssets[0] || data.assets[0];
  const filteredAssets = useMemo(() => { const text = query.trim().toUpperCase(); return text ? sortedAssets.filter((item) => item.ticker.includes(text) || item.name.toUpperCase().includes(text)) : sortedAssets; }, [query, sortedAssets]);
  const allEvents = data.events.filter((event) => event.ticker === asset.ticker);
  const visibleEvents = allEvents.filter((event) => (!selectedActor || event.actor === selectedActor) && (actionFilter === 'ALL' || (actionFilter === 'POSITIVE' ? positive.has(event.action) : !positive.has(event.action))));
  const holdings = data.holdings.filter((event) => event.ticker === asset.ticker);
  const visibleHoldings = selectedActor ? holdings.filter((event) => event.actor === selectedActor) : holdings;
  const actors = [...new Set(allEvents.map((event) => event.actor))].sort((a, b) => a.localeCompare(b));
  const holdingTicker = asset.ticker === 'GOOG' ? 'GOOGL' : asset.ticker;
  const increaseRank = increaseRanks.findIndex((row) => row.ticker === asset.ticker);
  const decreaseRank = decreaseRanks.findIndex((row) => row.ticker === asset.ticker);
  const holdingRank = holdingRanks.findIndex((row) => row.ticker === holdingTicker);
  const increaseRow = increaseRank >= 0 ? increaseRanks[increaseRank] : null;
  const decreaseRow = decreaseRank >= 0 ? decreaseRanks[decreaseRank] : null;
  const holdingRow = holdingRank >= 0 ? holdingRanks[holdingRank] : null;
  const series = asset.priceHistory;
  const markers = series.length ? visibleEvents.flatMap((event) => { const target = event.occurredAt; if (!target || target < series[0].date || target > series[series.length - 1].date) return []; const nearest = series.reduce((best, row) => Math.abs(Date.parse(row.date) - Date.parse(target)) < Math.abs(Date.parse(best.date) - Date.parse(target)) ? row : best, series[0]); return [{ ...event, pointDate: nearest.date, pointPrice: nearest.close }]; }) : [];

  function selectTicker(ticker: string) {
    setSelectedTicker(ticker);
    setSelectedActor(null);
    if (typeof window !== 'undefined') window.history.replaceState({}, '', `/assets/${ticker}`);
  }

  function selectAssetSort(mode: 'increase' | 'decrease' | 'holding') {
    setAssetSort(mode);
    setSelectedTicker('');
    setSelectedActor(null);
    if (typeof window !== 'undefined') window.history.replaceState({}, '', '/');
  }

  function selectPeriod(value: ActionPeriod) {
    if (assetSort === 'increase') setIncreasePeriod(value);
    if (assetSort === 'decrease') setDecreasePeriod(value);
    setSelectedTicker('');
    setSelectedActor(null);
    if (typeof window !== 'undefined') window.history.replaceState({}, '', '/');
  }

  const activePeriod = assetSort === 'increase' ? increasePeriod : decreasePeriod;
  const activeRank = new Map((assetSort === 'increase' ? increaseRanks.map((row, index) => [row.ticker, { index, score: row.increaseScore, count: row.increaseEvents }] as const) : assetSort === 'decrease' ? decreaseRanks.map((row, index) => [row.ticker, { index, score: row.decreaseScore, count: row.decreaseEvents }] as const) : holdingRanks.map((row, index) => [row.ticker, { index, score: row.score, count: lifetimeEventCounts.get(row.ticker === 'GOOGL' ? 'GOOG' : row.ticker) || 0 }] as const)).map(([ticker, value]) => [ticker === 'GOOGL' ? 'GOOG' : ticker, value]));

  return <main className="terminal-shell">
    <header className="terminal-header">
      <div className="terminal-brand"><span><Activity size={17} /></span><div><strong>WHALE INTELLIGENCE</strong><small>只看行动，不看观点</small></div></div>
      <div className="terminal-header-asset"><strong>{asset.ticker}</strong><span>{asset.name}</span><b>{asset.price === null ? '行情待接入' : `$${asset.price.toLocaleString('en-US')}`}</b>{asset.change !== null && <em className={asset.change >= 0 ? 'up' : 'down'}>{asset.change >= 0 ? '+' : ''}{asset.change.toFixed(2)}%</em>}</div>
      <div className="terminal-status"><span className={data.mode === 'production' ? '' : 'sample'} /><div><strong>{data.mode === 'production' ? '生产数据' : '回归样本'}</strong><small>更新 {dateOnly(data.generatedAt)}</small></div></div>
    </header>

    <section className="terminal-workspace">
      <aside className="terminal-left">
        <div className="terminal-left-title"><span>核心标的</span><b>{data.assets.length}</b></div>
        <div className="ticker-sort" aria-label="按集中度排序"><button className={assetSort === 'increase' ? 'active' : ''} onClick={() => selectAssetSort('increase')}>加仓集中度</button><button className={assetSort === 'decrease' ? 'active' : ''} onClick={() => selectAssetSort('decrease')}>减仓集中度</button><button className={assetSort === 'holding' ? 'active' : ''} onClick={() => selectAssetSort('holding')}>持仓集中度</button></div>
        {assetSort !== 'holding' && <div className="ticker-period" aria-label={`${assetSort === 'increase' ? '加仓' : '减仓'}集中度统计周期`}>{periodOptions.map((option) => <button className={activePeriod === option.value ? 'active' : ''} onClick={() => selectPeriod(option.value)} key={option.value}>{option.label}</button>)}</div>}
        <label className="terminal-search"><Search size={14} /><input aria-label="搜索核心标的" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索标的" /></label>
        <nav className="ticker-list" aria-label="核心标的列表">{filteredAssets.map((item) => { const ranked = activeRank.get(item.ticker); return <button aria-label={`查看 ${item.ticker} 价格与巨鲸行动`} className={item.ticker === asset.ticker ? 'selected' : ''} onClick={() => selectTicker(item.ticker)} key={item.ticker}><span><strong>{item.ticker}</strong><small>{item.name}</small></span><span className="ticker-side"><b>{ranked ? `#${ranked.index + 1}` : '—'}</b><small>{ranked ? `${ranked.score} 分 · ${ranked.count} 笔交易` : '暂无排名 · 0 笔交易'}</small></span></button>; })}</nav>
        <div className="terminal-left-foot"><ShieldCheck size={13} /><span>仅收录可验证行动</span></div>
      </aside>

      <section className="terminal-center">
        <div className="chart-toolbar">
          <div><p>PRICE × VERIFIED ACTIONS</p><h1>{asset.ticker} 价格行动图</h1></div>
          <div className="toolbar-controls"><span className="trade-date-mode">按交易发生日打点</span></div>
        </div>
        <div className="market-strip"><div><small>现价</small><strong>{asset.price === null ? '—' : `$${asset.price.toLocaleString('en-US')}`}</strong></div><div><small>今日涨跌</small><strong className={(asset.change || 0) >= 0 ? 'up' : 'down'}>{asset.change === null ? '—' : `${asset.change >= 0 ? '+' : ''}${asset.change.toFixed(2)}%`}</strong></div><div><small>日线蜡烛</small><strong>{series.length ? `${series.length} 日` : '待接入'}</strong></div><div><small>可验证行动</small><strong>{allEvents.length} 条</strong></div><span>{loading ? '正在读取最新数据…' : failed ? '数据读取失败' : `${series[0]?.date || '—'} → ${series.at(-1)?.date || '—'}`}</span></div>
        <div className="chart-filter-row"><div className="action-legend"><span><i className="buy" />买入/新建</span><span><i className="add" />加仓</span><span><i className="sell" />卖出/减仓</span><span><i className="exit" />清仓</span></div><div className="segmented compact"><button className={actionFilter === 'ALL' ? 'active' : ''} onClick={() => setActionFilter('ALL')}>全部</button><button className={actionFilter === 'POSITIVE' ? 'active' : ''} onClick={() => setActionFilter('POSITIVE')}>买入</button><button className={actionFilter === 'NEGATIVE' ? 'active' : ''} onClick={() => setActionFilter('NEGATIVE')}>卖出</button></div></div>
        <div className="terminal-chart">{series.length > 1 ? <CandlestickChart series={series} markers={markers} /> : <div className="terminal-chart-empty"><CalendarClock size={30} /><strong>暂无可验证历史价格</strong><p>不会使用模拟曲线。真实行情接入后，巨鲸行动会自动钉在对应日期。</p></div>}</div>
        <footer className="chart-footnote"><ShieldCheck size={14} /><span>图表严格按实际交易日期定位；披露日期与披露延迟仍保留在悬停详情中，不把晚披露误画成交易发生日。</span></footer>
      </section>

      <aside className="terminal-right">
        <div className="right-topbar"><a href="/whales"><Users size={15} /><span>巨鲸池</span><b>→</b></a></div>
        <div className="asset-rank-strip"><a href="/analysis#increase"><small>建仓 / 加仓 · {periodLabel(increasePeriod)}</small><strong>{increaseRank >= 0 ? `#${increaseRank + 1}` : '—'}</strong><span>{increaseRow ? `${increaseRow.increaseScore} 分 · ${increaseRow.increaseEvents} 笔` : '暂无有效行动'}</span></a><a href="/analysis#decrease"><small>减仓 / 清仓 · {periodLabel(decreasePeriod)}</small><strong>{decreaseRank >= 0 ? `#${decreaseRank + 1}` : '—'}</strong><span>{decreaseRow ? `${decreaseRow.decreaseScore} 分 · ${decreaseRow.decreaseEvents} 笔` : '暂无有效行动'}</span></a><a href="/analysis#holding"><small>持仓集中度</small><strong>{holdingRank >= 0 ? `#${holdingRank + 1}` : '—'}</strong><span>{holdingRow ? `${holdingRow.score} 分 / ${holdingRanks.length} 标的` : '暂无持仓快照'}</span></a></div>
        <div className="actor-filter"><div><strong>图表巨鲸筛选</strong><small>选择后只显示该主体的交易点</small></div><div className="actor-filter-list"><button className={!selectedActor ? 'active' : ''} onClick={() => setSelectedActor(null)}>全部</button>{actors.map((actor) => <button className={selectedActor === actor ? 'active' : ''} onClick={() => setSelectedActor(actor)} title={actor} key={actor}><i>{actor.slice(0, 1)}</i>{actor}</button>)}</div></div>
        <section className="holding-snapshot"><div className="right-heading"><div><strong>{asset.ticker} 巨鲸持仓</strong><small>最新可见正式披露快照，不重复展示图中的交易流水</small></div><span>{visibleHoldings.length} 位</span></div><div className="right-scroll">{visibleHoldings.length ? visibleHoldings.map((event) => <HoldingCard event={event} key={`holding-${event.id}`} />) : <div className="right-empty"><ShieldCheck size={24} /><strong>{selectedActor ? '该巨鲸暂无当前持仓快照' : '暂无当前持仓快照'}</strong><p>交易点仍可在价格图上按所选巨鲸筛选。</p></div>}</div></section>
      </aside>
    </section>
  </main>;
}
