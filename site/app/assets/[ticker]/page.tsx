import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { AssetDetail } from '@/components/asset-detail';
import { coreAssets } from '@/lib/whale-data';

export function generateStaticParams() { return coreAssets.map((asset) => ({ ticker: asset.ticker })); }

export async function generateMetadata({ params }: { params: Promise<{ ticker: string }> }): Promise<Metadata> {
  const { ticker } = await params; const asset = coreAssets.find((item) => item.ticker === ticker.toUpperCase());
  if (!asset) return { title: '标的不存在｜Whale Intelligence' };
  return { title: `${asset.ticker} 巨鲸行动时间轴｜Whale Intelligence`, description: `${asset.name} 的可验证交易、持仓变化、披露延迟与价格时间轴。`, openGraph: { images: [] }, twitter: { images: [] } };
}

export default async function AssetPage({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker } = await params; const normalized = ticker.toUpperCase();
  if (!coreAssets.some((asset) => asset.ticker === normalized)) notFound();
  return <AssetDetail ticker={normalized} />;
}
