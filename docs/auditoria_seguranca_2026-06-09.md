# 🔐 Auditoria de Segurança — AI.arq · 09/06/2026

> Auditor: `security-reviewer` · Verificação do estado REAL via Supabase MCP (project `kqjabzwgbfuivzlcfvvu`) + leitura de código backend/frontend + teste ativo com a anon key pública.
> Base anterior: `docs/auditoria_rls_2026-06-02.md` e `docs/migrations_rls_planejadas.sql`.

---

## Resumo executivo

As migrations RLS planejadas em 02/06 **NÃO foram aplicadas** — o banco continua exatamente como na auditoria anterior, com policies abertas pra `anon` (`qual=true`). **Provei na prática**: usando só a anon key pública (que está no JS do site), li dados reais de `user_credits` (saldos, UUIDs de usuários) e `contact_messages` (nome, email, telefone, IP). O backend foi corretamente migrado pra `service_role` nas rotas certas e os endpoints HTTP estão com checagem de dono/admin — o problema é 100% no banco, não na aplicação.

**Grade de risco geral: 🔴 CRÍTICO** — vazamento de PII e dado financeiro em produção, explorável agora por qualquer pessoa, sem login.

| Área | Grade |
|---|---|
| 🔑 RLS Supabase (banco) | 🔴 Crítico |
| Secrets no frontend | 🟢 Baixo |
| Auth backend (JWT/admin/IDOR) | 🟢 Baixo |
| Stripe | 🟡 Médio |
| Headers HTTP | 🟡 Médio |
| LGPD / cookie consent | 🟢 Baixo |
| CORS | 🟡 Médio |

---

## 🔑 ESTADO RLS REAL (via MCP) — ACHADO #1

**Veredito: as migrations NÃO foram aplicadas. Tudo continua aberto pra `anon`.**

Provas coletadas:

1. **Histórico de migrations** (`list_migrations`): a última é `20260518181327_add_get_project_owner_rpc` (18/05). **Não existe nenhuma migration de 02/06 ou depois.** O arquivo `migrations_rls_planejadas.sql` nunca rodou.
2. **`pg_policies` agora** = idêntico à auditoria de 02/06. Nenhuma policy `_select_own`, `_insert_own` etc. existe. As policies abertas originais (`qual=true`, role `anon`/`public`) seguem todas lá.
3. **RLS está LIGADO** em todas as tabelas (`relrowsecurity=true`) — mas isso é inútil, porque a policy aberta concede tudo. RLS ligado + policy `qual=true` = porta destrancada.
4. **🚨 Teste ativo (explorado de verdade com a anon key pública):**
   - `GET /rest/v1/user_credits` → retornou linhas reais: `user_id` (UUID), `amount_cents` (ex: 200000 = R$2.000), `source_ref` ("rafael_2026_05_04", "sidnei_2026_05_04"), descrição interna com nome de usuário. **Vazamento financeiro + PII confirmado.**
   - `GET /rest/v1/contact_messages` → retornou lead real: nome, email, telefone, mensagem, `source_page`, `user_agent` (IP/navegador). **Vazamento de PII confirmado.**
   - `project_clients`, `chat_leads`, `project_cashback_events` → hoje vazios (`[]`), mas o **caminho de leitura está aberto** — qualquer dado novo vaza na hora que entrar.

### Tabela por tabela (estado REAL hoje)

