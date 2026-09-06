export type CameraStatus = 'in_stock' | 'allocated' | 'deployed'

export type UserRole = 'reserve_admin' | 'range_user'

export type ChangeType =
  | 'registered'
  | 'allocated'
  | 'transferred'
  | 'deployed'
  | 'details_updated'
  | 'returned_to_stock'

export interface User {
  id: number
  email: string
  full_name: string
  role: UserRole
  range_id: number | null
  range_name: string | null
}

export interface Beat {
  id: number
  name: string
  range_id: number
}

export interface Range {
  id: number
  name: string
  beats: Beat[]
}

export interface Camera {
  id: number
  serial_number: string
  model: string | null
  status: CameraStatus
  range_id: number | null
  range_name: string | null
  beat_id: number | null
  beat_name: string | null
  site_name: string | null
  latitude: number | null
  longitude: number | null
  contact_name: string | null
  contact_phone: string | null
  notes: string | null
  allocated_at: string | null
  deployed_at: string | null
  created_at: string
  updated_at: string
}

export interface HistoryEntry {
  id: number
  camera_id: number
  camera_serial: string | null
  change_type: ChangeType
  changed_at: string
  changed_by_user_id: number | null
  changed_by_name: string | null
  changed_by_email: string | null
  from_range_id: number | null
  to_range_id: number | null
  from_range_name: string | null
  to_range_name: string | null
  from_beat_id: number | null
  to_beat_id: number | null
  from_beat_name: string | null
  to_beat_name: string | null
  from_site_name: string | null
  to_site_name: string | null
  from_status: CameraStatus | null
  to_status: CameraStatus | null
  from_latitude: number | null
  to_latitude: number | null
  from_longitude: number | null
  to_longitude: number | null
  from_contact_name: string | null
  to_contact_name: string | null
  from_contact_phone: string | null
  to_contact_phone: string | null
  note: string | null
}

export interface CameraDetail extends Camera {
  history: HistoryEntry[]
}

export interface CameraListResponse {
  items: Camera[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface RangeBreakdown {
  range_id: number
  range_name: string
  total: number
  allocated: number
  deployed: number
}

export interface ImportResult {
  total_rows: number
  created_count: number
  skipped_count: number
  error_count: number
  created: string[]
  skipped: { serial_number: string; reason: string }[]
  errors: { row: number; serial_number: string; message: string }[]
}

export interface Summary {
  total: number
  in_stock: number
  allocated: number
  deployed: number
  by_range: RangeBreakdown[]
}

export const STATUS_LABELS: Record<CameraStatus, string> = {
  in_stock: 'In stock',
  allocated: 'Allocated',
  deployed: 'Deployed',
}

export const CHANGE_LABELS: Record<ChangeType, string> = {
  registered: 'Registered',
  allocated: 'Allocated to a range',
  transferred: 'Transferred',
  deployed: 'Deployed',
  details_updated: 'Details updated',
  returned_to_stock: 'Returned to stock',
}
