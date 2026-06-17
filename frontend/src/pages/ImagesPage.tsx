import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { imagesApi } from '../api/images'

export function ImagesPage() {
  const { data, isLoading } = useQuery({ queryKey: ['images'], queryFn: imagesApi.list })
  if (isLoading) return <p className="text-slate-400">Loading…</p>
  return (
    <div>
      <h2 className="text-xl font-semibold text-slate-100 mb-6">Images</h2>
      <div className="space-y-2">
        {(data ?? []).map(img => (
          <Link key={img.id} to={`/images/${img.id}`}
            className="block bg-slate-800 rounded p-4 hover:bg-slate-700 transition-colors">
            <p className="text-slate-100 font-medium">{img.repository}:{img.tag}</p>
            <p className="text-slate-500 text-sm">{img.service_type} · {img.gitlab_project_id}</p>
          </Link>
        ))}
        {(data ?? []).length === 0 && <p className="text-slate-500">No images registered yet.</p>}
      </div>
    </div>
  )
}
