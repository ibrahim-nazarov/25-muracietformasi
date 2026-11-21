import os
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import streamlit as st

# 1. SƏHİFƏ AYARLARI
st.set_page_config(page_title="25% İmtahan Müraciəti Portalı", layout="wide")
st.title("🎓 25% İmtahan Müraciəti Portalı")

SHEET_NAME = "25 faizə müraciət"


# 2. TƏHLÜKƏSİZ GOOGLE SHEETS BAĞLANTISI (Çökməyən Versiya)
@st.cache_resource
def get_spreadsheet():
    # A) İlk öncə Streamlit Cloud-un gizli "Secrets" hissəsini yoxlayır
    if "gcp_service_account" in st.secrets:
        try:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds_dict["private_key"] = creds_dict["private_key"].replace(
                "\\n", "\n"
            )
            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = Credentials.from_service_account_info(
                creds_dict, scopes=scopes
            )
            client = gspread.authorize(creds)
            return client.open(SHEET_NAME)
        except Exception as e:
            st.error(f"Secrets oxunarkən xəta baş verdi: {e}")

    # B) Əgər lokalda işlədirsinizsə, "credentials.json" faylını yoxlayır
    elif os.path.exists("credentials.json"):
        try:
            client = gspread.service_account(filename="credentials.json")
            return client.open(SHEET_NAME)
        except Exception as e:
            st.error(f"credentials.json oxunarkən xəta baş verdi: {e}")

    # C) Hər ikisi yoxdursa, proqramı çökdürmür, istifadəçiyə kömək edir
    return None


sh = get_spreadsheet()

if sh is None:
    st.warning("⚠️ Google Cloud icazəsi (credentials) tapılmadı!")
    st.markdown(
        """
    ### 🛠️ Necə düzəltməli?
    Saytın çökməməsi üçün aşağıdakı addımlardan **biri** mütləq edilməlidir:
    
    * **Streamlit Cloud-da (Tövsiyə olunan):**
      1. Ekranın sağ aşağısındakı **Manage app** düyməsinə klikləyin.
      2. Üç nöqtədən **Settings** → **Secrets** bölməsinə keçin (aşağıdakı şəkildəki kimi).
      3. Google Cloud JSON faylınızın içindəki məlumatları bura yerləşdirin.
    """
    )
    # image_6.png
    st.info(
        "Lokalda işləyirsinizsə, proyekt qovluğuna 'credentials.json' faylını əlavə edin."
    )
    st.stop()


