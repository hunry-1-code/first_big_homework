from app.services.content_analysis_service import run_content_analysis


def run_analysis_pipeline(analysis_run_id: int) -> dict:
    return run_content_analysis(analysis_run_id)
