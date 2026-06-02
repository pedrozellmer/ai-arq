-- =============================================================================
-- Migrations RLS planejadas — AI.arq Supabase
-- =============================================================================
-- Projeto:    kqjabzwgbfuivzlcfvvu (ai-arq, US-East-1)
-- Autor:      DBA (sessão 2026-06-02)
-- Base:       docs/auditoria_rls_2026-06-02.md
--
-- ⚠️ PRÉ-REQUISITO CRÍTICO (não pular):
--    O backend Render HOJE usa SUPABASE anon key (vide backend/calibrator.py,
--    backend/agent.py, backend/instagram_webhook.py). Anon key NÃO bypassa RLS.
--    Aplicar essas migrations SEM antes migrar o backend pra service_role key
--    VAI QUEBRAR criação de projetos, upload de planilha, cashback, agente IG.
--
--    Antes de aplicar este arquivo:
--      1. Adicionar SUPABASE_SERVICE_ROLE_KEY no env do Render
--      2. Trocar SUPABASE_KEY = anon → service_role nos arquivos do backend
--         (mantendo anon key só pro frontend)
--      3. Deploy do backend
--      4. Smoke test produção
--      5. SÓ ENTÃO aplicar este arquivo na branch Supabase
--
-- Padrões adotados:
--   - SELECT do dono via JOIN com public.projects (p.user_id = auth.uid()::text)
--   - INSERT/UPDATE/DELETE: sem policy pra anon/authenticated → só service_role
--     (service_role bypassa RLS automaticamente, não precisa policy)
--   - DROP POLICY IF EXISTS antes de CREATE pra ser idempotente
-- =============================================================================


-- =============================================================================
-- FIX 1 — project_cashback_events (risco financeiro direto)
-- =============================================================================
-- Antes: INSERT e SELECT abertos pra anon (qual=true). Qualquer anon podia
--        inserir eventos fraudulentos de cashback (R$30/planilha revisada).
-- Depois: SELECT só pelo dono do projeto via JOIN. Escrita só service_role.

DROP POLICY IF EXISTS cashback_events_insert ON public.project_cashback_events;
DROP POLICY IF EXISTS cashback_events_read   ON public.project_cashback_events;
DROP POLICY IF EXISTS cashback_events_select_own ON public.project_cashback_events;

CREATE POLICY cashback_events_select_own ON public.project_cashback_events
  FOR SELECT TO authenticated
  USING (EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = project_cashback_events.project_id
      AND p.user_id = auth.uid()::text
  ));

-- INSERT/UPDATE/DELETE: sem policy → bloqueado pra anon/authenticated.
-- Backend cria eventos via service_role (que ignora RLS).


-- =============================================================================
-- FIX 2 — project_clients (PII / LGPD)
-- =============================================================================
-- Antes: SELECT/INSERT/UPDATE/DELETE todos qual=true pra anon. Dados de
--        cliente final (nome, CPF/CNPJ, telefone, email) expostos.
-- Depois: só dono lê via JOIN. Escrita só service_role.

DROP POLICY IF EXISTS project_clients_read   ON public.project_clients;
DROP POLICY IF EXISTS project_clients_insert ON public.project_clients;
DROP POLICY IF EXISTS project_clients_update ON public.project_clients;
DROP POLICY IF EXISTS project_clients_delete ON public.project_clients;
DROP POLICY IF EXISTS project_clients_select_own ON public.project_clients;

CREATE POLICY project_clients_select_own ON public.project_clients
  FOR SELECT TO authenticated
  USING (EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = project_clients.project_id
      AND p.user_id = auth.uid()::text
  ));


-- =============================================================================
-- FIX 3 — projects INSERT/UPDATE por ownership
-- =============================================================================
-- Antes: "Service can insert projects" (with_check=true) e
--        "Service can update projects" (qual=true) — qualquer um cria/sobrescreve
--        projeto em nome de qualquer user_id.
-- Depois: usuário só cria/atualiza projeto onde user_id = seu próprio uid.
--         Backend cria projetos anônimos via service_role.

