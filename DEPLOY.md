# Deploy no Railway

App Flask (`racha_app/`) + SQLite. Servido por gunicorn (ver `Procfile`).

## Passos

1. **Suba o projeto** (uma das opções):
   - GitHub: dê `git init`, commit, push, e no Railway → *New Project → Deploy from GitHub repo*.
   - CLI: `npm i -g @railway/cli`, `railway login`, `railway init`, `railway up`.

2. **Persista o banco** (obrigatório — sem isso os dados somem a cada redeploy):
   - No serviço → aba **Volumes** → *New Volume*, mount path `/data`.
   - Aba **Variables** → adicione `RACHA_DB = /data/racha.db`.

3. Pronto. O Railway detecta o Python via `requirements.txt`, roda o `Procfile`
   e injeta a porta em `$PORT`. A URL pública sai em *Settings → Networking → Generate Domain*.

## Notas

- `--workers 1` no Procfile de propósito: SQLite tem um escritor só, e é app de
  uso pessoal. Se um dia precisar de mais carga, troque o SQLite por Postgres
  (Railway tem addon) antes de subir workers.
- Sem volume o app roda igual, mas o `racha.db` é efêmero (reinício = banco zerado).
