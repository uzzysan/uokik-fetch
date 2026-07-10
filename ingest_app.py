"""
ingest_app.py — manual PDF ingest for UOKiK decisions (fairpact.pl/ingest).

Password-gated upload -> Gemini extraction -> editable review -> save to the
fairpact database (klauzule_niedozwolone + provenance in decyzje_uokik/decyzje_pdfs).
Runs as a local service behind nginx. Reuses pdf_parser + decision_extractor + models.
"""
from __future__ import annotations
import os, hmac, re, time, uuid, secrets
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

import config
from database import SessionLocal, init_db
from models import KlauzulaNiedozwolona, DecyzjaUOKiK, DecyzjaPDF
import pdf_parser
import decision_extractor

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = Path(config.INGEST_UPLOAD_DIR)
QUARANTINE = UPLOAD_DIR / "quarantine"
SAVED = UPLOAD_DIR / "saved"
for _d in (QUARANTINE, SAVED):
    _d.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD = 30 * 1024 * 1024
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

_COOKIE_SECURE = os.getenv("INGEST_COOKIE_SECURE", "true").lower() in ("1", "true", "yes")
app = FastAPI(title="UOKiK Ingest")
app.add_middleware(
    SessionMiddleware,
    secret_key=config.INGEST_SESSION_SECRET or "insecure-dev-secret",
    https_only=_COOKIE_SECURE, same_site="lax", max_age=8 * 3600,
)

@app.on_event("startup")
def _startup():
    try:
        init_db()
    except Exception:
        pass

_login_attempts: dict = {}
def _rate_limited(ip: str) -> bool:
    now = time.time()
    xs = [t for t in _login_attempts.get(ip, []) if now - t < 300]
    _login_attempts[ip] = xs
    return len(xs) >= 5
def _record_fail(ip: str):
    _login_attempts.setdefault(ip, []).append(time.time())

def _authed(request: Request) -> bool:
    return bool(request.session.get("authed"))
def _csrf(request: Request) -> str:
    tok = request.session.get("csrf")
    if not tok:
        tok = secrets.token_urlsafe(24)
        request.session["csrf"] = tok
    return tok
def _check_csrf(request: Request, token: Optional[str]) -> bool:
    return bool(token) and hmac.compare_digest(token, request.session.get("csrf", ""))

def _parse_date(s: str):
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None

def _unique_numer(db, base: str) -> str:
    cand = base
    while db.query(KlauzulaNiedozwolona.id).filter_by(numer_postanowienia=cand).first():
        cand = f"MAN-{uuid.uuid4().hex[:10]}"
    return cand

@app.get("/ingest", response_class=HTMLResponse)
def home(request: Request):
    if not _authed(request):
        return templates.TemplateResponse(request, "login.html", {"csrf": _csrf(request), "error": None})
    return templates.TemplateResponse(request, "upload.html", {"csrf": _csrf(request), "error": None})

@app.post("/ingest/login", response_class=HTMLResponse)
def login(request: Request, password: str = Form(""), csrf_token: str = Form("")):
    ip = request.client.host if request.client else "?"
    if _rate_limited(ip):
        return templates.TemplateResponse(request, "login.html", {"csrf": _csrf(request), "error": "Za duzo prob. Sprobuj ponownie za kilka minut."}, status_code=429)
    if not _check_csrf(request, csrf_token):
        return templates.TemplateResponse(request, "login.html", {"csrf": _csrf(request), "error": "Blad CSRF, odswiez strone."}, status_code=400)
    if config.INGEST_PASSWORD and hmac.compare_digest(password, config.INGEST_PASSWORD):
        request.session["authed"] = True
        return RedirectResponse("/ingest", status_code=303)
    _record_fail(ip)
    return templates.TemplateResponse(request, "login.html", {"csrf": _csrf(request), "error": "Nieprawidlowe haslo."}, status_code=401)

@app.get("/ingest/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/ingest", status_code=303)

@app.post("/ingest/upload", response_class=HTMLResponse)
async def upload(request: Request, pdf: UploadFile = File(...), csrf_token: str = Form("")):
    if not _authed(request):
        return RedirectResponse("/ingest", status_code=303)
    if not _check_csrf(request, csrf_token):
        return templates.TemplateResponse(request, "upload.html", {"csrf": _csrf(request), "error": "Blad CSRF, odswiez strone."}, status_code=400)
    data = await pdf.read()
    if len(data) > MAX_UPLOAD:
        return templates.TemplateResponse(request, "upload.html", {"csrf": _csrf(request), "error": "Plik za duzy (max 30 MB)."}, status_code=400)
    if not data[:5].startswith(b"%PDF"):
        return templates.TemplateResponse(request, "upload.html", {"csrf": _csrf(request), "error": "To nie jest plik PDF."}, status_code=400)
    draft_id = uuid.uuid4().hex
    qpath = QUARANTINE / f"{draft_id}.pdf"
    qpath.write_bytes(data)
    warning = None
    draft = {"sygnatura": "", "data_decyzji": "", "numer_decyzji": "", "pozwany": "", "powod": "Prezes UOKiK", "branza": "", "region": "", "klauzule": []}
    text = ""
    try:
        text = pdf_parser.extract_text_from_pdf(str(qpath)) or ""
    except Exception as e:
        warning = f"Nie udalo sie wyodrebnic tekstu: {e}"
    if text:
        try:
            draft = decision_extractor.extract_decision(text)
        except Exception as e:
            warning = f"Ekstrakcja AI nie powiodla sie: {e}. Uzupelnij dane recznie."
    else:
        warning = warning or "Pusty tekst PDF (mozliwy skan bez warstwy tekstowej). Uzupelnij recznie."
    if not draft.get("klauzule"):
        draft["klauzule"] = [{"postanowienie_niedozwolone": "", "numer_postanowienia": "", "zagadnienie": ""}]
    return templates.TemplateResponse(request, "review.html", {"csrf": _csrf(request), "draft": draft, "draft_id": draft_id, "pdf_filename": pdf.filename or f"{draft_id}.pdf", "warning": warning})

