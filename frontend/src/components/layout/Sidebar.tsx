import { NavLink } from 'react-router-dom'
import { Server, Image, GitMerge } from 'lucide-react'

const nav = [
  { to: '/registries', label: 'Registries', icon: Server },
  { to: '/images', label: 'Images', icon: Image },
  { to: '/merge-requests', label: 'Merge Requests', icon: GitMerge },
]

export function Sidebar() {
  return (
    <aside className="w-56 bg-slate-800 border-r border-slate-700 flex flex-col shrink-0">
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
