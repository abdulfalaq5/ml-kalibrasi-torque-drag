from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.services.templates import build_template

router = APIRouter(prefix="/api/templates", tags=["templates"])

NAMES = {"data-latih": "template_data_latih_TnD.xlsx", "sumur-baru": "template_sumur_baru_TnD.xlsx"}


@router.get("/{kind}.xlsx")
def template(kind: str):
    if kind not in NAMES:
        raise HTTPException(404, "Template tidak dikenal (data-latih | sumur-baru)")
    return Response(
        build_template(kind),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{NAMES[kind]}"'},
    )
