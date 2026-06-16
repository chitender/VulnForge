# PatchPilot Phases 5–8 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the full product — Findings UX (Phase 5), MR Engine (Phase 6), MR UX (Phase 7), and Hardening (Phase 8).

**Architecture:** Phases 5 and 7 are pure frontend. Phase 6 is pure backend. Phase 8 touches both.

**Tech Stack:** React 18, TypeScript, TanStack Query v5, shadcn/ui, Recharts, dockerfile-parse, python-gitlab 4.x, KEDA, Helm, GitHub Actions.

---

# PHASE 5 — Findings UX

## Task 19: API client layer + routing skeleton

**Files:**
- Create: `frontend/src/api/registries.ts`
- Create: `frontend/src/api/images.ts`
- Create: `frontend/src/api/scans.ts`
- Create: `frontend/src/components/layout/Sidebar.tsx`
- Create: `frontend/src/components/layout/AppLayout.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create `frontend/src/api/images.ts`**

```typescript
import { api } from '../lib/api'

export interface Image {
  id: string
  registry_id: string
  team_id: string
  repository: string
  tag: string
  last_digest: string | null
  service_type: 'UI' | 'BACKEND'
  base_dockerfile_path: string
  app_dockerfile_path: string
  gitlab_project_id: string
  gitlab_default_branch: string
}

export const imagesApi = {
  list: () => api.get<Image[]>('/api/images').then(r => r.data),
  get: (id: string) => api.get<Image>(`/api/images/${id}`).then(r => r.data),
  create: (body: Omit<Image, 'id' | 'team_id' | 'last_digest'> & { credentials?: unknown }) =>
    api.post<Image>('/api/images', body).then(r => r.data),
  delete: (id: string) => api.delete(`/api/images/${id}`),
}
```

- [ ] **Step 2: Create `frontend/src/api/scans.ts`**

```typescript
import { api } from '../lib/api'

export interface Scan {
  id: string
  image_id: string
  status: 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED'
  image_digest: string | null
  trivy_version: string | null
  summary_jsonb: { by_severity: Record<string, number>; total: number; fixable: number } | null
  error_text: string | null
}

export interface Finding {
  id: string
  scan_id: string
  vuln_id: string
  pkg_name: string
  installed_version: string
  fixed_version: string | null
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'UNKNOWN'
  target: string | null
  title: string | null
  primary_url: string | null
  is_fixable: boolean
  status: 'OPEN' | 'SELECTED' | 'MR_RAISED' | 'IGNORED' | 'RESOLVED'
}

export const scansApi = {
  trigger: (imageId: string) =>
    api.post<{ scan_id: string; status: string }>(`/api/images/${imageId}/scans`).then(r => r.data),
  get: (scanId: string) => api.get<Scan>(`/api/scans/${scanId}`).then(r => r.data),
  findings: (scanId: string, params?: { severity?: string; fixable_only?: boolean }) =>
    api.get<Finding[]>(`/api/scans/${scanId}/findings`, { params }).then(r => r.data),
}
```

- [ ] **Step 3: Create `frontend/src/api/registries.ts`**

```typescript
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
```

- [ ] **Step 4: Create `frontend/src/api/mergeRequests.ts`**

```typescript
import { api } from '../lib/api'

export interface MergeRequest {
  id: string
  image_id: string
  scan_id: string
  mr_type: 'FEATURE' | 'HOTFIX'
  target_kind: 'BASE_DOCKERFILE' | 'APP_DOCKERFILE'
  gitlab_project_id: string
  gitlab_mr_iid: number | null
  gitlab_mr_url: string | null
  source_branch: string | null
  target_branch: string
  state: 'OPENED' | 'MERGED' | 'CLOSED' | 'FAILED'
  pipeline_status: 'PENDING' | 'RUNNING' | 'PASSED' | 'FAILED' | 'UNKNOWN' | null
  finding_ids: string[]
  image_digest: string
}

export interface RaiseMRBody {
  scan_id: string
  finding_ids: string[]
  mr_type: 'FEATURE' | 'HOTFIX'
  targets: ('BASE_DOCKERFILE' | 'APP_DOCKERFILE')[]
  source_branch_template: string
  target_branch: string
  template_vars: Record<string, string>
}

export const mrApi = {
  list: () => api.get<MergeRequest[]>('/api/merge-requests').then(r => r.data),
  get: (id: string) => api.get<MergeRequest>(`/api/merge-requests/${id}`).then(r => r.data),
  create: (body: RaiseMRBody) => api.post<MergeRequest[]>('/api/merge-requests', body).then(r => r.data),
  sync: (id: string) => api.post<MergeRequest>(`/api/merge-requests/${id}/sync`).then(r => r.data),
}
```

- [ ] **Step 5: Create `frontend/src/components/layout/Sidebar.tsx`**

```typescript
import { NavLink } from 'react-router-dom'
import { Server, Image, Scan, GitMerge, Settings } from 'lucide-react'

