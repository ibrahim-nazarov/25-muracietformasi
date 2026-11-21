import base64
import hmac
import mimetypes
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components

import sheets as db

st.set_page_config(page_title="25% ödəniş müraciəti", page_icon="🎓", layout="wide")

BAKU = ZoneInfo("Asia/Baku")
MAX_RECEIPT_MB = 10
MAX_SUBJECTS = 2

STATUS_RECEIVED = "Müraciətiniz qəbul edildi"
STATUS_REVIEW = "Müraciətinizə baxılır"
STATUS_APPROVED = "Müraciətiniz təsdiq edildi"
STATUS_CANCELLED = "Müraciətiniz ləğv edildi"
STATUSES = [STATUS_RECEIVED, STATUS_REVIEW, STATUS_APPROVED, STATUS_CANCELLED]

# (fon, yazı) — Sheet-dəki rənglərlə eynidir
STATUS_STYLE = {
    STATUS_RECEIVED: ("#e5e7eb", "#111827"),
    STATUS_REVIEW: ("#fde68a", "#78350f"),
    STATUS_APPROVED: ("#15803d", "#ffffff"),
    STATUS_CANCELLED: ("#b91c1c", "#ffffff"),
}

SEASONS = ["Payız", "Yaz"]
SEASON_NONE = "Seçilməyib"


# ---------- Köməkçilər ----------

def status_badge(status):
    bg, fg = STATUS_STYLE.get(status, ("#e5e7eb", "#111827"))
    return (
        f'<span style="background:{bg};color:{fg};padding:4px 12px;'
        f'border-radius:999px;font-weight:600;white-space:nowrap;">{status}</span>'
    )


