'use client';

import { useMemo, useState } from 'react';
import { Activity, ArrowLeft, Building2, Landmark, Search, ShieldCheck, UserRoundCog, Users } from 'lucide-react';
import { useSiteData } from '@/lib/use-site-data';
import type { WhaleProfile } from '@/lib/site-data';

const categories: Array<{ name: WhaleProfile['category']; icon: typeof Users; note: string }> = [
  { name: '政界巨鲸', icon: Landmark, note: '美国国会 PTR 正式交易披露' },
  { name: '行政部门', icon: ShieldCheck, note: 'OGE 行政部门交易与资产披露' },
  { name: '公司关键人员', icon: UserRoundCog, note: '董事长、CEO、CFO、CIO、董事及重要高管的 SEC Form 4' },
  { name: '重点机构', icon: Building2, note: '纳入观察名单的机构及其 SEC 13F 持仓' },
];

export function WhalePool() {
  const { data } = useSiteData();
  const [query, setQuery] = useState('');
  const filtered = useMemo(() => { const value = query.trim().toLowerCase(); return value ? data.whales.filter((whale) => `${whale.name} ${whale.role} ${whale.source}`.toLowerCase().includes(value)) : data.whales; }, [data.whales, query]);
  const coreTickers = new Set(data.assets.map((asset) => asset.ticker));
  return <main className="whale-pool-page">
    <header className="analysis-header"><a href="/"><ArrowLeft size={17} />返回标的工作台</a><div className="terminal-brand"><span><Activity size={18} /></span><div><strong>WHALE INTELLIGENCE</strong><small>巨鲸池</small></div></div><span className="analysis-live"><i />{data.whales.length} 个主体</span></header>
    <section className="whale-pool-hero"><p>TRACKED WHALE UNIVERSE</p><h1>巨鲸池与权重</h1><span>只纳入存在正式可验证披露的政界、行政部门、公司关键人员与重点机构。点击任一主体可展开其最新可见股票持仓。</span><label><Search size={17} /><input aria-label="搜索巨鲸" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索姓名、机构或职务" /></label></section>
    <section className="whale-groups">{categories.map(({ name, icon: Icon, note }) => { const whales = filtered.filter((whale) => whale.category === name); return <article className="whale-group" key={name}><header><Icon size={20} /><div><h2>{name}</h2><p>{note}</p></div><b>{whales.length}</b></header><div>{whales.length ? whales.map((whale) => <details className="whale-card" key={whale.name}><summary><span className="whale-avatar">{whale.name.slice(0, 1).toUpperCase()}</span><span><strong>{whale.name}</strong><small>{whale.role || whale.source}</small></span><span className="whale-weight"><small>权重</small><b>{whale.weight.toFixed(2)}</b></span><span className="whale-count"><small>行动</small><b>{whale.eventCount}</b></span><i>⌄</i></summary><div className="whale-holdings"><h3>最新披露持仓</h3>{whale.holdings.length ? whale.holdings.map((holding) => { const ticker = holding.ticker === 'GOOGL' ? 'GOOG' : holding.ticker; const content = <><strong>{holding.ticker}</strong><span>{holding.amount}</span><small>{holding.source} · {holding.publishedAt || holding.occurredAt}</small></>; return coreTickers.has(ticker) ? <a href={`/assets/${ticker}`} key={`${whale.name}-${holding.id}`}>{content}</a> : <div className="whale-holding-row" key={`${whale.name}-${holding.id}`}>{content}</div>; }) : <p>该主体目前只有交易披露，尚无可验证的当前持仓快照。</p>}</div></details>) : <div className="whale-group-empty">当前数据中暂无该类别的有效披露主体。</div>}</div></article>; })}</section>
    <section className="whale-weight-method"><h2>权重规则</h2><p>政界巨鲸与行政部门关键官员为 1.00；重点机构为 0.90；公司董事及一般高管为 0.85；董事长、CEO、CFO、CIO 等关键岗位为 1.00。权重用于后续交织集中度计算，表示主体的跟踪优先级，不代表投资收益概率。</p></section>
  </main>;
}
