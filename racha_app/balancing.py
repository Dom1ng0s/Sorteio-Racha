"""Validação e sorteio balanceado de times."""
import random


def validar_sorteio(presentes, num_times, pending_import=False):
    """presentes: [{name, stars}]  ->  {ok, erros, avisos}."""
    erros, avisos = [], []
    n = len(presentes)

    if pending_import:
        erros.append("Há uma lista importada ainda não aplicada — aplique a presença antes de sortear.")
    if n == 0:
        erros.append("Nenhum jogador presente.")
    elif n < num_times:
        erros.append(f"Presentes insuficientes ({n}) para {num_times} times.")

    if n and n % num_times != 0:
        resto = n % num_times
        avisos.append(f"{resto} time(s) terão um jogador a mais (times de tamanhos diferentes).")
    if 0 < n < 8:
        avisos.append("Menos de 8 presentes — balanceamento por estrelas fica menos significativo.")
    if n:
        stars = [p["stars"] for p in presentes]
        if max(stars) - min(stars) > 4:
            avisos.append(f"Diferença grande de nível entre presentes ({min(stars)}★ a {max(stars)}★).")

    return {"ok": not erros, "erros": erros, "avisos": avisos}


def sortear(presentes, num_times):
    """Distribuição gulosa + busca local. presentes: [{name, stars}]."""
    n = len(presentes)
    base, resto = divmod(n, num_times)
    caps = [base + (1 if i < resto else 0) for i in range(num_times)]

    # embaralha antes de ordenar: jogadores de mesma estrela ficam em ordem
    # aleatória (sort é estável), então cada sorteio distribui os iguais
    # diferente sem mexer no equilíbrio de estrelas.
    jogadores = list(presentes)
    random.shuffle(jogadores)
    ordenados = sorted(jogadores, key=lambda p: p["stars"], reverse=True)
    times = [[] for _ in range(num_times)]
    somas = [0] * num_times

    for jog in ordenados:
        # time com vaga e menor soma atual; desempate aleatório entre times
        # de soma igual (embaralha a ordem antes do min, que é estável).
        ordem = list(range(num_times))
        random.shuffle(ordem)
        alvo = min((i for i in ordem if len(times[i]) < caps[i]),
                   key=lambda i: somas[i])
        times[alvo].append(jog)
        somas[alvo] += jog["stars"]

    # busca local: trocar pares que reduzem o desequilíbrio global
    def spread(s):
        return max(s) - min(s)

    for _ in range(500):
        melhorou = False
        for a in range(num_times):
            for b in range(a + 1, num_times):
                for ia, ja in enumerate(times[a]):
                    for ib, jb in enumerate(times[b]):
                        d_atual = abs(somas[a] - somas[b])
                        na = somas[a] - ja["stars"] + jb["stars"]
                        nb = somas[b] - jb["stars"] + ja["stars"]
                        if abs(na - nb) < d_atual:
                            times[a][ia], times[b][ib] = jb, ja
                            somas[a], somas[b] = na, nb
                            melhorou = True
        if not melhorou:
            break

    resultado = []
    for i, t in enumerate(times):
        resultado.append({
            "nome": f"Time {i + 1}",
            "jogadores": t,
            "soma": somas[i],
            "media": round(somas[i] / len(t), 2) if t else 0,
        })
    resultado.sort(key=lambda t: t["soma"], reverse=True)
    diff = spread(somas) if somas else 0
    return {"times": resultado, "diferenca": diff}


if __name__ == "__main__":
    assert not validar_sorteio([], 2)["ok"]
    assert not validar_sorteio([{"name": "a", "stars": 3}], 2)["ok"]
    assert validar_sorteio([{"name": "a", "stars": 3}, {"name": "b", "stars": 3}], 2)["ok"]
    ps = [{"name": f"p{i}", "stars": s} for i, s in enumerate([6, 6, 5, 5, 4, 4, 3, 3, 2, 2])]
    r = sortear(ps, 2)
    assert sum(len(t["jogadores"]) for t in r["times"]) == 10
    assert r["diferenca"] <= 1, r["diferenca"]
    # tamanhos desiguais não travam
    r2 = sortear(ps[:7], 2)
    assert sorted(len(t["jogadores"]) for t in r2["times"]) == [3, 4]

    # aleatoriedade: mesma lista, sorteios diferentes, mas sempre equilibrado
    big = [{"name": f"p{i}", "stars": s}
           for i, s in enumerate([6, 6, 5, 5, 5, 4, 4, 4, 4, 3, 3, 3, 2, 2, 2, 1] * 2)]
    assinaturas = set()
    for _ in range(20):
        r = sortear(big, 4)
        assert r["diferenca"] <= 1, r["diferenca"]
        assinaturas.add(tuple(sorted(
            tuple(sorted(j["name"] for j in t["jogadores"])) for t in r["times"])))
    assert len(assinaturas) > 1, "sorteio não variou!"
    print(f"balancing ok — {len(assinaturas)} composições distintas em 20 sorteios")
