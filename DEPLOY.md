# Deploy no Railway

App Flask (`racha_app/`) + **PostgreSQL gerenciado**, multi-tenant (contas,
rachas/orgs, convites). Servido por gunicorn (ver `Procfile`).

## Passos

1. **Suba o projeto** (uma das opções):
   - GitHub: dê `git init`, commit, push, e no Railway → *New Project → Deploy from GitHub repo*.
   - CLI: `npm i -g @railway/cli`, `railway login`, `railway init`, `railway up`.

2. **Adicione o banco** — no projeto → **+ New → Database → PostgreSQL**.
   O Railway cria o Postgres e injeta a variável `DATABASE_URL` no serviço do app
   automaticamente. **Não precisa de volume.** O banco é um servidor separado: os
   dados sobrevivem a todo deploy/redeploy e o Railway faz backup automático.

3. **Variáveis de ambiente** (aba **Variables** do serviço do app):
   - `SECRET_KEY` — **obrigatório em produção.** Assina o cookie de sessão. Sem
     ele, cada worker gera uma chave diferente e ninguém mantém login.
     Gere com `python -c "import secrets; print(secrets.token_hex(32))"`.
   - E-mail (convites e reset de senha). Sem isso o app funciona, mas o link vai
     pro **log do servidor** (stderr) em vez de ser enviado:
     `SMTP_HOST`, `SMTP_PORT` (padrão 587), `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`.
   - `COOKIE_SECURE` — padrão `1` (cookie só via HTTPS). Deixe assim em produção;
     use `0` apenas se rodar local sem HTTPS.

4. Pronto. O Railway detecta o Python via `requirements.txt`, roda o `Procfile`,
   injeta a porta em `$PORT` e cria as tabelas no primeiro boot (`init_db`).
   A URL pública sai em *Settings → Networking → Generate Domain*.

## Notas

- **Sem reset de dados no deploy:** o Postgres é gerenciado pelo Railway, fora do
  ciclo de vida do app. Fazer redeploy, trocar código ou reiniciar não toca nos
  dados. Isso era o problema do SQLite-em-arquivo — resolvido.
- `--workers 2` no Procfile: Postgres aguenta concorrência (o SQLite não aguentava,
  por isso era `--workers 1`). Cada worker abre seu próprio pool de conexões
  (`max_size=10` em `models.py`). Suba workers se precisar de mais carga.
- **Dev local:** aponte `DATABASE_URL` para um Postgres local (ex.
  `docker run -e POSTGRES_PASSWORD=x -p 5432:5432 postgres`) ou use o do Railway
  via `railway run python racha_app/app.py`. O app exige `DATABASE_URL` — sem ela
  não sobe (de propósito, pra não rodar sem banco por engano).

## Modelo de acesso

- **Conta** (e-mail + senha) → participa de vários **rachas** (orgs).
- Papéis por racha: `owner` (criador), `admin`, `member`. Owner/admin convidam e
  removem membros; todos editam jogadores e sorteiam.
- Convite: owner/admin manda por e-mail um link `/convite/<token>`; quem abre
  logado entra no racha. Reset de senha: `/forgot` → link `/reset/<token>` (1h, uso único).
