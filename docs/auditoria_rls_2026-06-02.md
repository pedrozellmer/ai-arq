# Auditoria RLS — Supabase AI.arq
**Data:** 2026-06-02
**Projeto:** kqjabzwgbfuivzlcfvvu (ai-arq, US-East-1)
**Auditor:** varredura automatizada via MCP

---

## Resumo executivo

Todas as 29 tabelas do schema `public` têm RLS ativado (bom ponto de partida). Porém, a **maioria das policies das tabelas de dados de projeto são abertas pro role `anon`** com `qual = true` — qualquer requisição com a anon key consegue ler/escrever/apagar dados de qualquer usuário. Isso só não é catastrófico porque o frontend usa exclusivamente a anon key e o backend (Render) usa a service_role key, mas significa que **a segurança real está no código backend, não no Postgres** — uma chave anon vazada = vazamento total de projetos, clientes, cashback, cotações.

**Nota geral: 🚨 CRÍTICO** — RLS está mais como "RLS de fachada" do que como camada de defesa. `projects` e `profiles` são as únicas tabelas sensíveis com filtro real por `auth.uid()`. Todo o restante (project_items, project_clients, project_supplier_quotes, project_cashback_events, item_reviews, item_notes, cronogramas, contact_messages, chat_leads) é leitura/escrita totalmente aberta pra anon.

Recomendação: priorizar refactor de policies pra usar `auth.uid()` + join com `projects.user_id`, ou mover policies abertas pra `service_role` apenas.

---

## Tabela por tabela

Legenda: ✓ blindado · ⚠ atenção · 🚨 crítico

### 🚨 projects
- **RLS:** ON
- **SELECT:**
  - `Users read own projects` — `auth.uid()::text = user_id` ✓
  - `Admin reads all projects` — admin por email ✓
  - `Backend can select anonymous projects` — permite ler projetos com `user_id` em `('anonymous', NULL, '')` ⚠ (qualquer um, inclusive anon, lê projetos anônimos)
- **INSERT:** `Service can insert projects` — `with_check = true` (sem restrição) 🚨
- **UPDATE:** `Service can update projects` — `qual = true` (qualquer um atualiza qualquer projeto) 🚨
- **DELETE:** sem policy → bloqueado por default ✓
- **Risco:** 🚨 — INSERT/UPDATE liberados pra role `public` sem checagem de ownership. Anon pode criar projeto em nome de qualquer user_id, ou sobrescrever projetos alheios.

### 🚨 project_items
- **RLS:** ON
- **ALL:** `Backend manage project_items` — role `{anon}`, `qual=true`, `with_check=true`
- **Risco:** 🚨 — anon faz SELECT/INSERT/UPDATE/DELETE em qualquer linha. Sem filtro por projeto/owner.

### 🚨 project_clients
- **RLS:** ON
- **SELECT/INSERT/UPDATE/DELETE:** todas `qual=true`, role `{anon}`
- **Risco:** 🚨 — dados de cliente (nome, CPF/CNPJ) totalmente expostos a quem tem anon key. **Implicação LGPD séria.**

### 🚨 project_supplier_quotes
- **RLS:** ON
- **SELECT/INSERT/UPDATE/DELETE:** todas `qual=true`, role `{anon}`
- **Risco:** 🚨 — cotações de fornecedor (dado comercial sensível) abertas. Qualquer um lê preço que outros pagaram.

### 🚨 project_cashback_events
- **RLS:** ON
- **INSERT:** `qual=true`, role `{anon}` 🚨
- **SELECT:** `qual=true`, role `{anon}` 🚨
- **UPDATE/DELETE:** sem policy → bloqueado ✓
- **Risco:** 🚨 — qualquer anon pode **inserir eventos de cashback fraudulentos**. Risco financeiro direto (Pedro paga R$30 por planilha revisada que nunca foi revisada).

### ✓ profiles
- **RLS:** ON
- **SELECT:** `auth.uid()::text = user_id` + admin override ✓
- **INSERT:** `with_check (auth.uid()::text = user_id)` ✓
- **UPDATE:** `auth.uid()::text = user_id` ✓
- **DELETE:** sem policy → bloqueado ✓
- **Risco:** ✓ — blindado corretamente.

### 🚨 item_reviews
- **RLS:** ON
- **ALL:** `qual=true`, role `{anon}`
- **Risco:** 🚨 — revisões/auditoria humana de itens (dado sensível pro modelo de cashback) abertas.

