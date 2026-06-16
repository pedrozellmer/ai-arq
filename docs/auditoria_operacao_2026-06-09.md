# 🛰️ Auditoria de Operação & Infra — AI.arq

> **Data:** 2026-06-09 · **Auditor:** Claude (papel COO + DevOps) · **Escopo:** operação e infraestrutura, não código de produto
> **Método:** leitura do repo + teste ao vivo do backend + Meta Graph API + Supabase MCP (banco real)

---

## 📋 Resumo (3 linhas)

A operação está **saudável e estável**: Instagram publicando 100% dos posts, backend no ar, RLS Fase 2 aplicada (banco fechado pra anon), custos dentro de todos os free tiers. O alerta do token Meta é **real mas menos grave do que parecia**: o token é válido e a renovação leva **1 comando** — porém o código de renovação automática está com a **API errada** e nunca é chamado, então hoje depende de ação manual. As pendências de roadmap (Indique-e-ganhe, email transacional, WhatsApp) continuam **todas paradas**, sem nenhum progresso de código.

---

## 🔴 URGENTE (com prazo)

### 1. Token Meta / Instagram — vence ~13/06 (4 dias) — **AÇÃO HOJE**

**Situação real (testei agora contra a Meta Graph API):**
- O token **está VÁLIDO** — `GET /me` devolveu `@ai.arq.br` (id 27523351593920440). ✅
- Os posts do IG **estão publicando 100%** — última publicação `feed_seg_w24` em 08/06 22:00, sem nenhum `failed` desde 02/06. ✅
- O primeiro post em risco é **`feed_sab_w24` em 13/06 14:00** — exatamente na virada do vencimento. Daí pra frente (semana 24 restante + semana 25 inteira, 8 posts) para se o token expirar.

**Achado importante — o token é tipo "Instagram Login" (`IGAA…`), não Facebook (`EAA…`):**
- A renovação correta é **`GET https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token=<TOKEN_ATUAL>`**.
- **Eu testei esse endpoint agora e ele FUNCIONOU** — devolveu um token novo válido por **60 dias** (5.184.000s) com todas as permissões (`instagram_business_content_publish`, etc.). Ou seja: renovar é **1 chamada**, sem precisar entrar no Facebook Developers, sem reautorizar app.

**🐞 Dois bugs operacionais por trás do alerta:**
1. **O código de renovação usa a API ERRADA.** `backend/instagram_api.py:219` (`refresh_long_lived_token`) chama `graph.facebook.com/oauth/access_token` com `grant_type=fb_exchange_token` e `client_id=META_APP_ID`. Isso é o fluxo de **token de usuário do Facebook** — não funciona pra token `IGAA…`. Além disso `META_APP_ID` nem existe no `.env`. Se alguém chamasse essa função hoje, ela falharia.
2. **Essa função NUNCA é chamada** em lugar nenhum do backend (confirmado por busca global). Não há job de renovação automática. O token só é renovado se alguém fizer manualmente.

**Passo a passo de renovação (escolha A — rápido, 5 min):**
1. Rodar 1 comando (PowerShell) com o token atual do `.env`:
   ```powershell
   $t = (Get-Content backend\.env | Where-Object {$_ -like "META_ACCESS_TOKEN=*"}) -replace "^META_ACCESS_TOKEN=",""
   (Invoke-RestMethod "https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token=$t").access_token
   ```
   (Importante: copiar o token do `.env` **exato** — caractere trocado dá erro `190 Failed to decrypt`.)
2. Copiar o `access_token` novo que voltar.
3. Colar nos **dois lugares**: `backend/.env` (local) **e** painel do Render → env var `META_ACCESS_TOKEN` → Save (Render redeploya sozinho).
4. Pronto — válido por +60 dias (até ~08/08/2026).

> ⚠️ Como o token expira a cada 60 dias e a renovação é manual, **isso vai voltar a acontecer em agosto**. Ver "Ações imediatas" item 2 pra automatizar de vez.

---