DROP POLICY IF EXISTS "Service can insert projects" ON public.projects;
DROP POLICY IF EXISTS "Service can update projects" ON public.projects;
DROP POLICY IF EXISTS projects_insert_own ON public.projects;
DROP POLICY IF EXISTS projects_update_own ON public.projects;

CREATE POLICY projects_insert_own ON public.projects
  FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid()::text);

CREATE POLICY projects_update_own ON public.projects
  FOR UPDATE TO authenticated
  USING (user_id = auth.uid()::text)
  WITH CHECK (user_id = auth.uid()::text);

-- SELECT mantém policies existentes:
--   "Users read own projects" (auth.uid()::text = user_id)
--   "Admin reads all projects" (admin por email)
--   "Backend can select anonymous projects" (user_id IN ('anonymous', NULL, ''))
-- DELETE permanece sem policy → bloqueado (só service_role).


-- =============================================================================
-- FIX 4 — contact_messages e chat_leads (PII / LGPD)
-- =============================================================================
-- Antes: SELECT/UPDATE abertos pra anon. Qualquer um listava emails,
--        telefones, mensagens de todos os leads.
-- Depois: mantém INSERT aberto (formulário público é legítimo), remove
--         SELECT/UPDATE. Admin lê via service_role no backend.

-- contact_messages
DROP POLICY IF EXISTS contact_anon_select ON public.contact_messages;
DROP POLICY IF EXISTS contact_anon_update ON public.contact_messages;
-- INSERT já está OK (formulário público) — mantém

-- chat_leads
DROP POLICY IF EXISTS chat_leads_read   ON public.chat_leads;
DROP POLICY IF EXISTS chat_leads_update ON public.chat_leads;
-- INSERT (chat widget público) — mantém


-- =============================================================================
-- FIX 5 — user_credits (risco financeiro)
-- =============================================================================
-- Antes: ALL qual=true pra role public. Anon podia dar créditos pra si mesmo.
-- Depois: SELECT só do próprio user_id. Escrita só service_role.

DROP POLICY IF EXISTS user_credits_all ON public.user_credits;
DROP POLICY IF EXISTS user_credits_select_own ON public.user_credits;

CREATE POLICY user_credits_select_own ON public.user_credits
  FOR SELECT TO authenticated
  USING (user_id = auth.uid()::text);


-- =============================================================================
-- EXTENSÃO — project_items (dados de medição por projeto)
-- =============================================================================
-- Antes: ALL qual=true pra anon. Qualquer um SELECT/INSERT/UPDATE/DELETE em
--        itens de qualquer projeto.
-- Depois: dono do projeto faz tudo via JOIN com projects.

DROP POLICY IF EXISTS "Backend manage project_items" ON public.project_items;
DROP POLICY IF EXISTS project_items_select_own ON public.project_items;
DROP POLICY IF EXISTS project_items_insert_own ON public.project_items;
DROP POLICY IF EXISTS project_items_update_own ON public.project_items;
DROP POLICY IF EXISTS project_items_delete_own ON public.project_items;

CREATE POLICY project_items_select_own ON public.project_items
  FOR SELECT TO authenticated
  USING (EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = project_items.project_id
      AND p.user_id = auth.uid()::text
  ));

CREATE POLICY project_items_insert_own ON public.project_items
  FOR INSERT TO authenticated
  WITH CHECK (EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = project_items.project_id
      AND p.user_id = auth.uid()::text
  ));

CREATE POLICY project_items_update_own ON public.project_items
  FOR UPDATE TO authenticated
  USING (EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = project_items.project_id
      AND p.user_id = auth.uid()::text
  ))
  WITH CHECK (EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = project_items.project_id
      AND p.user_id = auth.uid()::text
  ));

CREATE POLICY project_items_delete_own ON public.project_items
  FOR DELETE TO authenticated
  USING (EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = project_items.project_id
      AND p.user_id = auth.uid()::text
  ));


-- =============================================================================
-- EXTENSÃO — project_supplier_quotes (cotações de fornecedor)
-- =============================================================================
-- Antes: ALL aberto pra anon. Cotações comerciais sensíveis (preço/condições)
--        de todos os usuários acessíveis.
-- Depois: só dono via JOIN.

