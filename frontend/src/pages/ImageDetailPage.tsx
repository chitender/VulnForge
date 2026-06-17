import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { imagesApi } from '../api/images'
import { scansApi } from '../api/scans'

export function ImageDetailPage() {
  const { id } = useParams<{ id: string }>()
  const qc = useQueryClient()

  const imgQ = useQuery({
    queryKey: ['image', id],
    queryFn: () => imagesApi.get(id!),
  })

  const scanMut = useMutation({
    mutationFn: () => scansApi.trigger(id!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['image', id] }),
  })

  const img = imgQ.data

  if (imgQ.isLoading) {
    return <p className="text-slate-400">Loading…</p>
  }

  if (!img) {
    return <p className="text-red-400">Image not found.</p>
  }

  return (
    <div className="max-w-3xl">
      {/* Header */}
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-slate-100">
          {img.repository}
          <span className="text-slate-400 font-normal">:{img.tag}</span>
        </h2>
        <p className="text-slate-500 text-sm mt-1">
          {img.gitlab_project_id} · {img.service_type}
        </p>
      </div>

      {/* Scan now */}
      <div className="mb-6 flex items-center gap-4">
        <button
          onClick={() => scanMut.mutate()}
          disabled={scanMut.isPending}
          className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-4 py-2 rounded text-sm font-medium transition-colors"
        >
          {scanMut.isPending ? 'Queueing…' : 'Scan Now'}
        </button>
        {scanMut.data && (
          <Link
            to={`/scans/${scanMut.data.scan_id}`}
            className="text-blue-400 hover:underline text-sm"
          >
            View scan results →
          </Link>
        )}
        {scanMut.isError && (
          <p className="text-red-400 text-sm">Failed to trigger scan</p>
        )}
      </div>

      {/* Re-scan recommended banner (shown after MR merges — Phase 7) */}

      {/* Image metadata */}
      <div className="bg-slate-800 rounded-lg p-4 text-sm space-y-3">
        <div className="grid grid-cols-2 gap-x-4 gap-y-2">
          <span className="text-slate-500">Registry</span>
          <span className="text-slate-300 font-mono text-xs">{img.registry_id}</span>

          <span className="text-slate-500">Base Dockerfile</span>
          <span className="text-slate-300 font-mono text-xs">{img.base_dockerfile_path}</span>

          <span className="text-slate-500">App Dockerfile</span>
          <span className="text-slate-300 font-mono text-xs">{img.app_dockerfile_path}</span>

          <span className="text-slate-500">Default branch</span>
          <span className="text-slate-300 font-mono text-xs">{img.gitlab_default_branch}</span>

          {img.last_digest && (
            <>
              <span className="text-slate-500">Last digest</span>
              <span className="text-slate-300 font-mono text-xs break-all">{img.last_digest}</span>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
