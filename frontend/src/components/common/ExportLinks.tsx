/**
 * Download links for the export surface (R9 P4, spec §23 / §64-79).
 *
 * Plain anchors, not fetch: the backend responds with `Content-Disposition:
 * attachment`, so the browser saves the file and the SPA stays put. Rendering them as
 * links (not buttons) also means the user can copy the URL or open it in a new tab.
 */

import type { ExportFormat } from '../../lib/api';

const FORMATS: ExportFormat[] = ['csv', 'json'];

export function ExportLinks({
  url,
  label = 'Export',
  disabled = false,
  title,
}: {
  url: (format: ExportFormat) => string;
  label?: string;
  disabled?: boolean;
  title?: string;
}) {
  if (disabled) {
    return (
      <span className="export-links" title={title}>
        <span className="export-links-label">{label}</span>
        <span className="panel-sub">unavailable</span>
      </span>
    );
  }
  return (
    <span className="export-links" title={title}>
      <span className="export-links-label">{label}</span>
      {FORMATS.map((f) => (
        <a key={f} className="btn export-link" href={url(f)} rel="noopener">
          {f.toUpperCase()}
        </a>
      ))}
    </span>
  );
}