DROP POLICY IF EXISTS project_supplier_quotes_read   ON public.project_supplier_quotes;
DROP POLICY IF EXISTS project_supplier_quotes_insert ON public.project_supplier_quotes;
DROP POLICY IF EXISTS project_supplier_quotes_update ON public.project_supplier_quotes;
DROP POLICY IF EXISTS project_supplier_quotes_delete ON public.project_supplier_quotes;
DROP POLICY IF EXISTS project_supplier_quotes_select_own ON public.project_supplier_quotes;
DROP POLICY IF EXISTS project_supplier_quotes_insert_own ON public.project_supplier_quotes;
DROP POLICY IF EXISTS project_supplier_quotes_update_own ON public.project_supplier_quotes;
DROP POLICY IF EXISTS project_supplier_quotes_delete_own ON public.project_supplier_quotes;

CREATE POLICY project_supplier_quotes_select_own ON public.project_supplier_quotes
  FOR SELECT TO authenticated
  USING (EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = project_supplier_quotes.project_id
      AND p.user_id = auth.uid()::text
  ));

CREATE POLICY project_supplier_quotes_insert_own ON public.project_supplier_quotes
  FOR INSERT TO authenticated
  WITH CHECK (EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = project_supplier_quotes.project_id
      AND p.user_id = auth.uid()::text
  ));

CREATE POLICY project_supplier_quotes_update_own ON public.project_supplier_quotes
  FOR UPDATE TO authenticated
  USING (EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = project_supplier_quotes.project_id
      AND p.user_id = auth.uid()::text
  ))
  WITH CHECK (EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = project_supplier_quotes.project_id
      AND p.user_id = auth.uid()::text
  ));

CREATE POLICY project_supplier_quotes_delete_own ON public.project_supplier_quotes
  FOR DELETE TO authenticated
  USING (EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = project_supplier_quotes.project_id
      AND p.user_id = auth.uid()::text
  ));


-- =============================================================================
-- EXTENSÃO — item_reviews (revisões humanas alimentam IA)
-- =============================================================================
-- Antes: ALL qual=true pra anon. Revisões usadas pelo modelo de cashback
--        acessíveis e mutáveis por anon.
-- Depois: só dono via JOIN.

DROP POLICY IF EXISTS item_reviews_read   ON public.item_reviews;
DROP POLICY IF EXISTS item_reviews_insert ON public.item_reviews;
DROP POLICY IF EXISTS item_reviews_update ON public.item_reviews;
DROP POLICY IF EXISTS item_reviews_delete ON public.item_reviews;
DROP POLICY IF EXISTS item_reviews_select_own ON public.item_reviews;
DROP POLICY IF EXISTS item_reviews_insert_own ON public.item_reviews;
DROP POLICY IF EXISTS item_reviews_update_own ON public.item_reviews;
DROP POLICY IF EXISTS item_reviews_delete_own ON public.item_reviews;

CREATE POLICY item_reviews_select_own ON public.item_reviews
  FOR SELECT TO authenticated
  USING (EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = item_reviews.project_id
      AND p.user_id = auth.uid()::text
  ));

CREATE POLICY item_reviews_insert_own ON public.item_reviews
  FOR INSERT TO authenticated
  WITH CHECK (EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = item_reviews.project_id
      AND p.user_id = auth.uid()::text
  ));

CREATE POLICY item_reviews_update_own ON public.item_reviews
  FOR UPDATE TO authenticated
  USING (EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = item_reviews.project_id
      AND p.user_id = auth.uid()::text
  ))
  WITH CHECK (EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = item_reviews.project_id
      AND p.user_id = auth.uid()::text
  ));

CREATE POLICY item_reviews_delete_own ON public.item_reviews
  FOR DELETE TO authenticated
  USING (EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = item_reviews.project_id
      AND p.user_id = auth.uid()::text
  ));


-- =============================================================================
-- EXTENSÃO — item_notes (notas em itens)
-- =============================================================================
-- Antes: ALL qual=true pra anon. Notas de qualquer item acessíveis.
-- Depois: só dono via JOIN.

