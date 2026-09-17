'use client';

import { Activity, ArrowLeft, Building2, Network, ShieldCheck, Users } from 'lucide-react';
import { useSiteData } from '@/lib/use-site-data';

export function ConcentrationAnalysis() {
  const { data } = useSiteData();
  const maxAction = Math.max(1, ...data.concentration.map((row) => row.score));
  const maxHolding = Math.max(1, ...data.holdingConcentration.map((row) => row.holderCount));
  const coreTickers = new Set(data.assets.map((asset) => asset.ticker));
  const detailTicker = (ticker: string) => ticker === 'GOOGL' && coreTickers.has('GOOG') ? 'GOOG' : coreTickers.has(ticker) ? ticker : null;
  return <main className="analysis-page">
    <header className="analysis-header"><a href="/"><ArrowLeft size={15} />返回标的工作台</a><div className="terminal-brand"><span><Activity size={17} /></span><div><strong>WHALE INTELLIGENCE</strong><small>集中度分析</small></div></div><span className="analysis-live"><i />生产数据</span></header>
    <section className="analysis-hero"><p>CONCENTRATION INTELLIGENCE</p><h1>政商巨鲸行动与持仓集中度</h1><span>把跨主体、跨披露来源、跨行动方向的重合信号集中在一个独立视图；主工作台保持专注于单一标的。</span></section>
    <section className="analysis-summary"><div><Users size={18} /><span>行动覆盖标的<strong>{data.concentration.length}</strong></span></div><div><Building2 size={18} /><span>持仓覆盖标的<strong>{data.holdingConcentration.length}</strong></span></div><div><Network size={18} /><span>可验证行动<strong>{data.events.length}</strong></span></div><div><ShieldCheck size={18} /><span>数据原则<strong>只看行动</strong></span></div></section>
    <section className="analysis-grid">
      <article className="analysis-panel"><header><div><p>ACTION CONCENTRATION</p><h2>新建仓 / 加仓 / 减仓 / 清仓集中度</h2></div><span>多主体 × 多来源</span></header><div className="analysis-table-head"><span>排名 / 标的</span><span>主体</span><span>来源</span><span>净行动金额</span><span>评分</span></div>{data.concentration.map((row, index) => { const content = <><span className="analysis-rank">{String(index + 1).padStart(2, '0')}<strong>{row.ticker}</strong></span><span>{row.buyers}</span><span>{row.groups}</span><span>{row.net}</span><span className="analysis-score"><b>{row.score}</b><i><em style={{ width: `${row.score / maxAction * 100}%` }} /></i></span></>; const target = detailTicker(row.ticker); return target ? <a href={`/assets/${target}`} className="analysis-row" key={row.ticker}>{content}</a> : <div className="analysis-row" key={row.ticker}>{content}</div>; })}</article>
      <article className="analysis-panel"><header><div><p>HOLDING CONCENTRATION</p><h2>当前披露持仓集中度</h2></div><span>最新可见快照</span></header><div className="analysis-table-head holding"><span>排名 / 标的</span><span>持有人</span><span>披露类型</span><span>申报价值</span></div>{data.holdingConcentration.map((row, index) => { const content = <><span className="analysis-rank">{String(index + 1).padStart(2, '0')}<strong>{row.ticker}</strong></span><span>{row.holderCount}</span><span>{row.sourceCount}</span><span>{row.value}</span><span className="analysis-score"><i><em style={{ width: `${row.holderCount / maxHolding * 100}%` }} /></i></span></>; const target = detailTicker(row.ticker); return target ? <a href={`/assets/${target}`} className="analysis-row holding" key={row.ticker}>{content}</a> : <div className="analysis-row holding" key={row.ticker}>{content}</div>; })}</article>
    </section>
    <footer className="analysis-method"><ShieldCheck size={16} /><span>集中度不是投资建议。机构 13F 归因于申报机构；个人、配偶及关联账户按正式披露区分；观点和传闻不参与计算。</span></footer>
  </main>;
}
