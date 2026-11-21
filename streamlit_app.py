import streamlit as st
from sheets import get_data, add_request, update_status

st.set_page_config(page_title="25% Müraciət Portalı", layout="wide")
st.title("25% İmtahan Müraciəti Portalı")

students_df, plans_df, requests_df = get_data()

tab_student, tab_admin = st.tabs(["Tələbə", "Admin"])

# --- 1. TƏLƏBƏ ---
with tab_student:
    fin = st.text_input("FİN kodunuzu daxil edin:", max_chars=7).strip().upper()

    if fin:
        students_df["Finkod"] = students_df["Finkod"].astype(str).str.strip().str.upper()
        match = students_df[students_df["Finkod"] == fin]

        if match.empty:
            st.error("Bu FİN kod bazada tapılmadı.")
        else:
            student = match.iloc[0].to_dict()
            st.success(f"{student['Tələbənin S.A.A']} | Qrup: {student['Akademik qrup']} | {student['İxtisas']}")

            ixtisas_plans = plans_df[plans_df["İxtisas"] == student["İxtisas"]]
            if ixtisas_plans.empty:
                ixtisas_plans = plans_df

            with st.form("muraciet_form"):
                fenn_adi = st.selectbox("Fənn seçin:", ixtisas_plans["Fənnin adı"].unique())
                c1, c2 = st.columns(2)
                giris = c1.number_input("Giriş balı:", min_value=0.0, max_value=50.0, step=1.0)
                imtahan = c2.number_input("İmtahan balı:", min_value=0.0, max_value=50.0, step=1.0)

                if st.form_submit_button("Müraciət göndər"):
                    subj = ixtisas_plans[ixtisas_plans["Fənnin adı"] == fenn_adi].iloc[0].to_dict()
                    add_request(student, subj, giris, imtahan)
                    st.success("Müraciət qeydə alındı!")
                    st.rerun()

            if not requests_df.empty:
                my_reqs = requests_df[requests_df["Fin kod"].astype(str).str.upper() == fin]
                if not my_reqs.empty:
                    st.subheader("Müraciətlərim")
                    st.dataframe(
                        my_reqs[["Müraciət qeydiyyat tarixi:", "Fənn", "Nəticə", "Müraciətin statusu"]],
                        hide_index=True,
                    )

# --- 2. ADMIN ---
with tab_admin:
    pwd = st.text_input("Admin şifrəsi:", type="password")
    if pwd == "12345":
        if requests_df.empty:
            st.info("Hələ müraciət yoxdur.")
        else:
            st.dataframe(requests_df)

            idx = st.number_input("Sətir nömrəsi:", min_value=0, max_value=len(requests_df) - 1, step=1)
            status = st.selectbox("Yeni status:", ["Gözləmədə", "Təsdiqləndi", "İmtina edildi"])

            if st.button("Statusu yenilə"):
                update_status(int(idx), status)
                st.success("Status yeniləndi!")
                st.rerun()
