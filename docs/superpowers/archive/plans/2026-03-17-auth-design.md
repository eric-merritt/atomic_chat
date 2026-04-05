# Authentication & Authorization System

**Date:** 2026-03-17
**Status:** Approved
**Scope:** Add user auth (OAuth + local), API keys, role-based access, PostgreSQL user store

---

## 1. Token Types

Three distinct authentication mechanisms for different access patterns:

| Token Type | Transport | Lifetime | Use Case |
|------------|-----------|----------|----------|
| Session cookie | `Set-Cookie` (httpOnly, secure, sameSite=lax) | 24h, sliding | SPA browser sessions |
| Personal API key | `Authorization: Bearer <key>` or `X-API-Key` header | Long-lived, revocable | Programmatic access, roommate GPU access |
| Integration/OAuth token | Stored server-side per user | Provider-managed, refreshable | Third-party integrations (GitHub repos, etc.) |

---

## 2. Tech Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Auth framework | Flask-Login | Native Flask session management, well-tested |
| ORM | SQLAlchemy | Schema definition, migrations via Alembic |
| Migrations | Alembic | Incremental schema changes |
| OAuth | authlib | GitHub + Google OAuth2 flows |
| Password hashing | bcrypt | Industry standard, timing-safe |
| Database | PostgreSQL | Multi-user, relational, production-ready |

---

## 3. Database Schema

### users

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| email | VARCHAR(255) | Unique, nullable (OAuth users may not have one initially) |
| username | VARCHAR(64) | Unique, required |
| password_hash | VARCHAR(255) | Nullable (OAuth-only users have no password) |
| auth_method | VARCHAR(16) | `"local"` or `"oauth"` |
| oauth_provider | VARCHAR(32) | `"github"`, `"google"`, or NULL |
| oauth_provider_id | VARCHAR(255) | Provider's user ID |
| role | VARCHAR(16) | `"admin"`, `"user"`, `"viewer"` |
| avatar_url | VARCHAR(512) | From OAuth profile or Gravatar |
| created_at | TIMESTAMP | Default now() |
| last_login | TIMESTAMP | Updated on each login |

### sessions

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key, used as cookie value |
| user_id | UUID | FK → users.id |
| created_at | TIMESTAMP | Default now() |
| expires_at | TIMESTAMP | 24h from creation, sliding on activity |
| ip_address | VARCHAR(45) | Client IP at creation |
| user_agent | VARCHAR(512) | Browser/client identifier |

### api_keys

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| user_id | UUID | FK → users.id |
| key_hash | VARCHAR(255) | bcrypt hash of the key (raw key shown once at creation) |
| key_prefix | VARCHAR(8) | First 8 chars for identification (e.g., `ak_3f8b...`) |
| label | VARCHAR(128) | User-defined name ("my laptop", "roommate GPU") |
| role_override | VARCHAR(16) | Optional — override user's role for this key |
| created_at | TIMESTAMP | |
| last_used | TIMESTAMP | Updated on each use |
| revoked | BOOLEAN | Soft delete |

### oauth_tokens

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| user_id | UUID | FK → users.id |
| provider | VARCHAR(32) | `"github"`, `"google"`, etc. |
| access_token | VARCHAR(512) | Encrypted at rest |
| refresh_token | VARCHAR(512) | Encrypted at rest |
| scopes | VARCHAR(512) | Granted scopes |
| expires_at | TIMESTAMP | Token expiry |

---

## 4. API Middleware & Route Protection

### Authentication middleware (`before_request`)

Runs on every Flask request. Checks auth sources in priority order:

```
1. Session cookie → validate session in DB → attach user to g.user
2. Authorization: Bearer <key> → hash, lookup in api_keys → attach user
3. X-API-Key header → same as above
4. Static IP + API key match → auto-auth as admin (see Section 7)
5. None matched → g.user = None (anonymous)
```

### Route classification

```python
PUBLIC_PATHS = {
    "/api/health",
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/oauth/github",
    "/api/auth/oauth/github/callback",
    "/api/auth/oauth/google",
    "/api/auth/oauth/google/callback",
}

# Everything under /api/* not in PUBLIC_PATHS requires authentication
# Admin routes (/api/admin/*) require role == "admin"
# All other authenticated routes are accessible to any role
```

### Decorator pattern

```python
@public                # No auth check
@login_required        # Any authenticated user (Flask-Login built-in)
@admin_required        # role == "admin" only
```

---

## 5. OAuth Flow (GitHub & Google)

### Flow

```
1. User clicks "Sign in with GitHub"
   → GET /api/auth/oauth/github
   → 302 redirect to GitHub authorize URL (client_id, scope, state)

2. GitHub redirects back
   → GET /api/auth/oauth/github/callback?code=...&state=...
   → Exchange code for access token
   → Fetch user profile (email, name, avatar)
   → find_or_create user:
       - Match by (provider="github", provider_id=github_user_id)
       - If new: create user with auth_method="oauth", role="user"
       - If exists: update last_login, avatar
   → Store OAuth tokens in oauth_tokens table
   → Create session, set httpOnly cookie
   → 302 redirect to SPA /

3. Same pattern for Google at /api/auth/oauth/google/*
```

