export type FontFamily = 'NanumSquare' | 'NotoSansKR' | 'Paperlogy'
export type FontWeight = 'Regular' | 'Bold' | 'ExtraBold'

export interface Region {
  id: string
  observed: string
  corrected: string
  bbox: [number, number, number, number] // [x, y, width, height]
  clean_bbox?: [number, number, number, number]
  font_family: FontFamily
  font_weight: FontWeight
  font_size: number
  scale_x: number // 장평 (0.80 ~ 1.20)
  letter_spacing: number // 자간 (-3.0 ~ +3.0 px)
  line_gap: number // 행간 (0 ~ 40 px)
  text_color: string
  align: 'left' | 'center' | 'right'
  valign?: 'top' | 'center' | 'bottom'
}

export interface UserProfile {
  id: number
  email: string
  name: string
  department?: string
  is_admin?: boolean
}

export type AIModelType = 'strata_non_thinking' | 'strata_thinking' | 'azure_gpt'

export interface ProjectInfo {
  id: number
  name: string
  version: number
  original_image_path: string
  background_image_path?: string | null
  current_image_path?: string | null
  regions_count?: number
  metadata?: any
  created_at?: string
  updated_at?: string
}

export interface ComparisonItem {
  id: string
  observed: string
  corrected: string
  bbox: [number, number, number, number]
  comparison_url: string
}

export interface AutoRestoreResult {
  task_id: string
  background_image_url: string
  restored_image_url: string
  regions: Region[]
  comparisons: ComparisonItem[]
  metadata?: any
  elapsed_seconds?: {
    ocr: number
    inpaint: number
    typography_render: number
    total: number
  }
}

export interface StrataStatus {
  online: boolean
  busy: boolean
  waiting_count: number
  model: string | null
  max_context: number
  current_task?: {
    task_name: string
    model_type: string
    started_at: string
  } | null
  current_task_elapsed_sec: number
}

export interface CompletedThumbnail {
  id: string | number
  version: number
  imageUrl: string
  bgImageUrl?: string
  regions?: Region[]
  createdAt: string
  label?: string
}
