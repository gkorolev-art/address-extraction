"""Main Streamlit app for extracting address fields from Excel files."""

import io
import time
import logging
import traceback
from pathlib import Path

import pandas as pd
import streamlit as st

from parser.address_parser import parse_address, ParsedAddress
from parser.column_detector import score_all_columns

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
#  КОНСТАНТЫ
# ─────────────────────────────────────────────────────────────────

APP_TITLE   = "TZS address extractor"
APP_VERSION = "1.13.5"
FAVICON_PATH = Path(__file__).parent / "assets" / "tzs-favicon.svg"

COL_SETTLEMENT  = "Населённый пункт"
COL_HOUSE_STREET = "Номер дома, улица"
COL_SOURCE      = "Исходная строка"


# ─────────────────────────────────────────────────────────────────
#  НАСТРОЙКА СТРАНИЦЫ
# ─────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title=APP_TITLE,
    page_icon=str(FAVICON_PATH),
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={"About": f"{APP_TITLE} v{APP_VERSION}"},
)

st.markdown("""
<style>
    :root {
        --tzs-ink: #17201b;
        --tzs-muted: #667069;
        --tzs-line: rgba(29, 39, 34, 0.12);
        --tzs-panel: rgba(255, 255, 255, 0.82);
        --tzs-accent: #1f6f4a;
        --tzs-accent-dark: #145237;
    }

    .stApp {
        background:
            radial-gradient(circle at 12% 8%, rgba(192, 218, 207, 0.46), transparent 34%),
            radial-gradient(circle at 88% 12%, rgba(205, 214, 232, 0.42), transparent 30%),
            linear-gradient(135deg, rgba(248, 249, 246, 0.96), rgba(239, 245, 241, 0.92) 48%, rgba(245, 247, 250, 0.96));
        color: var(--tzs-ink);
    }

    #MainMenu,
    footer,
    [data-testid="stToolbar"],
    [data-testid="stDecoration"],
    [data-testid="stStatusWidget"],
    .stDeployButton {
        display: none !important;
        visibility: hidden !important;
    }

    [data-testid="stHeader"] {
        background: transparent;
        height: 0;
    }

    .main .block-container {
        max-width: 1180px;
        padding: 1rem 2rem 1.3rem;
    }

    .tzs-hero {
        display: flex;
        align-items: flex-end;
        justify-content: space-between;
        gap: 1.5rem;
        margin-bottom: 0.95rem;
        padding-bottom: 0.75rem;
        border-bottom: 1px solid var(--tzs-line);
    }

    .tzs-title {
        margin: 0;
        font-size: 2rem;
        line-height: 1.05;
        letter-spacing: 0;
        font-weight: 650;
        color: var(--tzs-ink);
    }

    .tzs-subtitle {
        margin-top: 0.3rem;
        color: var(--tzs-muted);
        font-size: 0.93rem;
    }

    .tzs-version {
        color: var(--tzs-muted);
        font-size: 0.9rem;
        white-space: nowrap;
    }

    .tzs-panel {
        border: 1px solid var(--tzs-line);
        border-radius: 8px;
        background: var(--tzs-panel);
        padding: 0.9rem 1rem;
        box-shadow: 0 18px 50px rgba(34, 42, 38, 0.08);
        margin-bottom: 0.8rem;
    }

    .tzs-check {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        color: var(--tzs-accent-dark);
        background: rgba(31, 111, 74, 0.09);
        border: 1px solid rgba(31, 111, 74, 0.18);
        border-radius: 999px;
        padding: 0.22rem 0.55rem;
        font-size: 0.84rem;
        margin-top: 0.25rem;
    }

    div[data-testid="stFileUploader"] {
        border: 1px solid var(--tzs-line);
        border-radius: 8px;
        background: rgba(255, 255, 255, 0.62);
        padding: 0.25rem 0.75rem;
    }

    div[data-testid="stMetricValue"] {
        font-size: 1.35rem;
        color: var(--tzs-ink);
    }

    div[data-testid="stMetricLabel"] {
        color: var(--tzs-muted);
    }

    .stDataFrame {
        font-size: 12.5px;
    }

    .stButton > button,
    .stDownloadButton > button {
        border-radius: 6px;
        min-height: 2.45rem;
        font-weight: 600;
    }

    .stButton > button[kind="primary"],
    .stDownloadButton > button[kind="primary"] {
        background: var(--tzs-accent);
        border-color: var(--tzs-accent);
    }

    .stSelectbox label,
    .stFileUploader label {
        color: var(--tzs-ink);
        font-weight: 560;
    }

    @media (max-width: 800px) {
        .main .block-container { padding: 0.8rem 1rem 1rem; }
        .tzs-hero { align-items: flex-start; flex-direction: column; gap: 0.35rem; }
        .tzs-title { font-size: 1.65rem; }
    }
</style>
""", unsafe_allow_html=True)


