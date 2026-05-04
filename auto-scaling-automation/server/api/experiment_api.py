
from fastapi import APIRouter

from experiment.models import ExperimentCleanupRequest, ExperimentSetupRequest, ExperimentSetupResponse
from experiment.experiment_logic import cleanup_experiment_logic, setup_experiment_logic

router = APIRouter()

@router.post("/experiment/setup", response_model=ExperimentSetupResponse)
def experiment_setup(req: ExperimentSetupRequest) -> ExperimentSetupResponse:
    return setup_experiment_logic(req)

@router.post("/experiment/cleanup")
def experiment_cleanup(req: ExperimentCleanupRequest):
    return cleanup_experiment_logic(req)
