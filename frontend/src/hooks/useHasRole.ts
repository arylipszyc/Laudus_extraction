import { useAuth } from '@/hooks/useAuth'
import type { UserRole, UserSession } from '@/types'

/**
 * Story 9.13 — frontend RBAC helper.
 *
 * Returns true when the authenticated user's role is included in `roles`.
 * Loading/unauthenticated state returns false (deny by default).
 *
 * Frontend gates are UX only — backend always re-checks (defense-in-depth, AC5).
 */
export function useHasRole(roles: readonly UserRole[]): boolean {
  const { data } = useAuth()
  const user = data as UserSession | undefined
  if (!user) return false
  return roles.includes(user.role)
}
