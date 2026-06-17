import { api } from '../lib/api'

export interface Image {
  id: string
  registry_id: string
  team_id: string
  repository: string
  tag: string
  last_digest: string | null
  service_type: 'UI' | 'BACKEND'
  base_dockerfile_path: string
  app_dockerfile_path: string
  gitlab_project_id: string
  gitlab_default_branch: string
}

export const imagesApi = {
  list: () => api.get<Image[]>('/api/images').then(r => r.data),
  get: (id: string) => api.get<Image>(`/api/images/${id}`).then(r => r.data),
  create: (body: Omit<Image, 'id' | 'team_id' | 'last_digest'> & { credentials?: unknown }) =>
    api.post<Image>('/api/images', body).then(r => r.data),
  delete: (id: string) => api.delete(`/api/images/${id}`),
}
