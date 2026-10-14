import React, { useEffect, useRef, useState } from 'react'
import { Image as ImageIcon, ZoomIn, Maximize2 } from 'lucide-react'

interface OriginalCropPreviewProps {
  imageUrl: string | null
  bbox: [number, number, number, number]
  observedText?: string
}

export const OriginalCropPreview: React.FC<OriginalCropPreviewProps> = ({
  imageUrl,
  bbox,
  observedText
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState(false)
  const [showFullModal, setShowFullModal] = useState(false)
  const [modalDataUrl, setModalDataUrl] = useState<string | null>(null)

  const [x, y, w, h] = bbox || [0, 0, 0, 0]

  useEffect(() => {
    if (!imageUrl || !w || !h) {
      setLoaded(false)
      return
    }

    setLoaded(false)
    setError(false)

    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.src = imageUrl

    img.onload = () => {
      const canvas = canvasRef.current
      if (!canvas) return

      // 원본 이미지 경계 보정
      const rx = Math.max(0, Math.min(img.naturalWidth - 1, Math.round(x)))
      const ry = Math.max(0, Math.min(img.naturalHeight - 1, Math.round(y)))
      const rw = Math.max(1, Math.min(img.naturalWidth - rx, Math.round(w)))
      const rh = Math.max(1, Math.min(img.naturalHeight - ry, Math.round(h)))

      // 캔버스 크기는 실제 크롭 크기로 지정 (고해상도 유지)
      canvas.width = rw
      canvas.height = rh

      const ctx = canvas.getContext('2d')
      if (ctx) {
        ctx.clearRect(0, 0, rw, rh)
        ctx.drawImage(img, rx, ry, rw, rh, 0, 0, rw, rh)
        try {
          setModalDataUrl(canvas.toDataURL('image/png'))
        } catch {
          // Cross-origin tainted canvas fallback
          setModalDataUrl(null)
        }
      }
      setLoaded(true)
    }

    img.onerror = () => {
      setError(true)
      setLoaded(false)
    }
  }, [imageUrl, x, y, w, h])

  if (!imageUrl) {
    return null
  }

  return (
    <div className="original-crop-card">
      <div className="original-crop-header">
        <div className="crop-title-wrap">
          <ImageIcon size={14} className="crop-icon" />
          <span className="crop-title">원래 이미지 영역 (Original Crop)</span>
        </div>
        <div className="crop-header-actions">
          <span className="crop-dimension">
            {Math.round(w)} × {Math.round(h)} px
          </span>
          {modalDataUrl && (
            <button
              type="button"
              className="crop-zoom-btn"
              title="크롭 확대 보기"
              onClick={() => setShowFullModal(true)}
            >
              <Maximize2 size={12} />
            </button>
          )}
        </div>
      </div>

      <div className="original-crop-container">
        {error ? (
          <div className="crop-error">원본 이미지를 불러올 수 없습니다.</div>
        ) : (
          <>
            <canvas
              ref={canvasRef}
              className="original-crop-canvas"
              title="원본 이미지 크롭 영역"
            />
            {!loaded && <div className="crop-loading">원본 로드 중...</div>}
          </>
        )}
      </div>

      {observedText && (
        <div className="original-crop-observed">
          <span className="label">인식된 텍스트:</span>
          <span className="text">{observedText}</span>
        </div>
      )}

      {/* Full Modal Viewer */}
      {showFullModal && modalDataUrl && (
        <div className="crop-modal-overlay" onClick={() => setShowFullModal(false)}>
          <div className="crop-modal-box" onClick={e => e.stopPropagation()}>
            <div className="crop-modal-header">
              <b>원래 이미지 크롭 고해상도 확대</b>
              <button type="button" className="close-btn" onClick={() => setShowFullModal(false)}>
                ✕
              </button>
            </div>
            <div className="crop-modal-body">
              <img src={modalDataUrl} alt="Original Crop" />
            </div>
            <div className="crop-modal-footer">
              <span>{Math.round(w)} × {Math.round(h)} px | 인식 텍스트: {observedText}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
