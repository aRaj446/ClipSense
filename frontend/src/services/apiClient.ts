import axios from 'axios'

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000',
  timeout: 0, // no timeout — needed for large video uploads up to 10 GB
})

export default apiClient
