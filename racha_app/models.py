"""Camada de acesso ao SQLite. Conexão nova por chamada (Flask é multi-thread)."""
import os
import sqlite3

# RACHA_DB permite apontar pra um volume persistente no Railway (ex. /data/racha.db).
DB = os.environ.get("RACHA_DB", os.path.join(os.path.dirname(__file__), "racha.db"))


def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def init_db():
    d = os.path.dirname(DB)
    if d:
        os.makedirs(d, exist_ok=True)
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            stars INTEGER NOT NULL CHECK(stars BETWEEN 1 AND 6),
            grupo TEXT NOT NULL CHECK(grupo IN ('mensalista','diarista'))
        );
        CREATE TABLE IF NOT EXISTS attendance (
            player_id INTEGER PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
            present INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS aliases (
            id INTEGER PRIMARY KEY,
            player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
            alias TEXT UNIQUE NOT NULL
        );
        """)


def all_players():
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM players ORDER BY name")]


def all_aliases():
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM aliases")]


def players_with_attendance(grupo=None):
    q = ("SELECT p.*, COALESCE(a.present,0) AS present FROM players p "
         "LEFT JOIN attendance a ON a.player_id = p.id")
    args = ()
    if grupo:
        q += " WHERE p.grupo = ?"
        args = (grupo,)
    q += " ORDER BY p.name"
    with conn() as c:
        return [dict(r) for r in c.execute(q, args)]


def aliases_for(player_id):
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM aliases WHERE player_id = ? ORDER BY alias", (player_id,))]


def presentes():
    """Jogadores com present=true, com nome e estrelas para o sorteio."""
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT p.id, p.name, p.stars FROM players p "
            "JOIN attendance a ON a.player_id = p.id WHERE a.present = 1")]


def create_player(name, stars, grupo):
    with conn() as c:
        cur = c.execute("INSERT INTO players(name, stars, grupo) VALUES(?,?,?)",
                        (name, stars, grupo))
        c.execute("INSERT OR IGNORE INTO attendance(player_id, present) VALUES(?,0)",
                  (cur.lastrowid,))
        return cur.lastrowid


def update_player(player_id, stars=None, grupo=None):
    sets, args = [], []
    if stars is not None:
        sets.append("stars = ?"); args.append(stars)
    if grupo is not None:
        sets.append("grupo = ?"); args.append(grupo)
    if not sets:
        return
    args.append(player_id)
    with conn() as c:
        c.execute(f"UPDATE players SET {', '.join(sets)} WHERE id = ?", args)


def delete_player(player_id):
    with conn() as c:
        c.execute("DELETE FROM players WHERE id = ?", (player_id,))


def set_present(player_id, present):
    with conn() as c:
        c.execute("INSERT INTO attendance(player_id, present) VALUES(?,?) "
                  "ON CONFLICT(player_id) DO UPDATE SET present = excluded.present",
                  (player_id, 1 if present else 0))


def reset_group_attendance(grupo):
    """Zera presença de todos os jogadores do grupo (criando linha se faltar)."""
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO attendance(player_id, present) "
                  "SELECT id, 0 FROM players WHERE grupo = ?", (grupo,))
        c.execute("UPDATE attendance SET present = 0 WHERE player_id IN "
                  "(SELECT id FROM players WHERE grupo = ?)", (grupo,))


def add_alias(player_id, alias):
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO aliases(player_id, alias) VALUES(?,?)",
                  (player_id, alias))


def delete_alias(alias_id):
    with conn() as c:
        c.execute("DELETE FROM aliases WHERE id = ?", (alias_id,))
