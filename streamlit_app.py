import os
from datetime import datetime
import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# ---------------------------------------------------------
# 1. SƏHİFƏ KONFİQURASİYASI VƏ YÜNGÜL STİL
# ---------------------------------------------------------
st.set_page_config(
    page_title="BDU | Sənəd Müraciətləri Portalı",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
    .status-badge {
        padding: 4px 10px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.85rem;
        display: inline-block;
    }
    .st-wait { background-color: #FEF3C7; color: #92400E; }
    .st-proc { background-color: #DBEAFE; color: #1E40AF; }
    .st-ready { background-color: #D1FAE5; color: #065F46; }
    .st-done { background-color: #E5E7EB; color: #374151; }
    .st-rej { background-color: #FEE2E2; color: #991B1B; }
    .card-box {
        border: 1px solid #E5E7EB;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 12px;
        background-color: #FFFFFF;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

STATUS_OPTIONS = [
    "Gözləmədə",
    "İcradadır",
    "Hazırdır",
    "Təhvil verildi",
    "İmtina edildi",
    "Ləğv edildi",
]

REQUIRED_COLUMNS = [
    "Müraciət ID",
    "Tarix",
    "FİN",
    "Ad Soyad",
    "Fakültə",
    "Qrup",
    "Sənəd növü",
    "Müraciətin statusu",
    "İcraçı qeydi",
    "Təhvil tarixi",
]


def get_status_badge(status: str) -> str:
    mapping = {
        "Gözləmədə": "st-wait",
        "İcradadır": "st-proc",
        "Hazırdır": "st-ready",
        "Təhvil verildi": "st-done",
        "İmtina edildi": "st-rej",
        "Ləğv edildi": "st-rej",
    }
    css_class = mapping.get(status, "st-done")
    return f'<span class="status-badge {css_class}">{status}</span>'


# ---------------------------------------------------------
# 2. GOOGLE SHEETS BAĞLANTISI VƏ KEŞLƏMƏ
# ---------------------------------------------------------
@st.cache_resource
def get_worksheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)

    sheet_id = st.secrets["sheets"]["spreadsheet_id"]
    worksheet_name = st.secrets["sheets"].get("worksheet_name", "Muracietler")
    spreadsheet = client.open_by_key(sheet_id)
    return spreadsheet.worksheet(worksheet_name)


@st.cache_data(ttl=30)
def load_requests() -> pd.DataFrame:
    ws = get_worksheet()
    records = ws.get_all_records()
    if not records:
        return pd.DataFrame(columns=REQUIRED_COLUMNS + ["_sheet_row"])

    df = pd.DataFrame(records)
    # Google Sheets-də 1-ci sətir başlıqdır, məlumatlar 2-ci sətirdən başlayır
    df["_sheet_row"] = range(2, len(df) + 2)

    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    df["FİN"] = df["FİN"].astype(str).str.strip().str.upper()
    return df


def append_request(row_data: dict):
    ws = get_worksheet()
    headers = ws.row_values(1)
    new_row = [row_data.get(h, "") for h in headers]
    ws.append_row(new_row, value_input_option="USER_ENTERED")
    load_requests.clear()


def update_request_row(sheet_row: int, updates: dict):
    ws = get_worksheet()
    headers = ws.row_values(1)
    header_map = {name: idx + 1 for idx, name in enumerate(headers)}

    cells_to_update = []
    for col_name, new_val in updates.items():
        if col_name in header_map:
            cells_to_update.append(
                gspread.Cell(row=sheet_row, col=header_map[col_name], value=str(new_val))
            )

    if cells_to_update:
        ws.update_cells(cells_to_update, value_input_option="USER_ENTERED")
        load_requests.clear()


# ---------------------------------------------------------
# 3. BAŞLIQ VƏ YAN PANEL (NAVİQASİYA)
# ---------------------------------------------------------
header_col1, header_col2 = st.columns([1, 8])
with header_col1:
    # Base64 əvəzinə lokal fayl istifadə olunur (əgər varsa)
    if os.path.exists("assets/bdu_logo.png"):
        st.image("assets/bdu_logo.png", width=70)
    else:
        st.markdown("## 🎓")

with header_col2:
    st.title("Bakı Dövlət Universiteti")
    st.caption("Tələbə Sənəd Müraciətlərinin İzlənməsi və İdarəetmə Portalı")

st.sidebar.header("Bölmə seçimi")
role = st.sidebar.radio("İstifadəçi rolu:", ["Tələbə", "Tyutor / İcraçı"])

if st.sidebar.button("🔄 Məlumatları yenilə"):
    load_requests.clear()
    st.rerun()


# ---------------------------------------------------------
# 4. TƏLƏBƏ PANELİ
# ---------------------------------------------------------
def render_student_portal(df: pd.DataFrame):
    tab_track, tab_new = st.tabs(["🔍 Müraciəti izlə", "📝 Yeni müraciət"])

    with tab_track:
        fin_input = st.text_input(
            "FİN kodunuzu daxil edin (7 simvol):",
            max_chars=7,
            placeholder="Məs: 5ABC123",
        ).strip().upper()

        if fin_input:
            user_df = df[df["FİN"] == fin_input].copy()

            if user_df.empty:
                st.info("Bu FİN kod üzrə aktiv və ya keçmiş müraciət tapılmadı.")
            else:
                st.success(f"Cəmi {len(user_df)} müraciət tapıldı.")
                for _, row in user_df.iloc[::-1].iterrows():
                    status = str(row["Müraciətin statusu"]).strip()
                    with st.container():
                        st.markdown(
                            f"""
                            <div class="card-box">
                                <div style="display:flex; justify-content:space-between; align-items:center;">
                                    <strong>#{row['Müraciət ID']} — {row['Sənəd növü']}</strong>
                                    {get_status_badge(status)}
                                </div>
                                <p style="margin:6px 0; color:#4B5563; font-size:0.9rem;">
                                    <strong>Tarix:</strong> {row['Tarix']} |
                                    <strong>Fakültə:</strong> {row['Fakültə']} ({row['Qrup']})
                                </p>
                                <p style="margin:4px 0; font-size:0.9rem;">
                                    <strong>İcraçı qeydi:</strong> {row['İcraçı qeydi'] or '—'}
                                </p>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                        # Yalnız "Gözləmədə" olan müraciəti tələbə ləğv edə bilər
                        if status == "Gözləmədə":
                            if st.button(
                                "❌ Müraciəti ləğv et",
                                key=f"cancel_{row['_sheet_row']}",
                            ):
                                update_request_row(
                                    int(row["_sheet_row"]),
                                    {
                                        "Müraciətin statusu": "Ləğv edildi",
                                        "İcraçı qeydi": "Tələbə tərəfindən ləğv edildi",
                                    },
                                )
                                st.warning("Müraciətiniz ləğv edildi.")
                                st.rerun()

    with tab_new:
        with st.form("new_request_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            fin = c1.text_input("FİN kod *", max_chars=7).strip().upper()
            full_name = c2.text_input("Ad, Soyad, Ata adı *").strip()

            c3, c4 = st.columns(2)
            faculty = c3.text_input("Fakültə *").strip()
            group = c4.text_input("Qrup nömrəsi *").strip()

            doc_type = st.selectbox(
                "Tələb olunan sənəd növü *",
                [
                    "Təhsil haqqında arayış",
                    "Transkript (Qiymət cədvəli)",
                    "Hərbi komissarlıq üçün arayış",
                    "Diplom əlavəsi / Dublikat",
                    "Digər",
                ],
            )
            submitted = st.form_submit_button("Müraciəti göndər", type="primary")

            if submitted:
                if len(fin) != 7 or not full_name or not faculty or not group:
                    st.error("Zəhmət olmasa bütün vacib (*) xanaları düzgün doldurun.")
                else:
                    req_id = f"BDU-{datetime.now().strftime('%y%m%d%H%M%S')}"
                    append_request(
                        {
                            "Müraciət ID": req_id,
                            "Tarix": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "FİN": fin,
                            "Ad Soyad": full_name,
                            "Fakültə": faculty,
                            "Qrup": group,
                            "Sənəd növü": doc_type,
                            "Müraciətin statusu": "Gözləmədə",
                            "İcraçı qeydi": "",
                            "Təhvil tarixi": "",
                        }
                    )
                    st.success(f"Müraciətiniz qeydə alındı! İzləmə kodu: **{req_id}**")


# ---------------------------------------------------------
# 5. TYUTOR / İCRAÇI PANELİ
# ---------------------------------------------------------
def render_admin_portal(df: pd.DataFrame):
    if "admin_authenticated" not in st.session_state:
        st.session_state.admin_authenticated = False

    if not st.session_state.admin_authenticated:
        st.subheader("🔐 Tyutor / İcraçı girişi")
        with st.form("admin_login"):
            username = st.text_input("İstifadəçi adı")
            password = st.text_input("Şifrə", type="password")
            login_btn = st.form_submit_button("Daxil ol", type="primary")

            if login_btn:
                valid_user = st.secrets["auth"]["admin_user"]
                valid_pass = st.secrets["auth"]["admin_password"]
                if username == valid_user and password == valid_pass:
                    st.session_state.admin_authenticated = True
                    st.rerun()
                else:
                    st.error("İstifadəçi adı və ya şifrə yanlışdır.")
        return

    if st.sidebar.button("🚪 Çıxış et"):
        st.session_state.admin_authenticated = False
        st.rerun()

    # Statistika (KPI)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Cəmi müraciət", len(df))
    k2.metric("Gözləmədə", int((df["Müraciətin statusu"] == "Gözləmədə").sum()))
    k3.metric("İcradadır", int((df["Müraciətin statusu"] == "İcradadır").sum()))
    k4.metric("Hazırdır", int((df["Müraciətin statusu"] == "Hazırdır").sum()))

    st.divider()

    # Filtrlər
    f1, f2 = st.columns([2, 2])
    selected_statuses = f1.multiselect(
        "Status üzrə filtr:",
        options=STATUS_OPTIONS,
        default=["Gözləmədə", "İcradadır", "Hazırdır"],
    )
    search_query = f2.text_input("FİN, Ad Soyad və ya Müraciət ID axtar:").strip().upper()

    filtered_df = df.copy()
    if selected_statuses:
        filtered_df = filtered_df[filtered_df["Müraciətin statusu"].isin(selected_statuses)]
    if search_query:
        mask = (
            filtered_df["FİN"].str.contains(search_query, na=False)
            | filtered_df["Ad Soyad"].astype(str).str.upper().str.contains(search_query, na=False)
            | filtered_df["Müraciət ID"].astype(str).str.upper().str.contains(search_query, na=False)
        )
        filtered_df = filtered_df[mask]

    display_cols = [c for c in REQUIRED_COLUMNS if c in filtered_df.columns]
    st.dataframe(filtered_df[display_cols], hide_index=True)

    # Status yeniləmə bloku
    st.subheader("✏️ Müraciət statusunu yenilə")
    if filtered_df.empty:
        st.info("Yeniləmək üçün uyğun müraciət yoxdur.")
        return

    options_map = {
        f"{r['Müraciət ID']} | {r['FİN']} - {r['Ad Soyad']} ({r['Sənəd növü']})": r
        for _, r in filtered_df.iterrows()
    }
    selected_label = st.selectbox("Müraciəti seçin:", list(options_map.keys()))
    selected_row = options_map[selected_label]

    with st.form("update_status_form"):
        current_status = str(selected_row["Müraciətin statusu"])
        default_idx = STATUS_OPTIONS.index(current_status) if current_status in STATUS_OPTIONS else 0

        new_status = st.selectbox("Yeni status:", STATUS_OPTIONS, index=default_idx)
        executor_note = st.text_input(
            "İcraçı qeydi:", value=str(selected_row.get("İcraçı qeydi", ""))
        )
        save_btn = st.form_submit_button("Yadda saxla", type="primary")

        if save_btn:
            updates = {
                "Müraciətin statusu": new_status,
                "İcraçı qeydi": executor_note,
            }
            if new_status == "Təhvil verildi" and not selected_row.get("Təhvil tarixi"):
                updates["Təhvil tarixi"] = datetime.now().strftime("%Y-%m-%d %H:%M")

            update_request_row(int(selected_row["_sheet_row"]), updates)
            st.success(f"#{selected_row['Müraciət ID']} nömrəli müraciət yeniləndi.")
            st.rerun()


# ---------------------------------------------------------
# 6. ƏSAS İCRA AXINI
# ---------------------------------------------------------
try:
    requests_df = load_requests()
    if role == "Tələbə":
        render_student_portal(requests_df)
    else:
        render_admin_portal(requests_df)
except Exception as e:
    st.error(f"Sistem xətası baş verdi: {e}")
