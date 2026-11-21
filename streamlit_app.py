import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime
import pytz
import io
import base64
import re

# ==========================================
# 1. SƏHİFƏ KONFİQURASİYASI VƏ DİZAYN
# ==========================================
st.set_page_config(
    page_title="BDU - 25% Akademik Borc Müraciət Portalı",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    .main-header {
        background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
        padding: 1.8rem 2rem;
        border-radius: 14px;
        color: white;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 15px rgba(30, 58, 138, 0.15);
    }
    .main-header h1 {
        margin: 0;
        font-size: 1.75rem;
        font-weight: 700;
    }
    .main-header p {
        margin: 0.4rem 0 0 0;
        opacity: 0.9;
        font-size: 0.95rem;
    }
    .info-card {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-left: 5px solid #2563eb;
        padding: 1.2rem;
        border-radius: 10px;
        margin-bottom: 1rem;
    }
    .formula-box {
        background: linear-gradient(to right, #eff6ff, #f0fdf4);
        border: 1px solid #bfdbfe;
        padding: 1.1rem 1.4rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
    .status-badge {
        display: inline-block;
        padding: 5px 14px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .status-accepted { background-color: #e5e7eb; color: #374151; }
    .status-reviewing { background-color: #fde68a; color: #92400e; }
    .status-approved { background-color: #065f46; color: #ffffff; }
    .status-rejected { background-color: #b91c1c; color: #ffffff; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. SABİTLƏR VƏ GOOGLE API BAĞLANTISI
# ==========================================
SPREADSHEET_ID = "1f_YFSuY1L0l7enBz9cQXQ_yXdqZdWgWjPG48OEU2GEc"
DRIVE_FOLDER_ID = "1NGhi0gWYQQOEalP92IHY51IlA4eg14Cs"
TUTOR_PASSWORD = "ad234min"
BAKU_TZ = pytz.timezone("Asia/Baku")

STATUS_OPTIONS = [
    "Müraciətiniz qəbul edildi",
    "Müraciətinizə baxılır.",
    "Müraciətiniz təsdiq edildi",
    "Müraciətiniz ləğv edildi"
]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

@st.cache_resource
def get_google_clients():
    creds_dict = dict(st.secrets["gcp_service_account"])
    
    if "private_key" in creds_dict:
        pk = str(creds_dict["private_key"]).strip()
        pk = pk.replace("\\n", "\n")
        creds_dict["private_key"] = pk
        
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    gc = gspread.authorize(creds)
    drive_service = build("drive", "v3", credentials=creds)
    return gc, drive_service

@st.cache_data(ttl=300)
def load_reference_data():
    gc, _ = get_google_clients()
    sh = gc.open_by_key(SPREADSHEET_ID)
    
    ws_students = sh.worksheet("Tələbə bazası")
    df_students = pd.DataFrame(ws_students.get_all_records())
    df_students.columns = [c.strip() for c in df_students.columns]
    
    ws_curriculum = sh.worksheet("Tədris planı")
    df_curriculum = pd.DataFrame(ws_curriculum.get_all_records())
    df_curriculum.columns = [c.strip() for c in df_curriculum.columns]
    
    return df_students, df_curriculum

def load_applications():
    gc, _ = get_google_clients()
    sh = gc.open_by_key(SPREADSHEET_ID)
    ws_apps = sh.worksheet("Müraciətlər")
    records = ws_apps.get_all_records()
    df_apps = pd.DataFrame(records)
    if not df_apps.empty:
        df_apps.columns = [c.strip() for c in df_apps.columns]
    return ws_apps, df_apps

def upload_receipt_to_drive(uploaded_file, student_name, timestamp_str):
    _, drive_service = get_google_clients()
    file_ext = uploaded_file.name.split(".")[-1].lower()
    clean_name = re.sub(r'[\\/*?:"<>|]', "", student_name).strip()
    safe_time = timestamp_str.replace(":", "-").replace(" ", "_")
    drive_filename = f"{clean_name}_{safe_time}.{file_ext}"
    
    file_metadata = {
        "name": drive_filename,
        "parents": [DRIVE_FOLDER_ID]
    }
    media = MediaIoBaseUpload(
        io.BytesIO(uploaded_file.getvalue()),
        mimetype=uploaded_file.type,
        resumable=True
    )
    created_file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, webViewLink",
        supportsAllDrives=True
    ).execute()
    
    file_id = created_file.get("id")
    try:
        drive_service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
            supportsAllDrives=True
        ).execute()
    except Exception:
        pass
        
    return created_file.get("webViewLink"), file_id

def get_drive_file_bytes(drive_link):
    if not drive_link or "drive.google.com" not in str(drive_link):
        return None, None
    match = re.search(r"/d/([a-zA-Z0-9_-]+)", str(drive_link))
    if not match:
        match = re.search(r"id=([a-zA-Z0-9_-]+)", str(drive_link))
    if not match:
        return None, None
        
    file_id = match.group(1)
    _, drive_service = get_google_clients()
    try:
        meta = drive_service.files().get(fileId=file_id, fields="mimeType, name", supportsAllDrives=True).execute()
        content = drive_service.files().get_media(fileId=file_id, supportsAllDrives=True).execute()
        return content, meta.get("mimeType", "")
    except Exception:
        return None, None

def render_status_badge(status):
    s = str(status).strip()
    if s == "Müraciətiniz qəbul edildi":
        cls = "status-accepted"
    elif s == "Müraciətinizə baxılır.":
        cls = "status-reviewing"
    elif s == "Müraciətiniz təsdiq edildi":
        cls = "status-approved"
    elif s == "Müraciətiniz ləğv edildi":
        cls = "status-rejected"
    else:
        cls = "status-accepted"
    return f'<span class="status-badge {cls}">{s}</span>'

# ==========================================
# 3. BAŞLIQ VƏ SESSİYA İDARƏETMƏSİ
# ==========================================
st.markdown("""
<div class="main-header">
    <h1>🎓 25% Akademik Borc (Təkrar İmtahan) Müraciət Portalı</h1>
    <p>Tələbə müraciətlərinin elektron qeydiyyatı, qəbz yüklənməsi və tyutor nəzarət sistemi</p>
</div>
""", unsafe_allow_html=True)

if "auth_role" not in st.session_state:
    st.session_state.auth_role = None
if "student_data" not in st.session_state:
    st.session_state.student_data = None

# ==========================================
# 4. GİRİŞ EKRANI (TƏLƏBƏ VƏ TYUTOR)
# ==========================================
if st.session_state.auth_role is None:
    col_left, col_center, col_right = st.columns([1, 1.4, 1])
    with col_center:
        tab_student, tab_tutor = st.tabs(["👨‍🎓 Tələbə Girişi", "👩‍🏫 Tyutor / Admin Girişi"])
        
        with tab_student:
            st.subheader("Tələbə Kabinetinə Giriş")
            st.caption("Daxil olmaq üçün həm istifadəçi adı, həm də şifrə bölməsinə **FİN kodunuzu** daxil edin.")
            with st.form("student_login_form"):
                fin_input = st.text_input("FİN kod", placeholder="Məs: 6WHSA2B").strip().upper()
                pass_input = st.text_input("Şifrə (FİN kod)", type="password", placeholder="FİN kodunuzu təkrar yazın").strip().upper()
                submitted_st = st.form_submit_button("Daxil ol", use_container_width=True, type="primary")
                
                if submitted_st:
                    if not fin_input or not pass_input:
                        st.error("Zəhmət olmasa FİN kod və şifrəni daxil edin.")
                    elif fin_input != pass_input:
                        st.error("FİN kod və şifrə eyni olmalıdır!")
                    else:
                        df_students, _ = load_reference_data()
                        df_students["Finkod_clean"] = df_students["Finkod"].astype(str).str.strip().str.upper()
                        matched = df_students[df_students["Finkod_clean"] == fin_input]
                        if matched.empty:
                            st.error("Bu FİN kod tələbə bazasında tapılmadı. Məlumatları yoxlayın.")
                        else:
                            st.session_state.auth_role = "student"
                            st.session_state.student_data = matched.iloc[0].to_dict()
                            st.rerun()

        with tab_tutor:
            st.subheader("Tyutor İdarəetmə Paneli")
            st.caption("Müraciətləri yoxlamaq, qəbzlərə baxmaq və statusları yeniləmək üçün şifrəni daxil edin.")
            with st.form("tutor_login_form"):
                tutor_pass = st.text_input("Tyutor Şifrəsi", type="password")
                submitted_tut = st.form_submit_button("Panelə daxil ol", use_container_width=True, type="primary")
                
                if submitted_tut:
                    if tutor_pass == TUTOR_PASSWORD:
                        st.session_state.auth_role = "tutor"
                        st.rerun()
                    else:
                        st.error("Şifrə yanlışdır!")

# ==========================================
# 5. TƏLƏBƏ KABİNETİ
# ==========================================
elif st.session_state.auth_role == "student":
    st_info = st.session_state.student_data
    
    top_col1, top_col2 = st.columns([5, 1])
    with top_col1:
        st.markdown(f"### 👋 Xoş gəlmisiniz, **{st_info.get('Tələbənin S.A.A', '')}**")
    with top_col2:
        if st.button("🚪 Çıxış", use_container_width=True):
            st.session_state.auth_role = None
            st.session_state.student_data = None
            st.rerun()

    st.markdown(f"""
    <div class="info-card">
        <b>FİN kod:</b> {st_info.get('Finkod', '')} &nbsp;|&nbsp;
        <b>İxtisas:</b> {st_info.get('İxtisas', '')} ({st_info.get('İxtisasın şifri', '')}) &nbsp;|&nbsp;
        <b>Kurs / Qrup:</b> {st_info.get('Kurs', '')} / {st_info.get('Akademik qrup', '')} &nbsp;|&nbsp;
        <b>Bölmə:</b> {st_info.get('Tədris dili', '')} &nbsp;|&nbsp;
        <b>Ödəniş forması:</b> {st_info.get('Ödəniş forması', '')}
    </div>
    """, unsafe_allow_html=True)

    tab_new, tab_my = st.tabs(["📝 Yeni 25% Müraciəti", "📋 Mənim Müraciətlərim və Statuslar"])

    with tab_new:
        _, df_curriculum = load_reference_data()
        
        ixtisas_sifr = str(st_info.get("İxtisasın şifri", "")).strip()
        ixtisas_adi = str(st_info.get("İxtisas", "")).strip()
        
        df_curriculum["Sifr_clean"] = df_curriculum["Şifr"].astype(str).str.strip()
        filtered_subjects = df_curriculum[df_curriculum["Sifr_clean"] == ixtisas_sifr]
        if filtered_subjects.empty:
            filtered_subjects = df_curriculum[df_curriculum["İxtisas"].astype(str).str.strip() == ixtisas_adi]
            
        if filtered_subjects.empty:
            st.warning("İxtisasınıza uyğun tədris planında fənn tapılmadı.")
        else:
            subject_names = filtered_subjects["Fənnin adı"].astype(str).unique().tolist()
            selected_subject = st.selectbox("1️⃣ Akademik borcunuz olan fənni seçin:", ["-- Fənn seçin --"] + subject_names)
            
            if selected_subject != "-- Fənn seçin --":
                subj_row = filtered_subjects[filtered_subjects["Fənnin adı"] == selected_subject].iloc[0]
                kredit = subj_row.get("Kredit", 0)
                semestr = subj_row.get("semestr", "")
                
                st.markdown(f"""
                <div class="formula-box">
                    <h4 style="margin:0 0 8px 0; color:#1e3a8a;">📐 25% Ödəniş Məbləğinin Hesablanma Düsturu</h4>
                    <p style="margin:0; font-size:1.05rem;">
                        <b>25% Məbləğ = (İllik təhsil haqqı ÷ 60) × {kredit} (Kredit) × 0.25</b>
                    </p>
                    <p style="margin:6px 0 0 0; font-size:0.88rem; color:#475569;">
                        ℹ️ <b>Seçilmiş fənn məlumatları:</b> Semestr: <b>{semestr}</b> | Kredit sayı: <b>{kredit}</b><br>
                        ⚠️ <i>Qeyd: Ödəniş edərkən bank/portal komissiya haqqını da nəzərə almağınız xahiş olunur.</i>
                    </p>
                </div>
                """, unsafe_allow_html=True)

                with st.form("application_submit_form"):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        amount_25 = st.number_input("Ödədiyiniz 25% məbləğ (AZN)", min_value=0.0, step=0.5, format="%.2f")
                    with c2:
                        exam_date = st.date_input("İmtahan / Müraciət tarixi (Cədvəldəki Tarix sütunu)")
                    with c3:
                        entry_score = st.number_input("Giriş balı (0 - 50 arası)", min_value=0.0, max_value=50.0, step=0.5)
                        
                    receipt_file = st.file_uploader(
                        "Ödənişin qəbzini yükləyin (Şəkil və ya PDF)",
                        type=["png", "jpg", "jpeg", "pdf"]
                    )
                    
                    submit_app = st.form_submit_button("✅ Müraciəti Göndər", type="primary", use_container_width=True)
                    
                    if submit_app:
                        if receipt_file is None:
                            st.error("Zəhmət olmasa ödənişin qəbzini yükləyin!")
                        elif amount_25 <= 0:
                            st.error("Zəhmət olmasa ödədiyiniz 25% məbləği düzgün daxil edin!")
                        else:
                            with st.spinner("Qəbz Google Drive-a yüklənir və müraciət qeydə alınır..."):
                                try:
                                    now_baku = datetime.now(BAKU_TZ)
                                    reg_timestamp = now_baku.strftime("%d.%m.%Y %H:%M:%S")
                                    
                                    student_saa = str(st_info.get("Tələbənin S.A.A", "")).strip()
                                    receipt_link, _ = upload_receipt_to_drive(receipt_file, student_saa, reg_timestamp)
                                    
                                    ws_apps, _ = load_applications()
                                    
                                    new_row = [
                                        reg_timestamp,
                                        str(st_info.get("Finkod", "")).strip(),
                                        student_saa,
                                        ixtisas_adi,
                                        str(st_info.get("Kurs", "")).strip(),
                                        str(st_info.get("Akademik qrup", "")).strip(),
                                        str(st_info.get("Tədris dili", "")).strip(),
                                        str(st_info.get("Ödəniş forması", "")).strip(),
                                        selected_subject,
                                        str(semestr),
                                        int(kredit) if str(kredit).isdigit() else kredit,
                                        float(amount_25),
                                        exam_date.strftime("%d.%m.%Y"),
                                        float(entry_score),
                                        "",
                                        "",
                                        "Müraciətiniz qəbul edildi",
                                        receipt_link
                                    ]
                                    ws_apps.append_row(new_row, value_input_option="USER_ENTERED")
                                    st.success(f"Müraciətiniz uğurla qeydə alındı! (Qeydiyyat vaxtı: {reg_timestamp})")
                                    st.balloons()
                                except Exception as e:
                                    st.error(f"Xəta baş verdi: {e}")

    with tab_my:
        st.subheader("Göndərdiyiniz Müraciətlər")
        if st.button("🔄 Statusları yenilə"):
            st.rerun()
            
        _, df_apps = load_applications()
        if df_apps.empty or "Fin kod" not in df_apps.columns:
            st.info("Hələlik heç bir müraciətiniz yoxdur.")
        else:
            my_fin = str(st_info.get("Finkod", "")).strip().upper()
            my_apps = df_apps[df_apps["Fin kod"].astype(str).str.strip().str.upper() == my_fin]
            
            if my_apps.empty:
                st.info("Sizin adınıza qeydə alınmış müraciət tapılmadı.")
            else:
                for idx, row in my_apps.iterrows():
                    with st.container(border=True):
                        c_info, c_stat = st.columns([3, 1.5])
                        with c_info:
                            st.markdown(f"**Fənn:** {row.get('Fənn', '')} ({row.get('Semestr', '')} | {row.get('Kredit', '')} kredit)")
                            st.caption(
                                f"🕒 Qeydiyyat: {row.get('Müraciət qeydiyyat tarixi:', '')} | "
                                f"💰 Ödəniş (25%): {row.get('25%', '')} AZN | "
                                f"📊 Giriş balı: {row.get('Giriş balı', '')}"
                            )
                        with c_stat:
                            st.markdown(render_status_badge(row.get("Müraciətin statusu", "Müraciətiniz qəbul edildi")), unsafe_allow_html=True)

# ==========================================
# 6. TYUTOR İDARƏETMƏ PANELİ
# ==========================================
elif st.session_state.auth_role == "tutor":
    t_col1, t_col2 = st.columns([5, 1])
    with t_col1:
        st.markdown("### 👩‍🏫 Tyutor Nəzarət və Təsdiq Paneli")
    with t_col2:
        if st.button("🚪 Çıxış", use_container_width=True):
            st.session_state.auth_role = None
            st.rerun()

    ws_apps, df_apps = load_applications()
    
    if df_apps.empty:
        st.info("Hazırda sistemdə heç bir müraciət yoxdur.")
    else:
        f_col1, f_col2, f_col3 = st.columns([1.5, 1.5, 1])
        with f_col1:
            status_filter = st.selectbox("Statusa görə süz:", ["Hamısı"] + STATUS_OPTIONS)
        with f_col2:
            search_query = st.text_input("Tələbə S.A.A, FİN kod və ya Fənn axtar:").strip().lower()
        with f_col3:
            st.metric("Ümumi Müraciət", len(df_apps))

        df_apps["sheet_row"] = df_apps.index + 2
        filtered_df = df_apps.copy()
        
        if status_filter != "Hamısı":
            filtered_df = filtered_df[filtered_df["Müraciətin statusu"].astype(str).str.strip() == status_filter]
        if search_query:
            mask = (
                filtered_df["Tələbənin S.A.A"].astype(str).str.lower().str.contains(search_query) |
                filtered_df["Fin kod"].astype(str).str.lower().str.contains(search_query) |
                filtered_df["Fənn"].astype(str).str.lower().str.contains(search_query)
            )
            filtered_df = filtered_df[mask]

        if filtered_df.empty:
            st.warning("Seçilmiş filtrə uyğun müraciət tapılmadı.")
        else:
            left_pane, right_pane = st.columns([1.15, 1.15], gap="large")
            
            with left_pane:
                st.subheader(f"📋 Müraciətlər ({len(filtered_df)})")
                
                options_map = {
                    f"#{row['sheet_row']-1} | {row['Tələbənin S.A.A']} — {row['Fənn']} ({row['Müraciətin statusu']})": row
                    for _, row in filtered_df.iterrows()
                }
                selected_label = st.selectbox("Yoxlamaq üçün müraciəti seçin:", list(options_map.keys()))
                selected_app = options_map[selected_label]
                
                with st.container(border=True):
                    st.markdown(f"#### 👤 {selected_app.get('Tələbənin S.A.A', '')}")
                    st.markdown(render_status_badge(selected_app.get("Müraciətin statusu", "")), unsafe_allow_html=True)
                    st.divider()
                    
                    d1, d2 = st.columns(2)
                    with d1:
                        st.write(f"**FİN kod:** `{selected_app.get('Fin kod', '')}`")
                        st.write(f"**İxtisas:** {selected_app.get('İxtisas', '')}")
                        st.write(f"**Kurs / Qrup:** {selected_app.get('Kurs', '')} / {selected_app.get('Qrup', '')}")
                        st.write(f"**Ödəniş forması:** {selected_app.get('Ödəniş forması', '')}")
                    with d2:
                        st.write(f"**Fənn:** {selected_app.get('Fənn', '')}")
                        st.write(f"**Semestr / Kredit:** {selected_app.get('Semestr', '')} / {selected_app.get('Kredit', '')}")
                        st.write(f"**Ödənilən 25%:** `{selected_app.get('25%', '')} AZN`")
                        st.write(f"**Giriş balı:** {selected_app.get('Giriş balı', '')}")
                        
                    st.info(f"🕒 **Qeydiyyat vaxtı (saniyə ilə):** {selected_app.get('Müraciət qeydiyyat tarixi:', '')}  |  📅 **Tarix:** {selected_app.get('Tarix', '')}")

                    current_status = str(selected_app.get("Müraciətin statusu", "")).strip()
                    default_idx = STATUS_OPTIONS.index(current_status) if current_status in STATUS_OPTIONS else 0
                    
                    new_status = st.selectbox(
                        "Müraciətin yeni statusunu seçin:",
                        STATUS_OPTIONS,
                        index=default_idx,
                        key=f"status_select_{selected_app['sheet_row']}"
                    )
                    
                    if st.button("💾 Statusu Google Sheet-də Yenilə", type="primary", use_container_width=True):
                        try:
                            headers = ws_apps.row_values(1)
                            status_col_idx = headers.index("Müraciətin statusu") + 1
                            ws_apps.update_cell(int(selected_app["sheet_row"]), status_col_idx, new_status)
                            st.success(f"Status '{new_status}' olaraq yeniləndi!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Status yenilənərkən xəta baş verdi: {e}")

            with right_pane:
                st.subheader("🧾 Ödəniş Qəbzi (Canlı Baxış)")
                receipt_url = selected_app.get("Ödənişin qəbzi", "")
                
                if not receipt_url:
                    st.warning("Bu müraciət üçün qəbz linki tapılmadı.")
                else:
                    file_bytes, mime_type = get_drive_file_bytes(receipt_url)
                    
                    if file_bytes and "image" in mime_type:
                        zoom_col1, zoom_col2 = st.columns([3, 1])
                        with zoom_col1:
                            zoom_pct = st.slider("🔍 Qəbzi yaxınlaşdır / uzaqlaşdır (%)", min_value=50, max_value=250, value=100, step=10)
                        with zoom_col2:
                            st.markdown(f"<br>[🔗 Drive-da aç]({receipt_url})", unsafe_allow_html=True)
                            
                        b64_img = base64.b64encode(file_bytes).decode()
                        st.markdown(f"""
                        <div style="border: 2px solid #cbd5e1; border-radius: 10px; overflow: auto; max-height: 620px; background: #f1f5f9; padding: 10px; text-align: center;">
                            <img src="data:{mime_type};base64,{b64_img}" style="width: {zoom_pct}%; max-width: none; border-radius: 6px; transition: width 0.15s ease;" />
                        </div>
                        """, unsafe_allow_html=True)
                        
                    elif file_bytes and "pdf" in mime_type:
                        st.info("Bu qəbz PDF formatındadır. Aşağıda baxa və ya Drive-da aça bilərsiniz:")
                        b64_pdf = base64.b64encode(file_bytes).decode()
                        st.markdown(f'<iframe src="data:application/pdf;base64,{b64_pdf}" width="100%" height="600px" style="border-radius:10px; border:1px solid #cbd5e1;"></iframe>', unsafe_allow_html=True)
                    else:
                        st.warning("Qəbz şəkli birbaşa yüklənə bilmədi (Drive icazəsini yoxlayın).")
                        st.markdown(f"👉 [Qəbzi Google Drive-da açmaq üçün klikləyin]({receipt_url})")
