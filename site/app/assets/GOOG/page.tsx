import { metadataFor, StaticAssetPage } from '@/lib/static-asset-page'; export const metadata = metadataFor('GOOG'); export default function Page() { return <StaticAssetPage ticker="GOOG" />; }
