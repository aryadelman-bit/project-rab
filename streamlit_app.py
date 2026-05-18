from __future__ import annotations

import hmac
import html
import os
import sqlite3
import tempfile
from typing import Any

import pandas as pd
import streamlit as st

from app.config import DB_PATH
from app.database import bootstrap_schema, db_cursor
from app.schemas import (
    ActivityPayload,
    BudgetLinePayload,
    BudgetLineUpdatePayload,
    FormSelectionPayload,
    ManualAccountPayload,
    SubComponentPayload,
)
from app.services.cloud_backup import GitHubBackupConfig, download_database, upload_database
from app.services.exports import build_excel_export, build_pdf_export
from app.services.rab import (
    add_manual_account,
    bootstrap_application_data,
    create_activity,
    create_budget_line,
    create_form_selection,
    create_sub_component,
    delete_budget_line,
    delete_form_selection,
    delete_sub_component,
    get_activity_state,
    list_activities,
    toggle_account_selection,
    update_activity,
    update_budget_line,
    update_form_selection,
    update_sub_component,
)


def _safe_html(value: Any) -> str:
    return html.escape(str(value or ""))


def _inject_theme() -> None:
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

:root {
    --rab-ink: #172f34;
    --rab-muted: #66797d;
    --rab-line: rgba(23, 47, 52, 0.12);
    --rab-card: rgba(255, 255, 255, 0.84);
    --rab-card-strong: #ffffff;
    --rab-teal: #0e4f5c;
    --rab-mint: #dff3ed;
    --rab-sand: #f7f1e4;
    --rab-amber: #d9893b;
    --rab-red: #b73b3b;
    --rab-shadow: 0 18px 46px rgba(19, 45, 51, 0.11);
}

html, body, [class*="css"] {
    font-family: 'Plus Jakarta Sans', 'Segoe UI', sans-serif;
}

.stApp {
    color: var(--rab-ink);
    background:
        radial-gradient(circle at 12% 4%, rgba(217, 137, 59, 0.16), transparent 32rem),
        radial-gradient(circle at 88% 0%, rgba(14, 79, 92, 0.14), transparent 30rem),
        linear-gradient(135deg, #fbf7ee 0%, #f3efe5 45%, #edf5f1 100%);
}

section[data-testid="stSidebar"] {
    background:
        linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(247, 241, 228, 0.9)),
        radial-gradient(circle at 10% 10%, rgba(14, 79, 92, 0.12), transparent 16rem);
    border-right: 1px solid var(--rab-line);
}

section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
    gap: 0.85rem;
}

.block-container {
    max-width: 1360px;
    padding-top: 1.2rem;
    padding-bottom: 4rem;
}

h1, h2, h3 {
    letter-spacing: -0.04em;
}

div[data-testid="stExpander"] {
    border: 1px solid var(--rab-line);
    border-radius: 22px;
    background: rgba(255, 255, 255, 0.68);
    box-shadow: 0 10px 30px rgba(23, 47, 52, 0.06);
    overflow: hidden;
}

div[data-testid="stExpander"] summary {
    font-weight: 700;
}

div[data-testid="stMetric"] {
    background: var(--rab-card);
    border: 1px solid var(--rab-line);
    border-radius: 20px;
    padding: 1rem;
    box-shadow: 0 10px 24px rgba(23, 47, 52, 0.06);
}

.stButton > button,
.stDownloadButton > button {
    border-radius: 999px;
    border: 1px solid rgba(14, 79, 92, 0.22);
    background: #ffffff;
    color: var(--rab-teal);
    font-weight: 750;
    min-height: 2.7rem;
    box-shadow: 0 8px 18px rgba(23, 47, 52, 0.07);
}

.stButton > button[kind="primary"],
.stDownloadButton > button[kind="primary"] {
    background: linear-gradient(135deg, #0e4f5c, #147486);
    color: #ffffff;
    border-color: transparent;
}

.stButton > button:hover,
.stDownloadButton > button:hover {
    border-color: rgba(14, 79, 92, 0.45);
    transform: translateY(-1px);
}

div[data-testid="stTabs"] div[role="tablist"] {
    position: sticky;
    top: 5.4rem;
    z-index: 30;
    gap: 0.35rem;
    padding: 0.55rem;
    margin: 0.85rem 0 1.05rem;
    border: 1px solid var(--rab-line);
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.82);
    backdrop-filter: blur(18px);
    box-shadow: 0 12px 30px rgba(23, 47, 52, 0.09);
}

div[data-testid="stTabs"] button[role="tab"] {
    border-radius: 999px;
    font-weight: 750;
    color: var(--rab-muted);
}

div[data-testid="stTabs"] button[aria-selected="true"] {
    background: var(--rab-teal);
    color: #ffffff;
}

.rab-sidebar-brand {
    padding: 1rem 0.2rem 0.2rem;
}

.rab-sidebar-brand .brand-kicker {
    color: var(--rab-amber);
    font-size: 0.74rem;
    font-weight: 800;
    letter-spacing: 0.12em;
    text-transform: uppercase;
}

.rab-sidebar-brand .brand-title {
    color: var(--rab-ink);
    font-size: 1.25rem;
    font-weight: 850;
    letter-spacing: -0.04em;
    line-height: 1.1;
}

