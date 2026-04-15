# Story 1.3: Google OAuth Authentication

Status: review

## Story

As an owner or contador,
I want to log in to the platform using my Google account,
so that I can access financial data securely without managing a separate username and password.

## Acceptance Criteria

1. User visiting the app without a session is redirected to `/login`
2. Login page displays a functional "Iniciar sesión con Google" button that initiates OAuth redirect
3. Backend receives OAuth callback, generates a JWT, and sets it as an httpOnly cookie
4. JWT is never accessible via JavaScript (`document.cookie`)
5. Subsequent API requests send the cookie automatically and backend validates JWT
6. Logout clears the httpOnly cookie server-side and redirects to `/login`
7. Unauthenticated requests to `/api/v1/` (except `/auth/*`) return HTTP 401
8. `App.tsx` auth guard reads real session state — authenticated users reach dashboard, unauthenticated go to `/login`

## Tasks / Subtasks

- [x] Backend: auth schemas (AC: 3)
  - [x] `backend/app/auth/schemas.py` — `TokenResponse`, `UserSession` Pydantic models
- [x] Backend: auth service — OAuth flow + JWT (AC: 3, 4, 7)
  - [x] `backend/app/auth/service.py` — Google OAuth flow via `authlib`
  - [x] JWT generation with `python-jose`: encode `email` + `role` + `exp` (8h)
  - [x] JWT decode + validation helper
- [x] Backend: auth router (AC: 2, 3, 6, 7)
  - [x] `backend/app/auth/router.py` — `GET /api/v1/auth/login`, `GET /api/v1/auth/callback`, `POST /api/v1/auth/logout`, `GET /api/v1/auth/me`
  - [x] `/login` redirects to Google OAuth consent URL
  - [x] `/callback` exchanges code for token, creates JWT, sets httpOnly cookie, redirects to `/dashboard`
  - [x] `/logout` clears cookie, returns 200
  - [x] `/me` returns current user from JWT (used by frontend to check session)
  - [x] Register auth router in `backend/app/api/v1/router.py`
- [x] Backend: `get_current_user()` dependency stub (AC: 5, 7)
  - [x] `backend/app/dependencies.py` — implement `get_current_user()` that reads JWT from cookie and returns `UserSession`
  - [x] Returns HTTP 401 if cookie missing, expired, or invalid
- [x] Frontend: update `App.tsx` auth guard (AC: 1, 8)
  - [x] `frontend/src/services/auth.ts` — `getMe()` calls `GET /api/v1/auth/me`
  - [x] `frontend/src/hooks/useAuth.ts` — React Query hook wrapping `getMe()`
  - [x] `App.tsx` `RequireAuth` uses `useAuth` — shows loading skeleton while checking, redirects to `/login` if no session
- [x] Frontend: update `LoginPlaceholder.tsx` → `Login.tsx` (AC: 2)
  - [x] Real login page with Google OAuth button that calls `GET /api/v1/auth/login`
  - [x] Show loading state during redirect
- [x] Frontend: logout in `Header.tsx` (AC: 6)
  - [x] "Cerrar sesión" button calls `POST /api/v1/auth/logout` then navigates to `/login`

## Dev Notes

### Google OAuth Setup Required

Before implementation, the following env vars must exist in `.env`:
```
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
FRONTEND_URL=http://localhost:5173
JWT_SECRET=<random 32-byte hex>
JWT_ALGORITHM=HS256
JWT_EXPIRE_HOURS=8
```

Register `http://localhost:8000/api/v1/auth/callback` as an authorized redirect URI in Google Cloud Console.

### Backend: authlib OAuth Client Setup

```python
from authlib.integrations.starlette_client import OAuth

oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)
```

### JWT Generation with python-jose

```python
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone

SECRET = os.getenv('JWT_SECRET')
ALGORITHM = os.getenv('JWT_ALGORITHM', 'HS256')
EXPIRE_HOURS = int(os.getenv('JWT_EXPIRE_HOURS', '8'))

def create_jwt(email: str, role: str) -> str:
    payload = {
        'sub': email,
        'role': role,
        'exp': datetime.now(timezone.utc) + timedelta(hours=EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)

def decode_jwt(token: str) -> dict:
    return jwt.decode(token, SECRET, algorithms=[ALGORITHM])
```