DROP POLICY IF EXISTS item_notes_read   ON public.item_notes;
DROP POLICY IF EXISTS item_notes_insert ON public.item_notes;
DROP POLICY IF EXISTS item_notes_update ON public.item_notes;
DROP POLICY IF EXISTS item_notes_delete ON public.item_notes;
DROP POLICY IF EXISTS item_notes_select_own ON public.item_notes;
DROP POLICY IF EXISTS item_notes_insert_own ON public.item_notes;
DROP POLICY IF EXISTS item_notes_update_own ON public.item_notes;
DROP POLICY IF EXISTS item_notes_delete_own ON public.item_notes;

CREATE POLICY item_notes_select_own ON public.item_notes
  FOR SELECT TO authenticated
  USING (EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = item_notes.project_id
      AND p.user_id = auth.uid()::text
  ));

CREATE POLICY item_notes_insert_own ON public.item_notes
  FOR INSERT TO authenticated
  WITH CHECK (EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = item_notes.project_id
      AND p.user_id = auth.uid()::text
  ));

CREATE POLICY item_notes_update_own ON public.item_notes
  FOR UPDATE TO authenticated
  USING (EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = item_notes.project_id
      AND p.user_id = auth.uid()::text
  ))
  WITH CHECK (EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = item_notes.project_id
      AND p.user_id = auth.uid()::text
  ));

CREATE POLICY item_notes_delete_own ON public.item_notes
  FOR DELETE TO authenticated
  USING (EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = item_notes.project_id
      AND p.user_id = auth.uid()::text
  ));


-- =============================================================================
-- EXTENSÃO — cronogramas (Fase 2, cronograma físico-financeiro)
-- =============================================================================
-- Antes: SELECT/INSERT/UPDATE com role public (mais amplo que anon — inclui
--        anon + authenticated + service_role). qual=true em todas.
-- Depois: dono via JOIN com projects.

DROP POLICY IF EXISTS cronogramas_select ON public.cronogramas;
DROP POLICY IF EXISTS cronogramas_insert ON public.cronogramas;
DROP POLICY IF EXISTS cronogramas_update ON public.cronogramas;
DROP POLICY IF EXISTS cronogramas_delete ON public.cronogramas;
DROP POLICY IF EXISTS cronogramas_read   ON public.cronogramas;
DROP POLICY IF EXISTS cronogramas_select_own ON public.cronogramas;
DROP POLICY IF EXISTS cronogramas_insert_own ON public.cronogramas;
DROP POLICY IF EXISTS cronogramas_update_own ON public.cronogramas;
DROP POLICY IF EXISTS cronogramas_delete_own ON public.cronogramas;

CREATE POLICY cronogramas_select_own ON public.cronogramas
  FOR SELECT TO authenticated
  USING (EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = cronogramas.project_id
      AND p.user_id = auth.uid()::text
  ));

CREATE POLICY cronogramas_insert_own ON public.cronogramas
  FOR INSERT TO authenticated
  WITH CHECK (EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = cronogramas.project_id
      AND p.user_id = auth.uid()::text
  ));

CREATE POLICY cronogramas_update_own ON public.cronogramas
  FOR UPDATE TO authenticated
  USING (EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = cronogramas.project_id
      AND p.user_id = auth.uid()::text
  ))
  WITH CHECK (EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = cronogramas.project_id
      AND p.user_id = auth.uid()::text
  ));

CREATE POLICY cronogramas_delete_own ON public.cronogramas
  FOR DELETE TO authenticated
  USING (EXISTS (
    SELECT 1 FROM public.projects p
    WHERE p.id = cronogramas.project_id
      AND p.user_id = auth.uid()::text
  ));


-- =============================================================================
-- EXTENSÃO — agent_conversations (conversas com IA, podem ter CAD/valores)
-- =============================================================================
-- Antes: ALL qual=true pra role public. Qualquer um lia conversas alheias.
-- Depois: se a tabela tem user_id, filtra por uid; se tem project_id, JOIN.
--         Cobrimos os dois caminhos pra ser defensivo.

