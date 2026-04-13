/**
 * PreprocessingPreview — shows 3D preprocessing steps (segmentation, masks, etc.)
 */

import React from 'react';

interface PreprocessingPreviewProps {
  pipelineId: string;
  previews: Record<string, string>;
  isActive: boolean;
}

export function PreprocessingPreview({ pipelineId, previews, isActive }: PreprocessingPreviewProps) {
  const previewEntries = Object.entries(previews);

  if (previewEntries.length === 0 && !isActive) return null;

  return (
    <div className="preprocessing-preview">
      <h3>🔬 3D Preprocessing</h3>
      <p className="preprocessing-hint">
        {isActive
          ? 'Preprocessing views for 3D reconstruction...'
          : 'Preprocessing complete'}
      </p>

      {previewEntries.length > 0 ? (
        <div className="preview-grid">
          {previewEntries.map(([name, url]) => (
            <div key={name} className="preview-card">
              <div className="preview-card-label">{name.replace(/_/g, ' ')}</div>
              <img src={url} alt={name} className="preview-card-img" loading="lazy" />
            </div>
          ))}
        </div>
      ) : (
        <div className="preprocessing-loading">
          <div className="spinner" />
          <p>Waiting for preprocessing results...</p>
        </div>
      )}
    </div>
  );
}

