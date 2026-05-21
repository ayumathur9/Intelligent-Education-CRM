# Architecture Refactor Plan
> Defines the target architecture for the Intelligent Education CRM.
> Changes are phased to avoid disrupting existing functionality.

---

## Current Architecture

```
backend/
├── apps/
│   ├── audit/           # ActivityLog model + views
│   ├── chat/            # WebSocket messaging consumers
│   ├── common/          # Shared: email, middleware, pagination, supabase_client
│   ├── crm/             # Core domain: Student, School, Lead, etc.
│   ├── files/           # File upload endpoint
│   ├── frontend/        # Session-auth HTML views (Django-rendered)
│   ├── notifications/   # Incomplete notification system
│   └── users/           # Auth, JWT, roles, password reset
└── config/
    ├── settings.py      # Single settings file (dev + prod logic mixed)
    ├── urls.py
    ├── asgi.py
    └── wsgi.py
```

### Current Problems
- Business logic lives directly in views (hard to test, hard to reuse)
- No service layer — views call models directly
- No selector layer — complex queries scattered across views
- No tasks layer — email is synchronous in request cycle
- Single `settings.py` mixes dev/prod concerns
- No test suite

---

## Target Architecture

```
backend/
├── apps/
│   ├── audit/
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── views.py
│   │   └── urls.py
│   ├── chat/
│   │   └── consumers.py
│   ├── common/
│   │   ├── email_service.py
│   │   ├── middleware.py
│   │   ├── pagination.py
│   │   ├── supabase_client.py
│   │   ├── storage.py          ← NEW: Supabase storage helpers
│   │   └── health.py           ← NEW: health check view
│   ├── crm/
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── views.py            ← Thin: delegates to services/selectors
│   │   ├── urls.py
│   │   ├── filters.py
│   │   ├── services/           ← NEW: business logic layer
│   │   │   ├── __init__.py
│   │   │   ├── student_service.py
│   │   │   ├── school_service.py
│   │   │   └── lead_service.py
│   │   ├── selectors/          ← NEW: complex query layer
│   │   │   ├── __init__.py
│   │   │   └── student_selectors.py
│   │   └── signals.py
│   ├── files/
│   │   ├── views.py
│   │   └── validators.py       ← NEW: file validation logic extracted
│   ├── frontend/
│   │   └── views.py
│   ├── notifications/
│   │   ├── models.py
│   │   ├── service.py          ← Wire to CRM events via signals
│   │   └── consumers.py
│   └── users/
│       ├── models.py
│       ├── serializers.py
│       ├── views.py
│       ├── urls.py
│       ├── throttles.py
│       └── permissions.py
├── tests/                      ← NEW: test suite
│   ├── conftest.py
│   ├── auth/
│   ├── crm/
│   ├── security/
│   ├── uploads/
│   └── api/
└── config/
    ├── settings.py
    ├── urls.py
    ├── asgi.py
    └── wsgi.py
```

---

## Service Layer Pattern

### What goes in `services/`
- Operations that span multiple models
- Business rules and state machine transitions
- Side effects (notifications, audit logs, emails)
- Any logic that must be tested independently of HTTP

### What stays in `views.py`
- HTTP parsing (request.data, request.user)
- Calling the appropriate service
- Returning serialized response

### Example: School Assignment Service

```python
# apps/crm/services/school_service.py

from apps.crm.models import Student, School, StudentAssignedSchool
from apps.audit.models import ActivityLog
from apps.notifications.service import create_notification


def assign_school_to_student(
    student: Student,
    school: School,
    assigned_by,
    course=None,
    notes: str = "",
    deadline=None,
) -> StudentAssignedSchool:
    """
    Assign a school to a student.
    Creates audit log and notification as side effects.
    Raises ValueError if already assigned.
    """
    if StudentAssignedSchool.objects.filter(student=student, school=school).exists():
        raise ValueError(f"{student} is already assigned to {school}")

    assignment = StudentAssignedSchool.objects.create(
        student=student,
        school=school,
        course=course,
        assigned_by=assigned_by,
        notes=notes,
        deadline=deadline,
    )

    ActivityLog.objects.create(
        actor=assigned_by,
        action="school_assigned",
        entity="Student",
        entity_id=str(student.pk),
        metadata={"school_id": school.pk, "school_name": school.name},
    )

    if student.user:
        create_notification(
            recipient=student.user,
            actor=assigned_by,
            verb="assigned you to",
            target=school,
        )

    return assignment
```

---

## Selector Layer Pattern

### What goes in `selectors/`
- Complex queryset building
- Annotated/aggregated queries
- Reusable filtering logic

```python
# apps/crm/selectors/student_selectors.py

from django.db.models import QuerySet
from apps.crm.models import Student
from apps.users.models import User


def get_students_for_user(user: User) -> QuerySet:
    """Return students visible to the given user based on their role."""
    base_qs = Student.active.select_related(
        "user", "counselor", "course"
    ).prefetch_related(
        "assigned_schools__school"
    )

    if user.role == "student":
        return base_qs.filter(user=user)
    if user.role == "counselor":
        return base_qs.filter(counselor=user)
    # admin, editor see all
    return base_qs
```

---

## Settings Architecture (Current vs Target)

### Current: Single settings.py
All dev/prod logic is mixed with `if not DEBUG:` branching.

### Target: Environment-driven single file (preserved)
The current pattern is acceptable for this scale. Keep it, but:
1. Add startup validation block (CRIT-001, CRIT-004, HIGH-007)
2. Add clear section comments
3. Move any remaining hardcoded defaults to env vars

---

## Migration Strategy for Architecture Changes

1. **Additive only** — add `services/` and `selectors/` without removing anything
2. **Refactor views incrementally** — move one endpoint at a time
3. **Keep backward compatibility** — no URL changes without versioning
4. **Test before refactor** — write tests first, then move logic

---

## Testing Architecture

### Framework
- `pytest-django` — test runner
- `factory_boy` — test fixtures
- `DRF APIClient` — API testing
- `coverage.py` — coverage measurement

### Required Coverage Targets

| Module | Target Coverage |
|---|---|
| `apps/users/` | 90% |
| `apps/crm/` | 80% |
| `apps/files/` | 85% |
| `apps/common/` | 75% |
| `apps/audit/` | 70% |
| **Overall** | **80%** |

### Test File Structure

```
tests/
├── conftest.py                 # Shared fixtures (users, clients, factories)
├── auth/
│   ├── test_login.py
│   ├── test_logout.py
│   ├── test_refresh.py
│   ├── test_password_reset.py
│   └── test_registration.py
├── crm/
│   ├── test_students.py
│   ├── test_schools.py
│   └── test_leads.py
├── security/
│   ├── test_rate_limiting.py
│   ├── test_permissions.py
│   └── test_idor.py
├── uploads/
│   ├── test_file_upload.py
│   └── test_file_validation.py
└── api/
    ├── test_health.py
    └── test_pagination.py
```