### 🚨 item_notes
- **RLS:** ON
- **ALL:** `qual=true`, role `{anon}`
- **Risco:** 🚨 — notas de item abertas.

### 🚨 cronogramas
- **RLS:** ON
- **SELECT/INSERT/UPDATE:** `qual=true`, role `{public}` (ainda mais amplo que anon)
- **DELETE:** sem policy → bloqueado ✓
- **Risco:** 🚨 — qualquer cliente HTTP lê/escreve cronogramas de qualquer projeto. Pior: role `{public}` inclui anon, authenticated, service_role.

### ⚠ contact_messages
- **RLS:** ON
- **INSERT:** `qual=true`, roles `{anon,authenticated}` ✓ (formulário público de contato — esperado)
- **SELECT:** `qual=true`, roles `{anon,authenticated}` 🚨 (qualquer um lê todas as mensagens enviadas — emails, telefones, textos)
- **UPDATE:** `qual=true`, roles `{anon,authenticated}` 🚨
- **Risco:** ⚠⇒🚨 — INSERT aberto é correto pra formulário, mas SELECT/UPDATE abertos vazam contatos dos leads (LGPD).

### ⚠ chat_leads
- **RLS:** ON
- **INSERT:** `qual=true`, role `{anon}` ✓
- **SELECT:** `qual=true`, role `{anon}` 🚨 (leads do chat expostos)
- **UPDATE:** `qual=true`, role `{anon}` 🚨
- **DELETE:** bloqueado ✓
- **Risco:** ⚠⇒🚨 — mesmo padrão do contact_messages.

### ⚠ user_credits
- **RLS:** ON
- **ALL:** `qual=true`, role `{public}`
- **Risco:** 🚨 — créditos do usuário (saldo financeiro) totalmente abertos. Anon pode dar créditos pra si mesmo.

### ⚠ calibration
- **RLS:** ON
- **INSERT:** `qual=true` (anyone can insert) ⚠
- **SELECT/UPDATE/DELETE:** admin-only por email ✓
- **Risco:** ⚠ — INSERT aberto. Anon polui tabela de calibração com lixo. Não é crítico (admin lê e filtra) mas é vetor de DoS/poluição.

### ✓ beta_codes
- **RLS:** ON
- **SELECT:** `auth.role() = 'authenticated'` ✓
- **ALL:** admin por email ✓
- **Risco:** ✓ — anon não vê códigos beta.

### ✓ nps_responses
- **RLS:** ON
- **INSERT:** `qual=true`, roles `{anon,authenticated}` ✓ (esperado)
- **SELECT:** `auth.uid()::text = user_id` ✓
- **Risco:** ✓ — único caso onde INSERT aberto + SELECT por uid faz sentido.

### ⚠ agent_conversations
- **RLS:** ON
- **ALL:** `qual=true`, role `{public}`
- **Risco:** 🚨 — conversas de agente totalmente abertas. Pode conter dados sensíveis (CAD, valores).

### ⚠ density_benchmarks / density_ingest_raw / market_heuristics
- **RLS:** ON
- **ALL:** `qual=true`
- **Risco:** ⚠ — dados de calibração/benchmark privados expostos. Não é PII mas é vantagem competitiva.

### ⚠ catalog_capitulo / catalog_familia / catalog_grupo
- **RLS:** ON
- **ALL:** `qual=true`, role `{public}`
- **Risco:** ⚠ — taxonomia SINAPI é dado público (catálogo aberto), mas INSERT/UPDATE/DELETE liberados pra anon = anon corrompe catálogo. SELECT aberto é OK; o resto não.

### ⚠ sinapi_composicao / sinapi_insumos
- **RLS:** ON
- **ALL** ou SELECT/INSERT `qual=true`, role `{anon}`
- **Risco:** ⚠ — SINAPI é catálogo público (SELECT OK), mas anon pode inserir/sobrescrever. Mesmo problema do catalog.

### ⚠ tcpo_composicoes / tcpo_insumos
- **RLS:** ON
- **SELECT/INSERT/UPDATE/DELETE:** `qual=true`, role `{anon,authenticated}` ou `{anon}`
- **Risco:** ⚠ — TCPO é dado privado (Pini, copyright); SELECT por anon é problemático juridicamente. INSERT/UPDATE/DELETE abertos = corrupção de catálogo.

