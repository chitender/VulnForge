export const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: '#ef4444',  // red-500
  HIGH: '#f97316',      // orange-500
  MEDIUM: '#eab308',    // yellow-400
  LOW: '#60a5fa',       // blue-400
  UNKNOWN: '#94a3b8',   // slate-400
}

export const SEVERITY_ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'UNKNOWN'] as const
export type SeverityLevel = typeof SEVERITY_ORDER[number]
