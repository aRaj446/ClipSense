import { useNavigate } from 'react-router-dom'
import { SearchX } from 'lucide-react'
import Button from '../components/Button'

export default function NotFound() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-surface flex flex-col items-center justify-center text-center px-4">
      <SearchX size={64} className="text-slate-600 mb-6" />
      <h1 className="text-6xl font-bold text-primary mb-2">404</h1>
      <p className="text-xl text-slate-300 font-medium mb-2">Page Not Found</p>
      <p className="text-slate-500 mb-8">
        The page you're looking for doesn't exist or has been moved.
      </p>
      <Button onClick={() => navigate('/')}>Go to Dashboard</Button>
    </div>
  )
}
