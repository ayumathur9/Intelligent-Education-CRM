# User Roles & Permissions

This document describes the four user roles in the Intelligent Education CRM, what each role can access, and how they are implemented.

---

## Roles Overview

| Role | Dashboard | Scope | Primary Purpose |
|------|-----------|-------|-----------------|
| **Admin** | Admin Dashboard | All students, all data | Full system management |
| **Staff (Counselor)** | Employee Dashboard | Assigned students only | Student guidance & school assignment |
| **Editor** | Employee Dashboard | All students | Document & application management |
| **Student** | Student Dashboard | Own profile only | Self-service profile & school applications |

---

## Admin

**Login redirect:** `/` → `admin_dashboard/code.html`

### What Admins Can Do
- View all students (active count, full list)
- Manage all schools — create, edit, delete (`/admin-schools/`)
- Assign counselors, POCs, and editors to any student
- Assign schools and courses to any student
- View all student profiles and edit them
- Access all messaging threads (all students, all counselors)
- View activity logs for any student
- Create counselor, editor, and student accounts via the API

### Pages Available
| Page | URL |
|------|-----|
| Admin Dashboard | `/` |
| Student List & Assignment | `/student-profile/` |
| Student Profile (detail) | `/student-profile/<id>/` |
| Student Application | `/student-application/<id>/` |
| School Management | `/admin-schools/` |
| Counselor Schools | `/counselor-schools/` |
| Counselor Students | `/counselor-students/` |
| Counselor Notes | `/counselor-notes/` |
| Counselor Activity | `/counselor-activity/` |

### Implementation Notes
- `request.user.role == "admin"` in `dashboard()` → renders `admin_dashboard/code.html`
- Admin sees all student threads in notes (not filtered by assignment)
- API permission class: `IsAdmin`

---

## Staff (Counselor)

**Login redirect:** `/` → `employee_dashboard/code.html`

**Model field:** `Student.counselor` or `Student.poc` — a student is "assigned" to a counselor when either field points to them.

### What Counselors Can Do
- View their assigned students (where `Student.counselor = me` or `Student.poc = me`)
- View the full student list (read access)
- Assign schools to any student
- Edit any student's profile
- View and upload documents for any student's school applications
- Message (chat with) their assigned students
- Direct-message other counselors, editors, and admins
- View activity logs for any student

### What Counselors Cannot Do
- Access admin school management (`/admin-schools/`)
- View messaging threads for students not assigned to them

### Pages Available
| Page | URL |
|------|-----|
| Employee Dashboard | `/` and `/employee-dashboard/` |
| Student List | `/counselor-students/` |
| School Assignment | `/counselor-schools/` |
| Student Profile | `/student-profile/<id>/` |
| Student Application | `/student-application/<id>/` |
| School Documents | `/counselor-schools/<sid>/schools/<scid>/documents/` |
| Notes & Messaging | `/counselor-notes/` |
| Activity Log | `/counselor-activity/` |

### Implementation Notes
- `request.user.role == "counselor"` in `dashboard()` → calls `employee_dashboard()`
- "My students" count on dashboard = students where `counselor = me OR poc = me`
- `_counselor_guard()` allows `counselor` role
- Ownership check on documents: `student.counselor_id == me OR student.poc_id == me`
- API permission class: `IsCounselorOrAdmin`

---

## Editor

**Login redirect:** `/` → `employee_dashboard/code.html`

**Model field:** `Student.editor` — a student is "assigned" to an editor when this field points to them.

### What Editors Can Do
- View all students (full student list)
- View and edit any student's profile
- View and upload documents for any student's school applications
- View and manage any student's application status
- Message (chat with) any student
- Direct-message other counselors, editors, and admins
- View activity logs for any student

### What Editors Cannot Do
- Assign or remove schools from students (`/counselor-schools/` is blocked)
- Access admin school management (`/admin-schools/`)
- Assign counselors/POCs/editors to students (counselor assignment)

### Pages Available
| Page | URL |
|------|-----|
| Employee Dashboard | `/` and `/employee-dashboard/` |
| Student List | `/counselor-students/` |
| School Assignment | `/counselor-schools/` |
| Student Profile | `/student-profile/<id>/` |
| Student Application | `/student-application/<id>/` |
| School Documents | `/counselor-schools/<sid>/schools/<scid>/documents/` |
| Notes & Messaging | `/counselor-notes/` |
| Activity Log | `/counselor-activity/` |

