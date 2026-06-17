import type { MergeRequest } from '../../api/mergeRequests'

const PIPELINE_BADGE: Record<string, { label: string; className: string }> = {
  PASSED:  { label: '✓ CI passed',  className: 'bg-green-900 text-green-300' },
  FAILED:  { label: '✗ CI failed',  className: 'bg-red-900 text-red-300' },
  RUNNING: { label: '⟳ CI running', className: 'bg-blue-900 text-blue-300 animate-pulse' },
  PENDING: { label: '· pending',    className: 'bg-slate-700 text-slate-400' },
  UNKNOWN: { label: '? unknown',    className: 'bg-slate-700 text-slate-400' },
}

const STATE_BADGE: Record<string, string> = {
  OPENED: 'bg-blue-900 text-blue-300',
  MERGED: 'bg-green-900 text-green-300',
  CLOSED: 'bg-slate-700 text-slate-400',
  FAILED: 'bg-red-900 text-red-300',
}

interface Props {
  mrs: MergeRequest[]
}

export function MRTable({ mrs }: Props) {
  if (mrs.length === 0) {
    return (
      <div className="text-center py-16 text-slate-500">
        <p className="text-4xl mb-3">🔒</p>
        <p className="text-sm">No merge requests yet.</p>
        <p className="text-xs mt-1">
          Scan an image, select fixable findings, and click "Raise MR".
        </p>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-slate-400 border-b border-slate-700">
            <th className="pb-2 pr-4">Source branch</th>
            <th className="pb-2 pr-4">Target</th>
            <th className="pb-2 pr-4">Kind</th>
            <th className="pb-2 pr-4">State</th>
            <th className="pb-2 pr-4">CI</th>
            <th className="pb-2">Link</th>
          </tr>
        </thead>
        <tbody>
          {mrs.map(mr => {
            const pipeline =
              PIPELINE_BADGE[mr.pipeline_status ?? 'UNKNOWN'] ??
              PIPELINE_BADGE.UNKNOWN
            return (
              <tr
                key={mr.id}
                className="border-b border-slate-800 hover:bg-slate-800/40 transition-colors"
              >
                <td className="py-3 pr-4 font-mono text-xs text-slate-300 max-w-[200px] truncate">
                  {mr.source_branch ?? '—'}
                </td>
                <td className="py-3 pr-4 font-mono text-xs text-slate-400">
                  {mr.target_branch}
                </td>
                <td className="py-3 pr-4 text-xs text-slate-400">
                  {mr.target_kind.replace('_DOCKERFILE', '')}
                </td>
                <td className="py-3 pr-4">
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-medium ${
                      STATE_BADGE[mr.state] ?? STATE_BADGE.CLOSED
                    }`}
                  >
                    {mr.state}
                  </span>
                </td>
                <td className="py-3 pr-4">
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-medium ${pipeline.className}`}
                  >
                    {pipeline.label}
                  </span>
                </td>
                <td className="py-3">
                  {mr.gitlab_mr_url ? (
                    <a
                      href={mr.gitlab_mr_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-400 hover:underline text-xs"
                    >
                      View MR ↗
                    </a>
                  ) : (
                    <span className="text-slate-600 text-xs">—</span>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
