import { metadataFor, StaticAssetPage } from '@/lib/static-asset-page'; export const metadata = metadataFor('MSFT'); export default function Page() { return <StaticAssetPage ticker="MSFT" />; }
