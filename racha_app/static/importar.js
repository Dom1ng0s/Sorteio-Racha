let PLAYERS = [];
let GROUPS = [];

document.getElementById("btn-parse").onclick = async () => {
  const text = document.getElementById("raw").value;
  PLAYERS = await jget("/api/players");
  const res = await jpost("/api/parse-list", { text });
  GROUPS = res.groups;
  renderRevisao(res.entries);
  document.getElementById("revisao").hidden = false;
  sessionStorage.setItem("pendingImport", "1"); // bloqueia sorteio até aplicar
};

function optionsFor(entry) {
  const sel = el("select", { className: "vinculo" });
  PLAYERS.forEach((p) =>
    sel.append(el("option", { value: "p" + p.id, textContent: `${p.name} (${p.stars}★)` }))
  );
  sel.append(el("option", { value: "new", textContent: "＋ cadastrar como novo" }));
  sel.append(el("option", { value: "ignore", textContent: "ignorar" }));
  if (entry.match_player_id && entry.match_type !== "none") sel.value = "p" + entry.match_player_id;
  else sel.value = "new";
  return sel;
}

function renderRevisao(entries) {
  const tbody = document.querySelector("#tabela tbody");
  tbody.textContent = "";
  entries.forEach((e) => {
    const sel = optionsFor(e);
    const stars = el("select", { className: "stars", hidden: sel.value !== "new" });
    for (let s = 1; s <= 6; s++)
      stars.append(el("option", { value: s, textContent: s + "★", selected: s === 3 }));
    const aliasChk = el("input", { type: "checkbox", checked: e.save_alias });

    const tag = e.needs_verify ? el("span", { className: "tag-verify", textContent: "verificar" }) : "";

    const nameCell = el("td", {}, e.name, " ", tag);
    const stCell = el("td", { className: e.present ? "ok" : "no", textContent: e.present ? "presente" : "ausente" });
    const linkCell = el("td", {}, sel, stars);
    const aliasCell = el("td", {}, aliasChk);

    sel.onchange = () => { stars.hidden = sel.value !== "new"; };

    const tr = el("tr", {}, nameCell, stCell, linkCell, aliasCell);
    tr._entry = e; tr._sel = sel; tr._stars = stars; tr._alias = aliasChk;
    tbody.append(tr);
  });
}

document.getElementById("btn-apply").onclick = async () => {
  const entries = [...document.querySelectorAll("#tabela tbody tr")].map((tr) => {
    const e = tr._entry, v = tr._sel.value;
    const base = { name: e.name, present: e.present, group: e.group };
    if (v === "ignore") return { ...base, action: "ignore" };
    if (v === "new") return { ...base, action: "new", stars: +tr._stars.value };
    return { ...base, action: "link", player_id: +v.slice(1), save_alias: tr._alias.checked };
  });
  await jpost("/api/apply-import", { groups: GROUPS, entries });
  sessionStorage.removeItem("pendingImport");
  document.getElementById("apply-msg").textContent = "✅ Presença aplicada!";
};
