from __future__ import annotations

import base64
import secrets
import sqlite3
from io import BytesIO

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import APP_TITLE, BASIC_AUTH_PASSWORD, BASIC_AUTH_USERNAME
from app.database import bootstrap_schema, db_cursor
from app.schemas import (
    ActivityPayload,
    AccountSelectionTogglePayload,
    BudgetLinePayload,
    BudgetLineUpdatePayload,
    FormSelectionPayload,
    ManualAccountPayload,
    SubComponentPayload,
)
from app.services.exports import build_excel_export, build_pdf_export
from app.services.rab import (
    activity_summary,
    add_manual_account,
    bootstrap_application_data,
    create_activity,
    create_budget_line,
    create_form_selection,
    create_sub_component,
    delete_activity,
    delete_budget_line,
    delete_form_selection,
    delete_sub_component,
    get_activity_state,
    list_activities,
    list_reference_data,
    toggle_account_selection,
    update_activity,
    update_budget_line,
    update_form_selection,
    update_sub_component,
)

app = FastAPI(title=APP_TITLE)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.middleware("http")
async def basic_auth_guard(request: Request, call_next):
    if not BASIC_AUTH_USERNAME or not BASIC_AUTH_PASSWORD or request.url.path == "/api/health":
        return await call_next(request)

    authorization = request.headers.get("Authorization", "")
    scheme, _, encoded_credentials = authorization.partition(" ")
    if scheme.lower() == "basic" and encoded_credentials:
        try:
            decoded = base64.b64decode(encoded_credentials).decode("utf-8")
            username, _, password = decoded.partition(":")
            if secrets.compare_digest(username, BASIC_AUTH_USERNAME) and secrets.compare_digest(password, BASIC_AUTH_PASSWORD):
                return await call_next(request)
        except (UnicodeDecodeError, ValueError):
            pass

    return Response(
        "Authentication required.",
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="RAB Workflow Assistant"'},
    )


@app.on_event("startup")
def startup() -> None:
    bootstrap_schema()
    with db_cursor() as connection:
        bootstrap_application_data(connection)


def _not_found_guard(result: object) -> object:
    if result is None:
        raise HTTPException(status_code=404, detail="Data tidak ditemukan.")
    return result


def _handle_db_error(error: Exception) -> None:
    if isinstance(error, ValueError):
        raise HTTPException(status_code=404, detail=str(error)) from error
    if isinstance(error, sqlite3.IntegrityError):
        raise HTTPException(status_code=400, detail=f"Operasi gagal: {error}") from error
    raise error


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "title": APP_TITLE,
        },
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/reference-data")
def get_reference_data() -> dict:
    with db_cursor() as connection:
        return list_reference_data(connection)


@app.get("/api/activities")
def get_activities() -> list[dict]:
    with db_cursor() as connection:
        return list_activities(connection)


@app.post("/api/activities")
def post_activity(payload: ActivityPayload) -> dict:
    try:
        with db_cursor() as connection:
            return create_activity(connection, payload)
    except Exception as error:
        _handle_db_error(error)


@app.get("/api/activities/{activity_id}")
def get_activity(activity_id: str) -> dict:
    try:
        with db_cursor() as connection:
            return get_activity_state(connection, activity_id)
    except Exception as error:
        _handle_db_error(error)


@app.patch("/api/activities/{activity_id}")
def patch_activity(activity_id: str, payload: ActivityPayload) -> dict:
    try:
        with db_cursor() as connection:
            return update_activity(connection, activity_id, payload)
    except Exception as error:
        _handle_db_error(error)


@app.delete("/api/activities/{activity_id}")
def remove_activity(activity_id: str) -> JSONResponse:
    with db_cursor() as connection:
        delete_activity(connection, activity_id)
    return JSONResponse({"status": "deleted"})


@app.get("/api/activities/{activity_id}/summary")
def get_activity_summary(activity_id: str) -> dict:
    with db_cursor() as connection:
        summary = activity_summary(connection, activity_id)
        return _not_found_guard(summary)


