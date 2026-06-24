import type { FolioPortfolioDetail } from '../api/dojoFolio';
import { cacheKeys } from '../cache/cacheKeys';
import { invalidateCache, invalidateCachePrefix, setCached } from '../cache/queryCache';

export const FOLIO_UPDATED_EVENT = 'alphadojo-folio-updated';

export type FolioUpdateAction = 'create' | 'update';

export interface FolioUpdatedDetail {
  portfolioId?: string;
  detail?: FolioPortfolioDetail;
  action?: FolioUpdateAction;
}

function dispatchFolioUpdated(payload: FolioUpdatedDetail) {
  window.dispatchEvent(
    new CustomEvent<FolioUpdatedDetail>(FOLIO_UPDATED_EVENT, {
      detail: payload,
    }),
  );
}

export function publishFolioListRefresh(options?: {
  portfolioId?: string;
  action?: FolioUpdateAction;
}) {
  invalidateCache(cacheKeys.folioPortfolios());
  dispatchFolioUpdated({
    portfolioId: options?.portfolioId,
    action: options?.action,
  });
}

export function publishFolioPortfolioUpdate(
  detail: FolioPortfolioDetail,
  options?: { action?: FolioUpdateAction },
) {
  invalidateCache(cacheKeys.folioPortfolios());
  invalidateCache(cacheKeys.folioPortfolioLite(detail.id));
  invalidateCachePrefix(`folio-portfolio:${detail.id}:`);
  setCached(cacheKeys.folioPortfolioLite(detail.id), detail);

  dispatchFolioUpdated({
    portfolioId: detail.id,
    detail,
    action: options?.action,
  });
}
