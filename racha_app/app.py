import os
import secrets

from flask import (Flask, g, jsonify, redirect, render_template, request,
                   session)

import auth
import models
from auth import login_required, manage_required
from balancing import sortear, validar_sorteio
from matching import best_match, normalize
from parsing import parse_list

app = Flask(__name__)
models.init_db()

# SECRET_KEY estável é obrigatório em produção (sessão sobrevive a restart e é a
# mesma entre workers). Sem ele, gera um por processo — ok só pra dev.
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",  # bloqueia POST/PATCH/DELETE cross-site (anti-CSRF)
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "1") != "0",
)


# ================= auth (páginas com form comum, sem JS) =================
@app.get("/signup")
def signup_page():
    return render_template("signup.html", next=request.args.get("next", ""))


@app.post("/signup")
def signup():
    email = request.form.get("email", "").strip().lower()
    pw = request.form.get("password", "")
    nxt = request.form.get("next") or "/importar"
    if not auth.valid_email(email):
        return render_template("signup.html", erro="E-mail inválido.", next=nxt), 400
    if len(pw) < 8:
        return render_template("signup.html", erro="Senha precisa de ao menos 8 caracteres.", next=nxt), 400
    if models.user_by_email(email):
        return render_template("signup.html", erro="E-mail já cadastrado.", next=nxt), 400
    uid = models.create_user(email, auth.hash_password(pw))
    models.create_org("Meu Racha", uid)
    auth.login_user(uid)
    return redirect(nxt)


@app.get("/login")
def login_page():
    return render_template("login.html", next=request.args.get("next", ""))


@app.post("/login")
def login():
    email = request.form.get("email", "").strip().lower()
    pw = request.form.get("password", "")
    nxt = request.form.get("next") or "/importar"
    u = models.user_by_email(email)
    if not u or not auth.verify_password(u["pw_hash"], pw):
        return render_template("login.html", erro="E-mail ou senha incorretos.", next=nxt), 401
    auth.login_user(u["id"])
    return redirect(nxt)


@app.post("/logout")
def logout():
    auth.logout_user()
    return redirect("/login")


@app.get("/forgot")
def forgot_page():
    return render_template("forgot.html")


@app.post("/forgot")
def forgot():
    email = request.form.get("email", "").strip().lower()
    u = models.user_by_email(email)
    if u:  # não revela se o e-mail existe — resposta é sempre a mesma
        token = auth.new_token()
        models.create_reset(u["id"], token)
        link = request.url_root.rstrip("/") + f"/reset/{token}"
        auth.send_email(email, "Redefinir senha — Racha",
                        f"Abra este link para redefinir sua senha (expira em 1h):\n{link}")
    return render_template("forgot.html", enviado=True)


@app.get("/reset/<token>")
def reset_page(token):
    if not models.reset_by_token(token):
        return render_template("reset.html", invalido=True), 400
    return render_template("reset.html", token=token)


@app.post("/reset/<token>")
def reset(token):
    r = models.reset_by_token(token)
    if not r:
        return render_template("reset.html", invalido=True), 400
    pw = request.form.get("password", "")
    if len(pw) < 8:
        return render_template("reset.html", token=token, erro="Senha precisa de ao menos 8 caracteres."), 400
    models.set_password(r["user_id"], auth.hash_password(pw))
    models.use_reset(token)
    return redirect("/login")


@app.get("/convite/<token>")
def accept_invite_page(token):
    if not session.get("user_id"):
        # precisa de conta; manda logar/cadastrar e voltar pra cá
        return redirect(f"/signup?next=/convite/{token}")
    oid = models.accept_invite(token, session["user_id"])
    if oid is None:
        return render_template("login.html", erro="Convite inválido ou já usado."), 400
    session["org_id"] = oid
    return redirect("/importar")


# ================= páginas do app =================
@app.get("/")
def home():
    return redirect("/importar" if session.get("user_id") else "/login")


@app.get("/importar")
@login_required
def importar():
    return render_template("importar.html", **_ctx())