DROP POLICY IF EXISTS agent_conversations_all     ON public.agent_conversations;
DROP POLICY IF EXISTS agent_conversations_read    ON public.agent_conversations;
DROP POLICY IF EXISTS agent_conversations_insert  ON public.agent_conversations;
DROP POLICY IF EXISTS agent_conversations_update  ON public.agent_conversations;
DROP POLICY IF EXISTS agent_conversations_delete  ON public.agent_conversations;
DROP POLICY IF EXISTS agent_conversations_select_own ON public.agent_conversations;
DROP POLICY IF EXISTS agent_conversations_insert_own ON public.agent_conversations;
DROP POLICY IF EXISTS agent_conversations_update_own ON public.agent_conversations;

CREATE POLICY agent_conversations_select_own ON public.agent_conversations
  FOR SELECT TO authenticated
  USING (
    user_id = auth.uid()::text
    OR EXISTS (
      SELECT 1 FROM public.projects p
      WHERE p.id = agent_conversations.project_id
        AND p.user_id = auth.uid()::text
    )
  );

CREATE POLICY agent_conversations_insert_own ON public.agent_conversations
  FOR INSERT TO authenticated
  WITH CHECK (
    user_id = auth.uid()::text
    OR EXISTS (
      SELECT 1 FROM public.projects p
      WHERE p.id = agent_conversations.project_id
        AND p.user_id = auth.uid()::text
    )
  );

CREATE POLICY agent_conversations_update_own ON public.agent_conversations
  FOR UPDATE TO authenticated
  USING (
    user_id = auth.uid()::text
    OR EXISTS (
      SELECT 1 FROM public.projects p
      WHERE p.id = agent_conversations.project_id
        AND p.user_id = auth.uid()::text
    )
  )
  WITH CHECK (
    user_id = auth.uid()::text
    OR EXISTS (
      SELECT 1 FROM public.projects p
      WHERE p.id = agent_conversations.project_id
        AND p.user_id = auth.uid()::text
    )
  );

-- DELETE só service_role.


-- =============================================================================
-- CATÁLOGOS PÚBLICOS — SELECT aberto, escrita só service_role
-- =============================================================================
-- catalog_capitulo / catalog_familia / catalog_grupo / sinapi_*: SINAPI é
-- catálogo aberto (gov), SELECT pode ser anon. Mas anon corrompendo o catálogo
-- não pode acontecer → remove INSERT/UPDATE/DELETE.


-- catalog_capitulo
DROP POLICY IF EXISTS catalog_capitulo_all    ON public.catalog_capitulo;
DROP POLICY IF EXISTS catalog_capitulo_read   ON public.catalog_capitulo;
DROP POLICY IF EXISTS catalog_capitulo_insert ON public.catalog_capitulo;
DROP POLICY IF EXISTS catalog_capitulo_update ON public.catalog_capitulo;
DROP POLICY IF EXISTS catalog_capitulo_delete ON public.catalog_capitulo;
DROP POLICY IF EXISTS catalog_capitulo_select_public ON public.catalog_capitulo;

CREATE POLICY catalog_capitulo_select_public ON public.catalog_capitulo
  FOR SELECT TO anon, authenticated
  USING (true);
-- INSERT/UPDATE/DELETE: sem policy → só service_role.


-- catalog_familia
DROP POLICY IF EXISTS catalog_familia_all    ON public.catalog_familia;
DROP POLICY IF EXISTS catalog_familia_read   ON public.catalog_familia;
DROP POLICY IF EXISTS catalog_familia_insert ON public.catalog_familia;
DROP POLICY IF EXISTS catalog_familia_update ON public.catalog_familia;
DROP POLICY IF EXISTS catalog_familia_delete ON public.catalog_familia;
DROP POLICY IF EXISTS catalog_familia_select_public ON public.catalog_familia;

CREATE POLICY catalog_familia_select_public ON public.catalog_familia
  FOR SELECT TO anon, authenticated
  USING (true);