.rab-hero {
    border: 1px solid rgba(14, 79, 92, 0.12);
    border-radius: 30px;
    padding: 1.4rem 1.5rem;
    background:
        linear-gradient(135deg, rgba(255,255,255,0.9), rgba(255,255,255,0.63)),
        radial-gradient(circle at 92% 18%, rgba(217, 137, 59, 0.18), transparent 18rem);
    box-shadow: var(--rab-shadow);
}

.rab-hero-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    flex-wrap: wrap;
}

.rab-kicker {
    color: var(--rab-amber);
    font-size: 0.74rem;
    font-weight: 850;
    letter-spacing: 0.14em;
    text-transform: uppercase;
}

.rab-hero h1 {
    margin: 0.25rem 0 0.35rem;
    font-size: clamp(2rem, 4vw, 3.6rem);
    line-height: 0.98;
}

.rab-hero p {
    margin: 0;
    max-width: 760px;
    color: var(--rab-muted);
    font-size: 1rem;
}

.rab-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    border-radius: 999px;
    padding: 0.5rem 0.78rem;
    background: var(--rab-mint);
    color: var(--rab-teal);
    font-weight: 800;
    font-size: 0.82rem;
}

.rab-budget-rail {
    position: sticky;
    top: 0.65rem;
    z-index: 35;
    margin: 0.9rem 0 1rem;
    border: 1px solid rgba(14, 79, 92, 0.14);
    border-radius: 26px;
    padding: 0.8rem;
    background: rgba(255, 255, 255, 0.86);
    backdrop-filter: blur(18px);
    box-shadow: var(--rab-shadow);
}

.rab-budget-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.65rem;
}

.rab-budget-card {
    border-radius: 20px;
    padding: 0.85rem 1rem;
    background: rgba(247, 241, 228, 0.62);
    border: 1px solid rgba(23, 47, 52, 0.08);
}

