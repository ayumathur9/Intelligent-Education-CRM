import logging
import mimetypes
import uuid
from pathlib import Path

from django.conf import settings as django_settings
from django.contrib import messages as django_messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.crm.models import (
    Course, DocumentCategory, EducationHistory,
    Lead, PriorityItemDismissal, Reference, School, Student, StudentActivity,
    StudentAssignedSchool, StudentPreference, StudentProfileDocument,
    StudentSchoolDocument, WorkExperience,
)

_LOGIN_URL = "/login/"
_logger = logging.getLogger(__name__)


def _upload_to_local_storage(file_obj, folder: str, filename: str) -> str:
    """
    Save *file_obj* to the local filesystem under MEDIA_ROOT/{folder}/{filename}.
    Returns the public media URL of the stored file.
    In production, ensure MEDIA_ROOT is on a persistent volume.
    """
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage
    file_bytes = file_obj.read()
    path = f"{folder}/{filename}"
    if default_storage.exists(path):
        default_storage.delete(path)
    default_storage.save(path, ContentFile(file_bytes))
    return f"{django_settings.MEDIA_URL}{path}"

_STUDENT_SIDEBAR_ITEMS = [
    ("dashboard", "/", "Dashboard"),
    ("person", "/my-profile/", "My Profile"),
    ("school", "/schools/", "Schools"),
    ("description", "/applications/", "Applications"),
    ("chat", "/notes/", "Notes & Chat"),
    ("history", "/recent-activity/", "Recent Activity"),
]


def _student_names(count=3):
    fallbacks = ["Alex Johnson", "Maria Smith", "James Brown"]
    qs = list(Student.objects.filter(is_active=True).values_list("full_name", flat=True)[:count])
    return {f"name_{i+1}": qs[i] if i < len(qs) else fallbacks[i] for i in range(count)}


def _get_student_for_user(user):
    qs = Student.objects.select_related("counselor", "poc", "course")
    student = qs.filter(user=user).first()
    if student:
        return student
    # Fallback: match by email (case-insensitive) and auto-link
    if user.email:
        student = qs.filter(email__iexact=user.email).first()
        if student:
            _logger.info("Auto-linking student %s (pk=%s) to user %s", student.full_name, student.pk, user.email)
            student.user = user
            student.save(update_fields=["user"])
            return student
    _logger.warning(
        "No student found for user pk=%s email=%s. Students with no user link: %s",
        user.pk, user.email,
        list(qs.filter(user__isnull=True).values_list("email", "full_name")[:10]),
    )
    return None


def _student_ctx(s: Student | None) -> dict:
    """Flatten all Student profile fields into a template-friendly dict."""
    if s is None:
        return {k: "" for k in [
            "first_name", "last_name", "email", "mobile", "dob", "gender",
            "nationality", "country_of_birth", "native_language",
            "passport_name", "passport_number", "passport_issue_location",
            "passport_issue_date", "passport_expiry_date",
            "perm_country", "perm_line_1", "perm_line_2", "perm_city", "perm_state", "perm_postcode",
            "curr_same_as_perm", "curr_country", "curr_line_1", "curr_line_2",
            "curr_city", "curr_state", "curr_postcode",
            "father_name", "father_phone", "father_email", "father_dob", "father_education", "father_profession", "father_company", "father_position", "father_annual_income",
            "mother_name", "mother_phone", "mother_email", "mother_dob", "mother_education", "mother_profession", "mother_company", "mother_position", "mother_annual_income",
            "emergency_name", "emergency_relationship", "emergency_mobile", "emergency_email",
            "destination_countries",
        ]}
    parts = s.full_name.split(" ", 1)
    return {
        "first_name": parts[0],
        "last_name": parts[1] if len(parts) > 1 else "",
        "email": s.email,
        "mobile": s.phone,
        "dob": s.dob,
        "gender": s.gender,
        "nationality": s.nationality,
        "country_of_birth": s.country_of_birth,
        "native_language": s.native_language,
        "passport_name": s.passport_name,
        "passport_number": s.passport_number,
        "passport_issue_location": s.passport_issue_location,
        "passport_issue_date": s.passport_issue_date,
        "passport_expiry_date": s.passport_expiry_date,
        "perm_country": s.perm_country,
        "perm_line_1": s.perm_line_1,
        "perm_line_2": s.perm_line_2,
        "perm_city": s.perm_city,
        "perm_state": s.perm_state,
        "perm_postcode": s.perm_postcode,
        "curr_same_as_perm": s.curr_same_as_perm,
        "curr_country": s.curr_country,
        "curr_line_1": s.curr_line_1,
        "curr_line_2": s.curr_line_2,
        "curr_city": s.curr_city,
        "curr_state": s.curr_state,
        "curr_postcode": s.curr_postcode,
        "father_name": s.father_name,
        "father_phone": s.father_phone,
        "father_email": s.father_email,
        "father_dob": s.father_dob,
        "father_education": s.father_education,
        "father_profession": s.father_profession,
        "father_company": s.father_company,
        "father_position": s.father_position,
        "father_annual_income": s.father_annual_income,
        "mother_name": s.mother_name,
        "mother_phone": s.mother_phone,
        "mother_email": s.mother_email,
        "mother_dob": s.mother_dob,
        "mother_education": s.mother_education,
        "mother_profession": s.mother_profession,
        "mother_company": s.mother_company,
        "mother_position": s.mother_position,
        "mother_annual_income": s.mother_annual_income,
        "emergency_name": s.emergency_name,
        "emergency_relationship": s.emergency_relationship,
        "emergency_mobile": s.emergency_mobile,
        "emergency_email": s.emergency_email,
        "destination_countries": s.destination_countries,
    }


def _save_student_profile(student: Student, post: dict) -> None:
    """Apply all POST fields onto the Student instance and save."""

    def _d(key):
        v = post.get(key, "").strip()
        return v if v else None

    parts_first = post.get("first_name", "").strip()
    parts_last = post.get("last_name", "").strip()
    full_name = f"{parts_first} {parts_last}".strip()
    if full_name:
        student.full_name = full_name
    if post.get("email"):
        student.email = post["email"].strip()
    if post.get("mobile"):
        student.phone = post["mobile"].strip()

    for field in [
        "gender", "nationality", "country_of_birth", "native_language",
        "passport_name", "passport_number", "passport_issue_location",
        "perm_country", "perm_line_1", "perm_line_2", "perm_city", "perm_state", "perm_postcode",
        "curr_country", "curr_line_1", "curr_line_2", "curr_city", "curr_state", "curr_postcode",
        "father_name", "father_phone", "father_email", "father_education", "father_profession", "father_company", "father_position", "father_annual_income",
        "mother_name", "mother_phone", "mother_email", "mother_education", "mother_profession", "mother_company", "mother_position", "mother_annual_income",
        "emergency_name", "emergency_relationship", "emergency_mobile", "emergency_email",
        "destination_countries",
    ]:
        setattr(student, field, post.get(field, "").strip())

    student.dob = _d("dob")
    student.father_dob = _d("father_dob")
    student.mother_dob = _d("mother_dob")
    student.passport_issue_date = _d("passport_issue_date")
    student.passport_expiry_date = _d("passport_expiry_date")
    student.curr_same_as_perm = bool(post.get("same_as_permanent"))
    student.save()


def _profile_completeness(s: Student) -> int:
    """Return an integer 0-100 representing profile completeness."""
    fields = [
        s.email, s.phone, s.dob, s.gender, s.nationality,
        s.passport_number, s.passport_expiry_date,
        s.perm_country, s.perm_city,
        s.emergency_name, s.emergency_mobile,
    ]
    return int(sum(bool(f) for f in fields) / len(fields) * 100)


# ─── Priority list ───────────────────────────────────────────────────────────

