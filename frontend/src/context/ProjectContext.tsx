import { createContext, useContext, useState, useCallback, ReactNode } from 'react'
import { Project } from '../types/project'
import { projectService } from '../services/projectService'

interface ProjectContextValue {
  projects: Project[]
  loading: boolean
  fetchProjects: () => Promise<void>
  removeProject: (id: string) => Promise<void>
}

const ProjectContext = createContext<ProjectContextValue | null>(null)

export function ProjectProvider({ children }: { children: ReactNode }) {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(false)

  const fetchProjects = useCallback(async () => {
    setLoading(true)
    try {
      const data = await projectService.listProjects()
      setProjects(data)
    } finally {
      setLoading(false)
    }
  }, [])

  const removeProject = useCallback(async (id: string) => {
    await projectService.deleteProject(id)
    setProjects((prev) => prev.filter((p) => p.id !== id))
  }, [])

  return (
    <ProjectContext.Provider value={{ projects, loading, fetchProjects, removeProject }}>
      {children}
    </ProjectContext.Provider>
  )
}

export function useProjects() {
  const ctx = useContext(ProjectContext)
  if (!ctx) throw new Error('useProjects must be used inside ProjectProvider')
  return ctx
}
