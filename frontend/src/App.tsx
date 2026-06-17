import { useAuth } from 'react-oidc-context'
import { useEffect } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { clearAuthToken, setAuthToken } from './lib/api'
import { AppLayout } from './components/layout/AppLayout'
import { ImagesPage } from './pages/ImagesPage'
import { ImageDetailPage } from './pages/ImageDetailPage'
import { MergeRequestsPage } from './pages/MergeRequestsPage'
import { RegistriesPage } from './pages/RegistriesPage'
import { ScanResultsPage } from './pages/ScanResultsPage'

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
  )
}
