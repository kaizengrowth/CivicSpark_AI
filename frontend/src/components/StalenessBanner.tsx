import React, { useEffect, useState } from 'react';
import { apiRequest, API_ENDPOINTS } from '../config/api';
import { IngestStatus } from '../types/meetings';

/**
 * Surfaces scraper staleness instead of hiding it: if the last
 * successful ingestion run is too old (or none exists), users see that
 * the data may be outdated rather than trusting silently stale answers.
 */
export const StalenessBanner: React.FC = () => {
  const [status, setStatus] = useState<IngestStatus | null>(null);

  useEffect(() => {
    apiRequest<IngestStatus>(API_ENDPOINTS.ingestStatus)
      .then(setStatus)
      .catch(() => setStatus(null));
  }, []);

  if (!status || !status.is_stale) return null;

  const lastSuccess = status.sources
    .map((s) => s.last_success_at)
    .filter(Boolean)
    .sort()
    .pop();

  return (
    <div
      className="bg-amber-50 border border-amber-300 text-amber-900 rounded-md px-4 py-3 mb-4 text-sm"
      role="alert"
    >
      <strong>Data may be out of date.</strong>{' '}
      {lastSuccess
        ? `The last successful update from the City of Tulsa was ${new Date(
            lastSuccess
          ).toLocaleDateString()}.`
        : 'No successful update from the City of Tulsa has been recorded yet.'}{' '}
      Recent meetings and documents may be missing.
    </div>
  );
};
