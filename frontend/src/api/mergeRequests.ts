import { api } from '../lib/api'

export interface MergeRequest {
  id: string
  image_id: string
  scan_id: string
  mr_type: 'FEATURE' | 'HOTFIX'
  target_kind: 'BASE_DOCKERFILE' | 'APP_DOCKERFILE'
  gitlab_project_id: string
  gitlab_mr_iid: number | null
  gitlab_mr_url: string | null
  source_branch: string | null
  target_branch: string
  state: 'OPENED' | 'MERGED' | 'CLOSED' | 'FAILED'
  pipeline_status: 'PENDING' | 'RUNNING' | 'PASSED' | 'FAILED' | 'UNKNOWN' | null
  finding_ids: string[]
  image_digest: string
}

export interface RaiseMRBody {
  scan_id: string
  finding_ids: string[]
  mr_type: 'FEATURE' | 'HOTFIX'
  targets: ('BASE_DOCKERFILE' | 'APP_DOCKERFILE')[]
  source_branch_template: string
  target_branch: string
  gitlab_token: string  // write-only, sent to backend but never stored in state
  template_vars: Record<string, string>
}

export const mrApi = {
  list: () => api.get<MergeRequest[]>('/api/merge-requests').then(r => r.data),
  get: (id: string) => api.get<MergeRequest>(`/api/merge-requests/${id}`).then(r => r.data),
  create: (body: RaiseMRBody) =>
    api.post<MergeRequest[]>('/api/merge-requests', body).then(r => r.data),
  sync: (id: string) =>
    api.post<MergeRequest>(`/api/merge-requests/${id}/sync`).then(r => r.data),
}