| Tabela | Estado atual | Deveria ser | Aplicada? | Risco |
|---|---|---|---|---|
| `user_credits` | `ALL` `qual=true` p/ `public` | SELECT só do próprio user | ❌ Não | 🔴 Crítico — fraude de crédito + vazamento de saldo (**vazando agora**) |
| `project_cashback_events` | `INSERT`+`SELECT` p/ `anon` `qual=true` | SELECT só do dono; escrita só service_role | ❌ Não | 🔴 Crítico — anon pode inserir cashback fraudulento (R$30-60/projeto) |
| `project_clients` | `SELECT/INSERT/UPDATE/DELETE` p/ `anon` `qual=true` | SELECT só do dono | ❌ Não | 🔴 Crítico — PII de cliente final (LGPD) |
| `contact_messages` | `SELECT/UPDATE` p/ anon `qual=true` | só INSERT público; SELECT removido | ❌ Não | 🔴 Crítico — PII de leads (**vazando agora**) |
| `chat_leads` | `SELECT/UPDATE` p/ anon `qual=true` | só INSERT público | ❌ Não | 🔴 Crítico — PII de leads |
| `project_items` | `ALL` p/ anon `qual=true` | dono via JOIN | ❌ Não | 🟡 Médio — medições por projeto |
| `project_supplier_quotes` | `ALL` p/ anon `qual=true` | dono via JOIN | ❌ Não | 🟡 Médio — cotações comerciais |
| `item_reviews` | `ALL` p/ anon `qual=true` | dono via JOIN | ❌ Não | 🟡 Médio |
| `item_notes` | `ALL` p/ anon `qual=true` | dono via JOIN | ❌ Não | 🟡 Médio |
| `cronogramas` | `INSERT/SELECT/UPDATE` p/ `public` `qual=true` | dono via JOIN | ❌ Não | 🟡 Médio |
| `agent_conversations` | `ALL` p/ `public` `qual=true` | dono (user_id ou JOIN) | ❌ Não | 🟡 Médio — conversas com a IA |
| `projects` | INSERT (`with_check` aberto) + UPDATE (`qual=true`) p/ `public` | INSERT/UPDATE só do próprio user_id | ❌ Não | 🟡 Médio — sobrescrever projeto alheio |
| `catalog_*` / `sinapi_*` | `ALL` `qual=true` | SELECT público, escrita só service_role | ❌ Não | 🟡 Médio — anon pode corromper catálogo |
| `tcpo_composicoes` / `tcpo_insumos` | SELECT p/ `anon,authenticated` + write p/ anon | SELECT só authenticated, sem write | ❌ Não | 🟡 Médio — copyright Pini exposto + corrompível |
| `density_benchmarks` / `market_heuristics` | `ALL`/SELECT+INSERT p/ anon | sem policy (só service_role) | ❌ Não | 🟡 Médio — diferencial competitivo exposto |
| `instagram_scheduled_posts` / `instagram_post_insights` | `ALL`/SELECT+INSERT p/ anon | sem policy (só service_role) | ❌ Não | 🟢 Baixo — operacional interno |
| `nps_responses` | INSERT anon + SELECT do próprio user | OK (já estava razoável) | n/a | 🟢 Baixo |
| `profiles` | SELECT/UPDATE do próprio + admin | OK | n/a | 🟢 Baixo |
| `beta_codes` | admin manage + authenticated read | OK | n/a | 🟢 Baixo |

**Conclusão do achado #1:** o backend já está preparado (service_role nas rotas certas), o "passo 0" do plano foi feito (Pedro confirmou a env no Render). Faltou só o passo final — aplicar o SQL. Hoje o sistema está no pior estado possível: backend pronto, banco aberto.

---

## 🟢 Acertos (o que está certo)

1. **Backend migrado pra `service_role` corretamente.** `main.py` usa `SUPABASE_SERVICE_ROLE_KEY` no header `Authorization` em todas as rotas não-autenticadas (webhook, contato, leads, jobs, admin), e usa o JWT do user via `_supa_rest_as_user(request, ...)` nas rotas de dono. O `apikey` continua sendo a anon (exigência do PostgREST) — correto.
2. **Validação de JWT é de verdade.** `_get_user_from_request` bate o token contra `/auth/v1/user` do Supabase (não só decodifica) — não dá pra forjar.
3. **Guard de admin sólido.** `_require_admin` exige JWT válido + email == `zarelalopes@gmail.com`. Todos os ~9 endpoints `/api/admin/*` chamam ele.
4. **IDOR coberto na aplicação.** `_require_project_owner` aparece em ~40 endpoints. `/api/sheet/{job_id}` foi corrigido (confirmado — tem o `_require_project_owner` e o comentário do fix). Endpoints com `{user_id}` (`cashback-all`, `by-user`, `credits/balance`) checam `jwt_user.id == user_id` ou admin.
5. **Sem secrets no frontend.** Nenhum `service_role`, `sk_live`, `sk_test` em HTML/JS. Só a anon key (pública por design) em `aiarq-utils.js` e `onboarding-tour.js` — confirmado que o role é `anon`, não `service_role`.
6. **Stripe entrante não existe** (confirmado): só checkout de saída + `verify`. Nada de webhook = nada de assinatura HMAC pra vazar. (Mas isso tem um custo — ver P1.)
7. **Cookie consent LGPD-ready.** `cookie-consent.js` grava a escolha com timestamp + versão, analytics é opt-in, ESC = "só essenciais" (default conservador), e é acessível (cor+ícone+texto, daltônico-safe). Dispara evento `aiarq:consent-changed` pra telemetria reagir.

