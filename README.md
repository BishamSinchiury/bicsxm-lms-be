# Learning Management System (LMS) — Authentication Foundation

A robust, enterprise-grade authentication, user state, and session management foundation for a Learning Management System (LMS) built with Python 3.12, Django 5.x, Django REST Framework, PostgreSQL, Redis, and Celery.

---

## 1. Key Architectural Features

- **Strict Multi-Role Isolation**: Three completely isolated user portals operating simultaneously in the same browser session without collision:
  - **Admin** (`/api/admin/`) — 2-Step OTP authentication, staff permissions, teacher application management, user lifecycle & audit log management.
  - **Teacher** (`/api/teacher/`) — Self-registration, email verification OTP, administrative approval workflow (`PENDING`, `APPROVED`, `REJECTED`).
  - **Student** (`/api/student/`) — Self-registration, email verification OTP, immediate activation upon verification.
- **Role-Scoped HttpOnly JWT Cookies**:
  - `admin_access` & `admin_refresh` scoped strictly to path `/api/admin/`
  - `teacher_access` & `teacher_refresh` scoped strictly to path `/api/teacher/`
  - `student_access` & `student_refresh` scoped strictly to path `/api/student/`
  - Cryptographic token isolation using per-role HMAC signing secrets (`JWT_SIGNING_KEYS`).
- **Role-Specific Double-Submit CSRF Protection**:
  - Three distinct non-HttpOnly CSRF cookies set with `Path=/`:
    - `admin_csrf`
    - `teacher_csrf`
    - `student_csrf`
  - React Axios instances automatically extract their corresponding cookie and attach it as the `X-CSRFToken` request header on state-mutating requests (`POST`, `PUT`, `PATCH`, `DELETE`).
  - This architecture prevents cross-role CSRF overwriting when an operator tests Student, Teacher, and Admin accounts in adjacent tabs of the same browser.
- **Cryptographic OTP Engine**:
  - 6-digit cryptographically secure OTP generation (`secrets.choice`).
  - Stored in Redis (DB 1) as HMAC-SHA256 hashes with constant-time comparison (`hmac.compare_digest`).
  - 60-second resend cooldown and 5-attempt brute-force protection with lockout.
- **Comprehensive Token Invalidation**:
  - Logout revokes access and refresh tokens in Redis.
  - Password reset updates a per-user `tokens_valid_after` timestamp in Redis, invalidating all previously issued tokens globally.
- **Async Email Worker with Development Fallback**:
  - Celery background workers with automatic exponential backoff retries.
  - Multi-part HTML & plain-text responsive email templates.
  - Automatic fallback to console backend (`django.core.mail.backends.console.EmailBackend`) when SMTP credentials are not configured or empty, logging OTP codes directly to the terminal stdout.
- **OpenAPI 3.0 Documentation**:
  - Interactive Swagger UI (`/api/docs/`) and ReDoc (`/api/redoc/`) via `drf-spectacular`.

---

## 2. Redis Database Allocation

| DB Index | Component | Purpose |
|---|---|---|
| `0` | Django Cache (`django-redis`) | User-state lookups, rate limiting |
| `1` | OTP & Revocation Storage | HMAC OTP hashes, token blacklist, `tokens_valid_after` timestamps |
| `2` | Celery Broker | Message queue for asynchronous tasks |
| `3` | Celery Backend | Task execution results |

---

## 3. Environment Variables Reference

See `.env.example` for the complete template.

| Variable | Description | Default |
|---|---|---|
| `DJANGO_SECRET_KEY` | Core Django cryptographic secret | Required |
| `DJANGO_DEBUG` | Enable debug mode | `False` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated allowed hostnames | `localhost,127.0.0.1` |
| `POSTGRES_DB` | PostgreSQL database name | `lms` |
| `POSTGRES_USER` | PostgreSQL username | `postgres` |
| `POSTGRES_PASSWORD` | PostgreSQL password | Required |
| `POSTGRES_HOST` | PostgreSQL host | `localhost` / `postgres` |
| `POSTGRES_PORT` | PostgreSQL port | `5432` |
| `REDIS_URL` | Base Redis connection string | `redis://localhost:6379` |
| `JWT_SIGNING_KEY_ADMIN` | Secret signing key for Admin tokens | Required |
| `JWT_SIGNING_KEY_TEACHER` | Secret signing key for Teacher tokens | Required |
| `JWT_SIGNING_KEY_STUDENT` | Secret signing key for Student tokens | Required |
| `JWT_ACCESS_TOKEN_LIFETIME_MINUTES` | Access token lifespan | `15` |
| `JWT_REFRESH_TOKEN_LIFETIME_DAYS` | Refresh token lifespan | `7` |
| `JWT_COOKIE_SECURE` | Set `Secure` flag on JWT cookies (enable in HTTPS production) | `False` |
| `JWT_COOKIE_SAMESITE` | `SameSite` attribute for JWT cookies (`Lax`, `Strict`, `None`) | `Lax` |
| `OTP_HMAC_SECRET` | Secret key for hashing OTPs in Redis | Required |
| `OTP_TTL` | OTP lifespan in seconds | `300` (5 minutes) |
| `OTP_RESEND_COOLDOWN` | Cooldown period between OTP requests in seconds | `60` |
| `OTP_MAX_ATTEMPTS` | Max allowed wrong attempts before invalidation | `5` |
| `EMAIL_BACKEND` | Email backend class | `django.core.mail.backends.console.EmailBackend` |
| `EMAIL_HOST` | SMTP server host (e.g. `smtp.gmail.com`) | Blank (console fallback) |
| `EMAIL_PORT` | SMTP server port | `587` |
| `EMAIL_HOST_USER` | SMTP username / Gmail address | Blank |
| `EMAIL_HOST_PASSWORD` | SMTP password / 16-character Google App Password | Blank |
| `EMAIL_USE_TLS` | Use TLS encryption for SMTP | `True` |
| `DEFAULT_FROM_EMAIL` | Default sender email address | `noreply@lms.local` |
| `CORS_ALLOWED_ORIGINS` | Comma-separated origins allowed for cross-origin requests | `http://localhost:5173,http://localhost:3000` |
| `FRONTEND_ORIGIN` | Allowed client origin for CORS/CSRF headers | `http://localhost:5173` |
| `FRONTEND_BASE_URL` | Base frontend URL for email verification links | `http://localhost:5173` |
| `USER_STATE_CACHE_TTL` | Cached user active/status lookup TTL in seconds | `15` |