def render_header() -> None:
    st.markdown(
        f"""
        <div class="tzs-hero">
            <div>
                <h1 class="tzs-title">{APP_TITLE}</h1>
                <div class="tzs-subtitle">Извлечение населённого пункта и адресной части из Excel</div>
            </div>
            <div class="tzs-version">v{APP_VERSION}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────
#  ОБРАБОТКА ФАЙЛА
# ─────────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def load_excel(file_bytes: bytes, file_name: str) -> dict[str, pd.DataFrame]:
    """Загружает все листы Excel-файла."""
    xl = pd.ExcelFile(io.BytesIO(file_bytes))
    return {sheet: xl.parse(sheet) for sheet in xl.sheet_names}


def process_dataframe(
    df: pd.DataFrame,
    address_col: str,
    progress_bar,
) -> pd.DataFrame:
    """
    Парсит адреса и возвращает результирующий DataFrame.
    """
    total = len(df)
    results = []

    for i, val in enumerate(df[address_col]):
        raw = str(val) if pd.notna(val) else ""

        parsed: ParsedAddress = parse_address(raw)

        row = {
            COL_SETTLEMENT:   parsed.settlement,
            COL_HOUSE_STREET: parsed.house_street,
            COL_SOURCE:       raw,
        }

        results.append(row)

        if progress_bar is not None:
            progress_bar.progress((i + 1) / total, text=f"Обработано {i + 1} из {total}")

    result_df = pd.DataFrame(results)
    return result_df


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    """Сериализует DataFrame в Excel-байты."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Результат")

        wb  = writer.book
        ws  = writer.sheets["Результат"]

        # Форматирование заголовков
        header_fmt = wb.add_format({
            "bold": True, "bg_color": "#1a7f37", "font_color": "white",
            "border": 1, "text_wrap": True, "valign": "vcenter",
        })
        for col_idx, col_name in enumerate(df.columns):
            ws.write(0, col_idx, col_name, header_fmt)

        # Ширина столбцов
        col_widths = {
            COL_SETTLEMENT:   28,
            COL_HOUSE_STREET: 40,
            COL_SOURCE:       60,
        }
        for col_idx, col_name in enumerate(df.columns):
            width = col_widths.get(col_name, 20)
            ws.set_column(col_idx, col_idx, width)

        ws.set_row(0, 24)

    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────
#  ГЛАВНЫЙ ИНТЕРФЕЙС
# ─────────────────────────────────────────────────────────────────

