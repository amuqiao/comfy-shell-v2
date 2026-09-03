from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.core.config.settings import ROOT_DIR

router = APIRouter(include_in_schema=False)


def _ui_html(api_prefix: str) -> str:
    template = (ROOT_DIR / "app" / "web" / "static" / "index.html").read_text(encoding="utf-8")
    return template.replace("__API_PREFIX__", api_prefix)


@router.get("/ui", include_in_schema=False)
@router.get("/ui/", include_in_schema=False)
async def ui(request: Request) -> HTMLResponse:
    return HTMLResponse(_ui_html(request.app.state.settings.service.api_prefix))
