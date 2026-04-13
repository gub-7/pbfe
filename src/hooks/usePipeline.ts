/**
 * Main pipeline hook — manages the full pipeline lifecycle.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  getPipelineStatus,
  rebrickPipeline,
  startPipeline,
} from '../api';
import type { BrickSettings, PipelineStatus } from '../types';
import { DEFAULT_BRICK_SETTINGS } from '../types';

export interface UsePipelineReturn {
  status: PipelineStatus | null;
  isActive: boolean;
  brickSettings: BrickSettings;
  setBrickSettings: (s: BrickSettings) => void;
  start: (file: File, debugAlignment?: boolean) => Promise<void>;
  rebrick: () => Promise<void>;
  reset: () => void;
  error: string | null;
}

export function usePipeline(): UsePipelineReturn {
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [brickSettings, setBrickSettings] = useState<BrickSettings>(DEFAULT_BRICK_SETTINGS);
  const [error, setError] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pipelineIdRef = useRef<string | null>(null);

  const isActive =
    isStarting ||
    (status !== null &&
    status.stage !== 'complete' &&
    status.stage !== 'failed');

  // Poll for status updates
  useEffect(() => {
    if (!pipelineIdRef.current || !isActive) {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
      return;
    }

    const poll = async () => {
      try {
        const s = await getPipelineStatus(pipelineIdRef.current!);
        setStatus(s);
        if (s.error) setError(s.error);
      } catch (e: any) {
        console.error('Polling error:', e);
      }
    };

    // Initial poll
    poll();

    pollingRef.current = setInterval(poll, 2000);

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [isActive, status?.stage]);

  const start = useCallback(async (file: File, debugAlignment: boolean = false) => {
    setError(null);
    setIsStarting(true);
    try {
      const resp = await startPipeline(file, debugAlignment);
      pipelineIdRef.current = resp.pipeline_id;
      setStatus({
        pipeline_id: resp.pipeline_id,
        stage: resp.status,
        progress: 0,
        stage_message: resp.message,
        generated_views: [],
        preprocessing_previews: {},
        glb_ready: false,
        glb_textured_ready: false,
        ldr_ready: false,
        bom_ready: false,
        rubric_metadata: null,
        debug_previews: {},
        error: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });
    } catch (e: any) {
      setError(e.message);
    } finally {
      setIsStarting(false);
    }
  }, []);

  const rebrick = useCallback(async () => {
    if (!pipelineIdRef.current) return;
    setError(null);
    try {
      await rebrickPipeline(pipelineIdRef.current, brickSettings);
      // Status will update via polling
    } catch (e: any) {
      setError(e.message);
    }
  }, [brickSettings]);

  const reset = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
    pipelineIdRef.current = null;
    setStatus(null);
    setError(null);
    setIsStarting(false);
    setBrickSettings(DEFAULT_BRICK_SETTINGS);
  }, []);

  return {
    status,
    isActive,
    brickSettings,
    setBrickSettings,
    start,
    rebrick,
    reset,
    error,
  };
}