-- catalog_grupo
DROP POLICY IF EXISTS catalog_grupo_all    ON public.catalog_grupo;
DROP POLICY IF EXISTS catalog_grupo_read   ON public.catalog_grupo;
DROP POLICY IF EXISTS catalog_grupo_insert ON public.catalog_grupo;
DROP POLICY IF EXISTS catalog_grupo_update ON public.catalog_grupo;
DROP POLICY IF EXISTS catalog_grupo_delete ON public.catalog_grupo;
DROP POLICY IF EXISTS catalog_grupo_select_public ON public.catalog_grupo;

CREATE POLICY catalog_grupo_select_public ON public.catalog_grupo
  FOR SELECT TO anon, authenticated
  USING (true);


-- sinapi_composicao
DROP POLICY IF EXISTS sinapi_composicao_all    ON public.sinapi_composicao;
DROP POLICY IF EXISTS sinapi_composicao_read   ON public.sinapi_composicao;
DROP POLICY IF EXISTS sinapi_composicao_insert ON public.sinapi_composicao;
DROP POLICY IF EXISTS sinapi_composicao_update ON public.sinapi_composicao;
DROP POLICY IF EXISTS sinapi_composicao_delete ON public.sinapi_composicao;
DROP POLICY IF EXISTS sinapi_composicao_select_public ON public.sinapi_composicao;

CREATE POLICY sinapi_composicao_select_public ON public.sinapi_composicao
  FOR SELECT TO anon, authenticated
  USING (true);


-- sinapi_insumos
DROP POLICY IF EXISTS sinapi_insumos_all    ON public.sinapi_insumos;
DROP POLICY IF EXISTS sinapi_insumos_read   ON public.sinapi_insumos;
DROP POLICY IF EXISTS sinapi_insumos_insert ON public.sinapi_insumos;
DROP POLICY IF EXISTS sinapi_insumos_update ON public.sinapi_insumos;
DROP POLICY IF EXISTS sinapi_insumos_delete ON public.sinapi_insumos;
DROP POLICY IF EXISTS sinapi_insumos_select_public ON public.sinapi_insumos;

CREATE POLICY sinapi_insumos_select_public ON public.sinapi_insumos
  FOR SELECT TO anon, authenticated
  USING (true);


-- =============================================================================
-- TCPO — copyright Pini, SELECT só pra authenticated
-- =============================================================================
-- TCPO é base privada (Editora Pini, com copyright). Não pode ficar exposto
-- pra anon. Authenticated lê (uso interno do usuário pagante), escrita só
-- service_role.

-- tcpo_composicoes
DROP POLICY IF EXISTS tcpo_composicoes_all    ON public.tcpo_composicoes;
DROP POLICY IF EXISTS tcpo_composicoes_read   ON public.tcpo_composicoes;
DROP POLICY IF EXISTS tcpo_composicoes_insert ON public.tcpo_composicoes;
DROP POLICY IF EXISTS tcpo_composicoes_update ON public.tcpo_composicoes;
DROP POLICY IF EXISTS tcpo_composicoes_delete ON public.tcpo_composicoes;
DROP POLICY IF EXISTS tcpo_composicoes_select_auth ON public.tcpo_composicoes;

CREATE POLICY tcpo_composicoes_select_auth ON public.tcpo_composicoes
  FOR SELECT TO authenticated
  USING (true);


-- tcpo_insumos
DROP POLICY IF EXISTS tcpo_insumos_all    ON public.tcpo_insumos;
DROP POLICY IF EXISTS tcpo_insumos_read   ON public.tcpo_insumos;
DROP POLICY IF EXISTS tcpo_insumos_insert ON public.tcpo_insumos;
DROP POLICY IF EXISTS tcpo_insumos_update ON public.tcpo_insumos;
DROP POLICY IF EXISTS tcpo_insumos_delete ON public.tcpo_insumos;
DROP POLICY IF EXISTS tcpo_insumos_select_auth ON public.tcpo_insumos;

CREATE POLICY tcpo_insumos_select_auth ON public.tcpo_insumos
  FOR SELECT TO authenticated
  USING (true);