## 💰 Custos (estimativa mensal)

| Serviço | Plano | Uso atual | Custo/mês | Risco de estourar |
|---|---|---|---|---|
| **Anthropic** (Claude) | Pay-as-you-go | Por projeto: Sonnet 4 (análise de prancha) + Haiku 4.5 (classificação SINAPI). + chat widget (Haiku) + agente IG (Sonnet) | **~US$ 30–80** (estimativa p/ ~10–20 projetos/mês) | Sem free tier — é o **maior custo variável**. Cada reprocessamento e cada prancha pesada gasta. Sobe linear com uso. |
| **Replicate** (imagens IG) | Pay-as-you-go | Geração de imagem só pra marketing IG (não no fluxo do cliente) | **~US$ 2–10** | Baixo. Uso esporádico (posts). |
| **Render** | Free tier | Backend FastAPI, dorme após 15min | **US$ 0** | ⚠️ Free tier some horas/mês? Não — o limite é só "dorme". Sem risco de cobrança, mas há custo de UX (cold start). |
| **Supabase** | Free tier | DB **39 MB** / 500 MB · Storage **176 MB** / 1 GB · 12 usuários | **US$ 0** | 🟡 Storage é o que mais cresce: 73 pranchas = 175 MB (~2,4 MB/arquivo). No ritmo atual cabe ~mais 350 arquivos antes de bater 1 GB. DB tranquilo. |
| **GitHub Pages** | Free | Frontend estático | **US$ 0** | Nenhum. |
| **Stripe** | Por transação | ~3,99% + R$0,39/venda | Variável (só sobre receita) | Nenhum (custo proporcional à receita). |

**Total estimado: ~US$ 35–95/mês**, quase tudo Anthropic. **Nenhum free tier em risco imediato.** O único que vai pedir atenção em alguns meses é o **Storage do Supabase** (pranchas grandes acumulando).

> 💡 Já existe limpeza: `cleanup-90d.yml` (workflow) + tabela `cleanup_log` + cron de retenção. Vale confirmar que está apagando pranchas antigas do Storage (não só registros do banco) pra segurar o crescimento.

---

## ⚙️ Infra

### Render — cold start: **tratado** ✅
- Teste ao vivo: backend respondeu o `/` em **0,4s** (estava acordado — o cron do IG a cada 15min funciona como keep-alive de fato).
- **Não existe** `/health` (devolve 404) — o smoke test e o keep-alive batem em `/`, o que funciona.
- **UX do cold start está tratada**: `dashboard.html:2336-2338` mostra a mensagem *"Acordando o motor (servidor estava em standby) — pode levar 30 a 60 segundos no primeiro acesso do dia."* — em vez da barra de progresso mentir. Bom.
- Keep-alive efetivo: o `pg_cron` do Supabase chama `/api/instagram/scheduler/tick` **a cada 15 min** (confirmado ativo no banco). Isso mantém o Render quente quase o tempo todo de dia. Não é garantido 24/7 (o intervalo bate no limite dos 15min), mas na prática reduz muito o cold start.

### Smoke test E2E — **existe e está bem configurado** ✅
- `.github/workflows/smoke-test.yml` roda em **todo push no main** (com 120s de espera pro Render deployar) **+ cron diário 9h UTC** + manual.
- **3 níveis:** (1) endpoints públicos, (2) login Supabase + download de planilha real via HTTP, (3) **Playwright headless** que faz login no navegador real e clica "Baixar XLSX" — pega justamente o bug Daniela (navegação direta sem header Authorization).
- Depende dos secrets `SMOKE_USER_EMAIL` / `SMOKE_USER_PASSWORD` no GitHub pros níveis 2 e 3. **Não dá pra confirmar a última execução sem `gh`/acesso ao Actions** — vale o Pedro abrir a aba Actions do repo e olhar o status do último run (verde/vermelho).