# 3. MƏLUMATLARIN YÜKLƏNMƏSİ
@st.cache_data(ttl=30)
def load_data():
    try:
        students = pd.DataFrame(sh.worksheet("Tələbə bazası").get_all_records())
        plans = pd.DataFrame(sh.worksheet("Tədris planı").get_all_records())
        requests = pd.DataFrame(sh.worksheet("Müraciətlər").get_all_records())
        return students, plans, requests
    except Exception as e:
        st.error(f"Cədvəldən məlumatları oxumaq mümkün olmadı: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()


students_df, plans_df, requests_df = load_data()


# 4. MÜRACİƏT ƏLAVƏ ETMƏK FUNKSİYASI
def add_request(
    student: dict, subject: dict, giris_bali: float, imtahan_bali: float
):
    try:
        ws = sh.worksheet("Müraciətlər")
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        row = [
            now,  # Müraciət qeydiyyat tarixi
            student.get("Finkod", ""),
            student.get("Tələbənin S.A.A", ""),
            student.get("İxtisas", ""),
            student.get("Kurs", ""),
            student.get("Akademik qrup", ""),
            student.get("Tədris dili", ""),
            student.get("Ödəniş forması", ""),
            subject.get("Fənnin adı", ""),
            subject.get("semestr", ""),
            subject.get("Kredit", ""),
            "25%",  # Müraciət növü
            now,  # Tarix
            giris_bali,
            imtahan_bali,
            giris_bali + imtahan_bali,  # Yekun
            "Gözləmədə",  # Status
            "",  # Qəbz/Qeyd
        ]
        ws.append_row(row, value_input_option="USER_ENTERED")
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Müraciət göndərilərkən xəta: {e}")
        return False


# 5. STATUS YENİLƏMƏ
def update_status(row_index: int, new_status: str):
    try:
        ws = sh.worksheet("Müraciətlər")
        # Python-da index 0-dan başlayır, Google Sheets-də 1-ci sətir başlıqdır (+2 sətir sürüşməsi)
        # Sütun 17 (Q sütunu) "Müraciətin statusu" üçün nəzərdə tutulub
        ws.update_cell(row_index + 2, 17, new_status)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Status yenilənərkən xəta: {e}")
        return False


# 6. PORTAL INTERFEYSI
tab_student, tab_admin = st.tabs(["🎓 Tələbə Bölməsi", "🔐 Admin Panel"])

# --- A) TƏLƏBƏ BÖLMƏSİ ---
with tab_student:
    fin = st.text_input("FİN kodunuzu daxil edin:", max_chars=7).strip().upper()

    if fin:
        if "Finkod" in students_df.columns:
            students_df["Finkod"] = (
                students_df["Finkod"].astype(str).str.strip().str.upper()
            )
            match = students_df[students_df["Finkod"] == fin]
        else:
            match = pd.DataFrame()

        if match.empty:
            st.error("Bu FİN kod tələbə bazasında tapılmadı.")
        else:
            student = match.iloc[0].to_dict()
            st.success(
                f"Xoş gördük, {student.get('Tələbənin S.A.A')}! Qrup: {student.get('Akademik qrup')} ({student.get('İxtisas')})"
            )

            # İxtisasa uyğun fənlər
            ixtisas_plans = plans_df[plans_df["İxtisas"] == student["İxtisas"]]
            if ixtisas_plans.empty:
                ixtisas_plans = plans_df

            st.write("---")
            st.subheader("📝 Yeni müraciət forması")
            with st.form("new_request_form"):
                fenn_adi = st.selectbox(
                    "Müraciət edilən fənn:",
                    ixtisas_plans["Fənnin adı"].unique()
                    if not ixtisas_plans.empty
                    else ["Fənn yoxdur"],
                )
                c1, c2 = st.columns(2)
                giris = c1.number_input(
                    "Giriş balı (max 50):",
                    min_value=0.0,
                    max_value=50.0,
                    value=0.0,
                )
                imtahan = c2.number_input(
                    "İmtahan balı (max 50):",
                    min_value=0.0,
                    max_value=50.0,
                    value=0.0,
                )

                if st.form_submit_button("Müraciəti təsdiqlə və göndər"):
                    if fenn_adi and fenn_adi != "Fənn yoxdur":
                        subj = ixtisas_plans[
                            ixtisas_plans["Fənnin adı"] == fenn_adi
                        ].iloc[0].to_dict()
                        if add_request(student, subj, giris, imtahan):
                            st.success("Müraciətiniz uğurla göndərildi!")
                            st.rerun()
                    else:
                        st.error("Zəhmət olmasa düzgün fənn seçin.")

            # Mövcud müraciətlərini göstər
            if not requests_df.empty and "Fin kod" in requests_df.columns:
                requests_df["Fin kod"] = (
                    requests_df["Fin kod"].astype(str).str.strip().str.upper()
                )
                my_reqs = requests_df[requests_df["Fin kod"] == fin]

                if not my_reqs.empty:
                    st.write("---")
                    st.subheader("📂 Əvvəlki Müraciətləriniz")
                    st.dataframe(
                        my_reqs[
                            [
                                "Müraciət qeydiyyat tarixi:",
                                "Fənn",
                                "Nəticə",
                                "Müraciətin statusu",
                            ]
                        ],
                        hide_index=True,
                    )

# --- B) ADMIN PANEL ---
with tab_admin:
    st.subheader("Sistem İdarəçisi")
    pwd = st.text_input("Admin şifrəsi:", type="password")

    # Sadə admin təhlükəsizliyi
    if pwd == "12345":
        st.success("Giriş təsdiqləndi.")

        if requests_df.empty:
            st.info("Sistemdə hələ heç bir müraciət yoxdur.")
        else:
            st.write("### 📋 Bütün Müraciətlər")
            st.dataframe(requests_df)

            st.write("---")
            st.subheader("✏️ Status Yenilə")

            idx = st.number_input(
                "Sətir nömrəsi (Index):",
                min_value=0,
                max_value=len(requests_df) - 1,
                value=0,
                step=1,
            )
            status = st.selectbox(
                "Yeni status seçin:",
                ["Gözləmədə", "Təsdiqləndi", "İmtina edildi", "Ləğv edildi"],
            )

            if st.button("Statusu Yenilə", type="primary"):
                if update_status(int(idx), status):
                    st.success("Status uğurla güncəlləndi!")
                    st.rerun()
