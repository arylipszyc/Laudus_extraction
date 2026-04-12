// Base API configuration — Story 3 adds feature-specific functions
const API_BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export const api = {
  baseUrl: API_BASE_URL,
}
