import { metadataFor, StaticAssetPage } from '@/lib/static-asset-page'; export const metadata = metadataFor('BTC'); export default function Page() { return <StaticAssetPage ticker="BTC" />; }
