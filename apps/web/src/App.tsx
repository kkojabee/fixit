import React, { useState, useRef, useEffect, useCallback } from 'react'
import { Stage, Layer, Image as KonvaImage, Rect, Text as KonvaText, Transformer, Group } from 'react-konva'
import {
  Sparkles,
  Upload,
  Scissors,
  Download,
  LogIn,
  LogOut,
  User,
  Sliders,
  RotateCcw,
  RotateCw,
  Save,
  History,
  FolderOpen,
  Check,
  ZoomIn,
  ZoomOut,
  AlertCircle,
  Eye,
  Trash2,
  X,
  FileText,
  Split,
  Layers,
  Shield,
  Cpu,
  Cloud,
  Clock,
  Lock,
  Activity,
  Image as LucideImage,
  ImagePlus,
  List,
  ChevronLeft,
  ChevronUp,
  ChevronDown,
  Undo2,
  Edit3,
  CheckCircle2,
  Plus
} from 'lucide-react'
import { Region, FontFamily, FontWeight, UserProfile, ProjectInfo, AutoRestoreResult, ComparisonItem, AIModelType, StrataStatus, CompletedThumbnail } from './types'
import { OriginalCropPreview } from './components/OriginalCropPreview'

// Offscreen Canvas 2D for accurate text width measurement (matching backend Pillow FreeType containment)
const measureCanvas = typeof document !== 'undefined' ? document.createElement('canvas') : null
const measureCtx = measureCanvas ? measureCanvas.getContext('2d') : null

function measureTextWidth(text: string, fontSpec: string, letterSpacing: number = 0): number {
  if (!measureCtx || !text) return 0
  try {
    measureCtx.font = fontSpec
    const baseW = measureCtx.measureText(text).width
    const extraSpacing = text.length > 1 ? (text.length - 1) * letterSpacing : 0
    return Math.max(0, baseW + extraSpacing)
  } catch {
    return text.length * 12
  }
}

function wrapTextToWidth(
  text: string,
  maxWidth: number,
  fontSpec: string,
  letterSpacing: number = 0
): string[] {
  if (!text) return []
  const paragraphs = text.split('\n')
  const resultLines: string[] = []

  for (const para of paragraphs) {
    const trimmed = para.trim()
    if (!trimmed) continue

    // If entire paragraph fits within maxWidth, no need to wrap
    if (measureTextWidth(trimmed, fontSpec, letterSpacing) <= maxWidth) {
      resultLines.push(trimmed)
      continue
    }

    const words = trimmed.split(' ')
    let currentLine = ''

    for (const word of words) {
      const candidate = currentLine ? `${currentLine} ${word}` : word
      const w = measureTextWidth(candidate, fontSpec, letterSpacing)

      if (w <= maxWidth) {
        currentLine = candidate
      } else {
        if (currentLine) {
          resultLines.push(currentLine)
          currentLine = ''
        }
        const wordW = measureTextWidth(word, fontSpec, letterSpacing)
        if (wordW <= maxWidth) {
          currentLine = word
        } else {
          // Break word character-by-character
          let chunk = ''
          for (const ch of word) {
            const nextChunk = chunk + ch
            if (measureTextWidth(nextChunk, fontSpec, letterSpacing) <= maxWidth) {
              chunk = nextChunk
            } else {
              if (chunk) resultLines.push(chunk)
              chunk = ch
            }
          }
          currentLine = chunk
        }
      }
    }
    if (currentLine) {
      resultLines.push(currentLine)
    }
  }

  return resultLines.length > 0 ? resultLines : [text]
}