### Key Differences from Counselor
| Feature | Counselor | Editor |
|---------|-----------|--------|
| "My students" on dashboard | Assigned students (counselor/poc) | Students where `editor = me` |
| Document access | All students | All students |
| School assignment | Yes (`/counselor-schools/`) | No (blocked) |
| Messaging threads | Own assigned students only | All students |
| DM list | Admin + Staff + Editors | Admin + Staff + Editors |

### Implementation Notes
- `request.user.role in ("counselor", "editor")` in `dashboard()` → calls `employee_dashboard()`
- "My students" count on editor dashboard = students where `editor = me`
- `_counselor_guard()` allows `editor` role
- Document ownership check skips for editors (same access as admin)
- Notes: `is_editor` flag passed to template; editors see all threads
- API permission classes: `IsEditorOrAdmin`, `IsCounselorEditorOrAdmin`

---

## Student

**Login redirect:** `/` → `student_dashboard/code.html`

**Model:** `Student` — linked to `User` via `Student.user` (OneToOne, matched by email on first login).

### What Students Can Do
- View their own dashboard (counselor info, school count, unread messages)
- Edit their own profile (`/my-profile/`)
- View their assigned schools and deadlines (`/schools/`)
- Upload documents for each assigned school (`/schools/<id>/documents/`)
- Chat with their assigned counselor (`/notes/`)
- View their own activity log (`/recent-activity/`)

### What Students Cannot Do
- Access any counselor or admin pages
- View other students' profiles or data
- Assign schools to themselves (schools are assigned by counselors)

### Pages Available
| Page | URL |
|------|-----|
| Student Dashboard | `/` and `/student-dashboard/` |
| My Profile | `/my-profile/` |
| My Schools | `/schools/` |
| School Documents | `/schools/<id>/documents/` |
| Notes / Chat | `/notes/` |
| Recent Activity | `/recent-activity/` |
| Applications | `/applications/` (redirects to `/schools/`) |

### Implementation Notes
- `request.user.role == "student"` (default fallback) in `dashboard()` → calls `student_dashboard()`
- Auto-linked to `Student` record by email on first login via `_get_student_for_user()`
- All student views are scoped to their own `Student` record only
- API permission class: authenticated user with `role == "student"` (no special class needed)

---

## Role Assignment

Roles are set on the `User` model (`User.role` field, `TextChoices`). They can be changed:

- **Via Django Admin** (`/django-admin/`) — superuser only
- **Via the API** (`/api/auth/register/`) — only admins can create admin/counselor roles; all others default to `student`

New users registered through the public API always get `role = "student"` by default. An admin must manually promote them to `counselor` or `editor`.

---

## Permission Classes (REST API)

| Class | Allowed Roles |
|-------|--------------|
| `IsAdmin` | admin |
| `IsCounselorOrAdmin` | admin, counselor |
| `IsEditorOrAdmin` | admin, editor |
| `IsCounselorEditorOrAdmin` | admin, counselor, editor |

Defined in `backend/apps/users/permissions.py`.

---

## Quick Reference: Role Check Locations

| File | Location | Check |
|------|----------|-------|
| `frontend/views.py` | `dashboard()` | Routes to correct dashboard per role |
| `frontend/views.py` | `_counselor_guard()` | Gate for all counselor-facing pages |
| `frontend/views.py` | `employee_dashboard()` | Allows admin, counselor, editor |
| `frontend/views.py` | `students_list()` | Allows admin, counselor, editor |
| `frontend/views.py` | `student_profile()` | Allows admin, counselor, editor |
| `frontend/views.py` | `student_application_view()` | Allows admin, counselor, editor |
| `frontend/views.py` | `counselor_schools_view()` | Admin + counselor only; editors blocked |
| `frontend/views.py` | `counselor_school_documents_view()` | Admin, counselor, editor all see all students |
| `frontend/views.py` | `counselor_notes_view()` | Staff scoped to assigned; admin+editor see all threads |
| `users/permissions.py` | Permission classes | DRF API-level role enforcement |
