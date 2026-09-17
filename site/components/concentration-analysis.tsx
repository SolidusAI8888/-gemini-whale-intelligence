'use client';

import { useMemo, useState } from 'react';
import { Activity, ArrowLeft, Building2, ExternalLink, Network, ShieldCheck, Users } from 'lucide-react';
import { formatMoney } from '@/lib/site-data';
import { useSiteData } from '@/lib/use-site-data';
import type { TradeEvent } from '@/lib/whale-data';

type Detail = { ticker: string; mode: 'increase' | 'decrease' | 'holding' } | null;
const positive = new Set(['BUY', 'NEW', 'ADD']);
const negative = new Set(['SELL', 'REDUCE', 'EXIT']);
const labels: Record<string, string> = { BUY: '买入', NEW: '新建仓', ADD: '加仓', SELL: '卖出', REDUCE: '减仓', EXIT: '清仓' };

function SourceList({ names }: { names: string[] }) {
  const label = names.length ? names.join(' · ') : '未标注';
  return <span className="source-list" title={label}>{label}</span>;
}

function DetailLedger({ detail, events, holdings }: { detail: NonNullable<Detail>; events: TradeEvent[]; holdings: TradeEvent[] }) {
  const rows = detail.mode === 'holding' ? holdings.filter((event) => event.ticker === detail.ticker) : events.filter((event) => event.ticker === detail.ticker && (detail.mode === 'increase' ? positive.has(event.action) : negative.has(event.action)));
  return <section className="analysis-detail" id="concentration-detail">
    <header><div><p>VERIFIABLE DETAIL</p><h2>{detail.ticker} · {detail.mode === 'holding' ? '当前持有人与仓位' : detail.mode === 'increase' ? '新建仓 / 加仓明细' : '减仓 / 清仓明细'}</h2></div><b>{rows.length} 条正式披露</b></header>
    <div className="detail-head"><span>主体</span><span>方向 / 仓位</span><span>金额</span><span>发生 / 披露日期</span><span>披露来源</span></div>
    {rows.length ? rows.map((event) => <article className="detail-row" key={`${detail.mode}-${event.id}`}><span><strong>{event.actor}</strong><small>{event.organization || event.role || '正式申报主体'}</small></span><span><b className={positive.has(event.action) ? 'up' : 'down'}>{detail.mode === 'holding' ? '持仓快照' : labels[event.action]}</b><small>{event.instrument}</small></span><span><strong>{event.amount}</strong></span><span><strong>{event.occurredAt || '未披露'}</strong><small>公开 {event.publishedAt || '未披露'}</small></span><span><strong>{event.source}</strong>{event.sourceUrl && <a href={event.sourceUrl} target="_blank" rel="noreferrer" aria-label="查看原始披露"><ExternalLink size={14} /></a>}</span></article>) : <div className="detail-empty">当前筛选下没有可验证记录。</div>}
  </section>;
}

