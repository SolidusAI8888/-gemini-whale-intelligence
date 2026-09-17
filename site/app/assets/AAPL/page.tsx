import { metadataFor, StaticAssetPage } from '@/lib/static-asset-page'; export const metadata = metadataFor('AAPL'); export default function Page() { return <StaticAssetPage ticker="AAPL" />; }
