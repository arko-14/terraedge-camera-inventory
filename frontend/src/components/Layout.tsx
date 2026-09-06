import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useState } from 'react'

import { useAuth } from '../auth/AuthContext'
import { Button } from './ui'

// Routes that sit under /cameras but have a nav entry of their own. Without
// this, NavLink's prefix matching lights up "Cameras" as well as "Register".
// A camera detail page (/cameras/12) is not listed, because it *is* part of
// the Cameras section and should highlight it.
const HAS_OWN_NAV_ENTRY = new Set(['/cameras/new', '/cameras/import'])

function navClass({ isActive }: { isActive: boolean }) {
  return `rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
    isActive ? 'bg-forest-100 text-forest-800' : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
  }`
}

export function Layout() {
  const { user, logout, isAdmin } = useAuth()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [signingOut, setSigningOut] = useState(false)

  async function handleSignOut() {
    setSigningOut(true)
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="flex min-h-full flex-col">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-forest-600 text-sm font-bold text-white">
              TE
            </span>
            <div className="leading-tight">
              <p className="text-sm font-semibold text-gray-900">Camera Inventory</p>
              <p className="text-xs text-gray-500">Similipal Tiger Reserve</p>
            </div>
          </div>

          <nav className="order-3 -mx-1 flex w-full gap-1 overflow-x-auto sm:order-none sm:w-auto">
            <NavLink to="/" end className={navClass}>
              Dashboard
            </NavLink>
            <NavLink
              to="/cameras"
              className={({ isActive }) =>
                navClass({ isActive: isActive && !HAS_OWN_NAV_ENTRY.has(pathname) })
              }
            >
              Cameras
            </NavLink>
            <NavLink to="/map" className={navClass}>
              Map
            </NavLink>
            {isAdmin && (
              <>
                <NavLink to="/cameras/new" className={navClass}>
                  Register
                </NavLink>
                <NavLink to="/cameras/import" className={navClass}>
                  Import
                </NavLink>
              </>
            )}
          </nav>

          <div className="ml-auto flex items-center gap-3">
            <div className="hidden text-right sm:block">
              <p className="text-sm font-medium text-gray-900">{user?.full_name}</p>
              <p className="text-xs text-gray-500">
                {isAdmin ? 'Reserve administrator' : `Range user · ${user?.range_name}`}
              </p>
            </div>
            <Button variant="secondary" onClick={handleSignOut} loading={signingOut}>
              Sign out
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 sm:py-8">
        <Outlet />
      </main>

      <footer className="border-t border-gray-200 bg-white px-4 py-3 text-center text-xs text-gray-500">
        Prototype · all camera, contact and location data shown is fictional.
      </footer>
    </div>
  )
}
