from flask import Blueprint, request

from app.core.response import fail, ok
from app.core.security import login_required
from app.services.report_service import get_report


reports_bp = Blueprint("reports", __name__)


@reports_bp.get("/<int:event_id>/report")
@login_required
def report(event_id: int):
    return ok(get_report(event_id))


@reports_bp.get("/<int:event_id>/report/export")
@login_required
def export_report(event_id: int):
    export_format = request.args.get("format", "html")
    if export_format not in {"html", "pdf"}:
        return fail("format 仅支持 html 或 pdf", 400)
    return ok(
        {
            "event_id": event_id,
            "format": export_format,
            "status": "reserved",
            "message": "报告导出接口已预留，后续实现 HTML/PDF 文件生成。",
        },
        message="export endpoint reserved",
    )