.rab-budget-label {
    color: var(--rab-muted);
    font-size: 0.72rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

.rab-budget-value {
    margin-top: 0.22rem;
    color: var(--rab-ink);
    font-size: clamp(1.05rem, 2vw, 1.45rem);
    font-weight: 850;
    letter-spacing: -0.04em;
}

.rab-budget-card.safe .rab-budget-value {
    color: var(--rab-teal);
}

.rab-budget-card.danger .rab-budget-value {
    color: var(--rab-red);
}

.rab-progress-track {
    height: 0.55rem;
    margin: 0.75rem 0.1rem 0.1rem;
    border-radius: 999px;
    background: rgba(23, 47, 52, 0.09);
    overflow: hidden;
}

.rab-progress-fill {
    display: block;
    height: 100%;
    border-radius: inherit;
    background: linear-gradient(90deg, var(--rab-teal), #67b39f);
}

.rab-progress-fill.danger {
    background: linear-gradient(90deg, var(--rab-red), #d9893b);
}

.rab-steps {
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 0.65rem;
    margin: 0.85rem 0 0.45rem;
}

.rab-step {
    min-height: 104px;
    border: 1px solid var(--rab-line);
    border-radius: 22px;
    padding: 0.9rem;
    background: rgba(255, 255, 255, 0.68);
    box-shadow: 0 10px 24px rgba(23, 47, 52, 0.06);
}

.rab-step.done {
    background: linear-gradient(160deg, rgba(223, 243, 237, 0.94), rgba(255,255,255,0.68));
    border-color: rgba(14, 79, 92, 0.24);
}

.rab-step.current {
    background: linear-gradient(160deg, rgba(255,255,255,0.94), rgba(247, 241, 228, 0.9));
    border-color: rgba(217, 137, 59, 0.5);
    box-shadow: 0 16px 34px rgba(217, 137, 59, 0.12);
}

.rab-step-index {
    width: 2rem;
    height: 2rem;
    display: grid;
    place-items: center;
    border-radius: 999px;
    background: rgba(23, 47, 52, 0.08);
    color: var(--rab-ink);
    font-weight: 850;
    font-size: 0.82rem;
}

.rab-step.done .rab-step-index {
    background: var(--rab-teal);
    color: #ffffff;
}

.rab-step.current .rab-step-index {
    background: var(--rab-amber);
    color: #ffffff;
}

.rab-step-title {
    margin-top: 0.65rem;
    font-weight: 850;
    letter-spacing: -0.03em;
}

.rab-step-caption {
    margin-top: 0.18rem;
    color: var(--rab-muted);
    font-size: 0.82rem;
    line-height: 1.35;
}

.rab-next-action {
    margin: 0.7rem 0 1rem;
    padding: 0.95rem 1.05rem;
    border-radius: 22px;
    border: 1px solid rgba(14, 79, 92, 0.14);
    background: rgba(255, 255, 255, 0.72);
    color: var(--rab-muted);
}

.rab-next-action strong {
    color: var(--rab-ink);
}

.rab-section-title {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    margin: 0.35rem 0 0.8rem;
}

.rab-section-title h2 {
    margin: 0;
    font-size: 1.35rem;
}

.rab-section-title p {
    margin: 0.22rem 0 0;
    color: var(--rab-muted);
    font-size: 0.92rem;
}

.rab-account-card {
    padding: 0.4rem 0;
}

@media (max-width: 1100px) {
    .rab-steps {
        grid-template-columns: repeat(3, minmax(0, 1fr));
    }
}

@media (max-width: 760px) {
    .block-container {
        padding-left: 1rem;
        padding-right: 1rem;
    }

    .rab-budget-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .rab-steps {
        grid-template-columns: 1fr;
    }

    div[data-testid="stTabs"] div[role="tablist"] {
        top: 6rem;
        border-radius: 24px;
    }
}
</style>
        """,
        unsafe_allow_html=True,
    )


st.set_page_config(
    page_title="RAB Workflow Assistant",
    page_icon="RAB",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _bootstrap() -> None:
    _restore_cloud_backup_on_startup()
    bootstrap_schema()
    with db_cursor() as connection:
        bootstrap_application_data(connection)


@st.cache_resource(show_spinner=False)
def _boot_once() -> bool:
    _bootstrap()
    return True


def _app_password() -> str | None:
    return _secret("APP_PASSWORD") or os.getenv("STREAMLIT_APP_PASSWORD")


def _secret(name: str) -> str | None:
    try:
        value = st.secrets.get(name)
        if value:
            return str(value)
    except Exception:
        pass
    return None


def _backup_config() -> GitHubBackupConfig | None:
    token = _secret("RAB_BACKUP_TOKEN") or os.getenv("RAB_BACKUP_TOKEN")
    repo = _secret("RAB_BACKUP_REPO") or os.getenv("RAB_BACKUP_REPO")
    if not token or not repo:
        return None
    return GitHubBackupConfig(
        token=token,
        repo=repo,
        branch=_secret("RAB_BACKUP_BRANCH") or os.getenv("RAB_BACKUP_BRANCH") or "main",
        path=_secret("RAB_BACKUP_PATH") or os.getenv("RAB_BACKUP_PATH") or "rab-state/rab.db",
    )


def _restore_cloud_backup_on_startup() -> None:
    config = _backup_config()
    if not config:
        return

    try:
        restored = download_database(config, DB_PATH)
    except Exception as exc:
        st.session_state.backup_warning = f"Restore backup cloud gagal: {exc}"
        return

    if restored:
        st.session_state.backup_status = "Backup cloud berhasil dipulihkan saat app start."


def _sync_cloud_backup(reason: str) -> None:
    config = _backup_config()
    if not config:
        return

    try:
        upload_database(config, DB_PATH, reason)
        st.session_state.backup_status = "Autosave cloud berhasil."
        st.session_state.pop("backup_warning", None)
    except Exception as exc:
        st.session_state.backup_warning = f"Autosave cloud gagal: {exc}"


def _validate_sqlite_bytes(data: bytes) -> None:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as temporary_file:
        temporary_file.write(data)
        temporary_name = temporary_file.name

    try:
        connection = sqlite3.connect(temporary_name)
        try:
            connection.execute("SELECT name FROM sqlite_master LIMIT 1").fetchall()
        finally:
            connection.close()
    finally:
        try:
            os.remove(temporary_name)
        except OSError:
            pass


def _password_gate() -> None:
    expected_password = _app_password()
    if not expected_password:
        return

    if st.session_state.get("authenticated"):
        return

    st.title("RAB Workflow Assistant")
    password = st.text_input("Password", type="password")
    if st.button("Masuk", type="primary"):
        if hmac.compare_digest(password, expected_password):
            st.session_state.authenticated = True
            st.rerun()
        st.error("Password belum sesuai.")
    st.stop()


def _rupiah(value: float | int | None) -> str:
    return f"Rp {float(value or 0):,.0f}".replace(",", ".")


def _number(value: float | int | None) -> str:
    return f"{float(value or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _load_activities() -> list[dict[str, Any]]:
    with db_cursor() as connection:
        return list_activities(connection)


def _load_activity(activity_id: str) -> dict[str, Any]:
    with db_cursor() as connection:
        return get_activity_state(connection, activity_id)


def _mutate(callback, *args, **kwargs) -> None:
    with db_cursor() as connection:
        callback(connection, *args, **kwargs)
    _sync_cloud_backup("Autosave RAB database")
    st.rerun()


def _mutate_batch(callback) -> None:
    with db_cursor() as connection:
        callback(connection)
    _sync_cloud_backup("Autosave RAB database")
    st.rerun()


def _create_activity_and_select(payload: ActivityPayload) -> None:
    with db_cursor() as connection:
        state = create_activity(connection, payload)
    _sync_cloud_backup("Autosave RAB database")
    st.session_state.activity_id = state["activity"]["id"]
    st.rerun()


def _reference_options(reference: dict[str, Any], field: dict[str, Any], values: dict[str, Any], activity: dict[str, Any]) -> list[str]:
    locations = reference.get("locations", {})
    reference_key = field.get("reference_key")
    current = values.get(field["name"], field.get("default", ""))

    if reference_key == "cities_by_province":
        if field.get("province_source") == "activity_default_province":
            province = activity.get("default_province") or ""
        else:
            province = values.get(field.get("province_source_field", ""), "")
        options = list((locations.get("cities_by_province") or {}).get(province, []))
        if not options:
            options = list(locations.get("cities", []))
    else:
        options = list(locations.get(reference_key, []))

    if current and current not in options:
        options.insert(0, current)
    return options


def _select_index(options: list[Any], value: Any) -> int:
    try:
        return options.index(value)
    except ValueError:
        return 0


def _is_visible(field: dict[str, Any], values: dict[str, Any]) -> bool:
    conditions = field.get("visible_when") or {}
    return all(str(values.get(key)) == str(expected) for key, expected in conditions.items())


def _render_parameter_fields(
    schema: list[dict[str, Any]],
    initial_values: dict[str, Any],
    reference: dict[str, Any],
    activity: dict[str, Any],
    key_prefix: str,
) -> dict[str, Any]:
    values: dict[str, Any] = {}

    for field in schema:
        name = field["name"]
        default = initial_values.get(name, field.get("default", ""))

        preview_values = {**initial_values, **values}
        if not _is_visible(field, preview_values):
            continue

        key = f"{key_prefix}-{name}"
        field_type = field.get("type")

        if field_type == "checkbox":
            values[name] = st.checkbox(field["label"], value=bool(default), key=key)
            continue

        if field_type == "number":
            values[name] = st.number_input(field["label"], value=float(default or 0), min_value=0.0, step=1.0, key=key)
            continue

        if field_type == "select" or field.get("reference_key"):
            if field.get("reference_key"):
                options = _reference_options(reference, field, {**initial_values, **values}, activity, )
            else:
                options = [option["value"] if isinstance(option, dict) else option for option in field.get("options", [])]
            if not options:
                values[name] = st.text_input(field["label"], value=str(default or ""), key=key)
                continue
            values[name] = st.selectbox(field["label"], options, index=_select_index(options, default), key=key)
            continue

        values[name] = st.text_input(field["label"], value=str(default or ""), key=key)

    return values


def _activity_form(reference: dict[str, Any], activity: dict[str, Any] | None = None, key_prefix: str = "activity") -> ActivityPayload:
    locations = reference.get("locations", {})
    provinces = list(locations.get("provinces", [])) or ["DKI JAKARTA"]
    province = activity.get("default_province") if activity else "DKI JAKARTA"
    province = province if province in provinces else provinces[0]
    cities = list((locations.get("cities_by_province") or {}).get(province, [])) or list(locations.get("cities", [])) or ["JAKARTA"]
    origin_city = activity.get("origin_city") if activity else "JAKARTA"
    origin_city = origin_city if origin_city in cities else cities[0]

    name = st.text_input("Nama kegiatan", value=(activity or {}).get("name", "Kegiatan Baru"), key=f"{key_prefix}-name")
    fiscal_year = st.number_input(
        "Tahun anggaran",
        value=int((activity or {}).get("fiscal_year", 2026)),
        min_value=2024,
        max_value=2100,
        key=f"{key_prefix}-fiscal-year",
    )
    budget_ceiling = st.number_input(
        "Pagu anggaran",
        value=float((activity or {}).get("budget_ceiling", 50_000_000)),
        min_value=1.0,
        step=1_000_000.0,
        key=f"{key_prefix}-budget-ceiling",
    )
    default_province = st.selectbox("Provinsi default", provinces, index=_select_index(provinces, province), key=f"{key_prefix}-province")
    cities = list((locations.get("cities_by_province") or {}).get(default_province, [])) or cities
    origin_city = origin_city if origin_city in cities else cities[0]
    origin_city = st.selectbox("Kota asal", cities, index=_select_index(cities, origin_city), key=f"{key_prefix}-origin-city")
    description = st.text_area(
        "Deskripsi",
        value=(activity or {}).get("description", "Kegiatan untuk disusun melalui workflow RAB."),
        key=f"{key_prefix}-description",
    )

    return ActivityPayload(
        name=name,
        description=description,
        fiscal_year=int(fiscal_year),
        budget_ceiling=float(budget_ceiling),
        default_province=default_province,
        origin_city=origin_city,
    )


def _form_definition(reference: dict[str, Any], form_code: str) -> dict[str, Any] | None:
    for form in reference.get("forms", []):
        if form["code"] == form_code:
            return form
    return None


def _render_app_header(state: dict[str, Any]) -> None:
    activity = state["activity"]
    sub_count = len(state.get("sub_components", []))
    form_count = sum(len(sub_component.get("forms", [])) for sub_component in state.get("sub_components", []))
    status = "Siap disusun" if sub_count else "Mulai dari tahapan"
    st.markdown(
        f"""
<div class="rab-hero">
  <div class="rab-hero-top">
    <div>
      <div class="rab-kicker">Assistant Penyusunan RAB</div>
      <h1>{_safe_html(activity.get("name"))}</h1>
      <p>Susun anggaran dari alur kegiatan: mulai dari pagu, tahapan, bentuk kegiatan, rekomendasi akun, detail belanja, sampai validasi sisa pagu.</p>
    </div>
    <div class="rab-pill">{_safe_html(status)} - {sub_count} tahapan - {form_count} bentuk</div>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def _render_budget_control(summary: dict[str, Any]) -> None:
    utilization = float(summary.get("utilization_percent") or 0)
    progress = max(0, min(utilization, 100))
    remaining = float(summary.get("remaining_budget") or 0)
    status_label = "Aman" if remaining >= 0 else "Melebihi pagu"
    status_class = "safe" if remaining >= 0 else "danger"
    progress_class = "" if remaining >= 0 else "danger"

    st.markdown(
        f"""
<div class="rab-budget-rail">
  <div class="rab-budget-grid">
    <div class="rab-budget-card">
      <div class="rab-budget-label">Pagu</div>
      <div class="rab-budget-value">{_safe_html(_rupiah(summary.get("budget_ceiling")))}</div>
    </div>
    <div class="rab-budget-card">
      <div class="rab-budget-label">Total RAB</div>
      <div class="rab-budget-value">{_safe_html(_rupiah(summary.get("grand_total")))}</div>
    </div>
    <div class="rab-budget-card {status_class}">
      <div class="rab-budget-label">Sisa Pagu</div>
      <div class="rab-budget-value">{_safe_html(_rupiah(remaining))}</div>
    </div>
    <div class="rab-budget-card {status_class}">
      <div class="rab-budget-label">Status</div>
      <div class="rab-budget-value">{_safe_html(status_label)} - {_safe_html(_number(utilization))}%</div>
    </div>
  </div>
  <div class="rab-progress-track"><span class="rab-progress-fill {progress_class}" style="width: {progress:.2f}%"></span></div>
</div>
        """,
        unsafe_allow_html=True,
    )

    if summary.get("warnings"):
        st.warning("\n".join(summary["warnings"]))


def _activity_progress(state: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    sub_components = state.get("sub_components", [])
    summary = state.get("summary", {})
    forms = [form for sub_component in sub_components for form in sub_component.get("forms", [])]
    accounts = [account for sub_component in sub_components for account in sub_component.get("accounts", []) if account.get("is_selected")]
    lines = [line for account in accounts for line in account.get("lines", [])]
    remaining = float(summary.get("remaining_budget") or 0)

    steps = [
        {
            "title": "Kegiatan",
            "caption": "Nama, tahun, pagu",
            "done": bool(state.get("activity", {}).get("name") and float(summary.get("budget_ceiling") or 0) > 0),
        },
        {
            "title": "Tahapan",
            "caption": f"{len(sub_components)} sub komponen",
            "done": len(sub_components) > 0,
        },
        {
            "title": "Bentuk",
            "caption": f"{len(forms)} bentuk kegiatan",
            "done": len(forms) > 0,
        },
        {
            "title": "Akun",
            "caption": f"{len(accounts)} akun aktif",
            "done": len(accounts) > 0,
        },
        {
            "title": "Detail",
            "caption": f"{len(lines)} item belanja",
            "done": len(lines) > 0,
        },
        {
            "title": "Validasi",
            "caption": "Pagu aman" if remaining >= 0 else "Perlu koreksi",
            "done": remaining >= 0,
        },
    ]

    if not sub_components:
        next_action = "Lanjutkan dengan membuka tab Tahapan & Bentuk, lalu tambahkan tahapan pertama."
    elif not forms:
        next_action = "Pilih bentuk kegiatan pada tahapan aktif agar sistem bisa merekomendasikan akun belanja."
    elif not accounts:
        next_action = "Cek rekomendasi akun dan aktifkan akun belanja yang relevan."
    elif not lines:
        next_action = "Isi detail belanja, volume, satuan, dan harga satuan."
    elif remaining < 0:
        next_action = "Total sudah melewati pagu. Turunkan volume atau harga pada detail belanja."
    else:
        next_action = "RAB sudah siap direview. Gunakan Ringkasan atau export Excel/PDF."

    return steps, next_action


def _render_workflow_overview(state: dict[str, Any]) -> None:
    steps, next_action = _activity_progress(state)
    current_index = next((index for index, step in enumerate(steps) if not step["done"]), len(steps) - 1)
    cards = []
    for index, step in enumerate(steps, start=1):
        class_name = "done" if step["done"] else "current" if index - 1 == current_index else ""
        cards.append(
            f"""
<div class="rab-step {class_name}">
  <div class="rab-step-index">{index:02d}</div>
  <div class="rab-step-title">{_safe_html(step["title"])}</div>
  <div class="rab-step-caption">{_safe_html(step["caption"])}</div>
</div>
            """
        )

    st.markdown(
        f"""
<div class="rab-steps">
  {''.join(cards)}
</div>
<div class="rab-next-action"><strong>Arah berikutnya:</strong> {_safe_html(next_action)}</div>
        """,
        unsafe_allow_html=True,
    )


def _section_title(title: str, caption: str | None = None) -> None:
    caption_html = f"<p>{_safe_html(caption)}</p>" if caption else ""
    st.markdown(
        f"""
<div class="rab-section-title">
  <div>
    <h2>{_safe_html(title)}</h2>
    {caption_html}
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def _render_sidebar(state: dict[str, Any]) -> str | None:
    st.sidebar.markdown(
        """
<div class="rab-sidebar-brand">
  <div class="brand-kicker">RAB Workflow</div>
  <div class="brand-title">Budget Assistant</div>
</div>
        """,
        unsafe_allow_html=True,
    )
    _render_data_safety_tools()
    activities = _load_activities()
    if not activities:
        st.sidebar.info("Belum ada kegiatan.")
        return None

    activity_labels = {f"{item['name']} - {_rupiah(item['summary']['grand_total'])}": item["id"] for item in activities}
    current_id = st.session_state.get("activity_id") or activities[0]["id"]
    current_label = next((label for label, value in activity_labels.items() if value == current_id), next(iter(activity_labels)))
    selected_label = st.sidebar.selectbox("Kegiatan", list(activity_labels), index=_select_index(list(activity_labels), current_label))
    st.session_state.activity_id = activity_labels[selected_label]
    return st.session_state.activity_id


def _render_data_safety_tools() -> None:
    with st.sidebar.expander("Backup data", expanded=False):
        st.caption("Streamlit Cloud tidak menjamin penyimpanan file lokal. Download backup berkala atau aktifkan autosave cloud.")

        if st.session_state.get("backup_status"):
            st.success(st.session_state["backup_status"])
        if st.session_state.get("backup_warning"):
            st.warning(st.session_state["backup_warning"])

        if DB_PATH.exists():
            st.download_button(
                "Download backup database",
                data=DB_PATH.read_bytes(),
                file_name="rab-backup.db",
                mime="application/octet-stream",
                key="download-db-backup",
            )
        else:
            st.info("Database lokal belum tersedia.")

        if _backup_config():
            if st.button("Backup sekarang ke cloud", key="backup-now-cloud"):
                _sync_cloud_backup("Manual RAB database backup")
                st.rerun()

        uploaded = st.file_uploader("Restore dari backup .db", type=["db"], key="restore-db-uploader")
        if uploaded and st.button("Restore backup", key="restore-db-button"):
            data = uploaded.getvalue()
            try:
                _validate_sqlite_bytes(data)
                DB_PATH.parent.mkdir(parents=True, exist_ok=True)
                if DB_PATH.exists():
                    DB_PATH.replace(DB_PATH.with_suffix(".db.before-restore"))
                DB_PATH.write_bytes(data)
                _sync_cloud_backup("Restore RAB database from uploaded backup")
                st.session_state.backup_status = "Backup berhasil direstore."
                st.cache_resource.clear()
                st.rerun()
            except Exception as exc:
                st.error(f"Restore gagal: {exc}")

        if not _backup_config():
            st.info("Autosave cloud belum aktif. Tambahkan secrets `RAB_BACKUP_TOKEN` dan `RAB_BACKUP_REPO` untuk backup otomatis.")


def _render_summary(summary: dict[str, Any]) -> None:
    cols = st.columns(4)
    cols[0].metric("Pagu", _rupiah(summary.get("budget_ceiling")))
    cols[1].metric("Total RAB", _rupiah(summary.get("grand_total")))
    cols[2].metric("Sisa pagu", _rupiah(summary.get("remaining_budget")))
    cols[3].metric("Utilisasi", f"{_number(summary.get('utilization_percent'))}%")
    if summary.get("warnings"):
        st.warning("\n".join(summary["warnings"]))


def _render_activity_editor(state: dict[str, Any]) -> None:
    activity = state["activity"]
    reference = state["reference"]

    _section_title("Informasi kegiatan", "Edit nama kegiatan, tahun anggaran, pagu, dan lokasi asal.")
    with st.expander("Form kegiatan aktif", expanded=True):
        payload = _activity_form(reference, activity, key_prefix=f"edit-activity-{activity['id']}")
        if st.button("Simpan kegiatan", type="primary", key=f"save-activity-{activity['id']}"):
            _mutate(update_activity, activity["id"], payload)


def _render_subcomponents(state: dict[str, Any], key_prefix: str) -> dict[str, Any] | None:
    sub_components = state.get("sub_components", [])
    _section_title("Tahapan kegiatan", "Buat sub komponen A, B, C, dan seterusnya sesuai proses kegiatan.")

    with st.expander("Tambah tahapan", expanded=not sub_components):
        name = st.text_input("Nama tahapan baru", value="Tahapan Baru", key=f"{key_prefix}-new-sub-name")
        notes = st.text_area("Catatan", value="Tambahkan tujuan atau catatan singkat tahapan ini.", key=f"{key_prefix}-new-sub-notes")
        if st.button("Tambah tahapan", type="primary", key=f"{key_prefix}-add-sub"):
            _mutate(create_sub_component, state["activity"]["id"], SubComponentPayload(name=name, notes=notes))

    if not sub_components:
        st.info("Tambahkan tahapan pertama agar bisa lanjut memilih bentuk kegiatan.")
        return None

    labels = {f"{item['code']}. {item['name']} - {_rupiah(item.get('sub_total'))}": item for item in sub_components}
    selected_label = st.selectbox("Sub komponen aktif", list(labels), key=f"{key_prefix}-active-sub-component")
    selected = labels[selected_label]

    with st.expander("Edit tahapan aktif"):
        name = st.text_input("Nama tahapan", value=selected["name"], key=f"{key_prefix}-sub-name-{selected['id']}")
        notes = st.text_area("Catatan tahapan", value=selected.get("notes") or "", key=f"{key_prefix}-sub-notes-{selected['id']}")
        col_save, col_delete = st.columns([1, 1])
        if col_save.button("Simpan tahapan", key=f"{key_prefix}-save-sub-{selected['id']}"):
            _mutate(update_sub_component, selected["id"], SubComponentPayload(name=name, notes=notes))
        if col_delete.button("Hapus tahapan", key=f"{key_prefix}-delete-sub-{selected['id']}"):
            _mutate(delete_sub_component, selected["id"])

    return selected


def _render_forms(state: dict[str, Any], sub_component: dict[str, Any]) -> None:
    reference = state["reference"]
    activity = state["activity"]
    forms = reference.get("forms", [])
    form_options = {form["name"]: form["code"] for form in forms}

    _section_title("Bentuk kegiatan", f"Tahapan aktif: {sub_component.get('code')}. {sub_component.get('name')}")

    with st.expander("Tambah bentuk kegiatan", expanded=not sub_component.get("forms")):
        selected_name = st.selectbox("Jenis bentuk kegiatan", list(form_options), key=f"new-form-{sub_component['id']}")
        form_code = form_options[selected_name]
        definition = _form_definition(reference, form_code) or {}
        attributes = _render_parameter_fields(
            definition.get("parameter_schema", []),
            {},
            reference,
            activity,
            f"new-{sub_component['id']}-{form_code}",
        )
        if st.button("Simpan bentuk kegiatan", type="primary", key=f"add-form-{sub_component['id']}"):
            _mutate(create_form_selection, sub_component["id"], FormSelectionPayload(form_code=form_code, attributes=attributes))

    for selection in sub_component.get("forms", []):
        with st.expander(selection["form_name"], expanded=False):
            current_code = selection["form_code"]
            current_name = next((name for name, code in form_options.items() if code == current_code), next(iter(form_options)))
            selected_name = st.selectbox("Jenis bentuk kegiatan", list(form_options), index=_select_index(list(form_options), current_name), key=f"form-code-{selection['id']}")
            form_code = form_options[selected_name]
            definition = _form_definition(reference, form_code) or {}
            attributes = _render_parameter_fields(
                definition.get("parameter_schema", []),
                selection.get("attributes", {}),
                reference,
                activity,
                f"existing-{selection['id']}-{form_code}",
            )
            col_save, col_delete = st.columns([1, 1])
            if col_save.button("Simpan bentuk kegiatan", key=f"save-form-{selection['id']}"):
                _mutate(update_form_selection, selection["id"], FormSelectionPayload(form_code=form_code, attributes=attributes))
            if col_delete.button("Hapus bentuk kegiatan", key=f"delete-form-{selection['id']}"):
                _mutate(delete_form_selection, selection["id"])


def _render_accounts(state: dict[str, Any], sub_component: dict[str, Any]) -> None:
    _section_title("Rekomendasi akun", "Akun muncul berdasarkan bentuk kegiatan yang dipilih, bukan dipilih manual dari awal.")
    reference = state["reference"]
    account_options = {f"{account['code']} - {account['name']}": account["code"] for account in reference.get("accounts", [])}

    for account in sub_component.get("accounts", []):
        with st.container(border=True):
            col_a, col_b, col_c = st.columns([2, 1, 1])
            col_a.markdown(f"**{account['account_code']} - {account['account_name']}**")
            col_b.write(_rupiah(account.get("account_total")))
            selected = col_c.checkbox("Aktif", value=bool(account.get("is_selected")), key=f"account-active-{account['id']}")
            if selected != bool(account.get("is_selected")):
                _mutate(toggle_account_selection, account["id"], selected)
            st.caption(account.get("recommendation_reason") or "Akun ditambahkan manual.")

    with st.expander("Tambah akun manual"):
        selected_account = st.selectbox("Akun belanja", list(account_options), key=f"manual-account-{sub_component['id']}")
        if st.button("Tambah akun manual", key=f"add-manual-{sub_component['id']}"):
            _mutate(add_manual_account, sub_component["id"], ManualAccountPayload(account_code=account_options[selected_account]))


def _render_budget_lines(sub_component: dict[str, Any]) -> None:
    _section_title("Detail belanja", "Isi volume, satuan, dan harga satuan. Subtotal dihitung otomatis saat disimpan.")

    for account in sub_component.get("accounts", []):
        with st.expander(f"{account['account_code']} - {account['account_name']} ({_rupiah(account.get('account_total'))})", expanded=False):
            lines = account.get("lines", [])
            if lines:
                rows = [
                    {
                        "id": line["id"],
                        "Detail belanja": line["item_name"],
                        "Spesifikasi": line.get("specification") or "",
                        "Volume": float(line.get("volume") or 0),
                        "Satuan": line.get("unit") or "",
                        "Harga satuan": float(line.get("unit_price") or 0),
                        "Subtotal": float(line.get("amount") or 0),
                        "Catatan referensi": line.get("suggestion_note") or "",
                    }
                    for line in lines
                ]
                edited = st.data_editor(
                    pd.DataFrame(rows),
                    hide_index=True,
                    disabled=["id", "Subtotal", "Catatan referensi"],
                    column_config={
                        "id": None,
                        "Volume": st.column_config.NumberColumn("Volume", min_value=0, step=1, format="%.2f"),
                        "Harga satuan": st.column_config.NumberColumn("Harga satuan", min_value=0, step=1000, format="Rp %.0f"),
                        "Subtotal": st.column_config.NumberColumn("Subtotal", format="Rp %.0f"),
                    },
                    key=f"lines-{account['id']}",
                    use_container_width=True,
                )
                if st.button("Simpan perubahan detail", key=f"save-lines-{account['id']}"):
                    def save_rows(connection):
                        for row in edited.to_dict(orient="records"):
                            update_budget_line(
                                connection,
                                row["id"],
                                BudgetLineUpdatePayload(
                                    item_name=row["Detail belanja"],
                                    specification=row["Spesifikasi"],
                                    volume=float(row["Volume"]),
                                    unit=row["Satuan"],
                                    unit_price=float(row["Harga satuan"]),
                                ),
                            )

                    _mutate_batch(save_rows)

                line_labels = {f"{line['item_name']} - {_rupiah(line.get('amount'))}": line["id"] for line in lines}
                selected_line = st.selectbox("Pilih detail untuk dihapus", list(line_labels), key=f"delete-line-choice-{account['id']}")
                if st.button("Hapus detail terpilih", key=f"delete-line-{account['id']}"):
                    _mutate(delete_budget_line, line_labels[selected_line])
            else:
                st.info("Belum ada detail pada akun ini.")

            st.markdown("**Tambah detail manual**")
            col_1, col_2, col_3, col_4 = st.columns(4)
            item_name = col_1.text_input("Detail", value="Detail belanja tambahan", key=f"manual-name-{account['id']}")
            volume = col_2.number_input("Volume", value=1.0, min_value=0.0, step=1.0, key=f"manual-volume-{account['id']}")
            unit = col_3.text_input("Satuan", value="Paket", key=f"manual-unit-{account['id']}")
            unit_price = col_4.number_input("Harga satuan", value=0.0, min_value=0.0, step=1000.0, key=f"manual-price-{account['id']}")
            specification = st.text_input("Spesifikasi", value="", key=f"manual-spec-{account['id']}")
            if st.button("Tambah detail manual", key=f"manual-add-{account['id']}"):
                _mutate(
                    create_budget_line,
                    account["id"],
                    BudgetLinePayload(
                        item_name=item_name,
                        specification=specification,
                        volume=float(volume),
                        unit=unit,
                        unit_price=float(unit_price),
                    ),
                )


def _render_downloads(activity_id: str) -> None:
    with db_cursor() as connection:
        state = get_activity_state(connection, activity_id)
        excel_data = build_excel_export(connection, activity_id)
        pdf_data = build_pdf_export(connection, activity_id)
    filename = state["activity"]["name"].replace(" ", "-")
    with st.container(border=True):
        col_title, col_xlsx, col_pdf = st.columns([2.2, 1, 1])
        col_title.markdown("**Export dokumen**")
        col_title.caption("Unduh hasil RAB untuk review atau arsip.")
        col_xlsx.download_button(
            "Export Excel",
            data=excel_data,
            file_name=f"RAB-{filename}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
        col_pdf.download_button(
            "Export PDF",
            data=pdf_data,
            file_name=f"RAB-{filename}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )


def main() -> None:
    _inject_theme()
    _password_gate()
    _boot_once()

    activities = _load_activities()
    if not activities:
        with db_cursor() as connection:
            create_activity(connection, ActivityPayload(name="Kegiatan Baru", budget_ceiling=50_000_000))
        st.rerun()

    selected_activity_id = _render_sidebar({"activities": activities}) or activities[0]["id"]
    state = _load_activity(selected_activity_id)

    _render_app_header(state)
    _render_budget_control(state["summary"])
    _render_workflow_overview(state)
    _render_downloads(selected_activity_id)

    tabs = st.tabs(["01 Kegiatan", "02 Tahapan & Bentuk", "03 Akun & Detail", "04 Ringkasan"])
    with tabs[0]:
        _render_activity_editor(state)
        st.divider()
        _section_title("Tambah kegiatan baru", "Buat kegiatan terpisah jika ingin menyusun RAB baru dari awal.")
        with st.expander("Buat kegiatan"):
            payload = _activity_form(state["reference"], key_prefix="create-activity")
            if st.button("Buat kegiatan", type="primary", key="create-activity-button"):
                _create_activity_and_select(payload)

    with tabs[1]:
        selected_sub = _render_subcomponents(state, key_prefix="forms-tab")
        if selected_sub:
            _render_forms(state, selected_sub)

    with tabs[2]:
        selected_sub = _render_subcomponents(state, key_prefix="budget-tab")
        if selected_sub:
            _render_accounts(state, selected_sub)
            _render_budget_lines(selected_sub)

    with tabs[3]:
        _section_title("Ringkasan RAB", "Pantau total per sub komponen dan per akun belanja.")
        st.markdown("**Total per sub komponen**")
        st.dataframe(pd.DataFrame(state["summary"].get("totals_by_sub_component", [])), use_container_width=True)
        st.markdown("**Total per akun**")
        st.dataframe(pd.DataFrame(state["summary"].get("totals_by_account", [])), use_container_width=True)


if __name__ == "__main__":
    main()