def _get_priority_items(user, student_ids: list) -> dict:
    """Return red/yellow/green priority item lists for the given student scope."""
    from datetime import timedelta, date as _date

    dismissed_doc_ids = set(
        PriorityItemDismissal.objects.filter(user=user, item_type="document")
        .values_list("item_id", flat=True)
    )
    dismissed_deadline_ids = set(
        PriorityItemDismissal.objects.filter(user=user, item_type="deadline")
        .values_list("item_id", flat=True)
    )

    now = timezone.now()
    today = now.date()
    red, yellow, green = [], [], []

    # Document-based items (exclude soft-deleted records)
    docs = (
        StudentSchoolDocument.objects
        .filter(student_id__in=student_ids, deleted_at__isnull=True)
        .exclude(id__in=dismissed_doc_ids)
        .select_related("student", "school")
        .order_by("-uploaded_at")
    )
    for doc in docs:
        age = now - doc.uploaded_at
        item = {
            "type": "document",
            "item_id": doc.pk,
            "title": f"{doc.student.full_name} uploaded {doc.get_category_display()}",
            "subtitle": f"for {doc.school.name}",
            "student_pk": doc.student.pk,
            "icon": "upload_file",
        }
        if age < timedelta(hours=24):
            green.append(item)
        elif age < timedelta(hours=48):
            yellow.append(item)
        else:
            red.append(item)

    # Deadline-based items (StudentAssignedSchool with a deadline set)
    assignments = (
        StudentAssignedSchool.objects
        .filter(student_id__in=student_ids, deadline__isnull=False)
        .exclude(id__in=dismissed_deadline_ids)
        .select_related("student", "school")
        .order_by("deadline")
    )
    for a in assignments:
        days_left = (a.deadline - today).days
        if days_left < 0:
            continue
        item = {
            "type": "deadline",
            "item_id": a.pk,
            "title": f"{a.student.full_name} — deadline approaching",
            "subtitle": f"{a.school.name} · {days_left} day{'s' if days_left != 1 else ''} left ({a.deadline})",
            "student_pk": a.student.pk,
            "icon": "event_upcoming",
        }
        if days_left <= 10:
            red.append(item)
        elif days_left <= 20:
            yellow.append(item)

    return {"red_items": red, "yellow_items": yellow, "green_items": green}


# ─── Auth ────────────────────────────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated:
        return redirect("/")
    error = None
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=email, password=password)
        if user is not None:
            login(request, user)
            return redirect(request.POST.get("next") or request.GET.get("next") or "/")
        error = "Invalid email or password."
    return render(request, "login.html", {"error": error, "next": request.GET.get("next", "")})


def logout_view(request):
    logout(request)
    return redirect("/login/")


# ─── Dashboard (role-based) ───────────────────────────────────────────────────

@login_required(login_url=_LOGIN_URL)
def dashboard(request):
    role = request.user.role
    if role == "admin":
        from apps.chat.models import ChatMessage
        from apps.notifications.models import Notification as _Notif
        from apps.users.models import User as _User
        # INFRA-003: use cached aggregate helpers to reduce DB round-trips.
        from apps.crm.services.cache_service import (
            get_student_counts, get_lead_counts,
            get_active_course_count, get_active_schools,
        )
        student_counts = get_student_counts()
        lead_counts = get_lead_counts()
        my_students = Student.objects.filter(
            Q(counselor=request.user) | Q(poc=request.user), is_active=True
        ).select_related("course", "counselor", "poc", "user").order_by("full_name")
        all_students = Student.objects.filter(is_active=True).select_related("course", "counselor", "poc", "user").order_by("full_name")
        counselor_users = _User.objects.filter(role__in=("admin", "counselor", "editor"), is_active=True).order_by("role", "full_name")
        all_student_ids = list(all_students.values_list("pk", flat=True))
        context = {
            "student": _student_names(),
            "total_students": student_counts["total"],
            "active_students": student_counts["active"],
            "active_employees": counselor_users.count(),
            "total_leads": lead_counts["total"],
            "total_courses": get_active_course_count(),
            "pending_leads": lead_counts["pending"],
            "unread_messages_count": ChatMessage.objects.filter(is_read=False).exclude(sender=request.user).count(),
            "notif_unread_count": _Notif.objects.filter(user=request.user, read_at__isnull=True).count(),
            "all_schools": get_active_schools(),
            "my_students": my_students,
            "all_students": all_students,
            "counselor_users": counselor_users,
            **_get_priority_items(request.user, all_student_ids),
        }
        return render(request, "admin_dashboard/code.html", context)
    elif role in ("counselor", "editor"):
        return employee_dashboard(request)
    else:
        return student_dashboard(request)


@login_required(login_url=_LOGIN_URL)
def employee_dashboard(request):
    if request.user.role not in ("admin", "counselor", "editor"):
        return redirect("/")
    from apps.chat.models import ChatMessage
    from django.db.models import Q as _Q

    school_save_message = None
    school_error_message = None

    if request.method == "POST" and request.POST.get("action") == "add_school" and request.user.role != "editor":
        name = request.POST.get("name", "").strip()
        country = request.POST.get("country", "").strip()
        description = request.POST.get("description", "").strip()
        website = request.POST.get("website", "").strip()
        deadline_raw = request.POST.get("deadline", "").strip() or None
        if name and country:
            School.objects.create(
                name=name, country=country, description=description,
                website=website, deadline=deadline_raw, created_by=request.user,
            )
            school_save_message = f"School '{name}' added successfully."
        else:
            school_error_message = "School name and country are required."

    if request.user.role == "editor":
        my_students = Student.objects.filter(
            editor=request.user, is_active=True
        ).select_related("course", "counselor", "poc", "user").order_by("full_name")
    else:
        my_students = Student.objects.filter(
            _Q(counselor=request.user) | _Q(poc=request.user), is_active=True
        ).select_related("course", "counselor", "poc", "user").order_by("full_name")

    assigned_pks = list(my_students.values_list("pk", flat=True))
    unread_count = ChatMessage.objects.filter(
        student_id__in=assigned_pks, is_read=False
    ).exclude(sender=request.user).count()

    # INFRA-003: use cached school list to avoid N+1 on every dashboard load.
    from apps.crm.services.cache_service import get_active_schools
    all_schools = get_active_schools()
    all_students = Student.objects.filter(is_active=True).select_related("course", "counselor", "poc", "user").order_by("full_name")

    pinned_notes = list(
        StudentActivity.objects.filter(
            student_id__in=assigned_pks, activity_type__in=("note", "note_added"), is_pinned=True
        ).select_related("created_by", "student").order_by("-created_at")[:20]
    )

    from apps.notifications.models import Notification as _Notif
    context = {
        "my_students_count": my_students.count(),
        "all_students_count": Student.objects.filter(is_active=True).count(),
        "total_schools_count": len(all_schools),
        "my_students": my_students,
        "all_students": all_students,
        "all_schools": all_schools,
        "unread_messages_count": unread_count,
        "notif_unread_count": _Notif.objects.filter(user=request.user, read_at__isnull=True).count(),
        "school_save_message": school_save_message,
        "school_error_message": school_error_message,
        "pinned_notes": pinned_notes,
        "is_editor": request.user.role == "editor",
        **_get_priority_items(request.user, assigned_pks),
    }
    return render(request, "employee_dashboard/code.html", context)


# ─── Counselor-specific pages ──────────────────────────────────────────────────

def _counselor_guard(request):
    if not request.user.is_authenticated:
        return redirect(_LOGIN_URL)
    if request.user.role not in ("admin", "counselor", "editor"):
        return redirect("/")
    return None


@login_required(login_url=_LOGIN_URL)
def counselor_students_view(request):
    if (r := _counselor_guard(request)):
        return r
    if request.user.role == "editor":
        my_students_qs_filter = Q(editor=request.user)
    else:
        my_students_qs_filter = Q(counselor=request.user) | Q(poc=request.user)
    my_students = (
        Student.objects.filter(my_students_qs_filter, is_active=True)
        .select_related("course", "counselor", "poc", "user")
        .order_by("full_name")
    )
    all_students = (
        Student.objects.filter(is_active=True)
        .select_related("course", "counselor", "poc", "user")
        .order_by("full_name")
    )
    return render(request, "counselor_students/code.html", {
        "my_students": my_students,
        "all_students": all_students,
    })


