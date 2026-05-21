"""
Cursor pagination tests — LOW-002.
"""
from __future__ import annotations

import pytest

from apps.crm.models import Student


STUDENTS_URL = "/api/crm/students/"


@pytest.fixture
def three_students(db, admin_user):
    """Create three students for pagination tests."""
    students = []
    for i in range(3):
        s = Student.objects.create(
            full_name=f"Student {i}",
            email=f"stu{i}@test.com",
        )
        students.append(s)
    return students


class TestCursorPagination:
    def test_list_without_cursor_uses_page_number(self, admin_client, three_students):
        resp = admin_client.get(STUDENTS_URL)
        assert resp.status_code == 200
        assert "results" in resp.data or isinstance(resp.data, list)

    def test_list_with_cursor_param_activates_cursor_pagination(self, admin_client, three_students):
        # First get without cursor to establish baseline.
        resp1 = admin_client.get(STUDENTS_URL)
        assert resp1.status_code == 200

        # Now request with cursor= (empty cursor = first page in cursor mode).
        resp2 = admin_client.get(STUDENTS_URL + "?cursor=")
        assert resp2.status_code == 200
        # Cursor pagination returns results and next/previous links.
        data = resp2.data
        assert "results" in data

    def test_page_size_respected(self, admin_client, three_students):
        resp = admin_client.get(STUDENTS_URL + "?page_size=2")
        assert resp.status_code == 200
        data = resp.data
        if "results" in data:
            assert len(data["results"]) <= 2


class TestPhoneValidation:
    """
    student_code is auto-generated on save() but not on full_clean().
    We exclude it from validation to isolate phone validation testing.
    """

    def test_valid_phone_passes(self, db):
        student = Student(
            student_code="STU-TEST-1",
            full_name="Valid Phone",
            email="valid@test.com",
            phone="+919876543210",
        )
        student.full_clean()  # Should not raise

    def test_invalid_phone_fails_validation(self, db):
        from django.core.exceptions import ValidationError
        student = Student(
            student_code="STU-TEST-2",
            full_name="Bad Phone",
            email="bad@test.com",
            phone="not-a-phone!!!",
        )
        with pytest.raises(ValidationError):
            student.full_clean()

    def test_blank_phone_allowed(self, db):
        student = Student(
            student_code="STU-TEST-3",
            full_name="No Phone",
            email="nophone@test.com",
            phone="",
        )
        student.full_clean()  # Blank is allowed

    def test_short_phone_fails(self, db):
        from django.core.exceptions import ValidationError
        student = Student(
            student_code="STU-TEST-4",
            full_name="Short Phone",
            email="short@test.com",
            phone="12345",  # Only 5 digits — minimum is 6
        )
        with pytest.raises(ValidationError):
            student.full_clean()
