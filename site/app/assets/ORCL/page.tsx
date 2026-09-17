import { metadataFor, StaticAssetPage } from '@/lib/static-asset-page'; export const metadata = metadataFor('ORCL'); export default function Page() { return <StaticAssetPage ticker="ORCL" />; }
