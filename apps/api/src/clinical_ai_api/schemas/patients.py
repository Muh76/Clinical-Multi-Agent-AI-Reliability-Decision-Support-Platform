from pydantic import BaseModel, Field


class PatientSummary(BaseModel):
    patient_id: str = Field(description="Internal patient reliability context identifier.")
    display_label: str
    risk_tier: str | None = None

