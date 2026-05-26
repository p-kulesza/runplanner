from __future__ import annotations

import calendar
import base64
import hmac
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from time import time

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from route_engine.gpx_library import (
    delete_route_file,
    get_supabase_client,
    import_gpx_file,
    load_routes,
    MAX_GPX_BYTES,
    route_analysis,
    route_gpx_bytes,
    save_routes,
    supabase_configured,
)
from route_engine.map_view import build_polyline_map


st.set_page_config(page_title="Kolejny GPX", layout="wide")

BG = "#EDE0C9"
SURFACE = "#F2E7D2"
SURFACE_SOFT = "#EFE2CC"
SURFACE_RAISED = "#E8D9BF"
TEXT = "#20263A"
MUTED = "#5A6278"
BLUE = "#1830B7"
BLUE_SOFT = "#DCE2FF"
CREAM = "#F5EBD8"
CREAM_SOFT = "#FBF5EA"
HAIRLINE = "#B4C0EE"
SHADOW = "0 8px 24px rgba(32, 38, 58, 0.05)"
PACE_PATTERN = re.compile(r"^\d{2}:\d{2}$")
LOGO_PATH = Path(__file__).resolve().parent / "assets" / "kolejny-logo.jpg"
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCK_SECONDS = 300
MAX_TEXT_FIELD_LENGTH = 120
MAX_PACER_NAME_LENGTH = 120
MONTH_NAMES = {
    1: "stycze\u0144",
    2: "luty",
    3: "marzec",
    4: "kwiecie\u0144",
    5: "maj",
    6: "czerwiec",
    7: "lipiec",
    8: "sierpie\u0144",
    9: "wrzesie\u0144",
    10: "pa\u017adziernik",
    11: "listopad",
    12: "grudzie\u0144",
}