### ⚠ instagram_post_insights / instagram_scheduled_posts
- **RLS:** ON
- **ALL/INSERT/SELECT/UPDATE:** `qual=true`, roles `{anon,authenticated}`
- **Risco:** ⚠ — dados internos de marketing expostos. Não é crítico mas anon não devia ler.

### ✓ cleanup_log
- **RLS:** ON
- **INSERT:** `qual=true`, role `{anon}` — só insert, sem SELECT
- **Risco:** ⚠ — anon pode poluir log mas não lê. Aceitável.

---

## 🚨 Achados críticos

1. **`projects` INSERT/UPDATE sem checagem de ownership** — qualquer chave anon cria/sobrescreve projeto em nome de qualquer usuário.
2. **`project_items`, `project_clients`, `project_supplier_quotes`, `item_reviews`, `item_notes` totalmente abertos pra anon** — todos os dados de projeto (medições, clientes, cotações, revisões) podem ser lidos/alterados/deletados por qualquer requisição com anon key.
3. **`project_cashback_events` INSERT aberto pra anon** — vetor de **fraude financeira direta**. Anon pode inserir eventos `planilha_revisada` e sacar R$30/conta.
4. **`user_credits` ALL aberto pra `public`** — anon dá créditos pra si mesmo. Combinado com cashback, é caminho aberto pra cash drain.
5. **`contact_messages` e `chat_leads` SELECT aberto** — vazamento de PII dos leads (LGPD: nome, email, telefone, mensagem).
6. **`project_clients` SELECT aberto** — vazamento de PII pesado (nomes, CPF/CNPJ de clientes de obra). Risco LGPD alto.
7. **`cronogramas` policies com role `{public}`** — escopo amplo demais (inclui anon + authenticated + service_role no mesmo bolo).
8. **`agent_conversations` ALL aberto** — conversas com IA podem conter conteúdo sensível dos projetos.

---

## 🟡 Sugestões

- **Catálogos públicos (SINAPI, catalog_*)**: manter SELECT aberto, mas remover INSERT/UPDATE/DELETE do role anon (deixar só pra service_role).
- **TCPO**: avaliar se SELECT aberto pra anon é OK juridicamente (copyright Pini); se não, fechar pra `authenticated` ou só backend.
- **`density_benchmarks` / `market_heuristics`**: privar SELECT (vantagem competitiva do Pedro). Backend lê via service_role.
- **`calibration` INSERT**: ainda OK ser aberto (feedback público), mas adicionar rate-limit no backend pra evitar poluição.
- **`instagram_*`**: fechar pra service_role apenas.
- **`agent_conversations`**: restringir SELECT/UPDATE ao usuário dono da conversa via `auth.uid()`.

---

## 🟢 OK (blindadas corretamente)

- `profiles` — uid filter ✓
- `beta_codes` — admin/authenticated ✓
- `nps_responses` — uid filter ✓
- `cleanup_log` — só INSERT, sem SELECT ✓

---

## 🛠️ Top 5 fixes via `apply_migration`

> ⚠️ **Importante:** antes de aplicar, validar que o backend (Render) usa exclusivamente `service_role` (que ignora RLS). Caso contrário, fechar policies quebra o app. Recomendação: rodar em branch do Supabase primeiro.

### Fix 1 — Fechar `project_cashback_events` (risco financeiro direto)
```sql
DROP POLICY IF EXISTS cashback_events_insert ON public.project_cashback_events;
DROP POLICY IF EXISTS cashback_events_read ON public.project_cashback_events;

-- Só usuário lê seus próprios eventos via join com projects
CREATE POLICY cashback_events_select_own ON public.project_cashback_events
  FOR SELECT TO authenticated
  USING (EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = project_cashback_events.project_id
      AND p.user_id = auth.uid()::text
  ));

-- INSERT/UPDATE/DELETE: bloqueado pra anon/authenticated; só service_role.
-- (service_role bypassa RLS automaticamente, não precisa policy.)
```