@login_required(login_url=_LOGIN_URL)
def counselor_schools_view(request):
    if (r := _counselor_guard(request)):
        return r

    save_message = None
    error_message = None
    student_id = request.GET.get("student_id") or request.POST.get("student_id")
    selected_student = None

    if student_id:
        try:
            selected_student = Student.objects.select_related("counselor", "poc", "user").get(pk=student_id)
        except Student.DoesNotExist:
            pass

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "assign" and selected_student:
            school_id = request.POST.get("school_id")
            course_id = request.POST.get("course_id") or None
            notes = request.POST.get("notes", "").strip()
            deadline_raw = request.POST.get("deadline", "").strip() or None
            try:
                school = School.objects.get(pk=school_id)
                course = Course.objects.get(pk=course_id) if course_id else None
                StudentAssignedSchool.objects.update_or_create(
                    student=selected_student, school=school,
                    defaults={"course": course, "assigned_by": request.user, "notes": notes, "deadline": deadline_raw},
                )
                StudentActivity.objects.create(
                    student=selected_student,
                    activity_type="preference_saved",
                    description=f"Assigned to {school.name}",
                    created_by=request.user,
                )
                save_message = f"{school.name} assigned successfully."
                if selected_student.user_id:
                    try:
                        from apps.notifications.service import notify_sync
                        notify_sync(
                            selected_student.user,
                            title=f"New school assigned: {school.name}",
                            message="A new school has been added to your application list.",
                            link="/schools/",
                        )
                    except Exception:
                        pass
            except Exception as exc:
                error_message = str(exc)
        elif action == "remove":
            assignment_id = request.POST.get("assignment_id")
            StudentAssignedSchool.objects.filter(pk=assignment_id).delete()
            save_message = "School removed."
        elif action == "add_school":
            name = request.POST.get("name", "").strip()
            country = request.POST.get("country", "").strip()
            description = request.POST.get("description", "").strip()
            website = request.POST.get("website", "").strip()
            deadline_raw = request.POST.get("deadline", "").strip() or None
            if name and country:
                School.objects.create(
                    name=name, country=country, description=description,
                    website=website, deadline=deadline_raw, created_by=request.user,
                )
                save_message = f"School '{name}' added successfully."
            else:
                error_message = "School name and country are required."
        elif action == "add_course":
            school_id = request.POST.get("school_id")
            code = request.POST.get("code", "").strip()
            name = request.POST.get("name", "").strip()
            duration_weeks = request.POST.get("duration_weeks", "0").strip() or "0"
            fee_amount = request.POST.get("fee_amount", "0").strip() or "0"
            intake_months = request.POST.get("intake_months", "").strip()
            if school_id and code and name:
                try:
                    school = School.objects.get(pk=school_id)
                    Course.objects.create(
                        school=school, code=code, name=name,
                        duration_weeks=int(duration_weeks),
                        fee_amount=float(fee_amount),
                        intake_months=intake_months,
                    )
                    save_message = f"Course '{name}' added to {school.name}."
                except Exception as exc:
                    error_message = str(exc)
            else:
                error_message = "School, course code, and course name are required."
        return redirect(f"/counselor-schools/?student_id={student_id or ''}")

    students = Student.objects.filter(is_active=True).select_related("counselor", "user").order_by("full_name")
    schools = School.objects.all().order_by("country", "name")
    courses = Course.objects.filter(is_active=True).order_by("name")
    assignments = (
        StudentAssignedSchool.objects.filter(student=selected_student)
        .select_related("school", "course", "assigned_by")
        .order_by("school__country", "school__name")
        if selected_student else []
    )

    return render(request, "counselor_schools/code.html", {
        "students": students,
        "selected_student": selected_student,
        "schools": schools,
        "courses": courses,
        "assignments": assignments,
        "save_message": save_message,
        "error_message": error_message,
    })


@login_required(login_url=_LOGIN_URL)
def counselor_notes_view(request):
    from django.shortcuts import redirect
    url = "/counselor-interaction-log/"
    qs = request.GET.urlencode()
    return redirect(f"{url}?{qs}" if qs else url)


@login_required(login_url=_LOGIN_URL)
def counselor_interaction_log_view(request):
    if (r := _counselor_guard(request)):
        return r
    from apps.chat.models import ChatMessage, DirectMessage
    from apps.users.models import User

    is_admin = request.user.role == "admin"
    is_editor = request.user.role == "editor"

    if is_admin or is_editor:
        student_threads = (
            Student.objects.filter(is_active=True)
            .select_related("counselor", "poc", "user")
            .order_by("full_name")
        )
    else:
        student_threads = (
            Student.objects.filter(
                Q(counselor=request.user) | Q(poc=request.user), is_active=True
            )
            .select_related("counselor", "poc", "user")
            .order_by("full_name")
        )

    counselor_users = User.objects.filter(role__in=("admin", "counselor", "editor"), is_active=True).exclude(pk=request.user.pk).order_by("full_name")

    thread_type = request.GET.get("t")
    thread_id = request.GET.get("id")
    messages = []
    notes = []
    pinned_notes = []
    active_student = None
    active_counselor = None

    if thread_type == "student" and thread_id:
        try:
            active_student = Student.objects.select_related("counselor", "poc").get(pk=thread_id)
            authorized = is_admin or is_editor or active_student.counselor_id == request.user.pk or active_student.poc_id == request.user.pk
            if authorized:
                messages_qs = list(
                    ChatMessage.objects.filter(student=active_student)
                    .select_related("sender")
                    .order_by("created_at")
                )
                ChatMessage.objects.filter(student=active_student, is_read=False).exclude(
                    sender=request.user
                ).update(is_read=True)
                for msg in messages_qs:
                    messages.append({
                        "kind": "message",
                        "created_at": msg.created_at,
                        "sender": msg.sender,
                        "content": msg.content,
                        "is_mine": msg.sender_id == request.user.pk,
                    })

                notes_qs = list(
                    StudentActivity.objects.filter(
                        student=active_student, activity_type__in=("note", "note_added")
                    )
                    .select_related("created_by")
                    .order_by("created_at")
                )
                raw_notes = []
                pinned_notes = []
                for note in notes_qs:
                    entry = {
                        "kind": "note",
                        "pk": note.pk,
                        "created_at": note.created_at,
                        "author": note.created_by,
                        "content": note.description,
                        "is_pinned": note.is_pinned,
                    }
                    raw_notes.append(entry)
                    if note.is_pinned:
                        pinned_notes.append(entry)
                current_date = None
                for entry in raw_notes:
                    entry_date = entry["created_at"].date()
                    if entry_date != current_date:
                        current_date = entry_date
                        notes.append({"kind": "date_sep", "created_at": entry["created_at"]})
                    notes.append(entry)
            else:
                active_student = None
        except Student.DoesNotExist:
            pass

    elif thread_type == "dm" and thread_id:
        try:
            active_counselor = User.objects.get(pk=thread_id)
            dm_qs = list(
                DirectMessage.objects.filter(
                    Q(sender=request.user, recipient=active_counselor) |
                    Q(sender=active_counselor, recipient=request.user)
                ).order_by("created_at")
            )
            DirectMessage.objects.filter(
                sender=active_counselor, recipient=request.user, is_read=False
            ).update(is_read=True)
            for msg in dm_qs:
                messages.append({
                    "kind": "message",
                    "created_at": msg.created_at,
                    "sender": msg.sender,
                    "content": msg.content,
                    "is_mine": msg.sender_id == request.user.pk,
                })
        except User.DoesNotExist:
            pass

    return render(request, "counselor_interaction_log/code.html", {
        "student_threads": student_threads,
        "counselor_users": counselor_users,
        "thread_type": thread_type,
        "thread_id": thread_id,
        "active_student": active_student,
        "active_counselor": active_counselor,
        "notes": notes,
        "pinned_notes": pinned_notes,
        "messages": messages,
        "is_admin": is_admin,
        "is_editor": is_editor,
    })


@login_required(login_url=_LOGIN_URL)
def counselor_activity_view(request):
    if (r := _counselor_guard(request)):
        return r
    student_id = request.GET.get("student_id")
    students = Student.objects.filter(is_active=True).select_related("user").order_by("full_name")
    selected_student = None
    activities = []
    if student_id:
        try:
            selected_student = Student.objects.select_related("counselor", "poc", "user").get(pk=student_id)
            activities = StudentActivity.objects.filter(student=selected_student).order_by("-created_at")[:100]
        except Student.DoesNotExist:
            pass
    return render(request, "counselor_activity/code.html", {
        "students": students,
        "selected_student": selected_student,
        "activities": activities,
    })


