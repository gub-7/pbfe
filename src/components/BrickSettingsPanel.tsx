/**
 * BrickSettingsPanel — exposes Rubric CLI options as UI controls.
 * User can tweak settings and re-run the brick conversion.
 */

import React from 'react';
import type { BrickSettings } from '../types';
import { RefreshCw } from 'lucide-react';

interface BrickSettingsPanelProps {
  settings: BrickSettings;
  onChange: (s: BrickSettings) => void;
  onRegenerate: () => void;
  disabled: boolean;
  isRegenerating: boolean;
}

export function BrickSettingsPanel({
  settings,
  onChange,
  onRegenerate,
  disabled,
  isRegenerating,
}: BrickSettingsPanelProps) {
  const update = (patch: Partial<BrickSettings>) => {
    onChange({ ...settings, ...patch });
  };

  return (
    <div className="brick-settings">
      <h3>🧱 Brick Settings</h3>

      {/* Target Size */}
      <div className="setting-group">
        <label htmlFor="studs">Target Size (studs)</label>
        <input
          id="studs"
          type="range"
          min={8}
          max={128}
          step={4}
          value={settings.studs}
          onChange={(e) => update({ studs: +e.target.value })}
        />
        <span className="setting-value">{settings.studs}</span>
      </div>

      {/* Build Mode */}
      <div className="setting-group">
        <label htmlFor="mode">Build Mode</label>
        <select
          id="mode"
          value={settings.mode}
          onChange={(e) => update({ mode: e.target.value })}
        >
          <option value="sculpture">Sculpture</option>
          <option value="vehicle">Vehicle</option>
          <option value="architecture">Architecture</option>
          <option value="mechanical">Mechanical</option>
          <option value="display">Display</option>
        </select>
      </div>

      {/* Catalog */}
      <div className="setting-group">
        <label htmlFor="catalog">Part Catalog</label>
        <select
          id="catalog"
          value={settings.catalog}
          onChange={(e) => update({ catalog: e.target.value })}
        >
          <option value="popup">Popup (recommended)</option>
          <option value="default_comprehensive">Comprehensive</option>
          <option value="basic_standard">Basic Standard</option>
          <option value="basic_1x1">1×1 Only</option>
          <option value="multipass_with_slopes">With Slopes</option>
        </select>
      </div>

      {/* Packer */}
      <div className="setting-group">
        <label htmlFor="packer">Packing Algorithm</label>
        <select
          id="packer"
          value={settings.packer}
          onChange={(e) => update({ packer: e.target.value })}
        >
          <option value="auto">Auto</option>
          <option value="1x1">1×1 (perfect geometry)</option>
          <option value="multipass">Multipass (optimized)</option>
        </select>
      </div>

      {/* Build Policy */}
      <div className="setting-group">
        <label htmlFor="build_policy">Build Policy</label>
        <select
          id="build_policy"
          value={settings.build_policy}
          onChange={(e) => update({ build_policy: e.target.value })}
        >
          <option value="relaxed">Relaxed</option>
          <option value="balanced">Balanced</option>
          <option value="strict">Strict</option>
        </select>
      </div>

      {/* Voxelizer */}
      <div className="setting-group">
        <label htmlFor="voxelizer">Voxelizer</label>
        <select
          id="voxelizer"
          value={settings.voxelizer}
          onChange={(e) => update({ voxelizer: e.target.value })}
        >
          <option value="auto">Auto</option>
          <option value="sdf">SDF</option>
          <option value="floodfill">Floodfill</option>
        </select>
      </div>

      {/* Color Method */}
      <div className="setting-group">
        <label htmlFor="color_method">Color Matching</label>
        <select
          id="color_method"
          value={settings.color_method}
          onChange={(e) => update({ color_method: e.target.value })}
        >
          <option value="perceptual">Perceptual</option>
          <option value="simple">Simple</option>
        </select>
      </div>

      {/* Toggles */}
      <div className="setting-group setting-group--toggle">
        <label>
          <input
            type="checkbox"
            checked={settings.enable_slopes}
            onChange={(e) => update({ enable_slopes: e.target.checked })}
          />
          Enable Slopes
        </label>
      </div>

      <div className="setting-group setting-group--toggle">
        <label>
          <input
            type="checkbox"
            checked={settings.enable_hollowing}
            onChange={(e) => update({ enable_hollowing: e.target.checked })}
          />
          Enable Hollowing
        </label>
      </div>

      {/* Rotation */}
      <div className="setting-group">
        <label>Rotation (X / Y / Z)</label>
        <div className="rotation-inputs">
          <input
            type="number"
            value={settings.rotate_x}
            onChange={(e) => update({ rotate_x: +e.target.value })}
            step={15}
            placeholder="X"
          />
          <input
            type="number"
            value={settings.rotate_y}
            onChange={(e) => update({ rotate_y: +e.target.value })}
            step={15}
            placeholder="Y"
          />
          <input
            type="number"
            value={settings.rotate_z}
            onChange={(e) => update({ rotate_z: +e.target.value })}
            step={15}
            placeholder="Z"
          />
        </div>
      </div>

      {/* Step interval */}
      <div className="setting-group">
        <label htmlFor="step_every_z">Step Interval (Z)</label>
        <input
          id="step_every_z"
          type="number"
          min={0}
          max={20}
          value={settings.step_every_z}
          onChange={(e) => update({ step_every_z: +e.target.value })}
        />
      </div>

      {/* Regenerate button */}
      <button
        className="btn btn-primary btn-regenerate"
        onClick={onRegenerate}
        disabled={disabled || isRegenerating}
      >
        <RefreshCw size={16} className={isRegenerating ? 'spin' : ''} />
        {isRegenerating ? 'Regenerating...' : 'Regenerate LEGO'}
      </button>
    </div>
  );
}

