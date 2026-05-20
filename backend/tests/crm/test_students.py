"""
CRM Student model tests — soft delete, student code generation, service layer.
"""
import pytest
from apps.crm.models import Student
from apps.crm.services.student_service import soft_delete_student, restore_student


@pytest.fixture
def student_record(db, admin_user):
    return Student.all_objects.create(
        full_name="Test Student Record",
        email="test.record@example.com",
    )


@pytest.mark.django_db
class TestStudentCode:
    def test_student_code_auto_generated(self, db, admin_user):
        student = Student.all_objects.create(full_name="Auto Code Student")
        assert student.student_code.startswith("STU-")
        assert student.student_code[4:].isdigit()

    def test_student_codes_are_sequential(self, db):
        s1 = Student.all_objects.create(full_name="First")
        s2 = Student.all_objects.create(full_name="Second")
        n1 = int(s1.student_code[4:])
        n2 = int(s2.student_code[4:])
        assert n2 == n1 + 1


@pytest.mark.django_db
class TestStudentSoftDelete:
    def test_soft_delete_sets_deleted_at(self, student_record, admin_user):
        soft_delete_student(student_record, deleted_by=admin_user)
        student_record.refresh_from_db()
        assert student_record.deleted_at is not None
        assert student_record.is_active is False

    def test_soft_deleted_student_hidden_from_default_manager(self, student_record, admin_user):
        pk = student_record.pk
        soft_delete_student(student_record, deleted_by=admin_user)
        # Default manager (Student.objects) should NOT return deleted records
        assert not Student.objects.filter(pk=pk).exists()

    def test_soft_deleted_student_visible_to_all_objects_manager(self, student_record, admin_user):
        pk = student_record.pk
        soft_delete_student(student_record, deleted_by=admin_user)
        # Unfiltered manager should still find it
        assert Student.all_objects.filter(pk=pk).exists()

    def test_restore_clears_deleted_at(self, student_record, admin_user):
        soft_delete_student(student_record, deleted_by=admin_user)
        restore_student(student_record, restored_by=admin_user)
        student_record.refresh_from_db()
        assert student_record.deleted_at is None
        assert student_record.is_active is True

    def test_cannot_soft_delete_already_deleted_student(self, student_record, admin_user):
        soft_delete_student(student_record, deleted_by=admin_user)
        with pytest.raises(ValueError, match="already deleted"):
            soft_delete_student(student_record, deleted_by=admin_user)

    def test_cannot_restore_non_deleted_student(self, student_record, admin_user):
        with pytest.raises(ValueError, match="not deleted"):
            restore_student(student_record, restored_by=admin_user)

    def test_soft_delete_creates_audit_log(self, student_record, admin_user):
        from apps.audit.models import ActivityLog
        soft_delete_student(student_record, deleted_by=admin_user)
        log = ActivityLog.objects.filter(action="student_deleted").first()
        assert log is not None
        assert str(student_record.pk) == log.entity_id