@login_required(login_url=_LOGIN_URL)
def counselor_profile_update(request):
    if request.method == "POST":
        user = request.user
        email = request.POST.get("email", "").strip()
        phone = request.POST.get("phone", "").strip()
        full_name = request.POST.get("full_name", "").strip()
        if email:
            user.email = email
        if phone is not None:
            user.phone = phone
        if full_name:
            user.full_name = full_name
        avatar_file = request.FILES.get("avatar")
        if avatar_file:
            try:
                ext = Path(avatar_file.name).suffix
                url = _upload_to_local_storage(avatar_file, "avatars", f"user_{user.pk}{ext}")
                user.avatar = url
            except Exception as exc:
                _logger.exception("Counselor avatar upload failed for user pk=%s", user.pk)
        user.save()
    return redirect(request.POST.get("next", "/"))


@login_required(login_url=_LOGIN_URL)
def admin_dashboard_view(request):
    total_students = Student.objects.count()
    active_students = Student.objects.filter(is_active=True).count()
    context = {
        "student": _student_names(),
        "total_students": total_students,
        "active_students": active_students,
        "total_leads": Lead.objects.count(),
        "total_courses": Course.objects.filter(is_active=True).count(),
        "pending_leads": Lead.objects.filter(status="new").count(),
    }
    return render(request, "admin_dashboard/code.html", context)


# ─── Student dashboard ────────────────────────────────────────────────────────

@login_required(login_url=_LOGIN_URL)
def student_dashboard(request):
    from apps.chat.models import ChatMessage

    student = _get_student_for_user(request.user)
    unread = (
        ChatMessage.objects.filter(student=student, is_read=False)
        .exclude(sender=request.user)
        .count()
        if student
        else 0
    )
    from apps.notifications.models import Notification as _Notif
    context = {
        "student_obj": student,
        "student_id": student.pk if student else None,
        "counselor": student.counselor if student else None,
        "poc": student.poc if student else None,
        "editor": student.editor if student else None,
        "preferred_schools_count": StudentAssignedSchool.objects.filter(student=student).count() if student else 0,
        "recent_activities": StudentActivity.objects.filter(student=student).order_by("-created_at")[:5] if student else [],
        "unread_messages_count": unread,
        "notif_unread_count": _Notif.objects.filter(user=request.user, read_at__isnull=True).count(),
        "pinned_notes": StudentActivity.objects.filter(
            student=student, activity_type__in=("note", "note_added"), is_pinned=True
        ).select_related("created_by").order_by("-created_at") if student else [],
    }
    return render(request, "student_dashboard/code.html", context)


# ─── My Profile (student's own) ──────────────────────────────────────────────

@login_required(login_url=_LOGIN_URL)
def my_profile_view(request):
    student = _get_student_for_user(request.user)
    save_message = None

    upload_errors: list[str] = []
    files_saved: list[str] = []

    if request.method == "POST":
        _logger.warning("my_profile_view POST: student=%s FILES=%s", student, list(request.FILES.keys()))

    if request.method == "POST" and student:
        _save_student_profile(student, request.POST)

        # Avatar upload
        avatar_file = request.FILES.get("avatar")
        if avatar_file:
            try:
                ext = Path(avatar_file.name).suffix
                url = _upload_to_local_storage(avatar_file, "avatars", f"user_{request.user.pk}{ext}")
                request.user.avatar = url
                request.user.save(update_fields=["avatar"])
                files_saved.append("profile photo")
            except Exception as exc:
                _logger.exception("Avatar upload failed")
                upload_errors.append(f"Profile photo upload failed: {exc}")

        # Education history
        student.education_history.all().delete()
        i = 1
        while request.POST.get(f"edu_inst_{i}"):
            EducationHistory.objects.create(
                student=student,
                institution_name=request.POST.get(f"edu_inst_{i}", ""),
                level=request.POST.get(f"edu_level_{i}", ""),
                course_major=request.POST.get(f"edu_course_{i}", ""),
                country=request.POST.get(f"edu_country_{i}", ""),
                start_date=request.POST.get(f"edu_start_{i}") or None,
                end_date=request.POST.get(f"edu_end_{i}") or None,
                grading_type=request.POST.get(f"edu_grading_{i}", ""),
                score=request.POST.get(f"edu_score_{i}", ""),
                order=i,
            )
            i += 1

        # Work experiences
        student.work_experiences.all().delete()
        i = 1
        while request.POST.get(f"work_company_{i}"):
            WorkExperience.objects.create(
                student=student,
                company=request.POST.get(f"work_company_{i}", ""),
                role=request.POST.get(f"work_role_{i}", ""),
                start_date=request.POST.get(f"work_start_{i}") or None,
                end_date=request.POST.get(f"work_end_{i}") or None,
                is_current=bool(request.POST.get(f"work_current_{i}")),
                order=i,
            )
            i += 1

        # References (up to 3)
        student.references.all().delete()
        for i in range(1, 4):
            if request.POST.get(f"ref_name_{i}"):
                Reference.objects.create(
                    student=student,
                    name=request.POST.get(f"ref_name_{i}", ""),
                    organization=request.POST.get(f"ref_org_{i}", ""),
                    phone=request.POST.get(f"ref_phone_{i}", ""),
                    email=request.POST.get(f"ref_email_{i}", ""),
                    relationship=request.POST.get(f"ref_relationship_{i}", ""),
                    order=i,
                )

        # Profile documents
        doc_categories = [
            "passport", "marksheet_10", "marksheet_11", "marksheet_12",
            "english_proficiency", "gre_gmat_other",
        ]
        for cat in doc_categories:
            doc_file = request.FILES.get(f"doc_{cat}")
            if doc_file:
                try:
                    ext = Path(doc_file.name).suffix
                    url = _upload_to_local_storage(doc_file, f"profile_docs/{student.pk}", f"{cat}{ext}")
                    # Soft-delete previous version so its URL is preserved.
                    StudentProfileDocument.objects.filter(
                        student=student, category=cat, deleted_at__isnull=True
                    ).update(deleted_at=timezone.now())
                    StudentProfileDocument.objects.create(
                        student=student,
                        category=cat,
                        file_name=doc_file.name,
                        file_path=url,
                    )
                    files_saved.append(doc_file.name)
                except Exception as exc:
                    _logger.exception("Doc %s upload failed", cat)
                    upload_errors.append(f"{cat} upload failed: {exc}")

        StudentActivity.objects.create(
            student=student,
            activity_type="profile_updated",
            description="Profile information updated",
            created_by=request.user,
        )
        if upload_errors:
            save_message = "Profile saved. Some uploads had errors (see below)."
        elif files_saved:
            save_message = f"Profile saved successfully. Files uploaded: {', '.join(files_saved)}"
        else:
            save_message = "Profile saved successfully."
        student.refresh_from_db()

    education_history = list(student.education_history.all()) if student else []
    work_experiences = list(student.work_experiences.all()) if student else []
    references = list(student.references.all()) if student else []
    profile_docs = {d.category: d for d in student.profile_documents.filter(deleted_at__isnull=True)} if student else {}

    # Pad references list to always have 3 slots
    while len(references) < 3:
        references.append(None)

    ctx = _student_ctx(student)
    ctx.update({
        "is_own_profile": True,
        "education_history": education_history,
        "work_experiences": work_experiences,
        "references": references,
        "profile_docs": profile_docs,
        "save_message": save_message,
        "upload_errors": upload_errors,
        "files_saved": files_saved,
        "counselor": student.counselor if student else None,
        "poc": student.poc if student else None,
    })
    return render(request, "student_profile_full_flow/code.html", ctx)


# ─── Signed URL redirect for profile documents ───────────────────────────────

