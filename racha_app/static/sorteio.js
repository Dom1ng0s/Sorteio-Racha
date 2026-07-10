const numSel = document.getElementById("num-times");
const btn = document.getElementById("btn-sortear");

function pending() { return sessionStorage.getItem("pendingImport") === "1" ? "1" : "0"; }

async function validar() {
  const v = await jget(`/api/validar-sorteio?num_times=${numSel.value}&pending_import=${pending()}`);
  const box = document.getElementById("validacao");
  box.textContent = "";
  v.erros.forEach((m) => box.append(el("div", { className: "erro", textContent: "⛔ " + m })));
  v.avisos.forEach((m) => box.append(el("div", { className: "aviso", textContent: "⚠️ " + m })));
  btn.disabled = !v.ok;
  const at = await jget("/api/attendance");
  document.getElementById("contador").textContent = at.filter((p) => p.present).length;
}

btn.onclick = async () => {
  try {
    const r = await jpost("/api/sortear", { num_times: +numSel.value, pending_import: pending() === "1" });
    render(r);
  } catch (e) {
    alert((e.data && e.data.erros || ["erro"]).join("\n"));
    validar();
  }
};

function render(r) {
  const out = document.getElementById("resultado");
  out.textContent = "";
  const diff = el("p", { className: "diff" });
  diff.append("Diferença forte × fraco: ", el("span", { className: "num", textContent: r.diferenca + "★" }));
  out.append(diff);
  const wrap = el("div", { className: "times" });
  r.times.forEach((t) => {
    const card = el("div", { className: "card" });
    const h = el("h3", {}, el("span", { textContent: t.nome }),
      el("span", { className: "soma", textContent: t.soma + "★" }));
    card.append(h);
    const ul = el("ul");
    t.jogadores.forEach((j) => ul.append(el("li", {},
      el("span", { textContent: j.name }), el("span", { className: "st", textContent: j.stars + "★" }))));
    card.append(el("div", { style: "font-size:.8rem;color:var(--muted);padding:0 .9rem .3rem", textContent: "média " + t.media + "★" }));
    card.append(ul);
    wrap.append(card);
  });
  out.append(wrap);
}

numSel.onchange = validar;
validar();
