/**
 * ImageCapture — drag-and-drop + file picker + camera capture for the input photo.
 */

import React, { useCallback, useRef, useState } from 'react';
import { Camera, Upload, Loader } from 'lucide-react';

interface ImageCaptureProps {
  onImageSelected: (file: File) => void;
  disabled: boolean;
  error?: string | null;
}

export function ImageCapture({ onImageSelected, disabled, error }: ImageCaptureProps) {
  const [dragActive, setDragActive] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    (file: File) => {
      if (disabled) return;
      const url = URL.createObjectURL(file);
      setPreview(url);
      onImageSelected(file);
    },
    [disabled, onImageSelected],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragActive(false);
      if (e.dataTransfer.files.length > 0) {
        handleFile(e.dataTransfer.files[0]);
      }
    },
    [handleFile],
  );

  return (
    <div className="capture-container">
      <h2>📸 Upload Your Photo</h2>
      <p className="capture-hint">
        Take a photo from a <strong>corner angle</strong> that shows ~3 sides of your subject.
        The AI will generate the remaining views.
      </p>

      <div
        className={`drop-zone ${dragActive ? 'drop-zone--active' : ''} ${disabled ? 'drop-zone--disabled' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        onClick={() => !disabled && fileInputRef.current?.click()}
      >
        {preview ? (
          <div className="drop-zone-preview-wrapper">
            <img src={preview} alt="Preview" className="drop-zone-preview" />
            {disabled && (
              <div className="drop-zone-overlay">
                <Loader size={32} className="spinner" />
                <p>Starting pipeline…</p>
              </div>
            )}
          </div>
        ) : (
          <div className="drop-zone-content">
            <Upload size={48} strokeWidth={1.5} />
            <p>Drag & drop an image here</p>
            <p className="drop-zone-sub">or click to browse</p>
          </div>
        )}
      </div>

      {/* Error message */}
      {error && (
        <div className="capture-error">
          <p>❌ {error}</p>
          <p className="capture-error-hint">Please try uploading again.</p>
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        style={{ display: 'none' }}
        onChange={(e) => {
          if (e.target.files?.[0]) handleFile(e.target.files[0]);
        }}
      />

      {/* Camera capture for mobile */}
      <button
        className="btn btn-secondary capture-camera-btn"
        onClick={() => cameraInputRef.current?.click()}
        disabled={disabled}
      >
        <Camera size={18} /> Take Photo
      </button>
      <input
        ref={cameraInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        style={{ display: 'none' }}
        onChange={(e) => {
          if (e.target.files?.[0]) handleFile(e.target.files[0]);
        }}
      />
    </div>
  );
}
