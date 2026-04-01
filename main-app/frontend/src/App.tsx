import { Routes, Route, Navigate } from 'react-router-dom'
import { useLayout } from './context/LayoutContext'
import { useAuth } from './context/AuthContext'
import Layout from './components/Layout'
import LayoutCommandCenter from './components/LayoutCommandCenter'
import Dashboard from './pages/Dashboard'
import Products from './pages/Products'
import Agent from './pages/Agent'
import SOPs from './pages/SOPs'
import Documentation from './pages/Documentation'
import Settings from './pages/Settings'
import McpBuilder from './pages/McpBuilder'
import BrainsDashboard from './pages/BrainsDashboard'
import BrainGallery from './pages/BrainGallery'
import BrainSetup from './pages/BrainSetup'
import BrainDetail from './pages/BrainDetail'
import BrainApprovals from './pages/BrainApprovals'
import Login from './pages/Login'
import { Loader2 } from 'lucide-react'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth()
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-rt-bg">
        <Loader2 className="w-8 h-8 animate-spin text-rt-primary" />
      </div>
    )
  }
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}

function App() {
  const { layoutMode } = useLayout()
  const LayoutComponent = layoutMode === 'command-center' ? LayoutCommandCenter : Layout

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <LayoutComponent />
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<Dashboard />} />
        <Route path="groups" element={<Navigate to="/products" replace />} />
        <Route path="products" element={<Products />} />
        <Route path="agent" element={<Agent />} />
        <Route path="sops" element={<SOPs />} />
        <Route path="docs" element={<Documentation />} />
        <Route path="settings" element={<Settings />} />
        <Route path="mcp-builder" element={<McpBuilder />} />
        <Route path="brains" element={<BrainsDashboard />} />
        <Route path="brains/new" element={<BrainGallery />} />
        <Route path="brains/:brainId/setup" element={<BrainSetup />} />
        <Route path="brains/:brainId" element={<BrainDetail />} />
        <Route path="brains/approvals" element={<BrainApprovals />} />
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}

export default App
