# Implantação — Gestor AKF multiusuário

Guia para colocar o app no ar (web, privado) com login e banco compartilhado.
Stack: **Streamlit Community Cloud** (hospedagem privada gratuita) + **Supabase** (banco).

> Enquanto não fizer isso, o app continua rodando **localmente** na sua máquina como
> antes (modo admin único, sem banco) — nada quebra.

---

## Passo 1 — Criar o projeto Supabase (banco)

1. Acesse <https://supabase.com> e entre (pode usar a conta do Google).
2. **New project** → dê um nome (ex.: `gestor-akf`), defina uma senha de banco e a
   região mais próxima (South America / São Paulo). **Crie um projeto NOVO**, separado
   do NEOControl (dados financeiros não devem dividir banco com o app de EPI).
3. Quando o projeto subir, vá em **SQL Editor → New query**, abra o arquivo
   [`db/schema.sql`](../db/schema.sql) deste projeto, **copie todo o conteúdo, cole e
   clique em Run**. Isso cria as tabelas (`usuarios`, `borderos`, `passivo_lancamentos`…).
4. Crie o bucket de PDFs: **Storage → New bucket** → nome `borderos` → **Private**.
5. Pegue as chaves em **Project Settings → API**:
   - **Project URL** → será o `SUPABASE_URL`.
   - **service_role key** (em "Project API keys") → será o `SUPABASE_SERVICE_KEY`.
     ⚠️ É secreta e poderosa — só vai nos *secrets* do app, nunca no GitHub.

---

## Passo 2 — Repositório privado no GitHub

1. Em <https://github.com> → **New repository** → nome `gestor-akf` → **Private** → Create.
2. Suba o código (o `.gitignore` já protege segredos, planilhas e PDFs):
   ```powershell
   cd C:\Users\alant\gestor-akf
   git init
   git add .
   git commit -m "Gestor AKF — base + multiusuário (fase 1)"
   git branch -M main
   git remote add origin https://github.com/SEU_USUARIO/gestor-akf.git
   git push -u origin main
   ```

---

## Passo 3 — Publicar no Streamlit Community Cloud

1. Acesse <https://share.streamlit.io> e entre com a conta do **GitHub**.
2. **Create app → Deploy a public app from GitHub** → escolha o repo `gestor-akf`,
   branch `main`, arquivo principal `app.py`.
3. Em **Advanced settings → Secrets**, cole o conteúdo de
   [`.streamlit/secrets.exemplo.toml`](../.streamlit/secrets.exemplo.toml) preenchido:
   ```toml
   SUPABASE_URL = "https://SEU-PROJETO.supabase.co"
   SUPABASE_SERVICE_KEY = "a service_role key do passo 1"
   BOOTSTRAP_ADMIN_EMAIL = "seu-email@neoformas.com.br"
   CONSISTEM_API_KEY = "o token do CSMEN050"
   ```
4. **Deploy**. Quando subir, deixe o app **privado**: **Settings → Sharing** →
   desmarque acesso público e **adicione os e-mails (Google)** das pessoas do
   financeiro que poderão abrir.

---

## Passo 4 — Primeiro acesso e usuários

1. Abra o app com o e-mail do `BOOTSTRAP_ADMIN_EMAIL` → você entra como **admin**.
2. Vá em **👥 Usuários** e cadastre cada pessoa com o papel:
   - **admin** — tudo + gerencia usuários.
   - **financeiro** — alimenta dados (borderôs, passivo, seleção) e consulta.
   - **leitura** — só relatórios.
3. Cada pessoa também precisa estar na **whitelist** do Sharing (passo 3.4) para
   conseguir abrir o app.

---

## Observações

- **Dados sensíveis em serviço de terceiros:** o app fica no Community Cloud e o banco
  no Supabase. Para uso interno de poucos usuários é adequado; se quiser tudo "dentro de
  casa", dá para hospedar numa máquina/servidor da Neo Formas (mais controle, mais
  manutenção) — me avise que ajusto o guia.
- **Token do Consistem:** o mesmo do NEOControl. Como já transitou pelo chat, vale
  regenerá-lo no CSMEN050 quando puder.
- **Custos:** Community Cloud e o plano free do Supabase são gratuitos para esse porte.
