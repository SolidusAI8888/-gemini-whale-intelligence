import type { Metadata } from 'next';
import { WhaleDashboard } from '@/components/whale-dashboard';
import { coreAssets } from '@/lib/whale-data';

export function metadataFor(ticker: string): Metadata {
  const asset = coreAssets.find((item) => item.ticker === ticker);
  return {
    title: `${ticker} 巨鲸行动时间轴｜Whale Intelligence`,
    description: `${asset?.name || ticker} 的真实价格、可验证交易、持仓变化与披露延迟。`,
    openGraph: { images: [] }, twitter: { images: [] },
  };
}

export function StaticAssetPage({ ticker }: { ticker: string }) { return <WhaleDashboard initialTicker={ticker} />; }