def main():
    render_header()

    # ── Загрузка файла ──────────────────────────────────────────
    uploaded = st.file_uploader(
        "Excel-файл",
        type=["xlsx", "xls"],
        help="Поддерживаются файлы .xlsx и .xls.",
    )

    if not uploaded:
        _show_welcome()
        return

    # ── Парсинг файла ───────────────────────────────────────────
    file_bytes = uploaded.read()
    try:
        sheets = load_excel(file_bytes, uploaded.name)
    except Exception as e:
        st.error(f"Не удалось прочитать файл: {e}")
        return

    # Выбор листа
    sheet_options = list(sheets.keys())
    with st.container(border=True):
        file_col, sheet_col, address_col_area, action_col = st.columns([1.7, 1.3, 2.2, 1.2])

        with file_col:
            st.caption("Файл")
            st.write(uploaded.name)

        with sheet_col:
            sheet_name = st.selectbox(
                "Лист",
                options=sheet_options,
                index=0,
                label_visibility="visible",
            )

        df = sheets[sheet_name]

        if df.empty:
            st.warning("Лист пустой.")
            return

        scores = score_all_columns(df)
        suggested = max(scores, key=scores.get)

        with address_col_area:
            address_col = st.selectbox(
                "Столбец с адресом",
                options=list(df.columns),
                index=list(df.columns).index(suggested),
            )
            if address_col == suggested:
                st.markdown(
                    f'<div class="tzs-check">✓ выбран «{suggested}»</div>',
                    unsafe_allow_html=True,
                )

        with action_col:
            st.caption("Строк")
            st.write(f"{len(df):,}".replace(",", " "))
            run_clicked = st.button("Extract", type="primary", use_container_width=True)

    with st.expander("Предпросмотр исходных данных", expanded=False):
        st.dataframe(df.head(8), use_container_width=True, height=230)

    # ── Кнопка запуска ─────────────────────────────────────────
    if run_clicked:
        progress = st.progress(0, text="Запуск…")
        start_t  = time.time()

        try:
            result_df = process_dataframe(
                df=df,
                address_col=address_col,
                progress_bar=progress,
            )
        except Exception:
            st.error("Ошибка при обработке:\n\n" + traceback.format_exc())
            return

        elapsed = time.time() - start_t
        progress.empty()
        st.session_state["result_df"] = result_df
        st.session_state["result_meta"] = {
            "file_name": uploaded.name,
            "address_col": address_col,
            "elapsed": elapsed,
        }

    result_df = st.session_state.get("result_df")
    result_meta = st.session_state.get("result_meta", {})
    if result_df is not None and result_meta.get("file_name") == uploaded.name:
        elapsed = result_meta.get("elapsed", 0.0)

        # Метрики
        m1, m2, m3 = st.columns(3)
        m1.metric("Всего строк", len(result_df))
        m2.metric("Найдено нас.пунктов",
                  result_df[COL_SETTLEMENT].notna().sum() -
                  (result_df[COL_SETTLEMENT] == "").sum())
        m3.metric("Время обработки", f"{elapsed:.1f} с")

        # Таблица результатов
        display_cols = [COL_SETTLEMENT, COL_HOUSE_STREET, COL_SOURCE]

        st.dataframe(
            result_df[display_cols],
            use_container_width=True,
            height=390,
            column_config={
                COL_SETTLEMENT:   st.column_config.TextColumn(COL_SETTLEMENT,   width="medium"),
                COL_HOUSE_STREET: st.column_config.TextColumn(COL_HOUSE_STREET, width="large"),
                COL_SOURCE:       st.column_config.TextColumn(COL_SOURCE,       width="large"),
            }
        )

        # Скачать результат
        excel_bytes = to_excel_bytes(result_df[display_cols])

        out_name = uploaded.name.replace(".xlsx", "").replace(".xls", "")
        dl_col, status_col = st.columns([1, 2])
        with dl_col:
            st.download_button(
                label="Download Excel",
                data=excel_bytes,
                file_name=f"{out_name}_адреса.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True,
            )
        with status_col:
            st.success(f"✓ Обработано {len(result_df)} строк за {elapsed:.1f} с.")


# ─────────────────────────────────────────────────────────────────
#  СТРАНИЦА ПРИВЕТСТВИЯ (до загрузки файла)
# ─────────────────────────────────────────────────────────────────

def _show_welcome():
    st.markdown(
        """
        <div class="tzs-panel">
            <strong>Загрузите Excel-файл, чтобы начать.</strong>
            <div style="height: 0.45rem;"></div>
            <div style="color: var(--tzs-muted);">
                На выходе будет готовый файл с колонками «Населённый пункт»,
                «Номер дома, улица» и «Исходная строка».
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()
