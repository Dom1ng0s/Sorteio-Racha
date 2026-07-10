"""Parser tolerante da lista de presença colada."""
import re

EMOJIS = "✅❌💰"
LINHA = re.compile(r"^\s*\d+\s*[-.)]\s*(.*)$")


def parse_list(text: str):
    """Retorna [{name, present, group}] na ordem em que aparecem."""
    grupo = "mensalista"
    grupos_vistos = []
    entries = []
    for raw in (text or "").splitlines():
        linha = raw.strip()
        if not linha:
            continue
        up = linha.upper()
        if "MENSALISTA" in up:
            grupo = "mensalista"
            if grupo not in grupos_vistos:
                grupos_vistos.append(grupo)
            continue
        if "DIARISTA" in up:
            grupo = "diarista"
            if grupo not in grupos_vistos:
                grupos_vistos.append(grupo)
            continue

        m = LINHA.match(linha)
        if not m:
            continue
        resto = m.group(1)
        present = "✅" in resto and "❌" not in resto
        nome = "".join(c for c in resto if c not in EMOJIS).strip()
        if not nome:  # ex.: "17-" sem nome
            continue
        if grupo not in grupos_vistos:
            grupos_vistos.append(grupo)
        entries.append({"name": nome, "present": present, "group": grupo})
    return {"groups": grupos_vistos, "entries": entries}


if __name__ == "__main__":
    r = parse_list("MENSALISTAS:\n1- Arthur ✅\n17-\n18-\n\nDIARISTAS:\n1- Deco ✅💰\n2- Lusking✅💰\n3- Sumido ❌")
    assert r["groups"] == ["mensalista", "diarista"], r["groups"]
    names = [(e["name"], e["present"], e["group"]) for e in r["entries"]]
    assert names == [("Arthur", True, "mensalista"), ("Deco", True, "diarista"),
                     ("Lusking", True, "diarista"), ("Sumido", False, "diarista")], names
    print("parsing ok")