-- =============================================================================
-- VANTAGEM COMPETITIVA — density_benchmarks / market_heuristics
-- =============================================================================
-- Calibração interna do AI.arq, NÃO é PII mas é diferencial. Anon/authenticated
-- não precisam ver — backend lê via service_role. Sem policy → bloqueado.

-- density_benchmarks
DROP POLICY IF EXISTS density_benchmarks_all    ON public.density_benchmarks;
DROP POLICY IF EXISTS density_benchmarks_read   ON public.density_benchmarks;
DROP POLICY IF EXISTS density_benchmarks_insert ON public.density_benchmarks;
DROP POLICY IF EXISTS density_benchmarks_update ON public.density_benchmarks;
DROP POLICY IF EXISTS density_benchmarks_delete ON public.density_benchmarks;
-- Sem CREATE POLICY → tudo bloqueado pra anon/authenticated. service_role bypassa RLS.


-- market_heuristics
DROP POLICY IF EXISTS market_heuristics_all    ON public.market_heuristics;
DROP POLICY IF EXISTS market_heuristics_read   ON public.market_heuristics;
DROP POLICY IF EXISTS market_heuristics_insert ON public.market_heuristics;
DROP POLICY IF EXISTS market_heuristics_update ON public.market_heuristics;
DROP POLICY IF EXISTS market_heuristics_delete ON public.market_heuristics;
-- Sem CREATE POLICY → tudo bloqueado pra anon/authenticated. service_role bypassa RLS.


-- =============================================================================
-- INSTAGRAM — operacional interno, só service_role
-- =============================================================================

-- instagram_post_insights
DROP POLICY IF EXISTS instagram_post_insights_all    ON public.instagram_post_insights;
DROP POLICY IF EXISTS instagram_post_insights_read   ON public.instagram_post_insights;
DROP POLICY IF EXISTS instagram_post_insights_insert ON public.instagram_post_insights;
DROP POLICY IF EXISTS instagram_post_insights_update ON public.instagram_post_insights;
DROP POLICY IF EXISTS instagram_post_insights_delete ON public.instagram_post_insights;
-- Sem policy → só service_role.


-- instagram_scheduled_posts
DROP POLICY IF EXISTS instagram_scheduled_posts_all    ON public.instagram_scheduled_posts;
DROP POLICY IF EXISTS instagram_scheduled_posts_read   ON public.instagram_scheduled_posts;
DROP POLICY IF EXISTS instagram_scheduled_posts_insert ON public.instagram_scheduled_posts;
DROP POLICY IF EXISTS instagram_scheduled_posts_update ON public.instagram_scheduled_posts;
DROP POLICY IF EXISTS instagram_scheduled_posts_delete ON public.instagram_scheduled_posts;
-- Sem policy → só service_role.


-- =============================================================================
-- FIM DAS MIGRATIONS
-- =============================================================================