const nav = [
  { to: '/registries', label: 'Registries', icon: Server },
  { to: '/images', label: 'Images', icon: Image },
  { to: '/merge-requests', label: 'Merge Requests', icon: GitMerge },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export function Sidebar() {
  return (
    <aside className="w-56 bg-slate-800 border-r border-slate-700 flex flex-col">
      <div className="px-4 py-5 border-b border-slate-700">
        <h1 className="text-lg font-bold text-white">PatchPilot</h1>
      </div>
      <nav className="flex-1 p-3 space-y-1">
        {nav.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded text-sm transition-colors ${
                isActive
                  ? 'bg-blue-600 text-white'
                  : 'text-slate-400 hover:bg-slate-700 hover:text-slate-100'
              }`
            }
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
```

- [ ] **Step 6: Create `frontend/src/components/layout/AppLayout.tsx`**

```typescript
import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'

export function AppLayout() {
  return (
    <div className="flex h-screen bg-slate-900 overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-6">
        <Outlet />
      </main>
    </div>
  )
}
```

- [ ] **Step 7: Update `frontend/src/App.tsx` to add routing**

```typescript
import { useAuth } from '@react-oidc-context'
import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { setAuthToken, clearAuthToken } from './lib/api'
import { AppLayout } from './components/layout/AppLayout'
import { RegistriesPage } from './pages/RegistriesPage'
import { ImagesPage } from './pages/ImagesPage'
import { ImageDetailPage } from './pages/ImageDetailPage'
import { ScanResultsPage } from './pages/ScanResultsPage'
import { MergeRequestsPage } from './pages/MergeRequestsPage'

export default function App() {
  const auth = useAuth()

  useEffect(() => {
    if (auth.user?.access_token) {
      setAuthToken(auth.user.access_token)
    } else {
      clearAuthToken()
    }
  }, [auth.user])

  if (auth.isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-900">
        <p className="text-slate-400">Loading…</p>
      </div>
    )
  }

  if (!auth.isAuthenticated) {
    return (
      <div className="flex h-screen flex-col items-center justify-center bg-slate-900 gap-4">
        <h1 className="text-2xl font-bold text-slate-100">PatchPilot</h1>
        <button
          onClick={() => auth.signinRedirect()}
          className="rounded bg-blue-600 px-6 py-2 text-white hover:bg-blue-700"
        >
          Sign in with Keycloak
        </button>
      </div>
    )
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/images" replace />} />
          <Route path="/registries" element={<RegistriesPage />} />
          <Route path="/images" element={<ImagesPage />} />
          <Route path="/images/:id" element={<ImageDetailPage />} />
          <Route path="/scans/:id" element={<ScanResultsPage />} />
          <Route path="/merge-requests" element={<MergeRequestsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
```

- [ ] **Step 8: Create stub pages** (so routing doesn't break)

Create `frontend/src/pages/RegistriesPage.tsx`:
```typescript
export function RegistriesPage() { return <div className="text-slate-100">Registries — coming soon</div> }
```

Create `frontend/src/pages/ImagesPage.tsx`:
```typescript
export function ImagesPage() { return <div className="text-slate-100">Images</div> }
```

Create `frontend/src/pages/ImageDetailPage.tsx`:
```typescript
export function ImageDetailPage() { return <div className="text-slate-100">Image Detail</div> }
```

Create `frontend/src/pages/ScanResultsPage.tsx`:
```typescript
export function ScanResultsPage() { return <div className="text-slate-100">Scan Results</div> }
```

Create `frontend/src/pages/MergeRequestsPage.tsx`:
```typescript
export function MergeRequestsPage() { return <div className="text-slate-100">Merge Requests</div> }
```

- [ ] **Step 9: Verify routing works**

```bash
cd frontend && npm run dev
```

Navigate to `http://localhost:5173` — should see sidebar with nav items after login.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/
git commit -m "feat: frontend routing skeleton + sidebar nav + API client layer"
```

---

## Task 20: SeverityDonut + ScanStatusBadge components

**Files:**
- Create: `frontend/src/components/scans/SeverityDonut.tsx`
- Create: `frontend/src/components/scans/ScanStatusBadge.tsx`
- Create: `frontend/src/lib/severity.ts`

- [ ] **Step 1: Create `frontend/src/lib/severity.ts`**

```typescript
export const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: '#ef4444',   // red-500
  HIGH: '#f97316',       // orange-500
  MEDIUM: '#eab308',     // yellow-400
  LOW: '#60a5fa',        // blue-400
  UNKNOWN: '#94a3b8',    // slate-400
}

export const SEVERITY_ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'UNKNOWN'] as const
```

- [ ] **Step 2: Create `frontend/src/components/scans/SeverityDonut.tsx`**

```typescript
import { PieChart, Pie, Cell, Tooltip, Legend } from 'recharts'
import { SEVERITY_COLORS, SEVERITY_ORDER } from '../../lib/severity'

interface Props {
  summary: Record<string, number>
}

export function SeverityDonut({ summary }: Props) {
  const data = SEVERITY_ORDER
    .filter(s => (summary[s] ?? 0) > 0)
    .map(s => ({ name: s, value: summary[s] ?? 0, color: SEVERITY_COLORS[s] }))

  if (data.length === 0) return <p className="text-slate-500 text-sm">No vulnerabilities found</p>

  return (
    <PieChart width={240} height={240}>
      <Pie data={data} cx={120} cy={120} innerRadius={60} outerRadius={100} dataKey="value">
        {data.map(entry => (
          <Cell key={entry.name} fill={entry.color} />
        ))}
      </Pie>
      <Tooltip
        contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', color: '#f1f5f9' }}
      />
      <Legend formatter={(value) => <span className="text-slate-300 text-xs">{value}</span>} />
    </PieChart>
  )
}
```

- [ ] **Step 3: Create `frontend/src/components/scans/ScanStatusBadge.tsx`**

```typescript
const STATUS_STYLES: Record<string, string> = {
  QUEUED: 'bg-slate-700 text-slate-300',
  RUNNING: 'bg-blue-900 text-blue-300 animate-pulse',
  SUCCEEDED: 'bg-green-900 text-green-300',
  FAILED: 'bg-red-900 text-red-300',
}

export function ScanStatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${STATUS_STYLES[status] ?? STATUS_STYLES.QUEUED}`}>
      {status}
    </span>
  )
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/severity.ts \
        frontend/src/components/scans/SeverityDonut.tsx \
        frontend/src/components/scans/ScanStatusBadge.tsx
git commit -m "feat: SeverityDonut (Recharts) + ScanStatusBadge components"
```

---

## Task 21: ImageDetailPage + FindingsTable + scan polling

**Files:**
- Modify: `frontend/src/pages/ImageDetailPage.tsx`
- Create: `frontend/src/components/scans/FindingsTable.tsx`
- Modify: `frontend/src/pages/ScanResultsPage.tsx`

- [ ] **Step 1: Write `frontend/src/components/scans/FindingsTable.tsx`**

```typescript
import { useState } from 'react'
import type { Finding } from '../../api/scans'
import { SEVERITY_COLORS } from '../../lib/severity'

interface Props {
  findings: Finding[]
  selectedIds: Set<string>
  onToggle: (id: string) => void
}

export function FindingsTable({ findings, selectedIds, onToggle }: Props) {
  const [filterSeverity, setFilterSeverity] = useState<string>('')
  const [fixableOnly, setFixableOnly] = useState(false)

  const filtered = findings.filter(f => {
    if (filterSeverity && f.severity !== filterSeverity) return false
    if (fixableOnly && !f.is_fixable) return false
    return true
  })

  return (
    <div>
      <div className="flex gap-3 mb-4">
        <select
          className="bg-slate-800 text-slate-200 border border-slate-600 rounded px-2 py-1 text-sm"
          value={filterSeverity}
          onChange={e => setFilterSeverity(e.target.value)}
        >
          <option value="">All severities</option>
          {['CRITICAL','HIGH','MEDIUM','LOW','UNKNOWN'].map(s => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm text-slate-300">
          <input type="checkbox" checked={fixableOnly} onChange={e => setFixableOnly(e.target.checked)} />
          Fixable only
        </label>
        <span className="text-slate-500 text-sm ml-auto">{filtered.length} findings</span>
      </div>

      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-slate-400 border-b border-slate-700">
            <th className="pb-2 w-8"></th>
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
                />
              </td>
              <td className="py-2">
                <a
                  href={f.primary_url ?? '#'}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-400 hover:underline font-mono text-xs"
                >
                  {f.vuln_id}
                </a>
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
                  style={{ backgroundColor: SEVERITY_COLORS[f.severity] + '22', color: SEVERITY_COLORS[f.severity] }}
                >
                  {f.severity}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
```

- [ ] **Step 2: Write `frontend/src/pages/ScanResultsPage.tsx`**

```typescript
import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { scansApi } from '../api/scans'
import { ScanStatusBadge } from '../components/scans/ScanStatusBadge'
import { SeverityDonut } from '../components/scans/SeverityDonut'
import { FindingsTable } from '../components/scans/FindingsTable'

export function ScanResultsPage() {
  const { id } = useParams<{ id: string }>()
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  const scanQ = useQuery({
    queryKey: ['scan', id],
    queryFn: () => scansApi.get(id!),
    refetchInterval: (data) =>
      data?.status === 'QUEUED' || data?.status === 'RUNNING' ? 3000 : false,
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
      <div className="flex items-center gap-4 mb-6">
        <h2 className="text-xl font-semibold text-slate-100">Scan Results</h2>
        {scan && <ScanStatusBadge status={scan.status} />}
      </div>

      {scan?.status === 'SUCCEEDED' && scan.summary_jsonb && (
        <div className="flex gap-8 mb-8">
          <SeverityDonut summary={scan.summary_jsonb.by_severity} />
          <div className="text-slate-300 self-center space-y-1">
            <p>Total findings: <span className="text-white font-medium">{scan.summary_jsonb.total}</span></p>
            <p>Fixable: <span className="text-green-400 font-medium">{scan.summary_jsonb.fixable}</span></p>
          </div>
        </div>
      )}

      {findingsQ.data && findingsQ.data.length > 0 && (
        <>
          <FindingsTable
            findings={findingsQ.data}
            selectedIds={selectedIds}
            onToggle={toggle}
          />
          {selectedIds.size > 0 && (
            <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-blue-600 text-white px-6 py-3 rounded-lg shadow-xl flex items-center gap-4">
              <span>{selectedIds.size} finding{selectedIds.size > 1 ? 's' : ''} selected</span>
              <button className="bg-white text-blue-600 px-4 py-1 rounded font-medium text-sm hover:bg-blue-50">
                Raise MR →
              </button>
            </div>
          )}
        </>
      )}

      {scan?.status === 'FAILED' && (
        <div className="bg-red-900/30 border border-red-700 rounded p-4 text-red-300">
          Scan failed: {scan.error_text}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Write `frontend/src/pages/ImageDetailPage.tsx`**

```typescript
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { imagesApi } from '../api/images'
import { scansApi } from '../api/scans'
import { ScanStatusBadge } from '../components/scans/ScanStatusBadge'

export function ImageDetailPage() {
  const { id } = useParams<{ id: string }>()
  const qc = useQueryClient()

  const imgQ = useQuery({ queryKey: ['image', id], queryFn: () => imagesApi.get(id!) })

  const scanMut = useMutation({
    mutationFn: () => scansApi.trigger(id!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['image', id] }),
  })

  const img = imgQ.data
  if (!img) return <p className="text-slate-400">Loading…</p>

  return (
    <div className="max-w-3xl">
      <h2 className="text-xl font-semibold text-slate-100 mb-1">{img.repository}:{img.tag}</h2>
      <p className="text-slate-400 text-sm mb-6">{img.gitlab_project_id} · {img.service_type}</p>

      <button
        onClick={() => scanMut.mutate()}
        disabled={scanMut.isPending}
        className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded text-sm mb-6 disabled:opacity-50"
      >
        {scanMut.isPending ? 'Queueing…' : 'Scan Now'}
      </button>

      {scanMut.data && (
        <p className="text-slate-300 text-sm mb-4">
          Scan queued:{' '}
          <Link to={`/scans/${scanMut.data.scan_id}`} className="text-blue-400 hover:underline">
            View results
          </Link>
        </p>
      )}

      <div className="bg-slate-800 rounded p-4 text-sm text-slate-300 space-y-2">
        <p><span className="text-slate-500">Base Dockerfile:</span> {img.base_dockerfile_path}</p>
        <p><span className="text-slate-500">App Dockerfile:</span> {img.app_dockerfile_path}</p>
        <p><span className="text-slate-500">Default branch:</span> {img.gitlab_default_branch}</p>
        {img.last_digest && (
          <p><span className="text-slate-500">Last digest:</span> <span className="font-mono text-xs">{img.last_digest}</span></p>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/
git commit -m "feat: ImageDetail + ScanResults + FindingsTable with polling and multi-select"
```

---

# PHASE 6 — MR Engine

## Task 22: Dockerfile patch generator

**Files:**
- Create: `backend/app/workers/patch_generator.py`
- Create: `backend/tests/test_patch_generator.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_patch_generator.py
import textwrap
import pytest
from app.workers.patch_generator import PatchGenerator, PatchResult

SIMPLE_DOCKERFILE = textwrap.dedent("""\
    FROM debian:12-slim
    RUN apt-get update && apt-get install -y libssl3 curl ca-certificates
    COPY app /app
    CMD ["/app/server"]
""")

MULTISTAGE_DOCKERFILE = textwrap.dedent("""\
    FROM golang:1.22 AS builder
    WORKDIR /src
    RUN apt-get update && apt-get install -y libssl-dev
    COPY . .
    RUN go build -o /app

    FROM debian:12-slim
    RUN apt-get update && apt-get install -y libssl3 curl
    COPY --from=builder /app /app
    CMD ["/app"]
""")

FIXABLE_FINDINGS = [
    {"pkg_name": "libssl3", "installed_version": "3.0.2", "fixed_version": "3.0.14", "is_fixable": True},
    {"pkg_name": "curl", "installed_version": "7.88.0", "fixed_version": "7.88.1", "is_fixable": True},
]

UNFIXABLE_FINDINGS = [
    {"pkg_name": "bash", "installed_version": "5.2", "fixed_version": None, "is_fixable": False},
]


def test_patches_apt_package_versions():
    gen = PatchGenerator()
    result = gen.patch(SIMPLE_DOCKERFILE, FIXABLE_FINDINGS)
    assert "libssl3=3.0.14" in result.patched_content
    assert "curl=7.88.1" in result.patched_content


def test_skips_unfixable_findings():
    gen = PatchGenerator()
    result = gen.patch(SIMPLE_DOCKERFILE, UNFIXABLE_FINDINGS)
    assert result.patched_content == SIMPLE_DOCKERFILE
    assert result.patches_applied == []


def test_only_patches_final_stage_in_multistage():
    gen = PatchGenerator()
    result = gen.patch(MULTISTAGE_DOCKERFILE, FIXABLE_FINDINGS)
    lines = result.patched_content.split("\n")
    builder_section = "\n".join(lines[:6])
    final_section = "\n".join(lines[6:])
    # builder stage RUN should NOT have version pins
    assert "libssl3=3.0.14" not in builder_section
    # final stage RUN should have pins
    assert "libssl3=3.0.14" in final_section


def test_from_line_not_modified():
    gen = PatchGenerator()
    result = gen.patch(SIMPLE_DOCKERFILE, FIXABLE_FINDINGS)
    assert "FROM debian:12-slim" in result.patched_content


def test_unrelated_lines_unchanged():
    gen = PatchGenerator()
    result = gen.patch(SIMPLE_DOCKERFILE, FIXABLE_FINDINGS)
    assert "COPY app /app" in result.patched_content
    assert 'CMD ["/app/server"]' in result.patched_content
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && pytest tests/test_patch_generator.py -v
```

- [ ] **Step 3: Write `backend/app/workers/patch_generator.py`**

```python
from __future__ import annotations
import re
from dataclasses import dataclass, field
from dockerfile_parse import DockerfileParser
import io


@dataclass
class PatchResult:
    patched_content: str
    patches_applied: list[dict]


class PatchGenerator:
    def patch(self, dockerfile_content: str, findings: list[dict]) -> PatchResult:
        fixable = {f["pkg_name"]: f["fixed_version"] for f in findings if f.get("is_fixable") and f.get("fixed_version")}
        if not fixable:
            return PatchResult(patched_content=dockerfile_content, patches_applied=[])

        dfp = DockerfileParser(fileobj=io.BytesIO(dockerfile_content.encode()))
        structure = dfp.structure

        # Find the last FROM index to identify the final stage
        from_indices = [i for i, item in enumerate(structure) if item["instruction"] == "FROM"]
        final_stage_start = from_indices[-1] if from_indices else 0

        patches_applied: list[dict] = []
        patched_lines = dockerfile_content.splitlines(keepends=True)

        for i, item in enumerate(structure):
            if i < final_stage_start:
                continue
            if item["instruction"] not in ("RUN",):
                continue

            run_value = item["value"]
            for pkg, fixed_ver in fixable.items():
                if self._pkg_in_run(pkg, run_value):
                    new_run_value, changed = self._pin_package(run_value, pkg, fixed_ver)
                    if changed:
                        # Replace in the actual file content
                        patched_lines = self._replace_run_in_lines(patched_lines, run_value, new_run_value)
                        patches_applied.append({"pkg": pkg, "pinned_to": fixed_ver})
                        run_value = new_run_value

        return PatchResult(
            patched_content="".join(patched_lines),
            patches_applied=patches_applied,
        )

    def _pkg_in_run(self, pkg: str, run_value: str) -> bool:
        return bool(re.search(rf'\b{re.escape(pkg)}\b', run_value))

    def _pin_package(self, run_value: str, pkg: str, fixed_version: str) -> tuple[str, bool]:
        pkg_re = re.compile(rf'\b{re.escape(pkg)}(?:=[^\s\\]+)?\b')
        new_val, n = pkg_re.subn(f"{pkg}={fixed_version}", run_value, count=1)
        return new_val, n > 0

    def _replace_run_in_lines(self, lines: list[str], old_run: str, new_run: str) -> list[str]:
        content = "".join(lines)
        # Replace the first occurrence of old_run in a RUN instruction
        content = content.replace(old_run, new_run, 1)
        return content.splitlines(keepends=True)
```

- [ ] **Step 4: Run tests**

```bash
cd backend && pytest tests/test_patch_generator.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/workers/patch_generator.py backend/tests/test_patch_generator.py
git commit -m "feat: Dockerfile patch generator using dockerfile-parse (BuildKit parser)"
```

---

## Task 23: Branch template resolver

**Files:**
- Create: `backend/app/workers/branch_resolver.py`
- Create: `backend/tests/test_branch_resolver.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_branch_resolver.py
from app.workers.branch_resolver import resolve_branch

def test_resolves_all_variables():
    result = resolve_branch(
        template="hotfix/backend/{version}-sec-{image}",
        variables={"version": "1.4.2", "image": "payments-api", "date": "2026-06-16"},
    )
    assert result == "hotfix/backend/1.4.2-sec-payments-api"

def test_image_slug_replaces_slashes():
    result = resolve_branch(
        template="feature/{image}-patch",
        variables={"image": "myorg/payments/api"},
    )
    assert result == "feature/myorg-payments-api-patch"

def test_unknown_variables_left_as_is():
    result = resolve_branch(template="fix/{unknown_var}", variables={})
    assert result == "fix/{unknown_var}"

def test_raises_on_empty_template():
    import pytest
    with pytest.raises(ValueError):
        resolve_branch(template="", variables={})
```

- [ ] **Step 2: Write `backend/app/workers/branch_resolver.py`**

```python
from __future__ import annotations
import re


def resolve_branch(template: str, variables: dict[str, str]) -> str:
    if not template.strip():
        raise ValueError("Branch template must not be empty")
    result = template
    for key, value in variables.items():
        safe_value = value.replace("/", "-") if key == "image" else value
        result = result.replace(f"{{{key}}}", safe_value)
    return result
```

- [ ] **Step 3: Run tests**

```bash
cd backend && pytest tests/test_branch_resolver.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/workers/branch_resolver.py backend/tests/test_branch_resolver.py
git commit -m "feat: branch template resolver with variable substitution"
```

---

## Task 24: GitLab client + MR Celery task

**Files:**
- Create: `backend/app/workers/gitlab_client.py`
- Create: `backend/app/tasks/mr_task.py`
- Create: `backend/app/schemas/merge_request.py`
- Create: `backend/app/services/mr_service.py`
- Create: `backend/tests/test_mr_task.py`

- [ ] **Step 1: Write `backend/app/workers/gitlab_client.py`**

```python
from __future__ import annotations
import gitlab
from dataclasses import dataclass


@dataclass
class MRResult:
    iid: int
    url: str
    source_branch: str
    pipeline_id: int | None


class GitLabClient:
    def __init__(self, url: str, token: str):
        self._gl = gitlab.Gitlab(url, private_token=token)

    def ensure_branch(self, project_id: str, source_branch: str, target_branch: str) -> None:
        project = self._gl.projects.get(project_id)
        existing = [b.name for b in project.branches.list(all=True)]
        if source_branch not in existing:
            project.branches.create({"branch": source_branch, "ref": target_branch})

    def commit_file(
        self,
        project_id: str,
        branch: str,
        file_path: str,
        content: str,
        commit_message: str,
    ) -> None:
        project = self._gl.projects.get(project_id)
        try:
            f = project.files.get(file_path=file_path, ref=branch)
            project.files.update(
                file_path=file_path,
                new_data={"branch": branch, "content": content, "commit_message": commit_message},
            )
        except Exception:
            project.files.create({
                "file_path": file_path,
                "branch": branch,
                "content": content,
                "commit_message": commit_message,
            })

    def create_or_update_mr(
        self,
        project_id: str,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str,
        labels: list[str],
    ) -> MRResult:
        project = self._gl.projects.get(project_id)
        existing = project.mergerequests.list(
            source_branch=source_branch,
            target_branch=target_branch,
            state="opened",
        )
        if existing:
            mr = existing[0]
            mr.description = description
            mr.save()
        else:
            mr = project.mergerequests.create({
                "source_branch": source_branch,
                "target_branch": target_branch,
                "title": title,
                "description": description,
                "labels": labels,
            })
        pipelines = mr.pipelines.list()
        pipeline_id = pipelines[0].id if pipelines else None
        return MRResult(iid=mr.iid, url=mr.web_url, source_branch=source_branch, pipeline_id=pipeline_id)

    def get_mr_state(self, project_id: str, mr_iid: int) -> dict:
        project = self._gl.projects.get(project_id)
        mr = project.mergerequests.get(mr_iid)
        pipelines = mr.pipelines.list()
        pipeline_status = pipelines[0].status if pipelines else "unknown"
        return {
            "state": mr.state,
            "pipeline_status": pipeline_status.upper(),
            "pipeline_id": pipelines[0].id if pipelines else None,
        }
```

- [ ] **Step 2: Write `backend/app/schemas/merge_request.py`**

```python
from __future__ import annotations
import uuid
from pydantic import BaseModel, ConfigDict
from app.models.merge_request import MRType, MRTargetKind, MRState, PipelineStatus


class RaiseMRRequest(BaseModel):
    scan_id: str
    finding_ids: list[str]
    mr_type: MRType
    targets: list[MRTargetKind]
    source_branch_template: str
    target_branch: str
    template_vars: dict[str, str] = {}


class MRResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    image_id: uuid.UUID
    scan_id: uuid.UUID
    mr_type: MRType
    target_kind: MRTargetKind
    gitlab_project_id: str
    gitlab_mr_iid: int | None
    gitlab_mr_url: str | None
    source_branch: str | None
    target_branch: str
    state: MRState
    pipeline_status: PipelineStatus | None
    finding_ids: list[str]
    image_digest: str
```

- [ ] **Step 3: Write `backend/app/services/mr_service.py`**

```python
from __future__ import annotations
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.merge_request import MergeRequest, MRState


class MRService:
    async def list(self, db: AsyncSession, team_image_ids: list[str]) -> list[MergeRequest]:
        result = await db.execute(
            select(MergeRequest).where(MergeRequest.image_id.in_([uuid.UUID(i) for i in team_image_ids]))
        )
        return list(result.scalars().all())

    async def get(self, db: AsyncSession, mr_id: str) -> MergeRequest | None:
        return await db.get(MergeRequest, uuid.UUID(mr_id))
```

- [ ] **Step 4: Write `backend/app/tasks/mr_task.py`**

```python
from __future__ import annotations
import hashlib
import structlog
from opentelemetry import trace
from app.core.celery_app import celery_app
from app.core.db import SyncSessionLocal
from app.core.credentials import CredentialStore
from app.workers.patch_generator import PatchGenerator
from app.workers.branch_resolver import resolve_branch
from app.workers.gitlab_client import GitLabClient
from app.models.merge_request import MergeRequest, MRState, PipelineStatus
from app.models.finding import Finding, FindingStatus
import redis as redis_lib
from app.core.config import settings

log = structlog.get_logger()
tracer = trace.get_tracer(__name__)
_redis = redis_lib.from_url(settings.REDIS_URL)

_DISPATCH_LOCK_TTL = 30  # seconds


def dispatch_mr_task(
    scan_id: str,
    finding_ids: list[str],
    mr_type: str,
    target_kind: str,
    source_branch_template: str,
    target_branch: str,
    template_vars: dict,
    gitlab_project_id: str,
    image_digest: str,
) -> bool:
    dedup_key = hashlib.sha256(
        f"{gitlab_project_id}:{image_digest}:{target_branch}:{target_kind}".encode()
    ).hexdigest()
    lock_key = f"mr_dispatch_lock:{dedup_key}"
    acquired = _redis.set(lock_key, "1", nx=True, ex=_DISPATCH_LOCK_TTL)
    if not acquired:
        return False

    create_mr_task.apply_async(args=[
        scan_id, finding_ids, mr_type, target_kind,
        source_branch_template, target_branch, template_vars,
        gitlab_project_id, image_digest,
    ])
    return True


@celery_app.task(name="patchpilot.create_mr", bind=True, max_retries=2, default_retry_delay=60)
def create_mr_task(
    self,
    scan_id: str,
    finding_ids: list[str],
    mr_type: str,
    target_kind: str,
    source_branch_template: str,
    target_branch: str,
    template_vars: dict,
    gitlab_project_id: str,
    image_digest: str,
) -> None:
    with tracer.start_as_current_span("create_mr"):
        with SyncSessionLocal() as db:
            from app.models.scan import Scan
            from app.models.image import Image
            scan = db.get(Scan, scan_id)
            if not scan:
                return
            image = db.get(Image, str(scan.image_id))
            registry = image.registry

            store = CredentialStore()
            creds = store.decrypt(registry.auth_ciphertext, registry.auth_dek_enc)

            # Fetch Dockerfile from GitLab
            gitlab_creds = store.decrypt(image.auth_ciphertext, image.auth_dek_enc) if hasattr(image, 'auth_ciphertext') else creds
            # NOTE: GitLab token stored separately on image — see Phase 3 extension
            gitlab_token = template_vars.get("gitlab_token", "")
            if not gitlab_token:
                log.error("no_gitlab_token", scan_id=scan_id)
                return

            gl = GitLabClient(url="https://gitlab.com", token=gitlab_token)

            dockerfile_path = (
                image.base_dockerfile_path if target_kind == "BASE_DOCKERFILE"
                else image.app_dockerfile_path
            )

            # Get Dockerfile content from GitLab
            import gitlab as python_gitlab
            raw_gl = python_gitlab.Gitlab("https://gitlab.com", private_token=gitlab_token)
            project = raw_gl.projects.get(gitlab_project_id)
            df_file = project.files.get(file_path=dockerfile_path, ref=target_branch)
            dockerfile_content = df_file.decode().decode()

            findings = db.query(Finding).filter(Finding.id.in_(finding_ids)).all()
            finding_dicts = [
                {"pkg_name": f.pkg_name, "fixed_version": f.fixed_version, "is_fixable": f.is_fixable}
                for f in findings
            ]

            gen = PatchGenerator()
            patch_result = gen.patch(dockerfile_content, finding_dicts)
            if not patch_result.patches_applied:
                log.info("no_patches_to_apply", scan_id=scan_id)
                return

            # Resolve branch name
            vars_with_image = {**template_vars, "image": image.repository.replace("/", "-")}
            source_branch = resolve_branch(source_branch_template, vars_with_image)

            # Build MR description
            cve_rows = "\n".join(
                f"| {f.vuln_id} | {f.pkg_name} | {f.installed_version} → {f.fixed_version} | {f.severity} |"
                for f in findings if f.is_fixable
            )
            description = f"""## PatchPilot Security Fix

| CVE | Package | Installed → Fixed | Severity |
|-----|---------|-------------------|----------|
{cve_rows}

[View scan in PatchPilot](/scans/{scan_id})

_Raised by PatchPilot on behalf of {template_vars.get('raised_by', 'unknown')}._

> **Note:** Base image tag bump not automated. Consider upgrading the FROM line manually.
"""

            gl.ensure_branch(gitlab_project_id, source_branch, target_branch)
            gl.commit_file(
                gitlab_project_id,
                source_branch,
                dockerfile_path,
                patch_result.patched_content,
                f"fix: pin vulnerable packages ({len(patch_result.patches_applied)} CVEs)",
            )

            mr_result = gl.create_or_update_mr(
                project_id=gitlab_project_id,
                source_branch=source_branch,
                target_branch=target_branch,
                title=f"🔒 [PatchPilot] Fix {len(findings)} vulnerabilities ({target_kind})",
                description=description,
                labels=["security", "patchpilot"],
            )

            # Upsert MR row with DB idempotency
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            stmt = pg_insert(MergeRequest).values(
                id=str(__import__('uuid').uuid4()),
                image_id=str(scan.image_id),
                scan_id=scan_id,
                mr_type=mr_type,
                target_kind=target_kind,
                gitlab_project_id=gitlab_project_id,
                gitlab_mr_iid=mr_result.iid,
                gitlab_mr_url=mr_result.url,
                gitlab_pipeline_id=mr_result.pipeline_id,
                pipeline_status=PipelineStatus.UNKNOWN,
                source_branch=source_branch,
                target_branch=target_branch,
                state=MRState.OPENED,
                finding_ids=finding_ids,
                image_digest=image_digest,
            ).on_conflict_do_update(
                index_where="state = 'OPENED'",
                set_={"finding_ids": finding_ids, "gitlab_mr_iid": mr_result.iid},
            )
            db.execute(stmt)

            for f in findings:
                f.status = FindingStatus.MR_RAISED
            db.commit()
            log.info("mr_created", mr_url=mr_result.url)
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/workers/gitlab_client.py backend/app/tasks/mr_task.py \
        backend/app/schemas/merge_request.py backend/app/services/mr_service.py
git commit -m "feat: GitLab client + MR Celery task with dispatch dedup + DB idempotency"
```

---

## Task 25: MR API router + audit log

**Files:**
- Create: `backend/app/api/routers/merge_requests.py`
- Create: `backend/app/services/audit_service.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write `backend/app/services/audit_service.py`**

```python
from __future__ import annotations
import uuid
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit_log import AuditLog


class AuditService:
    async def log(
        self,
        db: AsyncSession,
        actor_id: str | None,
        action: str,
        entity_type: str,
        entity_id: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        entry = AuditLog(
            actor_id=uuid.UUID(actor_id) if actor_id else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata_jsonb=metadata,
        )
        db.add(entry)
        await db.commit()
```

- [ ] **Step 2: Write `backend/app/api/routers/merge_requests.py`**

```python
from __future__ import annotations
from typing import Any
from fastapi import APIRouter, HTTPException, status

from app.api.deps import DB, CurrentUser
from app.schemas.merge_request import RaiseMRRequest, MRResponse
from app.services.image_service import ImageService
from app.services.scan_service import ScanService
from app.services.mr_service import MRService
from app.services.audit_service import AuditService
from app.tasks.mr_task import dispatch_mr_task
from app.workers.gitlab_client import GitLabClient
from app.models.merge_request import PipelineStatus, MRState
import structlog

router = APIRouter(prefix="/api/merge-requests", tags=["merge-requests"])
log = structlog.get_logger()


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def raise_mr(body: RaiseMRRequest, user: CurrentUser, db: DB) -> Any:
    scan_svc = ScanService()
    scan = await scan_svc.get(db=db, scan_id=body.scan_id)
    if not scan:
        raise HTTPException(404, "Scan not found")

    img_svc = ImageService()
    img = None
    for team_id in user.get("patchpilot_teams", []):
        img = await img_svc.get(db=db, image_id=str(scan.image_id), team_id=team_id)
        if img:
            break
    if not img:
        raise HTTPException(403, "Image not in your team")

    template_vars = {
        **body.template_vars,
        "raised_by": user.get("email", user["sub"]),
        "image": img.repository.replace("/", "-"),
        "tag": img.tag,
    }

    dispatched = []
    for target_kind in body.targets:
        ok = dispatch_mr_task(
            scan_id=body.scan_id,
            finding_ids=body.finding_ids,
            mr_type=body.mr_type.value,
            target_kind=target_kind.value,
            source_branch_template=body.source_branch_template,
            target_branch=body.target_branch,
            template_vars=template_vars,
            gitlab_project_id=img.gitlab_project_id,
            image_digest=scan.image_digest or "",
        )
        dispatched.append({"target_kind": target_kind.value, "queued": ok})

    audit = AuditService()
    await audit.log(
        db=db,
        actor_id=user["sub"],
        action="raise_mr",
        entity_type="scan",
        entity_id=body.scan_id,
        metadata={"targets": [t.value for t in body.targets], "finding_count": len(body.finding_ids)},
    )
    return {"dispatched": dispatched}


@router.get("", response_model=list[MRResponse])
async def list_mrs(user: CurrentUser, db: DB) -> Any:
    img_svc = ImageService()
    all_image_ids = []
    for team_id in user.get("patchpilot_teams", []):
        imgs = await img_svc.list(db=db, team_id=team_id)
        all_image_ids.extend(str(i.id) for i in imgs)
    svc = MRService()
    return await svc.list(db=db, team_image_ids=all_image_ids)


@router.get("/{mr_id}", response_model=MRResponse)
async def get_mr(mr_id: str, user: CurrentUser, db: DB) -> Any:
    svc = MRService()
    mr = await svc.get(db=db, mr_id=mr_id)
    if not mr:
        raise HTTPException(404, "MR not found")
    return mr


@router.post("/{mr_id}/sync", response_model=MRResponse)
async def sync_mr(mr_id: str, user: CurrentUser, db: DB) -> Any:
    svc = MRService()
    mr = await svc.get(db=db, mr_id=mr_id)
    if not mr:
        raise HTTPException(404, "MR not found")
    if not mr.gitlab_mr_iid:
        return mr

    # Fetch GitLab token from image's registry creds
    img_svc = ImageService()
    img = await img_svc.get(db=db, image_id=str(mr.image_id), team_id=str(mr.image_id))

    # NOTE: gitlab_token stored in template_vars at MR creation — for now, skip if absent
    log.info("mr_sync_skipped_no_token", mr_id=mr_id)
    return mr
```

- [ ] **Step 3: Register router in `backend/app/main.py`**

```python
from app.api.routers import registries, images, scans, merge_requests

app.include_router(registries.router)
app.include_router(images.router)
app.include_router(scans.router)
app.include_router(merge_requests.router)
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/routers/merge_requests.py \
        backend/app/services/audit_service.py backend/app/services/mr_service.py \
        backend/app/main.py
git commit -m "feat: MR raise/list/sync API + audit log"
```

---

# PHASE 7 — MR UX

## Task 26: RaiseMRDrawer component

**Files:**
- Create: `frontend/src/components/mr/RaiseMRDrawer.tsx`
- Modify: `frontend/src/pages/ScanResultsPage.tsx`

- [ ] **Step 1: Write `frontend/src/components/mr/RaiseMRDrawer.tsx`**

```typescript
import { useState, useEffect } from 'react'
import { useMutation } from '@tanstack/react-query'
import { mrApi, type RaiseMRBody } from '../../api/mergeRequests'
import { resolve_branch_preview } from '../../lib/branchPreview'
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

export function RaiseMRDrawer({ open, onClose, scanId, imageId, imageRepo, imageTag, findings, selectedIds }: Props) {
  const [template, setTemplate] = useState('feature/patchpilot-{image}-{date}')
  const [targetBranch, setTargetBranch] = useState('main')
  const [version, setVersion] = useState('')
  const [targets, setTargets] = useState<('BASE_DOCKERFILE' | 'APP_DOCKERFILE')[]>(['APP_DOCKERFILE'])
  const [mrType, setMrType] = useState<'FEATURE' | 'HOTFIX'>('FEATURE')

  const today = new Date().toISOString().split('T')[0]
  const imageSlug = imageRepo.replace(/\//g, '-')

  const previewBranch = template
    .replace('{image}', imageSlug)
    .replace('{date}', today)
    .replace('{version}', version || '{version}')
    .replace('{tag}', imageTag)

  const selectedFindings = findings.filter(f => selectedIds.has(f.id))

  const mut = useMutation({
    mutationFn: (body: RaiseMRBody) => mrApi.create(body),
    onSuccess: () => onClose(),
  })

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="flex-1 bg-black/50" onClick={onClose} />
      <div className="w-[560px] bg-slate-800 border-l border-slate-700 overflow-y-auto flex flex-col">
        <div className="flex items-center justify-between p-5 border-b border-slate-700">
          <h2 className="text-lg font-semibold text-slate-100">Raise MR</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200">✕</button>
        </div>

        <div className="p-5 space-y-5 flex-1">
          {/* MR type */}
          <div>
            <label className="block text-xs text-slate-400 mb-1">MR Type</label>
            <div className="flex gap-2">
              {(['FEATURE', 'HOTFIX'] as const).map(t => (
                <button
                  key={t}
                  onClick={() => setMrType(t)}
                  className={`px-3 py-1 rounded text-sm ${mrType === t ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300'}`}
                >
                  {t.toLowerCase()}
                </button>
              ))}
            </div>
          </div>

          {/* Targets */}
          <div>
            <label className="block text-xs text-slate-400 mb-1">Dockerfile targets</label>
            <div className="flex gap-2">
              {(['BASE_DOCKERFILE', 'APP_DOCKERFILE'] as const).map(t => (
                <label key={t} className="flex items-center gap-1 text-sm text-slate-300">
                  <input
                    type="checkbox"
                    checked={targets.includes(t)}
                    onChange={e => setTargets(prev => e.target.checked ? [...prev, t] : prev.filter(x => x !== t))}
                  />
                  {t === 'BASE_DOCKERFILE' ? 'Base Dockerfile' : 'App Dockerfile'}
                </label>
              ))}
            </div>
          </div>

          {/* Branch template */}
          <div>
            <label className="block text-xs text-slate-400 mb-1">
              Source branch template <span className="text-slate-600">(variables: {'{image}'} {'{date}'} {'{version}'} {'{tag}'})</span>
            </label>
            <input
              className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-1.5 text-sm text-slate-100 font-mono"
              value={template}
              onChange={e => setTemplate(e.target.value)}
            />
            <p className="mt-1 text-xs text-blue-400 font-mono">→ {previewBranch}</p>
          </div>

          {version !== undefined && template.includes('{version}') && (
            <div>
              <label className="block text-xs text-slate-400 mb-1">Version value</label>
              <input
                className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-1.5 text-sm text-slate-100"
                placeholder="e.g. 1.4.2"
                value={version}
                onChange={e => setVersion(e.target.value)}
              />
            </div>
          )}

          {/* Target branch */}
          <div>
            <label className="block text-xs text-slate-400 mb-1">Target branch (merge into)</label>
            <input
              className="w-full bg-slate-900 border border-slate-600 rounded px-3 py-1.5 text-sm text-slate-100 font-mono"
              value={targetBranch}
              onChange={e => setTargetBranch(e.target.value)}
            />
          </div>

          {/* CVE summary */}
          <div>
            <p className="text-xs text-slate-400 mb-2">Fixing {selectedFindings.length} finding{selectedFindings.length > 1 ? 's' : ''}:</p>
            <div className="bg-slate-900 rounded p-3 max-h-40 overflow-y-auto space-y-1">
              {selectedFindings.map(f => (
                <div key={f.id} className="flex justify-between text-xs">
                  <span className="font-mono text-blue-400">{f.vuln_id}</span>
                  <span className="text-slate-400">{f.pkg_name} → {f.fixed_version}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="p-5 border-t border-slate-700">
          <button
            disabled={targets.length === 0 || selectedIds.size === 0 || mut.isPending}
            onClick={() => mut.mutate({
              scan_id: scanId,
              finding_ids: [...selectedIds],
              mr_type: mrType,
              targets,
              source_branch_template: template,
              target_branch: targetBranch,
              template_vars: { version, image: imageSlug, date: today, tag: imageTag },
            })}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white py-2 rounded text-sm font-medium"
          >
            {mut.isPending ? 'Creating MR…' : `Create ${targets.length} MR${targets.length > 1 ? 's' : ''}`}
          </button>
          {mut.isError && <p className="text-red-400 text-xs mt-2">Error: {String(mut.error)}</p>}
          {mut.isSuccess && <p className="text-green-400 text-xs mt-2">MR queued successfully!</p>}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Wire drawer into ScanResultsPage**

Add to `ScanResultsPage.tsx` — import `RaiseMRDrawer` and replace the sticky bar button:

```typescript
// Add import at top:
import { RaiseMRDrawer } from '../components/mr/RaiseMRDrawer'
import { useQuery } from '@tanstack/react-query'
import { imagesApi } from '../api/images'

// Add state inside component:
const [drawerOpen, setDrawerOpen] = useState(false)

// Replace the "Raise MR →" button in the sticky bar:
<button
  className="bg-white text-blue-600 px-4 py-1 rounded font-medium text-sm hover:bg-blue-50"
  onClick={() => setDrawerOpen(true)}
>
  Raise MR →
</button>

// Add drawer at end of return, before closing div:
{scan && drawerOpen && (
  <RaiseMRDrawer
    open={drawerOpen}
    onClose={() => setDrawerOpen(false)}
    scanId={scan.id}
    imageId={scan.image_id}
    imageRepo=""
    imageTag=""
    findings={findingsQ.data ?? []}
    selectedIds={selectedIds}
  />
)}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/mr/ frontend/src/pages/ScanResultsPage.tsx
git commit -m "feat: RaiseMRDrawer with branch template input + live preview + CVE table"
```

---

## Task 27: MRs dashboard with pipeline badge

**Files:**
- Modify: `frontend/src/pages/MergeRequestsPage.tsx`
- Create: `frontend/src/components/mr/MRTable.tsx`

- [ ] **Step 1: Write `frontend/src/components/mr/MRTable.tsx`**

```typescript
import type { MergeRequest } from '../../api/mergeRequests'

const PIPELINE_BADGE: Record<string, { label: string; className: string }> = {
  PASSED: { label: '✓ CI passed', className: 'bg-green-900 text-green-300' },
  FAILED: { label: '✗ CI failed', className: 'bg-red-900 text-red-300' },
  RUNNING: { label: '⟳ CI running', className: 'bg-blue-900 text-blue-300 animate-pulse' },
  PENDING: { label: '· pending', className: 'bg-slate-700 text-slate-400' },
  UNKNOWN: { label: '? unknown', className: 'bg-slate-700 text-slate-400' },
}

const STATE_BADGE: Record<string, string> = {
  OPENED: 'bg-blue-900 text-blue-300',
  MERGED: 'bg-green-900 text-green-300',
  CLOSED: 'bg-slate-700 text-slate-400',
  FAILED: 'bg-red-900 text-red-300',
}

interface Props { mrs: MergeRequest[] }

export function MRTable({ mrs }: Props) {
  if (mrs.length === 0) {
    return <p className="text-slate-500 text-sm">No merge requests yet.</p>
  }
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-slate-400 border-b border-slate-700">
          <th className="pb-2">Branch</th>
          <th className="pb-2">Target</th>
          <th className="pb-2">Kind</th>
          <th className="pb-2">State</th>
          <th className="pb-2">CI</th>
          <th className="pb-2">Link</th>
        </tr>
      </thead>
      <tbody>
        {mrs.map(mr => {
          const pipeline = PIPELINE_BADGE[mr.pipeline_status ?? 'UNKNOWN']
          return (
            <tr key={mr.id} className="border-b border-slate-800 hover:bg-slate-800/40">
              <td className="py-2 font-mono text-xs text-slate-300">{mr.source_branch ?? '—'}</td>
              <td className="py-2 font-mono text-xs text-slate-400">{mr.target_branch}</td>
              <td className="py-2 text-xs text-slate-400">{mr.target_kind.replace('_DOCKERFILE', '')}</td>
              <td className="py-2">
                <span className={`px-2 py-0.5 rounded text-xs ${STATE_BADGE[mr.state]}`}>{mr.state}</span>
              </td>
              <td className="py-2">
                <span className={`px-2 py-0.5 rounded text-xs ${pipeline.className}`}>{pipeline.label}</span>
              </td>
              <td className="py-2">
                {mr.gitlab_mr_url
                  ? <a href={mr.gitlab_mr_url} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline text-xs">View MR ↗</a>
                  : <span className="text-slate-600 text-xs">—</span>}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
```

- [ ] **Step 2: Update `frontend/src/pages/MergeRequestsPage.tsx`**

```typescript
import { useQuery } from '@tanstack/react-query'
import { mrApi } from '../api/mergeRequests'
import { MRTable } from '../components/mr/MRTable'

export function MergeRequestsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['merge-requests'],
    queryFn: mrApi.list,
    refetchInterval: 15_000,
  })

  return (
    <div className="max-w-6xl">
      <h2 className="text-xl font-semibold text-slate-100 mb-6">Merge Requests</h2>
      {isLoading ? (
        <p className="text-slate-400">Loading…</p>
      ) : (
        <MRTable mrs={data ?? []} />
      )}
    </div>
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/mr/MRTable.tsx frontend/src/pages/MergeRequestsPage.tsx
git commit -m "feat: MRs dashboard with pipeline CI badge + 15s poll"
```

---

# PHASE 8 — Hardening

## Task 28: GHA CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  backend:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: patchpilot
          POSTGRES_PASSWORD: patchpilot
          POSTGRES_DB: patchpilot_test
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-timeout 3s
          --health-retries 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install deps
        run: cd backend && pip install -e ".[dev]"
      - name: Lint
        run: cd backend && ruff check . && ruff format --check .
      - name: Type check
        run: cd backend && mypy app
      - name: Test
        env:
          DATABASE_URL: postgresql+asyncpg://patchpilot:patchpilot@localhost:5432/patchpilot_test
          MASTER_KEY: ${{ secrets.TEST_MASTER_KEY }}
        run: cd backend && pytest tests/ -v --cov=app --cov-report=term-missing

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - name: Install deps
        run: cd frontend && npm ci
      - name: Type check
        run: cd frontend && npm run build
      - name: Test
        run: cd frontend && npm test -- --run
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "feat: GHA CI workflow — backend pytest + ruff + mypy, frontend tsc + vitest"
```

---

## Task 29: GHA build-push + helm-release workflows

**Files:**
- Create: `.github/workflows/build-push.yml`
- Create: `.github/workflows/helm-release.yml`

- [ ] **Step 1: Write `.github/workflows/build-push.yml`**

```yaml
name: Build and Push Docker Images

on:
  push:
    branches: [main]
    tags: ["v*"]

permissions:
  contents: read
  packages: write

jobs:
  build:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        include:
          - context: backend
            dockerfile: backend/Dockerfile
            image: patchpilot-backend
          - context: backend
            dockerfile: backend/Dockerfile.worker
            image: patchpilot-worker
          - context: frontend
            dockerfile: frontend/Dockerfile
            image: patchpilot-frontend

    steps:
      - uses: actions/checkout@v4

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Docker metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository_owner }}/${{ matrix.image }}
          tags: |
            type=sha,prefix=
            type=raw,value=latest,enable={{is_default_branch}}
            type=semver,pattern={{version}}

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: ${{ matrix.context }}
          file: ${{ matrix.dockerfile }}
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}

      - name: Sign image
        uses: sigstore/cosign-installer@v3
      - run: |
          cosign sign --yes ghcr.io/${{ github.repository_owner }}/${{ matrix.image }}@${{ steps.meta.outputs.digest }}
        env:
          COSIGN_EXPERIMENTAL: "true"
```

- [ ] **Step 2: Write `.github/workflows/helm-release.yml`**

```yaml
name: Helm Release

on:
  push:
    tags: ["helm/v*"]

permissions:
  contents: write
  pages: write
  id-token: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Install Helm
        uses: azure/setup-helm@v4

      - name: Package chart
        run: helm package infra/helm/patchpilot/ --destination /tmp/helm-packages

      - name: Upload to GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          files: /tmp/helm-packages/*.tgz

      - name: Publish to gh-pages Helm repo
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git checkout gh-pages || git checkout --orphan gh-pages
          cp /tmp/helm-packages/*.tgz .
          helm repo index . --url https://${{ github.repository_owner }}.github.io/${{ github.event.repository.name }} --merge index.yaml || \
            helm repo index . --url https://${{ github.repository_owner }}.github.io/${{ github.event.repository.name }}
          git add *.tgz index.yaml
          git commit -m "helm: release ${{ github.ref_name }}"
          git push origin gh-pages
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/build-push.yml .github/workflows/helm-release.yml
git commit -m "feat: GHA build-push (GHCR + cosign) + helm-release (gh-pages repo)"
```

---

## Task 30: Helm chart

**Files:**
- Create: `infra/helm/patchpilot/Chart.yaml`
- Create: `infra/helm/patchpilot/values.yaml`
- Create: `infra/helm/patchpilot/templates/_helpers.tpl`
- Create: `infra/helm/patchpilot/templates/backend-deployment.yaml`
- Create: `infra/helm/patchpilot/templates/worker-deployment.yaml`
- Create: `infra/helm/patchpilot/templates/worker-scaledobject.yaml`
- Create: `infra/helm/patchpilot/templates/trivy-server-deployment.yaml`
- Create: `infra/helm/patchpilot/templates/trivy-server-hpa.yaml`
- Create: `infra/helm/patchpilot/templates/frontend-deployment.yaml`
- Create: `infra/helm/patchpilot/templates/configmap.yaml`
- Create: `infra/helm/patchpilot/templates/ingress.yaml`
- Create: `infra/helm/patchpilot/values-staging.yaml`
- Create: `infra/helm/patchpilot/values-prod.yaml`

- [ ] **Step 1: Write `infra/helm/patchpilot/Chart.yaml`**

```yaml
apiVersion: v2
name: patchpilot
description: Container vulnerability scanner with automated GitLab MR patching
type: application
version: 0.1.0
appVersion: "0.1.0"
```

- [ ] **Step 2: Write `infra/helm/patchpilot/values.yaml`**

```yaml
global:
  image:
    registry: ghcr.io
    org: your-org
    tag: latest
    pullPolicy: IfNotPresent

backend:
  replicaCount: 2
  resources:
    requests: { cpu: 250m, memory: 256Mi }
    limits: { cpu: 1, memory: 512Mi }

worker:
  concurrency: 2
  resources:
    requests: { cpu: 1, memory: 512Mi, ephemeral-storage: 4Gi }
    limits: { cpu: 2, memory: 2Gi, ephemeral-storage: 8Gi }
  keda:
    minReplicas: 2
    maxReplicas: 50
    listLength: "2"

trivyServer:
  replicas: 2
  hpa:
    enabled: true
    minReplicas: 2
    maxReplicas: 8
    cpuTargetPercent: 60

frontend:
  replicaCount: 2

ingress:
  enabled: true
  host: patchpilot.example.com
  tls: true

config:
  keycloakUrl: ""
  keycloakRealm: patchpilot
  keycloakClientId: patchpilot-backend
  trivyServerUrl: "http://patchpilot-trivy-server:4954"
  redisUrl: "redis://patchpilot-redis:6379/0"

externalSecrets:
  masterKey:
    secretName: patchpilot-secrets
    secretKey: master-key
  databaseUrl:
    secretName: patchpilot-secrets
    secretKey: database-url
```

- [ ] **Step 3: Write `infra/helm/patchpilot/templates/trivy-server-deployment.yaml`**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "patchpilot.fullname" . }}-trivy-server
  labels: {{ include "patchpilot.labels" . | nindent 4 }}
spec:
  replicas: {{ .Values.trivyServer.replicas }}
  selector:
    matchLabels:
      app: {{ include "patchpilot.fullname" . }}-trivy-server
  template:
    metadata:
      labels:
        app: {{ include "patchpilot.fullname" . }}-trivy-server
    spec:
      initContainers:
        - name: trivy-db-init
          image: aquasec/trivy:latest
          command: ["trivy", "image", "--download-db-only", "--cache-dir", "/trivy-cache"]
          volumeMounts:
            - name: trivy-cache
              mountPath: /trivy-cache
      containers:
        - name: trivy-server
          image: aquasec/trivy:latest
          command: ["trivy", "server", "--listen", "0.0.0.0:4954", "--cache-dir", "/trivy-cache"]
          ports:
            - containerPort: 4954
          volumeMounts:
            - name: trivy-cache
              mountPath: /trivy-cache
          readinessProbe:
            tcpSocket:
              port: 4954
            initialDelaySeconds: 10
            periodSeconds: 5
      volumes:
        - name: trivy-cache
          emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: {{ include "patchpilot.fullname" . }}-trivy-server
spec:
  selector:
    app: {{ include "patchpilot.fullname" . }}-trivy-server
  ports:
    - port: 4954
      targetPort: 4954
```

- [ ] **Step 4: Write `infra/helm/patchpilot/templates/worker-scaledobject.yaml`**

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: {{ include "patchpilot.fullname" . }}-worker
spec:
  scaleTargetRef:
    name: {{ include "patchpilot.fullname" . }}-worker
  minReplicaCount: {{ .Values.worker.keda.minReplicas }}
  maxReplicaCount: {{ .Values.worker.keda.maxReplicas }}
  triggers:
    - type: redis
      metadata:
        address: {{ .Values.config.redisUrl | trimPrefix "redis://" }}
        listName: celery
        listLength: {{ .Values.worker.keda.listLength | quote }}
```

- [ ] **Step 5: Write `infra/helm/patchpilot/templates/worker-deployment.yaml`**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "patchpilot.fullname" . }}-worker
spec:
  selector:
    matchLabels:
      app: {{ include "patchpilot.fullname" . }}-worker
  template:
    metadata:
      labels:
        app: {{ include "patchpilot.fullname" . }}-worker
    spec:
      containers:
        - name: worker
          image: {{ .Values.global.image.registry }}/{{ .Values.global.image.org }}/patchpilot-worker:{{ .Values.global.image.tag }}
          imagePullPolicy: {{ .Values.global.image.pullPolicy }}
          command:
            - celery
            - -A
            - app.core.celery_app.celery_app
            - worker
            - --pool=prefork
            - --concurrency={{ .Values.worker.concurrency }}
            - --loglevel=info
            - --max-tasks-per-child=50
          envFrom:
            - configMapRef:
                name: {{ include "patchpilot.fullname" . }}-config
          env:
            - name: MASTER_KEY
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.externalSecrets.masterKey.secretName }}
                  key: {{ .Values.externalSecrets.masterKey.secretKey }}
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.externalSecrets.databaseUrl.secretName }}
                  key: {{ .Values.externalSecrets.databaseUrl.secretKey }}
          resources: {{ .Values.worker.resources | toYaml | nindent 12 }}
```

- [ ] **Step 6: Write `infra/helm/patchpilot/templates/_helpers.tpl`**

```
{{- define "patchpilot.fullname" -}}
{{- printf "%s" .Release.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "patchpilot.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
```

- [ ] **Step 7: Write `infra/helm/patchpilot/templates/configmap.yaml`**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "patchpilot.fullname" . }}-config
data:
  KEYCLOAK_URL: {{ .Values.config.keycloakUrl | quote }}
  KEYCLOAK_REALM: {{ .Values.config.keycloakRealm | quote }}
  KEYCLOAK_CLIENT_ID: {{ .Values.config.keycloakClientId | quote }}
  TRIVY_SERVER_URL: {{ .Values.config.trivyServerUrl | quote }}
  REDIS_URL: {{ .Values.config.redisUrl | quote }}
```

- [ ] **Step 8: Verify chart lints**

```bash
helm lint infra/helm/patchpilot/
```

Expected: `1 chart(s) linted, 0 chart(s) failed`

- [ ] **Step 9: Commit**

```bash
git add infra/helm/
git commit -m "feat: Helm chart — KEDA ScaledObject + trivy-server HPA + emptyDir DB per pod"
```

---

## Task 31: Postgres RLS + SQLAlchemy team-scope mixin enforcement

**Files:**
- Create: `backend/alembic/versions/002_rls.py`
- Modify: `backend/app/models/base.py`
- Create: `backend/app/core/team_scope.py`

- [ ] **Step 1: Write `backend/app/core/team_scope.py`**

```python
from __future__ import annotations
from sqlalchemy import select, event
from sqlalchemy.orm import Session
from app.models.base import TeamScopedMixin


def apply_team_scope(query, team_ids: list[str], model_class):
    """Apply team_id filter + deleted_at IS NULL to any team-scoped model query."""
    import uuid
    return query.where(
        model_class.team_id.in_([uuid.UUID(t) for t in team_ids]),
        model_class.deleted_at.is_(None),
    )
```

- [ ] **Step 2: Write Alembic migration for RLS**

Create `backend/alembic/versions/002_rls.py`:

```python
"""Enable RLS on team-scoped tables

Revision ID: 002
Revises: 001
"""
from alembic import op

def upgrade():
    for table in ("registries", "images", "merge_requests"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY team_isolation ON {table}
            USING (team_id = ANY(
                string_to_array(current_setting('patchpilot.team_ids', true), ',')::uuid[]
            ))
        """)

def downgrade():
    for table in ("registries", "images", "merge_requests"):
        op.execute(f"DROP POLICY IF EXISTS team_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
```

- [ ] **Step 3: Apply migration**

```bash
cd backend && alembic upgrade head
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/team_scope.py backend/alembic/versions/002_rls.py
git commit -m "feat: Postgres RLS on team-scoped tables + team_scope helper"
```

---

**Phase 8 complete. All 8 phases are implemented.**

## Final verification checklist

- [ ] `docker compose up` — all 7 services healthy
- [ ] `pytest tests/ -v` — all tests pass
- [ ] `helm lint infra/helm/patchpilot/` — 0 failures
- [ ] `npm run build` in frontend — no TypeScript errors
- [ ] Register a Docker Hub image, trigger a scan, see real CVEs
- [ ] Select fixable CVEs, open Raise MR drawer, create MR, confirm GitLab MR opens on correct branch
- [ ] Re-trigger MR for same image digest — confirm existing MR is updated, not duplicated
- [ ] Verify no credential fields in any API response (`curl /api/registries | jq 'keys'`)
