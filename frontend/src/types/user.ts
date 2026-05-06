export type UserRole = 'family' | 'contador' | 'admin'

export interface UserSession {
  email: string
  role: UserRole
}
