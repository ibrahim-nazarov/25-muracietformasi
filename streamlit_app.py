import base64
import hmac
import mimetypes
import re
from datetime import datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components

import sheets as db

st.set_page_config(page_title="25% ödəniş müraciəti", page_icon="🎓", layout="wide")

BAKU = ZoneInfo("Asia/Baku")
MAX_RECEIPT_MB = 10
MAX_SUBJECTS = 2
LIVE_REFRESH_SECONDS = 5

STATUS_RECEIVED = "Müraciətiniz qəbul edildi"
STATUS_REVIEW = "Müraciətinizə baxılır"
STATUS_APPROVED = "Müraciətiniz təsdiq edildi"
STATUS_CANCELLED = "Müraciətiniz ləğv edildi"
STATUSES = [STATUS_RECEIVED, STATUS_REVIEW, STATUS_APPROVED, STATUS_CANCELLED]
WAITING = (STATUS_RECEIVED, STATUS_REVIEW)

STATUS_CLASS = {
    STATUS_RECEIVED: "pill-received",
    STATUS_REVIEW: "pill-review",
    STATUS_APPROVED: "pill-approved",
    STATUS_CANCELLED: "pill-cancelled",
}

PROGRESS_STEPS = [STATUS_RECEIVED, STATUS_REVIEW, STATUS_APPROVED]
PROGRESS_LABELS = ["Qəbul", "Baxılır", "Təsdiq"]

SEASONS = ["Payız", "Yaz"]
SEASON_NONE = "Seçilməyib"

APP_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap');

html, body, .stApp { font-family: 'Manrope', 'Segoe UI', Roboto, sans-serif; }
#MainMenu, footer { visibility: hidden; }
.block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1200px; }

.hero {
  border-radius: 22px; padding: 28px 32px; color: #ffffff; margin-bottom: 1.25rem;
  background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 55%, #db2777 100%);
  box-shadow: 0 18px 40px -14px rgba(79, 70, 229, 0.5);
}
.hero .eyebrow { text-transform: uppercase; letter-spacing: .12em; font-size: .72rem; font-weight: 700; opacity: .85; margin-bottom: .45rem; }
.hero h1 { color: #ffffff; font-size: 1.85rem; font-weight: 800; margin: 0 0 .3rem; letter-spacing: -.01em; }
.hero p { margin: 0; opacity: .92; font-size: .98rem; }

.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 1.25rem; }
.stat { border-radius: 16px; padding: 16px 18px; border: 1px solid rgba(127,127,127,.22); background: rgba(127,127,127,.06); }
.stat .v { font-size: 1.6rem; font-weight: 800; line-height: 1.1; }
.stat .l { font-size: .82rem; opacity: .7; margin-top: 4px; }

.app-card {
  border-radius: 18px; padding: 18px 20px; margin-bottom: 14px;
  border: 1px solid rgba(127,127,127,.22); background: rgba(127,127,127,.05);
  transition: box-shadow .2s ease, transform .2s ease;
}
.app-card:hover { box-shadow: 0 10px 28px -12px rgba(0,0,0,.25); transform: translateY(-1px); }
.app-head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; flex-wrap: wrap; }
.app-title { font-weight: 800; font-size: 1.05rem; }
.app-meta { font-size: .86rem; opacity: .72; margin-top: 3px; }
.pills { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }

