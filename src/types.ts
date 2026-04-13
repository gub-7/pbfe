/**
 * Shared TypeScript types for the BrickedUp frontend.
 */

export type PipelineStage =
  | 'uploaded'
  | 'generating_views'
  | 'preprocessing_3d'
  | 'reconstructing_3d'
  | 'converting_to_brick'
  | 'complete'
  | 'failed';

export interface PipelineCreateResponse {
  pipeline_id: string;
  status: PipelineStage;
  message: string;
}

export interface PipelineStatus {
  pipeline_id: string;
  stage: PipelineStage;
  progress: number;
  stage_message: string;
  generated_views: string[];
  preprocessing_previews: Record<string, string>;
  glb_ready: boolean;
  glb_textured_ready: boolean;
  ldr_ready: boolean;
  bom_ready: boolean;
  rubric_metadata: Record<string, any> | null;
  debug_previews: Record<string, string>;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface BrickSettings {
  studs: number;
  catalog: string;
  packer: string;
  mode: string;
  rotate_x: number;
  rotate_y: number;
  rotate_z: number;
  enable_slopes: boolean;
  enable_hollowing: boolean;
  support_mode: string;
  build_policy: string;
  voxelizer: string;
  max_studs: number;
  max_plates: number;
  step_every_z: number;
  color_method: string;
}

export const DEFAULT_BRICK_SETTINGS: BrickSettings = {
  studs: 32,
  catalog: 'popup',
  packer: 'auto',
  mode: 'sculpture',
  rotate_x: 0,
  rotate_y: 0,
  rotate_z: 0,
  enable_slopes: true,
  enable_hollowing: false,
  support_mode: 'none',
  build_policy: 'balanced',
  voxelizer: 'auto',
  max_studs: 200,
  max_plates: 600,
  step_every_z: 3,
  color_method: 'perceptual',
};

export const CANONICAL_VIEWS = ['front', 'side', 'top'] as const;

/** All pipeline stages in order, for the stepper display. */
export const PIPELINE_STAGES: { key: PipelineStage; label: string; icon: string }[] = [
  { key: 'uploaded', label: 'Upload', icon: '📸' },
  { key: 'generating_views', label: 'AI Views', icon: '🎨' },
  { key: 'preprocessing_3d', label: 'Preprocess', icon: '🔬' },
  { key: 'reconstructing_3d', label: '3D Model', icon: '🧊' },
  { key: 'converting_to_brick', label: 'LEGO Build', icon: '🧱' },
  { key: 'complete', label: 'Done', icon: '✅' },
];

