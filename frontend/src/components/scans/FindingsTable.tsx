import { useState } from 'react'
import type { Finding } from '../../api/scans'
import { SEVERITY_COLORS } from '../../lib/severity'

interface Props {
  findings: Finding[]
  selectedIds: Set<string>
  onToggle: (id: string) => void
}

export function FindingsTable({ findings, selectedIds, onToggle }: Props) {
  const [filterSeverity, setFilterSeverity] = useState('')
  const [fixableOnly, setFixableOnly] = useState(false)

  const filtered = findings.filter(f => {
    if (filterSeverity && f.severity !== filterSeverity) return false
    if (fixableOnly && !f.is_fixable) return false
    return true
  })

  return (
    <div>
      {/* Filter bar */}
      <div className="flex gap-3 mb-4 items-center">
        <select
          className="bg-slate-800 text-slate-200 border border-slate-600 rounded px-2 py-1 text-sm"
          value={filterSeverity}
          onChange={e => setFilterSeverity(e.target.value)}
        >
          <option value="">All severities</option>
          {['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'UNKNOWN'].map(s => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
          <input
            type="checkbox"
            checked={fixableOnly}
            onChange={e => setFixableOnly(e.target.checked)}
          />
          Fixable only
        </label>
        <span className="text-slate-500 text-sm ml-auto">{filtered.length} findings</span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-400 border-b border-slate-700">
              <th className="pb-2 w-8" />
              <th className="pb-2">CVE</th>
              <th className="pb-2">Package</th>
              <th className="pb-2">Installed</th>
              <th className="pb-2">Fixed</th>
              <th className="pb-2">Severity</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(f => (
              <tr key={f.id} className="border-b border-slate-800 hover:bg-slate-800/40">
                <td className="py-2">
                  <input
                    type="checkbox"
                    checked={selectedIds.has(f.id)}
                    onChange={() => onToggle(f.id)}
                    disabled={!f.is_fixable}
                    className="cursor-pointer disabled:cursor-not-allowed disabled:opacity-30"
                  />
                </td>
                <td className="py-2">
                  {f.primary_url ? (
                    <a
                      href={f.primary_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-400 hover:underline font-mono text-xs"
                    >
                      {f.vuln_id}
                    </a>
                  ) : (
                    <span className="font-mono text-xs text-slate-300">{f.vuln_id}</span>
                  )}
                </td>
                <td className="py-2 text-slate-200">{f.pkg_name}</td>
                <td className="py-2 text-slate-400 font-mono text-xs">{f.installed_version}</td>
                <td className="py-2 font-mono text-xs">
                  {f.fixed_version
                    ? <span className="text-green-400">{f.fixed_version}</span>
                    : <span className="text-slate-600">—</span>}
                </td>
                <td className="py-2">
                  <span
                    className="px-2 py-0.5 rounded text-xs font-medium"
                    style={{
                      backgroundColor: SEVERITY_COLORS[f.severity] + '22',
                      color: SEVERITY_COLORS[f.severity],
                    }}
                  >
                    {f.severity}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {filtered.length === 0 && (
          <p className="text-slate-500 text-sm mt-4 text-center py-8">
            No findings match the current filters.
          </p>
        )}
      </div>
    </div>
  )
}