@login_required(login_url=_LOGIN_URL)
def view_profile_doc(request, doc_id):
    from django.http import HttpResponseForbidden, HttpResponseNotFound
    from django.shortcuts import redirect as _redirect
    try:
        doc = StudentProfileDocument.objects.select_related("student__user").get(pk=doc_id, deleted_at__isnull=True)
    except StudentProfileDocument.DoesNotExist:
        return HttpResponseNotFound("Document not found.")

    user = request.user
    is_owner = doc.student.user_id == user.pk
    is_privileged = getattr(user, "role", None) in ("admin", "counselor")
    if not is_owner and not is_privileged:
        return HttpResponseForbidden("Access denied.")

    file_url = doc.file_path
    force_download = request.GET.get("download")
    if force_download:
        file_url += ("&" if "?" in file_url else "?") + f"download={force_download}"
    return _redirect(file_url)


# ─── Avatar proxy helpers ─────────────────────────────────────────────────────

def _avatar_redirect(avatar_value):
    """Return a redirect response for an avatar field value."""
    from django.http import HttpResponseNotFound
    if not avatar_value:
        return HttpResponseNotFound()
    return redirect(avatar_value)


@login_required(login_url=_LOGIN_URL)
def my_avatar_view(request):
    return _avatar_redirect(request.user.avatar)


@login_required(login_url=_LOGIN_URL)
def user_avatar_view(request, pk):
    from django.http import HttpResponseNotFound
    from apps.users.models import User as _User
    try:
        target = _User.objects.get(pk=pk)
    except _User.DoesNotExist:
        return HttpResponseNotFound()
    return _avatar_redirect(target.avatar)


# ─── Instant profile-file upload (AJAX, session-auth) ────────────────────────

@login_required(login_url=_LOGIN_URL)
def upload_profile_file(request):
    from django.http import JsonResponse
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    category = request.POST.get("category", "").strip()
    file_obj = request.FILES.get("file")

    if not file_obj:
        return JsonResponse({"error": "No file received."}, status=400)

    # ── Avatar ──
    if category == "avatar":
        try:
            ext = Path(file_obj.name).suffix
            url = _upload_to_local_storage(file_obj, "avatars", f"user_{request.user.pk}{ext}")
            request.user.avatar = url
            request.user.save(update_fields=["avatar"])
            return JsonResponse({"url": "/my-avatar/", "file_name": file_obj.name})
        except Exception as exc:
            _logger.exception("Avatar AJAX upload failed")
            return JsonResponse({"error": str(exc)}, status=500)

    # ── Profile documents ──
    valid_cats = {
        "passport", "marksheet_10", "marksheet_11", "marksheet_12",
        "english_proficiency", "gre_gmat_other",
    }
    if category not in valid_cats:
        return JsonResponse({"error": f"Unknown category: {category}"}, status=400)

    student = _get_student_for_user(request.user)
    if not student:
        _logger.error(
            "upload_profile_file: no student for user pk=%s email=%s",
            request.user.pk, request.user.email,
        )
        return JsonResponse({"error": "No student profile linked to your account."}, status=400)

    try:
        # Capture existing profile doc so we can email it before overwriting
        existing_profile_doc = StudentProfileDocument.objects.filter(student=student, category=category, deleted_at__isnull=True).first()

        ext = Path(file_obj.name).suffix
        url = _upload_to_local_storage(file_obj, f"profile_docs/{student.pk}", f"{category}{ext}")

        # Email the replaced document before deletion
        if existing_profile_doc and existing_profile_doc.file_path:
            try:
                import requests as _req
                import mimetypes as _mt
                resp = _req.get(existing_profile_doc.file_path, timeout=15)
                if resp.status_code == 200:
                    old_filename = existing_profile_doc.file_name or f"{category}{Path(existing_profile_doc.file_path).suffix}"
                    mime = _mt.guess_type(old_filename)[0] or "application/octet-stream"
                    _send_doc_deleted_email(
                        student, old_filename, existing_profile_doc.category,
                        resp.content, old_filename, mime,
                    )
            except Exception:
                pass

        # Soft-delete the previous version so its URL is preserved in the DB.
        StudentProfileDocument.objects.filter(
            student=student, category=category, deleted_at__isnull=True
        ).update(deleted_at=timezone.now())
        doc = StudentProfileDocument.objects.create(
            student=student,
            category=category,
            file_name=file_obj.name,
            file_path=url,
        )
        return JsonResponse({"url": url, "file_name": file_obj.name, "doc_id": doc.pk})
    except Exception as exc:
        _logger.exception("Doc AJAX upload failed for category=%s student=%s", category, student.pk)
        return JsonResponse({"error": str(exc)}, status=500)


# ─── Staff/admin student profile view ────────────────────────────────────────

@login_required(login_url=_LOGIN_URL)
def applications(request):
    return redirect("/schools/")


@login_required(login_url=_LOGIN_URL)
def application_manager(request):
    return render(request, "application_manager_enhanced/code.html", {})


@login_required(login_url=_LOGIN_URL)
def notes_chat(request):
    from django.shortcuts import redirect
    return redirect("/interaction-log/")


@login_required(login_url=_LOGIN_URL)
def interaction_log(request):
    from apps.chat.models import ChatMessage

    student = _get_student_for_user(request.user)

    if request.method == "POST" and student:
        description = request.POST.get("description", "").strip()
        if description:
            StudentActivity.objects.create(
                student=student,
                activity_type="note_added",
                description=description,
                created_by=request.user,
            )
        return redirect("/interaction-log/")

    messages = []
    notes = []
    pinned_notes = []

    if student:
        messages_qs = list(
            ChatMessage.objects.filter(student=student)
            .select_related("sender")
            .order_by("created_at")
        )
        ChatMessage.objects.filter(student=student, is_read=False).exclude(
            sender=request.user
        ).update(is_read=True)
        for msg in messages_qs:
            messages.append({
                "kind": "message",
                "created_at": msg.created_at,
                "sender": msg.sender,
                "content": msg.content,
                "is_mine": msg.sender_id == request.user.pk,
            })

        notes_qs = list(
            StudentActivity.objects.filter(
                student=student, activity_type__in=("note", "note_added")
            )
            .select_related("created_by")
            .order_by("created_at")
        )
        raw_notes = []
        pinned_notes = []
        for note in notes_qs:
            entry = {
                "kind": "note",
                "pk": note.pk,
                "created_at": note.created_at,
                "author": note.created_by,
                "content": note.description,
                "is_pinned": note.is_pinned,
            }
            raw_notes.append(entry)
            if note.is_pinned:
                pinned_notes.append(entry)

        current_date = None
        for entry in raw_notes:
            entry_date = entry["created_at"].date()
            if entry_date != current_date:
                current_date = entry_date
                notes.append({"kind": "date_sep", "created_at": entry["created_at"]})
            notes.append(entry)

    return render(
        request,
        "interaction_log/code.html",
        {
            "student_obj": student,
            "student_id": student.pk if student else None,
            "counselor": student.counselor if student else None,
            "poc": student.poc if student else None,
            "notes": notes,
            "pinned_notes": pinned_notes,
            "messages": messages,
        },
    )