.pill { display: inline-flex; align-items: center; gap: 6px; padding: 5px 12px; border-radius: 999px; font-size: .8rem; font-weight: 700; white-space: nowrap; }
.pill-received { background: #e0e7ff; color: #3730a3; }
.pill-review { background: #fef3c7; color: #92400e; }
.pill-approved { background: #dcfce7; color: #166534; }
.pill-cancelled { background: #fee2e2; color: #991b1b; }
.pill-receipt { background: #ede9fe; color: #5b21b6; }

.steps { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-top: 14px; }
.step { height: 6px; border-radius: 999px; background: rgba(127,127,127,.22); }
.step.on { background: linear-gradient(90deg, #6366f1, #a855f7); }
.step-labels { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; font-size: .74rem; opacity: .7; margin-top: 6px; }

.cov-row { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 9px 0; border-top: 1px dashed rgba(127,127,127,.3); }

div[data-testid="stForm"] { border-radius: 18px; border: 1px solid rgba(127,127,127,.22); padding: 1.1rem 1.2rem; }
div[data-testid="stFormSubmitButton"] button, .stButton > button { border-radius: 12px; font-weight: 700; }
button[role="tab"] { font-weight: 700 !important; }

@media (max-width: 640px) {
  .block-container { padding-left: 1rem; padding-right: 1rem; padding-top: 1rem; }
  .hero { padding: 22px 20px; }
  .hero h1 { font-size: 1.4rem; }
}
</style>
"""


# ---------- Köməkçilər ----------

def esc(value):
    return "" if value is None else escape(str(value))


def status_pill(status):
    cls = STATUS_CLASS.get(status, "pill-received")
    return f'<span class="pill {cls}">{esc(status)}</span>'


def progress_html(status):
    if status == STATUS_CANCELLED:
        reached = 0
    elif status in PROGRESS_STEPS:
        reached = PROGRESS_STEPS.index(status) + 1
    else:
        reached = 1
    bars = "".join(
        f'<div class="step{" on" if i < reached else ""}"></div>' for i in range(3)
    )
    labels = "".join(f"<div>{t}</div>" for t in PROGRESS_LABELS)
    return f'<div class="steps">{bars}</div><div class="step-labels">{labels}</div>'


def hero(eyebrow, title, subtitle=""):
    sub = f"<p>{esc(subtitle)}</p>" if subtitle else ""
    st.markdown(
        f'<div class="hero"><div class="eyebrow">{esc(eyebrow)}</div>'
        f'<h1>{esc(title)}</h1>{sub}</div>',
        unsafe_allow_html=True,
    )


def stat_tiles(items):
    cells = "".join(
        f'<div class="stat"><div class="v">{esc(v)}</div><div class="l">{esc(label)}</div></div>'
        for v, label in items
    )
    st.markdown(f'<div class="stats">{cells}</div>', unsafe_allow_html=True)


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
    hero(
        "25% ödəniş müraciəti",
        "Xoş gəlmisiniz",
        "Tələbələr FIN kodu ilə, tutorlar öz parolu ilə daxil olur.",
    )
    _, mid, _ = st.columns([1, 1.3, 1])
    with mid:
        tab_student, tab_tutor = st.tabs(["Tələbə", "Tutor"])

        with tab_student:
            with st.form("student_login"):
                fin = st.text_input("FIN kod")
                password = st.text_input("Parol", type="password", help="Parol FIN kodunuzdur.")
                ok = st.form_submit_button("Daxil ol", type="primary")
            if ok:
                fin_n = fin.strip().upper()
                if fin_n and password.strip().upper() == fin_n and db.get_student(fin_n):
                    st.session_state.update(role="student", fin=fin_n)
                    st.rerun()
                st.error("FIN kod və ya parol yanlışdır.")

        with tab_tutor:
            with st.form("tutor_login"):
                password = st.text_input("Tutor parolu", type="password")
                ok = st.form_submit_button("Daxil ol", type="primary")
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

    hero(
        "Tələbə paneli",
        f"Salam, {student['name']}",
        f"{student['specialty']} · Kurs: {student['course']} · Qrup: {student['group']}",
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

    st.markdown(
        f'<span class="pill pill-receipt">Açıq semestr: {esc(season_label(season))}</span> '
        f'<span class="pill pill-received">Qalan hüquq: {remaining} fən</span>',
        unsafe_allow_html=True,
    )
    st.caption("Ən azı 1 fənn seçməlisiniz. İkinci fənn istəyə bağlıdır.")

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


def student_app_card(a):
    return (
        '<div class="app-card"><div class="app-head"><div>'
        f'<div class="app-title">{esc(a["subject"])}</div>'
        f'<div class="app-meta">{esc(a["semester"])} · {esc(a["credits"])} kredit · {esc(a["date"])}</div>'
        f'</div>{status_pill(a["status"])}</div>'
        f'{progress_html(a["status"])}</div>'
    )


@st.fragment(run_every=LIVE_REFRESH_SECONDS)
def my_applications(fin):
    """Tutor statusu dəyişəndə bu hissə avtomatik yenilənir — səhifəni refresh etmək lazım deyil."""
    apps = db.list_applications(fin=fin)
    active = [a for a in apps if a["status"] != STATUS_CANCELLED]
    stat_tiles([
        (len(active), "Aktiv müraciət"),
        (max(MAX_SUBJECTS - len(active), 0), "Qalan müraciət hüququ"),
        (sum(1 for a in apps if a["status"] == STATUS_APPROVED), "Təsdiqlənmiş"),
    ])
    if not apps:
        st.info("Hələ müraciətiniz yoxdur.")
        return
    for a in reversed(apps):
        st.markdown(student_app_card(a), unsafe_allow_html=True)


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


def student_profile_card(student, count):
    st.markdown(
        '<div class="app-card"><div class="app-head"><div>'
        f'<div class="app-title">{esc(student["name"])}</div>'
        f'<div class="app-meta">FIN: {esc(student["fin"])} · {esc(student["specialty"])}</div>'
        f'<div class="app-meta">Kurs: {esc(student["course"])} · Qrup: {esc(student["group"])} · '
        f'{esc(student["payment_form"])}</div>'
        f'</div><span class="pill pill-receipt">{count} müraciət</span></div></div>',
        unsafe_allow_html=True,
    )


def app_header_html(app, receipt_no=None):
    result_text = esc(app["result"]) or "—"
    receipt_pill = (
        f'<span class="pill pill-receipt">🧾 Qəbz {receipt_no}</span>' if receipt_no else ""
    )
    return (
        '<div class="app-card"><div class="app-head"><div>'
        f'<div class="app-title">{esc(app["subject"])}</div>'
        f'<div class="app-meta">{esc(app["semester"])} · {esc(app["credits"])} kredit · {esc(app["date"])}</div>'
        f'<div class="app-meta">Nəticə: <b>{result_text}</b></div>'
        f'</div><div class="pills">{status_pill(app["status"])}{receipt_pill}</div>'
        '</div></div>'
    )


def score_form(app, receipt_no=None):
    row = app["row"]
    st.markdown(app_header_html(app, receipt_no), unsafe_allow_html=True)

    with st.form(f"edit_{row}"):
        entry_text = st.text_input("Giriş balı", value=app["entry_score"], key=f"entry_{row}")
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
        st.session_state["flash"] = f"{app['subject']} üzrə məlumat yadda saxlandı. Nəticə: {result or '—'}"
        st.rerun()


def receipt_block(link, n, covered, key):
    rows = "".join(
        f'<div class="cov-row"><span>{esc(a["subject"])}</span>{status_pill(a["status"])}</div>'
        for a in covered
    )
    st.markdown(
        '<div class="app-card"><div class="app-head">'
        f'<div class="app-title">🧾 Qəbz {n}</div>'
        f'<span class="pill pill-receipt">{len(covered)} müraciətə aiddir</span>'
        f'</div>{rows}</div>',
        unsafe_allow_html=True,
    )

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
            f'style="width:100%;height:800px;border:none;border-radius:14px;"></iframe>',
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


def tutor_page(tutor_name):
    tutor = find_tutor(tutor_name)

    hero("Tutor paneli", tutor_name, "Tələbələrin müraciətləri, balları və qəbzləri")

    flash = st.session_state.pop("flash", None)
    if flash:
        st.success(flash)

    if tutor:
        season_block(tutor)

    mine = []
    for a in db.list_applications():
        student = db.get_student(a["fin"])
        if student and student["tutor"] == tutor_name:
            mine.append((a, student))

    if not mine:
        st.info("Sizin tələbələrinizə aid müraciət yoxdur.")
        return

    stat_tiles([
        (len({s["fin"] for _, s in mine}), "Tələbə"),
        (len(mine), "Müraciət"),
        (sum(1 for a, _ in mine if a["status"] in WAITING), "Baxılmalıdır"),
        (sum(1 for a, _ in mine if a["status"] == STATUS_APPROVED), "Təsdiqlənmiş"),
    ])

    status_filter = st.selectbox("Status filtri", ["Hamısı"] + STATUSES)

    # Tələbə üzrə qruplaşdırma: bir tələbənin bütün müraciətləri bir yerdə
    groups = {}
    for a, student in mine:
        if status_filter != "Hamısı" and a["status"] != status_filter:
            continue
        group = groups.setdefault(student["fin"].upper(), {"student": student, "apps": []})
        group["apps"].append(a)

    if not groups:
        st.info("Bu statusda müraciət yoxdur.")
        return

    fin_key = st.selectbox(
        "Tələbə",
        options=list(groups),
        format_func=lambda f: f"{groups[f]['student']['name']} · {len(groups[f]['apps'])} müraciət",
    )
    student = groups[fin_key]["student"]
    apps = groups[fin_key]["apps"]

    # Eyni qəbz linki olan müraciətlər eyni nömrəni alır
    links = []
    for a in apps:
        if a["receipt"] and a["receipt"] not in links:
            links.append(a["receipt"])
    receipt_no = {link: n for n, link in enumerate(links, start=1)}

    left, right = st.columns([1, 1], gap="large")
    with left:
        student_profile_card(student, len(apps))
        for a in apps:
            score_form(a, receipt_no.get(a["receipt"]))
    with right:
        if not links:
            st.warning("Qəbz yüklənməyib.")
        for link in links:
            n = receipt_no[link]
            covered = [a for a in apps if a["receipt"] == link]
            receipt_block(link, n, covered, key=f"{fin_key}_{n}")


# ---------- Əsas axın ----------

def main():
    st.markdown(APP_CSS, unsafe_allow_html=True)

    if st.session_state.get("role") is None:
        login_page()
        return

    _, out = st.columns([6, 1])
    if out.button("Çıxış"):
        st.session_state.clear()
        st.rerun()

    if st.session_state["role"] == "student":
        student_page(st.session_state["fin"])
    else:
        tutor_page(st.session_state["tutor_name"])


main()