### Deploy — **dois pipelines automáticos** ✅
- **Frontend:** `deploy-pages.yml` (custom, porque o pipeline automático do Pages falhava). Empacota a raiz em `_site/`, deploya no GitHub Pages a cada push no main. Último commit no main: `a8c989b` (aviso de PDF sem texto).
- **Backend:** Render redeploya automático a cada push no main (~3min).
- **Não há `render.yaml`** no repo — a config do Render vive só no painel (cloud). Funciona, mas significa que a config de infra do backend **não está versionada** (env vars, comando de start, etc. existem só no Render).

### Backups — ⚠️ ponto fraco do free tier
- **Supabase free NÃO tem PITR (point-in-time recovery)** nem backup diário automático garantido — backups diários completos são recurso de plano pago. No free, a recuperação depende de snapshots limitados da Supabase.
- **Storage (pranchas + planilhas) não tem redundância configurada** além da do próprio Supabase. Se um arquivo for apagado por engano (ex: cleanup mal calibrado), não há cópia.
- Como o DB é pequeno (39 MB), um **dump manual periódico** (pg_dump via MCP ou painel) seria um seguro barato. Ver "Decisões pra Pedro".

### Segurança do banco (Supabase advisors) — RLS aplicada, mas com ressalvas
- **RLS Fase 2 FOI aplicada** — corrige a nota de memória "bloqueio Fase 2". TODAS as 29 tabelas do schema `public` têm `rls_ativo = true` com policies (inclusive as que estavam abertas: `project_cashback_events`, `user_credits`, `project_clients`, `project_supplier_quotes`).
- Advisor de segurança retornou **84 avisos**, sendo:
  - **1 ERROR** — view `public.calibration_factors` com `SECURITY DEFINER` (roda com permissão do dono, não do usuário). Vale revisar/recriar como `SECURITY INVOKER`.
  - **40 WARN `rls_policy_always_true`** — a maioria é **intencional**: policies de leitura aberta nas tabelas de catálogo (SINAPI/TCPO/`catalog_*`) e policies que o backend usa via **service_role** (que por design tem acesso total). O advisor não distingue "service-role legítimo" de "vazamento". Mas **vale uma varredura** pra confirmar que nenhuma tabela com PII (ex: `chat_leads`, `contact_messages`, `project_clients`) tem policy `true` aberta pra `anon`.
  - **2 WARN** — buckets públicos `contact-attachments` e `logos` permitem **listar** todos os arquivos (policy SELECT ampla). Os dois estão vazios hoje, mas a policy devia permitir só leitura por URL, não listagem.
  - **1 WARN** — proteção contra senha vazada desligada no Supabase Auth (1 clique pra ligar no painel).

---

## 📋 Pendências paradas

### Roadmap (nenhuma teve progresso de código)
| Prioridade | Item | Estado real |
|---|---|---|
| 🥇 **TOP** | **Indique-e-ganhe** (loop viral) | **0% feito.** Confirmei no banco: não existe tabela `referrals` nem coluna `referral_code` em `profiles`. Spec pronta há ~1 mês (`docs/SPEC_INDIQUE_E_GANHE.md`), nunca implementada. É a maior alavanca de crescimento parada. |
| 🥈 | **Email transacional (Resend/SMTP)** | Parado. Ainda usa o email default do Supabase. Sem notificação de "planilha pronta", "cashback ganho", "volte após 30d". |
| 🥉 | **WhatsApp como canal** | Parado. Botão flutuante não existe. |
| — | **Email do domínio `pedro@ai.arq.br` (Zoho)** | Parado, **depende do Pedro** criar conta Zoho + colar DNS no Registro.br. Bloqueado fora do código. |
| — | Página de cases (testemunho Daniela), linkagem interna do blog, calculadora de preço na landing, templates email PT-BR | Backlog menor, todos parados. |