@login_required(login_url=_LOGIN_URL)
def students_list(request):
    if request.user.role not in ("admin", "counselor", "editor"):
        return redirect("/")

    from apps.users.models import User
    save_message = None
    error_message = None

    if request.method == "POST":
        action = request.POST.get("action")
        student_id = request.POST.get("student_id")
        try:
            student = Student.objects.get(pk=student_id)
        except Student.DoesNotExist:
            return redirect("/student-profile/")

        if action == "assign_counselor":
            counselor_id = request.POST.get("counselor_id") or None
            poc_id = request.POST.get("poc_id") or None
            editor_id = request.POST.get("editor_id") or None
            pack_selected = request.POST.get("pack_selected", "").strip()
            student.counselor_id = counselor_id
            student.poc_id = poc_id
            student.editor_id = editor_id
            student.pack_selected = pack_selected
            student.save(update_fields=["counselor", "poc", "editor", "pack_selected"])
            StudentActivity.objects.create(
                student=student,
                activity_type="status_changed",
                description="Counselor/POC assignment updated",
                created_by=request.user,
            )
            save_message = "Counselor assigned successfully."
        elif action == "assign_school":
            school_id = request.POST.get("school_id")
            course_id = request.POST.get("course_id") or None
            deadline_raw = request.POST.get("deadline", "").strip() or None
            notes = request.POST.get("notes", "").strip()
            try:
                school = School.objects.get(pk=school_id)
                course = Course.objects.get(pk=course_id) if course_id else None
                StudentAssignedSchool.objects.update_or_create(
                    student=student, school=school,
                    defaults={"course": course, "assigned_by": request.user, "notes": notes, "deadline": deadline_raw},
                )
                StudentActivity.objects.create(
                    student=student,
                    activity_type="preference_saved",
                    description=f"Assigned to {school.name}",
                    created_by=request.user,
                )
                if student.user_id:
                    try:
                        from apps.notifications.service import notify_sync
                        notify_sync(
                            student.user,
                            title=f"New school assigned: {school.name}",
                            message="A new school has been added to your application list.",
                            link="/schools/",
                        )
                    except Exception:
                        pass
            except Exception as exc:
                error_message = str(exc)
        elif action == "remove_school":
            assignment_id = request.POST.get("assignment_id")
            StudentAssignedSchool.objects.filter(pk=assignment_id).delete()

        return redirect(f"/student-profile/?student_id={student_id}")

    # Selected student
    student_id = request.GET.get("student_id")
    selected_student = None
    selected_student_assignments = []

    if student_id:
        try:
            selected_student = Student.objects.select_related("counselor", "poc", "course").get(pk=student_id)
            selected_student_assignments = list(
                StudentAssignedSchool.objects.filter(student=selected_student)
                .select_related("school", "course", "assigned_by")
                .order_by("school__country", "school__name")
            )
        except Student.DoesNotExist:
            pass

    students_qs = Student.objects.select_related("course", "counselor", "poc").order_by("full_name")
    students = list(students_qs)
    for s in students:
        s.completeness = _profile_completeness(s)

    counselor_users = User.objects.filter(role__in=("admin", "counselor"), is_active=True).order_by("full_name")
    editor_users = User.objects.filter(role="editor", is_active=True).order_by("full_name")
    schools = School.objects.filter(is_active=True).prefetch_related("courses").order_by("country", "name")
    courses = Course.objects.filter(is_active=True).order_by("name")

    from apps.crm.models import Student as _S
    pack_choices = _S.PackSelected.choices

    return render(request, "student_profile/code.html", {
        "students": students,
        "selected_student": selected_student,
        "selected_student_assignments": selected_student_assignments,
        "counselor_users": counselor_users,
        "editor_users": editor_users,
        "pack_choices": pack_choices,
        "schools": schools,
        "courses": courses,
        "save_message": save_message,
        "error_message": error_message,
    })


@login_required(login_url=_LOGIN_URL)
def student_profile(request, student_id=None):
    if request.user.role not in ("admin", "counselor", "editor"):
        return redirect("/")
    student = None
    if student_id:
        try:
            student = Student.objects.select_related("counselor", "poc", "user").get(pk=student_id)
        except Student.DoesNotExist:
            pass

    save_message = None
    if request.method == "POST" and student:
        _save_student_profile(student, request.POST)

        # Education history
        student.education_history.all().delete()
        i = 1
        while request.POST.get(f"edu_inst_{i}"):
            EducationHistory.objects.create(
                student=student,
                institution_name=request.POST.get(f"edu_inst_{i}", ""),
                level=request.POST.get(f"edu_level_{i}", ""),
                course_major=request.POST.get(f"edu_course_{i}", ""),
                country=request.POST.get(f"edu_country_{i}", ""),
                start_date=request.POST.get(f"edu_start_{i}") or None,
                end_date=request.POST.get(f"edu_end_{i}") or None,
                grading_type=request.POST.get(f"edu_grading_{i}", ""),
                score=request.POST.get(f"edu_score_{i}", ""),
                order=i,
            )
            i += 1

        # Work experiences
        student.work_experiences.all().delete()
        i = 1
        while request.POST.get(f"work_company_{i}"):
            from apps.crm.models import WorkExperience
            WorkExperience.objects.create(
                student=student,
                company=request.POST.get(f"work_company_{i}", ""),
                role=request.POST.get(f"work_role_{i}", ""),
                start_date=request.POST.get(f"work_start_{i}") or None,
                end_date=request.POST.get(f"work_end_{i}") or None,
                is_current=bool(request.POST.get(f"work_current_{i}")),
                order=i,
            )
            i += 1

        # References (up to 3)
        student.references.all().delete()
        for i in range(1, 4):
            if request.POST.get(f"ref_name_{i}"):
                from apps.crm.models import Reference
                Reference.objects.create(
                    student=student,
                    name=request.POST.get(f"ref_name_{i}", ""),
                    organization=request.POST.get(f"ref_org_{i}", ""),
                    phone=request.POST.get(f"ref_phone_{i}", ""),
                    email=request.POST.get(f"ref_email_{i}", ""),
                    relationship=request.POST.get(f"ref_relationship_{i}", ""),
                    order=i,
                )

        StudentActivity.objects.create(
            student=student,
            activity_type="profile_updated",
            description="Profile information updated by counselor",
            created_by=request.user,
        )
        save_message = "Profile saved successfully."
        student.refresh_from_db()

    education_history = list(student.education_history.all()) if student else []
    work_experiences = list(student.work_experiences.all()) if student else []
    references = list(student.references.all()) if student else []
    while len(references) < 3:
        references.append(None)
    profile_docs = {d.category: d for d in student.profile_documents.filter(deleted_at__isnull=True)} if student else {}
    ctx = _student_ctx(student)
    ctx.update({
        "education_history": education_history,
        "work_experiences": work_experiences,
        "references": references,
        "profile_docs": profile_docs,
        "student_id": student_id,
        "save_message": save_message,
        "is_own_profile": False,
        "counselor": student.counselor if student else None,
        "poc": student.poc if student else None,
        "student_user": student.user if student else None,
    })
    return render(request, "student_profile_full_flow/code.html", ctx)


# ─── Admin Schools Management ─────────────────────────────────────────────────

@login_required(login_url=_LOGIN_URL)
def admin_schools_view(request):
    if request.user.role != "admin":
        return redirect("/")

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "add_school":
            name = request.POST.get("name", "").strip()
            country = request.POST.get("country", "").strip()
            description = request.POST.get("description", "").strip()
            website = request.POST.get("website", "").strip()
            deadline_raw = request.POST.get("deadline", "").strip() or None
            if name and country:
                School.objects.create(
                    name=name, country=country, description=description,
                    website=website, deadline=deadline_raw, created_by=request.user,
                )
                django_messages.success(request, f"School '{name}' added successfully.")
            else:
                django_messages.error(request, "School name and country are required.")

        elif action == "edit_school":
            school_id = request.POST.get("school_id")
            try:
                school = School.objects.get(pk=school_id)
                school.name = request.POST.get("name", school.name).strip()
                school.country = request.POST.get("country", school.country).strip()
                school.description = request.POST.get("description", "").strip()
                school.website = request.POST.get("website", "").strip()
                deadline_raw = request.POST.get("deadline", "").strip() or None
                school.deadline = deadline_raw
                school.save()
                django_messages.success(request, f"School '{school.name}' updated.")
            except School.DoesNotExist:
                django_messages.error(request, "School not found.")

        elif action == "toggle_school":
            school_id = request.POST.get("school_id")
            try:
                school = School.objects.get(pk=school_id)
                school.is_active = not school.is_active
                school.save(update_fields=["is_active"])
                state = "activated" if school.is_active else "deactivated"
                django_messages.success(request, f"School {state}.")
            except School.DoesNotExist:
                django_messages.error(request, "School not found.")

        elif action == "add_course":
            school_id = request.POST.get("school_id")
            code = request.POST.get("code", "").strip()
            name = request.POST.get("name", "").strip()
            duration_weeks = request.POST.get("duration_weeks", "0").strip() or "0"
            fee_amount = request.POST.get("fee_amount", "0").strip() or "0"
            intake_months = request.POST.get("intake_months", "").strip()
            if school_id and code and name:
                try:
                    school = School.objects.get(pk=school_id)
                    Course.objects.create(
                        school=school, code=code, name=name,
                        duration_weeks=int(duration_weeks),
                        fee_amount=float(fee_amount),
                        intake_months=intake_months,
                    )
                    django_messages.success(request, f"Course '{name}' added to {school.name}.")
                except School.DoesNotExist:
                    django_messages.error(request, "School not found.")
                except Exception as exc:
                    err = str(exc)
                    if "unique" in err.lower() or "duplicate" in err.lower():
                        django_messages.error(request, f"A course with code '{code}' already exists. Course codes must be unique across all schools.")
                    else:
                        django_messages.error(request, err)
            else:
                django_messages.error(request, "Course code, name, and school are required.")

        elif action == "toggle_course":
            course_id = request.POST.get("course_id")
            try:
                course = Course.objects.get(pk=course_id)
                course.is_active = not course.is_active
                course.save(update_fields=["is_active"])
                state = "activated" if course.is_active else "deactivated"
                django_messages.success(request, f"Course {state}.")
            except Course.DoesNotExist:
                django_messages.error(request, "Course not found.")

        # Preserve selected school after POST
        selected_school_id = request.POST.get("selected_school_id") or request.POST.get("school_id")
        redirect_url = "/admin-schools/"
        if selected_school_id:
            redirect_url += f"?school_id={selected_school_id}"
        return redirect(redirect_url)

    selected_school_id = request.GET.get("school_id")
    selected_school = None
    if selected_school_id:
        try:
            selected_school = School.objects.prefetch_related("courses").get(pk=selected_school_id)
        except School.DoesNotExist:
            pass

    schools = School.objects.prefetch_related("courses").order_by("country", "name")

    return render(request, "admin_schools/code.html", {
        "schools": schools,
        "selected_school": selected_school,
    })


