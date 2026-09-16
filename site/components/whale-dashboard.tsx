'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { Activity, ArrowDownRight, ArrowUpRight, Building2, Clock3, DatabaseZap, Landmark, Search, ShieldCheck } from 'lucide-react';
import { Line, LineChart } from 'recharts';
import { concentration, coreAssets, tradeEvents, type ActionKind } from '@/lib/whale-data';

const actionMeta: Record<ActionKind, { label: string; className: string }> = {
  BUY: { label: '买入', className: 'action-add' }, SELL: { label: '卖出', className: 'action-reduce' },
  NEW: { label: '新建仓', className: 'action-new' }, ADD: { label: '加仓', className: 'action-add' },
  REDUCE: { label: '减仓', className: 'action-reduce' }, EXIT: { label: '清仓', className: 'action-exit' },
};

function MiniSpark({ values, positive }: { values: number[]; positive: boolean }) {
  const data = values.map((value, index) => ({ index, value }));
  return <LineChart width={105} height={28} data={data} margin={{ top: 2, right: 1, bottom: 2, left: 1 }}><Line type="monotone" dataKey="value" stroke={positive ? '#42d7a4' : '#ff6b6b'} strokeWidth={1.8} dot={false} isAnimationActive={false} /></LineChart>;
}

function Brand() {
  return <div className="brand-lockup"><span className="brand-mark"><Activity size={18} /></span><span><strong>WHALE</strong><em>INTELLIGENCE</em></span></div>;
}

export function WhaleDashboard() {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<'ALL' | ActionKind>('ALL');
  const assets = useMemo(() => {
    const q = query.trim().toUpperCase();
    return q ? coreAssets.filter((asset) => asset.ticker.includes(q) || asset.name.toUpperCase().includes(q)) : coreAssets;
  }, [query]);
  const events = filter === 'ALL' ? tradeEvents : tradeEvents.filter((event) => event.action === filter);

  return <main className="app-shell">
    <header className="topbar">
      <Brand />
      <nav aria-label="主导航"><a className="active" href="#overview">行动雷达</a><a href="#core-assets">核心标的</a><a href="#concentration">集中度</a><a href="#evidence">证据库</a></nav>
      <div className="freshness"><span /> 数据截至 2026-09-16</div>
    </header>

    <section className="control-deck" id="overview">
      <div><p className="eyebrow">ACTION-ONLY MARKET INTELLIGENCE</p><h1>巨鲸做了什么，市场何时知道</h1><p className="subhead">只展示可验证交易与持仓变化。机构行为、个人行为、配偶及关联账户严格分开。</p></div>
      <div className="status-cards" aria-label="数据状态">
        <div><ShieldCheck size={17} /><span><b>A/B</b>证据门槛</span></div>
        <div><Clock3 size={17} /><span><b>25天</b>样本披露延迟</span></div>
        <div><DatabaseZap size={17} /><span><b>21</b>核心标的</span></div>
      </div>
    </section>

    <section className="workspace-grid">
      <section className="panel asset-panel" id="core-assets">
        <div className="panel-heading"><div><p className="kicker">CORE UNIVERSE</p><h2>核心标的</h2></div><label className="searchbox"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索代码" /></label></div>
        <div className="asset-grid">{assets.map((asset) => <Link className="asset-card" href={`/assets/${asset.ticker}`} key={asset.ticker}>
          <div className="asset-top"><span className="ticker">{asset.ticker}</span><span className="signal-count">{asset.signals} 条行动</span></div>
          <p>{asset.name}</p><div className="asset-metrics"><strong>{asset.kind === 'Crypto' ? '$' : ''}{asset.price.toLocaleString('en-US')}</strong><span className={asset.change >= 0 ? 'up' : 'down'}>{asset.change >= 0 ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}{Math.abs(asset.change).toFixed(2)}%</span></div>
          <div className="spark"><MiniSpark values={asset.spark} positive={asset.change >= 0} /></div>
        </Link>)}</div>
      </section>

      <aside className="panel concentration-panel" id="concentration">
        <div className="panel-heading compact"><div><p className="kicker">CROSS-GROUP</p><h2>行动集中度</h2></div><span className="window-pill">90D</span></div>
        <p className="panel-note">证据可靠度、独立主体数、披露新鲜度与跨群体一致性的综合排序。</p>
        <div className="rank-list">{concentration.map((row, index) => <Link href={`/assets/${row.ticker}`} className="rank-row" key={row.ticker}>
          <span className="rank">0{index + 1}</span><div><strong>{row.ticker}</strong><small>{row.buyers} 个主体 · {row.groups} 类群体</small></div><div className="score"><b>{row.score}</b><small>{row.net}</small></div><span className="score-bar"><i style={{ width: `${row.score}%` }} /></span>
        </Link>)}</div>
        <div className="method-strip"><ShieldCheck size={16} /><span>言论、传闻和无法验证的媒体推断不计分</span></div>
      </aside>
    </section>

    <section className="panel evidence-panel" id="evidence">
      <div className="panel-heading evidence-heading"><div><p className="kicker">VERIFIED ACTIONS</p><h2>最新可验证行动</h2></div><fieldset className="filter-row" aria-label="行动筛选">
        {(['ALL', 'BUY', 'SELL', 'NEW', 'ADD', 'REDUCE', 'EXIT'] as const).map((item) => <button className={filter === item ? 'selected' : ''} onClick={() => setFilter(item)} key={item}>{item === 'ALL' ? '全部' : actionMeta[item].label}</button>)}
      </fieldset></div>
      <div className="evidence-table-wrap"><table className="evidence-table"><thead><tr><th>公开日期</th><th>标的 / 行动</th><th>实际交易主体</th><th>关联机构 / 身份</th><th>金额 / 工具</th><th>披露延迟</th><th>证据</th></tr></thead><tbody>
        {events.map((event) => <tr key={event.id}>
          <td><strong>{event.publishedAt}</strong><small>发生 {event.occurredAt}</small></td>
          <td><Link href={`/assets/${event.ticker}`} className="event-ticker">{event.ticker}</Link><span className={`action-tag ${actionMeta[event.action].className}`}>{actionMeta[event.action].label}</span></td>
          <td><strong>{event.actor}</strong><small>{event.instrument}</small></td>
          <td><span className="identity"><Landmark size={14} />{event.organization}</span><small>{event.role}</small></td>
          <td><strong>{event.amount}</strong><small>{event.source}</small></td><td><span className="lag"><Clock3 size={14} />{event.lagDays} 天</span></td><td><span className={`evidence-grade grade-${event.evidence.toLowerCase()}`}>{event.evidence}</span></td>
        </tr>)}
      </tbody></table></div>
      <footer className="table-footer"><span><Building2 size={14} />机构申报只归因于机构；关键岗位人员不会被错误标记为个人买入。</span><span>产品预览 · 使用历史回归样本</span></footer>
    </section>
  </main>;
}
