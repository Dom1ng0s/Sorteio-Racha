"""Autenticação, sessão e envio de e-mail. Sem dependência nova:
werkzeug (vem com Flask) faz o hash de senha, smtplib (stdlib) manda e-mail."""
import os
import re
import secrets
import smtplib
import sys
from email.message import EmailMessage
from functools import wraps

from flask import g, jsonify, redirect, request, session
from werkzeug.security import check_password_hash, generate_password_hash

import models

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_email(e):
    return bool(EMAIL_RE.match((e or "").strip()))


def hash_password(pw):
    return generate_password_hash(pw)


def verify_password(pw_hash, pw):
    return check_password_hash(pw_hash, pw)


def new_token():
    return secrets.token_urlsafe(32)


# ---------- sessão ----------
def login_user(user_id):
    session.clear()
    session["user_id"] = user_id
    orgs = models.orgs_for(user_id)
    session["org_id"] = orgs[0]["id"] if orgs else None


def logout_user():
    session.clear()


def _wants_json():
    return request.path.startswith("/api/")


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        uid = session.get("user_id")
        if not uid or not models.user_by_id(uid):
            session.clear()
            return (jsonify({"error": "auth"}), 401) if _wants_json() else redirect("/login")

        org_id = session.get("org_id")
        if not org_id or not models.is_member(uid, org_id):
            orgs = models.orgs_for(uid)
            if not orgs:  # perdeu todas as orgs — cria uma padrão pra não travar
                org_id = models.create_org("Meu Racha", uid)
            else:
                org_id = orgs[0]["id"]
            session["org_id"] = org_id

        g.user_id = uid
        g.org_id = org_id
        g.role = models.role_of(uid, org_id)
        return f(*args, **kwargs)
    return wrapper


def manage_required(f):
    """owner/admin: gerência de membros e convites."""
    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if g.role not in ("owner", "admin"):
            return (jsonify({"error": "forbidden"}), 403) if _wants_json() else ("Sem permissão", 403)
        return f(*args, **kwargs)
    return wrapper


# ---------- e-mail ----------
def send_email(to, subject, body):
    """Manda via SMTP se SMTP_HOST estiver setado; senão loga no stderr (dev)."""
    host = os.environ.get("SMTP_HOST")
    sender = os.environ.get("SMTP_FROM", "no-reply@racha.local")
    if not host:
        print(f"\n[email dev] para={to}\nassunto={subject}\n{body}\n", file=sys.stderr, flush=True)
        return
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    port = int(os.environ.get("SMTP_PORT", 587))
    with smtplib.SMTP(host, port) as s:
        s.starttls()
        user, pw = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASS")
        if user:
            s.login(user, pw)
        s.send_message(msg)


if __name__ == "__main__":
    h = hash_password("segredo")
    assert verify_password(h, "segredo")
    assert not verify_password(h, "errado")
    assert valid_email("a@b.com") and not valid_email("nope")
    assert len(new_token()) > 20 and new_token() != new_token()
    print("auth ok")