@app.post("/api/activities/{activity_id}/sub-components")
def post_sub_component(activity_id: str, payload: SubComponentPayload) -> dict:
    try:
        with db_cursor() as connection:
            return create_sub_component(connection, activity_id, payload)
    except Exception as error:
        _handle_db_error(error)


@app.patch("/api/sub-components/{sub_component_id}")
def patch_sub_component(sub_component_id: str, payload: SubComponentPayload) -> dict:
    try:
        with db_cursor() as connection:
            return update_sub_component(connection, sub_component_id, payload)
    except Exception as error:
        _handle_db_error(error)


@app.delete("/api/sub-components/{sub_component_id}")
def remove_sub_component(sub_component_id: str) -> dict:
    try:
        with db_cursor() as connection:
            return delete_sub_component(connection, sub_component_id)
    except Exception as error:
        _handle_db_error(error)


@app.post("/api/sub-components/{sub_component_id}/forms")
def post_form_selection(sub_component_id: str, payload: FormSelectionPayload) -> dict:
    try:
        with db_cursor() as connection:
            return create_form_selection(connection, sub_component_id, payload)
    except Exception as error:
        _handle_db_error(error)


@app.patch("/api/forms/{selection_id}")
def patch_form_selection(selection_id: str, payload: FormSelectionPayload) -> dict:
    try:
        with db_cursor() as connection:
            return update_form_selection(connection, selection_id, payload)
    except Exception as error:
        _handle_db_error(error)


@app.delete("/api/forms/{selection_id}")
def remove_form_selection(selection_id: str) -> dict:
    try:
        with db_cursor() as connection:
            return delete_form_selection(connection, selection_id)
    except Exception as error:
        _handle_db_error(error)


@app.patch("/api/accounts/{selection_id}/toggle")
def patch_account_toggle(selection_id: str, payload: AccountSelectionTogglePayload) -> dict:
    try:
        with db_cursor() as connection:
            return toggle_account_selection(connection, selection_id, payload.is_selected)
    except Exception as error:
        _handle_db_error(error)


@app.post("/api/sub-components/{sub_component_id}/manual-account")
def post_manual_account(sub_component_id: str, payload: ManualAccountPayload) -> dict:
    try:
        with db_cursor() as connection:
            return add_manual_account(connection, sub_component_id, payload)
    except Exception as error:
        _handle_db_error(error)


@app.post("/api/accounts/{selection_id}/lines")
def post_budget_line(selection_id: str, payload: BudgetLinePayload) -> dict:
    try:
        with db_cursor() as connection:
            return create_budget_line(connection, selection_id, payload)
    except Exception as error:
        _handle_db_error(error)


@app.patch("/api/lines/{line_id}")
def patch_budget_line(line_id: str, payload: BudgetLineUpdatePayload) -> dict:
    try:
        with db_cursor() as connection:
            return update_budget_line(connection, line_id, payload)
    except Exception as error:
        _handle_db_error(error)


@app.delete("/api/lines/{line_id}")
def remove_budget_line(line_id: str) -> dict:
    try:
        with db_cursor() as connection:
            return delete_budget_line(connection, line_id)
    except Exception as error:
        _handle_db_error(error)


@app.get("/api/activities/{activity_id}/export/xlsx")
def export_xlsx(activity_id: str) -> StreamingResponse:
    with db_cursor() as connection:
        binary = build_excel_export(connection, activity_id)
        state = get_activity_state(connection, activity_id)
    filename = f"RAB-{state['activity']['name'].replace(' ', '-')}.xlsx"
    return StreamingResponse(
        BytesIO(binary),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/activities/{activity_id}/export/pdf")
def export_pdf(activity_id: str) -> StreamingResponse:
    with db_cursor() as connection:
        binary = build_pdf_export(connection, activity_id)
        state = get_activity_state(connection, activity_id)
    filename = f"RAB-{state['activity']['name'].replace(' ', '-')}.pdf"
    return StreamingResponse(
        BytesIO(binary),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
