/**
 * MetadataPanel — shows Rubric build metadata (part count, colors, etc.)
 */

import React from 'react';

interface MetadataPanelProps {
  metadata: Record<string, any> | null;
}

export function MetadataPanel({ metadata }: MetadataPanelProps) {
  if (!metadata) return null;

  const stats = [
    { label: 'Total Parts', value: metadata.total_parts || metadata.part_count },
    { label: 'Unique Parts', value: metadata.unique_parts },
    { label: 'Colors Used', value: metadata.color_count || metadata.colors_used },
    { label: 'Dimensions', value: metadata.dimensions },
    { label: 'Build Time', value: metadata.build_time },
  ].filter((s) => s.value !== undefined && s.value !== null);

  if (stats.length === 0) return null;

  return (
    <div className="metadata-panel">
      <h4>📊 Build Stats</h4>
      <div className="metadata-grid">
        {stats.map((s) => (
          <div key={s.label} className="metadata-item">
            <span className="metadata-label">{s.label}</span>
            <span className="metadata-value">{String(s.value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