# ─── Schools (counselor-assigned) ────────────────────────────────────────────

@login_required(login_url=_LOGIN_URL)
def schools_view(request):
    student = _get_student_for_user(request.user)
    assigned = []
    if student:
        assigned = (
            StudentAssignedSchool.objects
            .filter(student=student)
            .select_related("school", "course", "assigned_by")
            .order_by("school__country", "school__name")
        )
    from datetime import date
    return render(request, "schools/code.html", {"assigned_schools": assigned, "today": date.today()})


# ─── Pin note ────────────────────────────────────────────────────────────────

@login_required(login_url=_LOGIN_URL)
def toggle_pin_note(request, pk):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    try:
        note = StudentActivity.objects.select_related("student").get(
            pk=pk, activity_type__in=("note", "note_added")
        )
    except StudentActivity.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)

    student = note.student
    authorized = (
        request.user.role in ("admin", "editor")
        or student.counselor_id == request.user.pk
        or student.poc_id == request.user.pk
        or note.created_by_id == request.user.pk
        or (hasattr(student, "editor_id") and student.editor_id == request.user.pk)
    )
    if not authorized:
        return JsonResponse({"error": "Forbidden"}, status=403)

    note.is_pinned = not note.is_pinned
    note.save(update_fields=["is_pinned"])
    return JsonResponse({"is_pinned": note.is_pinned, "pk": note.pk})


# ─── School documents ─────────────────────────────────────────────────────────

_DOC_PANEL_META = [
    ("essay",  "Essays",                     "edit_note"),
    ("lor",    "Letters of Recommendation",  "recommend"),
    ("resume", "Resume / CV",                "work"),
]


def _build_doc_panels(docs_qs):
    groups = {key: [] for key, _, _ in _DOC_PANEL_META}
    for d in docs_qs:
        if d.category in groups:
            groups[d.category].append(d)
    return [
        {"key": key, "label": label, "icon": icon, "files": groups[key]}
        for key, label, icon in _DOC_PANEL_META
    ]


def _send_doc_deleted_email(student, doc_name, doc_category, file_bytes, filename, mimetype=None):
    """Email the deleted document as an attachment to student, counselor, editor and POC."""
    from django.core.mail import EmailMessage

    if not (
        getattr(django_settings, "EMAIL_HOST_USER", None)
        and getattr(django_settings, "EMAIL_HOST_PASSWORD", None)
    ):
        return

    recipients = set()
    if student.email:
        recipients.add(student.email)
    if student.user_id and student.user and student.user.email:
        recipients.add(student.user.email)
    if student.counselor_id and student.counselor and student.counselor.email:
        recipients.add(student.counselor.email)
    if student.editor_id and student.editor and student.editor.email:
        recipients.add(student.editor.email)
    if student.poc_id and student.poc and student.poc.email:
        recipients.add(student.poc.email)

    if not recipients:
        return

    student_name = student.full_name or student.email or f"Student #{student.pk}"
    category_display = doc_category.replace("_", " ").title()
    subject = f"[IE CRM] Document Deleted – {doc_name} ({student_name})"
    body = (
        f"A document has been deleted from the Intelligent Education CRM.\n\n"
        f"Student : {student_name}\n"
        f"Document: {doc_name}\n"
        f"Category: {category_display}\n\n"
        f"The deleted file is attached for your records.\n\n"
        f"— Intelligent Education CRM"
    )
    msg = EmailMessage(
        subject=subject,
        body=body,
        from_email=django_settings.DEFAULT_FROM_EMAIL,
        to=list(recipients),
    )
    msg.attach(filename, file_bytes, mimetype or "application/octet-stream")
    try:
        msg.send(fail_silently=True)
    except Exception:
        pass


def _handle_document_upload(request, student, school):
    """Handle a document upload POST. Returns a save_message string or None."""
    import os
    from django.conf import settings as django_settings

    action = request.POST.get("action")

    if action == "delete":
        doc_id = request.POST.get("doc_id")
        # Only match non-deleted docs; ignore already-soft-deleted records.
        qs = StudentSchoolDocument.objects.filter(pk=doc_id, student=student, school=school, deleted_at__isnull=True)
        doc = qs.first()
        if doc:
            # Permission check: students may only delete their own uploads;
            # counselors/admins/editors may delete any document for this student.
            user = request.user
            is_privileged = getattr(user, "role", None) in ("admin", "counselor", "editor")
            is_uploader = doc.uploaded_by_id == user.pk
            if not is_privileged and not is_uploader:
                return "Permission denied: you may only delete files you uploaded."

            # Email a copy of the file before marking deleted.
            file_bytes = None
            file_url = doc.file_url or ""
            if file_url.startswith("http"):
                try:
                    import requests as _req
                    resp = _req.get(file_url, timeout=15)
                    if resp.status_code == 200:
                        file_bytes = resp.content
                except Exception:
                    pass

            if file_bytes:
                import mimetypes as _mt
                mime = _mt.guess_type(doc.file_name)[0] or "application/octet-stream"
                _send_doc_deleted_email(student, doc.file_name, doc.category, file_bytes, doc.file_name, mime)

            # Soft-delete: stamp deleted_at, keep DB record and file intact.
            doc.deleted_at = timezone.now()
            doc.save(update_fields=["deleted_at"])
            return "Document deleted."
        return None

    category = request.POST.get("category")
    uploaded_file = request.FILES.get("file")
    if not category or not uploaded_file or category not in DocumentCategory.values:
        return None

    import uuid as _uuid
    ext = os.path.splitext(uploaded_file.name)[1]
    unique_name = f"{_uuid.uuid4().hex}{ext}"
    storage_folder = f"school_docs/{student.pk}/{school.pk}"

    try:
        public_url = _upload_to_local_storage(uploaded_file, storage_folder, unique_name)
    except Exception as exc:
        _logger.exception("School doc upload failed: student=%s school=%s", student.pk, school.pk)
        return f"Upload failed: {exc}"

    StudentSchoolDocument.objects.create(
        student=student,
        school=school,
        category=category,
        file_name=uploaded_file.name,
        file_url=public_url,
        uploaded_by=request.user,
    )
    StudentActivity.objects.create(
        student=student,
        activity_type="document_uploaded",
        description=f"Uploaded {dict(DocumentCategory.choices)[category]} for {school.name}",
        created_by=request.user,
    )
    return f"{dict(DocumentCategory.choices)[category]} — {uploaded_file.name} uploaded."


