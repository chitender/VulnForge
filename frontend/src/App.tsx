import { useAuth } from 'react-oidc-context'
import { useEffect } from 'react'
import { setAuthToken, clearAuthToken } from './lib/api'

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
    <div className="min-h-screen bg-slate-900 text-slate-100 p-8">
      <p className="text-slate-400">Signed in as {auth.user?.profile.email}</p>
      <p className="text-green-400 mt-2">✓ Foundation complete — routing coming in Phase 5</p>
    </div>
  )
}