@app.get("/mensalistas")
@login_required
def mensalistas():
    return render_template("catalogo.html", grupo="mensalista", titulo="Mensalistas", **_ctx())


@app.get("/diaristas")
@login_required
def diaristas():
    return render_template("catalogo.html", grupo="diarista", titulo="Diaristas", **_ctx())


@app.get("/sorteio")
@login_required
def sorteio():
    return render_template("sorteio.html", **_ctx())


@app.get("/membros")
@login_required
def membros():
    return render_template("membros.html", **_ctx())


def _ctx():
    """Contexto comum de nav: usuário, orgs e org ativa."""
    return {
        "user": models.user_by_id(g.user_id),
        "orgs": models.orgs_for(g.user_id),
        "org_id": g.org_id,
        "role": g.role,
    }


# ================= orgs =================
@app.post("/trocar-org/<int:oid>")
@login_required
def trocar_org(oid):
    if models.is_member(g.user_id, oid):
        session["org_id"] = oid
    return redirect(request.form.get("next") or "/importar")


@app.post("/api/orgs")
@login_required
def api_create_org():
    name = (request.get_json(force=True).get("name") or "").strip()
    if not name:
        return jsonify({"error": "nome vazio"}), 400
    oid = models.create_org(name, g.user_id)
    session["org_id"] = oid
    return jsonify({"id": oid})


@app.get("/api/org/members")
@login_required
def api_members():
    return jsonify({
        "role": g.role,
        "members": models.members_of(g.org_id),
        "invites": models.pending_invites(g.org_id) if g.role in ("owner", "admin") else [],
        "me": g.user_id,
    })


@app.post("/api/org/invites")
@manage_required
def api_invite():
    d = request.get_json(force=True)
    email = (d.get("email") or "").strip().lower()
    role = d.get("role", "member")
    if not auth.valid_email(email):
        return jsonify({"error": "e-mail inválido"}), 400
    if role not in ("admin", "member"):
        return jsonify({"error": "papel inválido"}), 400
    token = auth.new_token()
    models.create_invite(g.org_id, email, role, token)
    link = request.url_root.rstrip("/") + f"/convite/{token}"
    org = next((o for o in models.orgs_for(g.user_id) if o["id"] == g.org_id), None)
    auth.send_email(email, "Convite para um racha",
                    f'Você foi convidado para "{org["name"] if org else "um racha"}".\n'
                    f"Aceite abrindo:\n{link}")
    return jsonify({"ok": True})


@app.delete("/api/org/invites/<int:iid>")
@manage_required
def api_delete_invite(iid):
    models.delete_invite(iid, g.org_id)
    return jsonify({"ok": True})


@app.delete("/api/org/members/<int:uid>")
@manage_required
def api_remove_member(uid):
    # não deixa remover o último owner (org ficaria órfã)
    if models.role_of(uid, g.org_id) == "owner" and models.count_owners(g.org_id) <= 1:
        return jsonify({"error": "não é possível remover o único owner"}), 400
    models.remove_member(g.org_id, uid)
    return jsonify({"ok": True})


# ================= importação =================
@app.post("/api/parse-list")
@login_required
def api_parse_list():
    text = (request.get_json(force=True).get("text", "") or "")[:20000]  # cap anti-DoS
    parsed = parse_list(text)
    players = models.all_players(g.org_id)
    aliases = models.all_aliases(g.org_id)
    pid_name = {p["id"]: p["name"] for p in players}
    verify = {"substring", "levenshtein"}

    out = []
    for e in parsed["entries"]:
        pid, tipo = best_match(e["name"], players, aliases)
        out.append({
            "name": e["name"],
            "present": e["present"],
            "group": e["group"],
            "match_player_id": pid,
            "match_type": tipo,
            "match_player_name": pid_name.get(pid),
            "needs_verify": tipo in verify,
            "save_alias": tipo in verify,   # marcado por padrão nos incertos
            "new_stars": 3,
        })
    return jsonify({"groups": parsed["groups"], "entries": out})