---

## 🔴 Críticos (P0)

### P0-1 — RLS aberta pra anon (vazamento ativo de PII + financeiro)
Detalhado no achado #1. **Explorável agora, sem login**, com a anon key que está pública no JS do site. Já vazando `user_credits` e `contact_messages` reais. **Ação: aplicar `migrations_rls_planejadas.sql` hoje.** Passo exato abaixo.

### P0-2 — Anon key precisa ser rotacionada
A anon key atual está em screenshots, históricos e no git público (`pedrozellmer/ai-arq`). Mesmo depois de fechar a RLS, ela continua sendo uma chave válida com role `anon`. Como o backend usa service_role, dá pra rotacionar sem quebrar o backend — só precisa atualizar `aiarq-utils.js` **e** `onboarding-tour.js` (são os 2 lugares no frontend). Fazer **depois** de fechar a RLS (passo 5-6 do plano).

---

## 🟡 Médios (P1)

### P1-1 — Sem webhook Stripe entrante (confiança no redirect do cliente)
Não há `checkout.session.completed` webhook. A confirmação de pagamento depende de `/api/checkout/verify/{session_id}` chamado pelo browser no redirect de sucesso. Se o cliente fecha a aba antes do redirect, o pagamento acontece no Stripe mas o sistema pode não registrar. Pior: `verify_payment` não tem checagem de dono — qualquer um com um `session_id` vê `paid`/`amount` de qualquer checkout (vazamento menor de valor, não de cartão). Recomendado pra Fase 5/mensalidade: implementar webhook com verificação de assinatura HMAC (`stripe.Webhook.construct_event`).

### P1-2 — Headers HTTP ausentes (CSP / HSTS / X-Frame-Options)
`curl https://ai.arq.br` não traz `Content-Security-Policy`, `Strict-Transport-Security`, `X-Frame-Options` nem `X-Content-Type-Options`. O `index.html` também não tem meta CSP. GitHub Pages não deixa setar headers de resposta, mas dá pra mitigar com `<meta http-equiv="Content-Security-Policy">` no `<head>` (CSP e X-Content-Type funcionam por meta; HSTS e X-Frame não). Sem X-Frame/`frame-ancestors`, o site pode ser embutido em iframe (clickjacking). Risco real é baixo (site institucional + login Supabase com domínio próprio), mas é higiene barata. Backend (Render/Cloudflare) já tem TLS; vale checar HSTS lá também.

### P1-3 — CORS `allow_origins=["*"]` + `allow_credentials=True`
`main.py:831` combina origem coringa com credenciais. Essa combinação é inválida pela spec (o browser ignora/recusa quando há credencial), então na prática não abre brecha hoje — mas sinaliza intenção permissiva. Como a auth é por header `Authorization` (não cookie), o impacto é baixo. Recomendado: restringir `allow_origins` a `https://ai.arq.br` (+ localhost de dev) e deixar `allow_credentials=False`, ou manter `*` sem credentials.

### P1-4 — Módulos do backend ainda com anon key hardcoded
`calibrator.py`, `classifier.py`, `density_calibration.py`, `sinapi_classifier.py`, `sinapi_loader.py`, `agent.py` (e alguns `*_matcher`/`*_loader`) ainda têm a anon key hardcoded ou usam só `SUPABASE_KEY` (anon) no `Authorization`. Hoje funciona porque a RLS está aberta. **Quando a RLS fechar**, esses módulos vão falhar ao escrever em `density_benchmarks`, `market_heuristics`, `agent_conversations`, `catalog_*` (que passam a exigir service_role). Precisa migrar esses módulos pra `SUPABASE_SERVICE_ROLE_KEY` **junto** com a aplicação da RLS, senão calibração/classificação/agente quebram. **Esse é o risco prático nº1 de aplicar a RLS sem teste em branch.**