---

## 4. Email Configuration & Gmail App Password Setup

### Development (Console Backend)
By default, `EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend`.
Whenever an OTP or verification email is dispatched, it is printed directly to the terminal stdout of the running Celery worker (or Django dev server if eager execution is enabled).

### Production / Live Email Delivery (Gmail SMTP)
To send real verification emails via Google Gmail SMTP:
1. **Enable 2-Step Verification** on your Google Account: [Google Account Security](https://myaccount.google.com/security).
2. **Create an App Password**:
   - Navigate to Security → 2-Step Verification → **App passwords**.
   - Enter an app name (e.g. `LMS Backend`) and click **Create**.
   - Copy the generated 16-character password (e.g. `abcd efgh ijkl mnop`).
3. **Configure `.env`**:
   ```env
   EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
   EMAIL_HOST=smtp.gmail.com
   EMAIL_PORT=587
   EMAIL_HOST_USER=your-actual-email@gmail.com
   EMAIL_HOST_PASSWORD=abcdefghijklmnop
   EMAIL_USE_TLS=True
   DEFAULT_FROM_EMAIL=your-actual-email@gmail.com
   ```
4. **Safety Fallback**: If `EMAIL_HOST_PASSWORD` is omitted or empty while using `smtp.EmailBackend`, the application automatically falls back to `console.EmailBackend` and logs a warning in console logs so that local testing never fails due to missing credentials.

---

## 5. API Endpoints Reference

### Student Authentication (`/api/student/auth/`)

| Method | Path | Auth / Scope | Description |
|---|---|---|---|
| `POST` | `/api/student/auth/signup/` | Public | Register student, send OTP, set limited cookies & `student_csrf` |
| `POST` | `/api/student/auth/verify-otp/` | Cookie (Limited) | Verify OTP, upgrade token to `full` scope |
| `POST` | `/api/student/auth/resend-otp/` | Cookie (Limited) | Resend verification code (60s cooldown enforced) |
| `POST` | `/api/student/auth/login/` | Public | Login with email + password, sets student cookies |
| `POST` | `/api/student/auth/token/refresh/` | Cookie (Refresh) | Rotate refresh token, issue fresh access token |
| `POST` | `/api/student/auth/logout/` | Cookie (Limited/Full) | Blacklist tokens in Redis, delete student cookies |
| `GET` | `/api/student/auth/me/` | Cookie (Limited/Full) | Retrieve authenticated student profile & status |
| `POST` | `/api/student/auth/password-reset/request/` | Public | Request reset OTP (generic response) |
| `POST` | `/api/student/auth/password-reset/confirm/` | Public | Verify reset OTP, update password, invalidate tokens |

### Teacher Authentication (`/api/teacher/auth/`)

| Method | Path | Auth / Scope | Description |
|---|---|---|---|
| `POST` | `/api/teacher/auth/signup/` | Public | Register teacher, send OTP, set limited cookies & `teacher_csrf` |
| `POST` | `/api/teacher/auth/verify-otp/` | Cookie (Limited) | Verify email OTP; status remains `PENDING_APPROVAL` |
| `POST` | `/api/teacher/auth/resend-otp/` | Cookie (Limited) | Resend verification code (60s cooldown enforced) |
| `POST` | `/api/teacher/auth/login/` | Public | Login; issues limited token if pending/rejected |
| `POST` | `/api/teacher/auth/token/refresh/` | Cookie (Refresh) | Re-evaluates status (upgrades to `full` when approved) |
| `POST` | `/api/teacher/auth/logout/` | Cookie (Limited/Full) | Revoke tokens in Redis, clear teacher cookies |
| `GET` | `/api/teacher/auth/me/` | Cookie (Limited/Full) | Retrieve teacher profile and approval status |
| `POST` | `/api/teacher/auth/password-reset/request/` | Public | Request reset OTP (generic response) |
| `POST` | `/api/teacher/auth/password-reset/confirm/` | Public | Confirm reset with OTP, update password |

### Admin Authentication & Teacher Approvals (`/api/admin/`)

| Method | Path | Auth / Scope | Description |
|---|---|---|---|
| `POST` | `/api/admin/auth/login/` | Public | Step 1: Verify email + password -> Dispatches OTP |
| `POST` | `/api/admin/auth/login/verify-otp/` | Public | Step 2: Verify OTP -> Sets admin cookies (`full` scope) & `admin_csrf` |
| `POST` | `/api/admin/auth/resend-otp/` | Public | Resend Step 1 OTP without cookie (cooldown enforced) |
| `POST` | `/api/admin/auth/token/refresh/` | Cookie (Refresh) | Refresh admin access token |
| `POST` | `/api/admin/auth/logout/` | Cookie (Admin Full) | Revoke admin tokens, clear admin cookies |
| `GET` | `/api/admin/auth/me/` | Cookie (Admin Full) | Retrieve admin profile |
| `GET` | `/api/admin/teachers/` | Cookie (Admin Full) | List teachers (filter: `?status=pending\|approved\|rejected`) |
| `POST` | `/api/admin/teachers/{id}/approve/` | Cookie (Admin Full) | Approve teacher account, send notification email |
| `POST` | `/api/admin/teachers/{id}/reject/` | Cookie (Admin Full) | Reject teacher account, send notification email |

### Admin User Management (`/api/admin/users/`)

| Method | Path | Auth / Scope | Description |
|---|---|---|---|
| `GET` | `/api/admin/users/` | Cookie (Admin Full) | List all users (filters: `?role=`, `?status=`, `?search=`, pagination `page`, `page_size`) |
| `GET` | `/api/admin/users/{id}/` | Cookie (Admin Full) | Retrieve user details by UUID |
| `PATCH` | `/api/admin/users/{id}/` | Cookie (Admin Full) | Update user profile (`full_name`) |
| `DELETE` | `/api/admin/users/{id}/` | Cookie (Admin Full) | Soft-delete user (`is_active=False`, prevents self & last-admin deletion) |
| `POST` | `/api/admin/users/{id}/activate/` | Cookie (Admin Full) | Re-activate a deactivated user (`is_active=True`, logs AuditLog) |
| `POST` | `/api/admin/users/{id}/deactivate/` | Cookie (Admin Full) | Deactivate user (`is_active=False`, logs AuditLog) |
| `POST` | `/api/admin/users/{id}/resend-verification/`| Cookie (Admin Full) | Resend email verification OTP to unverified user |

### Dashboard Verification Pings

| Method | Path | Auth Required | Expected Output |
|---|---|---|---|
| `GET` | `/api/admin/dashboard/ping/` | Admin (`full`) | `{"role": "admin", "message": "pong"}` |
| `GET` | `/api/teacher/dashboard/ping/` | Teacher (`full`) | `{"role": "teacher", "message": "pong"}` |
| `GET` | `/api/student/dashboard/ping/` | Student (`full`) | `{"role": "student", "message": "pong"}` |

---

## 6. Local Setup & Execution Guide

### Prerequisites
- Python 3.12+
- PostgreSQL 16+
- Redis 7+
- Node.js 18+ (for frontend)

### 1. Environment Setup
```bash
cd backend
python -m venv .venv

# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

### 2. Database Migrations
```bash
python manage.py migrate
```

### 3. Create Default Admin Account
```bash
python manage.py create_admin --email admin@lms.local --password "AdminPass123!" --full-name "LMS SuperAdmin"
```

### 4. Run Development Services
```bash
# Terminal 1: Django API Server (runs on http://localhost:8000)
python manage.py runserver 8000

# Terminal 2: Celery Background Worker
celery -A config worker -l info
```

### 5. Run Test Suite
```bash
pytest
```
To run specific test modules:
```bash
pytest apps/accounts/tests/test_admin_user_management.py
pytest apps/authentication/tests/test_role_isolation.py
```

### 6. Where to Find OTPs During Local Testing
When using the default console backend, OTPs appear directly in the output of the running service:
- If Celery is running: Inspect the **Celery Worker terminal**.
- If `CELERY_TASK_ALWAYS_EAGER=True`: Inspect the **Django dev server terminal**.
- Look for blocks formatted like:
  ```text
  --------------------------------------------------
  Your verification code is: 123456
  --------------------------------------------------
  ```
- Alternatively, check Redis directly:
  ```bash
  redis-cli -n 1 KEYS "otp:*"
  ```

---

## 7. Docker Compose Deployment

To spin up the entire backend stack (PostgreSQL, Redis, Mongo init replica set, Django API, Celery worker) automatically:

```bash
docker compose up --build
```
Interactive API documentation will be available at:
- **Swagger UI**: `http://localhost:8000/api/docs/`
- **ReDoc**: `http://localhost:8000/api/redoc/`
