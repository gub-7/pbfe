/**
 * ViewGallery — displays the AI-generated canonical views.
 *
 * When debug alignment previews are available, shows the incremental
 * reconstruction render beneath each view card so the user can see
 * how each additional view carves the visual hull.
 */

import React from 'react';
import { getViewImageUrl, getInputImageUrl } from '../api';
import { CANONICAL_VIEWS } from '../types';

interface ViewGalleryProps {
  pipelineId: string;
  generatedViews: string[];
  isGenerating: boolean;
  /** Optional debug previews: { front: url, side: url, top: url } */
  debugPreviews?: Record<string, string>;
}

export function ViewGallery({ pipelineId, generatedViews, isGenerating, debugPreviews }: ViewGalleryProps) {
  const allViews = ['input', ...CANONICAL_VIEWS] as const;
  const hasDebug = debugPreviews && Object.keys(debugPreviews).length > 0;

  return (
    <div className="view-gallery">
      <h3>🎨 Generated Views</h3>
      <p className="view-gallery-hint">
        {isGenerating
          ? 'AI is generating canonical views from your photo...'
          : `${generatedViews.length} views generated`}
      </p>

      <div className="view-grid">
        {allViews.map((viewName) => {
          const isReady =
            viewName === 'input' || generatedViews.includes(viewName);
          const url =
            viewName === 'input'
              ? getInputImageUrl(pipelineId)
              : getViewImageUrl(pipelineId, viewName);

          const debugUrl = viewName !== 'input' && debugPreviews ? debugPreviews[viewName] : undefined;

          return (
            <div
              key={viewName}
              className={`view-card ${isReady ? 'view-card--ready' : 'view-card--pending'}`}
            >
              <div className="view-card-label">
                {viewName === 'input' ? '📸 Input' : viewName}
              </div>
              {isReady ? (
                <img src={url} alt={viewName} className="view-card-img" loading="lazy" />
              ) : (
                <div className="view-card-placeholder">
                  <div className="spinner" />
                </div>
              )}

              {/* Debug alignment preview: incremental reconstruction render */}
              {debugUrl && (
                <div className="view-card-debug">
                  <div className="view-card-debug-label">
                    🔍 Reconstruction with {viewName === 'front' ? '1 view' : viewName === 'side' ? '2 views' : '3 views'}
                  </div>
                  <img
                    src={debugUrl}
                    alt={`Debug recon: ${viewName}`}
                    className="view-card-debug-img"
                    loading="lazy"
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>

      {hasDebug && (
        <div className="debug-legend">
          <p className="debug-legend-text">
            🔍 <strong>Debug Alignment:</strong> Each preview shows the 3D visual hull
            after adding that view. Compare shapes to spot camera misalignment —
            if a view carves incorrectly, its camera angle may be wrong.
          </p>
        </div>
      )}
    </div>
  );
}
