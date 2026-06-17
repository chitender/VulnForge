import { api } from '../lib/api'

export interface Scan {
  id: string
  image_id: string
  status: 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED'
  image_digest: string | null
  trivy_version: string | null
  summary_jsonb: { by_severity: Record<string, number>; total: number; fixable: number } | null
  error_text: string | null
}

export interface Finding {
  id: string
  scan_id: string
  vuln_id: string
  pkg_name: string
  installed_version: string
  fixed_version: string | null
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'UNKNOWN'
  target: string | null
  title: string | null
  primary_url: string | null
  is_fixable: boolean
  status: 'OPEN' | 'SELECTED' | 'MR_RAISED' | 'IGNORED' | 'RESOLVED'
}

export const scansApi = {
  trigger: (imageId: string) =>
    api.post<{ scan_id: string; status: string }>(`/api/images/${imageId}/scans`).then(r => r.data),
  get: (scanId: string) => api.get<Scan>(`/api/scans/${scanId}`).then(r => r.data),
  findings: (scanId: string, params?: { severity?: string; fixable_only?: boolean }) =>
    api.get<Finding[]>(`/api/scans/${scanId}/findings`, { params }).then(r => r.data),
}
