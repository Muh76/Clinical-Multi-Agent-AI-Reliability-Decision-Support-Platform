"""ORM model registry.

Import this module in Alembic and application startup paths so SQLAlchemy metadata
contains every mapped table.
"""

from clinical_ai_platform.db.models.audit_log import AuditLog
from clinical_ai_platform.db.models.clinical_case import ClinicalCase
from clinical_ai_platform.db.models.patient import Patient

__all__ = ["AuditLog", "ClinicalCase", "Patient"]

