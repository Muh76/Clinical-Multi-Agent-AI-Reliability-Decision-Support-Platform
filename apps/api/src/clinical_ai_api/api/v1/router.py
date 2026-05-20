from fastapi import APIRouter

from clinical_ai_api.api.v1.endpoints import evaluation, patients, safety, workflows

router = APIRouter()
router.include_router(patients.router, prefix="/patients", tags=["patients"])
router.include_router(safety.router, prefix="/safety", tags=["safety"])
router.include_router(evaluation.router, prefix="/evaluation", tags=["evaluation"])
router.include_router(workflows.router, prefix="/workflows", tags=["workflows"])

