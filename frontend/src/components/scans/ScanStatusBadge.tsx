const STATUS_STYLES: Record<string, string> = {
  QUEUED:    'bg-slate-700 text-slate-300',
  RUNNING:   'bg-blue-900 text-blue-300 animate-pulse',
  SUCCEEDED: 'bg-green-900 text-green-300',
  FAILED:    'bg-red-900 text-red-300',
}

export function ScanStatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
        STATUS_STYLES[status] ?? STATUS_STYLES.QUEUED
      }`}
    >
      {status}
    </span>
  )
}