### Configuration

```
GITHUB_CLIENT_ID      — env var
GITHUB_CLIENT_SECRET  — env var
GOOGLE_CLIENT_ID      — env var
GOOGLE_CLIENT_SECRET  — env var
OAUTH_REDIRECT_BASE   — e.g., https://agent.eric-merritt.com
```

---

## 6. Registration & Login (Local Auth)

### Register

```
POST /api/auth/register
Body: { email, username, password }

→ Validate:
  - email unique (if provided)
  - username unique, 3-64 chars, alphanumeric + underscore
  - password >= 8 chars
→ Hash password (bcrypt, 12 rounds)
→ Create user (auth_method="local", role="user")
→ Create session, set cookie
→ 201 { user: { id, username, email, role } }
```

### Login

```
POST /api/auth/login
Body: { username, password }

→ Lookup user by username OR email
→ Verify bcrypt hash
→ Update last_login
→ Create session, set cookie
→ 200 { user: { id, username, email, role } }

Failure: 401 { error: "Invalid credentials" }
  (same message for bad username or bad password — no enumeration)
```

### Logout

```
POST /api/auth/logout
→ Delete session from DB
→ Clear cookie
→ 200 { ok: true }
```

### Current user

```
GET /api/auth/me
→ If authenticated: 200 { user: { id, username, email, role, avatar_url } }
→ If not: 401 { error: "Not authenticated" }
```

---

## 7. Static IP Auto-Auth

For the admin's static IP (50.248.206.70), API key presence auto-authenticates without login:

```python
ADMIN_STATIC_IP = os.environ.get("ADMIN_STATIC_IP", "50.248.206.70")

# In before_request:
if request.remote_addr == ADMIN_STATIC_IP:
    api_key = request.headers.get("X-API-Key") or request.args.get("api_key")
    if api_key:
        key_user = lookup_api_key(api_key)
        if key_user:
            g.user = key_user
            # No session created — stateless per-request auth
```

Roommate's API key works the same way from the same IP — his key maps to his user account with `role="user"`. Both have full Ollama/chat/tools access; only admin routes are gated.

---

## 8. Frontend Auth Integration

### New files

```
frontend/src/
  api/auth.ts              ← API adapter (login, register, logout, me)
  atoms/user.ts            ← User type, Role enum
  providers/AuthProvider.tsx ← top of context hierarchy
  hooks/useAuth.ts         ← convenience hook
  pages/LoginPage.tsx      ← login form, register tab, OAuth buttons
```

### AuthProvider behavior

```
On mount:
  GET /api/auth/me
    → success: set user, authenticated=true
    → 401: set anonymous, authenticated=false
    → loading=false

Route gate:
  if (loading) → spinner
  if (!authenticated) → <LoginPage />
  if (authenticated) → <ChatPage /> (existing app)
```

### Context hierarchy (updated)

```
<AuthProvider>        ← NEW: gates everything
  <ThemeProvider>
    <ModelProvider>
      <ToolProvider>
        <ChatProvider>
          <WebSocketProvider>
            <Router>
              <Routes />
            </Router>
          </WebSocketProvider>
        </ChatProvider>
      </ToolProvider>
    </ModelProvider>
  </ThemeProvider>
</AuthProvider>
```

### Session handling

The SPA relies on httpOnly session cookies — set by Flask, sent automatically by the browser on every fetch. No token storage in localStorage/sessionStorage. The `credentials: 'include'` fetch option is set on all API calls.

API key users (programmatic, roommate's scripts) pass `Authorization: Bearer <key>` in headers and don't interact with the SPA auth flow.

---

## 9. Implementation Order

1. **PostgreSQL setup** — install, create database, configure connection
2. **SQLAlchemy models** — User, Session, ApiKey, OAuthToken
3. **Alembic init** — migration infrastructure, initial schema migration
4. **Auth middleware** — `before_request` handler, route protection decorators
5. **Local auth endpoints** — register, login, logout, me
6. **API key management** — create, list, revoke endpoints
7. **OAuth endpoints** — GitHub flow, then Google
8. **Static IP auto-auth** — admin + roommate key setup
9. **Frontend AuthProvider** — context, hook, API adapter
10. **LoginPage** — login form, register form, OAuth buttons
11. **Wire up** — wrap App in AuthProvider, add `credentials: 'include'` to all fetches
12. **Seed admin user** — CLI command or migration to create initial admin account

---

## 10. Environment Variables

```
DATABASE_URL=postgresql://user:pass@localhost:5432/agentic
SECRET_KEY=<flask-session-secret>
ADMIN_STATIC_IP=50.248.206.70
ADMIN_API_KEY=<admin-key>
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
OAUTH_REDIRECT_BASE=https://agent.eric-merritt.com
```
