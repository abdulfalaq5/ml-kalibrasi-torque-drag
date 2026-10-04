from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.services.templates import build_template

router = APIRouter(prefix="/api/templates", tags=["templates"])

NAMES = {"training": "TnD_template_training.xlsx", "monitoring": "TnD_template_monitoring.xlsx"}
ALIASES = {"data-latih": "training", "sumur-baru": "monitoring"}  # tautan lama


@router.get("/{kind}.xlsx")
def template(kind: str):
    kind = ALIASES.get(kind, kind)
    if kind not in NAMES:
        raise HTTPException(404, "Unknown template (training | monitoring)")
    return Response(
        build_template(kind),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{NAMES[kind]}"'},
    )