export default function App() {
  // Authentication
  const [token, setToken] = useState<string | null>(localStorage.getItem('fixit_token'))
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null)
  const [showLoginModal, setShowLoginModal] = useState(false)
  const [loginEmail, setLoginEmail] = useState('')
  const [loginPassword, setLoginPassword] = useState('')
  const [loginError, setLoginError] = useState('')

  // Project state
  const [projectId, setProjectId] = useState<number | null>(null)
  const [projectName, setProjectName] = useState<string>('새 프로젝트')
  const [projectVersion, setProjectVersion] = useState<number>(1)
  const [originalImageUrl, setOriginalImageUrl] = useState<string | null>(null)
  const [bgImageUrl, setBgImageUrl] = useState<string | null>(null)
  const [imageSize, setImageSize] = useState<{ width: number; height: number }>({ width: 1200, height: 800 })
  const [bgImageObj, setBgImageObj] = useState<HTMLImageElement | null>(null)
  const [currentMetadata, setCurrentMetadata] = useState<any>(null)

  // Typography regions
  const [regions, setRegions] = useState<Region[]>([])
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const selectedId = selectedIds[0] || null
  const setSelectedId = (id: string | null) => setSelectedIds(id ? [id] : [])
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [activeTool, setActiveTool] = useState<'wysiwyg' | 'cutout'>('wysiwyg')
  const [rightSidebarTab, setRightSidebarTab] = useState<'list' | 'props'>('list')
  const [isProcessing, setIsProcessing] = useState(false)
  const [processingType, setProcessingType] = useState<'analyze' | 'render'>('analyze')
  const [processingStatus, setProcessingStatus] = useState<string>('')
  const [zoom, setZoom] = useState(0.85)
  const [autoFit, setAutoFit] = useState<boolean>(true)

  // View mode: 'edit' (WYSIWYG Canvas Editor) vs 'result' (Rendered Result File Viewer)
  const [viewMode, setViewMode] = useState<'edit' | 'result'>('edit')
  const [currentRenderedUrl, setCurrentRenderedUrl] = useState<string | null>(null)
  const [renderedImageObj, setRenderedImageObj] = useState<HTMLImageElement | null>(null)

  // Marquee drag selection box for multi-selecting text regions
  const [selectionBox, setSelectionBox] = useState<{
    visible: boolean
    x1: number
    y1: number
    x2: number
    y2: number
  } | null>(null)

  // Completed rendered images thumbnails & Version switch modal
  const [completedThumbnails, setCompletedThumbnails] = useState<CompletedThumbnail[]>([])
  const [isGalleryCollapsed, setIsGalleryCollapsed] = useState<boolean>(false)
  const [switchVersionTarget, setSwitchVersionTarget] = useState<CompletedThumbnail | null>(null)

  // AI Model Selection & Local VLM Lock Status State
  const [showModelModal, setShowModelModal] = useState(false)
  const [selectedEngine, setSelectedEngine] = useState<AIModelType>('azure_gpt')
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const [strataStatus, setStrataStatus] = useState<StrataStatus | null>(null)

  // Undo / Redo history
  const [undoStack, setUndoStack] = useState<Region[][]>([])
  const [redoStack, setRedoStack] = useState<Region[][]>([])
  const [isDirty, setIsDirty] = useState(false)

  // Modals & Popups
  const [showProjectsModal, setShowProjectsModal] = useState(false)
  const [projectsList, setProjectsList] = useState<ProjectInfo[]>([])
  const [showRevisionsModal, setShowRevisionsModal] = useState(false)
  const [revisionsList, setRevisionsList] = useState<any[]>([])
  const [comparisons, setComparisons] = useState<ComparisonItem[]>([])
  const [showComparisonModal, setShowComparisonModal] = useState(false)
  const [cutoutModalUrl, setCutoutModalUrl] = useState<string | null>(null)
  const [showOriginalModal, setShowOriginalModal] = useState(false)
  const [recoveryDraft, setRecoveryDraft] = useState<Region[] | null>(null)
  const [showMergeConfirmModal, setShowMergeConfirmModal] = useState(false)
  const [notification, setNotification] = useState<string | null>(null)

  // Drag and Drop State & Refs
  const [isDraggingFile, setIsDraggingFile] = useState(false)
  const dragCounterRef = useRef(0)

  // AI Processing Elapsed Timer
  const [processElapsedSec, setProcessElapsedSec] = useState(0)

  const fileInputRef = useRef<HTMLInputElement>(null)
  const canvasWrapRef = useRef<HTMLDivElement>(null)
  const stageRef = useRef<any>(null)
  const transformerRef = useRef<any>(null)
  const selectedNodeRef = useRef<any>(null)
  const [isExporting, setIsExporting] = useState(false)
  const isExportingRef = useRef(false)

  // Timer effect for AI analysis in-flight
  useEffect(() => {
    let timer: any = null
    if (isProcessing) {
      setProcessElapsedSec(0)
      timer = setInterval(() => {
        setProcessElapsedSec(s => s + 1)
      }, 1000)
    } else {
      setProcessElapsedSec(0)
    }
    return () => {
      if (timer) clearInterval(timer)
    }
  }, [isProcessing])

  const showToast = (msg: string) => {
    setNotification(msg)
    setTimeout(() => setNotification(null), 3000)
  }

  // Track whether custom fonts are fully loaded & ready for Canvas 2D
  const [fontsReady, setFontsReady] = useState(false)

  // Preload primary and fallback fonts so Canvas 2D can render Hanja/special glyphs immediately
  useEffect(() => {
    if (typeof document !== 'undefined' && 'fonts' in document) {
      Promise.allSettled([
        document.fonts.load('400 16px NanumSquare'),
        document.fonts.load('700 16px NanumSquare'),
        document.fonts.load('800 16px NanumSquare'),
        document.fonts.load('400 16px NotoSansKR'),
        document.fonts.load('700 16px NotoSansKR'),
        document.fonts.load('800 16px NotoSansKR'),
        document.fonts.load('400 16px Paperlogy'),
        document.fonts.load('700 16px Paperlogy'),
      ]).then(() => {
        document.fonts.ready.then(() => {
          setFontsReady(true)
          stageRef.current?.batchDraw()
        })
      })
    } else {
      setFontsReady(true)
    }
  }, [])

  // Prevent browser from opening dragged image files in new window/tab
  useEffect(() => {
    const preventDrag = (e: DragEvent) => {
      e.preventDefault()
    }
    window.addEventListener('dragover', preventDrag)
    window.addEventListener('drop', preventDrag)
    return () => {
      window.removeEventListener('dragover', preventDrag)
      window.removeEventListener('drop', preventDrag)
    }
  }, [])

  // Drag and Drop Event Handlers
  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounterRef.current += 1
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setIsDraggingFile(true)
    }
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounterRef.current -= 1
    if (dragCounterRef.current <= 0) {
      dragCounterRef.current = 0
      setIsDraggingFile(false)
    }
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounterRef.current = 0
    setIsDraggingFile(false)

    const files = e.dataTransfer.files
    if (files && files.length > 0) {
      const file = files[0]
      if (file.type.startsWith('image/')) {
        setSelectedEngine('azure_gpt')
        setPendingFile(file)
        setShowModelModal(true)
      } else {
        showToast('이미지 파일(PNG, JPG, WebP)만 지원합니다.')
      }
    }
  }

  // Reset all workspace states to empty initial upload state
  const resetWorkspace = () => {
    setProjectId(null)
    setProjectName('새 프로젝트')
    setProjectVersion(1)
    setOriginalImageUrl(null)
    setBgImageUrl(null)
    setBgImageObj(null)
    setImageSize({ width: 1200, height: 800 })
    setRenderedImageObj(null)
    setCurrentRenderedUrl(null)
    setViewMode('edit')
    setRegions([])
    setSelectedIds([])
    setHoveredId(null)
    setCompletedThumbnails([])
    setUndoStack([])
    setRedoStack([])
    setIsDirty(false)
    setSelectionBox(null)
    setRevisionsList([])
    setCurrentMetadata(null)
    setComparisons([])
    setRecoveryDraft(null)
    try {
      localStorage.removeItem('fixit_draft')
    } catch {
      // ignore
    }
  }

  // Load a project by ID and populate workspace & revision thumbnails
  const loadProject = async (id: number) => {
    setIsProcessing(true)

    // 1. Immediately reset canvas and state to eliminate ghosting from the prior project
    setBgImageObj(null)
    setRenderedImageObj(null)
    setBgImageUrl(null)
    setCurrentRenderedUrl(null)
    setRegions([])
    setSelectedIds([])
    setHoveredId(null)
    setSelectionBox(null)
    setCompletedThumbnails([])
    setUndoStack([])
    setRedoStack([])
    setIsDirty(false)
    try {
      localStorage.removeItem('fixit_draft')
    } catch {
      // ignore
    }

    try {
      const res = await fetch(`/api/projects/${id}`)
      if (!res.ok) throw new Error('프로젝트 로드 실패')
      const data = await res.json()

      setProjectId(data.id)
      setProjectName(data.name)
      setProjectVersion(data.version)
      setOriginalImageUrl(data.original_image_path)

      const cleanBg = data.background_image_path && !data.background_image_path.includes('uploads/')
        ? data.background_image_path
        : null
      const effectiveBg = data.version === 0
        ? data.original_image_path
        : (cleanBg || data.background_image_path || data.original_image_path)

      setBgImageUrl(effectiveBg)
      setCurrentRenderedUrl(data.current_image_path || (data.version === 0 ? data.original_image_path : null))
      setRegions(data.regions || [])
      setCurrentMetadata(data.metadata || null)
      setSelectedIds([])
      setUndoStack([])
      setRedoStack([])
      setIsDirty(false)
      setShowProjectsModal(false)
      setViewMode('edit')
      setActiveTool('wysiwyg')

      // Fetch existing revision thumbnails for filmstrip (deduplicate by version)
      try {
        const revRes = await fetch(`/api/projects/${id}/revisions`)
        if (revRes.ok) {
          const revData = await revRes.json()
          const revMap = new Map<number, any>()
          revData.forEach((r: any) => {
            if (!revMap.has(r.version)) {
              revMap.set(r.version, r)
            }
          })
          const thumbs: CompletedThumbnail[] = Array.from(revMap.values())
            .filter((r: any) => r.image_path)
            .map((r: any) => {
              const label =
                r.version === 0
                  ? '원본 (AI 인식 전)'
                  : r.version === 1
                    ? '초기 AI 복원본'
                    : '고화질 렌더본'
              const revBg = r.background_image_path && !r.background_image_path.includes('uploads/')
                ? r.background_image_path
                : (cleanBg || undefined)
              return {
                id: `rev_${r.id}_v${r.version}`,
                version: r.version,
                imageUrl: r.image_path,
                bgImageUrl: r.version === 0 ? (data.original_image_path || r.image_path) : revBg,
                createdAt: r.created_at ? new Date(r.created_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' }) : `v${r.version}`,
                regions: r.regions || [],
                label
              }
            })

          if (!thumbs.some(t => t.version === 0) && data.original_image_path) {
            thumbs.unshift({
              id: `v0_orig_${Date.now()}`,
              version: 0,
              imageUrl: data.original_image_path,
              bgImageUrl: data.original_image_path,
              createdAt: '원본',
              regions: [],
              label: '원본 (AI 인식 전)'
            })
          }
          thumbs.sort((a, b) => a.version - b.version)
          setCompletedThumbnails(thumbs)

          // Verify and synchronize active version truth from revisions
          const activeRev = thumbs.find(t => t.version === data.version) || (data.version > 0 ? thumbs.find(t => t.version > 0) : null)
          if (activeRev) {
            if (activeRev.regions && activeRev.regions.length > 0) {
              setRegions(activeRev.regions)
            }
            if (data.version > 0 && activeRev.bgImageUrl && !activeRev.bgImageUrl.includes('uploads/')) {
              setBgImageUrl(activeRev.bgImageUrl)
            }
            if (activeRev.imageUrl) {
              setCurrentRenderedUrl(activeRev.imageUrl)
            }
          }
        }
      } catch {
        // ignore
      }

      showToast(`'${data.name}' 프로젝트를 로드했습니다. (${data.regions?.length || 0}개 텍스트 블록)`)
    } catch (err: any) {
      alert(err.message)
    } finally {
      setIsProcessing(false)
    }
  }

  // Auto-load most recently updated project upon login or initial load
  const loadLatestProject = async (authToken?: string) => {
    try {
      const headers: Record<string, string> = {}
      const activeTok = authToken || token
      if (activeTok) headers['Authorization'] = `Bearer ${activeTok}`
      const res = await fetch('/api/projects', { headers })
      if (res.ok) {
        const list: ProjectInfo[] = await res.json()
        if (list && list.length > 0) {
          await loadProject(list[0].id)
        } else {
          resetWorkspace()
        }
      }
    } catch (err) {
      console.debug('[AutoLoad] Failed to load latest project:', err)
    }
  }

  // 1. Fetch current user & Auto login modal prompt & Auto-load latest project
  useEffect(() => {
    if (token) {
      fetch('/api/auth/me', { headers: { Authorization: `Bearer ${token}` } })
        .then(res => res.ok ? res.json() : null)
        .then(data => {
          if (data) {
            setCurrentUser(data)
            setShowLoginModal(false)
            if (!projectId) {
              loadLatestProject(token)
            }
          } else {
            handleLogout()
          }
        })
        .catch(() => handleLogout())
    } else {
      setShowLoginModal(true)
    }
  }, [token])

  // 2. LocalStorage Crash Recovery Check
  useEffect(() => {
    try {
      const savedDraft = localStorage.getItem('fixit_draft')
      if (savedDraft) {
        const parsed = JSON.parse(savedDraft)
        if (parsed.regions && parsed.regions.length > 0 && !projectId) {
          setRecoveryDraft(parsed.regions)
        }
      }
    } catch (e) {
      // ignore
    }
  }, [])

  // 3. Auto-save to LocalStorage with 1-sec debounce
  useEffect(() => {
    if (!isDirty || regions.length === 0) return
    const timer = setTimeout(() => {
      localStorage.setItem('fixit_draft', JSON.stringify({
        projectId,
        projectName,
        originalImageUrl,
        bgImageUrl,
        regions,
        updatedAt: new Date().toISOString()
      }))
    }, 1000)
    return () => clearTimeout(timer)
  }, [regions, isDirty, projectId, projectName, originalImageUrl, bgImageUrl])

  // 4. On-Premise Local Strata VLM Health & Concurrency Lock Status Poller
  const fetchStrataStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/strata/status')
      if (res.ok) {
        const data: StrataStatus = await res.json()
        setStrataStatus(data)
      }
    } catch (err) {
      console.debug('[VLM Status] Fetch failed:', err)
    }
  }, [])

  useEffect(() => {
    fetchStrataStatus()
    const intervalTime = (isProcessing || showModelModal) ? 2500 : 8000
    const timer = setInterval(fetchStrataStatus, intervalTime)
    return () => clearInterval(timer)
  }, [fetchStrataStatus, isProcessing, showModelModal])

  // Dynamic progress status update if waiting in local VLM queue
  useEffect(() => {
    if (isProcessing && selectedEngine.startsWith('strata') && strataStatus) {
      if (strataStatus.busy && strataStatus.waiting_count > 0) {
        setProcessingStatus(
          `사내 로컬 GPU 다른 작업 진행 중입니다. 충돌 방지를 위해 대기열에서 안전 대기 중... (대기: ${strataStatus.waiting_count}명 / 진행: ${Math.round(strataStatus.current_task_elapsed_sec)}초)`
        )
      }
    }
  }, [strataStatus, isProcessing, selectedEngine])

  // Push state to undo stack
  const updateRegionsWithHistory = (newRegions: Region[]) => {
    setUndoStack(prev => [...prev.slice(-29), structuredClone(regions)])
    setRedoStack([])
    setRegions(newRegions)
    setIsDirty(true)
  }

  const handleUndo = () => {
    if (undoStack.length === 0) return
    const previous = undoStack[undoStack.length - 1]
    setRedoStack(prev => [...prev, structuredClone(regions)])
    setUndoStack(prev => prev.slice(0, -1))
    setRegions(previous)
    setIsDirty(true)
    showToast('실행 취소 (Undo)')
  }

  const handleRedo = () => {
    if (redoStack.length === 0) return
    const next = redoStack[redoStack.length - 1]
    setUndoStack(prev => [...prev, structuredClone(regions)])
    setRedoStack(prev => prev.slice(0, -1))
    setRegions(next)
    setIsDirty(true)
    showToast('다시 실행 (Redo)')
  }

  // Handle deleting multiple or single selected text regions (with Undo support)
  const handleDeleteSelectedRegions = () => {
    if (selectedIds.length === 0) return
    const idsToDelete = new Set(selectedIds)
    const next = regions.filter(r => !idsToDelete.has(r.id))
    const count = selectedIds.length
    updateRegionsWithHistory(next)
    setSelectedIds([])
    showToast(count === 1 ? '텍스트 블록이 삭제되었습니다. (Ctrl+Z 복구 가능)' : `${count}개 텍스트 블록이 삭제되었습니다. (Ctrl+Z 복구 가능)`)
  }

  // 4. Keyboard Shortcuts for Undo / Redo / Delete
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      // Ignore shortcut when editing in text inputs, textareas, or contenteditables
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable) return

      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === 'z') {
        e.preventDefault()
        handleUndo()
      } else if (
        ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'z') ||
        ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y')
      ) {
        e.preventDefault()
        handleRedo()
      } else if (e.key === 'Delete' || e.key === 'Backspace') {
        if (selectedIds.length > 0 && viewMode === 'edit') {
          e.preventDefault()
          handleDeleteSelectedRegions()
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [undoStack, redoStack, regions, selectedIds, viewMode])

  const handleDiscardDraft = () => {
    if (window.confirm('정말로 저장되지 않은 모든 수정을 취소하시겠습니까?')) {
      if (undoStack.length > 0) {
        setRegions(undoStack[0])
      }
      setUndoStack([])
      setRedoStack([])
      setIsDirty(false)
      localStorage.removeItem('fixit_draft')
      showToast('모든 수정이 취소되었습니다.')
    }
  }

  // Handle adding a new text region manually
  const handleAddRegion = () => {
    const defaultW = Math.min(220, Math.round((imageSize.width || 1200) * 0.35))
    const defaultH = Math.min(60, Math.round((imageSize.height || 800) * 0.12))

    // Position: canvas center or slight stagger offset
    const offset = (regions.length % 6) * 20
    const centerX = Math.max(20, Math.round(((imageSize.width || 1200) - defaultW) / 2) + offset)
    const centerY = Math.max(20, Math.round(((imageSize.height || 800) - defaultH) / 2) + offset)

    const newRegion: Region = {
      id: `manual_${Date.now()}`,
      observed: '',
      corrected: '새 텍스트 영역',
      bbox: [centerX, centerY, defaultW, defaultH],
      clean_bbox: [centerX, centerY, defaultW, defaultH],
      font_family: 'NanumSquare',
      font_weight: 'Bold',
      font_size: 24,
      scale_x: 0.95,
      letter_spacing: -0.5,
      line_gap: 6,
      text_color: '#000000',
      align: 'center',
      valign: 'center'
    }

    const next = [...regions, newRegion]
    updateRegionsWithHistory(next)
    setSelectedIds([newRegion.id])
    setViewMode('edit')
    setRightSidebarTab('props')
    showToast('새 텍스트 영역이 추가되었습니다.')
  }

  // Handle deleting a single text region
  const handleDeleteRegion = (id: string) => {
    const next = regions.filter(r => r.id !== id)
    updateRegionsWithHistory(next)
    setSelectedIds(prev => prev.filter(selectedId => selectedId !== id))
    showToast('텍스트 영역이 삭제되었습니다.')
  }

  // Responsive auto-fit zoom calculation
  const fitToContainer = useCallback(() => {
    if (!canvasWrapRef.current) return
    const naturalW = bgImageObj ? bgImageObj.naturalWidth : imageSize.width
    const naturalH = bgImageObj ? bgImageObj.naturalHeight : imageSize.height
    if (!naturalW || !naturalH) return

    const container = canvasWrapRef.current
    const availW = container.clientWidth - 48
    const availH = container.clientHeight - 48
    if (availW > 50 && availH > 50) {
      const fitScale = Math.min(availW / naturalW, availH / naturalH, 1.0)
      setZoom(Math.max(0.12, Math.round(fitScale * 100) / 100))
    }
  }, [bgImageObj, imageSize])

  // Load image object when background URL changes
  useEffect(() => {
    // If projectVersion === 0 (Raw Original View), background MUST be originalImageUrl.
    // If projectVersion > 0, background should be cleaned inpainted background (bgImageUrl).
    const targetUrl = projectVersion === 0
      ? (originalImageUrl || bgImageUrl)
      : (bgImageUrl || originalImageUrl || null)
    if (!targetUrl) {
      setBgImageObj(null)
      return
    }
    const img = new window.Image()
    img.crossOrigin = 'anonymous'
    img.src = targetUrl
    img.onload = () => {
      setBgImageObj(img)
      setImageSize({ width: img.naturalWidth, height: img.naturalHeight })

      // Auto fit zoom to canvas window viewport on load if autoFit is active
      if (autoFit) {
        const container = canvasWrapRef.current
        if (container) {
          const availW = container.clientWidth - 48
          const availH = container.clientHeight - 48
          if (availW > 0 && availH > 0 && img.naturalWidth > 0 && img.naturalHeight > 0) {
            const fitScale = Math.min(availW / img.naturalWidth, availH / img.naturalHeight, 1.0)
            setZoom(Math.max(0.12, Math.round(fitScale * 100) / 100))
          }
        }
      }
    }
    img.onerror = () => {
      console.warn('[Canvas] Failed to load background image:', targetUrl)
    }
  }, [bgImageUrl, originalImageUrl, autoFit, projectVersion])

  // Active rendered result image URL for current version (v1, v2+, etc.)
  const activeRenderedUrl =
    currentRenderedUrl ||
    completedThumbnails.find(t => t.version === projectVersion)?.imageUrl ||
    null

  // Preload rendered image object for Result File View
  useEffect(() => {
    if (!activeRenderedUrl) {
      setRenderedImageObj(null)
      return
    }
    const img = new window.Image()
    img.crossOrigin = 'anonymous'
    img.src = activeRenderedUrl
    img.onload = () => {
      setRenderedImageObj(img)
    }
    img.onerror = () => {
      console.warn('[Canvas] Failed to load active rendered image:', activeRenderedUrl)
    }
  }, [activeRenderedUrl])

  // Responsive screen/container resizing listener (Default AutoFit to Window)
  useEffect(() => {
    if (!autoFit) return
    fitToContainer()

    const container = canvasWrapRef.current
    if (!container) return

    let timer: any = null
    const handleResize = () => {
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => {
        fitToContainer()
      }, 50)
    }

    const observer = new ResizeObserver(handleResize)
    observer.observe(container)
    window.addEventListener('resize', handleResize)

    return () => {
      observer.disconnect()
      window.removeEventListener('resize', handleResize)
      if (timer) clearTimeout(timer)
    }
  }, [autoFit, fitToContainer, isGalleryCollapsed, completedThumbnails.length])

  // Immediate re-fit when gallery is toggled or revisions change
  useEffect(() => {
    if (autoFit) {
      const timer = setTimeout(() => {
        fitToContainer()
      }, 60)
      return () => clearTimeout(timer)
    }
  }, [isGalleryCollapsed, completedThumbnails.length, autoFit, fitToContainer])

  // Login handler
  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoginError('')
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: loginEmail, password: loginPassword })
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || '로그인에 실패했습니다.')
      }
      const data = await res.json()
      localStorage.setItem('fixit_token', data.access_token)
      setToken(data.access_token)
      setCurrentUser(data.user)
      setShowLoginModal(false)
      showToast(`환영합니다, ${data.user.name}님!`)
      loadLatestProject(data.access_token)
    } catch (err: any) {
      setLoginError(err.message)
    }
  }

  const handleLogout = () => {
    localStorage.removeItem('fixit_token')
    setToken(null)
    setCurrentUser(null)
    resetWorkspace()
    setShowLoginModal(true)
    showToast('로그아웃되었습니다.')
  }

  // File Upload - Prompts Model Selection Modal
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setSelectedEngine('azure_gpt')
    setPendingFile(file)
    setShowModelModal(true)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  // Execute Analysis with Chosen AI Model
  const startAnalysisWithModel = async (engine: AIModelType) => {
    if (!pendingFile && !originalImageUrl) return
    setShowModelModal(false)
    setProcessingType('analyze')
    setIsProcessing(true)
    setViewMode('edit')
    setActiveTool('wysiwyg')

    const isLocal = engine.startsWith('strata')
    const isLocalBusy = isLocal && strataStatus?.busy

    let statusMsg = ''
    if (isLocalBusy) {
      statusMsg = `사내 로컬 GPU 다른 작업 진행 중입니다. 충돌 방지를 위해 대기열에서 안전 대기 중... (대기: ${(strataStatus?.waiting_count || 0) + 1}명 / 선행 작업 진행: ${Math.round(strataStatus?.current_task_elapsed_sec || 0)}초)`
    } else if (engine === 'strata_non_thinking') {
      statusMsg = '사내 폐쇄망 로컬 모델 (Strata 고속) 분석 중... (예상 약 120초)'
    } else if (engine === 'strata_thinking') {
      statusMsg = '사내 폐쇄망 로컬 모델 (Strata 심층 CoT) 추론 중... (예상 약 3분 40초)'
    } else {
      statusMsg = 'Azure GPT-6.1-sol 고성능 클라우드 모델 분석 중... (예상 약 120초)'
    }
    setProcessingStatus(statusMsg)

    try {
      let activePid = projectId
      // 1. If new file uploaded, create project first
      if (pendingFile) {
        const formData = new FormData()
        formData.append('file', pendingFile)
        formData.append('name', pendingFile.name.replace(/\.[^/.]+$/, ''))

        const resProj = await fetch('/api/projects', {
          method: 'POST',
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          body: formData
        })
        if (!resProj.ok) throw new Error('프로젝트 생성에 실패했습니다.')
        const dataProj = await resProj.json()

        activePid = dataProj.id
        setProjectId(dataProj.id)
        setProjectName(dataProj.name)
        setProjectVersion(0)
        setOriginalImageUrl(dataProj.original_image_path)
        setBgImageUrl(dataProj.original_image_path)

        const v0Thumb: CompletedThumbnail = {
          id: `init_v0_${Date.now()}`,
          version: 0,
          imageUrl: dataProj.original_image_path,
          regions: [],
          createdAt: new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' }),
          label: '원본 (AI 인식 전)'
        }
        setCompletedThumbnails([v0Thumb])
      }

      // 2. Trigger auto restoration with selected model_type
      const restoreForm = new FormData()
      if (pendingFile) {
        restoreForm.append('file', pendingFile)
      } else if (originalImageUrl) {
        const resp = await fetch(originalImageUrl)
        const blob = await resp.blob()
        restoreForm.append('file', blob, 'image.png')
      }
      if (activePid) {
        restoreForm.append('project_id', activePid.toString())
      }
      restoreForm.append('model_type', engine)

      const resRestore = await fetch('/api/restore/auto', {
        method: 'POST',
        body: restoreForm
      })
      if (!resRestore.ok) {
        const errorData = await resRestore.json().catch(() => null)
        throw new Error(
          typeof errorData?.detail === 'string'
            ? errorData.detail
            : 'AI 분석 및 복원에 실패했습니다.'
        )
      }
      const data: AutoRestoreResult = await resRestore.json()

      setBgImageUrl(data.background_image_url)
      setRegions(data.regions)
      setComparisons(data.comparisons || [])
      setCurrentMetadata(data.metadata || null)
      setSelectedIds([])
      setUndoStack([])
      setRedoStack([])
      setProjectVersion(1)
      setIsDirty(false)
      setViewMode('edit')
      setActiveTool('wysiwyg')
      setRightSidebarTab('list')

      if (data.restored_image_url) {
        setCurrentRenderedUrl(data.restored_image_url)
        const initThumb: CompletedThumbnail = {
          id: `init_v1_${Date.now()}`,
          version: 1,
          imageUrl: data.restored_image_url,
          bgImageUrl: data.background_image_url,
          regions: [...data.regions],
          createdAt: new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' }),
          label: '초기 AI 복원본'
        }
        setCompletedThumbnails(prev => {
          const hasV0 = prev.some(t => t.version === 0)
          const v0Thumb: CompletedThumbnail = {
            id: `init_v0_${Date.now()}`,
            version: 0,
            imageUrl: originalImageUrl || '',
            bgImageUrl: originalImageUrl || '',
            regions: [],
            createdAt: new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' }),
            label: '원본 (AI 인식 전)'
          }
          const baseList = hasV0 ? prev.filter(t => t.version !== 1) : [v0Thumb, ...prev.filter(t => t.version !== 1)]
          return [...baseList, initThumb].sort((a, b) => a.version - b.version)
        })
      }

      const engineLabel =
        engine === 'strata_non_thinking'
          ? '로컬 Strata 고속'
          : engine === 'strata_thinking'
            ? '로컬 Strata 심층 CoT'
            : 'Azure GPT-6.1-sol'
      showToast(`${engineLabel} 분석 완료! (${data.regions.length}개 블록 인식, ${data.metadata?.elapsed_sec || ''}초)`)
    } catch (err: any) {
      showToast(err.message || 'AI 분석 및 복원 중 오류가 발생했습니다.')
    } finally {
      setIsProcessing(false)
      setProcessingStatus('')
      setPendingFile(null)
    }
  }

  // Save Project to Database
  const handleSaveProject = async () => {
    if (!projectId) {
      showToast('프로젝트를 먼저 생성해 주세요.')
      return
    }
    // 사용자가 저장 버튼을 눌러도 이전 버전에 비해 변경이 없는 경우에는 "변경된 사항이 없습니다" 표출하고 저장안함
    if (!isDirty) {
      showToast('변경된 사항이 없습니다.')
      return
    }

    setIsProcessing(true)
    try {
      // V2에서 V1돌아와서 변경후 저장하는 경우 V3가 되며 V1에서 변경되었음을 표기함
      const allVersions = completedThumbnails.map(t => t.version).concat([projectVersion])
      const maxVer = Math.max(...allVersions, 0)
      const nextVer = maxVer + 1
      const prevVer = projectVersion

      const res = await fetch(`/api/projects/${projectId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: projectName,
          regions: regions,
          current_image_url: currentRenderedUrl || bgImageUrl,
          background_image_url: bgImageUrl,
          set_version: nextVer
        })
      })
      if (!res.ok) throw new Error('저장에 실패했습니다.')
      const data = await res.json()
      setProjectVersion(nextVer)
      setIsDirty(false)
      localStorage.removeItem('fixit_draft')

      // Add to completed thumbnails filmstrip bar
      const newThumb: CompletedThumbnail = {
        id: `save_v${nextVer}_${Date.now()}`,
        version: nextVer,
        imageUrl: currentRenderedUrl || bgImageUrl || originalImageUrl || '',
        bgImageUrl: bgImageUrl || undefined,
        regions: structuredClone(regions),
        createdAt: new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' }),
        label: `v${prevVer} 기반 수정본`
      }
      setCompletedThumbnails(prev => {
        const filtered = prev.filter(t => t.version !== nextVer)
        return [...filtered, newThumb].sort((a, b) => a.version - b.version)
      })

      showToast(`v${prevVer}에서 변경되어 v${nextVer} 새 버전으로 저장되었습니다.`)
    } catch (err: any) {
      alert(err.message)
    } finally {
      setIsProcessing(false)
    }
  }

  // Final High-Res Render & Download (100% WYSIWYG Unified Composite)
  const handleFinalRender = async () => {
    if (!bgImageUrl) return
    setProcessingType('render')
    setProcessingStatus('지정된 폰트와 스타일을 바탕으로 고화질 합성을 진행하고 있습니다...')
    setIsProcessing(true)
    try {
      // 100% WYSIWYG Unification: Capture exact text layer from Konva stage at 1:1 image resolution
      let textLayerDataUrl: string | undefined = undefined
      if (stageRef.current && imageSize.width > 0 && imageSize.height > 0) {
        try {
          isExportingRef.current = true
          setIsExporting(true)
          setSelectedIds([])

          await new Promise(r => setTimeout(r, 60))
          if (stageRef.current) {
            stageRef.current.batchDraw()
            const layers = stageRef.current.getLayers()
            const bgLayer = layers[0]
            const wasBgVis = bgLayer ? bgLayer.visible() : true
            if (bgLayer) bgLayer.visible(false)
            stageRef.current.batchDraw()

            textLayerDataUrl = stageRef.current.toDataURL({
              pixelRatio: 1 / zoom,
              x: 0,
              y: 0,
              width: imageSize.width * zoom,
              height: imageSize.height * zoom
            })

            if (bgLayer) bgLayer.visible(wasBgVis)
            stageRef.current.batchDraw()
          }
        } catch (e) {
          console.warn('Canvas text layer export fallback:', e)
        } finally {
          isExportingRef.current = false
          setIsExporting(false)
        }
      }

      const res = await fetch('/api/restore/render', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          background_image_url: bgImageUrl,
          original_image_url: originalImageUrl,
          regions: regions,
          text_layer_image: textLayerDataUrl
        })
      })
      if (!res.ok) throw new Error('최종 렌더링에 실패했습니다.')
      const data = await res.json()

      // Sync background image if newly re-inpainted with expanded masking regions
      if (data.background_image_url) {
        setBgImageUrl(data.background_image_url)
      }

      // Increment version ONLY if modifications were made (isDirty === true)
      const willIncrement = isDirty
      const allVersions = completedThumbnails.map(t => t.version).concat([projectVersion])
      const maxVer = Math.max(...allVersions, 0)
      const nextVer = willIncrement ? maxVer + 1 : projectVersion
      const prevVer = projectVersion
      setProjectVersion(nextVer)
      setIsDirty(false)
      setCurrentRenderedUrl(data.restored_image_url)
      setViewMode('result')

      showToast(willIncrement ? `v${prevVer}에서 변경되어 v${nextVer} 새 버전 렌더링이 완료되었습니다.` : `v${nextVer} 고화질 렌더링이 완료되었습니다.`)

      // Add to completed thumbnails filmstrip bar
      const newThumb: CompletedThumbnail = {
        id: `render_v${nextVer}_${Date.now()}`,
        version: nextVer,
        imageUrl: data.restored_image_url,
        bgImageUrl: data.background_image_url || bgImageUrl || undefined,
        regions: [...regions],
        createdAt: new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' }),
        label: nextVer === 0 ? '원본 (AI 인식 전)' : nextVer === 1 ? '초기 AI 복원본' : (willIncrement ? `v${prevVer} 기반 렌더본` : '고화질 렌더본')
      }
      setCompletedThumbnails(prev => {
        const filtered = prev.filter(t => t.version !== nextVer)
        return [...filtered, newThumb].sort((a, b) => a.version - b.version)
      })

      // Sync project image with newly rendered version in database
      if (projectId) {
        fetch(`/api/projects/${projectId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: projectName,
            regions: regions,
            current_image_url: data.restored_image_url,
            background_image_url: data.background_image_url || bgImageUrl,
            set_version: nextVer
          })
        }).catch(() => { })
      }
    } catch (err: any) {
      alert(err.message)
    } finally {
      setIsProcessing(false)
      setProcessingStatus('')
    }
  }

  // Load Projects List
  const openProjectsModal = async () => {
    try {
      const res = await fetch('/api/projects', {
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      })
      if (res.ok) {
        const data = await res.json()
        setProjectsList(data)
        setShowProjectsModal(true)
      }
    } catch (err) {
      showToast('프로젝트 목록을 불러오지 못했습니다.')
    }
  }

  // Delete Project
  const handleDeleteProject = async (pId: number, pName: string) => {
    if (!window.confirm(`'${pName}' 프로젝트를 완전히 삭제하시겠습니까? 관련된 모든 리비전과 작업 데이터가 삭제되며 되돌릴 수 없습니다.`)) {
      return
    }
    setIsProcessing(true)
    try {
      const res = await fetch(`/api/projects/${pId}`, {
        method: 'DELETE'
      })
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.detail || '프로젝트 삭제에 실패했습니다.')
      }
      const data = await res.json()
      showToast(data.message)

      // Fetch the updated latest projects list from API to reflect current truth
      let remainingList: ProjectInfo[] = []
      try {
        const pRes = await fetch('/api/projects', {
          headers: token ? { Authorization: `Bearer ${token}` } : {}
        })
        if (pRes.ok) {
          remainingList = await pRes.json()
        }
      } catch {
        remainingList = projectsList.filter(p => p.id !== pId)
      }
      setProjectsList(remainingList)

      // If active project was deleted OR no projects remain at all in DB
      if (projectId === pId || remainingList.length === 0) {
        if (remainingList.length > 0) {
          // Switch to the first remaining project
          await loadProject(remainingList[0].id)
        } else {
          // All projects deleted: clean reset to initial upload state
          resetWorkspace()
        }
      }
    } catch (err: any) {
      alert(err.message)
    } finally {
      setIsProcessing(false)
    }
  }

  // Load Revisions List
  const openRevisionsModal = async () => {
    if (!projectId) return
    try {
      const res = await fetch(`/api/projects/${projectId}/revisions`)
      if (res.ok) {
        const data = await res.json()
        setRevisionsList(data)
        setShowRevisionsModal(true)
      }
    } catch (err) {
      showToast('리비전 목록 로드 실패')
    }
  }

  const restoreRevision = async (targetVer: number) => {
    if (!projectId) return
    setIsProcessing(true)
    try {
      const form = new FormData()
      form.append('target_version', targetVer.toString())
      const res = await fetch(`/api/projects/${projectId}/revisions/restore`, {
        method: 'POST',
        body: form
      })
      if (!res.ok) throw new Error('버전 복원 실패')
      const data = await res.json()
      setProjectVersion(data.version)
      setRegions(data.regions || [])
      // 캔버스 편집 배경은 반드시 해당 버전의 인페인팅 배경(background_image_path)을 설정
      if (data.background_image_path) {
        setBgImageUrl(data.background_image_path)
      }
      // 렌더링 완성본은 결과 뷰에 설정
      if (data.current_image_path) {
        setCurrentRenderedUrl(data.current_image_path)
      }
      // 해당 버전의 VLM 메타데이터 복원
      if (data.metadata) {
        setCurrentMetadata(data.metadata)
      }
      setSelectedIds([])
      setUndoStack([])
      setRedoStack([])
      setIsDirty(false)
      setShowRevisionsModal(false)
      showToast(data.message)
    } catch (err: any) {
      alert(err.message)
    } finally {
      setIsProcessing(false)
    }
  }

  // Delete a specific revision/version
  const handleDeleteRevision = async (targetVer: number) => {
    if (!projectId) return
    if (!window.confirm(`정말 v${targetVer} 버전을 삭제하시겠습니까? 삭제된 버전은 복구할 수 없습니다.`)) {
      return
    }
    try {
      const res = await fetch(`/api/projects/${projectId}/revisions/${targetVer}`, {
        method: 'DELETE'
      })
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.detail || '버전 삭제에 실패했습니다.')
      }
      const data = await res.json()

      // 1. 썸네일 스트립 및 리비전 목록에서 삭제된 버전 제거
      const nextThumbnails = completedThumbnails.filter(t => t.version !== targetVer)
      setCompletedThumbnails(nextThumbnails)
      setRevisionsList(prev => prev.filter(r => r.version !== targetVer))

      // 2. 버전 전환 모달이 열려있었다면 닫기
      if (switchVersionTarget && switchVersionTarget.version === targetVer) {
        setSwitchVersionTarget(null)
      }

      // 3. 가장 최신 버전이 삭제되거나 현재 작업 중인 버전이 삭제된 경우: 자동으로 이전 최신 버전으로 이동
      const isCurrentVersion = targetVer === projectVersion
      const wasLatestVersion = !completedThumbnails.some(t => t.version > targetVer)

      if (isCurrentVersion || wasLatestVersion) {
        if (nextThumbnails.length > 0) {
          const nextLatest = nextThumbnails.reduce((prev, curr) => curr.version > prev.version ? curr : prev)
          await executeSwitchVersion(nextLatest)
          showToast(`v${targetVer} 버전이 삭제되었으며, 이전 최신 버전(v${nextLatest.version})으로 자동 이동했습니다.`)
          return
        }
      }

      showToast(data.message || `v${targetVer} 버전이 삭제되었습니다.`)
    } catch (err: any) {
      alert(err.message)
    }
  }

  // Core version switch execution
  const executeSwitchVersion = async (target: CompletedThumbnail) => {
    try {
      if (projectId) {
        const form = new FormData()
        form.append('target_version', target.version.toString())
        const res = await fetch(`/api/projects/${projectId}/revisions/restore`, {
          method: 'POST',
          body: form
        })
        if (res.ok) {
          const data = await res.json()
          setProjectVersion(data.version)
          setRegions(data.regions || [])

          // 1. 캔버스 편집 배경은 반드시 해당 버전의 인페인팅 배경(background_image_path) 설정
          if (target.version === 0) {
            setBgImageUrl(data.original_image_path || originalImageUrl || target.imageUrl)
            setCurrentRenderedUrl(data.original_image_path || originalImageUrl || target.imageUrl)
            setRegions([])
            setCurrentMetadata(null)
          } else {
            let cleanBg = (data.background_image_path && !data.background_image_path.includes('uploads/'))
              ? data.background_image_path
              : (target.bgImageUrl && !target.bgImageUrl.includes('uploads/'))
                ? target.bgImageUrl
                : null
            if (!cleanBg) {
              const found = completedThumbnails.find(t => t.version > 0 && t.bgImageUrl && !t.bgImageUrl.includes('uploads/'))
              if (found) cleanBg = found.bgImageUrl
            }
            if (cleanBg) {
              setBgImageUrl(cleanBg)
            }
            // 2. 렌더링 완성본은 결과 뷰에 설정
            setCurrentRenderedUrl(target.imageUrl || data.current_image_path)
            // 3. 메타데이터 복원
            if (data.metadata) {
              setCurrentMetadata(data.metadata)
            }
          }

          setSelectedIds([])
          setHoveredId(null)
          setSelectionBox(null)
          setRenderedImageObj(null)
          setUndoStack([])
          setRedoStack([])
          setIsDirty(false)
          setViewMode('edit')
          setActiveTool('wysiwyg')
          showToast(target.version === 0 ? 'v0 원본 이미지(AI 인식 전) 상태로 전환되었습니다.' : `v${data.version} 버전으로 이동했습니다.`)
          return
        }
      }

      // Fallback if no project ID or local state
      if (target.regions !== undefined) {
        setProjectVersion(target.version)
        setRegions(target.regions || [])
      }
      if (target.version === 0) {
        setBgImageUrl(originalImageUrl || target.imageUrl)
        setCurrentRenderedUrl(originalImageUrl || target.imageUrl)
        setRegions([])
        setCurrentMetadata(null)
      } else if (target.bgImageUrl && !target.bgImageUrl.includes('uploads/')) {
        setBgImageUrl(target.bgImageUrl)
      }
      setCurrentRenderedUrl(target.imageUrl)
      setRenderedImageObj(null)
      setSelectedIds([])
      setHoveredId(null)
      setSelectionBox(null)
      setUndoStack([])
      setRedoStack([])
      setIsDirty(false)
      setViewMode('edit')
      setActiveTool('wysiwyg')
      showToast(target.version === 0 ? 'v0 원본 이미지(AI 인식 전) 상태로 전환되었습니다.' : `v${target.version} 상태로 전환되었습니다.`)
    } catch (err: any) {
      alert('버전 전환 중 오류가 발생했습니다: ' + err.message)
    }
  }

  // Request version switch from completed thumbnails bar
  const handleRequestSwitchVersion = (thumb: CompletedThumbnail) => {
    if (thumb.version === projectVersion) {
      showToast(`현재 편집 중인 버전(v${projectVersion})입니다.`)
      return
    }
    if (isDirty) {
      // Changes pending: Ask user whether to save to DB or keep in session draft
      setSwitchVersionTarget(thumb)
    } else {
      // Clean state: Switch directly without prompt
      executeSwitchVersion(thumb)
    }
  }

  // Option 1: Save current work to DB and switch
  const handleConfirmSwitchWithSave = async () => {
    if (!switchVersionTarget) return
    const target = switchVersionTarget
    setSwitchVersionTarget(null)

    if (projectId) {
      try {
        const allVersions = completedThumbnails.map(t => t.version).concat([projectVersion])
        const maxVer = Math.max(...allVersions, 0)
        const nextVer = maxVer + 1
        const prevVer = projectVersion
        await fetch(`/api/projects/${projectId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: projectName,
            regions: regions,
            current_image_url: currentRenderedUrl || bgImageUrl,
            background_image_url: bgImageUrl,
            set_version: nextVer
          })
        })
        const newThumb: CompletedThumbnail = {
          id: `save_v${nextVer}_${Date.now()}`,
          version: nextVer,
          imageUrl: currentRenderedUrl || bgImageUrl || originalImageUrl || '',
          bgImageUrl: bgImageUrl || undefined,
          regions: structuredClone(regions),
          createdAt: new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' }),
          label: `v${prevVer} 기반 수정본`
        }
        setCompletedThumbnails(prev => {
          const filtered = prev.filter(t => t.version !== nextVer)
          return [...filtered, newThumb].sort((a, b) => a.version - b.version)
        })
        showToast(`v${prevVer}에서 변경되어 v${nextVer} 새 버전으로 자동 저장되었습니다.`)
      } catch (e) {
        console.error('Save failed before switch:', e)
      }
    }
    await executeSwitchVersion(target)
  }

  // Option 2: Keep current work in session/localStorage draft and switch without DB save
  const handleConfirmSwitchKeepSessionDraft = async () => {
    if (!switchVersionTarget) return
    const target = switchVersionTarget
    setSwitchVersionTarget(null)

    // Save to local session draft
    localStorage.setItem('fixit_draft', JSON.stringify({
      projectId,
      projectName,
      originalImageUrl,
      bgImageUrl,
      regions,
      savedFromVersion: projectVersion,
      updatedAt: new Date().toISOString()
    }))

    showToast(`현재 v${projectVersion} 작업 내용은 브라우저 세션에 안전하게 보존되었습니다.`)
    await executeSwitchVersion(target)
  }

  // Marquee Drag Selection: Mouse down on canvas background
  const handleStageMouseDown = (e: any) => {
    if (viewMode !== 'edit' || activeTool === 'cutout') return
    const stage = e.target.getStage()
    if (!stage) return

    // Allow dragging selection box when clicking empty stage or canvas background image
    const isStage = e.target === stage
    const isBgImg = e.target.name && e.target.name() === 'bg-canvas-image'

    if (isStage || isBgImg) {
      const pointer = stage.getPointerPosition()
      if (!pointer) return
      const sx = pointer.x / zoom
      const sy = pointer.y / zoom
      setSelectionBox({
        visible: true,
        x1: sx,
        y1: sy,
        x2: sx,
        y2: sy
      })

      // If user isn't holding Ctrl/Cmd/Shift, clear previous selection on background click
      const isMultiKey = e.evt.ctrlKey || e.evt.metaKey || e.evt.shiftKey
      if (!isMultiKey) {
        setSelectedIds([])
      }
    }
  }

  // Marquee Drag Selection: Mouse move
  const handleStageMouseMove = (e: any) => {
    if (!selectionBox || !selectionBox.visible) return
    const stage = e.target.getStage()
    if (!stage) return
    const pointer = stage.getPointerPosition()
    if (!pointer) return
    const sx = pointer.x / zoom
    const sy = pointer.y / zoom
    setSelectionBox(prev => prev ? { ...prev, x2: sx, y2: sy } : null)
  }

  // Marquee Drag Selection: Mouse up & hit detection
  const handleStageMouseUp = (e: any) => {
    if (!selectionBox || !selectionBox.visible) return
    const bx = Math.min(selectionBox.x1, selectionBox.x2)
    const by = Math.min(selectionBox.y1, selectionBox.y2)
    const bw = Math.abs(selectionBox.x2 - selectionBox.x1)
    const bh = Math.abs(selectionBox.y2 - selectionBox.y1)

    // Check if drag was intentional (more than 4px distance)
    if (bw > 4 || bh > 4) {
      const isMultiKey = e.evt.ctrlKey || e.evt.metaKey || e.evt.shiftKey
      const hitIds = regions
        .filter(reg => {
          const [rx, ry, rw, rh] = reg.bbox
          // Standard AABB bounding box collision test
          return !(rx > bx + bw || rx + rw < bx || ry > by + bh || ry + rh < by)
        })
        .map(reg => reg.id)

      if (hitIds.length > 0) {
        if (isMultiKey) {
          setSelectedIds(prev => Array.from(new Set([...prev, ...hitIds])))
        } else {
          setSelectedIds(hitIds)
        }
        setRightSidebarTab('props')
      }
    }

    setSelectionBox(null)
  }

  // Interactive Cutout Click
  const handleStageClick = async (e: any) => {
    if (activeTool !== 'cutout') return
    const stage = e.target.getStage()
    const pointer = stage.getPointerPosition()
    if (!pointer) return

    // Transform pointer position from stage to original image coordinates
    const scale = zoom
    const origX = Math.round(pointer.x / scale)
    const origY = Math.round(pointer.y / scale)

    const targetUrl = originalImageUrl || bgImageUrl
    if (!targetUrl) return

    setIsProcessing(true)
    try {
      const res = await fetch('/api/cutout/click', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image_url: targetUrl,
          click_x: origX,
          click_y: origY,
          radius: 180
        })
      })
      if (!res.ok) throw new Error('누끼따기에 실패했습니다.')
      const data = await res.json()
      setCutoutModalUrl(data.cutout_url)
      showToast('피사체 누끼따기가 완료되었습니다!')
    } catch (err: any) {
      alert(err.message)
    } finally {
      setIsProcessing(false)
    }
  }

  // Selected region helper (Primary active item)
  const selectedRegion = regions.find(r => selectedIds.includes(r.id)) || null

  // Batch or single field updater for all currently selected regions
  const updateSelectedField = (field: keyof Region, value: any) => {
    if (selectedIds.length === 0) return
    const next = regions.map(r => {
      if (selectedIds.includes(r.id)) {
        return { ...r, [field]: value }
      }
      return r
    })
    updateRegionsWithHistory(next)
  }

  // Bounding box / masking region updater (X, Y, W, H)
  const updateBboxField = (index: number, value: number) => {
    if (selectedIds.length === 0) return
    const next = regions.map(r => {
      if (selectedIds.includes(r.id)) {
        const newBbox = [...r.bbox] as [number, number, number, number]
        newBbox[index] = value
        return {
          ...r,
          bbox: newBbox,
          clean_bbox: newBbox
        }
      }
      return r
    })
    updateRegionsWithHistory(next)
  }

  // Expand masking area by pad px in all directions
  const handleExpandMask = (regionId: string, pad: number) => {
    const next = regions.map(r => {
      if (r.id === regionId) {
        const [x, y, w, h] = r.bbox
        const newX = Math.max(0, x - pad)
        const newY = Math.max(0, y - pad)
        const newW = w + pad * 2
        const newH = h + pad * 2
        const newBbox: [number, number, number, number] = [newX, newY, newW, newH]
        return {
          ...r,
          bbox: newBbox,
          clean_bbox: newBbox
        }
      }
      return r
    })
    updateRegionsWithHistory(next)
    showToast(`마스킹 영역이 +${pad}px 확장되었습니다.`)
  }

  // Split Block Handler: Splits multi-line region into two independent blocks
  const handleSplitRegion = (regionId: string, splitLineIndex: number) => {
    const target = regions.find(r => r.id === regionId)
    if (!target) return
    const lines = target.corrected.split('\n')
    if (lines.length <= 1 || splitLineIndex <= 0 || splitLineIndex >= lines.length) return

    const topLines = lines.slice(0, splitLineIndex)
    const bottomLines = lines.slice(splitLineIndex)

    const [rx, ry, rw, rh] = target.bbox
    const topRatio = topLines.length / lines.length
    const topH = Math.max(16, Math.round(rh * topRatio))
    const botH = Math.max(16, rh - topH)
    const botY = ry + topH

    const topObserved = target.observed ? target.observed.split('\n').slice(0, splitLineIndex).join('\n') || target.observed : ''
    const botObserved = target.observed ? target.observed.split('\n').slice(splitLineIndex).join('\n') || target.observed : ''

    const topRegion: Region = {
      ...target,
      corrected: topLines.join('\n'),
      observed: topObserved,
      bbox: [rx, ry, rw, topH],
      clean_bbox: target.clean_bbox ? [target.clean_bbox[0], target.clean_bbox[1], target.clean_bbox[2], Math.round(target.clean_bbox[3] * topRatio)] : undefined
    }

    const newId = `${target.id}_part2_${Date.now()}`
    const bottomRegion: Region = {
      ...target,
      id: newId,
      corrected: bottomLines.join('\n'),
      observed: botObserved,
      bbox: [rx, botY, rw, botH],
      clean_bbox: target.clean_bbox ? [target.clean_bbox[0], target.clean_bbox[1] + Math.round(target.clean_bbox[3] * topRatio), target.clean_bbox[2], target.clean_bbox[3] - Math.round(target.clean_bbox[3] * topRatio)] : undefined
    }

    const next = regions.flatMap(r => r.id === regionId ? [topRegion, bottomRegion] : [r])
    updateRegionsWithHistory(next)
    setSelectedIds([topRegion.id, bottomRegion.id])
    showToast(`블록이 2개(상단 ${topLines.length}줄, 하단 ${bottomLines.length}줄)로 분할되었습니다.`)
  }

  // Merge Selected Regions Handler: Merges multiple selected blocks into a single block
  const handleRequestMerge = () => {
    if (selectedIds.length < 2) {
      showToast('병합할 영역을 2개 이상 선택해 주세요. (Shift 또는 Ctrl+클릭)')
      return
    }
    setShowMergeConfirmModal(true)
  }

  const confirmExecuteMerge = () => {
    const selectedRegions = selectedIds
      .map(id => regions.find(r => r.id === id))
      .filter(Boolean) as Region[]

    if (selectedRegions.length < 2) {
      setShowMergeConfirmModal(false)
      return
    }

    // First selected region is the anchor for styles
    const firstRegion = selectedRegions[0]

    // Calculate union bounding box (min_x, min_y, max_x, max_y)
    const minX = Math.min(...selectedRegions.map(r => r.bbox[0]))
    const minY = Math.min(...selectedRegions.map(r => r.bbox[1]))
    const maxX = Math.max(...selectedRegions.map(r => r.bbox[0] + r.bbox[2]))
    const maxY = Math.max(...selectedRegions.map(r => r.bbox[1] + r.bbox[3]))

    // Calculate union clean_bbox
    const cMinX = Math.min(...selectedRegions.map(r => (r.clean_bbox ? r.clean_bbox[0] : r.bbox[0])))
    const cMinY = Math.min(...selectedRegions.map(r => (r.clean_bbox ? r.clean_bbox[1] : r.bbox[1])))
    const cMaxX = Math.max(...selectedRegions.map(r => (r.clean_bbox ? r.clean_bbox[0] + r.clean_bbox[2] : r.bbox[0] + r.bbox[2])))
    const cMaxY = Math.max(...selectedRegions.map(r => (r.clean_bbox ? r.clean_bbox[1] + r.clean_bbox[3] : r.bbox[1] + r.bbox[3])))

    // Merge text lines in order
    const mergedCorrected = selectedRegions.map(r => r.corrected).join('\n')
    const mergedObserved = selectedRegions.map(r => r.observed || r.corrected).join('\n')

    const mergedRegion: Region = {
      ...firstRegion,
      bbox: [minX, minY, Math.max(10, maxX - minX), Math.max(10, maxY - minY)],
      clean_bbox: [cMinX, cMinY, Math.max(10, cMaxX - cMinX), Math.max(10, cMaxY - cMinY)],
      corrected: mergedCorrected,
      observed: mergedObserved
    }

    // Replace firstRegion with mergedRegion, remove the other selected regions
    const nextRegions = regions.flatMap(r => {
      if (r.id === firstRegion.id) return [mergedRegion]
      if (selectedIds.includes(r.id)) return []
      return [r]
    })

    updateRegionsWithHistory(nextRegions)
    setSelectedIds([mergedRegion.id])
    setShowMergeConfirmModal(false)
    showToast(`${selectedRegions.length}개 텍스트 영역이 성공적으로 병합되었습니다. (Ctrl+Z 취소 가능)`)
  }

  // Konva Transformer binding for single or multi-selection
  useEffect(() => {
    if (selectedIds.length > 0 && transformerRef.current && stageRef.current) {
      const selectedNodes = selectedIds
        .map(id => stageRef.current.findOne(`#node-${id}`))
        .filter(Boolean)
      if (selectedNodes.length > 0) {
        transformerRef.current.nodes(selectedNodes)
        transformerRef.current.getLayer()?.batchDraw()
      } else {
        transformerRef.current.nodes([])
      }
    } else if (transformerRef.current) {
      transformerRef.current.nodes([])
    }
  }, [selectedIds, regions])

  return (
    <div
      className="app-container"
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Invisible Font Warmers: Forces browser layout engine to rasterize Hanja glyphs for Canvas 2D fallback */}
      <div style={{ position: 'absolute', width: 0, height: 0, overflow: 'hidden', opacity: 0, pointerEvents: 'none' }} aria-hidden="true">
        <span style={{ fontFamily: 'NanumSquare, NotoSansKR, sans-serif', fontWeight: 800 }}>先 1단계 체계 완비 S/W 구축</span>
        <span style={{ fontFamily: 'NotoSansKR, sans-serif', fontWeight: 800 }}>先 1단계 체계 완비 S/W 구축</span>
        <span style={{ fontFamily: 'NotoSansKR, sans-serif', fontWeight: 700 }}>先 1단계 체계 완비 S/W 구축</span>
        <span style={{ fontFamily: 'NotoSansKR, sans-serif', fontWeight: 400 }}>先 1단계 체계 완비 S/W 구축</span>
        <span style={{ fontFamily: 'Paperlogy, NotoSansKR, sans-serif', fontWeight: 700 }}>先 1단계 체계 완비 S/W 구축</span>
      </div>
      {/* Drag & Drop Fullscreen Upload Overlay */}
      {isDraggingFile && (
        <div
          className="drag-drop-overlay"
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <div className="drag-drop-box">
            <div className="drag-drop-icon">
              <Upload size={34} />
            </div>
            <h3>이미지를 여기에 놓으세요</h3>
            <p>고해상도 이미지(PNG, JPG, WebP)를 놓으면 AI 모델 선택 및 OCR 복원이 시작됩니다.</p>
          </div>
        </div>
      )}

      {/* Toast Notification */}
      {notification && (
        <div className="toast-notification">
          <Check size={14} /> {notification}
        </div>
      )}

      {/* Header */}
      <header>
        <div className="brand">
          <img src="/fixit.png" alt="Fixit Logo" className="brand-logo-img" />
          <span>Fixit</span>
          <span className="brand-sub">STUDIO</span>
        </div>

        <div className="header-center">
          <span className="dot" />
          <b>{projectName}</b>
          <span className="version-badge">v{projectVersion}</span>
          {isDirty && <span className="draft-badge">미저장 초안</span>}
          {bgImageObj && (
            <span className="header-meta-size">{imageSize.width} × {imageSize.height} px</span>
          )}

          {currentMetadata && (
            <span className={`model-tag-badge ${currentMetadata.is_airgapped_secure ? 'local' : 'azure'}`}>
              {currentMetadata.is_airgapped_secure ? '🛡️ 로컬 폐쇄망' : '⚡ Azure 클라우드'}
              {currentMetadata.elapsed_sec ? ` (${currentMetadata.elapsed_sec}s)` : ''}
            </span>
          )}

          {/* On-premise Strata VLM live status chip */}
          <div className="strata-status-badge" title="사내 폐쇄망 온프레미스 GPU(Strata) 실시간 가동 상태">
            {strataStatus ? (
              strataStatus.online ? (
                strataStatus.busy ? (
                  <span className="chip busy">
                    <span className="indicator-dot orange" />
                    <span>로컬 GPU 사용 중 ({strataStatus.waiting_count}명 대기, {Math.round(strataStatus.current_task_elapsed_sec)}s)</span>
                  </span>
                ) : (
                  <span className="chip ready">
                    <span className="indicator-dot green" />
                    <span>로컬 GPU 대기 완료 (유휴)</span>
                  </span>
                )
              ) : (
                <span className="chip offline">
                  <span className="indicator-dot red" />
                  <span>로컬 VLM 오프라인</span>
                </span>
              )
            ) : (
              <span className="chip checking">
                <span className="indicator-dot gray" />
                <span>로컬 확인 중</span>
              </span>
            )}
          </div>
        </div>

        <div className="header-actions">
          {/* New Work / Clear Canvas */}
          <button
            className="outline small header-action-btn"
            title="새 작업 시작 (캔버스 초기화)"
            data-tooltip="새 작업"
            onClick={() => {
              if (isDirty && !window.confirm('저장되지 않은 작업 내용이 있습니다. 새 작업을 시작하시겠습니까?')) {
                return
              }
              resetWorkspace()
              showToast('새 작업을 위해 캔버스가 초기화되었습니다.')
            }}
          >
            <Plus size={14} />
            <span className="btn-label">새 작업</span>
          </button>

          {/* Project Management */}
          <button
            className="outline small header-action-btn"
            title="프로젝트 목록 열기"
            data-tooltip="프로젝트"
            onClick={openProjectsModal}
          >
            <FolderOpen size={14} />
            <span className="btn-label">프로젝트</span>
          </button>

          {/* User Auth */}
          {currentUser ? (
            <div
              className="user-profile header-action-btn"
              title={currentUser.name}
              data-tooltip={currentUser.name}
            >
              <User size={14} />
              <span className="btn-label user-name">{currentUser.name}</span>
              <button className="icon" title="로그아웃" onClick={handleLogout}>
                <LogOut size={14} />
              </button>
            </div>
          ) : (
            <button
              className="outline small header-action-btn"
              title="로그인"
              data-tooltip="로그인"
              onClick={() => setShowLoginModal(true)}
            >
              <LogIn size={14} />
              <span className="btn-label">로그인</span>
            </button>
          )}
        </div>
      </header>

      {/* Main Workspace (2-Column: Wide Canvas + Integrated Right Sidebar) */}
      <div className="workspace">
        {/* Center: Konva WYSIWYG Canvas */}
        <div className="canvas-section">
          {processingStatus && (
            <div className="progress-banner">
              <Clock size={16} />
              <b>{processingStatus}</b>
            </div>
          )}
          <div className="canvas-bar unified-canvas-bar">
            <div className="canvas-unified-toolbar">
              {/* 1. History Tools */}
              <div className="action-group">
                <button
                  className="icon canvas-action-btn"
                  title="되돌리기 (Ctrl+Z)"
                  data-tooltip="되돌리기"
                  disabled={undoStack.length === 0}
                  onClick={handleUndo}
                >
                  <RotateCcw size={15} />
                </button>
                <button
                  className="icon canvas-action-btn"
                  title="다시 실행 (Ctrl+Shift+Z)"
                  data-tooltip="다시 실행"
                  disabled={redoStack.length === 0}
                  onClick={handleRedo}
                >
                  <RotateCw size={15} />
                </button>
                {isDirty && (
                  <button
                    className="outline tiny text-muted canvas-action-btn"
                    title="저장 전 모든 수정 취소"
                    data-tooltip="초안 취소"
                    onClick={handleDiscardDraft}
                  >
                    <Undo2 size={12} />
                    <span className="btn-label">초안 취소</span>
                  </button>
                )}
              </div>

              {/* 2. Version History & Delete */}
              {projectId && (
                <button
                  className="outline small canvas-action-btn"
                  title="버전 복원 및 히스토리"
                  data-tooltip="버전 복원"
                  onClick={openRevisionsModal}
                >
                  <History size={13} />
                  <span className="btn-label">버전 복원</span>
                </button>
              )}
              {projectId && (
                <button
                  className="outline small canvas-action-btn"
                  style={{ color: '#ef4444', borderColor: '#fca5a5' }}
                  title="현재 프로젝트 삭제"
                  data-tooltip="프로젝트 삭제"
                  onClick={() => handleDeleteProject(projectId, projectName)}
                >
                  <Trash2 size={13} />
                </button>
              )}

              <span className="bar-separator" />

              {/* 3. Original Image Peek, Add Region, Save & High-Res Render */}
              <button
                className="outline small canvas-action-btn"
                title="최초 인식 전 원본 이미지(v0) 보기"
                onClick={() => setShowOriginalModal(true)}
                disabled={!originalImageUrl && !bgImageUrl}
              >
                <Eye size={13} />
                <span className="btn-label">원본 보기</span>
              </button>
              <button
                className="outline small canvas-action-btn"
                title="새로운 텍스트 영역 추가"
                onClick={handleAddRegion}
                disabled={!bgImageUrl && !originalImageUrl}
              >
                <Plus size={14} />
                <span className="btn-label">영역추가</span>
              </button>
              {selectedIds.length > 1 && viewMode === 'edit' && (
                <button
                  type="button"
                  className="button small canvas-action-btn"
                  style={{ background: '#4f46e5', borderColor: '#4338ca', color: '#ffffff' }}
                  title="선택된 영역들을 하나로 병합"
                  onClick={handleRequestMerge}
                >
                  <Layers size={13} />
                  <span className="btn-label">영역 병합 ({selectedIds.length})</span>
                </button>
              )}
              <button
                className="outline small canvas-action-btn"
                title="프로젝트 저장"
                data-tooltip="저장"
                onClick={handleSaveProject}
                disabled={isProcessing}
              >
                <Save size={13} />
                <span className="btn-label">저장</span>
              </button>
              <button
                className="button small canvas-action-btn render-btn"
                title="이미지 생성 실행 (3X 슈퍼샘플링 합성)"
                data-tooltip="이미지생성"
                onClick={handleFinalRender}
                disabled={isProcessing || !bgImageUrl}
              >
                <ImagePlus size={14} />
                <span className="btn-label">이미지생성</span>
              </button>

              <span className="bar-separator" />

              {/* 4. View Mode Toggle (Merged with Canvas Toolbar) */}
              {activeRenderedUrl && (
                <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                  <div className="view-mode-toggle" title="편집 뷰와 최종 렌더링 결과 파일 보기 전환">
                    <button
                      type="button"
                      className={`view-mode-btn ${viewMode === 'edit' ? 'active' : ''}`}
                      onClick={() => setViewMode('edit')}
                    >
                      <Edit3 size={13} />
                      <span>편집 뷰</span>
                    </button>
                    <button
                      type="button"
                      className={`view-mode-btn ${viewMode === 'result' ? 'active' : ''}`}
                      onClick={() => setViewMode('result')}
                    >
                      <LucideImage size={13} />
                      <span>렌더 결과 뷰</span>
                      <span className="view-mode-pill">v{projectVersion}</span>
                    </button>
                  </div>
                  {viewMode === 'result' && (
                    <a
                      href={activeRenderedUrl}
                      download={
                        (() => {
                          const base = (projectName || 'image').replace(/\.[^/.]+$/, '').replace(/_fixit$/, '')
                          return projectVersion > 1 ? `${base}_v${projectVersion}_fixit.png` : `${base}_fixit.png`
                        })()
                      }
                      className="button small canvas-action-btn"
                      style={{
                        padding: '5px 10px',
                        fontSize: '11px',
                        background: '#2c3e25',
                        color: '#f1f8ea',
                        textDecoration: 'none',
                        borderRadius: '6px'
                      }}
                      title={`v${projectVersion} 고화질 렌더링 완성본 다운로드`}
                      data-tooltip="다운로드"
                    >
                      <Download size={13} />
                      <span className="btn-label">다운로드</span>
                    </a>
                  )}
                </div>
              )}

              <span className="bar-separator" />

              {/* 5. Zoom & Image Upload Controls */}
              <div className="canvas-zoom-group">
                <button
                  className="icon"
                  title="축소"
                  onClick={() => {
                    setAutoFit(false)
                    setZoom(z => Math.max(0.15, Math.round((z - 0.1) * 100) / 100))
                  }}
                >
                  <ZoomOut size={15} />
                </button>
                <button
                  className="icon"
                  title="확대"
                  onClick={() => {
                    setAutoFit(false)
                    setZoom(z => Math.min(2.5, Math.round((z + 0.1) * 100) / 100))
                  }}
                >
                  <ZoomIn size={15} />
                </button>
                <button
                  className="icon"
                  title="100% 원본 크기"
                  onClick={() => {
                    setAutoFit(false)
                    setZoom(1.0)
                  }}
                >
                  1:1
                </button>
                <button
                  className={`icon ${autoFit ? 'active-fit' : ''}`}
                  title={autoFit ? '자동 맞춤 활성화됨' : '현재 창 크기에 자동 맞춤'}
                  onClick={() => {
                    setAutoFit(true)
                    fitToContainer()
                  }}
                >
                  Fit
                </button>
              </div>

              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                style={{ display: 'none' }}
                onChange={handleFileChange}
              />
              <button className="outline small" onClick={() => fileInputRef.current?.click()} disabled={isProcessing}>
                <Upload size={13} /> 새 이미지
              </button>
            </div>
          </div>

          <div className="canvas-wrap" ref={canvasWrapRef}>

            {bgImageObj ? (
              <Stage
                key={`stage_p${projectId ?? 'none'}_v${projectVersion}`}
                ref={stageRef}
                width={imageSize.width * zoom}
                height={imageSize.height * zoom}
                scaleX={zoom}
                scaleY={zoom}
                onMouseDown={handleStageMouseDown}
                onMouseMove={handleStageMouseMove}
                onMouseUp={handleStageMouseUp}
                onClick={(e) => {
                  handleStageClick(e)
                }}
                style={{ cursor: activeTool === 'cutout' ? 'crosshair' : (selectionBox?.visible ? 'crosshair' : 'default') }}
              >
                {/* Background Layer: Super-sampled result image in result view, clean background in edit view */}
                <Layer name="bg-layer">
                  <KonvaImage
                    key={`bg_img_${projectId ?? 'none'}_v${projectVersion}_${viewMode === 'result' ? (currentRenderedUrl || 'res') : (bgImageUrl || originalImageUrl || 'bg')}`}
                    name="bg-canvas-image"
                    image={viewMode === 'result' ? (renderedImageObj || bgImageObj) : bgImageObj}
                    width={imageSize.width}
                    height={imageSize.height}
                  />
                </Layer>

                {/* Typography Layer (Active only in Edit View) */}
                {viewMode === 'edit' && (
                  <Layer>
                    {regions.map(reg => {
                      const [rx, ry, rw, rh] = reg.bbox
                      const isSelected = selectedIds.includes(reg.id)

                      // Font Family resolving: Fallback chain ensures Hanja (先, etc.) and missing glyphs render cleanly via NotoSansKR and system fonts
                      const baseFam = reg.font_family || 'NanumSquare'
                      const fontFam = `${baseFam}, NotoSansKR, sans-serif`
                      const fontWt = reg.font_weight === 'ExtraBold' ? '800' : reg.font_weight === 'Bold' ? 'bold' : 'normal'

                      return (
                        <Group
                          key={`${reg.id}_${fontsReady ? 'ready' : 'loading'}`}
                          id={`node-${reg.id}`}
                          x={rx}
                          y={ry}
                          draggable={activeTool === 'wysiwyg'}
                          onMouseEnter={() => {
                            setHoveredId(reg.id)
                            if (stageRef.current) stageRef.current.container().style.cursor = 'pointer'
                          }}
                          onMouseLeave={() => {
                            setHoveredId(null)
                            if (stageRef.current) stageRef.current.container().style.cursor = 'default'
                          }}
                          onClick={(e) => {
                            e.cancelBubble = true
                            const isMulti = e.evt.ctrlKey || e.evt.metaKey
                            if (isMulti) {
                              setSelectedIds(prev =>
                                prev.includes(reg.id) ? prev.filter(id => id !== reg.id) : [...prev, reg.id]
                              )
                            } else {
                              setSelectedIds([reg.id])
                            }
                            setRightSidebarTab('props')
                          }}
                          onDragEnd={(e) => {
                            const newX = Math.round(e.target.x())
                            const newY = Math.round(e.target.y())
                            const next = regions.map(r => {
                              if (r.id === reg.id) {
                                const updatedCleanBbox: [number, number, number, number] = r.clean_bbox
                                  ? [newX, newY, r.clean_bbox[2], r.clean_bbox[3]]
                                  : [newX, newY, rw, rh]
                                return {
                                  ...r,
                                  bbox: [newX, newY, rw, rh] as [number, number, number, number],
                                  clean_bbox: updatedCleanBbox
                                }
                              }
                              return r
                            })
                            updateRegionsWithHistory(next)
                          }}
                          onTransformEnd={(e) => {
                            const node = e.target
                            const scaleX = node.scaleX()
                            const scaleY = node.scaleY()
                            const newX = Math.round(node.x())
                            const newY = Math.round(node.y())
                            const newW = Math.max(20, Math.round(rw * scaleX))
                            const newH = Math.max(15, Math.round(rh * scaleY))

                            // Reset scale on node to prevent compounded scaling upon next render
                            node.scaleX(1)
                            node.scaleY(1)

                            const next = regions.map(r => {
                              if (r.id === reg.id) {
                                const newBbox: [number, number, number, number] = [newX, newY, newW, newH]
                                return {
                                  ...r,
                                  bbox: newBbox,
                                  clean_bbox: newBbox
                                }
                              }
                              return r
                            })
                            updateRegionsWithHistory(next)
                          }}
                        >
                          {/* Recognized Region Bounding Box (Hidden during export) */}
                          <Rect
                            visible={!isExporting}
                            width={rw}
                            height={rh}
                            fill={
                              isSelected
                                ? 'rgba(37, 99, 235, 0.05)'
                                : hoveredId === reg.id
                                  ? 'rgba(59, 130, 246, 0.08)'
                                  : 'transparent'
                            }
                            stroke={isSelected ? '#2563eb' : hoveredId === reg.id ? '#3b82f6' : '#94a3b8'}
                            strokeWidth={isSelected ? 1.8 : hoveredId === reg.id ? 1.5 : 1}
                            dash={isSelected ? [5, 4] : hoveredId === reg.id ? [4, 2] : [4, 3]}
                            opacity={isSelected ? 1 : hoveredId === reg.id ? 0.95 : 0.65}
                            cornerRadius={2}
                          />

                          {/* WYSIWYG Corrected Typography Text - Exact Alignment with LLM intent & containment */}
                          {(() => {
                            const rawText = reg.corrected || ''
                            const baseFontSize = reg.font_size || 24

                            // 1. LLM 기준 줄바꿈 100% 보존 (임의 자동 줄바꿈 완전 제거)
                            const maxLineW = rw > 0 ? rw - 4 : 500
                            const rawLines = rawText.split('\n')
                            const lines: string[] = rawLines.length > 0 ? rawLines : [rawText]

                            // 2. LLM 기준 폰트 크기 100% 보존 (임의 폰트 축소 완전 제거)
                            const effectiveFontSize = baseFontSize
                            const lineH = Math.round(effectiveFontSize * 1.15)
                            const totalGlyphH = lines.length * lineH

                            // Distribute remaining height across lines so line gaps match the total box height
                            let computedLineGap = reg.line_gap || 0
                            const remainingH = rh - totalGlyphH
                            if (remainingH > 0 && lines.length > 1) {
                              computedLineGap = Math.max(computedLineGap, Math.floor(remainingH / (lines.length - 1)))
                            }

                            // 3. Vertical start position
                            const totalRenderH = lines.length * lineH + Math.max(0, lines.length - 1) * computedLineGap
                            let startY = 0
                            if (reg.valign === 'bottom') {
                              startY = Math.max(0, rh - totalRenderH)
                            } else if (reg.valign === 'top') {
                              startY = 0
                            } else {
                              startY = Math.max(0, Math.round((rh - totalRenderH) / 2))
                            }

                            return lines.map((line, lIdx) => {
                              const currentFontSpec = `${fontWt} ${effectiveFontSize}px ${fontFam}`
                              const numGaps = Math.max(1, line.length - 1)
                              const availW = maxLineW

                              // Base styling: default scale_x = 0.95 (95%), default letter_spacing = -0.5
                              const baseScale = reg.scale_x && reg.scale_x !== 0.95 ? reg.scale_x : 0.95
                              const baseSpacing = reg.letter_spacing !== undefined && reg.letter_spacing !== -0.5 ? reg.letter_spacing : -0.5

                              let lineSpacing = baseSpacing
                              let lineScaleX = baseScale

                              // Precise width measurement without pre-baking compression
                              const unscaledW = measureTextWidth(line, currentFontSpec, 0)
                              const wAtBase = (unscaledW + numGaps * baseSpacing) * baseScale

                              // 마스킹 영역을 초과할 때만 정밀하게 비례 조절하여 과도한 압축 방지
                              if (availW > 0 && wAtBase > availW) {
                                const excess = wAtBase - availW

                                // Step 1: 자간(letter_spacing)을 초과분만큼만 미세 조절 (최대 -0.9px, 절대 과도하게 압축하지 않음)
                                const reqSpacing = baseSpacing - (excess / numGaps)
                                lineSpacing = Math.max(-0.9, Math.round(reqSpacing * 100) / 100)

                                // Step 2: 자간 조절 후에도 남는 초과분만 장평(scale_x)으로 정밀 피팅 (최대 0.85까지 완만하게 조절)
                                const wAfterSpacing = (unscaledW + numGaps * lineSpacing) * baseScale
                                if (wAfterSpacing > availW) {
                                  const reqScale = availW / Math.max(1, (unscaledW + numGaps * lineSpacing))
                                  lineScaleX = Math.max(0.85, Math.min(0.95, Math.round(reqScale * 1000) / 1000))
                                }
                              }

                              const renderedLineW = measureTextWidth(line, currentFontSpec, lineSpacing) * lineScaleX
                              let lineX = 0
                              if (reg.align === 'center') {
                                lineX = Math.max(0, Math.round((rw - renderedLineW) / 2))
                              } else if (reg.align === 'right') {
                                lineX = Math.max(0, Math.round(rw - renderedLineW))
                              }

                              const lineY = startY + lIdx * (lineH + computedLineGap)

                              return (
                                <KonvaText
                                  key={lIdx}
                                  x={lineX}
                                  y={lineY}
                                  text={line}
                                  fontSize={effectiveFontSize}
                                  fontFamily={fontFam}
                                  fontStyle={fontWt}
                                  scaleX={lineScaleX}
                                  letterSpacing={lineSpacing}
                                  fill={reg.text_color}
                                  wrap="none"
                                  ellipsis={false}
                                  listening={false}
                                />
                              )
                            })
                          })()}
                        </Group>
                      )
                    })}

                    {activeTool === 'wysiwyg' && !isExporting && (
                      <Transformer
                        ref={transformerRef}
                        rotateEnabled={false}
                        boundBoxFunc={(oldBox, newBox) => {
                          if (newBox.width < 20 || newBox.height < 15) {
                            return oldBox
                          }
                          return newBox
                        }}
                      />
                    )}
                  </Layer>
                )}

                {/* Marquee Drag Selection Box (Rubberband Selection) */}
                {selectionBox && selectionBox.visible && (
                  <Layer listening={false}>
                    <Rect
                      x={Math.min(selectionBox.x1, selectionBox.x2)}
                      y={Math.min(selectionBox.y1, selectionBox.y2)}
                      width={Math.abs(selectionBox.x2 - selectionBox.x1)}
                      height={Math.abs(selectionBox.y2 - selectionBox.y1)}
                      fill="rgba(59, 130, 246, 0.16)"
                      stroke="#2563eb"
                      strokeWidth={1.5 / zoom}
                      dash={[6 / zoom, 3 / zoom]}
                      cornerRadius={2}
                    />
                  </Layer>
                )}
              </Stage>
            ) : (
              <div
                className="upload-card"
                onClick={() => fileInputRef.current?.click()}
                onDragOver={handleDragOver}
                onDrop={handleDrop}
              >
                <div className="upload-icon">
                  <Upload size={30} />
                </div>
                <strong>이미지를 선택하거나 여기에 드래그하세요</strong>
                <span>PNG, JPG, WebP 고해상도 인포그래픽 지원</span>
                <small>업로드 시 Strata VLM / Azure GPT-6.1-sol이 자동으로 오탈자 및 텍스트 영역을 복원합니다</small>
              </div>
            )}
          </div>

          {/* Completed Thumbnails Filmstrip Bar at Bottom of Canvas */}
          {completedThumbnails.length > 0 && (
            <div className={`completed-thumbnails-strip ${isGalleryCollapsed ? 'collapsed' : ''}`}>
              <div
                className="strip-header"
                onClick={() => setIsGalleryCollapsed(prev => !prev)}
                style={{ cursor: 'pointer' }}
              >
                <div className="strip-title">
                  <LucideImage size={15} />
                  <span>완성된 이미지 갤러리 (버전별 결과물)</span>
                  <span className="strip-badge">{completedThumbnails.length}개 버전</span>
                </div>
                <div className="strip-header-right">
                  <small>썸네일을 클릭하면 해당 버전으로 즉시 이동할 수 있습니다 (현재 작업 자동 저장)</small>
                  <button
                    type="button"
                    className="strip-toggle-btn"
                    onClick={(e) => {
                      e.stopPropagation()
                      setIsGalleryCollapsed(prev => !prev)
                    }}
                    title={isGalleryCollapsed ? '갤러리 펼치기' : '갤러리 접기'}
                  >
                    {isGalleryCollapsed ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                    <span>{isGalleryCollapsed ? '펼치기' : '접기'}</span>
                  </button>
                </div>
              </div>

              {!isGalleryCollapsed && (
                <div className="strip-scroll-area">
                  {completedThumbnails.map((thumb) => {
                    const isCurrent = thumb.version === projectVersion
                    return (
                      <div
                        key={thumb.id}
                        className={`strip-thumb-card ${isCurrent ? 'current' : ''}`}
                        onClick={() => handleRequestSwitchVersion(thumb)}
                        title={isCurrent ? `현재 편집 중인 버전 (v${thumb.version})` : `v${thumb.version} 버전으로 이동`}
                      >
                        <div className="thumb-img-box">
                          <img src={thumb.imageUrl} alt={thumb.label} />
                          {isCurrent && <div className="current-indicator">현재 편집중</div>}
                        </div>
                        <div className="thumb-info">
                          <b>v{thumb.version}</b>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                            <span>{((thumb.label || '').replace(/\s*\(v\d+\)/gi, '').replace(/^v\d+\s*/, '')).trim() || (thumb.version === 0 ? '원본' : thumb.version === 1 ? '초기 AI 복원본' : '고화질 렌더본')}</span>
                            {thumb.version !== 0 && (
                              <button
                                type="button"
                                className="thumb-del-btn"
                                title={`v${thumb.version} 버전 삭제`}
                                onClick={(e) => {
                                  e.stopPropagation()
                                  handleDeleteRevision(thumb.version)
                                }}
                              >
                                <Trash2 size={11} />
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right Panel: Integrated Typography List & Inspector */}
        <div className="inspector-panel integrated-sidebar">
          {/* Top Tabs */}
          <div className="sidebar-tab-nav">
            <button
              type="button"
              className={`sidebar-tab-btn ${rightSidebarTab === 'list' ? 'active' : ''}`}
              onClick={() => setRightSidebarTab('list')}
            >
              <List size={14} />
              <span>텍스트 목록</span>
              <span className="tab-pill">{regions.length}</span>
            </button>
            <button
              type="button"
              className={`sidebar-tab-btn ${rightSidebarTab === 'props' ? 'active' : ''}`}
              onClick={() => setRightSidebarTab('props')}
            >
              <Sliders size={14} />
              <span>속성 편집</span>
              {selectedRegion && <span className="tab-active-dot" />}
            </button>
          </div>

          {/* Result View Notice Banner in Sidebar */}
          {viewMode === 'result' && (
            <div className="sidebar-result-notice">
              <div className="notice-header">
                <LucideImage size={14} />
                <b>렌더링 결과 파일 보기 모드</b>
              </div>
              <p>서버에서 합성된 v{projectVersion} 고화질 완성본을 확인 중입니다. 텍스트를 수정하려면 [편집 뷰]로 전환하세요.</p>
              <button
                type="button"
                className="button tiny full"
                onClick={() => setViewMode('edit')}
              >
                <Edit3 size={12} /> 편집 뷰로 전환하기
              </button>
            </div>
          )}

          {/* Tab Content 1: Text Region List */}
          {rightSidebarTab === 'list' && (
            <div className="sidebar-list-content">
              <div className="section-title">
                <span>텍스트 영역 ({regions.length})</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  {selectedIds.length > 1 && (
                    <button
                      type="button"
                      className="button tiny"
                      style={{ padding: '3px 8px', fontSize: '11px', background: '#4f46e5', borderColor: '#4338ca', color: '#ffffff', display: 'flex', alignItems: 'center', gap: '4px' }}
                      title="선택된 영역들을 하나로 병합"
                      onClick={handleRequestMerge}
                    >
                      <Layers size={12} /> 병합 ({selectedIds.length})
                    </button>
                  )}
                  <button
                    className="outline tiny"
                    style={{ padding: '3px 8px', fontSize: '11px', display: 'flex', alignItems: 'center', gap: '4px' }}
                    title="새로운 텍스트 영역 수동 추가"
                    onClick={handleAddRegion}
                    disabled={!bgImageUrl && !originalImageUrl}
                  >
                    <Plus size={12} /> 영역 추가
                  </button>
                  <button
                    className="icon small"
                    title="AI 분석 엔진 선택 및 재실행"
                    onClick={() => setShowModelModal(true)}
                    disabled={isProcessing}
                  >
                    <Sparkles size={14} />
                  </button>
                </div>
              </div>

              <div className="region-list">
                {regions.map((reg, idx) => {
                  const isSelected = selectedIds.includes(reg.id)
                  return (
                    <button
                      key={reg.id}
                      className={isSelected ? 'selected' : ''}
                      onClick={(e) => {
                        const isMulti = e.ctrlKey || e.metaKey
                        if (isMulti) {
                          setSelectedIds(prev =>
                            prev.includes(reg.id) ? prev.filter(id => id !== reg.id) : [...prev, reg.id]
                          )
                        } else {
                          setSelectedIds([reg.id])
                          setViewMode('edit')
                          setRightSidebarTab('props')
                        }
                      }}
                      onMouseEnter={() => setHoveredId(reg.id)}
                      onMouseLeave={() => setHoveredId(null)}
                      title="클릭: 속성 편집 열기 (Ctrl/Cmd+클릭: 다중 선택)"
                    >
                      <b>{idx + 1}.</b>
                      <span>{reg.corrected.split('\n')[0] || reg.observed}</span>
                    </button>
                  )
                })}
                {regions.length === 0 && (
                  <div className="tool-hint">
                    <p>이미지를 업로드하면 자동으로 텍스트 영역이 추출됩니다.</p>
                  </div>
                )}
              </div>

              {comparisons.length > 0 && (
                <div className="divider-section">
                  <button className="outline full small" onClick={() => setShowComparisonModal(true)}>
                    <Eye size={14} /> 교정 전/후 비교 ({comparisons.length})
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Tab Content 2: Typography Properties Inspector */}
          {rightSidebarTab === 'props' && (
            <div className="sidebar-props-content">
              <div className="props-header-nav">
                <button
                  type="button"
                  className="back-to-list-btn"
                  onClick={() => setRightSidebarTab('list')}
                  title="텍스트 목록으로 돌아가기"
                >
                  <ChevronLeft size={13} /> 목록으로
                </button>
                {selectedRegion && (
                  <span className="current-region-indicator">
                    #{regions.findIndex(r => r.id === selectedRegion.id) + 1} 영역 편집 중
                  </span>
                )}
              </div>

              {selectedRegion ? (
                <div className="inspector-content">
                  {/* Batch Selection Banner */}
                  {selectedIds.length > 1 && (
                    <div className="batch-edit-badge">
                      <div className="badge-header">
                        <Layers size={14} />
                        <b>다중 선택 모드 ({selectedIds.length}개 블록)</b>
                      </div>
                      <p>아래에서 폰트, 크기, 장평, 자간 변경 시 선택된 모든 블록에 일괄 적용됩니다.</p>
                      <div style={{ display: 'flex', gap: '8px', marginTop: '8px', flexWrap: 'wrap' }}>
                        <button
                          type="button"
                          className="button tiny"
                          style={{ background: '#4f46e5', borderColor: '#4338ca', color: '#ffffff', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
                          onClick={handleRequestMerge}
                          title="선택된 모든 텍스트 영역을 하나로 병합합니다"
                        >
                          <Layers size={12} />
                          <span>선택 영역 병합</span>
                        </button>
                        <button
                          type="button"
                          className="outline tiny"
                          style={{ color: '#ef4444', borderColor: '#fca5a5', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
                          onClick={handleDeleteSelectedRegions}
                          title="선택된 모든 텍스트 블록 삭제 (Delete 키)"
                        >
                          <Trash2 size={12} />
                          <span>일괄 삭제 (Delete)</span>
                        </button>
                        <button type="button" className="outline tiny" onClick={() => setSelectedIds([])}>
                          선택 해제
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Text Edit & Split Block (Only for Single Selection) */}
                  {selectedIds.length === 1 ? (
                    <>
                      {/* 1. Original Image Crop Preview at the Top of Inspector */}
                      <OriginalCropPreview
                        imageUrl={originalImageUrl || bgImageUrl}
                        bbox={selectedRegion.bbox}
                        observedText={selectedRegion.observed}
                      />

                      {/* 2. Corrected Text Edit Textarea */}
                      <div className="field">
                        <span>교정된 문구 (Corrected)</span>
                        <textarea
                          rows={3}
                          value={selectedRegion.corrected}
                          onChange={(e) => updateSelectedField('corrected', e.target.value)}
                          placeholder="교정할 텍스트를 입력하세요"
                        />
                      </div>

                      {/* Split Block Control for Multi-line Blocks */}
                      {selectedRegion.corrected.split('\n').length > 1 && (
                        <div className="split-block-box">
                          <div className="split-block-title">
                            <Split size={14} />
                            <span>블록 분할 (독립 블록으로 분리)</span>
                          </div>
                          <div className="split-actions">
                            {selectedRegion.corrected.split('\n').slice(0, -1).map((line, lineIdx) => (
                              <button
                                key={lineIdx}
                                type="button"
                                className="split-btn"
                                onClick={() => handleSplitRegion(selectedRegion.id, lineIdx + 1)}
                                title={`${lineIdx + 1}번째 줄 아래에서 분리`}
                              >
                                <span>{lineIdx + 1}행: "{line.trim().slice(0, 16)}..."</span>
                                <b>✂ 아래에서 분할</b>
                              </button>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* 3. Masking / Bounding Box Size Controls */}
                      <div className="field">
                        <span>마스킹 및 바운딩 박스 영역 (px)</span>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginTop: '4px' }}>
                          <label style={{ fontSize: '11px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                            <span style={{ color: '#64748b' }}>X 좌표</span>
                            <input
                              type="number"
                              value={selectedRegion.bbox[0]}
                              onChange={(e) => updateBboxField(0, parseInt(e.target.value) || 0)}
                              style={{ padding: '4px 8px', fontSize: '12px', border: '1px solid #cbd5e1', borderRadius: '4px' }}
                            />
                          </label>
                          <label style={{ fontSize: '11px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                            <span style={{ color: '#64748b' }}>Y 좌표</span>
                            <input
                              type="number"
                              value={selectedRegion.bbox[1]}
                              onChange={(e) => updateBboxField(1, parseInt(e.target.value) || 0)}
                              style={{ padding: '4px 8px', fontSize: '12px', border: '1px solid #cbd5e1', borderRadius: '4px' }}
                            />
                          </label>
                          <label style={{ fontSize: '11px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                            <span style={{ color: '#64748b' }}>너비 (W)</span>
                            <input
                              type="number"
                              min={10}
                              value={selectedRegion.bbox[2]}
                              onChange={(e) => updateBboxField(2, Math.max(10, parseInt(e.target.value) || 10))}
                              style={{ padding: '4px 8px', fontSize: '12px', border: '1px solid #cbd5e1', borderRadius: '4px' }}
                            />
                          </label>
                          <label style={{ fontSize: '11px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                            <span style={{ color: '#64748b' }}>높이 (H)</span>
                            <input
                              type="number"
                              min={10}
                              value={selectedRegion.bbox[3]}
                              onChange={(e) => updateBboxField(3, Math.max(10, parseInt(e.target.value) || 10))}
                              style={{ padding: '4px 8px', fontSize: '12px', border: '1px solid #cbd5e1', borderRadius: '4px' }}
                            />
                          </label>
                        </div>
                        <div style={{ display: 'flex', gap: '6px', marginTop: '6px' }}>
                          <button
                            type="button"
                            className="outline small"
                            style={{ fontSize: '11px', padding: '3px 8px', flex: 1 }}
                            onClick={() => handleExpandMask(selectedRegion.id, 10)}
                            title="마스킹 영역을 상하좌우 10px씩 확장합니다"
                          >
                            +10px 영역 확장
                          </button>
                          <button
                            type="button"
                            className="outline small"
                            style={{ fontSize: '11px', padding: '3px 8px', flex: 1 }}
                            onClick={() => handleExpandMask(selectedRegion.id, 20)}
                            title="마스킹 영역을 상하좌우 20px씩 확장합니다"
                          >
                            +20px 영역 확장
                          </button>
                        </div>
                      </div>
                    </>
                  ) : (
                    <div className="field">
                      <span>선택된 블록 정보</span>
                      <small className="observed-badge">
                        {selectedIds.length}개 블록 동시 선택 중 (개별 텍스트 편집은 단일 선택 시 지원)
                      </small>
                    </div>
                  )}

                  <div className="divider" />

                  {/* 3 Fonts Selection */}
                  <div className="field">
                    <span>폰트 패밀리</span>
                    <select
                      value={selectedRegion.font_family}
                      onChange={(e) => updateSelectedField('font_family', e.target.value as FontFamily)}
                    >
                      <option value="NanumSquare">나눔스퀘어 (NanumSquare)</option>
                      <option value="NotoSansKR">본고딕 (NotoSansKR)</option>
                      <option value="Paperlogy">페이퍼로지 (Paperlogy)</option>
                    </select>
                  </div>

                  {/* Font Weight */}
                  <div className="field">
                    <span>폰트 두께 (Weight)</span>
                    <select
                      value={selectedRegion.font_weight}
                      onChange={(e) => updateSelectedField('font_weight', e.target.value as FontWeight)}
                    >
                      <option value="Regular">Regular (기본)</option>
                      <option value="Bold">Bold (굵게)</option>
                      {selectedRegion.font_family === 'NanumSquare' && (
                        <option value="ExtraBold">ExtraBold (초굵게)</option>
                      )}
                    </select>
                  </div>

                  {/* Font Size */}
                  <div className="field">
                    <span>폰트 크기</span>
                    <div className="slider-control-row">
                      <input
                        type="range"
                        min={8}
                        max={120}
                        step={1}
                        value={selectedRegion.font_size}
                        onChange={(e) => updateSelectedField('font_size', parseInt(e.target.value) || 8)}
                      />
                      <div className="slider-input-badge">
                        <input
                          type="number"
                          className="slider-num-input"
                          min={6}
                          max={300}
                          step={1}
                          value={selectedRegion.font_size}
                          onChange={(e) => {
                            const val = parseInt(e.target.value)
                            if (!isNaN(val)) updateSelectedField('font_size', val)
                          }}
                        />
                        <span className="unit">pt</span>
                      </div>
                    </div>
                  </div>

                  {/* Aspect Ratio (장평) */}
                  <div className="field">
                    <span>장평 (Aspect Ratio)</span>
                    <div className="slider-control-row">
                      <input
                        type="range"
                        min={0.50}
                        max={1.50}
                        step={0.01}
                        value={Number(selectedRegion.scale_x.toFixed(2))}
                        onChange={(e) => updateSelectedField('scale_x', parseFloat(e.target.value) || 1.0)}
                      />
                      <div className="slider-input-badge no-unit">
                        <input
                          type="number"
                          className="slider-num-input"
                          min={0.20}
                          max={3.00}
                          step={0.01}
                          value={Number(selectedRegion.scale_x.toFixed(2))}
                          onChange={(e) => {
                            const val = parseFloat(e.target.value)
                            if (!isNaN(val)) updateSelectedField('scale_x', Math.round(val * 100) / 100)
                          }}
                        />
                      </div>
                    </div>
                  </div>

                  {/* Tracking (자간) */}
                  <div className="field">
                    <span>자간 (Tracking)</span>
                    <div className="slider-control-row">
                      <input
                        type="range"
                        min={-5.0}
                        max={10.0}
                        step={0.1}
                        value={Number(selectedRegion.letter_spacing.toFixed(1))}
                        onChange={(e) => updateSelectedField('letter_spacing', parseFloat(e.target.value) || 0)}
                      />
                      <div className="slider-input-badge">
                        <input
                          type="number"
                          className="slider-num-input"
                          min={-20.0}
                          max={50.0}
                          step={0.1}
                          value={Number(selectedRegion.letter_spacing.toFixed(1))}
                          onChange={(e) => {
                            const val = parseFloat(e.target.value)
                            if (!isNaN(val)) updateSelectedField('letter_spacing', Math.round(val * 10) / 10)
                          }}
                        />
                        <span className="unit">px</span>
                      </div>
                    </div>
                  </div>

                  {/* Line Gap (행간) */}
                  <div className="field">
                    <span>행간 (Line Gap)</span>
                    <div className="slider-control-row">
                      <input
                        type="range"
                        min={-10}
                        max={60}
                        step={1}
                        value={selectedRegion.line_gap}
                        onChange={(e) => updateSelectedField('line_gap', parseInt(e.target.value) || 0)}
                      />
                      <div className="slider-input-badge">
                        <input
                          type="number"
                          className="slider-num-input"
                          min={-30}
                          max={150}
                          step={1}
                          value={selectedRegion.line_gap}
                          onChange={(e) => {
                            const val = parseInt(e.target.value)
                            if (!isNaN(val)) updateSelectedField('line_gap', val)
                          }}
                        />
                        <span className="unit">px</span>
                      </div>
                    </div>
                  </div>

                  {/* Text Color & Alignment */}
                  <div className="field-row">
                    <div className="field">
                      <span>색상</span>
                      <input
                        type="color"
                        value={selectedRegion.text_color || '#000000'}
                        onChange={(e) => updateSelectedField('text_color', e.target.value)}
                      />
                    </div>
                    <div className="field">
                      <span>정렬</span>
                      <select
                        value={selectedRegion.align}
                        onChange={(e) => updateSelectedField('align', e.target.value as any)}
                      >
                        <option value="left">왼쪽</option>
                        <option value="center">가운데</option>
                        <option value="right">오른쪽</option>
                      </select>
                    </div>

                    <div style={{ marginTop: '16px', paddingTop: '14px', borderTop: '1px solid #e2e8f0', display: 'flex', gap: '8px' }}>
                      <button
                        type="button"
                        className="outline small full"
                        style={{ color: '#ef4444', borderColor: '#fca5a5', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '4px' }}
                        onClick={() => handleDeleteRegion(selectedRegion.id)}
                        title="선택된 텍스트 영역 삭제"
                      >
                        <Trash2 size={13} />
                        <span>영역 삭제</span>
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="empty-props-box">
                  <Sliders size={32} />
                  <p>선택된 텍스트 영역이 없습니다</p>
                  <small>캔버스에서 블록을 직접 클릭하거나, 새 영역을 추가하세요.</small>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', width: '100%', marginTop: '14px' }}>
                    <button
                      type="button"
                      className="button small full"
                      onClick={handleAddRegion}
                      disabled={!bgImageUrl && !originalImageUrl}
                    >
                      <Plus size={14} /> 새 영역 추가하기
                    </button>
                    <button
                      type="button"
                      className="outline small full"
                      onClick={() => setRightSidebarTab('list')}
                    >
                      <List size={14} /> 텍스트 목록에서 선택하기
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Crash Recovery Notification Modal */}
      {recoveryDraft && (
        <div className="modal-backdrop">
          <div className="modal">
            <h2>미저장 작업 복구 안내</h2>
            <p>이전에 편집 중이던 작업 내용({recoveryDraft.length}개 영역)이 브라우저에 보존되어 있습니다. 지금 복원하시겠습니까?</p>
            <div className="modal-actions">
              <button
                className="outline"
                onClick={() => {
                  localStorage.removeItem('fixit_draft')
                  setRecoveryDraft(null)
                }}
              >
                삭제하고 새로 시작
              </button>
              <button
                className="button"
                onClick={() => {
                  setRegions(recoveryDraft)
                  setIsDirty(true)
                  setRecoveryDraft(null)
                  showToast('이전 작업이 복구되었습니다.')
                }}
              >
                작업 복원하기
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Projects Modal with Model History */}
      {showProjectsModal && (
        <div className="modal-backdrop">
          <div className="modal wide">
            <button className="close" onClick={() => setShowProjectsModal(false)}>
              <X size={18} />
            </button>
            <h2>내 프로젝트 목록 (히스토리)</h2>
            <div className="project-grid">
              {projectsList.map(p => {
                const isSecure = p.metadata?.is_airgapped_secure ?? (!p.metadata?.requested_engine || p.metadata?.requested_engine?.startsWith('strata'))
                return (
                  <div key={p.id} className="project-card" onClick={() => loadProject(p.id)}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <b>{p.name}</b>
                      <span className={`model-tag-badge ${isSecure ? 'local' : 'azure'}`}>
                        {isSecure ? '🛡️ 로컬 폐쇄망' : '⚡ Azure 클라우드'}
                      </span>
                    </div>
                    <span>버전 {p.version} • {p.regions_count ?? 0}개 텍스트 블록</span>
                    <div className="project-card-footer">
                      <small>{p.updated_at ? new Date(p.updated_at).toLocaleString() : ''}</small>
                      <button
                        type="button"
                        className="project-del-btn"
                        title={`'${p.name}' 프로젝트 삭제`}
                        onClick={(e) => {
                          e.stopPropagation()
                          handleDeleteProject(p.id, p.name)
                        }}
                      >
                        <Trash2 size={12} />
                        <span>삭제</span>
                      </button>
                    </div>
                  </div>
                )
              })}
              {projectsList.length === 0 && <p>저장된 프로젝트가 없습니다.</p>}
            </div>
          </div>
        </div>
      )}

      {/* AI Model Selection Modal */}
      {showModelModal && (
        <div className="modal-backdrop">
          <div className="modal wide">
            <button className="close" onClick={() => { setShowModelModal(false); setPendingFile(null); }}>
              <X size={18} />
            </button>
            <h2>AI 이미지 분석 및 OCR 엔진 선택</h2>
            <p>문서의 보안 등급과 목적에 맞는 AI 모델을 선택하세요. 클라우드 고성능 모델과 사내 폐쇄망 로컬 VLM(RapidOCR + vLLM) 중 원하는 엔진을 선택하여 분석할 수 있습니다.</p>

            <div className="security-alert-box">
              <Shield size={18} />
              <div>
                <b>보안 및 모델 안내:</b>
                <span> 사내 기밀 및 대외비 문서는 <b>사내 폐쇄망 로컬 VLM</b>을, 복합 서체 세분화 및 초고속 분석은 <b>Azure GPT-6.1-sol</b>을 권장합니다.</span>
              </div>
            </div>

            <div className="model-selection-grid">
              {/* Option 1: Azure GPT-6.1-sol (최상단 / 추천 / 기본 활성화) */}
              <div
                className={`model-option-card ${selectedEngine === 'azure_gpt' ? 'selected' : ''}`}
                onClick={() => setSelectedEngine('azure_gpt')}
              >
                <div className="model-card-header">
                  <div className="model-title-wrap">
                    <Cloud size={18} color="#0369a1" />
                    <span>클라우드 고성능 모델 (Azure GPT-6.1-sol)</span>
                  </div>
                  <span className="model-badge cloud">최고 정밀도</span>
                </div>
                <div className="model-specs">
                  <span><Clock size={13} /> 예상 소요: <b>약 120초</b></span>
                  <span><Sparkles size={13} /> 품질: <b>초고품질 (복합 서체 세분화 및 고정밀 OCR)</b></span>
                  <span><AlertCircle size={13} /> 외부 통신: <b>Azure 클라우드 API 호출</b></span>
                </div>
                <p className="model-desc">
                  최첨단 클라우드 VLM을 사용하여 카드 제목/본문 복합 폰트 및 영역을 가장 정밀하게 분리해냅니다. 공개용 및 고품질 인포그래픽 복원에 적합합니다.
                </p>
              </div>

              {/* Option 2: 사내 로컬 VLM (내부 vLLM 통합 엔진) */}
              <div
                className={`model-option-card ${selectedEngine === 'strata_non_thinking' ? 'selected' : ''}`}
                onClick={() => setSelectedEngine('strata_non_thinking')}
              >
                <div className="model-card-header">
                  <div className="model-title-wrap">
                    <Cpu size={18} color="#166534" />
                    <span>사내 로컬 VLM (RapidOCR + 내부 vLLM 통합)</span>
                  </div>
                  <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                    {strataStatus?.busy ? (
                      <span className="model-badge busy-badge">🟠 VLM 사용 중</span>
                    ) : strataStatus?.online ? (
                      <span className="model-badge secure">🟢 실행 가능</span>
                    ) : (
                      <span className="model-badge secure" style={{ background: '#fee2e2', color: '#b91c1c' }}>🔴 오프라인</span>
                    )}
                  </div>
                </div>
                <div className="model-specs">
                  <span><Clock size={13} /> 예상 소요: <b>약 120초</b></span>
                  <span><Sparkles size={13} /> 품질: <b>RapidOCR 검출 + 기하학적 문단 머징</b></span>
                  <span><Lock size={13} /> 외부 통신: <b>0% (사내 폐쇄망 완전 격리)</b></span>
                </div>
                <p className="model-desc">
                  RapidOCR 100% 순수 검출 박스를 기반으로 단일 패스 기하학적 세로 머징(-5px 간격/배경색 일치)을 거친 후, 사내 Strata vLLM 배치 질의로 오탈자를 누락 없이 완벽 교정합니다.
                </p>
              </div>
            </div>

            <div className="modal-actions">
              <button
                className="outline"
                onClick={() => {
                  setShowModelModal(false)
                  setPendingFile(null)
                }}
              >
                취소
              </button>
              <button
                className="button"
                disabled={selectedEngine === 'strata_non_thinking' && strataStatus?.online === false}
                onClick={() => startAnalysisWithModel(selectedEngine)}
              >
                선택한 엔진으로 분석 시작
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Merge Confirmation Modal */}
      {showMergeConfirmModal && (
        <div className="modal-backdrop">
          <div className="modal merge-confirm-modal">
            <button className="close" onClick={() => setShowMergeConfirmModal(false)}>
              <X size={18} />
            </button>
            <h2>선택 영역 병합 확인</h2>
            <p style={{ margin: '8px 0 12px 0', fontSize: '14px', color: '#1e293b', fontWeight: 600 }}>
              선택된 영역을 병합하겠습니까?
            </p>

            <div className="merge-warning-box">
              <AlertCircle size={18} style={{ flexShrink: 0, color: '#2563eb' }} />
              <span>첫번째 선택된 영역으로 텍스트 스타일이 고정됩니다.</span>
            </div>

            <div className="merge-preview-summary">
              {(() => {
                const targetFirst = regions.find(r => r.id === selectedIds[0])
                const firstIdx = regions.findIndex(r => r.id === selectedIds[0])
                return (
                  <>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <b>기준 스타일 (첫 번째 영역):</b>
                      <span>#{firstIdx + 1} ({targetFirst?.font_family || 'NanumSquare'}, {targetFirst?.font_size || 20}pt, {targetFirst?.font_weight || 'Bold'})</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '6px' }}>
                      <b>병합 대상:</b>
                      <span>총 {selectedIds.length}개 블록</span>
                    </div>
                  </>
                )
              })()}
            </div>

            <div className="modal-actions">
              <button type="button" className="outline" onClick={() => setShowMergeConfirmModal(false)}>
                취소
              </button>
              <button
                type="button"
                className="button"
                style={{ background: '#4f46e5', borderColor: '#4338ca' }}
                onClick={confirmExecuteMerge}
              >
                병합 실행
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Revisions History Modal */}
      {showRevisionsModal && (
        <div className="modal-backdrop">
          <div className="modal">
            <button className="close" onClick={() => setShowRevisionsModal(false)}>
              <X size={18} />
            </button>
            <h2>저장 버전 히스토리 (되돌리기)</h2>
            <p>원하는 이전 완성본 시점으로 되돌릴 수 있습니다.</p>
            <div className="revision-list">
              {revisionsList.map(r => {
                const isCurrent = r.version === projectVersion
                const label =
                  r.version === 0
                    ? '버전 0 (원본 - AI 인식 전)'
                    : r.version === 1
                      ? '버전 1 (초기 AI 복원본)'
                      : `버전 ${r.version}`
                return (
                  <div key={r.id} className="revision-item">
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <b>{label}</b>
                        {isCurrent && <span style={{ fontSize: '10px', background: '#ecfdf5', color: '#059669', padding: '1px 6px', borderRadius: '4px', fontWeight: 600 }}>현재 작업중</span>}
                      </div>
                      <span>({r.regions_count}개 영역)</span>
                      <small>{r.created_at ? new Date(r.created_at).toLocaleString() : ''}</small>
                    </div>
                    <div className="revision-actions">
                      <button className="outline small" onClick={() => restoreRevision(r.version)}>
                        이 시점으로 롤백
                      </button>
                      {r.version !== 0 && (
                        <button
                          type="button"
                          className="revision-del-btn"
                          title={`버전 ${r.version} 삭제`}
                          onClick={() => handleDeleteRevision(r.version)}
                        >
                          <Trash2 size={12} />
                          <span>삭제</span>
                        </button>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {/* Raw Original Image (v0) Modal */}
      {showOriginalModal && (
        <div className="modal-backdrop">
          <div className="modal" style={{ maxWidth: '820px', width: '92vw' }}>
            <button className="close" onClick={() => setShowOriginalModal(false)}>
              <X size={18} />
            </button>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
              <Eye size={20} color="#729255" />
              <h2 style={{ margin: 0, fontSize: '18px' }}>최초 인식 전 원본 이미지 (v0)</h2>
            </div>
            <p style={{ fontSize: '13px', color: '#64748b', marginTop: 0, marginBottom: '14px' }}>
              AI 글자 인식 및 마스킹 인페인팅이 적용되기 전 원본 원천 이미지입니다.
            </p>
            <div
              style={{
                maxHeight: '60vh',
                overflow: 'auto',
                border: '1px solid #e2e8f0',
                borderRadius: '8px',
                background: '#0f172a',
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                padding: '12px'
              }}
            >
              {originalImageUrl ? (
                <img
                  src={originalImageUrl}
                  alt="원본 이미지"
                  style={{ maxWidth: '100%', maxHeight: '55vh', objectFit: 'contain', borderRadius: '4px' }}
                />
              ) : (
                <div style={{ color: '#94a3b8', padding: '30px', textAlign: 'center' }}>
                  <p>등록된 원본 원천 이미지 경로를 찾을 수 없습니다.</p>
                </div>
              )}
            </div>
            <div className="modal-actions" style={{ marginTop: '16px', display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              {projectVersion !== 0 && (
                <button
                  type="button"
                  className="button primary"
                  onClick={() => {
                    setShowOriginalModal(false)
                    handleRequestSwitchVersion({
                      id: 'v0_switch',
                      version: 0,
                      imageUrl: originalImageUrl || '',
                      createdAt: '원본',
                      regions: [],
                      label: '원본 (AI 인식 전)'
                    })
                  }}
                >
                  <RotateCcw size={14} style={{ marginRight: '5px' }} />
                  v0 원본 상태로 복원 및 편집
                </button>
              )}
              {originalImageUrl && (
                <a
                  className="outline"
                  style={{
                    color: '#1e293b',
                    background: '#ffffff',
                    border: '1px solid #cbd5e1',
                    textDecoration: 'none',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '8px 14px',
                    borderRadius: '7px',
                    fontWeight: 600,
                    fontSize: '13px'
                  }}
                  href={originalImageUrl}
                  download="original_image.png"
                >
                  <Download size={14} color="#1e293b" />
                  <span style={{ color: '#1e293b', fontWeight: 600 }}>원본 파일 다운로드</span>
                </a>
              )}
              <button
                type="button"
                className="outline"
                style={{
                  color: '#1e293b',
                  background: '#ffffff',
                  border: '1px solid #cbd5e1',
                  padding: '8px 16px',
                  borderRadius: '7px',
                  fontWeight: 600,
                  fontSize: '13px'
                }}
                onClick={() => setShowOriginalModal(false)}
              >
                <span style={{ color: '#1e293b', fontWeight: 600 }}>닫기</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Comparisons Modal */}
      {showComparisonModal && (
        <div className="modal-backdrop">
          <div className="modal wide">
            <button className="close" onClick={() => setShowComparisonModal(false)}>
              <X size={18} />
            </button>
            <h2>Before / After 교정 비교 리포트</h2>
            <div className="comparisons-scroll">
              {comparisons.map(c => (
                <div key={c.id} className="comp-item">
                  <img src={c.comparison_url} alt="Comparison" />
                  <div>
                    <span className="corrupted">원본: {c.observed}</span>
                    <span className="corrected">교정: {c.corrected}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Cutout Result Modal */}
      {cutoutModalUrl && (
        <div className="modal-backdrop">
          <div className="modal">
            <button className="close" onClick={() => setCutoutModalUrl(null)}>
              <X size={18} />
            </button>
            <h2>✂️ 누끼따기 완료</h2>
            <div className="cutout-preview">
              <img src={cutoutModalUrl} alt="Cutout" />
            </div>
            <div className="modal-actions">
              <a className="button full" href={cutoutModalUrl} download="cutout.png">
                <Download size={15} /> 투명 PNG 다운로드
              </a>
            </div>
          </div>
        </div>
      )}

      {/* AI Processing / Final High-Res Render In-Flight Modal */}
      {isProcessing && (
        <div className="modal-backdrop processing-backdrop">
          <div className="processing-modal-card">
            {processingType === 'render' ? (
              <>
                {/* 1. Final High-Resolution Rendering Modal View */}
                <div className="processing-spinner-wrap render-mode">
                  <div className="spinner-ring render-ring" />
                  <div className="spinner-core">
                    <Layers size={28} className="render-pulse-anim" />
                  </div>
                </div>

                <div className="processing-badge-tag">
                  <span className="model-tag-badge render-badge">
                    <Sparkles size={12} /> 초고화질 3X 슈퍼샘플링 합성 엔진
                  </span>
                </div>

                <h3>최종 고화질 렌더링 진행 중</h3>
                <p className="processing-live-status render-status">
                  {processingStatus || '설정된 나눔스퀘어/본고딕/페이퍼로지 서체 및 자간·장평을 고해상도로 합성하고 있습니다...'}
                </p>

                <div className="processing-timer-box">
                  <Clock size={15} />
                  <span>렌더링 경과: <b>{processElapsedSec}초</b></span>
                  <span className="expected-time-hint">(예상 약 3~5초 소요)</span>
                </div>

                <div className="processing-steps-flow">
                  <div className="step-flow-item done">✓ 1. 배경 인페인팅 검증</div>
                  <div className="step-flow-arrow">→</div>
                  <div className="step-flow-item done">✓ 2. 폰트/스타일 파라미터 매핑</div>
                  <div className="step-flow-arrow">→</div>
                  <div className="step-flow-item active render-step">3. 3X 슈퍼샘플링 합성 & 다운로드</div>
                </div>

                <small className="processing-note">
                  렌더링 완료 즉시 브라우저에서 초고화질 복원 이미지(PNG)가 자동으로 다운로드됩니다.
                </small>
              </>
            ) : (
              <>
                {/* 2. Standard AI VLM Analysis & Restoration Modal View */}
                <div className="processing-spinner-wrap">
                  <div className="spinner-ring" />
                  <div className="spinner-core">
                    <Sparkles size={26} className="sparkle-anim" />
                  </div>
                </div>

                <div className="processing-badge-tag">
                  {selectedEngine.startsWith('strata') ? (
                    <span className="model-tag-badge local">🛡️ 사내 폐쇄망 로컬 VLM ({selectedEngine === 'strata_thinking' ? '심층 CoT' : '고속'})</span>
                  ) : (
                    <span className="model-tag-badge azure">⚡ Azure GPT-6.1-sol 클라우드</span>
                  )}
                </div>

                <h3>AI 이미지 분석 및 복원 진행 중</h3>
                <p className="processing-live-status">
                  {processingStatus || 'AI 모델이 텍스트 및 레이아웃을 정밀 분석하고 있습니다...'}
                </p>

                <div className="processing-timer-box">
                  <Clock size={15} />
                  <span>진행 경과: <b>{processElapsedSec}초</b></span>
                  <span className="expected-time-hint">
                    {selectedEngine === 'strata_non_thinking' && '(예상 약 120초)'}
                    {selectedEngine === 'strata_thinking' && '(예상 약 3분 40초)'}
                    {selectedEngine === 'azure_gpt' && '(예상 약 120초)'}
                  </span>
                </div>

                {selectedEngine.startsWith('strata') && strataStatus?.busy && (strataStatus.waiting_count || 0) > 0 && (
                  <div className="queue-waiting-alert">
                    <AlertCircle size={15} />
                    <span>
                      다른 사용자의 작업이 앞서 진행 중입니다. 충돌 방지를 위해 대기열에서 안전하게 대기한 후 자동 실행됩니다. (대기열: {strataStatus.waiting_count}명)
                    </span>
                  </div>
                )}

                <div className="processing-steps-flow">
                  <div className="step-flow-item active">1. VLM 정밀 OCR & 오탈자 교정</div>
                  <div className="step-flow-arrow">→</div>
                  <div className="step-flow-item">2. 스마트 배경 인페인팅</div>
                  <div className="step-flow-arrow">→</div>
                  <div className="step-flow-item">3. 고화질 폰트 렌더링</div>
                </div>

                <small className="processing-note">
                  창을 닫거나 새로고침하지 마시고 잠시만 기다려 주세요. 분석 완료 시 자동으로 편집기 화면으로 전환됩니다.
                </small>
              </>
            )}
          </div>
        </div>
      )}

      {/* Switch Version Confirmation Modal */}
      {switchVersionTarget && (
        <div className="modal-backdrop">
          <div className="switch-version-modal-box">
            <div className="switch-version-header">
              <div className="switch-version-icon">
                <History size={20} />
              </div>
              <div>
                <h3>버전 이동 확인</h3>
                <small style={{ color: '#64748b' }}>이전 버전 상태로 워크스페이스를 복원합니다</small>
              </div>
            </div>

            <div className="switch-preview-row">
              <img
                src={switchVersionTarget.imageUrl}
                alt={switchVersionTarget.label}
                className="switch-preview-img"
              />
              <div className="switch-preview-details">
                <b>v{switchVersionTarget.version} ({switchVersionTarget.label})</b>
                <span>생성 일시: {switchVersionTarget.createdAt}</span>
                <span>블록 개수: {switchVersionTarget.regions?.length || 0}개</span>
              </div>
            </div>

            <div className="switch-auto-save-notice" style={{ background: '#fef3c7', borderColor: '#fcd34d', color: '#92400e' }}>
              <AlertCircle size={16} style={{ flexShrink: 0, color: '#b45309' }} />
              <div>
                <strong>현재 v{projectVersion}에 편집 중인 변경사항이 있습니다.</strong>
                <div style={{ fontSize: '11px', marginTop: '2px', opacity: 0.9 }}>
                  v{switchVersionTarget.version} 버전으로 이동하기 전에 작업 내용을 어떻게 처리할지 선택해 주세요.
                </div>
              </div>
            </div>

            <div className="switch-actions" style={{ flexDirection: 'column', gap: '8px', marginTop: '16px' }}>
              <button
                type="button"
                className="button primary full"
                style={{ justifyContent: 'center' }}
                onClick={handleConfirmSwitchWithSave}
              >
                <Save size={14} style={{ marginRight: '6px' }} />
                현재 버전에 저장 후 v{switchVersionTarget.version}으로 이동
              </button>

              <button
                type="button"
                className="outline full"
                style={{ justifyContent: 'center', borderColor: '#cbd5e1' }}
                onClick={handleConfirmSwitchKeepSessionDraft}
              >
                <Clock size={14} style={{ marginRight: '6px' }} />
                저장 안 함 (세션 임시 초안으로 보존하고 이동)
              </button>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%', marginTop: '6px' }}>
                <button
                  type="button"
                  className="switch-del-btn"
                  title={`v${switchVersionTarget.version} 버전 영구 삭제`}
                  onClick={() => {
                    const targetVer = switchVersionTarget.version
                    setSwitchVersionTarget(null)
                    handleDeleteRevision(targetVer)
                  }}
                >
                  <Trash2 size={13} />
                  <span>이 버전 삭제</span>
                </button>
                <button
                  type="button"
                  className="outline"
                  style={{ padding: '6px 14px' }}
                  onClick={() => setSwitchVersionTarget(null)}
                >
                  이동 취소
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Login Modal (Mandatory when unauthenticated) */}
      {showLoginModal && (
        <div className="modal-backdrop">
          <div className="modal">
            {currentUser && (
              <button className="close" onClick={() => setShowLoginModal(false)}>
                <X size={18} />
              </button>
            )}
            <h2>사내 계정 로그인</h2>
            <p>Fixit Studio 서비스를 이용하시려면 사내 계정으로 로그인해 주세요.</p>
            {loginError && <div className="error-alert" style={{ background: '#fee2e2', color: '#b91c1c', padding: '8px 12px', borderRadius: '6px', fontSize: '12px', marginBottom: '14px', border: '1px solid #fca5a5' }}>{loginError}</div>}

            <form onSubmit={handleLogin}>
              <div className="field">
                <span>이메일 또는 아이디</span>
                <input
                  type="text"
                  required
                  placeholder="예: icarus@kiast.or.kr 또는 icarus"
                  value={loginEmail}
                  onChange={e => setLoginEmail(e.target.value)}
                  autoFocus
                />
              </div>
              <div className="field">
                <span>비밀번호</span>
                <input
                  type="password"
                  required
                  placeholder="비밀번호 입력"
                  value={loginPassword}
                  onChange={e => setLoginPassword(e.target.value)}
                />
              </div>
              <button type="submit" className="button full" style={{ marginTop: '12px' }}>로그인</button>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
