"""Google Sheets və Drive ilə məlumat qatı."""
import base64
import mimetypes
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import gspread
import requests
import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from gspread.utils import rowcol_to_a1

BAKU = ZoneInfo("Asia/Baku")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

STUDENTS_TAB = "Tələbə bazası"
CURRICULUM_TAB = "Tədris planı"
APPLICATIONS_TAB = "Müraciətlər"
TUTORS_TAB = "Tutorlar"

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

TUTOR_COLS = {
    "name": "Tyutor",
    "password": "Parol",
    "season": "Semestr",
    "deadline": "Tarix və saat",
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

# Sheets tarixi müxtəlif formatda qaytara bilər, hamısını tanıyırıq
DEADLINE_DATETIME_FORMATS = [
    "%d.%m.%Y %H:%M",
    "%d.%m.%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
]
DEADLINE_DATE_FORMATS = ["%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d"]


@st.cache_resource
def _clients():
    info = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    gc = gspread.authorize(creds)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    return gc, drive


@st.cache_resource
def _spreadsheet():
    gc, _ = _clients()
    return gc.open_by_key(st.secrets["sheet_id"])


def _code(value):
    # Sheets kodu rəqəm kimi saxlasa, baş sıfır itə bilər (050213 -> 50213)
    return (value or "").strip().lstrip("0")


def _col_index(headers, header):
    if header not in headers:
        raise ValueError(f"Sheet-də '{header}' sütunu tapılmadı.")
    return headers.index(header) + 1  # 1-dən başlayır


def _parse_deadline(text):
    """Mətni Bakı vaxtı ilə tarixə çevirir. Tanınmırsa None qaytarır."""
    text = (text or "").strip()
    if not text:
        return None
    for fmt in DEADLINE_DATETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=BAKU)
        except ValueError:
            pass
    for fmt in DEADLINE_DATE_FORMATS:
        try:
            # Yalnız tarix yazılıbsa, həmin günün sonu (23:59) qəbul edilir
            return datetime.strptime(text, fmt).replace(hour=23, minute=59, tzinfo=BAKU)
        except ValueError:
            pass
    return None


def _read_tab_raw(tab_name):
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


@st.cache_data(ttl=30, show_spinner=False)
def _read_tab(tab_name):
    """Dəyişməyən cədvəllər (tələbə, plan, tutorlar) 30 saniyə keşdə saxlanılır."""
    return _read_tab_raw(tab_name)


@st.cache_data(ttl=3, show_spinner=False)
def _applications_rows():
    """Müraciətlər 3 saniyə keşdə saxlanılır. Yazma olanda keş təmizlənir."""
    return _read_tab_raw(APPLICATIONS_TAB)


def get_student(fin):
    for r in _read_tab(STUDENTS_TAB):
        if r.get(STUDENT_COLS["fin"], "").upper() == fin.upper():
            return {k: r.get(h, "") for k, h in STUDENT_COLS.items()}
    return None


def list_tutors():
    result = []
    for r in _read_tab(TUTORS_TAB):
        name = r.get(TUTOR_COLS["name"], "")
        password = r.get(TUTOR_COLS["password"], "")
        if not name or not password:
            continue
        deadline_text = r.get(TUTOR_COLS["deadline"], "")
        result.append({
            "name": name,
            "password": password,
            "season": r.get(TUTOR_COLS["season"], ""),
            "deadline_text": deadline_text,
            "deadline": _parse_deadline(deadline_text),
            "row": r["_row"],
        })
    return result


def set_tutor_season(row, season):
    ws = _spreadsheet().worksheet(TUTORS_TAB)
    headers = [h.strip() for h in ws.row_values(1)]
    ws.batch_update([{
        "range": rowcol_to_a1(row, _col_index(headers, TUTOR_COLS["season"])),
        "values": [[season]],
    }])
    _read_tab.clear()


def set_tutor_deadline(row, deadline):
    """deadline=None olarsa xana boşaldılır. Format: dd.mm.yyyy HH:MM"""
    ws = _spreadsheet().worksheet(TUTORS_TAB)
    headers = [h.strip() for h in ws.row_values(1)]
    value = deadline.strftime("%d.%m.%Y %H:%M") if deadline else ""
    ws.batch_update([{
        "range": rowcol_to_a1(row, _col_index(headers, TUTOR_COLS["deadline"])),
        "values": [[value]],
    }])
    _read_tab.clear()


def list_subjects(specialty_code):
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


def list_applications(fin=None):
    result = []
    for r in _applications_rows():
        item = {k: r.get(h, "") for k, h in APP_COLS.items()}
        if not item["fin"]:
            continue  # boş sətirləri ötür
        if fin is None or item["fin"].upper() == fin.upper():
            item["row"] = r["_row"]
            result.append(item)
    return result


def _upload_receipt(data, name):
    """Qəbzi Apps Script vasitəsilə sizin Drive qovluğunuza yükləyir."""
    payload = {
        "secret": st.secrets["apps_script_secret"],
        "file_name": name,
        "mime_type": mimetypes.guess_type(name)[0] or "application/octet-stream",
        "data": base64.b64encode(data).decode(),
    }
    resp = requests.post(st.secrets["apps_script_url"], json=payload, timeout=120)
    resp.raise_for_status()
    result = resp.json()
    if not result.get("ok"):
        raise RuntimeError(f"Qəbz yüklənmədi: {result.get('error')}")
    return result["link"]


def create_applications(records, receipt_bytes, receipt_name):
    """Qəbzi bir dəfə yükləyir, hər fənn üçün Sheet-də ayrı sətir yazır."""
    ws = _spreadsheet().worksheet(APPLICATIONS_TAB)
    headers = [h.strip() for h in ws.row_values(1)]

    for header in APP_COLS.values():
        _col_index(headers, header)

    link = _upload_receipt(receipt_bytes, receipt_name)

    rows = []
    for record in records:
        record = {**record, "receipt": link}
        row = [""] * len(headers)
        for key, header in APP_COLS.items():
            row[_col_index(headers, header) - 1] = str(record.get(key, ""))
        rows.append(row)
    ws.append_rows(rows, value_input_option="RAW")
    _applications_rows.clear()


def update_application(row, updates):
    """Bütün dəyişən xanaları bir sorğuda yazır (sürətli)."""
    ws = _spreadsheet().worksheet(APPLICATIONS_TAB)
    headers = [h.strip() for h in ws.row_values(1)]
    data = [
        {
            "range": rowcol_to_a1(row, _col_index(headers, APP_COLS[key])),
            "values": [[str(value)]],
        }
        for key, value in updates.items()
    ]
    ws.batch_update(data)
    _applications_rows.clear()


@st.cache_data(ttl=3600, show_spinner=False)
def _download_receipt(file_id):
    _, drive = _clients()
    meta = drive.files().get(
        fileId=file_id, fields="mimeType", supportsAllDrives=True
    ).execute()
    data = drive.files().get_media(fileId=file_id, supportsAllDrives=True).execute()
    return data, meta["mimeType"]


def get_receipt(link):
    match = re.search(r"/d/([\w-]+)", link)
    if not match:
        raise ValueError("Qəbz linki düzgün deyil.")
    return _download_receipt(match.group(1))