### httpOnly Cookie Pattern

```python
# In /callback handler
response.set_cookie(
    key='access_token',
    value=token,
    httponly=True,
    secure=False,   # True in production (Cloud Run serves HTTPS)
    samesite='lax',
    max_age=8 * 3600,
)

# In get_current_user()
token = request.cookies.get('access_token')
```

### Role Assignment

For MVP, roles are pre-configured via env var `ALLOWED_USERS`:
```
ALLOWED_USERS=ary@example.com:owner,contador@example.com:contador
```

`auth/service.py` looks up the authenticated email in `ALLOWED_USERS`. If not found → HTTP 403.

Add `ALLOWED_USERS` to `.env.example`.

### Frontend: useAuth Hook

```typescript
// src/hooks/useAuth.ts
import { useQuery } from '@tanstack/react-query'
import { getMe } from '@/services/auth'

export function useAuth() {
  return useQuery({
    queryKey: ['auth', 'me'],
    queryFn: getMe,
    retry: false,
    staleTime: 5 * 60 * 1000, // 5 min
  })
}
```

### Frontend: RequireAuth with Loading State

```typescript
function RequireAuth({ children }: { children: React.ReactNode }) {
  const { data: user, isLoading } = useAuth()
  if (isLoading) return <Skeleton className="h-screen w-screen" />
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}
```

### API URL for Frontend

Frontend calls backend at `import.meta.env.VITE_API_URL` (default `http://localhost:8000`).
All auth calls use `fetch` with `credentials: 'include'` so cookies are sent cross-origin.

### Story 1.1 / 1.2 Context

- `backend/app/dependencies.py` already exists with `get_repository()` — add `get_current_user()` to the same file
- `frontend/src/App.tsx` has `RequireAuth` stub with `isAuthenticated = false` — replace with `useAuth()`
- `frontend/src/pages/LoginPlaceholder.tsx` → rename/replace with `Login.tsx`
- Auth router goes in `backend/app/auth/router.py`, registered in `backend/app/api/v1/router.py`

### References

- Architecture: Auth → `architecture.md#Authentication & Security`
- Architecture: RBAC → `architecture.md#Process Patterns`
- Story 1.1 deps file: `backend/requirements.txt` already has `authlib`, `python-jose[cryptography]`

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- `starlette.middleware.sessions.SessionMiddleware` requires `itsdangerous` — not in requirements.txt. Added `itsdangerous>=2.1.0` to requirements.txt and Pipfile.
- `LoginPlaceholder.tsx` kept (not deleted) to avoid breaking any future reference; `Login.tsx` is the replacement used in `App.tsx`.

### Completion Notes List

- All 8 ACs satisfied. Backend: 27/27 tests passing. Frontend: 88 modules, 0 TS errors, build 533ms.
- `SessionMiddleware` added to middleware.py — required by authlib for OAuth CSRF state.
- `ALLOWED_USERS` env var pattern implemented in `auth/service.py` with case-insensitive email lookup.
- `get_current_user()` added to `dependencies.py` alongside `get_repository()` as specified.
- `Login.tsx` uses `window.location.href` redirect (not fetch) — correct pattern for OAuth initiation.
- `logout()` in `services/auth.ts` + `Header.tsx` navigates to `/login` after server-side cookie clear.

### File List

- `backend/app/auth/__init__.py` (new)
- `backend/app/auth/schemas.py` (new)
- `backend/app/auth/service.py` (new)
- `backend/app/auth/router.py` (new)
- `backend/app/api/v1/router.py` (modified: registered auth router)
- `backend/app/dependencies.py` (modified: added `get_current_user()`)
- `backend/app/middleware.py` (modified: added `SessionMiddleware`)
- `backend/requirements.txt` (modified: added `itsdangerous`)
- `backend/tests/test_auth.py` (new — 12 tests)
- `Pipfile` (modified: added `itsdangerous`)
- `.env.example` (modified: added `ALLOWED_USERS`)
- `frontend/src/services/auth.ts` (new)
- `frontend/src/hooks/useAuth.ts` (new)
- `frontend/src/pages/Login.tsx` (new)
- `frontend/src/App.tsx` (modified: RequireAuth uses useAuth, Login.tsx route)
- `frontend/src/components/layout/Header.tsx` (modified: real logout flow)
