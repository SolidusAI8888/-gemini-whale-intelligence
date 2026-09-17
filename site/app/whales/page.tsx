import type { Metadata } from 'next';
import { WhalePool } from '@/components/whale-pool';

export const metadata: Metadata = { title: '巨鲸池｜Whale Intelligence', description: '已纳入跟踪的政界、行政部门、公司关键人员与重点机构，以及权重和最新披露持仓。', openGraph: { images: [] }, twitter: { images: [] } };

export default function Page() { return <WhalePool />; }
