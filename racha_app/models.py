"""Camada de acesso ao PostgreSQL (psycopg3 + pool de conexões).

Multi-tenant: os dados do racha (players/aliases/attendance) pertencem a uma
org. Toda função de dados recebe org_id e filtra por ele — isolamento é feito
aqui, na query, não na camada web. IDs vindos da URL só casam se forem da org
ativa (WHERE id=%s AND org_id=%s), então um ID de outra org não acha nada (IDOR).
"""
import atexit
import os

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

# Railway injeta DATABASE_URL no serviço quando você adiciona o addon Postgres.
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL não definido. Adicione o Postgres no Railway (ele injeta a "
        "variável) ou aponte para um Postgres local para rodar/testar.")

# Um pool por processo (worker). Threads compartilham — o pool é thread-safe.
POOL = ConnectionPool(DATABASE_URL, min_size=1, max_size=10,
                      kwargs={"row_factory": dict_row}, open=True)
atexit.register(POOL.close)  # encerra as threads do pool sem barulho no shutdown


def conn():
    """Context manager: commita ao sair, faz rollback em exceção, devolve ao pool."""
    return POOL.connection()


def init_db():
    with conn() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            pw_hash TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE TABLE IF NOT EXISTS orgs (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE TABLE IF NOT EXISTS memberships (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            org_id  INTEGER NOT NULL REFERENCES orgs(id)  ON DELETE CASCADE,
            role TEXT NOT NULL CHECK(role IN ('owner','admin','member')),
            PRIMARY KEY (user_id, org_id)
        );
        CREATE TABLE IF NOT EXISTS invites (
            id SERIAL PRIMARY KEY,
            org_id INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
            email TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','member')),
            token TEXT UNIQUE NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            accepted_at TIMESTAMPTZ
        );
        CREATE TABLE IF NOT EXISTS password_resets (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at TIMESTAMPTZ NOT NULL,
            used_at TIMESTAMPTZ
        );
        CREATE TABLE IF NOT EXISTS players (
            id SERIAL PRIMARY KEY,
            org_id INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            stars INTEGER NOT NULL CHECK(stars BETWEEN 1 AND 6),
            grupo TEXT NOT NULL CHECK(grupo IN ('mensalista','diarista')),
            UNIQUE(org_id, name)
        );
        CREATE TABLE IF NOT EXISTS attendance (
            player_id INTEGER PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
            present INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS aliases (
            id SERIAL PRIMARY KEY,
            org_id INTEGER NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
            player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
            alias TEXT NOT NULL,
            UNIQUE(org_id, alias)
        );
        """)


# ---------- usuários ----------
def create_user(email, pw_hash):
    with conn() as c:
        r = c.execute("INSERT INTO users(email, pw_hash) VALUES(%s,%s) RETURNING id",
                      (email, pw_hash)).fetchone()
        return r["id"]


def user_by_email(email):
    with conn() as c:
        return c.execute("SELECT * FROM users WHERE email = %s", (email,)).fetchone()


def user_by_id(uid):
    with conn() as c:
        return c.execute("SELECT * FROM users WHERE id = %s", (uid,)).fetchone()


def set_password(user_id, pw_hash):
    with conn() as c:
        c.execute("UPDATE users SET pw_hash = %s WHERE id = %s", (pw_hash, user_id))


# ---------- orgs / membros ----------
def create_org(name, owner_user_id):
    with conn() as c:
        oid = c.execute("INSERT INTO orgs(name) VALUES(%s) RETURNING id", (name,)).fetchone()["id"]
        c.execute("INSERT INTO memberships(user_id, org_id, role) VALUES(%s,%s,'owner')",
                  (owner_user_id, oid))
        return oid


def orgs_for(user_id):
    with conn() as c:
        return c.execute(
            "SELECT o.id, o.name, m.role FROM orgs o "
            "JOIN memberships m ON m.org_id = o.id WHERE m.user_id = %s "
            "ORDER BY o.name", (user_id,)).fetchall()


def role_of(user_id, org_id):
    with conn() as c:
        r = c.execute("SELECT role FROM memberships WHERE user_id = %s AND org_id = %s",
                      (user_id, org_id)).fetchone()
        return r["role"] if r else None


def is_member(user_id, org_id):
    return role_of(user_id, org_id) is not None


def members_of(org_id):
    with conn() as c:
        return c.execute(
            "SELECT u.id AS user_id, u.email, m.role FROM memberships m "
            "JOIN users u ON u.id = m.user_id WHERE m.org_id = %s "
            "ORDER BY m.role, u.email", (org_id,)).fetchall()


def add_member(user_id, org_id, role):
    with conn() as c:
        c.execute("INSERT INTO memberships(user_id, org_id, role) VALUES(%s,%s,%s) "
                  "ON CONFLICT (user_id, org_id) DO NOTHING", (user_id, org_id, role))


def remove_member(org_id, user_id):
    with conn() as c:
        c.execute("DELETE FROM memberships WHERE org_id = %s AND user_id = %s", (org_id, user_id))


def count_owners(org_id):
    with conn() as c:
        return c.execute("SELECT COUNT(*) n FROM memberships WHERE org_id = %s AND role='owner'",
                         (org_id,)).fetchone()["n"]


def rename_org(org_id, name):
    with conn() as c:
        c.execute("UPDATE orgs SET name = %s WHERE id = %s", (name, org_id))


# ---------- convites ----------
def create_invite(org_id, email, role, token):
    with conn() as c:
        c.execute("INSERT INTO invites(org_id, email, role, token) VALUES(%s,%s,%s,%s)",
                  (org_id, email, role, token))


def invite_by_token(token):
    with conn() as c:
        return c.execute("SELECT * FROM invites WHERE token = %s", (token,)).fetchone()


def pending_invites(org_id):
    with conn() as c:
        return c.execute(
            "SELECT id, email, role, created_at FROM invites "
            "WHERE org_id = %s AND accepted_at IS NULL ORDER BY created_at", (org_id,)).fetchall()


def accept_invite(token, user_id):
    """Adiciona o usuário à org do convite e marca aceito. Retorna org_id ou None."""
    with conn() as c:
        r = c.execute("SELECT * FROM invites WHERE token = %s AND accepted_at IS NULL",
                      (token,)).fetchone()
        if not r:
            return None
        c.execute("INSERT INTO memberships(user_id, org_id, role) VALUES(%s,%s,%s) "
                  "ON CONFLICT (user_id, org_id) DO NOTHING", (user_id, r["org_id"], r["role"]))
        c.execute("UPDATE invites SET accepted_at = now() WHERE token = %s", (token,))
        return r["org_id"]


def delete_invite(invite_id, org_id):
    with conn() as c:
        c.execute("DELETE FROM invites WHERE id = %s AND org_id = %s", (invite_id, org_id))


# ---------- reset de senha ----------
def create_reset(user_id, token):
    with conn() as c:
        c.execute("INSERT INTO password_resets(token, user_id, expires_at) "
                  "VALUES(%s,%s, now() + interval '1 hour')", (token, user_id))


def reset_by_token(token):
    with conn() as c:
        return c.execute(
            "SELECT * FROM password_resets WHERE token = %s AND used_at IS NULL "
            "AND expires_at > now()", (token,)).fetchone()


def use_reset(token):
    with conn() as c:
        c.execute("UPDATE password_resets SET used_at = now() WHERE token = %s", (token,))


# ---------- jogadores (escopo por org) ----------
def all_players(org_id):
    with conn() as c:
        return c.execute("SELECT * FROM players WHERE org_id = %s ORDER BY name",
                         (org_id,)).fetchall()


def all_aliases(org_id):
    with conn() as c:
        return c.execute("SELECT * FROM aliases WHERE org_id = %s", (org_id,)).fetchall()


def players_with_attendance(org_id, grupo=None):
    q = ("SELECT p.*, COALESCE(a.present,0) AS present FROM players p "
         "LEFT JOIN attendance a ON a.player_id = p.id WHERE p.org_id = %s")
    args = [org_id]
    if grupo:
        q += " AND p.grupo = %s"
        args.append(grupo)
    q += " ORDER BY p.name"
    with conn() as c:
        return c.execute(q, args).fetchall()


def aliases_for(org_id, player_id):
    with conn() as c:
        return c.execute(
            "SELECT * FROM aliases WHERE org_id = %s AND player_id = %s ORDER BY alias",
            (org_id, player_id)).fetchall()


def presentes(org_id):
    """Jogadores com present=true, com nome e estrelas para o sorteio."""
    with conn() as c:
        return c.execute(
            "SELECT p.id, p.name, p.stars FROM players p "
            "JOIN attendance a ON a.player_id = p.id "
            "WHERE p.org_id = %s AND a.present = 1", (org_id,)).fetchall()


def create_player(org_id, name, stars, grupo):
    with conn() as c:
        pid = c.execute("INSERT INTO players(org_id, name, stars, grupo) VALUES(%s,%s,%s,%s) "
                        "RETURNING id", (org_id, name, stars, grupo)).fetchone()["id"]
        c.execute("INSERT INTO attendance(player_id, present) VALUES(%s,0) "
                  "ON CONFLICT (player_id) DO NOTHING", (pid,))
        return pid


def update_player(org_id, player_id, stars=None, grupo=None):
    sets, args = [], []
    if stars is not None:
        sets.append("stars = %s"); args.append(stars)
    if grupo is not None:
        sets.append("grupo = %s"); args.append(grupo)
    if not sets:
        return
    args += [player_id, org_id]
    with conn() as c:
        c.execute(f"UPDATE players SET {', '.join(sets)} WHERE id = %s AND org_id = %s", args)


def delete_player(org_id, player_id):
    with conn() as c:
        c.execute("DELETE FROM players WHERE id = %s AND org_id = %s", (player_id, org_id))


def _player_in_org(c, org_id, player_id):
    return c.execute("SELECT 1 FROM players WHERE id = %s AND org_id = %s",
                     (player_id, org_id)).fetchone() is not None


def set_present(org_id, player_id, present):
    with conn() as c:
        if not _player_in_org(c, org_id, player_id):
            return False
        c.execute("INSERT INTO attendance(player_id, present) VALUES(%s,%s) "
                  "ON CONFLICT(player_id) DO UPDATE SET present = excluded.present",
                  (player_id, 1 if present else 0))
        return True


def reset_group_attendance(org_id, grupo):
    """Zera presença de todos os jogadores do grupo na org (criando linha se faltar)."""
    with conn() as c:
        c.execute("INSERT INTO attendance(player_id, present) "
                  "SELECT id, 0 FROM players WHERE org_id = %s AND grupo = %s "
                  "ON CONFLICT (player_id) DO NOTHING", (org_id, grupo))
        c.execute("UPDATE attendance SET present = 0 WHERE player_id IN "
                  "(SELECT id FROM players WHERE org_id = %s AND grupo = %s)", (org_id, grupo))


def add_alias(org_id, player_id, alias):
    with conn() as c:
        if not _player_in_org(c, org_id, player_id):
            return False
        c.execute("INSERT INTO aliases(org_id, player_id, alias) VALUES(%s,%s,%s) "
                  "ON CONFLICT (org_id, alias) DO NOTHING", (org_id, player_id, alias))
        return True


def delete_alias(org_id, alias_id):
    with conn() as c:
        c.execute("DELETE FROM aliases WHERE id = %s AND org_id = %s", (alias_id, org_id))


if __name__ == "__main__":
    # ponytail: self-check de isolamento entre orgs — o ponto crítico do multi-tenant.
    # Precisa de um Postgres em DATABASE_URL; roda tudo e limpa o que criou no fim.
    init_db()
    u1 = create_user("selfcheck_a@x.com", "h")
    u2 = create_user("selfcheck_b@x.com", "h")
    A = create_org("Racha A", u1)
    B = create_org("Racha B", u2)
    try:
        pa = create_player(A, "Arthur", 5, "mensalista")
        pb = create_player(B, "Bruno", 3, "diarista")

        assert [p["name"] for p in all_players(A)] == ["Arthur"]
        assert [p["name"] for p in all_players(B)] == ["Bruno"]

        # IDOR: A tentando mexer no jogador de B não faz nada
        delete_player(A, pb)
        assert len(all_players(B)) == 1, "delete cruzou org!"
        update_player(A, pb, stars=6)
        assert all_players(B)[0]["stars"] == 3, "update cruzou org!"
        assert set_present(A, pb, True) is False, "presença cruzou org!"
        assert presentes(B) == [], "presença vazou!"
        assert add_alias(A, pb, "b") is False, "alias cruzou org!"

        # mesmo nome pode existir em orgs diferentes
        create_player(B, "Arthur", 4, "mensalista")
        assert len(all_players(B)) == 2

        # membership / roles
        assert role_of(u1, A) == "owner"
        assert is_member(u2, A) is False
        add_member(u2, A, "member")
        assert role_of(u2, A) == "member"

        # convite
        create_invite(A, "c@x.com", "member", "selfcheck_tok")
        assert any(i["email"] == "c@x.com" for i in pending_invites(A))
        u3 = create_user("selfcheck_c@x.com", "h")
        assert accept_invite("selfcheck_tok", u3) == A
        assert is_member(u3, A) is True
        assert accept_invite("selfcheck_tok", u3) is None  # não reutiliza
        print("models ok — isolamento entre orgs garantido")
    finally:
        # limpa (CASCADE apaga orgs/players/aliases/memberships/invites juntos)
        with conn() as c:
            c.execute("DELETE FROM users WHERE email LIKE 'selfcheck_%'")
            c.execute("DELETE FROM orgs WHERE id IN (%s,%s)", (A, B))
