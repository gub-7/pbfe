/**
 * ModelViewer — displays the 3D GLB model using <model-viewer>.
 * Shows both textured and wireframe views.
 */

import React from 'react';
import { getGlbUrl, getLdrUrl } from '../api';
import { Download } from 'lucide-react';

// Extend JSX for model-viewer web component
declare global {
  namespace JSX {
    interface IntrinsicElements {
      'model-viewer': React.DetailedHTMLProps<
        React.HTMLAttributes<HTMLElement> & {
          src?: string;
          alt?: string;
          'auto-rotate'?: boolean;
          'camera-controls'?: boolean;
          'shadow-intensity'?: string;
          exposure?: string;
          poster?: string;
          loading?: string;
          reveal?: string;
          'environment-image'?: string;
          'tone-mapping'?: string;
        },
        HTMLElement
      >;
    }
  }
}

interface ModelViewerProps {
  pipelineId: string;
  glbReady: boolean;
  ldrReady: boolean;
}

export function ModelViewer({ pipelineId, glbReady, ldrReady }: ModelViewerProps) {
  const glbUrl = glbReady ? getGlbUrl(pipelineId) : '';
  const ldrUrl = ldrReady ? getLdrUrl(pipelineId) : '';

  return (
    <div className="model-viewer-container">
      <h3>🧊 3D Model</h3>

      {glbReady ? (
        <>
          <div className="model-viewer-wrapper">
            <model-viewer
              src={glbUrl}
              alt="3D Model"
              auto-rotate
              camera-controls
              shadow-intensity="1"
              exposure="1"
              tone-mapping="neutral"
              style={{ width: '100%', height: '400px', borderRadius: '12px' }}
            />
          </div>

          <div className="model-actions">
            <a href={glbUrl} download="model.glb" className="btn btn-secondary">
              <Download size={16} /> Download GLB
            </a>
            {ldrReady && (
              <a href={ldrUrl} download="model.ldr" className="btn btn-primary">
                <Download size={16} /> Download LDR
              </a>
            )}
          </div>
        </>
      ) : (
        <div className="model-placeholder">
          <div className="spinner" />
          <p>Building 3D model...</p>
        </div>
      )}
    </div>
  );
}