### Pendências de sessão
| Item | Estado |
|---|---|
| **RLS Fase 2 aplicada?** | ✅ **SIM** — banco fechado pra anon, todas as tabelas com RLS. (Memória dizia "bloqueada por exigir Supabase Pro" — desatualizada; foi aplicada.) |
| **Rotação da anon key (pós-RLS)** | ❓ Não verificável daqui. Era o passo 4 do guia. Pedro confirmar se rotacionou. |
| **CPF / Stripe duplicação** | ✅ Sem risco no backend. O checkout Stripe (`main.py:4750+`) **não passa CPF nenhum** — CPF não é coluna do banco (`profiles` não tem `cpf`). A duplicação, se houver, é só de UX no modal `#modal-cpf` do frontend, não cobra/duplica nada no Stripe. |
| **Reprocess confirmado?** | ✅ **SIM** — `/api/project/{job_id}/reprocess` existe e funciona, com política de 1 reprocessamento grátis por projeto (`REPROCESS_FREE_LIMIT = 1`). |

---

## 🛠️ Ações imediatas (ordem de prioridade)

1. **🔴 HOJE — renovar o token Meta** (5 min, 1 comando — passo a passo na seção URGENTE). Sem isso, IG para no dia 13/06. Eu posso rodar a renovação e te entregar o token novo pra você colar no Render — é só pedir.
2. **🟠 Esta semana — consertar a renovação automática do token.** Trocar `instagram_api.py:refresh_long_lived_token()` pelo fluxo correto (`graph.instagram.com/refresh_access_token` / `ig_refresh_token`) **e** agendar um `pg_cron` mensal que chame um endpoint que renova o token e grava no banco/env. Isso elimina o risco recorrente de 60 em 60 dias. (Hoje a função está com a API errada e nunca é chamada.)
3. **🟡 Corrigir o model ID inválido** em `backend/agent.py:650` — usa `claude-sonnet-4-6`, que **não é um ID válido** (os outros arquivos usam `claude-sonnet-4-20250514` e `claude-haiku-4-5`). Qualquer chamada por esse caminho de agente quebra em runtime. Trocar pelo ID válido.
4. **🟡 Revisar o ERROR do banco** — recriar a view `calibration_factors` como `SECURITY INVOKER`.
5. **🟡 Apertar buckets públicos** — remover a policy de listagem (`SELECT` amplo) de `contact-attachments` e `logos`; manter só leitura por URL.
6. **🟢 Ligar proteção de senha vazada** no Supabase Auth (1 clique no painel).
7. **🟢 Confirmar a aba Actions do GitHub** — abrir o repo → Actions → ver se o último smoke test e o último deploy estão verdes.

---

## ❓ Decisões pra Pedro

1. **Renovação do token IG: manual recorrente ou automatizar agora?** Recomendo automatizar (ação 2) — caso contrário você vai precisar lembrar de renovar a cada 60 dias, e se esquecer o IG para sem aviso. Custo: ~1h de dev minha.
2. **Backup do banco:** o plano free do Supabase não dá backup diário garantido. Quer que eu configure um **dump mensal automático** (workflow do GitHub que roda `pg_dump` e guarda o .sql como artefato/no repo privado)? É barato e te protege contra apagão acidental. Alternativa: subir pro Supabase Pro (US$25/mês) que tem PITR — provavelmente cedo demais com 12 usuários.
3. **Storage crescendo:** quer que eu confirme/ajuste o `cleanup-90d` pra apagar de fato as **pranchas no Storage** (não só registros), segurando o 1 GB do free tier? Hoje 176 MB / 1 GB.
4. **Indique-e-ganhe:** a spec está pronta há ~1 mês e é a maior alavanca parada. Quer que eu **implemente** (tabela + código de indicação + crédito na conversão)? É a recomendação número 1 do roadmap.
5. **Anon key:** você chegou a rotacionar a anon key do Supabase depois de aplicar a RLS Fase 2 (passo 4 do guia)? Se não, vale fazer agora que o banco está fechado.

---

*Auditoria gerada via leitura do repo + Meta Graph API ao vivo + Supabase MCP (dados reais de produção). Nada foi commitado nem alterado em produção — só leitura e testes não-destrutivos.*