### Fix 2 — Fechar `project_clients` (PII / LGPD)
```sql
DROP POLICY IF EXISTS project_clients_read ON public.project_clients;
DROP POLICY IF EXISTS project_clients_insert ON public.project_clients;
DROP POLICY IF EXISTS project_clients_update ON public.project_clients;
DROP POLICY IF EXISTS project_clients_delete ON public.project_clients;

CREATE POLICY project_clients_select_own ON public.project_clients
  FOR SELECT TO authenticated
  USING (EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = project_clients.project_id
      AND p.user_id = auth.uid()::text
  ));
-- INSERT/UPDATE/DELETE só via service_role no backend.
```

### Fix 3 — Restringir `projects` INSERT/UPDATE por ownership
```sql
DROP POLICY IF EXISTS "Service can insert projects" ON public.projects;
DROP POLICY IF EXISTS "Service can update projects" ON public.projects;

CREATE POLICY projects_insert_own ON public.projects
  FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid()::text);

CREATE POLICY projects_update_own ON public.projects
  FOR UPDATE TO authenticated
  USING (user_id = auth.uid()::text)
  WITH CHECK (user_id = auth.uid()::text);
-- Backend usa service_role (bypassa RLS) pra criar projetos anônimos / no fluxo de pagamento.
```

### Fix 4 — Fechar `contact_messages` e `chat_leads` SELECT (LGPD)
```sql
-- contact_messages: manter INSERT aberto (form público), fechar SELECT/UPDATE
DROP POLICY IF EXISTS contact_anon_select ON public.contact_messages;
DROP POLICY IF EXISTS contact_anon_update ON public.contact_messages;
-- Sem policy de SELECT/UPDATE → bloqueado pra anon. Backend lê via service_role.

-- chat_leads idem
DROP POLICY IF EXISTS chat_leads_read ON public.chat_leads;
DROP POLICY IF EXISTS chat_leads_update ON public.chat_leads;
```

### Fix 5 — Fechar `user_credits` (risco financeiro)
```sql
DROP POLICY IF EXISTS user_credits_all ON public.user_credits;

CREATE POLICY user_credits_select_own ON public.user_credits
  FOR SELECT TO authenticated
  USING (user_id = auth.uid()::text);
-- INSERT/UPDATE/DELETE: só service_role.
```

---

## Próximos passos sugeridos

1. **Confirmar com Pedro** que o backend Render usa `SUPABASE_SERVICE_ROLE_KEY` (não anon key) pra rotas autenticadas. Se sim, os fixes acima não quebram nada.
2. **Aplicar fixes em branch do Supabase** primeiro (`create_branch` MCP) — validar que dashboard, geração de planilha, cashback, contato continuam funcionando.
3. **Rotacionar a anon key** depois dos fixes, porque a chave antiga pode estar vazada em algum lugar (frontend antigo, screenshot, log).
4. **Auditar nas próximas semanas** as outras tabelas (`project_items`, `cronogramas`, `agent_conversations`, etc.) com o mesmo padrão.
5. **Considerar coluna `owner_user_id` redundante** em tabelas filhas (`project_items`, `cronogramas`, etc.) pra evitar JOIN em toda policy — melhora performance e simplifica RLS.

---

## 🟡 Status Fase 2 (2026-06-02) — BLOQUEADO

**Tentativa de aplicar `migrations_rls_planejadas.sql` em branch isolada:** abortada.

- **Erro:** `PaymentRequiredException — Branching is supported only on the Pro plan or above`.
- **Projeto:** `kqjabzwgbfuivzlcfvvu` está em plano Free; branching só no Pro ($25/mês).
- **Migrations aplicadas:** 0 de 38. Banco de produção intacto.
- **Smoke a-e:** não executado (rodar smoke direto em `main` sem branch isolada é destrutivo em produção).

### Caminhos pro Pedro decidir

1. **Upgrade Supabase Pro** ($25/mês) → criar branch → aplicar plano original com isolamento. Mais seguro.
2. **Smoke direto em produção com rollback pronto** → aplicar `migrations_rls_planejadas.sql` no projeto principal em janela de baixo tráfego (madrugada), com SQL de rollback pré-pronto pra reverter em ~30s se quebrar.
3. **Validar SQL offline + aplicar direto** → confirmar via curl que o backend Render usa `SUPABASE_SERVICE_ROLE_KEY` numa rota autenticada (tarefa #16 marcada como concluída — convém checar antes), aplicar no main em janela calma, smoke pós-aplicação.

**Status do arquivo `migrations_rls_planejadas.sql`:** pronto e idempotente (38 policies, DROP IF EXISTS + CREATE), aguardando decisão.
