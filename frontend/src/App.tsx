import { BrowserRouter, Routes, Route, useNavigate, useParams } from 'react-router-dom'
import { ProjectProvider } from './context/ProjectContext'
import { ToastProvider } from './context/ToastContext'
import MainLayout from './layouts/MainLayout'
import Dashboard from './pages/Dashboard'
import UploadPage from './pages/UploadPage'
import ProjectDetails from './pages/ProjectDetails'
import TrailersGalleryPage from './pages/TrailersGalleryPage'
import AnalyticsPage from './pages/AnalyticsPage'
import ScrubberPage from './pages/ScrubberPage'
import SmartDetailsPage from './pages/SmartDetailsPage'
import NotFound from './pages/NotFound'

function SmartDetailsRoute() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  return (
    <SmartDetailsPage
      jobId={id!}
      onBack={() => navigate('/trailers?mode=smart')}
    />
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <ProjectProvider>
          <Routes>
            <Route element={<MainLayout />}>
              <Route path="/" element={<Dashboard />} />
              <Route path="/upload" element={<UploadPage />} />
              <Route path="/project/:id" element={<ProjectDetails />} />
              <Route path="/trailers" element={<TrailersGalleryPage />} />
              <Route path="/analytics" element={<AnalyticsPage />} />
              <Route path="/scrubber" element={<ScrubberPage />} />
              <Route path="/smart-trailer/:id" element={<SmartDetailsRoute />} />
            </Route>
            <Route path="*" element={<NotFound />} />
          </Routes>
        </ProjectProvider>
      </ToastProvider>
    </BrowserRouter>
  )
}