def to_number(text):
    text = (text or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def fmt_number(value):
    if value is None:
        return ""
    return str(int(value)) if float(value).is_integer() else str(value)


def safe_filename(text):
    return re.sub(r'[\\/:*?"<>|]+', "", text).strip()


def season_key(text):
    """'payız-1', 'Payiz', 'yaz-2' kimi yazılışları eyni qrupa salır."""
    t = (text or "").strip().lower()
    if t.startswith("pay"):
        return "payiz"
    if t.startswith("yaz"):
        return "yaz"
    return ""


def season_label(value):
    key = season_key(value)
    for s in SEASONS:
        if key and season_key(s) == key:
            return s
    return SEASON_NONE


def find_tutor(name):
    for t in db.list_tutors():
        if t["name"] == name:
            return t
    return None


def check_tutor_login(password):
    password = (password or "").strip()
    if not password:
        return None
    for tutor in db.list_tutors():
        if hmac.compare_digest(password.encode(), tutor["password"].encode()):
            return tutor["name"]
    return None


# ---------- Giriş ----------

def login_page():
    st.title("🎓 25% ödəniş müraciəti")
    tab_student, tab_tutor = st.tabs(["Tələbə", "Tutor"])

    with tab_student:
        with st.form("student_login"):
            fin = st.text_input("FIN kod")
            password = st.text_input("Parol", type="password", help="Parol FIN kodunuzdur.")
            ok = st.form_submit_button("Daxil ol")
        if ok:
            fin_n = fin.strip().upper()
            if fin_n and password.strip().upper() == fin_n and db.get_student(fin_n):
                st.session_state.update(role="student", fin=fin_n)
                st.rerun()
            st.error("FIN kod və ya parol yanlışdır.")

    with tab_tutor:
        with st.form("tutor_login"):
            password = st.text_input("Tutor parolu", type="password")
            ok = st.form_submit_button("Daxil ol")
        if ok:
            name = check_tutor_login(password)
            if name:
                st.session_state.update(role="tutor", tutor_name=name)
                st.rerun()
            st.error("Parol yanlışdır.")


# ---------- Tələbə ----------

def student_page(fin):
    student = db.get_student(fin)
    if student is None:
        st.error("Tələbə məlumatı tapılmadı.")
        return

    tutor = find_tutor(student["tutor"])
    season = tutor["season"] if tutor else ""

    st.title(f"Salam, {student['name']}")
    st.markdown(
        f"**İxtisas:** {student['specialty']}  \n"
        f"**Kurs:** {student['course']} · **Qrup:** {student['group']} · "
        f"**Ödəniş forması:** {student['payment_form']}"
    )

    flash = st.session_state.pop("flash", None)
    if flash:
        st.success(flash)

    tab_new, tab_mine = st.tabs(["Yeni müraciət", "Müraciətlərim"])
    with tab_new:
        apply_form(student, season)
    with tab_mine:
        my_applications(fin)


def apply_form(student, season):
    if season_key(season) == "":
        st.info("Tutorunuz hələ açıq semestr seçməyib. Müraciət hazırda mümkün deyil.")
        return

    active = [
        a for a in db.list_applications(fin=student["fin"])
        if a["status"] != STATUS_CANCELLED
    ]
    remaining = MAX_SUBJECTS - len(active)

    if remaining <= 0:
        st.info(
            f"Siz artıq {MAX_SUBJECTS} fənnə müraciət etmisiniz. "
            "Yeni müraciət üçün mövcud müraciətlərdən biri ləğv edilməlidir."
        )
        return

    taken = {(a["subject"], a["semester"]) for a in active}
    by_key = {}
    for s in db.list_subjects(student["specialty_code"]):
        if season_key(s["semester"]) != season_key(season):
            continue
        if (s["subject"], s["semester"]) in taken:
            continue
        by_key[f"{s['subject']}||{s['semester']}"] = s

    if not by_key:
        st.info(f"Bu ixtisas üçün {season_label(season)} semestrində müraciət edilə biləcək fənn yoxdur.")
        return

    keys = list(by_key)

    def label(k):
        s = by_key[k]
        return f"{s['subject']} · {s['semester']} · {s['credits']} kredit"

    st.caption(
        f"Açıq semestr: {season_label(season)} · "
        f"Qalan müraciət hüququ: {remaining} fən. "
        "Ən azı 1 fənn seçməlisiniz, ikinci fənn istəyə bağlıdır."
    )

    with st.form("apply_form"):
        first = st.selectbox(
            "1-ci fənn (məcburi)",
            options=keys,
            index=None,
            format_func=label,
            placeholder="Fənn seçin",
        )
        second = None
        if remaining >= 2:
            second = st.selectbox(
                "2-ci fənn (istəyə bağlı)",
                options=keys,
                index=None,
                format_func=label,
                placeholder="Yalnız bir fənn istəyirsinizsə boş buraxın",
            )
        receipt = st.file_uploader(
            "Ödənişin qəbzi (PDF, JPG və ya PNG)",
            type=["pdf", "jpg", "jpeg", "png"],
            help="Seçdiyiniz bütün fənnlər üçün bir qəbz yükləyin.",
        )
        submitted = st.form_submit_button("Müraciət et", type="primary")

    if not submitted:
        return

    chosen_keys = [k for k in (first, second) if k is not None]

    problems = []
    if first is None:
        problems.append("1-ci fənni seçin.")
    if len(chosen_keys) != len(set(chosen_keys)):
        problems.append("Eyni fənni iki dəfə seçmək olmaz.")
    if len(chosen_keys) > remaining:
        problems.append(f"Ən çox {remaining} fənn seçə bilərsiniz.")
    if receipt is None:
        problems.append("Qəbzi yükləyin.")
    elif receipt.size > MAX_RECEIPT_MB * 1024 * 1024:
        problems.append(f"Fayl {MAX_RECEIPT_MB} MB-dan böyük ola bilməz.")

    if problems:
        for p in problems:
            st.error(p)
        return

    chosen = [by_key[k] for k in chosen_keys]

    now = datetime.now(BAKU)
    ext = Path(receipt.name).suffix.lower()
    file_name = f"{safe_filename(student['name'])}_{now:%Y-%m-%d_%H-%M-%S}{ext}"
    date_text = now.strftime("%d.%m.%Y %H:%M:%S")

    # Hər seçilmiş fənn üçün ayrı sətir, eyni tələbə məlumatı və eyni qəbz linki
    records = [
        {
            "date": date_text,
            "fin": student["fin"],
            "name": student["name"],
            "specialty": student["specialty"],
            "course": student["course"],
            "group": student["group"],
            "division": student["language"],
            "payment_form": student["payment_form"],
            "subject": s["subject"],
            "semester": s["semester"],
            "credits": s["credits"],
            "exam_date": "",
            "entry_score": "",
            "exam_score": "",
            "result": "",
            "status": STATUS_RECEIVED,
        }
        for s in chosen
    ]

    try:
        db.create_applications(
            records,
            receipt_bytes=receipt.getvalue(),
            receipt_name=file_name,
        )
    except Exception as e:
        st.error("Müraciət saxlanılmadı. Səbəb:")
        st.code(f"{type(e).__name__}: {str(e)[:800]}")
        return

    st.session_state["flash"] = f"{len(chosen)} fən üzrə müraciətiniz qəbul edildi."
    st.rerun()


def my_applications(fin):
    apps = db.list_applications(fin=fin)
    if not apps:
        st.info("Hələ müraciətiniz yoxdur.")
        return
    for a in reversed(apps):
        with st.container(border=True):
            left, right = st.columns([3, 2])
            left.markdown(
                f"**{a['subject']}**  \n"
                f"{a['semester']} · {a['credits']} kredit · {a['date']}"
            )
            right.markdown(status_badge(a["status"]), unsafe_allow_html=True)


# ---------- Tutor ----------

def season_block(tutor):
    current = season_label(tutor["season"])
    options = [SEASON_NONE] + SEASONS
    choice = st.radio(
        "Açıq semestr (tələbələr yalnız bu semestrin fənlərinə müraciət edə bilər)",
        options,
        index=options.index(current),
        horizontal=True,
        key=f"season_{tutor['row']}",
    )
    if choice != current:
        db.set_tutor_season(tutor["row"], "" if choice == SEASON_NONE else choice)
        st.success(f"Açıq semestr: {choice}. Dəyişiklik yadda saxlandı.")


def tutor_page(tutor_name):
    tutor = find_tutor(tutor_name)

    st.title("Tutor paneli")
    st.caption(f"Tutor: {tutor_name}")

    if tutor:
        season_block(tutor)
        st.divider()

    status_filter = st.selectbox("Status filtri", ["Hamısı"] + STATUSES)

    # Tələbə üzrə qruplaşdırma: bir tələbənin bütün fənləri bir yerdə görünür
    groups = {}
    for a in db.list_applications():
        if status_filter != "Hamısı" and a["status"] != status_filter:
            continue
        student = db.get_student(a["fin"])
        if not student or student["tutor"] != tutor_name:
            continue
        key = a["fin"].upper()
        group = groups.setdefault(key, {"student": student, "apps": []})
        group["apps"].append(a)

    if not groups:
        st.info("Bu filtrə uyğun müraciət yoxdur.")
        return

    fin_key = st.selectbox(
        "Tələbə",
        options=list(groups),
        format_func=lambda f: (
            f"{groups[f]['student']['name']} · {len(groups[f]['apps'])} fən"
        ),
    )
    student = groups[fin_key]["student"]
    apps = groups[fin_key]["apps"]

    left, right = st.columns([1, 1], gap="large")
    with left:
        student_header(student)
        for app in apps:
            score_form(app)
    with right:
        links = []
        for a in apps:
            if a["receipt"] and a["receipt"] not in links:
                links.append(a["receipt"])
        if not links:
            st.warning("Qəbz yüklənməyib.")
        for n, link in enumerate(links, start=1):
            covered = ", ".join(a["subject"] for a in apps if a["receipt"] == link)
            receipt_viewer(
                link,
                key=f"{fin_key}_{n}",
                title="Ödənişin qəbzi" if len(links) == 1 else f"Ödənişin qəbzi {n}",
                note=f"Bu qəbz əhatə edir: {covered}",
            )


def student_header(student):
    st.subheader(student["name"])
    st.markdown(
        f"**FIN:** {student['fin']}  \n"
        f"**İxtisas:** {student['specialty']} · **Kurs:** {student['course']} · "
        f"**Qrup:** {student['group']}  \n"
        f"**Ödəniş forması:** {student['payment_form']}"
    )


def score_form(app):
    row = app["row"]
    with st.container(border=True):
        st.markdown(
            f"**{app['subject']}**  \n"
            f"{app['semester']} · {app['credits']} kredit · müraciət: {app['date']}"
        )
        st.markdown(status_badge(app["status"]), unsafe_allow_html=True)

        with st.form(f"edit_{row}"):
            entry_text = st.text_input(
                "Giriş balı", value=app["entry_score"], key=f"entry_{row}"
            )
            exam_text = st.text_input(
                "İmtahanda topladığı bal", value=app["exam_score"], key=f"exam_{row}"
            )
            status = st.selectbox(
                "Müraciətin statusu",
                STATUSES,
                index=STATUSES.index(app["status"]) if app["status"] in STATUSES else 0,
                key=f"status_{row}",
            )
            saved = st.form_submit_button("Yadda saxla", type="primary")

        if saved:
            entry, exam = to_number(entry_text), to_number(exam_text)
            if (entry_text.strip() and entry is None) or (exam_text.strip() and exam is None):
                st.error("Balları rəqəm kimi yazın (məsələn 72 və ya 72.5).")
                return

            # Nəticə = Giriş balı + İmtahanda topladığı bal
            result = fmt_number(entry + exam) if entry is not None and exam is not None else ""

            db.update_application(row, {
                "entry_score": fmt_number(entry),
                "exam_score": fmt_number(exam),
                "result": result,
                "status": status,
            })
            st.success(f"Yadda saxlandı. Nəticə: {result or '—'}")


def receipt_viewer(link, key, title, note=""):
    st.subheader(title)
    if note:
        st.caption(note)
    try:
        data, mime = db.get_receipt(link)
    except Exception:
        st.error("Qəbz açılmadı. Drive icazələrini yoxlayın.")
        return

    zoom = st.slider(
        "Yaxınlıq (%)",
        min_value=50,
        max_value=300,
        value=100,
        step=10,
        key=f"zoom_{key}",
    )

    if mime == "application/pdf":
        b64 = base64.b64encode(data).decode()
        components.html(
            f'<iframe src="data:application/pdf;base64,{b64}#zoom={zoom}" '
            f'style="width:100%;height:800px;border:none;"></iframe>',
            height=820,
        )
    elif mime.startswith("image/"):
        st.image(data, width=int(600 * zoom / 100))

    ext = mimetypes.guess_extension(mime) or ""
    st.download_button(
        "Qəbzi yüklə",
        data,
        file_name=f"qebz_{key}{ext}",
        mime=mime,
        key=f"dl_{key}",
    )


# ---------- Əsas axın ----------

def main():
    if st.session_state.get("role") is None:
        login_page()
        return

    with st.sidebar:
        if st.button("Çıxış"):
            st.session_state.clear()
            st.rerun()

    if st.session_state["role"] == "student":
        student_page(st.session_state["fin"])
    else:
        tutor_page(st.session_state["tutor_name"])


main()
