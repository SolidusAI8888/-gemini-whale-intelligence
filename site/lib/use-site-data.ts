'use client';
import { useEffect, useState } from 'react';
import { regressionSiteView, toSiteView, type SitePayload, type SiteViewData } from '@/lib/site-data';
export function useSiteData(): { data: SiteViewData; loading: boolean; failed: boolean } {
  const [data, setData] = useState<SiteViewData>(regressionSiteView); const [loading, setLoading] = useState(true); const [failed, setFailed] = useState(false);
  useEffect(() => { let active = true; fetch('/data/site-data.json', { cache: 'no-store' }).then((response) => { if (!response.ok) throw new Error(`site data ${response.status}`); return response.json() as Promise<SitePayload>; }).then((payload) => { if (active) setData(toSiteView(payload)); }).catch(() => { if (active) setFailed(true); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, []);
  return { data, loading, failed };
}