-- =============================================================================
-- ## Como aplicar (em branch Supabase primeiro)
-- =============================================================================
--
-- ⚠️ ORDEM IMPORTANTÍSSIMA — não pular passos.
--
-- ### Passo 0 — Pré-requisito: migrar backend pra service_role
--
-- HOJE o backend usa SUPABASE anon key (em backend/calibrator.py linha 20,
-- backend/agent.py linha 25, backend/instagram_webhook.py linhas 525/540/558).
-- Anon key NÃO bypassa RLS. Se aplicar este SQL antes de migrar o backend,
-- todas as rotas autenticadas vão começar a falhar.
--
-- O que precisa rolar:
--   1. No Render → Environment, confirmar/adicionar var
--      SUPABASE_SERVICE_ROLE_KEY (pegar no Supabase Dashboard → Settings → API).
--   2. Editar os 3 arquivos do backend pra ler a service_role key:
--        SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or <fallback anon>
--      Deixar a anon key como fallback temporário só pra não derrubar produção
--      durante a transição. Remover o fallback DEPOIS de tudo testado.
--   3. Commit + push (Render faz deploy automático).
--   4. Smoke test em produção:
--      - Listar projetos (admin + usuário comum)
--      - Criar projeto novo
--      - Baixar planilha
--      - Ver cashback no dashboard
--      - Disparar tick do scheduler IG (/api/instagram/scheduler/tick)
--
-- ### Passo 1 — Criar branch Supabase
--
-- Via MCP:
--   mcp__dbd6b42c-...__create_branch(name="rls-hardening-2026-06-02")
--
-- Anota o branch_id retornado. Branches Supabase têm Postgres separado, então
-- você pode testar as policies sem afetar produção.
--
-- ### Passo 2 — Aplicar migrations na branch
--
-- Via MCP, com project_id=<branch_id>:
--   mcp__dbd6b42c-...__apply_migration(
--     project_id=<branch_id>,
--     name="rls_hardening_2026_06_02",
--     query=<conteúdo deste arquivo, exceto o cabeçalho de comentário>
--   )
--
-- ### Passo 3 — Smoke test na branch
--
-- Apontar uma cópia local do frontend pro URL/anon-key da branch e testar:
--   - [ ] Cadastro novo → magic link
--   - [ ] Login → dashboard mostra projetos só do user
--   - [ ] Outro user logado NÃO vê projetos do primeiro (testar via SELECT
--         direto com 2 anon keys de users diferentes via SQL)
--   - [ ] Backend (apontando pra branch) cria projeto → aparece pro dono
--   - [ ] Upload de CAD → planilha gera → download funciona
--   - [ ] Cashback aparece no dashboard depois de evento gerado pelo backend
--   - [ ] Anon na browser console NÃO consegue:
--           - INSERT em project_cashback_events
--           - SELECT em project_clients de outro user
--           - SELECT em user_credits de outro user
--           - INSERT/UPDATE em projects com user_id alheio
--   - [ ] Admin (Pedro, zarelalopes@gmail.com) continua vendo "Admin reads all"
--   - [ ] Catálogo SINAPI continua sendo lido pelo frontend (autocomplete)
--   - [ ] TCPO só carrega quando user tá autenticado
--
-- ### Passo 4 — Merge branch → main
--
-- Se tudo ok no smoke test:
--   mcp__dbd6b42c-...__merge_branch(branch_id=<branch_id>)
--
-- Migrations vão ser aplicadas no projeto principal (kqjabzwgbfuivzlcfvvu).
--
-- ### Passo 5 — Rotacionar anon key
--
-- Anon key antiga ficou exposta em screenshots/históricos. Trocar:
--   Supabase Dashboard → Settings → API → "Reset anon key"
--
-- ### Passo 6 — Atualizar SUPABASE_KEY no frontend
--
-- Boa notícia: o anon key fica centralizado em aiarq-utils.js (só 1 lugar).
-- Editar:
--   - C:\Users\admin\Desktop\arq\projeto_arq\aiarq-utils.js  (variável SUPABASE_KEY ou similar)
--
-- Conferir se há outras ocorrências:
--   grep -r "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ" projeto_arq/ --include="*.html"
--   grep -r "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ" projeto_arq/ --include="*.js"
--
-- Atualizar todas se encontrar outras.
--
-- ### Passo 7 — Commit + push site
--
-- git add aiarq-utils.js (e outros se tiver)
-- git commit -m "chore(security): rotaciona anon key Supabase pós RLS hardening"
-- git push origin main
--
-- GitHub Pages publica em ~2min. Hard refresh no browser pra invalidar cache.
--
-- ### Passo 8 — Verificação final
--
-- - [ ] Site carrega login normalmente com anon key nova
-- - [ ] Backend continua operando com service_role key
-- - [ ] Smoke test E2E completo em produção (mesmos itens do Passo 3)
-- - [ ] Anon key antiga retorna 401 (testar com curl)
--
-- ### Rollback (se algo quebrar)
--
-- Cada DROP/CREATE POLICY é reversível recriando a policy original. Como temos
-- a auditoria de origem (docs/auditoria_rls_2026-06-02.md), dá pra recriar
-- todas as policies abertas em emergência. Mas a opção real é manter a branch
-- Supabase ativa por 24h pós-merge pra comparação rápida.
--
-- =============================================================================