@app.post("/api/apply-import")
@login_required
def api_apply_import():
    data = request.get_json(force=True)
    for grupo in data.get("groups", []):
        models.reset_group_attendance(g.org_id, grupo)

    for e in data.get("entries", []):
        action = e.get("action")
        if action == "ignore":
            continue
        if action == "new":
            pid = models.create_player(g.org_id, e["name"].strip(), int(e.get("stars", 3)), e["group"])
        elif action == "link":
            pid = int(e["player_id"])
            if e.get("save_alias"):
                models.add_alias(g.org_id, pid, normalize(e["name"]))
        else:
            continue
        models.set_present(g.org_id, pid, bool(e.get("present")))
    return jsonify({"ok": True})


# ================= catálogo =================
@app.get("/api/players")
@login_required
def api_players():
    grupo = request.args.get("grupo")
    return jsonify(models.players_with_attendance(g.org_id, grupo))


@app.post("/api/players")
@login_required
def api_create_player():
    d = request.get_json(force=True)
    name = (d.get("name") or "").strip()
    if not name:
        return jsonify({"error": "nome vazio"}), 400
    try:
        stars = int(d.get("stars", 3))
        if not 1 <= stars <= 6:
            return jsonify({"error": "estrelas fora de 1–6"}), 400
        if d.get("grupo") not in ("mensalista", "diarista"):
            return jsonify({"error": "grupo inválido"}), 400
        pid = models.create_player(g.org_id, name, stars, d["grupo"])
    except Exception:
        return jsonify({"error": "nome já existe"}), 400
    return jsonify({"id": pid})


@app.patch("/api/players/<int:pid>")
@login_required
def api_update_player(pid):
    d = request.get_json(force=True)
    stars = None
    if "stars" in d:
        stars = int(d["stars"])
        if not 1 <= stars <= 6:
            return jsonify({"error": "estrelas fora de 1–6"}), 400
    grupo = d.get("grupo")
    if grupo is not None and grupo not in ("mensalista", "diarista"):
        return jsonify({"error": "grupo inválido"}), 400
    models.update_player(g.org_id, pid, stars=stars, grupo=grupo)
    return jsonify({"ok": True})


@app.delete("/api/players/<int:pid>")
@login_required
def api_delete_player(pid):
    models.delete_player(g.org_id, pid)
    return jsonify({"ok": True})


@app.get("/api/players/<int:pid>/aliases")
@login_required
def api_list_aliases(pid):
    return jsonify(models.aliases_for(g.org_id, pid))


@app.post("/api/players/<int:pid>/aliases")
@login_required
def api_add_alias(pid):
    alias = normalize(request.get_json(force=True).get("alias", ""))
    if not alias:
        return jsonify({"error": "apelido vazio"}), 400
    models.add_alias(g.org_id, pid, alias)
    return jsonify({"ok": True})


@app.delete("/api/aliases/<int:aid>")
@login_required
def api_delete_alias(aid):
    models.delete_alias(g.org_id, aid)
    return jsonify({"ok": True})


# ================= presença =================
@app.get("/api/attendance")
@login_required
def api_attendance():
    return jsonify(models.players_with_attendance(g.org_id))


@app.patch("/api/attendance/<int:pid>")
@login_required
def api_toggle_attendance(pid):
    models.set_present(g.org_id, pid, bool(request.get_json(force=True).get("present")))
    return jsonify({"ok": True})


# ================= sorteio =================
@app.get("/api/validar-sorteio")
@login_required
def api_validar():
    num = max(2, min(int(request.args.get("num_times", 2)), 20))
    pending = request.args.get("pending_import") == "1"
    return jsonify(validar_sorteio(models.presentes(g.org_id), num, pending_import=pending))


@app.post("/api/sortear")
@login_required
def api_sortear():
    d = request.get_json(force=True)
    num = max(2, min(int(d.get("num_times", 2)), 20))  # clamp anti-DoS
    pending = bool(d.get("pending_import"))
    ps = models.presentes(g.org_id)
    v = validar_sorteio(ps, num, pending_import=pending)
    if not v["ok"]:
        return jsonify({"erros": v["erros"]}), 400
    res = sortear(ps, num)
    res["avisos"] = v["avisos"]
    return jsonify(res)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")
