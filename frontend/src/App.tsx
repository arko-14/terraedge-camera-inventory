import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import type { ReactNode } from 'react'

import { useAuth } from './auth/AuthContext'
import { Layout } from './components/Layout'
import { LoadingBlock } from './components/ui'
import { CameraDetailPage } from './pages/CameraDetailPage'
import { CamerasPage } from './pages/CamerasPage'
import { DashboardPage } from './pages/DashboardPage'
import { ImportCamerasPage } from './pages/ImportCamerasPage'
import { LoginPage } from './pages/LoginPage'
import { MapPage } from './pages/MapPage'
import { RegisterCameraPage } from './pages/RegisterCameraPage'

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, initialising } = useAuth()
  const location = useLocation()

  if (initialising) return <LoadingBlock label="Checking your session…" />
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return <>{children}</>
}

/**
 * A usability guard only: it stops a range user opening a page that can only
 * fail. The backend rejects the request regardless of what the UI shows.
 */
function RequireAdmin({ children }: { children: ReactNode }) {
  const { isAdmin } = useAuth()
  if (!isAdmin) return <Navigate to="/cameras" replace />
  return <>{children}</>
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route path="/" element={<DashboardPage />} />
        <Route path="/cameras" element={<CamerasPage />} />
        <Route path="/map" element={<MapPage />} />
        <Route
          path="/cameras/new"
          element={
            <RequireAdmin>
              <RegisterCameraPage />
            </RequireAdmin>
          }
        />
        <Route
          path="/cameras/import"
          element={
            <RequireAdmin>
              <ImportCamerasPage />
            </RequireAdmin>
          }
        />
        <Route path="/cameras/:cameraId" element={<CameraDetailPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
