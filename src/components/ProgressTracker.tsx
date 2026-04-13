/**
 * ProgressTracker — shows pipeline stages as a horizontal stepper with progress bar.
 */

import React from 'react';
import type { PipelineStage } from '../types';
import { PIPELINE_STAGES } from '../types';

interface ProgressTrackerProps {
  stage: PipelineStage;
  progress: number;
  stageMessage: string;
  error: string | null;
}

export function ProgressTracker({ stage, progress, stageMessage, error }: ProgressTrackerProps) {
  const currentIdx = PIPELINE_STAGES.findIndex((s) => s.key === stage);

  return (
    <div className="progress-tracker">
      {/* Stepper */}
      <div className="stepper">
        {PIPELINE_STAGES.map((s, i) => {
          let cls = 'stepper-step';
          if (i < currentIdx) cls += ' stepper-step--done';
          else if (i === currentIdx) cls += ' stepper-step--active';
          if (stage === 'failed' && i === currentIdx) cls += ' stepper-step--error';

          return (
            <div key={s.key} className={cls}>
              <span className="stepper-icon">{s.icon}</span>
              <span className="stepper-label">{s.label}</span>
            </div>
          );
        })}
      </div>

      {/* Progress bar */}
      <div className="progress-bar-container">
        <div
          className={`progress-bar ${stage === 'failed' ? 'progress-bar--error' : ''}`}
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Status message */}
      <p className="progress-message">
        {error ? (
          <span className="error-text">❌ {error}</span>
        ) : (
          stageMessage
        )}
      </p>
    </div>
  );
}

