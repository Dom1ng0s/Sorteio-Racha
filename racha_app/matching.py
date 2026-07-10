"""Normalização de nomes e casamento com o catálogo."""
import re
import unicodedata


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def best_match(name, players, aliases):
    """players: [{id,name,...}]  aliases: [{player_id,alias}]  (alias já normalizado).
    Retorna (player_id | None, tipo) onde tipo in exact|alias|substring|levenshtein|none."""
    n = normalize(name)
    if not n:
        return None, "none"

    by_norm = {}
    for p in players:
        by_norm.setdefault(normalize(p["name"]), p["id"])

    if n in by_norm:
        return by_norm[n], "exact"

    for a in aliases:
        if a["alias"] == n:
            return a["player_id"], "alias"

    # substring: n contido no nome do jogador ou vice-versa, candidato único
    subs = [pid for norm, pid in by_norm.items() if n in norm.split() or norm in n.split()
            or (len(n) >= 2 and (n in norm or norm in n))]
    subs = list(dict.fromkeys(subs))
    if len(subs) == 1:
        return subs[0], "substring"

    # levenshtein: aceita se distância <= 30% do tamanho (mín. 2)
    best_pid, best_d = None, None
    for norm, pid in by_norm.items():
        d = levenshtein(n, norm)
        if best_d is None or d < best_d:
            best_pid, best_d = pid, d
    limite = max(2, int(len(n) * 0.3))
    if best_pid is not None and best_d <= limite:
        return best_pid, "levenshtein"

    return None, "none"
