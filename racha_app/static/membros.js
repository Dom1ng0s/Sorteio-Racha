const PAPEL = { owner: "Dono", admin: "Admin", member: "Membro" };

async function load() {
  const d = await jget("/api/org/members");
  const manage = d.role === "owner" || d.role === "admin";
  const tbody = document.querySelector("#tabela-membros tbody");
  tbody.textContent = "";
  d.members.forEach((m) => {
    const cells = [el("td", { textContent: m.email }), el("td", { textContent: PAPEL[m.role] || m.role })];
    const act = el("td");
    // pode remover se gerencia, não é você e não é o único dono
    if (manage && m.user_id !== d.me && m.role !== "owner") {
      const x = el("button", { className: "danger", textContent: "Remover" });
      x.onclick = async () => {
        if (confirm("Remover " + m.email + "?")) { await jdel("/api/org/members/" + m.user_id); load(); }
      };
      act.append(x);
    }
    cells.push(act);
    tbody.append(el("tr", {}, ...cells));
  });

  document.getElementById("convites-sec").hidden = !manage;
  if (!manage) return;

  const ul = document.getElementById("lista-convites");
  ul.textContent = "";
  if (!d.invites.length) ul.append(el("li", { textContent: "(nenhum)", className: "hint" }));
  d.invites.forEach((inv) => {
    const x = el("button", { className: "danger tiny", textContent: "✕" });
    x.onclick = async () => { await jdel("/api/org/invites/" + inv.id); load(); };
    ul.append(el("li", {}, `${inv.email} (${PAPEL[inv.role] || inv.role}) `, x));
  });
}

document.getElementById("btn-convidar").onclick = async () => {
  const email = document.getElementById("conv-email").value.trim();
  const role = document.getElementById("conv-role").value;
  if (!email) return;
  try {
    await jpost("/api/org/invites", { email, role });
    document.getElementById("conv-email").value = "";
    alert("Convite enviado.");
    load();
  } catch (e) { alert((e.data && e.data.error) || "Erro ao convidar"); }
};

document.getElementById("btn-novo-racha").onclick = async () => {
  const name = document.getElementById("novo-racha").value.trim();
  if (!name) return;
  await jpost("/api/orgs", { name });
  location.reload();  // recarrega com a nova org ativa
};

load();
