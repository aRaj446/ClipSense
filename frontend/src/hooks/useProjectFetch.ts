import { useEffect } from 'react'
import { useProjects } from '../context/ProjectContext'

export function useProjectFetch() {
  const { fetchProjects, projects, loading } = useProjects()
  useEffect(() => {
    fetchProjects()
  }, [fetchProjects])
  return { projects, loading }
}