### P1-5 — Endpoints `{user_id}` sem auth (menores)
`/api/nps/check/{user_id}` consulta NPS por user_id sem validar JWT — vaza só "respondeu NPS sim/não" (baixo). `/api/nps` (POST) aceita user_id arbitrário no body sem auth — anon pode poluir NPS de qualquer user. Baixo impacto, mas vale fechar quando mexer nessa área.

---

## 🛠️ Top fixes (em ordem)

1. **🔴 HOJE — Fechar a RLS.** Antes de aplicar, resolver o P1-4 (módulos com anon key). Passo exato abaixo.
2. **🔴 Rotacionar a anon key** (P0-2) depois da RLS fechada — atualizar `aiarq-utils.js` E `onboarding-tour.js`.
3. **🟡 Restringir CORS** (P1-3) — `allow_origins=["https://ai.arq.br"]`, `allow_credentials=False`.
4. **🟡 Adicionar meta CSP + X-Content-Type-Options** nos HTMLs (P1-2).
5. **🟡 Webhook Stripe + ownership no `verify`** quando entrar mensalidade (P1-1).

### Passo exato pra aplicar a RLS (já que o backend está pronto)

> ⚠️ O Free plan do Supabase não tem branch. Como já não dá pra testar em branch isolada e a aplicação já está em service_role, a ordem segura é:

**Passo A — Migrar os módulos do backend que ainda usam anon (P1-4).**
Em `calibrator.py`, `classifier.py`, `density_calibration.py`, `sinapi_classifier.py`, `sinapi_loader.py`, `agent.py`, trocar o `Authorization` pra usar a service_role:
```python
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or "<anon fallback temporário>"
# nos headers de escrita: Authorization: Bearer {SUPABASE_SERVICE_ROLE_KEY}; apikey continua a anon
```
Commit + push (deploy Render ~3min) + smoke test (calibração, classificação, agente IG).

**Passo B — Aplicar o SQL via MCP `apply_migration`** (NÃO `execute_sql` — DDL deve ser migration versionada):
```
apply_migration(
  project_id="kqjabzwgbfuivzlcfvvu",
  name="rls_hardening_2026_06_09",
  query=<corpo de docs/migrations_rls_planejadas.sql, sem o cabeçalho de comentário>
)
```
O SQL é idempotente (`DROP POLICY IF EXISTS` antes de cada `CREATE`).

**Passo C — Smoke test produção** (itens do passo 3 do .sql):
- Listar projetos (admin + user comum)
- Criar projeto, baixar planilha, ver cashback no dashboard
- Disparar tick do scheduler IG
- **Re-rodar o teste de vazamento**: `GET /rest/v1/user_credits` e `/rest/v1/contact_messages` com a anon key devem voltar `[]` ou erro — não mais dados reais.

**Passo D — Rotacionar anon key** (Supabase → Settings → API → Reset) e atualizar `aiarq-utils.js` + `onboarding-tour.js`. Commit + push.

---

## ❓ Decisão pra Pedro

**A pergunta principal foi respondida: as migrations NÃO foram aplicadas. O banco está aberto e está vazando dado de usuário agora** (eu li saldo de crédito e mensagem de contato real só com a chave pública do site).

O backend já está pronto (você fez o passo 0 certo — service_role no Render). Falta só apertar o botão: aplicar o SQL.

**O que preciso de você pra decidir:**

1. **Posso aplicar a RLS hoje?** Como o Free plan não tem branch pra testar isolado, tem um risco controlado: alguns módulos internos (calibração, classificador, agente IG) ainda usam a chave anon e vão quebrar quando a porta fechar. O jeito seguro é eu **primeiro arrumar esses 6 arquivos do backend** (passo A), fazer deploy, testar, e **só então** aplicar o SQL. São ~30min de trabalho meu + 2 deploys. **Quer que eu toque isso agora de ponta a ponta?**

2. **Rotacionar a anon key** logo depois — vai exigir um hard-refresh no seu navegador e nos dos usuários (a sessão de login pode pedir re-login). Tudo bem fazer isso hoje, ou prefere avisar a Daniela e os outros antes?

> Nota: esta auditoria só LEU o banco. Nenhuma mudança foi aplicada. Nada foi commitado.
