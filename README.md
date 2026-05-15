# Intelligent Education CRM — Technical Reference

> **AI Agent Handoff Document** — Everything a new developer or AI agent needs to understand, run, extend, and deploy this system without prior context.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Tech Stack](#2-tech-stack)
3. [Folder Structure](#3-folder-structure)
4. [System Architecture](#4-system-architecture)
5. [Database Schema](#5-database-schema)
6. [Environment Setup](#6-environment-setup)
7. [URL & API Reference](#7-url--api-reference)
8. [Deployment Reference](#8-deployment-reference)
9. [Development Workflow](#9-development-workflow)
10. [Roadmap & Pending Tasks](#10-roadmap--pending-tasks)

---

## 1. Project Overview

**Intelligent Education CRM** is a multi-role student-management platform for international education counseling agencies. It manages the full student lifecycle from initial enquiry to school application submission.

### Key Capabilities

| Role | What they can do |
|------|-----------------|
| **Admin** | Full system access — manage users (counselors + students), view all data, assign schools, configure leads |
| **Staff (Counselor)** | Manage assigned students, assign schools with deadlines, chat with students, track activity |
| **Student** | View assigned schools, upload application documents, edit own profile, view activity history |

### Core Feature Modules

- **Authentication** — Email/password session login, role-gated redirects, password reset via Gmail SMTP
- **Student Profiles** — Comprehensive personal, passport, address, education history, work, referee data
- **School Assignments** — Staff assigns schools to students with optional course, deadline, and notes
- **Document Upload** — Students upload essays, LORs, resumes per school; tracked with review status
- **Real-time Chat** — Student↔Support team chat (WebSocket), Staff↔Staff direct messages (WebSocket)
- **Activity Timeline** — Per-student activity log with typed events (application submitted, document uploaded, etc.)
- **CRM Pipeline** — Lead intake, enquiries, follow-up scheduling

---

## 2. Tech Stack

### Frontend
- **Tailwind CSS** (CDN, `tailwindcss.com?plugins=forms,container-queries`) with custom Material Design 3 color tokens
- **Material Symbols Outlined** icon font (Google Fonts CDN)
- **Vanilla JavaScript** — no framework; client-side filtering via `querySelectorAll + classList.toggle`
- **Django templates** — all HTML pages are server-rendered `.html` files in their own folders

### Backend
- **Python 3.11+**
- **Django 5.x** — ORM, auth, sessions, template engine, admin
- **Django Channels 4.x + Daphne 4.x** — ASGI server, WebSocket real-time messaging
- **Django REST Framework 3.15+** — JWT API (separate from template views)
- **djangorestframework-simplejwt** — JWT access (15 min) + refresh (7 days) tokens
- **drf-spectacular** — OpenAPI schema auto-generation at `/api/docs/`
- **django-filter** — Query param filtering on API endpoints
- **django-cors-headers** — CORS for external frontend integration
- **whitenoise** — Static file serving in production

### Database
- **PostgreSQL 14+** in production (Railway managed Postgres)
- **SQLite** fallback for local dev when `DATABASE_URL` is not set
- **dj-database-url** — parses `DATABASE_URL` env var

### Infrastructure & Storage
- **Railway** — primary deployment platform (auto-detects Django + Postgres plugin)
- **Supabase Storage** — optional file storage for uploaded documents (bucket: `crm-uploads`)
- **Gmail SMTP** — transactional email (password reset, welcome)
- **Gunicorn** — WSGI/ASGI process manager for production via Daphne

---

## 3. Folder Structure

```
CRMcursor/
├── README.md                          # This file
├── docker-compose.yml                 # Local Docker dev environment
├── .dockerignore
├── manage.py                          # Root-level manage.py alias
│
├── backend/                           # Django project root
│   ├── manage.py
│   ├── requirements.txt               # Python dependencies
│   ├── Dockerfile                     # Container definition
│   ├── .env                           # Local secrets (never commit)
│   ├── .env.example                   # Template for env vars
│   │
│   ├── config/                        # Django project config
│   │   ├── settings.py                # All settings, env-driven
│   │   ├── urls.py                    # Root URL routing
│   │   ├── asgi.py                    # ASGI entry (HTTP + WebSocket)
│   │   └── wsgi.py                    # WSGI entry (fallback)
│   │
│   ├── templates/
│   │   └── login.html                 # Login page template
│   │
│   ├── media/                         # User-uploaded files (gitignored)
│   │   └── avatars/                   # Profile photos: user_{pk}.{ext}
│   │
│   └── apps/                          # All Django apps
│       ├── common/                    # Shared utilities
│       │   ├── pagination.py          # StandardResultsSetPagination (20/page)
│       │   └── management/commands/
│       │       └── seed_demo.py       # Demo data seeder
│       │
│       ├── users/                     # Authentication & user management
│       │   ├── models.py              # User, PasswordResetToken
│       │   ├── views.py               # JWT auth API endpoints
│       │   ├── serializers.py
│       │   ├── permissions.py         # IsAdmin, IsStaff, IsStudent
│       │   ├── urls.py
│       │   └── migrations/
│       │       ├── 0001_initial.py
│       │       └── 0002_user_avatar.py
│       │
│       ├── crm/                       # Core CRM domain models
│       │   ├── models.py              # School, Course, Lead, Student, etc.
│       │   ├── views.py               # CRM REST API views
│       │   ├── signals.py             # Auto-activity logging on model save
│       │   └── migrations/
│       │       ├── 0001_initial.py
│       │       ├── 0002_...
│       │       ├── 0003_...
│       │       └── 0004_studentassignedschool_deadline.py
│       │
│       ├── chat/                      # Real-time messaging
│       │   ├── models.py              # ChatMessage, DirectMessage
│       │   ├── consumers.py           # AsyncWebsocketConsumer
│       │   └── routing.py             # WebSocket URL patterns
│       │
│       ├── frontend/                  # Template-rendered HTML views
│       │   ├── views.py               # All view functions (session auth)
│       │   └── urls.py                # URL patterns for HTML pages
│       │
│       ├── files/                     # Supabase Storage integration
│       │   ├── models.py              # FileObject metadata
│       │   ├── admin.py
│       │   └── migrations/
│       │
│       ├── audit/                     # Activity log
│       │   ├── models.py              # ActivityLog
│       │   ├── services.py            # log() helper
│       │   └── migrations/
│       │
│       └── notifications/             # User notifications
│           ├── models.py              # Notification
│           └── migrations/
│
├── admin_dashboard/
│   └── code.html                      # Admin portal dashboard
├── employee_dashboard/
│   └── code.html                      # Staff portal dashboard
├── student_dashboard/
│   └── code.html                      # Student portal dashboard
├── student_profile_full_flow/
│   └── code.html                      # Student/Counselor — full profile editor
├── student_profile/
│   └── code.html                      # Student profile (simple view)
├── student_profile_multi_step/
│   └── code.html                      # Multi-step profile wizard (legacy)
├── counselor_students/
│   └── code.html                      # Counselor — student list + search
├── counselor_schools/
│   └── code.html                      # Counselor — assign schools to student
├── counselor_notes/
│   └── code.html                      # Counselor — chat interface
├── counselor_activity/
│   └── code.html                      # Counselor — per-student activity timeline
├── schools/
│   └── code.html                      # Student — assigned schools list
├── school_documents/
│   └── code.html                      # Student — upload documents per school
├── applications/
│   └── code.html                      # Student — applications overview
├── application_manager_enhanced/
│   └── code.html                      # Counselor — application management
├── notes_chat/
│   └── code.html                      # Student — chat with support team
├── notes_chat_enhanced/
│   └── code.html                      # Enhanced chat (legacy variant)
├── recent_activity/
│   └── code.html                      # Student — activity timeline
└── dashboard_enhanced/
    └── code.html                      # Enhanced dashboard (legacy variant)
```

---

## 4. System Architecture

### Request Lifecycle

```
Browser Request
      │
      ▼
Daphne (ASGI Server)
      │
      ├─── HTTP ──► Django Middleware Stack
      │                    │
      │             SecurityMiddleware
      │             WhiteNoiseMiddleware   (serves /static/)
      │             CorsMiddleware
      │             SessionMiddleware
      │             CsrfViewMiddleware
      │             AuthenticationMiddleware
      │                    │
      │             Router (config/urls.py)
      │                    │
      │         ┌──────────┴──────────┐
      │         │                     │
      │   /api/* (JWT REST)    /* (Session HTML)
      │   DRF ViewSets         Template Views
      │         │                     │
      │    JSON Response       render(request, "template.html", ctx)
      │
      └─── WebSocket ──► channels.auth.AuthMiddlewareStack
                              │
                         URLRouter (chat/routing.py)
                              │
                         AsyncWebsocketConsumer
                         (chat/consumers.py)
```

### Authentication Flows

**Session Auth (HTML pages)**
```
POST /login/  →  authenticate(email, password)
              →  login(request, user)   [sets session cookie]
              →  redirect based on user.role:
                   admin  → /  → admin_dashboard/code.html
                   counselor  → /  → employee_dashboard/code.html
                   student→ /  → student_dashboard/code.html

GET  /logout/ → logout(request) → redirect /login/
```

**JWT Auth (REST API)**
```
POST /api/auth/login/     → returns {access, refresh}
POST /api/auth/refresh/   → rotates refresh, returns new access
GET  /api/...             → Authorization: Bearer <access>
```

**Password Reset**
```
POST /api/auth/password-reset/request/
  → mints PasswordResetToken (30 min TTL, secrets.token_urlsafe(32))
  → sends email via Gmail SMTP with link to /api/auth/password-reset/confirm/

POST /api/auth/password-reset/confirm/
  → validates token.is_valid(), sets new password, marks token used
```

### Role-Based Access Control

```python
# In every template view:
def _counselor_guard(request):
    if not request.user.is_authenticated:
        return redirect("/login/")
    if request.user.role not in ("admin", "counselor"):
        return redirect("/")

# Role values stored in users_user.role:
#   "admin"   — full access
#   "counselor" — counselor/employee access
#   "student" — own data only
```

### WebSocket Architecture

```
Client WS connect: ws://<host>/ws/chat/<room>/
        │
        ▼
AllowedHostsOriginValidator
        │
AuthMiddlewareStack  (attaches request.user from session cookie)
        │
URLRouter  →  ChatConsumer(AsyncWebsocketConsumer)
        │
InMemoryChannelLayer  (dev only — does NOT persist across workers)
        │
Room group: "chat_<student_id>"     for student↔support messages
            "dm_<min_pk>_<max_pk>"  for counselor↔counselor DMs
```

**Important:** `InMemoryChannelLayer` is in-process only. For multi-worker production deployments, replace with `channels_redis.core.RedisChannelLayer`.

### Media File Handling

Avatar uploads bypass Django's `ImageField` (Pillow not installed). Files are saved manually:

```python
# In views.py (counselor_profile_update, my_profile_view):
avatar_file = request.FILES.get("avatar")
ext = os.path.splitext(avatar_file.name)[1].lower()
filename = f"user_{request.user.pk}{ext}"
save_path = os.path.join(settings.MEDIA_ROOT, "avatars", filename)
with open(save_path, "wb+") as dest:
    for chunk in avatar_file.chunks():
        dest.write(chunk)
user.avatar = f"/media/avatars/{filename}"
user.save(update_fields=["avatar"])
```

In DEBUG mode, `/media/` is served by Django via `urlpatterns += static(MEDIA_URL, ...)`.

---

## 5. Database Schema

> All tables use `BigAutoField` primary keys unless noted.

### `users_user`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `email` | varchar(254) | UNIQUE, NOT NULL, indexed |
| `full_name` | varchar(200) | |
| `phone` | varchar(32) | |
| `role` | varchar(20) | NOT NULL, DEFAULT `'student'`, indexed; choices: `admin`, `counselor`, `student` |
| `avatar` | varchar(500) | stores relative URL e.g. `/media/avatars/user_5.jpg` |
| `is_active` | boolean | DEFAULT true |
| `is_staff` | boolean | DEFAULT false (Django admin access) |
| `is_superuser` | boolean | DEFAULT false |
| `password` | varchar(128) | hashed |
| `last_login` | timestamptz | nullable |
| `date_joined` | timestamptz | DEFAULT now() |
| `updated_at` | timestamptz | auto_now |

### `users_passwordresettoken`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `user_id` | bigint | FK → `users_user.id` CASCADE |
| `token` | varchar(64) | UNIQUE, indexed |
| `created_at` | timestamptz | auto_now_add |
| `expires_at` | timestamptz | indexed |
| `used_at` | timestamptz | nullable |

Composite index on `(user_id, expires_at)`.

### `crm_school`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `name` | varchar(200) | NOT NULL |
| `country` | varchar(100) | NOT NULL |
| `description` | text | |
| `website` | varchar(200) | URL |
| `is_active` | boolean | DEFAULT true |
| `created_by_id` | bigint | FK → `users_user.id` SET NULL, nullable |
| `created_at` | timestamptz | auto_now_add |
| `updated_at` | timestamptz | auto_now |

Index on `(is_active, country)`. Default ordering: `['country', 'name']`.

### `crm_course`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `code` | varchar(30) | UNIQUE |
| `name` | varchar(200) | |
| `description` | text | |
| `duration_weeks` | int unsigned | DEFAULT 0 |
| `fee_amount` | decimal(12,2) | DEFAULT 0 |
| `is_active` | boolean | DEFAULT true |
| `school_id` | bigint | FK → `crm_school.id` SET NULL, nullable |
| `available_countries` | text | comma-separated |
| `intake_months` | varchar(200) | e.g. `"January, May, September"` |
| `created_at` | timestamptz | auto_now_add |
| `updated_at` | timestamptz | auto_now |

Index on `(is_active, name)`.

### `crm_lead`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `full_name` | varchar(200) | |
| `phone` | varchar(32) | indexed |
| `email` | varchar(254) | indexed |
| `source` | varchar(120) | |
| `course_interested_id` | bigint | FK → `crm_course.id` SET NULL, nullable |
| `status` | varchar(20) | indexed; choices: `new`, `contacted`, `qualified`, `lost`, `converted` |
| `assigned_to_id` | bigint | FK → `users_user.id` SET NULL, nullable |
| `notes` | text | |
| `created_by_id` | bigint | FK → `users_user.id` SET NULL, nullable |
| `created_at` | timestamptz | auto_now_add |
| `updated_at` | timestamptz | auto_now |

Indexes on `(status, created_at)`, `(phone)`, `(email)`.

### `crm_student`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `user_id` | bigint | FK → `users_user.id` SET NULL, nullable, OneToOne |
| `student_code` | varchar(40) | UNIQUE, indexed |
| `full_name` | varchar(200) | |
| `phone` | varchar(32) | |
| `email` | varchar(254) | |
| `course_id` | bigint | FK → `crm_course.id` SET NULL, nullable |
| `joined_on` | date | DEFAULT today |
| `is_active` | boolean | DEFAULT true |
| `counselor_id` | bigint | FK → `users_user.id` SET NULL, nullable |
| `poc_id` | bigint | FK → `users_user.id` SET NULL, nullable |
| `dob` | date | nullable |
| `gender` | varchar(20) | |
| `nationality` | varchar(100) | |
| `country_of_birth` | varchar(100) | |
| `native_language` | varchar(100) | |
| `passport_name` | varchar(200) | |
| `passport_number` | varchar(50) | |
| `passport_issue_location` | varchar(100) | |
| `passport_issue_date` | date | nullable |
| `passport_expiry_date` | date | nullable |
| `perm_country` | varchar(100) | |
| `perm_line_1` | varchar(200) | |
| `perm_line_2` | varchar(200) | |
| `perm_city` | varchar(100) | |
| `perm_state` | varchar(100) | |
| `perm_postcode` | varchar(20) | |
| `curr_same_as_perm` | boolean | DEFAULT false |
| `curr_country` | varchar(100) | |
| `curr_line_1` | varchar(200) | |
| `curr_line_2` | varchar(200) | |
| `curr_city` | varchar(100) | |
| `curr_state` | varchar(100) | |
| `curr_postcode` | varchar(20) | |
| `emergency_name` | varchar(200) | |
| `emergency_relationship` | varchar(100) | |
| `emergency_mobile` | varchar(32) | |
| `emergency_email` | varchar(254) | |
| `destination_countries` | text | comma-separated |
| `work_company` | varchar(200) | |
| `work_role` | varchar(200) | |
| `work_start` | date | nullable |
| `work_end` | date | nullable |
| `work_current` | boolean | DEFAULT false |
| `referee_name` | varchar(200) | |
| `referee_org` | varchar(200) | |
| `referee_phone` | varchar(32) | |
| `referee_email` | varchar(254) | |
| `referee_relationship` | varchar(100) | |
| `created_at` | timestamptz | auto_now_add |
| `updated_at` | timestamptz | auto_now |

Index on `(is_active, student_code)`.

### `crm_educationhistory`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `student_id` | bigint | FK → `crm_student.id` CASCADE |
| `institution_name` | varchar(200) | |
| `level` | varchar(100) | |
| `course_major` | varchar(200) | |
| `country` | varchar(100) | |
| `start_date` | date | nullable |
| `end_date` | date | nullable |
| `grading_type` | varchar(50) | |
| `score` | varchar(50) | |
| `order` | int unsigned | DEFAULT 0 |

Default ordering: `['order', 'start_date']`.

### `crm_studentassignedschool`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `student_id` | bigint | FK → `crm_student.id` CASCADE |
| `school_id` | bigint | FK → `crm_school.id` CASCADE |
| `course_id` | bigint | FK → `crm_course.id` SET NULL, nullable |
| `assigned_by_id` | bigint | FK → `users_user.id` SET NULL, nullable |
| `notes` | text | |
| `deadline` | date | nullable — application deadline shown to student |
| `created_at` | timestamptz | auto_now_add |

UNIQUE on `(student_id, school_id)`. Index on `(student_id)`.

### `crm_studentschooldocument`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `student_id` | bigint | FK → `crm_student.id` CASCADE |
| `school_id` | bigint | FK → `crm_school.id` CASCADE |
| `document_type` | varchar(20) | indexed; choices: `essay_1`, `essay_2`, `lor_1`, `lor_2`, `resume` |
| `file_name` | varchar(255) | |
| `file_url` | varchar(500) | relative path e.g. `/media/...` |
| `status` | varchar(20) | indexed; choices: `pending`, `uploaded`, `reviewing`, `approved` |
| `uploaded_at` | timestamptz | nullable |
| `created_at` | timestamptz | auto_now_add |
| `updated_at` | timestamptz | auto_now |

UNIQUE on `(student_id, school_id, document_type)`. Index on `(student_id, school_id)`.

### `crm_studentpreference`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `student_id` | bigint | FK → `crm_student.id` CASCADE |
| `school_id` | bigint | FK → `crm_school.id` CASCADE |
| `course_id` | bigint | FK → `crm_course.id` SET NULL, nullable |
| `preferred_country` | varchar(100) | |
| `notes` | text | |
| `created_at` | timestamptz | auto_now_add |
| `updated_at` | timestamptz | auto_now |

UNIQUE on `(student_id, school_id, course_id)`. Index on `(student_id)`.

### `crm_studentactivity`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `student_id` | bigint | FK → `crm_student.id` CASCADE |
| `activity_type` | varchar(50) | indexed; choices: `application_submitted`, `document_uploaded`, `message_received`, `preference_saved`, `profile_updated`, `status_changed`, `note_added`, `meeting_scheduled` |
| `description` | text | |
| `created_at` | timestamptz | auto_now_add, indexed |
| `created_by_id` | bigint | FK → `users_user.id` SET NULL, nullable |

Default ordering: `['-created_at']`. Index on `(student_id, created_at)`.

### `crm_enquiry`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `subject` | varchar(200) | |
| `message` | text | |
| `status` | varchar(20) | indexed; choices: `open`, `in_progress`, `resolved`, `closed` |
| `lead_id` | bigint | FK → `crm_lead.id` SET NULL, nullable |
| `student_id` | bigint | FK → `crm_student.id` SET NULL, nullable |
| `assigned_to_id` | bigint | FK → `users_user.id` SET NULL, nullable |
| `created_by_id` | bigint | FK → `users_user.id` SET NULL, nullable |
| `created_at` | timestamptz | auto_now_add |
| `updated_at` | timestamptz | auto_now |

Constraint: must have either `lead_id` or `student_id` (enforced via `clean()`). Index on `(status, created_at)`.

### `crm_followup`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `status` | varchar(20) | indexed; choices: `pending`, `done`, `missed` |
| `scheduled_at` | timestamptz | indexed |
| `completed_at` | timestamptz | nullable |
| `note` | text | |
| `lead_id` | bigint | FK → `crm_lead.id` CASCADE, nullable |
| `enquiry_id` | bigint | FK → `crm_enquiry.id` CASCADE, nullable |
| `student_id` | bigint | FK → `crm_student.id` CASCADE, nullable |
| `assigned_to_id` | bigint | FK → `users_user.id` SET NULL, nullable |
| `created_by_id` | bigint | FK → `users_user.id` SET NULL, nullable |
| `created_at` | timestamptz | auto_now_add |
| `updated_at` | timestamptz | auto_now |

Constraint: exactly one of `lead_id`, `enquiry_id`, `student_id` must be set. Index on `(status, scheduled_at)`.

### `chat_chatmessage`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `student_id` | bigint | FK → `crm_student.id` CASCADE |
| `sender_id` | bigint | FK → `users_user.id` CASCADE |
| `content` | text | |
| `created_at` | timestamptz | auto_now_add |
| `is_read` | boolean | DEFAULT false |

Default ordering: `['created_at']`. Room name: `chat_<student_id>`.

### `chat_directmessage`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `sender_id` | bigint | FK → `users_user.id` CASCADE |
| `recipient_id` | bigint | FK → `users_user.id` CASCADE |
| `content` | text | |
| `created_at` | timestamptz | auto_now_add |
| `is_read` | boolean | DEFAULT false |

Default ordering: `['created_at']`. Room name: `dm_{min(sender,recipient)}_{max(sender,recipient)}`.

### `audit_activitylog`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `actor_id` | bigint | FK → `users_user.id` SET NULL, nullable |
| `action` | varchar(120) | |
| `entity` | varchar(120) | e.g. `"Student"`, `"Lead"` |
| `entity_id` | varchar(120) | stringified PK |
| `metadata` | jsonb | DEFAULT `{}` |
| `created_at` | timestamptz | auto_now_add |

Indexes on `(action, created_at)` and `(entity, entity_id)`.

### `files_fileobject`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | bigint | PK, auto |
| `bucket` | varchar(120) | Supabase bucket name |
| `path` | varchar(512) | path within bucket |
| `public_url` | varchar(1024) | full public URL |
| `content_type` | varchar(200) | MIME type |
| `size_bytes` | bigint | DEFAULT 0 |
| `created_at` | timestamptz | auto_now_add |

### `notifications_notification` *(schema TBD)*

Exists as an empty app scaffold. Model and migrations are present but the notification feature is not yet implemented beyond the DB table creation.

---

## 6. Environment Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 14+ (or use SQLite for local dev — no setup required)
- Git

### Step 1 — Clone and create virtual environment

```powershell
cd "D:\Intelligent Education\tool\CRMcursor"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

### Step 2 — Install dependencies

```powershell
cd backend
pip install -r requirements.txt
```

### Step 3 — Configure environment

```powershell
copy .env.example .env
```

Edit `backend/.env`:

```env
DJANGO_ENV=development
DJANGO_DEBUG=1
DJANGO_SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_urlsafe(50))">
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# Leave blank to use SQLite locally
DATABASE_URL=

# Gmail SMTP (optional for dev — use console backend instead)
EMAIL_HOST_USER=your@gmail.com
EMAIL_HOST_PASSWORD=your-app-password

# Supabase (optional for dev — local file upload works without this)
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
```

To use the console email backend during development, add to `.env`:
```env
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
```
(Override in settings.py or add a dev-specific settings check.)

### Step 4 — Run migrations

```powershell
python manage.py migrate
```

Expected output includes:
```
Applying users.0001_initial... OK
Applying users.0002_user_avatar... OK
Applying crm.0001_initial... OK
...
Applying crm.0004_studentassignedschool_deadline... OK
```

### Step 5 — Create admin user

```powershell
python manage.py createsuperuser
# Enter email and password when prompted
# Role defaults to 'admin' for superusers
```

### Step 6 — Seed demo data (optional)

```powershell
python manage.py seed_demo
```

### Step 7 — Run the server

```powershell
python manage.py runserver 0.0.0.0:8000
```

The app is served at `http://localhost:8000/`.

- Login: `http://localhost:8000/login/`
- Django admin: `http://localhost:8000/admin/`
- API docs (Swagger): `http://localhost:8000/api/docs/`

### Media files in development

In DEBUG mode, Django automatically serves `MEDIA_ROOT` at `/media/`. Avatar uploads will appear at `http://localhost:8000/media/avatars/user_<pk>.<ext>`.

---

## 7. URL & API Reference

### Frontend Routes (Session Auth, returns HTML)

| Method | Path | View | Description |
|--------|------|------|-------------|
| GET/POST | `/login/` | `login_view` | Login form |
| GET | `/logout/` | `logout_view` | Clears session |
| GET | `/` | `dashboard` | Redirects by role |
| GET | `/dashboard/` | `dashboard` | Same as `/` |
| GET | `/employee-dashboard/` | `employee_dashboard` | Staff/Admin only |
| GET | `/admin-dashboard/` | `admin_dashboard_view` | Admin only |
| GET | `/student-dashboard/` | `student_dashboard` | Student view |
| GET/POST | `/my-profile/` | `my_profile_view` | Own profile + avatar upload |
| GET | `/applications/` | `applications` | Student applications list |
| GET | `/application-manager/` | `application_manager` | Staff application manager |
| GET | `/notes/` | `notes_chat` | Student chat |
| GET | `/student-profile/` | `students_list` | Counselor — student list |
| GET/POST | `/student-profile/<id>/` | `student_profile` | Counselor — edit student |
| GET | `/schools/` | `schools_view` | Student — assigned schools |
| GET/POST | `/schools/<id>/documents/` | `school_documents_view` | Student — doc upload |
| GET | `/recent-activity/` | `recent_activity_view` | Student activity feed |
| GET | `/counselor-students/` | `counselor_students_view` | Counselor — student management |
| GET/POST | `/counselor-schools/` | `counselor_schools_view` | Counselor — school assignment |
| GET | `/counselor-notes/` | `counselor_notes_view` | Counselor — chat with students |
| GET | `/counselor-activity/` | `counselor_activity_view` | Counselor — activity timeline |
| POST | `/counselor-profile-update/` | `counselor_profile_update` | Counselor — avatar/profile update |

### REST API Routes (JWT Auth, returns JSON)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/login/` | Obtain JWT `{access, refresh}` |
| POST | `/api/auth/refresh/` | Rotate refresh token |
| POST | `/api/auth/password-reset/request/` | Send reset email |
| POST | `/api/auth/password-reset/confirm/` | Apply new password |
| GET/POST | `/api/users/` | List/create users (admin only) |
| GET/PUT/DELETE | `/api/users/<id>/` | User detail |
| GET/POST | `/api/students/` | List/create students |
| GET/PUT/DELETE | `/api/students/<id>/` | Student detail |
| GET/POST | `/api/schools/` | List/create schools |
| GET/PUT/DELETE | `/api/schools/<id>/` | School detail |
| GET/POST | `/api/courses/` | List/create courses |
| GET/PUT/DELETE | `/api/courses/<id>/` | Course detail |
| GET/POST | `/api/leads/` | List/create leads |
| GET/PUT/DELETE | `/api/leads/<id>/` | Lead detail |
| GET/POST | `/api/enquiries/` | List/create enquiries |
| GET/POST | `/api/followups/` | List/create follow-ups |
| GET/POST | `/api/files/` | File metadata list |
| GET/POST | `/api/activity-logs/` | Audit log list (admin only) |
| GET | `/api/schema/` | OpenAPI YAML schema |
| GET | `/api/docs/` | Swagger UI |

### WebSocket Endpoints

| Path | Consumer | Room | Usage |
|------|----------|------|-------|
| `ws://<host>/ws/chat/<room>/` | `ChatConsumer` | `chat_<student_id>` | Student↔Support |
| `ws://<host>/ws/chat/<room>/` | `ChatConsumer` | `dm_<lo>_<hi>` | Staff↔Staff DM |

---

## 8. Deployment Reference

### Railway (Primary)

1. Create Railway project at `railway.app`
2. Add **PostgreSQL** plugin — Railway injects `DATABASE_URL` automatically
3. Set environment variables in Railway dashboard:

```
DJANGO_ENV=production
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=<long random string>
DJANGO_ALLOWED_HOSTS=your-railway-app.railway.app,yourdomain.com
DJANGO_CORS_ALLOWED_ORIGINS=https://yourdomain.com
DATABASE_URL=<auto-injected by Railway Postgres plugin>
EMAIL_HOST_USER=your@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=Intelligent Education CRM <your@gmail.com>
FRONTEND_BASE_URL=https://your-railway-app.railway.app
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_STORAGE_BUCKET=crm-uploads
SUPABASE_PUBLIC_URL_BASE=https://your-project.supabase.co/storage/v1/object/public
```

4. Set Railway **Start Command**:
```
cd backend && daphne -b 0.0.0.0 -p $PORT config.asgi:application
```

5. Set Railway **Deploy Command** (runs before start on each deploy):
```
cd backend && python manage.py migrate --noinput && python manage.py collectstatic --noinput
```

6. Push to connected GitHub repo to trigger deployment.

### Supabase Storage Setup

1. Create a Supabase project
2. Go to Storage → Create bucket named `crm-uploads`
3. Set bucket to **Public** (for direct URL access)
4. Copy **Service Role Key** from Settings → API
5. Set `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_PUBLIC_URL_BASE` in Railway env vars

### Custom Domain

In Railway: Settings → Domains → Add custom domain → Set CNAME in DNS.
HTTPS is provisioned automatically via Let's Encrypt.

### Production Checklist

- [ ] `DJANGO_DEBUG=0`
- [ ] `DJANGO_SECRET_KEY` is long (50+ chars), random, not the dev default
- [ ] `DJANGO_ALLOWED_HOSTS` includes your domain
- [ ] `DATABASE_URL` points to production Postgres
- [ ] `SESSION_COOKIE_SECURE=True` (automatic when `DEBUG=False`)
- [ ] `CSRF_COOKIE_SECURE=True` (automatic when `DEBUG=False`)
- [ ] Static files collected (`collectstatic`)
- [ ] Media files: if using Railway ephemeral filesystem, mount a persistent volume at `backend/media/` or migrate avatars to Supabase Storage
- [ ] Email SMTP credentials set and tested
- [ ] For multi-worker deployments: replace `InMemoryChannelLayer` with `RedisChannelLayer`

---

## 9. Development Workflow

### Adding a New Template Page

1. Create folder `new_page/` with `code.html`
2. Add view function to `backend/apps/frontend/views.py`
3. Add URL pattern to `backend/apps/frontend/urls.py`
4. Templates are resolved via `TEMPLATES[0]['DIRS'] = [BASE_DIR / "templates", BASE_DIR.parent]` — the project root is a template dir, so `new_page/code.html` is found as-is

### Sidebar + Navbar Pattern

All pages follow the same layout:

```html
<!-- Fixed sidebar: w-[260px], bg-primary -->
<aside class="fixed left-0 top-0 h-full w-[260px] bg-primary ...">

<!-- Fixed top navbar: left-[260px], h-[72px] -->
<header class="fixed top-0 right-0 h-[72px] left-[260px] ...">

<!-- Scrollable main content -->
<main class="ml-[260px] pt-[72px] min-h-screen p-gutter">
```

Active nav item uses `bg-on-primary-fixed-variant scale-95` classes. All other nav items use `hover:bg-on-primary-fixed-variant/50`.

### Adding a Database Field

```powershell
# 1. Edit the model in backend/apps/<app>/models.py
# 2. Create migration
python manage.py makemigrations <app> --name <descriptive_name>
# 3. Apply
python manage.py migrate
# 4. Update views.py to pass/receive the field
# 5. Update relevant code.html templates
```

### Running Migrations

```powershell
cd backend
python manage.py showmigrations          # see status
python manage.py migrate                  # apply all pending
python manage.py migrate crm 0003        # roll back to specific migration
```

### Django Shell (debugging)

```powershell
python manage.py shell
>>> from apps.crm.models import Student
>>> Student.objects.all()
```

### Client-Side Filtering Pattern

All search/filter inputs use vanilla JS without page reloads:

```javascript
// Pattern used across admin_dashboard, counselor_students, counselor_activity, etc.
function filterRows(q) {
  q = q.toLowerCase();
  document.querySelectorAll(".row-class").forEach(el => {
    el.classList.toggle("hidden", q && !el.textContent.toLowerCase().includes(q));
  });
}
```

### Code Style Conventions

- Python: no type annotations required outside models/views; use `from __future__ import annotations` at top of files that do use them
- Templates: Tailwind utility classes only, no custom CSS unless unavoidable
- No JavaScript frameworks — keep everything in vanilla JS within `<script>` tags at end of `<body>`
- Form submissions: standard HTML POST with Django CSRF token `{% csrf_token %}`
- Avatar/file forms require `enctype="multipart/form-data"` on the `<form>` tag

---

## 10. Roadmap & Pending Tasks

### In Progress / Immediate

- [ ] **Notifications app** — `apps/notifications/` is scaffolded with a model but has no views, signals, or UI. Implement: create notification on school assignment, document status change, new chat message. Display in top navbar bell icon.

### High Priority

- [ ] **WebSocket production readiness** — Replace `InMemoryChannelLayer` in `settings.py` with `channels_redis.core.RedisChannelLayer`. Add Redis URL to Railway env vars. `InMemoryChannelLayer` does not work across multiple workers or dyno restarts.

- [ ] **Media persistence on Railway** — Railway's filesystem is ephemeral. Either mount a Railway persistent volume at `backend/media/` or move avatar uploads to Supabase Storage (preferred). Currently avatars are lost on each Railway deploy.

- [ ] **Counselor-to-counselor DM list** — `chat_directmessage` table and WebSocket consumer exist, but there is no UI page for initiating counselor DMs. Add a counselor DM inbox page at `/counselor-dm/`.

- [ ] **Email verification on registration** — New user accounts are created by admin only (no public signup). However, student users created via admin can't self-verify their email. Add email confirmation step.

### Medium Priority

- [ ] **Pagination on student list** — `counselor_students_view` loads all students. Add DB-level pagination for agencies with 100+ students.

- [ ] **Application status tracking** — `applications/code.html` shows a static UI. Wire it to `crm_studentschooldocument` statuses. Add admin/counselor ability to change `DocumentStatus` from `uploaded` → `reviewing` → `approved`.

- [ ] **Lead-to-Student conversion flow** — `Lead` model has `status=converted` but there's no UI to convert a lead into a `Student` record. Build this conversion form in the admin or counselor portal.

- [ ] **Follow-up reminders** — `crm_followup` records exist but nothing sends reminders. Add a management command or Celery task to email assigned counselors about pending follow-ups.

- [ ] **Admin user management UI** — Admins create/edit counselor and student users via Django's built-in `/admin/` panel. A proper in-app UI at `/admin-dashboard/` for user CRUD is needed.

- [ ] **Education history in profile** — `crm_educationhistory` table exists but the student profile form (`student_profile_full_flow/code.html`) does not render/save education history rows. Implement a dynamic add/remove JS form section.

### Low Priority / Nice to Have

- [ ] **Dark mode** — Tailwind config has `darkMode: "class"`. Add a theme toggle button that sets `<html class="dark">`.

- [ ] **Activity log auto-creation** — `crm_signals.py` has signal stubs but actual `StudentActivity` creation on model saves is not fully implemented. Ensure signals fire for: profile updates, document uploads, school assignments.

- [ ] **Redis cache** — Add Redis-backed Django cache (`django-redis`) for expensive queries (student count aggregates, school lists).

- [ ] **File type validation** — Avatar uploads accept any extension client-side (`accept="image/*"`) but there's no server-side MIME type check. Add extension allowlist in the view.

- [ ] **Docker Compose dev environment** — `docker-compose.yml` and `Dockerfile` exist but have not been tested end-to-end with Channels/Daphne. Verify and document Docker dev workflow.

- [ ] **Test suite** — `apps/crm/tests.py` exists but is empty. Add model tests, view tests for the key auth flows, and WebSocket consumer tests.

### Known Limitations

| Limitation | Impact | Fix |
|-----------|--------|-----|
| `InMemoryChannelLayer` | Chat doesn't work across workers; lost on restart | Switch to Redis channel layer |
| Avatar files stored on Railway ephemeral FS | Lost on redeploy | Mount persistent volume or use Supabase Storage |
| No Pillow — avatars are any file format | Potential non-image file stored as avatar | Add server-side extension validation |
| SQLite fallback for local dev | Not supported by some Django Channels features | Always use Postgres in dev if using WebSockets |
| `seed_demo.py` scope unknown | May create incomplete demo state | Review and test seeder |

---

*Last updated: 2026-05-07*
# Intelligent-Education-CRM
