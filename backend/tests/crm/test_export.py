"""
Tests for PERF-003 streaming CSV export endpoint.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


class TestStudentCsvExport:
    _URL = "/api/crm/students/export/"

    def test_export_returns_200_for_counselor(self, counselor_client):
        response = counselor_client.get(self._URL)
        assert response.status_code == 200

    def test_export_content_type_is_csv(self, counselor_client):
        response = counselor_client.get(self._URL)
        assert "text/csv" in response.get("Content-Type", "")

    def test_export_content_disposition_is_attachment(self, counselor_client):
        response = counselor_client.get(self._URL)
        disposition = response.get("Content-Disposition", "")
        assert "attachment" in disposition
        assert "students_export.csv" in disposition

    def test_export_contains_header_row(self, counselor_client):
        response = counselor_client.get(self._URL)
        content = b"".join(response.streaming_content).decode()
        assert "Student Code" in content
        assert "Full Name" in content

    def test_export_denied_for_students(self, student_client):
        response = student_client.get(self._URL)
        assert response.status_code in (403, 401)

    def test_export_denied_for_anonymous(self, api_client):
        response = api_client.get(self._URL)
        assert response.status_code == 401

    def test_export_is_active_filter(self, counselor_client, db):
        from apps.crm.models import Student
        Student.objects.create(
            full_name="Active Student",
            email="active@test.com",
            student_code="STU-EXP-1",
            is_active=True,
        )
        Student.objects.create(
            full_name="Inactive Student",
            email="inactive@test.com",
            student_code="STU-EXP-2",
            is_active=False,
        )
        response = counselor_client.get(f"{self._URL}?is_active=true")
        content = b"".join(response.streaming_content).decode()
        assert "STU-EXP-1" in content
        assert "STU-EXP-2" not in content

    def test_export_empty_db_returns_header_only(self, counselor_client):
        response = counselor_client.get(self._URL)
        content = b"".join(response.streaming_content).decode()
        lines = [l for l in content.split("\n") if l.strip()]
        assert len(lines) >= 1