@login_required(login_url=_LOGIN_URL)
def school_documents_view(request, school_id):
    student = _get_student_for_user(request.user)
    school = get_object_or_404(School, pk=school_id, is_active=True)

    if not student or not StudentAssignedSchool.objects.filter(student=student, school=school).exists():
        return redirect("/schools/")

    save_message = None
    if request.method == "POST":
        save_message = _handle_document_upload(request, student, school)

    docs = list(StudentSchoolDocument.objects.filter(student=student, school=school, deleted_at__isnull=True).select_related("uploaded_by"))
    doc_panels = _build_doc_panels(docs)

    return render(request, "school_documents/code.html", {
        "school": school,
        "doc_panels": doc_panels,
        "additional_student_docs": [d for d in docs if d.category == "additional_student"],
        "additional_counsel_docs": [d for d in docs if d.category == "additional_counsel"],
        "save_message": save_message,
        "is_counselor_view": False,
        "student": student,
        "back_url": "/schools/",
    })


@login_required(login_url=_LOGIN_URL)
def counselor_school_documents_view(request, student_id, school_id):
    if (r := _counselor_guard(request)):
        return r
    student = get_object_or_404(Student, pk=student_id)
    school = get_object_or_404(School, pk=school_id)

    # All internal roles (admin, counselor, editor) can access documents for any student

    save_message = None
    if request.method == "POST":
        save_message = _handle_document_upload(request, student, school)

    docs = list(StudentSchoolDocument.objects.filter(student=student, school=school, deleted_at__isnull=True).select_related("uploaded_by"))
    doc_panels = _build_doc_panels(docs)

    return render(request, "school_documents/code.html", {
        "school": school,
        "doc_panels": doc_panels,
        "additional_student_docs": [d for d in docs if d.category == "additional_student"],
        "additional_counsel_docs": [d for d in docs if d.category == "additional_counsel"],
        "save_message": save_message,
        "is_counselor_view": True,
        "student": student,
        "back_url": f"/counselor-schools/?student_id={student_id}",
    })


# ─── Student Application View (counselor/admin detail page) ──────────────────

@login_required(login_url=_LOGIN_URL)
def student_application_view(request, student_id):
    if request.user.role not in ("admin", "counselor", "editor"):
        return redirect("/")

    student = get_object_or_404(Student.objects.select_related("editor"), pk=student_id)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add_note":
            description = request.POST.get("description", "").strip()
            if description:
                StudentActivity.objects.create(
                    student=student,
                    activity_type="note_added",
                    description=description,
                    created_by=request.user,
                )
                if student.user_id:
                    try:
                        from apps.notifications.service import notify_sync
                        notify_sync(
                            student.user,
                            title=f"New note from {request.user.full_name or request.user.email}",
                            message=description[:120],
                            link="/interaction-log/",
                        )
                    except Exception:
                        pass
        else:
            school_id = request.POST.get("school_id")
            if school_id:
                try:
                    school = School.objects.get(pk=school_id)
                    _handle_document_upload(request, student, school)
                except School.DoesNotExist:
                    pass
        return redirect(f"/student-application/{student_id}/")

    activities = list(
        StudentActivity.objects
        .filter(student=student)
        .select_related("created_by")
        .order_by("-created_at")[:10]
    )

    assignments_raw = list(
        StudentAssignedSchool.objects
        .filter(student=student)
        .select_related("school", "course")
        .order_by("school__name")
    )

    school_panels = []
    for asgn in assignments_raw:
        docs = list(
            StudentSchoolDocument.objects.filter(student=student, school=asgn.school, deleted_at__isnull=True)
            .select_related("uploaded_by")
        )
        school_panels.append({
            "assignment": asgn,
            "school": asgn.school,
            "course": asgn.course,
            "lor_docs": [d for d in docs if d.category == "lor"],
            "essay_docs": [d for d in docs if d.category == "essay"],
            "resume_docs": [d for d in docs if d.category == "resume"],
            "additional_student_docs": [d for d in docs if d.category == "additional_student"],
            "additional_counsel_docs": [d for d in docs if d.category == "additional_counsel"],
        })

    from apps.chat.models import ChatMessage
    if request.user.role == "admin":
        unread_count = ChatMessage.objects.filter(is_read=False).exclude(sender=request.user).count()
    elif request.user.role == "editor":
        assigned_pks = Student.objects.filter(editor=request.user).values_list("pk", flat=True)
        unread_count = ChatMessage.objects.filter(
            student_id__in=assigned_pks, is_read=False
        ).exclude(sender=request.user).count()
    else:
        assigned_pks = Student.objects.filter(
            Q(counselor=request.user) | Q(poc=request.user)
        ).values_list("pk", flat=True)
        unread_count = ChatMessage.objects.filter(
            student_id__in=assigned_pks, is_read=False
        ).exclude(sender=request.user).count()

    return render(request, "student_application/code.html", {
        "student": student,
        "school_panels": school_panels,
        "activities": activities,
        "unread_messages_count": unread_count,
    })


# ─── Recent Activity ──────────────────────────────────────────────────────────

@login_required(login_url=_LOGIN_URL)
def recent_activity_view(request):
    student = _get_student_for_user(request.user)
    activities = []
    if student:
        activities = StudentActivity.objects.filter(student=student).order_by("-created_at")[:50]
    return render(request, "recent_activity/code.html", {"activities": activities})


# ─── Global Search (session-auth JSON) ───────────────────────────────────────

@login_required(login_url=_LOGIN_URL)
def global_search(request):
    q = request.GET.get("q", "").strip()
    if not q or len(q) < 2:
        return JsonResponse({"students": [], "schools": [], "courses": []})

    role = request.user.role
    results: dict = {"students": [], "schools": [], "courses": []}

    if role in ("admin", "counselor", "editor"):
        qs = Student.objects.select_related("course")
        if role in ("counselor", "editor"):
            qs = qs.filter(
                Q(counselor=request.user) | Q(poc=request.user) | Q(editor=request.user)
            )
        students = qs.filter(
            Q(full_name__icontains=q)
            | Q(email__icontains=q)
            | Q(student_code__icontains=q)
            | Q(phone__icontains=q)
        ).order_by("full_name")[:8]
        results["students"] = [
            {
                "id": s.pk,
                "name": s.full_name,
                "code": s.student_code or "",
                "email": s.email or "",
                "course": s.course.name if s.course else "",
                "url": f"/student-profile/{s.pk}/",
            }
            for s in students
        ]

        schools = School.objects.filter(
            Q(name__icontains=q) | Q(country__icontains=q)
        ).order_by("name")[:6]
        school_url = "/admin-schools/" if role == "admin" else "/counselor-schools/"
        results["schools"] = [
            {"id": s.pk, "name": s.name, "country": s.country or "", "url": school_url}
            for s in schools
        ]

        courses = Course.objects.select_related("school").filter(
            Q(name__icontains=q) | Q(code__icontains=q) | Q(school__name__icontains=q)
        ).order_by("name")[:6]
        results["courses"] = [
            {
                "id": c.pk,
                "name": c.name,
                "code": c.code or "",
                "school": c.school.name if c.school else "",
            }
            for c in courses
        ]
    else:
        # Student role: search their own assigned schools and courses
        student = _get_student_for_user(request.user)
        if student:
            assigned = StudentAssignedSchool.objects.filter(student=student).select_related("school", "course")
            for a in assigned:
                if q.lower() in (a.school.name or "").lower() or q.lower() in (a.school.country or "").lower():
                    results["schools"].append(
                        {"id": a.school.pk, "name": a.school.name, "country": a.school.country or "", "url": "/schools/"}
                    )
                if a.course and (q.lower() in (a.course.name or "").lower() or q.lower() in (a.course.code or "").lower()):
                    results["courses"].append(
                        {"id": a.course.pk, "name": a.course.name, "code": a.course.code or "", "school": a.school.name}
                    )

    return JsonResponse(results)


# ─── Priority item dismiss ────────────────────────────────────────────────────

@login_required(login_url=_LOGIN_URL)
def dismiss_priority_item(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    item_type = request.POST.get("item_type", "")
    item_id = request.POST.get("item_id", "")
    if item_type not in ("document", "deadline") or not item_id:
        return JsonResponse({"error": "Invalid parameters"}, status=400)
    try:
        item_id = int(item_id)
    except ValueError:
        return JsonResponse({"error": "Invalid item_id"}, status=400)
    PriorityItemDismissal.objects.get_or_create(
        user=request.user, item_type=item_type, item_id=item_id
    )
    return JsonResponse({"ok": True})


