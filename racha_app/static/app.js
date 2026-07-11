// Helpers de fetch compartilhados.
async function api(method, url, body) {
  const opt = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) opt.body = JSON.stringify(body);
  const r = await fetch(url, opt);
  if (r.status === 401) { location.href = "/login"; throw new Error("auth"); }
  const data = r.status === 204 ? null : await r.json().catch(() => null);
  if (!r.ok) throw Object.assign(new Error("erro"), { data, status: r.status });
  return data;
}
const jget = (u) => api("GET", u);
const jpost = (u, b) => api("POST", u, b);
const jpatch = (u, b) => api("PATCH", u, b);
const jdel = (u) => api("DELETE", u);

const el = (tag, props = {}, ...kids) => {
  const n = Object.assign(document.createElement(tag), props);
  kids.flat().forEach((k) => n.append(k));
  return n;
};

// notificação flutuante (substitui alert)
function toast(msg, type = "erro") {
  let box = document.getElementById("toasts");
  if (!box) document.body.append((box = el("div", { id: "toasts" })));
  const t = el("div", { className: "toast " + type, textContent: msg,
    role: type === "erro" ? "alert" : "status" });
  box.append(t);
  setTimeout(() => t.remove(), 4000);
}

// desabilita + mostra spinner enquanto a ação async roda
async function busy(btn, fn) {
  const wasDisabled = btn.disabled;
  btn.disabled = true;
  btn.classList.add("loading");
  try { return await fn(); }
  finally { btn.classList.remove("loading"); btn.disabled = wasDisabled; }
}

// marca o link de navegação da página atual
document.querySelectorAll("nav a").forEach((a) => {
  if (a.getAttribute("href") === location.pathname) a.setAttribute("aria-current", "page");
});
