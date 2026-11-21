"""Google Sheets və Google Drive ilə məlumat qatı."""
import io
import mimetypes
import re

import gspread
import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

STUDENTS_TAB = "Tələbə bazası"
CURRICULUM_TAB = "Tədris planı"
APPLICATIONS_TAB = "Müraciətlər"

# Daxili açar -> Sheet-dəki başlıq (dəqiq eyni olmalıdır)
STUDENT_COLS = {
    "name": "Tələbənin S.A.A",
    "group": "Akademik qrup",
    "specialty": "İxtisas",
    "specialty_code": "İxtisasın şifri",
    "fin": "Finkod",
    "tutor": "Tyutor",
    "payment_form": "Ödəniş forması",
    "language": "Tədris dili",
    "course": "Kurs",
}

CURRICULUM_COLS = {
    "subject": "Fənnin adı",
    "credits": "Kredit",
    "semester": "semestr",
    "specialty_code": "Şifr",
}

APP_COLS = {
    "date": "Müraciət qeydiyyat tarixi:",
    "fin": "Fin kod",
    "name": "Tələbənin S.A.A",
    "specialty": "İxtisas",
    "course": "Kurs",
    "group": "Qrup",
    "division": "Bölmə",
    "payment_form": "Ödəniş forması",
    "subject": "Fənn",
    "semester": "Semestr",
    "credits": "Kredit",
    "exam_date": "Tarix",
    "entry_score": "Giriş balı",
    "exam_score": "İmtahanda topladığı bal",
    "result": "Nəticə",
    "status": "Müraciətin statusu",
    "receipt": "Ödənişin qəbzi",
}


@st.cache_resource
def _clients():
    info = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    gc = gspread.authorize(creds)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    return gc, drive


def _spreadsheet():
    gc, _ = _clients()
    return gc.open_by_key(st.secrets["sheet_id"])


def _code(value: str) -> str:
    # Sheets kodu rəqəm kimi saxlasa, baş sıfır itə bilər (050213 -> 50213)
    return (value or "").strip().lstrip("0")


def _col_index(headers, header):
    if header not in headers:
        raise ValueError(f"Sheet-də '{header}' sütunu tapılmadı.")
    return headers.index(header) + 1  # 1-dən başlayır


@st.cache_data(ttl=60)
def _read_tab(tab_name: str):
    ws = _spreadsheet().worksheet(tab_name)
    values = ws.get_all_values()
    if not values:
        return []
    headers = [h.strip() for h in values[0]]
    records = []
    for row_number, row in enumerate(values[1:], start=2):
        rec = {}
        for j, h in enumerate(headers):
            if h:
                rec[h] = row[j].strip() if j < len(row) else ""
        rec["_row"] = row_number
        records.append(rec)
    return records


def get_student(fin: str):
    for r in _read_tab(STUDENTS_TAB):
        if r.get(STUDENT_COLS["fin"], "").upper() == fin:
            return {k: r.get(h, "") for k, h in STUDENT_COLS.items()}
    return None


def list_subjects(specialty_code: str):
    return [
        {
            "subject": r.get(CURRICULUM_COLS["subject"], ""),
            "credits": r.get(CURRICULUM_COLS["credits"], ""),
            "semester": r.get(CURRICULUM_COLS["semester"], ""),
        }
        for r in _read_tab(CURRICULUM_TAB)
        if r.get(CURRICULUM_COLS["subject"], "")
        and _code(r.get(CURRICULUM_COLS["specialty_code"], "")) == _code(specialty_code)
    ]


def list_applications(fin: str | None = None):
    result = []
    for r in _read_tab(APPLICATIONS_TAB):
        item = {k: r.get(h, "") for k, h in APP_COLS.items()}
        if not item["fin"]:
            continue  # boş sətirləri ötür
        if fin is None or item["fin"].upper() == fin:
            item["row"] = r["_row"]
            result.append(item)
    return result


def _upload_receipt(drive, data: bytes, name: str) -> str:
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime, resumable=False)
    body = {"name": name, "parents": [st.secrets["drive_folder_id"]]}
    created = drive.files().create(
        body=body,
        media_body=media,
        fields="id, webViewLink",
        supportsAllDrives=True,
    ).execute()
    return created["webViewLink"]


def create_application(record: dict, receipt_bytes: bytes, receipt_name: str):
    _, drive = _clients()
    ws = _spreadsheet().worksheet(APPLICATIONS_TAB)
    headers = [h.strip() for h in ws.row_values(1)]

    # Əvvəlcə başlıqları yoxlayırıq, sonra faylı yükləyirik
    for header in APP_COLS.values():
        _col_index(headers, header)

    link = _upload_receipt(drive, receipt_bytes, receipt_name)
    record = {**record, "receipt": link}

    row = [""] * len(headers)
    for key, header in APP_COLS.items():
        row[_col_index(headers, header) - 1] = str(record.get(key, ""))
    ws.append_row(row, value_input_option="USER_ENTERED")
    _read_tab.clear()


def update_application(row: int, updates: dict):
    ws = _spreadsheet().worksheet(APPLICATIONS_TAB)
    headers = [h.strip() for h in ws.row_values(1)]
    for key, value in updates.items():
        ws.update_cell(row, _col_index(headers, APP_COLS[key]), value)
    _read_tab.clear()


def get_receipt(link: str):
    match = re.search(r"/d/([\w-]+)", link)
    if not match:
        raise ValueError("Qəbz linki düzgün deyil.")
    file_id = match.group(1)
    _, drive = _clients()
    meta = drive.files().get(
        fileId=file_id, fields="mimeType", supportsAllDrives=True
    ).execute()
    data = drive.files().get_media(fileId=file_id, supportsAllDrives=True).execute()
    return data, meta["mimeType"]
