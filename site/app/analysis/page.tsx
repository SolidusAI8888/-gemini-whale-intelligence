import type { Metadata } from 'next';
import { ConcentrationAnalysis } from '@/components/concentration-analysis';

export const metadata: Metadata = { title: '集中度分析｜Whale Intelligence', description: '政商巨鲸行动集中度与当前披露持仓集中度。' };
export default function Page() { return <ConcentrationAnalysis />; }