export function ConcentrationAnalysis() {
  const { data } = useSiteData();
  const [detail, setDetail] = useState<Detail>(null);
  const increase = useMemo(() => [...data.concentration].filter((row) => row.increaseEvents > 0).sort((a, b) => b.increaseScore - a.increaseScore || b.increaseAmountUsd - a.increaseAmountUsd), [data.concentration]);
  const decrease = useMemo(() => [...data.concentration].filter((row) => row.decreaseEvents > 0).sort((a, b) => b.decreaseScore - a.decreaseScore || b.decreaseAmountUsd - a.decreaseAmountUsd), [data.concentration]);
  const holdings = useMemo(() => [...data.holdingConcentration].sort((a, b) => b.score - a.score || b.valueUsd - a.valueUsd), [data.holdingConcentration]);
  const openDetail = (next: NonNullable<Detail>) => { setDetail(next); requestAnimationFrame(() => document.getElementById('concentration-detail')?.scrollIntoView({ behavior: 'smooth', block: 'start' })); };
  return <main className="analysis-page">
    <header className="analysis-header"><a href="/"><ArrowLeft size={17} />返回标的工作台</a><div className="terminal-brand"><span><Activity size={18} /></span><div><strong>WHALE INTELLIGENCE</strong><small>集中度分析</small></div></div><span className="analysis-live"><i />生产数据</span></header>
    <section className="analysis-hero"><p>CONCENTRATION INTELLIGENCE</p><h1>政商巨鲸行动与持仓集中度</h1><span>买入侧、卖出侧与持仓侧独立排名。每一行均可展开到底层申报主体、金额、日期和原始证据。</span></section>
    <section className="analysis-summary"><div><Users size={20} /><span>买入侧覆盖标的<strong>{increase.length}</strong></span></div><div><Building2 size={20} /><span>卖出侧覆盖标的<strong>{decrease.length}</strong></span></div><div><Network size={20} /><span>持仓覆盖标的<strong>{holdings.length}</strong></span></div><div><ShieldCheck size={20} /><span>可验证行动<strong>{data.events.length}</strong></span></div></section>
    <section className="analysis-grid three-panels">
      <article className="analysis-panel"><header><div><p>INCREASE CONCENTRATION</p><h2>新建仓 / 加仓</h2></div><span>全部 {increase.length}</span></header><div className="analysis-table-head"><span>排名 / 标的</span><span>主体</span><span>披露来源</span><span>买入金额</span><span>评分</span></div>{increase.map((row, index) => <button className="analysis-row" onClick={() => openDetail({ ticker: row.ticker, mode: 'increase' })} key={row.ticker}><span className="analysis-rank">{String(index + 1).padStart(2, '0')}<strong>{row.ticker}</strong></span><span>{row.increaseActors}</span><SourceList names={row.increaseSources} /><span>{formatMoney(row.increaseAmountUsd)}</span><span className="analysis-score"><b>{row.increaseScore}</b><i><em style={{ width: `${row.increaseScore}%` }} /></i></span></button>)}</article>
      <article className="analysis-panel"><header><div><p>DECREASE CONCENTRATION</p><h2>减仓 / 清仓</h2></div><span>全部 {decrease.length}</span></header><div className="analysis-table-head"><span>排名 / 标的</span><span>主体</span><span>披露来源</span><span>卖出金额</span><span>评分</span></div>{decrease.map((row, index) => <button className="analysis-row" onClick={() => openDetail({ ticker: row.ticker, mode: 'decrease' })} key={row.ticker}><span className="analysis-rank">{String(index + 1).padStart(2, '0')}<strong>{row.ticker}</strong></span><span>{row.decreaseActors}</span><SourceList names={row.decreaseSources} /><span>{formatMoney(row.decreaseAmountUsd)}</span><span className="analysis-score"><b>{row.decreaseScore}</b><i><em className="negative-bar" style={{ width: `${row.decreaseScore}%` }} /></i></span></button>)}</article>
      <article className="analysis-panel"><header><div><p>HOLDING CONCENTRATION</p><h2>当前披露持仓</h2></div><span>全部 {holdings.length}</span></header><div className="analysis-table-head holding"><span>排名 / 标的</span><span>持有人</span><span>披露来源</span><span>申报价值</span><span>评分</span></div>{holdings.map((row, index) => <button className="analysis-row holding" onClick={() => openDetail({ ticker: row.ticker, mode: 'holding' })} key={row.ticker}><span className="analysis-rank">{String(index + 1).padStart(2, '0')}<strong>{row.ticker}</strong></span><span>{row.holderCount}</span><SourceList names={row.sourceNames} /><span>{formatMoney(row.valueUsd)}</span><span className="analysis-score"><b>{row.score}</b><i><em style={{ width: `${row.score}%` }} /></i></span></button>)}</article>
    </section>
    {detail && <DetailLedger detail={detail} events={data.events} holdings={data.holdings} />}
    <section className="methodology">
      <article><h2>行动集中度评分（0–100）</h2><p>买入侧与卖出侧分别计算，不再混成一个净值。主体广度占 35%，正式披露来源多样性占 20%，披露金额的对数相对规模占 20%，证据等级占 15%，行动记录数量占 10%。各项均相对本期全体标的归一化，因此只有真正领先的标的接近 100，避免旧公式大面积封顶。</p></article>
      <article><h2>持仓集中度评分（0–100）</h2><p>独立持有人数量占 45%，披露来源多样性占 15%，可验证仓位记录数量占 15%，申报价值的对数相对规模占 25%。13F 代表申报期末快照而非即时成交，不把它误称为当天买卖。</p></article>
      <article><h2>“披露来源”是什么意思？</h2><p>页面直接展示名称：Congress PTR 为美国国会议员交易披露；OGE 为行政部门伦理财务披露；SEC Form 4 为公司内部人交易；SEC 13F 为机构季度持仓。数字不再用“来源 1/2”这种模糊写法。</p></article>
    </section>
    <footer className="analysis-method"><ShieldCheck size={17} /><span>集中度不是投资建议。机构 13F 归因于申报机构；个人、配偶及关联账户按正式披露区分；观点、传闻和无法核验的社交媒体信息不参与计算。</span></footer>
  </main>;
}
