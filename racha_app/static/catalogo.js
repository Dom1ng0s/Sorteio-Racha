const grupo = window.GRUPO;

const semAcento = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

async function load() {
  const players = await jget("/api/players?grupo=" + grupo);
  const tbody = document.querySelector("#tabela tbody");
  tbody.textContent = "";
  players.forEach((p) => {
    const tr = row(p);
    tr.dataset.nome = semAcento(p.name);
    tr.dataset.present = p.present ? "1" : "0";
    tbody.append(tr);
  });
  reordenar();
  filtrar();
}

// presentes primeiro, depois ordem alfabética
function reordenar() {
  const tbody = document.querySelector("#tabela tbody");
  const rows = [...tbody.children].filter((tr) => tr.dataset.nome !== undefined);
  rows.sort((a, b) =>
    (b.dataset.present === "1") - (a.dataset.present === "1") ||
    a.dataset.nome.localeCompare(b.dataset.nome));
  rows.forEach((tr) => tbody.append(tr));
}

const busca = document.getElementById("busca");
function filtrar() {
  const q = semAcento(busca.value.trim());
  document.querySelectorAll("#tabela tbody tr").forEach((tr) => {
    if (tr.dataset.nome === undefined) return; // linha de apelidos expandida
    tr.hidden = q && !tr.dataset.nome.includes(q);
  });
}
busca.addEventListener("input", filtrar);

function row(p) {
  const pres = el("input", { type: "checkbox", checked: !!p.present, title: "Presente hoje" });
  pres.setAttribute("aria-label", "Presença de " + p.name);
  pres.onchange = () => {
    jpatch("/api/attendance/" + p.id, { present: pres.checked });
    tr.dataset.present = pres.checked ? "1" : "0";
    reordenar();
  };

  const stars = el("select");
  stars.setAttribute("aria-label", "Estrelas de " + p.name);
  for (let s = 1; s <= 6; s++)
    stars.append(el("option", { value: s, textContent: s + "★", selected: s === p.stars }));
  stars.onchange = () => jpatch("/api/players/" + p.id, { stars: +stars.value });

  const name = el("span", { className: "pname", textContent: p.name, tabIndex: 0, role: "button" });
  name.onclick = () => toggleAliases(p.id, tr);
  name.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleAliases(p.id, tr); } };

  const del = el("button", { className: "danger", textContent: "✕" });
  del.setAttribute("aria-label", "Remover " + p.name);
  del.onclick = async () => {
    if (confirm("Remover " + p.name + " do catálogo?")) { await jdel("/api/players/" + p.id); load(); }
  };

  const tr = el("tr", {}, el("td", {}, pres), el("td", {}, name), el("td", {}, stars), el("td", {}, del));
  return tr;
}

async function toggleAliases(pid, tr) {
  if (tr.nextSibling && tr.nextSibling._alias) { tr.nextSibling.remove(); return; }
  const aliases = await jget(`/api/players/${pid}/aliases`);
  const box = el("div", { className: "aliasbox" });
  const list = el("div");
  const draw = (arr) => {
    list.textContent = "Apelidos: ";
    if (!arr.length) list.append("(nenhum) ");
    arr.forEach((a) => {
      const x = el("button", { className: "danger tiny", textContent: "✕" });
      x.setAttribute("aria-label", "Remover apelido " + a.alias);
      x.onclick = async () => { await jdel("/api/aliases/" + a.id); refresh(); };
      list.append(el("span", { className: "chip" }, a.alias, x), " ");
    });
  };
  const inp = el("input", { placeholder: "novo apelido" });
  inp.setAttribute("aria-label", "Novo apelido");
  const add = el("button", { className: "icon-btn", textContent: "+" });
  add.setAttribute("aria-label", "Adicionar apelido");
  add.onclick = async () => {
    if (!inp.value.trim()) return;
    await jpost(`/api/players/${pid}/aliases`, { alias: inp.value }); inp.value = ""; refresh();
  };
  async function refresh() { draw(await jget(`/api/players/${pid}/aliases`)); }
  draw(aliases);
  box.append(list, inp, add);
  const arow = el("tr"); arow._alias = true;
  arow.append(el("td", { colSpan: 4 }, box));
  tr.after(arow);
}

const btnAdd = document.getElementById("btn-add");
btnAdd.onclick = () => busy(btnAdd, async () => {
  const name = document.getElementById("novo-nome").value.trim();
  const stars = +document.getElementById("novo-stars").value;
  if (!name) return;
  try { await jpost("/api/players", { name, stars, grupo }); } catch (e) { toast("Esse nome já existe no catálogo."); return; }
  document.getElementById("novo-nome").value = "";
  await load();
});

load();
