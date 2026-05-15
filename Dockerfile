FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TEMPLATE_ROOT=/templates

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy Django backend source
COPY backend/ ./

# Copy all HTML template directories from repo root
COPY admin_dashboard/         /templates/admin_dashboard/
COPY admin_schools/           /templates/admin_schools/
COPY application_manager_enhanced/ /templates/application_manager_enhanced/
COPY counselor_activity/      /templates/counselor_activity/
COPY counselor_interaction_log/ /templates/counselor_interaction_log/
COPY counselor_notes/         /templates/counselor_notes/
COPY counselor_schools/       /templates/counselor_schools/
COPY counselor_students/      /templates/counselor_students/
COPY employee_dashboard/      /templates/employee_dashboard/
COPY interaction_log/         /templates/interaction_log/
COPY notes_chat/              /templates/notes_chat/
COPY notes_chat_enhanced/     /templates/notes_chat_enhanced/
COPY recent_activity/         /templates/recent_activity/
COPY school_documents/        /templates/school_documents/
COPY schools/                 /templates/schools/
COPY student_application/     /templates/student_application/
COPY student_dashboard/       /templates/student_dashboard/
COPY student_profile/         /templates/student_profile/
COPY student_profile_full_flow/ /templates/student_profile_full_flow/
COPY student_profile_multi_step/ /templates/student_profile_multi_step/

# Collect static files at build time
RUN DJANGO_SECRET_KEY=build-placeholder DJANGO_DEBUG=0 python manage.py collectstatic --noinput

RUN chmod +x /app/start.sh

EXPOSE 8000

CMD ["/app/start.sh"]
