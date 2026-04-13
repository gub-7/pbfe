/**
 * API client for the BrickedUp backend orchestrator.
 */

import type { BrickSettings, PipelineCreateResponse, PipelineStatus } from './types';

const API_BASE = '/api';

/** Start a new pipeline by uploading an image. */
export async function startPipeline(file: File, debugAlignment: boolean = false): Promise<PipelineCreateResponse> {
  const form = new FormData();
  form.append('file', file);

  const url = debugAlignment ? `${API_BASE}/pipeline/start?debug_alignment=true` : `${API_BASE}/pipeline/start`;
  const res = await fetch(url, {
    method: 'POST',
    body: form,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to start pipeline');
  }

  return res.json();
}

/** Poll the pipeline status. */
export async function getPipelineStatus(pipelineId: string): Promise<PipelineStatus> {
  const res = await fetch(`${API_BASE}/pipeline/${pipelineId}/status`);
  if (!res.ok) {
    throw new Error('Failed to get pipeline status');
  }
  return res.json();
}

/** Re-run brick conversion with new settings. */
export async function rebrickPipeline(
  pipelineId: string,
  settings: BrickSettings,
): Promise<void> {
  const res = await fetch(`${API_BASE}/pipeline/${pipelineId}/rebrick`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ settings }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to start re-conversion');
  }
}

/** Get URL for the input image. */
export function getInputImageUrl(pipelineId: string): string {
  return `${API_BASE}/pipeline/${pipelineId}/input-image`;
}

/** Get URL for a generated view image. */
export function getViewImageUrl(pipelineId: string, viewName: string): string {
  return `${API_BASE}/pipeline/${pipelineId}/view/${viewName}`;
}

/** Get URL for the GLB model. */
export function getGlbUrl(pipelineId: string): string {
  return `${API_BASE}/pipeline/${pipelineId}/glb`;
}

/** Get URL for the LDR model download. */
export function getLdrUrl(pipelineId: string): string {
  return `${API_BASE}/pipeline/${pipelineId}/ldr`;
}

/** Get URL for the BOM. */
export function getBomUrl(pipelineId: string): string {
  return `${API_BASE}/pipeline/${pipelineId}/bom`;
}