@app.post("/ingest/save", response_class=HTMLResponse)
async def save(request: Request):
    if not _authed(request):
        return RedirectResponse("/ingest", status_code=303)
    form = await request.form()
    if not _check_csrf(request, form.get("csrf_token")):
        return HTMLResponse("Blad CSRF", status_code=400)
    draft_id = re.sub(r"[^a-f0-9]", "", form.get("draft_id", ""))[:32]
    filename = form.get("pdf_filename") or "decyzja.pdf"
    dec = {
        "sygnatura": (form.get("sygnatura") or "").strip(),
        "data_decyzji": (form.get("data_decyzji") or "").strip(),
        "numer_decyzji": (form.get("numer_decyzji") or "").strip(),
        "pozwany": (form.get("pozwany") or "").strip(),
        "powod": ((form.get("powod") or "").strip() or "Prezes UOKiK"),
        "branza": (form.get("branza") or "").strip(),
        "region": (form.get("region") or "").strip(),
    }
    for _f, _n in (("sygnatura",100),("numer_decyzji",50),("pozwany",500),("powod",500),("branza",200),("region",100)):
        if dec[_f]:
            dec[_f] = dec[_f][:_n]
    tresci = form.getlist("k_tresc")
    numery = form.getlist("k_numer")
    zagad = form.getlist("k_zagadnienie")
    clauses = []
    for i, t in enumerate(tresci):
        t = (t or "").strip()
        if not t:
            continue
        clauses.append({
            "postanowienie_niedozwolone": t,
            "numer_postanowienia": (numery[i].strip()[:50] if i < len(numery) else ""),
            "zagadnienie": (zagad[i].strip()[:500] if i < len(zagad) else ""),
        })
    if not clauses:
        return HTMLResponse("Brak klauzul do zapisania. Wroc i dodaj co najmniej jedna.", status_code=400)
    ddate = _parse_date(dec["data_decyzji"])
    rok = dec["data_decyzji"][:4] if re.match(r"^\d{4}", dec["data_decyzji"]) else (str(ddate.year) if ddate else None)
    db = SessionLocal()
    saved = 0; skipped = 0
    numer_decyzji = dec["numer_decyzji"] or f"MAN-DEC-{uuid.uuid4().hex[:8]}"
    try:
        qpath = QUARANTINE / f"{draft_id}.pdf"
        saved_path = None; fsize = None; safe = None
        if qpath.exists():
            safe = re.sub(r"[^A-Za-z0-9._-]", "_", filename) or "decyzja.pdf"
            saved_path = SAVED / f"{draft_id}_{safe}"
            saved_path.write_bytes(qpath.read_bytes())
            fsize = saved_path.stat().st_size
        decyzja = db.query(DecyzjaUOKiK).filter_by(numer_decyzji=numer_decyzji).first()
        if not decyzja:
            decyzja = DecyzjaUOKiK(
                numer_decyzji=numer_decyzji, data_wydania=ddate,
                sygnatura_akt=dec["sygnatura"] or None, branza=dec["branza"] or None,
                region=dec["region"] or None, rok=rok, pdf_filename=filename,
                pdf_local_path=str(saved_path) if saved_path else None,
                status_parsowania="zweryfikowane",
            )
            db.add(decyzja); db.flush()
        if saved_path:
            db.add(DecyzjaPDF(decyzja_id=decyzja.id, pdf_url=f"manual://{safe}", local_path=str(saved_path), file_size=fsize, download_date=datetime.utcnow()))
        today = date.today()
        for c in clauses:
            exists = db.query(KlauzulaNiedozwolona.id).filter_by(sygnatura=dec["sygnatura"] or None, postanowienie_niedozwolone=c["postanowienie_niedozwolone"]).first()
            if exists:
                skipped += 1; continue
            base = c["numer_postanowienia"] or f"MAN-{uuid.uuid4().hex[:10]}"
            db.add(KlauzulaNiedozwolona(
                numer_postanowienia=_unique_numer(db, base), data_wyroku=ddate,
                sygnatura=dec["sygnatura"] or None, postanowienie_niedozwolone=c["postanowienie_niedozwolone"],
                branza=dec["branza"] or None, powod=dec["powod"] or None, pozwany=dec["pozwany"] or None,
                data_wpisu=today, zagadnienie=c["zagadnienie"] or None, source="manual",
            ))
            saved += 1
        db.commit()
    except Exception as e:
        db.rollback()
        return HTMLResponse(f"Blad zapisu: {type(e).__name__}: {e}", status_code=500)
    finally:
        db.close()
    try:
        if qpath.exists():
            qpath.unlink()
    except Exception:
        pass
    return templates.TemplateResponse(request, "done.html", {"saved": saved, "skipped": skipped, "numer_decyzji": numer_decyzji})
