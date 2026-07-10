from flask import Flask, jsonify, redirect, render_template, request

import models
from balancing import sortear, validar_sorteio
from matching import best_match, normalize
from parsing import parse_list

app = Flask(__name__)
models.init_db()


# ---------- páginas ----------
@app.get("/")
def home():
    return redirect("/importar")


@app.get("/importar")
def importar():
    return render_template("importar.html")


@app.get("/mensalistas")
def mensalistas():
    return render_template("catalogo.html", grupo="mensalista", titulo="Mensalistas")


@app.get("/diaristas")
def diaristas():
    return render_template("catalogo.html", grupo="diarista", titulo="Diaristas")


@app.get("/sorteio")
def sorteio():
    return render_template("sorteio.html")


# ---------- importação ----------
@app.post("/api/parse-list")
def api_parse_list():
    parsed = parse_list(request.get_json(force=True).get("text", ""))
    players = models.all_players()
    aliases = models.all_aliases()
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
def api_apply_import():
    data = request.get_json(force=True)
    for grupo in data.get("groups", []):
        models.reset_group_attendance(grupo)

    for e in data.get("entries", []):
        action = e.get("action")
        if action == "ignore":
            continue
        if action == "new":
            pid = models.create_player(e["name"].strip(), int(e.get("stars", 3)), e["group"])
        elif action == "link":
            pid = int(e["player_id"])
            if e.get("save_alias"):
                models.add_alias(pid, normalize(e["name"]))
        else:
            continue
        models.set_present(pid, bool(e.get("present")))
    return jsonify({"ok": True})


# ---------- catálogo ----------
@app.get("/api/players")
def api_players():
    grupo = request.args.get("grupo")
    return jsonify(models.players_with_attendance(grupo))


@app.post("/api/players")
def api_create_player():
    d = request.get_json(force=True)
    try:
        pid = models.create_player(d["name"].strip(), int(d.get("stars", 3)), d["grupo"])
    except Exception as ex:
        return jsonify({"error": str(ex)}), 400
    return jsonify({"id": pid})


@app.patch("/api/players/<int:pid>")
def api_update_player(pid):
    d = request.get_json(force=True)
    stars = int(d["stars"]) if "stars" in d else None
    models.update_player(pid, stars=stars, grupo=d.get("grupo"))
    return jsonify({"ok": True})


@app.delete("/api/players/<int:pid>")
def api_delete_player(pid):
    models.delete_player(pid)
    return jsonify({"ok": True})


@app.get("/api/players/<int:pid>/aliases")
def api_list_aliases(pid):
    return jsonify(models.aliases_for(pid))


@app.post("/api/players/<int:pid>/aliases")
def api_add_alias(pid):
    alias = normalize(request.get_json(force=True).get("alias", ""))
    if not alias:
        return jsonify({"error": "apelido vazio"}), 400
    models.add_alias(pid, alias)
    return jsonify({"ok": True})


@app.delete("/api/aliases/<int:aid>")
def api_delete_alias(aid):
    models.delete_alias(aid)
    return jsonify({"ok": True})


# ---------- presença ----------
@app.get("/api/attendance")
def api_attendance():
    return jsonify(models.players_with_attendance())


@app.patch("/api/attendance/<int:pid>")
def api_toggle_attendance(pid):
    models.set_present(pid, bool(request.get_json(force=True).get("present")))
    return jsonify({"ok": True})


# ---------- sorteio ----------
@app.get("/api/validar-sorteio")
def api_validar():
    num = int(request.args.get("num_times", 2))
    pending = request.args.get("pending_import") == "1"
    return jsonify(validar_sorteio(models.presentes(), num, pending_import=pending))


@app.post("/api/sortear")
def api_sortear():
    d = request.get_json(force=True)
    num = int(d.get("num_times", 2))
    pending = bool(d.get("pending_import"))
    ps = models.presentes()
    v = validar_sorteio(ps, num, pending_import=pending)
    if not v["ok"]:
        return jsonify({"erros": v["erros"]}), 400
    res = sortear(ps, num)
    res["avisos"] = v["avisos"]
    return jsonify(res)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
