'use client';

import { useMemo, useState } from 'react';
import { Activity, ArrowLeft, Building2, Landmark, Search, ShieldCheck, UserRoundCog, Users } from 'lucide-react';
import { useSiteData } from '@/lib/use-site-data';
import type { WhaleProfile } from '@/lib/site-data';

const categories: Array<{ name: WhaleProfile['category']; icon: typeof Users; note: string }> = [
  { name: '政界巨鲸', icon: Landmark, note: '交易活跃的众议院与参议院 PTR 申报主体' },
  { name: '行政部门', icon: ShieldCheck, note: '特朗普及现任 Cabinet / Cabinet-level 官员' },
  { name: '公司关键人员', icon: UserRoundCog, note: '所有核心公司的董事长、CEO、CFO 岗位' },
  { name: '重点机构', icon: Building2, note: '美股 TOP20 机构基准及已采集的重点 13F 机构' },
];

export function WhalePool() {
  const { data } = useSiteData();
  const [query, setQuery] = useState('');
  const filtered = useMemo(() => { const value = query.trim().toLowerCase(); return value ? data.whales.filter((whale) => `${whale.name} ${whale.role} ${whale.source} ${whale.ticker}`.toLowerCase().includes(value)) : data.whales; }, [data.whales, query]);
  const coreTickers = new Set(data.assets.map((asset) => asset.ticker));
  const disclosedTotal = data.whales.filter((whale) => whale.trackingStatus === 'disclosed').length;
  const holdingTotal = data.whales.filter((whale) => whale.holdings.length > 0).length;
  const actionOnlyTotal = data.whales.filter((whale) => whale.eventCount > 0 && whale.holdings.length === 0).length;
  const coverage = data.whales.length ? Math.round(disclosedTotal / data.whales.length * 100) : 0;
  return <main className="whale-pool-page">
    <header className="analysis-header"><a href="/"><ArrowLeft size={17} />返回标的工作台</a><div className="terminal-brand"><span><Activity size={18} /></span><div><strong>WHALE INTELLIGENCE</strong><small>巨鲸池</small></div></div><span className="analysis-live"><i />{data.whales.length} 个主体</span></header>
    <section className="whale-pool-hero"><p>TRACKED WHALE UNIVERSE</p><h1>巨鲸池与权重</h1><span>跟踪范围与交易事实严格分离：名单完整纳入监测，但只有正式可验证披露才能形成行动、持仓、图表打点或集中度评分。交易披露不等于当前持仓，二者单独统计。</span><div className="coverage-strip"><b>{coverage}%<small>主体披露覆盖率</small></b><b>{holdingTotal}<small>有当前持仓快照</small></b><b>{actionOnlyTotal}<small>仅有行动、无持仓快照</small></b><b>{data.whales.length - disclosedTotal}<small>尚无有效披露</small></b></div><label><Search size={17} /><input aria-label="搜索巨鲸" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索姓名、机构、股票或职务" /></label></section>
    <section className="whale-groups">{categories.map(({ name, icon: Icon, note }) => { const whales = filtered.filter((whale) => whale.category === name); const disclosed = whales.filter((whale) => whale.trackingStatus === 'disclosed').length; return <article className="whale-group" key={name}><header><Icon size={20} /><div><h2>{name}</h2><p>{note}</p></div><b>{whales.length}<small>{disclosed} 有披露</small></b></header><div>{whales.length ? whales.map((whale) => { const hasHoldings = whale.holdings.length > 0; const countLabel = hasHoldings ? '持仓' : whale.trackingStatus === 'disclosed' ? '行动' : '状态'; const countValue = hasHoldings ? whale.holdings.length : whale.trackingStatus === 'disclosed' ? whale.eventCount : '无有效披露'; return <details className="whale-card" key={`${whale.category}-${whale.name}`}><summary><span className="whale-avatar">{whale.name.slice(0, 1).toUpperCase()}</span><span><strong>{whale.name}</strong><small>{whale.role || whale.source}</small></span><span className="whale-weight"><small>权重</small><b>{whale.weight.toFixed(2)}</b></span><span className="whale-count"><small>{countLabel}</small><b>{countValue}</b></span><i>⌄</i></summary><div className="whale-holdings"><h3>正式披露记录</h3>{whale.holdings.length ? whale.holdings.map((holding) => { const ticker = holding.ticker === 'GOOGL' ? 'GOOG' : holding.ticker; const content = <><strong>{holding.ticker}</strong><span>{holding.amount}</span><small>{holding.source} · {holding.publishedAt || holding.occurredAt}</small></>; return coreTickers.has(ticker) ? <a href={`/assets/${ticker}`} key={`${whale.name}-${holding.id}`}>{content}</a> : <div className="whale-holding-row" key={`${whale.name}-${holding.id}`}>{content}</div>; }) : <p>{whale.trackingStatus === 'disclosed' ? '已有可验证行动，但尚无可验证的当前持仓快照。' : '已纳入跟踪范围；目前没有通过数据质量门的交易或持仓披露，因此不会进入图表或评分。'}</p>}{whale.sourceUrl && <a className="whale-source" href={whale.sourceUrl} target="_blank" rel="noreferrer">查看跟踪依据</a>}</div></details>; }) : <div className="whale-group-empty">当前筛选下暂无主体。</div>}</div></article>; })}</section>
    <section className="whale-weight-method"><h2>权重规则</h2><p>政界巨鲸与行政部门关键官员为 1.00；重点机构为 0.90；公司董事及一般高管为 0.85；董事长、CEO、CFO、CIO 等关键岗位为 1.00。权重用于后续交织集中度计算，表示主体的跟踪优先级，不代表投资收益概率。</p></section>
  </main>;
}
