from datetime import datetime
import gspread
import pandas as pd
import streamlit as st

SHEET_NAME = "25 faizə müraciət"


@st.cache_resource
def get_spreadsheet():
    if "gcp_service_account" in st.secrets:
        creds = dict(st.secrets["gcp_service_account"])
        creds["private_key"] = creds["private_key"].replace("\\n", "\n")
        gc = gspread.service_account_from_dict(creds)
    else:
        gc = gspread.service_account(filename="credentials.json")
    return gc.open(SHEET_NAME)


def get_data():
    sh = get_spreadsheet()
    students = pd.DataFrame(sh.worksheet("Tələbə bazası").get_all_records())
    plans = pd.DataFrame(sh.worksheet("Tədris planı").get_all_records())
    requests = pd.DataFrame(sh.worksheet("Müraciətlər").get_all_records())
    return students, plans, requests


def add_request(student: dict, subject: dict, giris_bali: float, imtahan_bali: float):
    ws = get_spreadsheet().worksheet("Müraciətlər")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    row = [
        now,                         # Müraciət qeydiyyat tarixi:
        student["Finkod"],           # Fin kod
        student["Tələbənin S.A.A"],  # Tələbənin S.A.A
        student["İxtisas"],          # İxtisas
        student["Kurs"],             # Kurs
        student["Akademik qrup"],    # Qrup
        student["Tədris dili"],      # Bölmə
        student["Ödəniş forması"],   # Ödəniş forması
        subject["Fənnin adı"],       # Fənn
        subject["semestr"],          # Semestr
        subject["Kredit"],           # Kredit
        "",                          # 25%
        "",                          # Tarix
        giris_bali,                  # Giriş balı
        imtahan_bali,                # İmtahanda topladığı bal
        giris_bali + imtahan_bali,   # Nəticə
        "Gözləmədə",                 # Müraciətin statusu
        "",                          # Ödənişin qəbzi
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")


def update_status(row_index: int, new_status: str):
    ws = get_spreadsheet().worksheet("Müraciətlər")
    # 1-ci sətir başlıq olduğu üçün +2, 17-ci sütun "Müraciətin statusu"dur
    ws.update_cell(row_index + 2, 17, new_status)