def logo_data_uri() -> str | None:
    if not LOGO_PATH.exists():
        return None
    encoded = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def require_authentication() -> None:
    st.session_state.setdefault("is_authenticated", False)
    st.session_state.setdefault("login_attempts", 0)
    st.session_state.setdefault("login_lock_until", 0.0)
    configured_password = st.secrets.get("app_password")

    if st.session_state["is_authenticated"]:
        return

    if not configured_password:
        st.error("Brak konfiguracji hasła aplikacji. Ustaw `app_password` w sekretach środowiska.")
        st.stop()

    st.markdown(
        """
        <div class="login-shell">
            <div class="login-hero">
                <h1>Kolejny GPX</h1>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="section-title">Logowanie</div>', unsafe_allow_html=True)
    now = time()
    lock_until = float(st.session_state.get("login_lock_until", 0.0))
    if lock_until > now:
        remaining = int(lock_until - now)
        st.warning(f"Zbyt wiele prób logowania. Spróbuj ponownie za około {remaining} s.")
        st.stop()

    password = st.text_input("Has\u0142o", type="password", key="login_password")
    if st.button("Wejd\u017a", use_container_width=True):
        if hmac.compare_digest(password, str(configured_password)):
            st.session_state["is_authenticated"] = True
            st.session_state["login_attempts"] = 0
            st.session_state["login_lock_until"] = 0.0
            st.session_state.pop("login_password", None)
            st.rerun()
        else:
            st.session_state["login_attempts"] += 1
            if st.session_state["login_attempts"] >= MAX_LOGIN_ATTEMPTS:
                st.session_state["login_lock_until"] = time() + LOGIN_LOCK_SECONDS
                st.session_state["login_attempts"] = 0
                st.error("Zbyt wiele błędnych prób. Logowanie zostało chwilowo zablokowane.")
                st.stop()
            st.error("Nieprawid\u0142owe has\u0142o.")
    st.stop()


def inject_styles() -> None:
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

        :root {{
            --bg: {BG};
            --surface: {SURFACE};
            --surface-soft: {SURFACE_SOFT};
            --surface-raised: {SURFACE_RAISED};
            --text: {TEXT};
            --muted: {MUTED};
            --blue: {BLUE};
            --blue-soft: {BLUE_SOFT};
            --cream: {CREAM};
            --cream-soft: {CREAM_SOFT};
            --hairline: {HAIRLINE};
        }}

        .stApp {{
            background: var(--bg);
            color: var(--text);
        }}

        html, body, [class*="css"] {{
            font-family: "Inter", sans-serif;
        }}

        .block-container {{
            max-width: 860px;
            padding-top: 1.5rem;
            padding-bottom: 1.75rem;
        }}

        .login-shell,
        .shell {{
            background: transparent;
            border-radius: 0;
            box-shadow: none;
            padding: 0;
            border: 0;
            min-height: 0;
        }}

        .hero-grid {{
            display: grid;
            grid-template-columns: 1fr;
            gap: 0;
            align-items: center;
        }}

        .hero-card {{
            padding: 0;
            background: transparent;
            border: 0;
            box-shadow: none;
            border-radius: 0;
        }}

        .hero-brand {{
            display: flex;
            align-items: center;
            gap: 1rem;
            min-width: 0;
            flex-wrap: nowrap;
        }}

        .hero-title-wrap {{
            min-width: 0;
            flex: 1 1 auto;
        }}

        .hero-logo {{
            width: 92px;
            height: 92px;
            border-radius: 14px;
            overflow: hidden;
            background: transparent;
            border: 1px solid rgba(24, 48, 183, 0.15);
            box-shadow: none;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 0.18rem;
        }}

        .hero-logo img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
            border-radius: 12px;
        }}

        .hero-card h1,
        .login-hero h1 {{
            margin: 0;
            color: var(--text);
            font-family: "Inter", sans-serif;
            font-size: clamp(3rem, 5.2vw, 4.5rem);
            line-height: 1;
            letter-spacing: -0.05em;
            font-weight: 800;
            white-space: nowrap;
        }}

        .hero-kicker {{
            color: var(--text);
            font-size: 0.98rem;
            font-weight: 700;
            margin-bottom: 0.28rem;
        }}

        .hero-note,
        .storage-caption {{
            color: var(--muted);
            font-size: 0.86rem;
            line-height: 1.5;
        }}

        .header-controls {{
            margin-top: 0.75rem;
            padding-top: 0.7rem;
            border-top: 1px solid var(--hairline);
        }}

        .nav-segment {{
            display: flex;
            gap: 0.5rem;
            flex-wrap: wrap;
        }}

        .header-side {{
            min-width: 0;
        }}

        .panel {{
            margin-top: 1.5rem;
            padding: 0 0 0.35rem;
            background: transparent;
            border: 0;
            box-shadow: none;
        }}

        .section-frame {{
            padding-top: 0.8rem;
            border-top: 1.5px solid var(--blue);
        }}

        .login-panel {{
            max-width: 420px;
            margin: 2rem auto 0;
        }}

        .section-title {{
            color: var(--text);
            font-size: 1.15rem;
            font-weight: 800;
            margin-bottom: 0.6rem;
        }}

        .route-card {{
            padding: 0.72rem 0;
            margin-bottom: 0;
            background: transparent;
            box-shadow: none;
            border: 0;
            border-radius: 0;
            border-bottom: 1px solid var(--hairline);
        }}

        .muted {{
            color: var(--muted);
            font-size: 0.92rem;
        }}

        .route-meta-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.35rem;
            margin-top: 0.5rem;
        }}

        .route-chip {{
            display: inline-flex;
            align-items: center;
            min-height: 1.8rem;
            padding: 0.26rem 0.54rem;
            border-radius: 999px;
            background: transparent;
            color: var(--text);
            font-size: 0.78rem;
            border: 1px solid var(--hairline);
        }}

        .detail-card {{
            padding: 0.95rem 0;
            box-shadow: none;
            background: transparent;
            border: 0;
            border-radius: 0;
            border-bottom: 1px solid var(--hairline);
        }}

        .micro-grid {{
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.7rem;
        }}

        .micro-card {{
            background: transparent;
            border-radius: 0;
            padding: 0.65rem 0;
            border: 0;
            border-bottom: 1px solid var(--hairline);
        }}

        .micro-label {{
            color: var(--muted);
            font-size: 0.8rem;
            letter-spacing: 0;
        }}

        .micro-value {{
            color: var(--text);
            font-size: 1.02rem;
            font-weight: 700;
            margin-top: 0.22rem;
        }}

        .calendar-day {{
            min-height: 156px;
            padding: 0.65rem 0.7rem;
            background: transparent;
            box-shadow: none;
            border: 1px solid var(--hairline);
            border-radius: 0;
        }}

        .calendar-empty {{
            opacity: 0.18;
        }}

        .calendar-number {{
            color: var(--text);
            font-weight: 800;
            margin-bottom: 0.45rem;
        }}

        .calendar-caption {{
            color: var(--muted);
            font-size: 0.82rem;
            margin-bottom: 0.4rem;
        }}

        .group-card {{
            padding: 0.8rem 0;
            margin-bottom: 0.75rem;
            box-shadow: none;
            background: transparent;
            border: 0;
            border-radius: 0;
            border-bottom: 1px solid var(--hairline);
        }}

        .stRadio > div {{
            gap: 0.35rem;
        }}

        .stRadio [role="radiogroup"] {{
            background: transparent;
            border-radius: 0;
            padding: 0;
            width: fit-content;
            border: 0;
        }}

        .stRadio label {{
            margin: 0 !important;
            padding-right: 0.8rem;
        }}

        .stRadio [data-testid="stMarkdownContainer"] p {{
            color: var(--muted);
            font-weight: 700;
            font-size: 0.9rem;
        }}

        .stRadio [aria-checked="true"] [data-testid="stMarkdownContainer"] p {{
            color: var(--blue);
        }}

        .stTabs [data-baseweb="tab-list"] {{
            gap: 0.35rem;
            border-bottom: 1px solid var(--hairline);
        }}

        .stTabs [data-baseweb="tab"] {{
            background: transparent;
            border-radius: 0;
            color: var(--muted);
            padding: 0.6rem 0.2rem;
            border: 0;
        }}

        .stTabs [aria-selected="true"] {{
            background: transparent !important;
            color: var(--blue) !important;
            border-bottom: 2px solid var(--blue) !important;
        }}

        .stTabs [data-baseweb="tab-panel"] {{
            background: transparent !important;
            color: var(--text) !important;
        }}

        .stButton > button,
        .stDownloadButton > button,
        button[kind="secondary"],
        button[kind="tertiary"] {{
            min-height: 40px;
            border-radius: 0;
            border: 1px solid var(--blue);
            background: var(--blue);
            color: var(--cream-soft);
            box-shadow: none;
            font-weight: 600;
        }}

        .stButton > button:hover,
        .stDownloadButton > button:hover,
        button[kind="secondary"]:hover,
        button[kind="tertiary"]:hover {{
            border-color: var(--blue);
            background: #122792;
            color: var(--cream-soft);
        }}

        .stButton > button:disabled,
        .stDownloadButton > button:disabled,
        button[kind="secondary"]:disabled,
        button[kind="tertiary"]:disabled {{
            background: #A8B3D9 !important;
            border-color: #A8B3D9 !important;
            color: rgba(32, 38, 58, 0.8) !important;
        }}

        .stTextInput input,
        .stDateInput input,
        .stSelectbox div[data-baseweb="select"] > div,
        .stFileUploader section {{
            background: var(--cream-soft) !important;
            color: var(--text) !important;
            border-radius: 0 !important;
            border: 1px solid var(--blue) !important;
        }}

        .stTextInput input:focus,
        .stDateInput input:focus {{
            border-color: var(--blue) !important;
            box-shadow: 0 0 0 1px var(--blue) !important;
        }}

        .stTextInput input,
        .stDateInput input,
        .stSelectbox input {{
            caret-color: var(--text) !important;
        }}

        .stTextInput input::placeholder {{
            color: var(--muted) !important;
            opacity: 1;
        }}

        [data-testid="stFileUploader"] small,
        [data-testid="stFileUploader"] span,
        [data-testid="stFileUploader"] p {{
            color: var(--text) !important;
        }}

        [data-testid="stFileUploader"] button {{
            background: var(--blue) !important;
            color: var(--cream-soft) !important;
            border: 1px solid var(--blue) !important;
            border-radius: 0 !important;
            font-weight: 600 !important;
        }}

        [data-testid="stFileUploader"] button:hover {{
            background: #122792 !important;
            color: var(--cream-soft) !important;
        }}

        div[data-testid="stDialog"] > div {{
            background: var(--cream-soft) !important;
            color: var(--text) !important;
            border: 1px solid var(--hairline) !important;
            box-shadow: 0 18px 40px rgba(32, 38, 58, 0.12) !important;
        }}

        div[data-testid="stDialog"] h1,
        div[data-testid="stDialog"] h2,
        div[data-testid="stDialog"] h3,
        div[data-testid="stDialog"] p,
        div[data-testid="stDialog"] label,
        div[data-testid="stDialog"] span,
        div[data-testid="stDialog"] div {{
            color: var(--text) !important;
        }}

        div[data-testid="stDialog"] [data-baseweb="modal"] {{
            background: var(--cream-soft) !important;
        }}

        div[data-testid="stPopover"] > div,
        div[data-testid="stPopoverContent"],
        [data-baseweb="popover"] {{
            background: var(--cream-soft) !important;
            color: var(--text) !important;
            border: 1px solid var(--hairline) !important;
        }}

        div[data-testid="stPopover"] button,
        div[data-testid="stPopoverContent"] button {{
            background: var(--blue) !important;
            color: var(--cream-soft) !important;
            border: 1px solid var(--blue) !important;
        }}

        div[data-testid="stPopover"] button:hover,
        div[data-testid="stPopoverContent"] button:hover {{
            background: #122792 !important;
            color: var(--cream-soft) !important;
        }}

        div[data-testid="stMetric"] {{
            background: transparent;
            border-radius: 0;
            padding: 0.2rem 0;
            border: 0;
        }}

        div[data-testid="stMetricLabel"] {{
            color: var(--muted);
        }}

        div[data-testid="stMetricValue"] {{
            color: var(--text);
        }}

        .stTable table,
        .stTable th,
        .stTable td {{
            background: var(--cream-soft) !important;
            color: var(--text) !important;
            border-color: var(--hairline) !important;
        }}

        .calendar-day div[data-testid="stButton"] > button,
        .route-card + div[data-testid="stButton"] > button {{
            background: var(--blue);
            color: var(--cream-soft);
        }}

        label,
        .stAlert,
        .stCaption,
        .stMarkdown,
        .stSelectbox label,
        .stDateInput label,
        .stFileUploader label,
        .stTextInput label {{
            color: var(--text) !important;
        }}

        .stAlert {{
            border-radius: 0;
            border: 1px solid var(--hairline);
            box-shadow: none;
            background: rgba(24, 48, 183, 0.08);
        }}

        [data-testid="stFileUploader"] section {{
            padding: 0.85rem !important;
        }}

        .header-meta {{
            margin-bottom: 0.85rem;
        }}

        .footer-band {{
            background: var(--blue);
            color: var(--cream-soft);
            margin: 1.75rem -2.35rem 0;
            padding: 1rem 2.35rem 1.15rem;
        }}

        .footer-band h4 {{
            margin: 0 0 0.35rem 0;
            font-size: 1.05rem;
            font-weight: 700;
            color: var(--cream-soft);
        }}

        .footer-band p {{
            margin: 0;
            font-size: 0.88rem;
            line-height: 1.55;
            color: rgba(251, 245, 234, 0.94);
        }}

        @media (max-width: 980px) {{
            .hero-logo {{
                width: 82px;
                height: 82px;
            }}

            .footer-band {{
                margin-left: -1rem;
                margin-right: -1rem;
                padding-left: 1rem;
                padding-right: 1rem;
            }}
        }}

        @media (max-width: 640px) {{
            .hero-brand {{
                gap: 0.7rem;
            }}

            .nav-segment {{
                gap: 0.4rem;
            }}

            .hero-card h1,
            .login-hero h1 {{
                font-size: clamp(2.3rem, 8.4vw, 3rem);
            }}

            .hero-logo {{
                width: 68px;
                height: 68px;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def init_state() -> None:
    st.session_state.setdefault("selected_route_id", None)
    st.session_state.setdefault("calendar_year", date.today().year)
    st.session_state.setdefault("calendar_month", date.today().month)
    st.session_state.setdefault("active_view", "Trasy")
    st.session_state.setdefault("uploader_nonce", 0)
    st.session_state.setdefault("pending_upload", None)
    st.session_state.setdefault("login_attempts", 0)
    st.session_state.setdefault("login_lock_until", 0.0)


def load_routes_safely() -> list[dict]:
    try:
        return load_routes()
    except Exception:
        st.error("Nie udało się wczytać biblioteki tras. Sprawdź konfigurację storage i spróbuj ponownie.")
        return []


def save_routes_safely(routes: list[dict], success_message: str | None = None) -> bool:
    try:
        save_routes(routes)
    except Exception:
        st.error("Nie udało się zapisać zmian. Spróbuj ponownie za chwilę.")
        return False

    if success_message:
        st.success(success_message)
    return True


def route_lookup(routes: list[dict]) -> dict[str, dict]:
    return {route["id"]: route for route in routes}


def routes_by_day(routes: list[dict]) -> dict[str, list[dict]]:
    scheduled: dict[str, list[dict]] = defaultdict(list)
    for route in routes:
        for day in route.get("scheduled_dates", []):
            scheduled[day].append(route)
    return scheduled


def update_route(routes: list[dict], route_id: str, updater) -> list[dict]:
    updated: list[dict] = []
    for route in routes:
        if route["id"] == route_id:
            updated.append(updater(route))
        else:
            updated.append(route)
    return updated


def delete_route(routes: list[dict], route_id: str) -> list[dict]:
    remaining: list[dict] = []
    for route in routes:
        if route["id"] == route_id:
            delete_route_file(route)
            continue
        remaining.append(route)
    return remaining


def sorted_dates(values: list[str]) -> list[str]:
    return sorted(set(values))


def nearest_scheduled_day(routes: list[dict]) -> tuple[str, list[dict]] | None:
    scheduled = routes_by_day(routes)
    if not scheduled:
        return None
    today = date.today().isoformat()
    future_days = sorted(day for day in scheduled if day >= today)
    target = future_days[0] if future_days else sorted(scheduled)[-1]
    return target, scheduled[target]


def clear_pending_upload() -> None:
    st.session_state["pending_upload"] = None
    st.session_state["uploader_nonce"] += 1


def open_route_details(route_id: str) -> None:
    st.session_state["selected_route_id"] = route_id
    st.session_state["active_view"] = "Szczeg\u00f3\u0142y"
    st.rerun()


def group_summary_lines(route: dict) -> list[str]:
    groups = route.get("groups", [])
    if not groups:
        return ["Brak grup."]

    rows: list[str] = []
    for idx, group in enumerate(groups, start=1):
        pace = group.get("pace") or "brak tempa"
        pacers = ", ".join(group.get("pacers", [])) or "brak pacer\u00f3w"
        rows.append(f"Grupa {idx}: tempo {pace} | pacers: {pacers}")
    return rows


def render_upcoming_summary(routes: list[dict]) -> None:
    nearest = nearest_scheduled_day(routes)
    st.markdown('<div class="panel"><div class="section-frame">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Najbli\u017cszy termin</div>', unsafe_allow_html=True)
    if nearest is None:
        st.caption("Brak zaplanowanych tras.")
        st.markdown("</div></div>", unsafe_allow_html=True)
        return

    target_day, day_routes = nearest
    st.subheader(target_day)
    for route in day_routes:
        st.markdown('<div class="route-card">', unsafe_allow_html=True)
        st.write(route["title"])
        st.caption(f"D\u0142ugo\u015b\u0107: {route['distance_km']:.2f} km")
        for line in group_summary_lines(route):
            st.caption(line)
        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div></div>", unsafe_allow_html=True)


def render_top_shell() -> None:
    logo_uri = logo_data_uri()
    st.markdown('<div class="hero-grid">', unsafe_allow_html=True)

    if logo_uri:
        hero_content = f"""
        <header class="hero-card">
            <div class="hero-brand">
                <div class="hero-logo"><img src="{logo_uri}" alt="Logo Kolejny Running Club"></div>
                <div class="hero-title-wrap">
                    <h1>Kolejny GPX</h1>
                </div>
            </div>
        </header>
        """
    else:
        hero_content = """
        <header class="hero-card">
            <h1>Kolejny GPX</h1>
        </header>
        """
    st.markdown(hero_content, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def render_footer_band(status_title: str, status_detail: str) -> None:
    st.markdown(
        f"""
        <section class="footer-band" aria-label="Stopka aplikacji">
            <div style="display:grid;grid-template-columns:minmax(0,1fr);gap:1rem;">
                <div>
                    <h4>Storage</h4>
                    <p>{status_title}<br>{status_detail}</p>
                </div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def storage_status_summary() -> tuple[str, str]:
    if not supabase_configured():
        return ("Storage: lokalny fallback", "Supabase nie jest skonfigurowany.")

    client = get_supabase_client()
    if client is None:
        return ("Storage: b\u0142\u0105d konfiguracji", "Nie uda\u0142o si\u0119 utworzy\u0107 klienta Supabase.")

    try:
        client.table("routes").select("id").limit(1).execute()
        return ("Storage: Supabase connected", "Dane s\u0105 zapisywane w trwa\u0142ej bazie Supabase.")
    except Exception:
        return ("Storage: b\u0142\u0105d po\u0142\u0105czenia", "Supabase jest skonfigurowany, ale zapytanie do tabeli routes nie dzia\u0142a.")


@st.dialog("Nowa trasa")
def render_import_dialog(routes: list[dict]) -> None:
    pending = st.session_state.get("pending_upload")
    if not pending:
        return

    st.write(f"Plik: `{pending['name']}`")
    custom_title = st.text_input("Nazwa trasy", value=Path(pending["name"]).stem, key="dialog_title")
    chosen_date = st.date_input("Data u\u017cycia", value=date.today(), key="dialog_scheduled_date")
    author = st.text_input("Autor", key="dialog_author")

    actions = st.columns(2)
    with actions[0]:
        if st.button("Zapisz tras\u0119", use_container_width=True):
            normalized_title = custom_title.strip()
            normalized_author = author.strip()
            if not normalized_title:
                st.warning("Uzupe\u0142nij nazw\u0119 trasy.")
            elif len(normalized_title) > MAX_TEXT_FIELD_LENGTH:
                st.warning("Nazwa trasy jest zbyt d\u0142uga.")
            elif not normalized_author:
                st.warning("Uzupe\u0142nij autora.")
            elif len(normalized_author) > MAX_TEXT_FIELD_LENGTH:
                st.warning("Pole autora jest zbyt d\u0142ugie.")
            else:
                try:
                    route = import_gpx_file(
                        pending["name"],
                        pending["bytes"],
                        author=normalized_author,
                        scheduled_date=chosen_date.isoformat(),
                        custom_title=normalized_title,
                    )
                except ValueError as exc:
                    st.warning(str(exc))
                    return
                except Exception:
                    st.error("Nie udało się zaimportować pliku GPX.")
                    return
                routes.append(route)
                if save_routes_safely(routes, "Trasa została zapisana."):
                    st.session_state["selected_route_id"] = route["id"]
                    st.session_state["active_view"] = "Szczeg\u00f3\u0142y"
                    clear_pending_upload()
                    st.rerun()
    with actions[1]:
        if st.button("Anuluj", use_container_width=True):
            clear_pending_upload()
            st.rerun()


def render_route_card(route: dict) -> None:
    next_day = route.get("scheduled_dates", [])
    next_label = next_day[0] if next_day else "bez terminu"
    st.markdown('<div class="route-card">', unsafe_allow_html=True)
    st.write(route["title"])
    st.caption(route["filename"])
    st.caption(f"D\u0142ugo\u015b\u0107: {route['distance_km']:.2f} km | Termin: {next_label}")
    st.markdown("</div>", unsafe_allow_html=True)
    if st.button("Szczeg\u00f3\u0142y trasy", key=f"details_{route['id']}", use_container_width=True):
        open_route_details(route["id"])


def render_routes_tab(routes: list[dict]) -> None:
    layout_cols = st.columns([1.45, 0.95], gap="large", vertical_alignment="top")

    with layout_cols[0]:
        st.markdown('<div class="panel"><div class="section-frame">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Trasy</div>', unsafe_allow_html=True)
        upload = st.file_uploader(
            "Dodaj plik GPX",
            type=["gpx"],
            accept_multiple_files=False,
            key=f"gpx_uploader_{st.session_state['uploader_nonce']}",
        )

        if upload is not None and st.session_state.get("pending_upload") is None:
            raw_bytes = upload.getvalue()
            existing_names = {route["filename"] for route in routes}
            if upload.name in existing_names:
                st.warning("Plik o tej nazwie ju\u017c istnieje w bibliotece.")
            elif len(raw_bytes) > MAX_GPX_BYTES:
                st.warning(f"Plik GPX jest zbyt du\u017cy. Maksymalny rozmiar to {MAX_GPX_BYTES // (1024 * 1024)} MB.")
            else:
                st.session_state["pending_upload"] = {"name": upload.name, "bytes": raw_bytes}
                st.rerun()

        if st.session_state.get("pending_upload") is not None:
            render_import_dialog(routes)

        if not routes:
            st.info("Nie ma jeszcze \u017cadnych tras. Dodaj pierwszy plik .gpx.")
            st.markdown("</div></div>", unsafe_allow_html=True)
        else:
            query = st.text_input("Szukaj po nazwie trasy", value="", placeholder="Wpisz nazw\u0119 trasy")
            normalized_query = query.strip().lower()
            visible_routes = [
                route for route in routes if not normalized_query or normalized_query in route["title"].lower()
            ]

            if not visible_routes:
                st.info("Brak tras pasuj\u0105cych do wyszukiwania.")
            else:
                for route in visible_routes:
                    render_route_card(route)
            st.markdown("</div></div>", unsafe_allow_html=True)

    with layout_cols[1]:
        render_upcoming_summary(routes)


def render_history_tab(route: dict, routes: list[dict]) -> None:
    history_rows = [{"Data": value} for value in route.get("scheduled_dates", [])]
    if history_rows:
        st.table(pd.DataFrame(history_rows))
    else:
        st.info("Brak zapisanych u\u017cy\u0107 tej trasy.")

    add_col, remove_col = st.columns(2)
    with add_col:
        new_date = st.date_input("Dodaj u\u017cycie", value=date.today(), key=f"history_add_{route['id']}")
        if st.button("Dodaj dat\u0119", key=f"history_add_btn_{route['id']}", use_container_width=True):

            def updater(item: dict) -> dict:
                item["scheduled_dates"] = sorted_dates(item.get("scheduled_dates", []) + [new_date.isoformat()])
                return item

            if save_routes_safely(update_route(routes, route["id"], updater), "Data została dodana."):
                st.rerun()

    with remove_col:
        dates = route.get("scheduled_dates", [])
        remove_date = st.selectbox(
            "Usu\u0144 u\u017cycie",
            options=dates if dates else ["brak dat"],
            disabled=not dates,
            key=f"history_remove_{route['id']}",
        )
        if st.button("Usu\u0144 dat\u0119", key=f"history_remove_btn_{route['id']}", use_container_width=True, disabled=not dates):

            def updater(item: dict) -> dict:
                item["scheduled_dates"] = [value for value in item.get("scheduled_dates", []) if value != remove_date]
                return item

            if save_routes_safely(update_route(routes, route["id"], updater), "Data została usunięta."):
                st.rerun()


def save_group_pace(routes: list[dict], route_id: str, group_index: int, pace_value: str) -> None:
    if not PACE_PATTERN.match(pace_value):
        st.warning("Tempo musi mie\u0107 format MM:SS.")
        return

    def updater(item: dict) -> dict:
        item["groups"][group_index]["pace"] = pace_value
        return item

    if save_routes_safely(update_route(routes, route_id, updater), "Tempo zostało zapisane."):
        st.rerun()


def add_group(routes: list[dict], route_id: str) -> None:
    def updater(item: dict) -> dict:
        item["groups"].append({"pace": "", "pacers": []})
        return item

    if save_routes_safely(update_route(routes, route_id, updater)):
        st.rerun()


def remove_group(routes: list[dict], route_id: str, group_index: int) -> None:
    def updater(item: dict) -> dict:
        item["groups"] = [group for idx, group in enumerate(item.get("groups", [])) if idx != group_index]
        return item

    if save_routes_safely(update_route(routes, route_id, updater)):
        st.rerun()


def add_pacer(routes: list[dict], route_id: str, group_index: int, pacer_name: str) -> None:
    normalized_pacer = pacer_name.strip()
    if not normalized_pacer:
        st.warning("Podaj imi\u0119 i nazwisko pacera.")
        return
    if len(normalized_pacer) > MAX_PACER_NAME_LENGTH:
        st.warning("Imi\u0119 i nazwisko pacera jest zbyt d\u0142ugie.")
        return

    def updater(item: dict) -> dict:
        pacers = item["groups"][group_index].get("pacers", [])
        pacers.append(normalized_pacer)
        item["groups"][group_index]["pacers"] = pacers
        return item

    if save_routes_safely(update_route(routes, route_id, updater)):
        st.rerun()


def remove_pacer(routes: list[dict], route_id: str, group_index: int, pacer_index: int) -> None:
    def updater(item: dict) -> dict:
        pacers = item["groups"][group_index].get("pacers", [])
        item["groups"][group_index]["pacers"] = [value for idx, value in enumerate(pacers) if idx != pacer_index]
        return item

    if save_routes_safely(update_route(routes, route_id, updater)):
        st.rerun()


def render_groups_tab(route: dict, routes: list[dict]) -> None:
    groups = route.get("groups", [])
    if not groups:
        st.info("Nie ma jeszcze zdefiniowanych grup.")

    for group_index, group in enumerate(groups):
        st.markdown('<div class="group-card">', unsafe_allow_html=True)
        st.markdown(f"**Grupa {group_index + 1}**")
        pace_cols = st.columns([2, 1, 1])
        pace_value = pace_cols[0].text_input(
            "Tempo",
            value=group.get("pace", ""),
            placeholder="MM:SS",
            key=f"pace_input_{route['id']}_{group_index}",
        )
        if pace_cols[1].button("Zapisz tempo", key=f"save_pace_{route['id']}_{group_index}", use_container_width=True):
            save_group_pace(routes, route["id"], group_index, pace_value)
        if pace_cols[2].button("Usu\u0144 grup\u0119", key=f"delete_group_{route['id']}_{group_index}", use_container_width=True):
            remove_group(routes, route["id"], group_index)

        st.markdown("**Pacers**")
        pacers = group.get("pacers", [])
        if pacers:
            for pacer_index, pacer in enumerate(pacers):
                pacer_cols = st.columns([4, 1])
                pacer_cols[0].write(pacer)
                if pacer_cols[1].button(
                    "Usu\u0144",
                    key=f"remove_pacer_{route['id']}_{group_index}_{pacer_index}",
                    use_container_width=True,
                ):
                    remove_pacer(routes, route["id"], group_index, pacer_index)
        else:
            st.caption("Brak pacer\u00f3w w tej grupie.")

        pacer_cols = st.columns([3, 1])
        pacer_name = pacer_cols[0].text_input(
            "Nowy pacer",
            value="",
            placeholder="Imi\u0119 i nazwisko",
            key=f"new_pacer_{route['id']}_{group_index}",
        )
        if pacer_cols[1].button("Dodaj pacera", key=f"add_pacer_{route['id']}_{group_index}", use_container_width=True):
            add_pacer(routes, route["id"], group_index, pacer_name)
        st.markdown("</div>", unsafe_allow_html=True)

    if st.button("Dodaj grup\u0119", key=f"add_group_{route['id']}", use_container_width=True):
        add_group(routes, route["id"])


def render_route_detail(route: dict, routes: list[dict]) -> None:
    try:
        analysis = route_analysis(route)
        gpx_bytes = route_gpx_bytes(route)
    except ValueError as exc:
        st.error(f"Nie uda\u0142o si\u0119 odczyta\u0107 trasy: {exc}")
        if st.button("Powr\u00f3t do tras", key=f"detail_back_error_{route['id']}", use_container_width=True):
            st.session_state["active_view"] = "Trasy"
            st.rerun()
        return
    except Exception:
        st.error("Nie uda\u0142o si\u0119 wczyta\u0107 szczeg\u00f3\u0142\u00f3w trasy.")
        if st.button("Powr\u00f3t do tras", key=f"detail_back_unknown_{route['id']}", use_container_width=True):
            st.session_state["active_view"] = "Trasy"
            st.rerun()
        return

    st.markdown('<div class="panel"><div class="section-frame">', unsafe_allow_html=True)
    header_cols = st.columns([1.1, 3.1, 1.05], vertical_alignment="top")
    with header_cols[0]:
        if st.button("Powr\u00f3t do tras", use_container_width=True):
            st.session_state["active_view"] = "Trasy"
            st.rerun()
    with header_cols[1]:
        st.markdown('<div class="detail-card">', unsafe_allow_html=True)
        st.subheader(route["title"])
        st.caption(f"Plik: {route['filename']}")
        st.caption(f"D\u0142ugo\u015b\u0107: {route['distance_km']:.2f} km | Autor: {route.get('author') or 'brak'}")
        st.markdown("</div>", unsafe_allow_html=True)
        edit_cols = st.columns([3, 1])
        edited_title = edit_cols[0].text_input("Nazwa trasy", value=route["title"], key=f"edit_title_{route['id']}")
        if edit_cols[1].button("Zapisz nazw\u0119", key=f"save_title_{route['id']}", use_container_width=True):
            normalized_title = edited_title.strip()
            if not normalized_title:
                st.warning("Nazwa trasy nie mo\u017ce by\u0107 pusta.")
            elif len(normalized_title) > MAX_TEXT_FIELD_LENGTH:
                st.warning("Nazwa trasy jest zbyt d\u0142uga.")
            else:

                def updater(item: dict) -> dict:
                    item["title"] = normalized_title
                    return item

                if save_routes_safely(update_route(routes, route["id"], updater), "Nazwa trasy została zapisana."):
                    st.rerun()
    with header_cols[2]:
        with st.popover("Usu\u0144 GPX", use_container_width=True):
            st.warning("Tej operacji nie da si\u0119 cofn\u0105\u0107.")
            if st.button("Potwierd\u017a usuni\u0119cie", key=f"delete_route_{route['id']}", use_container_width=True):
                updated_routes = delete_route(routes, route["id"])
                if save_routes_safely(updated_routes, "Plik GPX został usunięty."):
                    st.session_state["selected_route_id"] = None
                    st.session_state["active_view"] = "Trasy"
                    st.rerun()

    st.download_button(
        "Pobierz oryginalny GPX",
        data=gpx_bytes,
        file_name=route["filename"],
        mime="application/gpx+xml",
        key=f"detail_download_{route['id']}",
    )

    metric_cols = st.columns(4)
    metric_cols[0].metric("D\u0142ugo\u015b\u0107", f"{analysis['distance_km']:.2f} km")
    metric_cols[1].metric("Przewy\u017cszenie +", f"{analysis['ascent_m']:.0f} m")
    metric_cols[2].metric("Przewy\u017cszenie -", f"{analysis['descent_m']:.0f} m")
    metric_cols[3].metric("Punkty \u015bladu", analysis["point_count"])

    top_cols = st.columns([1.7, 1], vertical_alignment="top")
    with top_cols[0]:
        points = analysis["points"]
        map_view = build_polyline_map(points, line_color=BLUE, tiles="CartoDB positron")
        st_folium(map_view, width=None, height=560, returned_objects=[], key=f"detail_map_{route['id']}")
    with top_cols[1]:
        st.markdown(
            f"""
            <div class="detail-card">
                <div class="section-title">Szczeg\u00f3\u0142y trasy</div>
                <div class="micro-grid">
                    <div class="micro-card">
                        <div class="micro-label">Min wysoko\u015b\u0107</div>
                        <div class="micro-value">{f"{analysis['min_elevation_m']:.1f} m" if analysis['min_elevation_m'] is not None else "brak"}</div>
                    </div>
                    <div class="micro-card">
                        <div class="micro-label">Max wysoko\u015b\u0107</div>
                        <div class="micro-value">{f"{analysis['max_elevation_m']:.1f} m" if analysis['max_elevation_m'] is not None else "brak"}</div>
                    </div>
                    <div class="micro-card">
                        <div class="micro-label">Start</div>
                        <div class="micro-value">{analysis['start_point'][0]:.4f}, {analysis['start_point'][1]:.4f}</div>
                    </div>
                    <div class="micro-card">
                        <div class="micro-label">Meta</div>
                        <div class="micro-value">{analysis['end_point'][0]:.4f}, {analysis['end_point'][1]:.4f}</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    history_tab, groups_tab = st.tabs(["Historia", "Grupy"])
    with history_tab:
        render_history_tab(route, routes)
    with groups_tab:
        render_groups_tab(route, routes)
    st.markdown("</div>", unsafe_allow_html=True)


def render_calendar_tab(routes: list[dict]) -> None:
    st.markdown('<div class="panel"><div class="section-frame">', unsafe_allow_html=True)
    top = st.columns([1, 1.2, 1], vertical_alignment="center")
    with top[0]:
        if st.button("Poprzedni miesi\u0105c", use_container_width=True):
            month = st.session_state["calendar_month"] - 1
            year = st.session_state["calendar_year"]
            if month == 0:
                month = 12
                year -= 1
            st.session_state["calendar_month"] = month
            st.session_state["calendar_year"] = year
            st.rerun()
    with top[1]:
        month_number = st.session_state["calendar_month"]
        st.markdown(
            f'<div class="section-title" style="text-align:center;">{MONTH_NAMES[month_number]} {st.session_state["calendar_year"]}</div>',
            unsafe_allow_html=True,
        )
    with top[2]:
        if st.button("Nast\u0119pny miesi\u0105c", use_container_width=True):
            month = st.session_state["calendar_month"] + 1
            year = st.session_state["calendar_year"]
            if month == 13:
                month = 1
                year += 1
            st.session_state["calendar_month"] = month
            st.session_state["calendar_year"] = year
            st.rerun()

    scheduled = routes_by_day(routes)
    year = st.session_state["calendar_year"]
    month = st.session_state["calendar_month"]
    weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)

    weekday_cols = st.columns(7)
    for col, label in zip(weekday_cols, ["Pon", "Wt", "\u015ar", "Czw", "Pt", "Sob", "Nd"]):
        with col:
            st.caption(label)

    for week in weeks:
        cols = st.columns(7)
        for idx, day_num in enumerate(week):
            with cols[idx]:
                if day_num == 0:
                    st.markdown('<div class="calendar-day calendar-empty"></div>', unsafe_allow_html=True)
                    continue

                day_key = date(year, month, day_num).isoformat()
                st.markdown(f'<div class="calendar-day"><div class="calendar-number">{day_num}</div>', unsafe_allow_html=True)
                day_routes = scheduled.get(day_key, [])
                if not day_routes:
                    st.caption("Brak tras")
                else:
                    for route in day_routes:
                        if st.button(route["title"], key=f"calendar_{day_key}_{route['id']}", use_container_width=True):
                            open_route_details(route["id"])
                        st.markdown(f'<div class="calendar-caption">{route["distance_km"]:.2f} km</div>', unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div></div>", unsafe_allow_html=True)


def render_navigation(selected_route_exists: bool) -> str:
    options = ["Trasy", "Kalendarz"]
    if selected_route_exists:
        options.append("Szczeg\u00f3\u0142y")

    current = st.session_state.get("active_view", "Trasy")
    if current not in options:
        current = "Trasy"
        st.session_state["active_view"] = current

    st.markdown('<div class="nav-segment">', unsafe_allow_html=True)
    nav_cols = st.columns(len(options), gap="small")
    for idx, option in enumerate(options):
        with nav_cols[idx]:
            is_active = option == current
            if st.button(option, key=f"nav_{option}", use_container_width=True, disabled=is_active):
                st.session_state["active_view"] = option
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)
    return current


def main() -> None:
    inject_styles()
    init_state()
    require_authentication()
    routes = load_routes_safely()
    selected_route = route_lookup(routes).get(st.session_state.get("selected_route_id"))
    status_title, status_detail = storage_status_summary()

    render_top_shell()
    st.markdown('<div class="header-controls">', unsafe_allow_html=True)
    controls_left, controls_right = st.columns([1.2, 0.8], gap="large", vertical_alignment="center")
    with controls_left:
        active_view = render_navigation(selected_route is not None)
    with controls_right:
        if st.button("Wyloguj", use_container_width=True):
            st.session_state["is_authenticated"] = False
            st.session_state.pop("selected_route_id", None)
            st.session_state["active_view"] = "Trasy"
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    if active_view == "Trasy":
        render_routes_tab(routes)
    elif active_view == "Kalendarz":
        render_calendar_tab(routes)
    else:
        if selected_route is None:
            st.session_state["active_view"] = "Trasy"
            st.rerun()
        render_route_detail(selected_route, routes)
    render_footer_band(status_title, status_detail)


if __name__ == "__main__":
    main()
