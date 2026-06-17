import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { mrApi, type RaiseMRBody } from '../../api/mergeRequests'
import { resolveBranchPreview } from '../../lib/branchPreview'
import type { Finding } from '../../api/scans'

interface Props {
  open: boolean
  onClose: () => void
  scanId: string
  imageId: string
  imageRepo: string
  imageTag: string
  findings: Finding[]
  selectedIds: Set<string>
}

export function RaiseMRDrawer({
  open,
  onClose,
  scanId,
  imageRepo,
  imageTag,
  findings,
  selectedIds,
}: Props) {
  const [template, setTemplate] = useState('feature/patchpilot-{image}-{date}')
  const [targetBranch, setTargetBranch] = useState('main')
  const [version, setVersion] = useState('')
  const [gitlabToken, setGitlabToken] = useState('')
  const [targets, setTargets] = useState<('BASE_DOCKERFILE' | 'APP_DOCKERFILE')[]>([
    'APP_DOCKERFILE',
  ])
  const [mrType, setMrType] = useState<'FEATURE' | 'HOTFIX'>('FEATURE')

  const today = new Date().toISOString().split('T')[0]
  const imageSlug = imageRepo.replace(/\//g, '-')

  const previewBranch = resolveBranchPreview(template, {
    image: imageSlug,
    date: today,
    version: version || '{version}',
    tag: imageTag,
  })

  const selectedFindings = findings.filter(f => selectedIds.has(f.id))

  const mut = useMutation({
    mutationFn: (body: RaiseMRBody) => mrApi.create(body),
    onSuccess: () => onClose(),
  })

  if (!open) return null

  const toggleTarget = (t: 'BASE_DOCKERFILE' | 'APP_DOCKERFILE', checked: boolean) => {
    setTargets(prev => (checked ? [...prev, t] : prev.filter(x => x !== t)))
  }

  return (
    <div className="fixed inset-0 z-50 flex" role="dialog" aria-modal>
      {/* Backdrop */}
      <div className="flex-1 bg-black/50" onClick={onClose} />

      {/* Drawer */}
      <div className="w-[560px] bg-slate-800 border-l border-slate-700 overflow-y-auto flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-slate-700 shrink-0">
          <h2 className="text-lg font-semibold text-slate-100">Raise MR</h2>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 text-xl leading-none"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div className="p-5 space-y-5 flex-1 overflow-y-auto">
          {/* MR type */}
          <div>
            <label className="block text-xs text-slate-400 mb-1 font-medium">MR Type</label>
            <div className="flex gap-2">
              {(['FEATURE', 'HOTFIX'] as const).map(t => (
                <button
                  key={t}
                  onClick={() => setMrType(t)}
                  className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
                    mrType === t
                      ? 'bg-blue-600 text-white'
                      : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                  }`}
                >
                  {t.toLowerCase()}
                </button>
              ))}
            </div>
          </div>

          {/* Dockerfile targets */}
          <div>
            <label className="block text-xs text-slate-400 mb-1 font-medium">
              Dockerfile targets
            </label>
            <div className="flex gap-4">
              {(
                [
                  ['BASE_DOCKERFILE', 'Base Dockerfile'],
                  ['APP_DOCKERFILE', 'App Dockerfile'],
                ] as const
              ).map(([val, label]) => (
                <label
                  key={val}
                  className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={targets.includes(val)}
                    onChange={e => toggleTarget(val, e.target.checked)}
                  />
                  {label}
                </label>
              ))}
            </div>
            {targets.length === 0 && (
              <p className="text-amber-400 text-xs mt-1">Select at least one target</p>
            )}
          </div>

          {/* Branch template */}
          <div>
            <label className="block text-xs text-slate-400 mb-1 font-medium">
              Source branch template{' '}
              <span className="text-slate-600 font-normal">
                — vars: {'{image}'} {'{date}'} {'{version}'} {'{tag}'}
              </span>
            </label>
            <input
              className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-1.5 text-sm text-slate-100 font-mono focus:border-blue-500 focus:outline-none"
              value={template}
              onChange={e => setTemplate(e.target.value)}
              spellCheck={false}
            />
            <p className="mt-1 text-xs text-blue-400 font-mono truncate" title={previewBranch}>
              → {previewBranch || <span className="text-slate-600">enter a template above</span>}
            </p>
          </div>

          {/* Version field — shown when template contains {version} */}
          {template.includes('{version}') && (
            <div>
              <label className="block text-xs text-slate-400 mb-1 font-medium">
                Version value{' '}
                <span className="text-slate-600 font-normal">— fills {'{version}'}</span>
              </label>
              <input
                className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-1.5 text-sm text-slate-100 focus:border-blue-500 focus:outline-none"
                placeholder="e.g. 1.4.2"
                value={version}
                onChange={e => setVersion(e.target.value)}
              />
            </div>
          )}

          {/* Target branch */}
          <div>
            <label className="block text-xs text-slate-400 mb-1 font-medium">
              Target branch{' '}
              <span className="text-slate-600 font-normal">— merge into</span>
            </label>
            <input
              className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-1.5 text-sm text-slate-100 font-mono focus:border-blue-500 focus:outline-none"
              value={targetBranch}
              onChange={e => setTargetBranch(e.target.value)}
              spellCheck={false}
            />
          </div>

          {/* GitLab token */}
          <div>
            <label className="block text-xs text-slate-400 mb-1 font-medium">
              GitLab token{' '}
              <span className="text-slate-600 font-normal">— write-only, not stored</span>
            </label>
            <input
              type="password"
              className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-1.5 text-sm text-slate-100 focus:border-blue-500 focus:outline-none"
              placeholder="glpat-…"
              value={gitlabToken}
              onChange={e => setGitlabToken(e.target.value)}
              autoComplete="off"
            />
          </div>

          {/* CVE table */}
          <div>
            <p className="text-xs text-slate-400 mb-2 font-medium">
              Fixing {selectedFindings.length} finding
              {selectedFindings.length !== 1 ? 's' : ''}:
            </p>
            <div className="bg-slate-900 rounded p-3 max-h-48 overflow-y-auto space-y-1.5">
              {selectedFindings.map(f => (
                <div key={f.id} className="flex justify-between items-center text-xs gap-2">
                  <span className="font-mono text-blue-400 shrink-0">{f.vuln_id}</span>
                  <span className="text-slate-400 truncate">
                    {f.pkg_name}{' '}
                    <span className="text-slate-600">→</span>{' '}
                    <span className="text-green-400">{f.fixed_version}</span>
                  </span>
                </div>
              ))}
              {selectedFindings.length === 0 && (
                <p className="text-slate-600 text-xs">No findings selected</p>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-5 border-t border-slate-700 shrink-0 space-y-2">
          <button
            disabled={
              targets.length === 0 ||
              selectedIds.size === 0 ||
              !gitlabToken.trim() ||
              mut.isPending
            }
            onClick={() =>
              mut.mutate({
                scan_id: scanId,
                finding_ids: [...selectedIds],
                mr_type: mrType,
                targets,
                source_branch_template: template,
                target_branch: targetBranch,
                gitlab_token: gitlabToken,
                template_vars: {
                  version,
                  image: imageSlug,
                  date: today,
                  tag: imageTag,
                },
              })
            }
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed text-white py-2 rounded text-sm font-medium transition-colors"
          >
            {mut.isPending
              ? 'Creating MR…'
              : `Create ${targets.length} MR${targets.length !== 1 ? 's' : ''}`}
          </button>
          {!gitlabToken.trim() && (
            <p className="text-slate-500 text-xs text-center">Enter a GitLab token to create MRs</p>
          )}
          {mut.isError && (
            <p className="text-red-400 text-xs">Error: {String(mut.error)}</p>
          )}
          {mut.isSuccess && (
            <p className="text-green-400 text-xs text-center">MR queued successfully!</p>
          )}
        </div>
      </div>
    </div>
  )
}
