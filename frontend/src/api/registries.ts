import { api } from '../lib/api'

export interface Registry {
  id: string
  name: string
  type: 'ECR' | 'ACR' | 'DOCKERHUB' | 'GAR' | 'GENERIC_OCI'
  registry_url: string
  region: string | null
  team_id: string
}

export const registriesApi = {
  list: () => api.get<Registry[]>('/api/registries').then(r => r.data),
  create: (body: Omit<Registry, 'id' | 'team_id'> & { credentials: unknown }) =>
    api.post<Registry>('/api/registries', body).then(r => r.data),
  validate: (id: string) =>
    api.post<{ status: string; detail?: string }>(`/api/registries/${id}/validate`).then(r => r.data),
  delete: (id: string) => api.delete(`/api/registries/${id}`),
}
