import { useQuery } from '@tanstack/react-query'
import { mrApi } from '../api/mergeRequests'
import { MRTable } from '../components/mr/MRTable'

export function MergeRequestsPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['merge-requests'],
    queryFn: mrApi.list,
    refetchInterval: 15_000,  // refresh every 15s to pick up pipeline status changes
  })

  return (
    <div className="max-w-6xl">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold text-slate-100">Merge Requests</h2>
        {data && data.length > 0 && (
          <span className="text-slate-500 text-sm">{data.length} total</span>
        )}
      </div>

      {isLoading && <p className="text-slate-400">Loading…</p>}
      {isError && (
        <p className="text-red-400">Failed to load merge requests.</p>
      )}
      {!isLoading && !isError && <MRTable mrs={data ?? []} />}
    </div>
  )
}
