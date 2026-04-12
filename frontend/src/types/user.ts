export type UserRole = 'owner' | 'contador'

export interface UserSession {
  email: string
  role: UserRole
}
