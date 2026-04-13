import React, { useEffect, useRef, useState } from 'react';
import { ImageCapture } from './components/ImageCapture';
import { ViewGallery } from './components/ViewGallery';
import { PreprocessingPreview } from './components/PreprocessingPreview';
import { ProgressTracker } from './components/ProgressTracker';
import { BrickSettingsPanel } from './components/BrickSettingsPanel';
import { ModelViewer } from './components/ModelViewer';
import { MetadataPanel } from './components/MetadataPanel';
import { usePipeline } from './hooks/usePipeline';
import { RotateCcw } from 'lucide-react';

/**
 * Stage ordering — used to determine if a stage has been "reached".
 * Once a stage is reached, its UI section stays visible permanently
 * and new sections appear below it (never replacing it).
 */
const STAGE_INDEX: Record<string, number> = {
  uploaded: 0,
  generating_views: 1,
  preprocessing_3d: 2,
  reconstructing_3d: 3,
  converting_to_brick: 4,
  complete: 5,
  failed: 99,
};

export default function App() {
  const {
    status,
    isActive,
    brickSettings,
    setBrickSettings,
    start,
    rebrick,
    reset,
    error,
  } = usePipeline();

  const [debugAlignment, setDebugAlignment] = useState(false);

  // Track the highest stage ever reached so sections never disappear
  const [highWaterStage, setHighWaterStage] = useState(-1);
  useEffect(() => {
    if (status) {
      const idx = STAGE_INDEX[status.stage] ?? -1;
      setHighWaterStage((prev) => Math.max(prev, idx));
    }
  }, [status?.stage]);

  const hasStarted = status !== null;

  // Sections appear once their stage is reached and never disappear
  const reachedViews = highWaterStage >= 1;
  const reachedPreprocessing = highWaterStage >= 2;
  const reachedModel = highWaterStage >= 3 || (hasStarted && status.glb_ready);
  const reachedComplete = hasStarted && status.stage === 'complete';
  const isRegenerating = hasStarted && status.stage === 'converting_to_brick';

  const handleStart = (file: File) => start(file, debugAlignment);

  const handleReset = () => {
    setHighWaterStage(-1);
    reset();
  };

  return (
    <div className="app">
      {/* Header */}
      <header className="app-header">
        <div className="header-content">
          <div className="logo">
            <span className="logo-icon">🧱</span>
            <h1>BrickedUp</h1>
          </div>
          <p className="tagline">Turn any photo into a buildable LEGO model</p>
          {hasStarted && (
            <button onClick={handleReset} className="btn btn-ghost">
              <RotateCcw size={16} /> Start Over
            </button>
          )}
        </div>
      </header>

      {/* Sticky progress bar — visible once pipeline has started */}
      {hasStarted && (
        <div className="sticky-progress">
          <ProgressTracker
            stage={status.stage}
            progress={status.progress}
            stageMessage={status.stage_message}
            error={status.error || error}
          />
        </div>
      )}

      <main className="app-main">
        {/* ── Section 1: Image Upload / Input Preview ──────────────── */}
        <section className="section section-capture">
          {!hasStarted ? (
            <>
              <ImageCapture onImageSelected={handleStart} disabled={isActive} error={error} />
              <div className="debug-toggle">
                <label className="debug-toggle-label">
                  <input
                    type="checkbox"
                    checked={debugAlignment}
                    onChange={(e) => setDebugAlignment(e.target.checked)}
                    className="debug-toggle-checkbox"
                  />
                  <span className="debug-toggle-text">
                    🔍 Debug camera alignment (shows incremental reconstruction per view)
                  </span>
                </label>
              </div>
            </>
          ) : (
            <div className="input-preview">
              <h3>📸 Input Photo</h3>
              <div className="input-preview-img-wrapper">
                <img
                  src={`/api/pipeline/${status.pipeline_id}/input-image`}
                  alt="Input"
                  className="input-preview-img"
                />
              </div>
              {debugAlignment && (
                <span className="input-preview-badge">🔍 Debug alignment enabled</span>
              )}
            </div>
          )}
        </section>

        {/* ── Section 2: Generated Views ───────────────────────────── */}
        {reachedViews && (
          <section className="section section-views section-appear">
            <ViewGallery
              pipelineId={status!.pipeline_id}
              generatedViews={status!.generated_views}
              isGenerating={status!.stage === 'generating_views'}
              debugPreviews={status!.debug_previews}
            />
          </section>
        )}

        {/* ── Section 3: 3D Preprocessing Previews ─────────────────── */}
        {reachedPreprocessing && (
          <section className="section section-preprocessing section-appear">
            <PreprocessingPreview
              pipelineId={status!.pipeline_id}
              previews={status!.preprocessing_previews}
              isActive={status!.stage === 'preprocessing_3d'}
            />
          </section>
        )}

        {/* ── Section 4: 3D Model + Brick Settings ─────────────────── */}
        {reachedModel && (
          <section className="section section-result section-appear">
            <div className="result-layout">
              <div className="result-viewer">
                <ModelViewer
                  pipelineId={status!.pipeline_id}
                  glbReady={status!.glb_ready}
                  ldrReady={status!.ldr_ready}
                />
                <MetadataPanel metadata={status!.rubric_metadata} />
              </div>

              <div className="result-settings">
                <BrickSettingsPanel
                  settings={brickSettings}
                  onChange={setBrickSettings}
                  onRegenerate={rebrick}
                  disabled={!status!.glb_ready}
                  isRegenerating={isRegenerating}
                />
              </div>
            </div>
          </section>
        )}

        {/* ── Section 5: Complete Banner ────────────────────────────── */}
        {reachedComplete && (
          <section className="section section-complete section-appear">
            <div className="complete-banner">
              <h2>🎉 Your LEGO model is ready!</h2>
              <p>
                Download the LDR file and open it in{' '}
                <a href="https://www.leocad.org/" target="_blank" rel="noopener noreferrer">LeoCAD</a>{' '}
                or{' '}
                <a href="https://www.bricklink.com/v3/studio/download.page" target="_blank" rel="noopener noreferrer">BrickLink Studio</a>{' '}
                to view and order parts.
              </p>
              <p className="complete-hint">
                Tweak the settings and hit <strong>Regenerate LEGO</strong> to try different configurations.
              </p>
            </div>
          </section>
        )}

        {/* ── Error display ────────────────────────────────────────── */}
        {hasStarted && status.stage === 'failed' && (
          <section className="section section-error section-appear">
            <div className="error-banner">
              <h3>❌ Pipeline Failed</h3>
              <p>{status.error || error || 'An unknown error occurred.'}</p>
              <button onClick={handleReset} className="btn btn-primary" style={{ marginTop: 16 }}>
                <RotateCcw size={16} /> Try Again
              </button>
            </div>
          </section>
        )}
      </main>

      <footer className="app-footer">
        <p>BrickedUp — Powered by <strong>Rubric</strong> &amp; <strong>GPU Cluster</strong></p>
      </footer>
    </div>
  );
}
