import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { scansApi } from '../api/scans'
import { FindingsTable } from '../components/scans/FindingsTable'
import { ScanStatusBadge } from '../components/scans/ScanStatusBadge'
import { SeverityDonut } from '../components/scans/SeverityDonut'

export function ScanResultsPage() {
  const { id } = useParams<{ id: string }>()
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  const scanQ = useQuery({
    queryKey: ['scan', id],
    queryFn: () => scansApi.get(id!),
    // Poll every 3s while the scan is still active
    refetchInterval: query => {
      const status = query.state.data?.status
      return status === 'QUEUED' || status === 'RUNNING' ? 3000 : false
    },
  })

  const findingsQ = useQuery({
    queryKey: ['findings', id],
    queryFn: () => scansApi.findings(id!),
    enabled: scanQ.data?.status === 'SUCCEEDED',
  })

  const toggle = (fid: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      next.has(fid) ? next.delete(fid) : next.add(fid)
      return next
    })
  }

  const scan = scanQ.data

  return (
    <div className="max-w-6xl">
      {/* Header */}
      <div className="flex items-center gap-4 mb-6">
        <h2 className="text-xl font-semibold text-slate-100">Scan Results</h2>
        {scan && <ScanStatusBadge status={scan.status} />}
        {scan?.image_digest && (
          <span className="text-slate-500 font-mono text-xs ml-auto">
            {scan.image_digest.slice(0, 19)}…
          </span>
        )}
      </div>

      {/* Summary + donut */}
      {scan?.status === 'SUCCEEDED' && scan.summary_jsonb && (
        <div className="flex gap-8 mb-8 bg-slate-800/50 rounded-lg p-4">
          <SeverityDonut summary={scan.summary_jsonb.by_severity} />
          <div className="text-slate-300 self-center space-y-2">
            <p className="text-2xl font-bold text-slate-100">{scan.summary_jsonb.total}</p>
            <p className="text-slate-400 text-sm">total findings</p>
            <p className="text-green-400 font-medium mt-2">
              {scan.summary_jsonb.fixable} fixable
            </p>
            <p className="text-slate-500 text-sm">
              {scan.summary_jsonb.total - scan.summary_jsonb.fixable} no fix available
            </p>
          </div>
        </div>
      )}

      {/* Findings table */}
      {findingsQ.data && findingsQ.data.length > 0 && (
        <>
          <FindingsTable
            findings={findingsQ.data}
            selectedIds={selectedIds}
            onToggle={toggle}
          />

          {/* Sticky raise-MR bar */}
          {selectedIds.size > 0 && (
            <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-blue-600 text-white px-6 py-3 rounded-lg shadow-xl flex items-center gap-4 z-50">
              <span className="text-sm">
                {selectedIds.size} finding{selectedIds.size > 1 ? 's' : ''} selected
              </span>
              <button className="bg-white text-blue-600 px-4 py-1 rounded font-medium text-sm hover:bg-blue-50 transition-colors">
                Raise MR →
              </button>
            </div>
          )}
        </>
      )}

      {/* Active scan */}
      {(scan?.status === 'QUEUED' || scan?.status === 'RUNNING') && (
        <div className="flex items-center gap-3 text-slate-400 mt-8">
          <div className="h-2 w-2 rounded-full bg-blue-400 animate-pulse" />
          <span className="text-sm">
            Scan {scan.status === 'QUEUED' ? 'queued' : 'running'}…
          </span>
        </div>
      )}

      {/* Error */}
      {scan?.status === 'FAILED' && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300 mt-4">
          <p className="font-medium mb-1">Scan failed</p>
          <p className="text-sm font-mono">{scan.error_text}</p>
        </div>
      )}
    </div>
  )
}
