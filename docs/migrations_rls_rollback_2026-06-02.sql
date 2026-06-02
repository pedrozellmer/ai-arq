-- =============================================================================
-- ROLLBACK das policies fechadas em migrations_rls_planejadas.sql
-- =============================================================================
-- Data:       2026-06-02
-- Projeto:    kqjabzwgbfuivzlcfvvu (ai-arq, Supabase)
-- Snapshot:   61 policies de public.* coletadas de pg_policies ANTES da
--             aplicação de docs/migrations_rls_planejadas.sql.
--
-- Propósito:
--   Reverter em <60s o estado das policies caso migrations_rls_planejadas.sql
--   quebre algo em produção. Esse arquivo:
--     1. DROP POLICY IF EXISTS pra TODA policy nova criada pela migration
--     2. CREATE POLICY recriando o snapshot do estado anterior
--
-- Como rodar:
--   Cole TODO o conteúdo abaixo no SQL Editor do Supabase Dashboard
--   (https://supabase.com/dashboard/project/kqjabzwgbfuivzlcfvvu/sql/new)
--   e clique em "Run". Cada bloco é idempotente.
--
-- ⚠️ Aviso:
--   Esse rollback reabre o banco pro estado vulnerável (várias policies anon).
--   Use SÓ se a aplicação quebrou e precisa de reversão imediata. Depois,
--   redesenhar a migration antes de reaplicar.
-- =============================================================================


-- =============================================================================
-- PARTE 1 — DROP POLICY IF EXISTS pra cada policy NOVA criada pela migration
-- =============================================================================
-- Nomes extraídos de docs/migrations_rls_planejadas.sql (CREATE POLICY *_own /
-- *_public / *_auth). DROP idempotente — se policy não existe, é no-op.

DROP POLICY IF EXISTS cashback_events_select_own           ON public.project_cashback_events;
DROP POLICY IF EXISTS project_clients_select_own           ON public.project_clients;
DROP POLICY IF EXISTS projects_insert_own                  ON public.projects;
DROP POLICY IF EXISTS projects_update_own                  ON public.projects;
DROP POLICY IF EXISTS user_credits_select_own              ON public.user_credits;
DROP POLICY IF EXISTS project_items_select_own             ON public.project_items;
DROP POLICY IF EXISTS project_items_insert_own             ON public.project_items;
DROP POLICY IF EXISTS project_items_update_own             ON public.project_items;
DROP POLICY IF EXISTS project_items_delete_own             ON public.project_items;
DROP POLICY IF EXISTS project_supplier_quotes_select_own   ON public.project_supplier_quotes;
DROP POLICY IF EXISTS project_supplier_quotes_insert_own   ON public.project_supplier_quotes;
DROP POLICY IF EXISTS project_supplier_quotes_update_own   ON public.project_supplier_quotes;
DROP POLICY IF EXISTS project_supplier_quotes_delete_own   ON public.project_supplier_quotes;
DROP POLICY IF EXISTS item_reviews_select_own              ON public.item_reviews;
DROP POLICY IF EXISTS item_reviews_insert_own              ON public.item_reviews;
DROP POLICY IF EXISTS item_reviews_update_own              ON public.item_reviews;
DROP POLICY IF EXISTS item_reviews_delete_own              ON public.item_reviews;
DROP POLICY IF EXISTS item_notes_select_own                ON public.item_notes;
DROP POLICY IF EXISTS item_notes_insert_own                ON public.item_notes;
DROP POLICY IF EXISTS item_notes_update_own                ON public.item_notes;
DROP POLICY IF EXISTS item_notes_delete_own                ON public.item_notes;
DROP POLICY IF EXISTS cronogramas_select_own               ON public.cronogramas;
DROP POLICY IF EXISTS cronogramas_insert_own               ON public.cronogramas;
DROP POLICY IF EXISTS cronogramas_update_own               ON public.cronogramas;
DROP POLICY IF EXISTS cronogramas_delete_own               ON public.cronogramas;
DROP POLICY IF EXISTS agent_conversations_select_own       ON public.agent_conversations;
DROP POLICY IF EXISTS agent_conversations_insert_own       ON public.agent_conversations;
DROP POLICY IF EXISTS agent_conversations_update_own       ON public.agent_conversations;
DROP POLICY IF EXISTS catalog_capitulo_select_public       ON public.catalog_capitulo;
DROP POLICY IF EXISTS catalog_familia_select_public        ON public.catalog_familia;
DROP POLICY IF EXISTS catalog_grupo_select_public          ON public.catalog_grupo;
DROP POLICY IF EXISTS sinapi_composicao_select_public      ON public.sinapi_composicao;
DROP POLICY IF EXISTS sinapi_insumos_select_public         ON public.sinapi_insumos;
DROP POLICY IF EXISTS tcpo_composicoes_select_auth         ON public.tcpo_composicoes;
DROP POLICY IF EXISTS tcpo_insumos_select_auth             ON public.tcpo_insumos;

-- A migration também faz DROP de várias policies antigas (cashback_events_insert,
-- cashback_events_read, project_clients_*, Service can insert/update projects,
-- user_credits_all, Backend manage *, *_all, *_read, *_insert, *_update,
-- *_delete, contact_anon_select/update, chat_leads_read/update, supplier_*).
-- A PARTE 2 abaixo recria todas elas com os mesmos params do snapshot.


-- =============================================================================
-- PARTE 2 — CREATE POLICY recriando o estado anterior (61 policies)
-- =============================================================================
-- Ordem: por tabela, por cmd, por nome (igual o ORDER BY do snapshot).
-- Cada CREATE POLICY foi gerado a partir de pg_policies com seus params
-- originais (roles, cmd, USING, WITH CHECK).
-- =============================================================================


-- ---------- agent_conversations ----------
CREATE POLICY agent_conv_all ON public.agent_conversations
  FOR ALL TO public
  USING (true)
  WITH CHECK (true);


-- ---------- beta_codes ----------
CREATE POLICY "Admin manages beta_codes" ON public.beta_codes
  FOR ALL TO public
  USING ((auth.jwt() ->> 'email'::text) = 'zarelalopes@gmail.com'::text);

CREATE POLICY "Authenticated read beta_codes" ON public.beta_codes
  FOR SELECT TO public
  USING (auth.role() = 'authenticated'::text);


-- ---------- calibration ----------
CREATE POLICY "Admin deletes calibration" ON public.calibration
  FOR DELETE TO public
  USING ((auth.jwt() ->> 'email'::text) = 'zarelalopes@gmail.com'::text);

CREATE POLICY "Anyone can insert calibration" ON public.calibration
  FOR INSERT TO public
  WITH CHECK (true);

CREATE POLICY "Admin reads all calibration" ON public.calibration
  FOR SELECT TO public
  USING ((auth.jwt() ->> 'email'::text) = 'zarelalopes@gmail.com'::text);

CREATE POLICY "Admin updates calibration" ON public.calibration
  FOR UPDATE TO public
  USING ((auth.jwt() ->> 'email'::text) = 'zarelalopes@gmail.com'::text);


-- ---------- catalog_capitulo ----------
CREATE POLICY catalog_capitulo_all ON public.catalog_capitulo
  FOR ALL TO public
  USING (true)
  WITH CHECK (true);


-- ---------- catalog_familia ----------
CREATE POLICY catalog_familia_all ON public.catalog_familia
  FOR ALL TO public
  USING (true)
  WITH CHECK (true);


-- ---------- catalog_grupo ----------
CREATE POLICY catalog_grupo_all ON public.catalog_grupo
  FOR ALL TO public
  USING (true)
  WITH CHECK (true);


-- ---------- chat_leads ----------
CREATE POLICY chat_leads_insert ON public.chat_leads
  FOR INSERT TO anon
  WITH CHECK (true);

CREATE POLICY chat_leads_read ON public.chat_leads
  FOR SELECT TO anon
  USING (true);

CREATE POLICY chat_leads_update ON public.chat_leads
  FOR UPDATE TO anon
  USING (true);


-- ---------- cleanup_log ----------
CREATE POLICY "Backend insert cleanup log" ON public.cleanup_log
  FOR INSERT TO anon
  WITH CHECK (true);


-- ---------- contact_messages ----------
CREATE POLICY contact_anon_insert ON public.contact_messages
  FOR INSERT TO anon, authenticated
  WITH CHECK (true);

CREATE POLICY contact_anon_select ON public.contact_messages
  FOR SELECT TO anon, authenticated
  USING (true);

CREATE POLICY contact_anon_update ON public.contact_messages
  FOR UPDATE TO anon, authenticated
  USING (true)
  WITH CHECK (true);


-- ---------- cronogramas ----------
CREATE POLICY cronogramas_all_insert ON public.cronogramas
  FOR INSERT TO public
  WITH CHECK (true);

CREATE POLICY cronogramas_all_select ON public.cronogramas
  FOR SELECT TO public
  USING (true);

CREATE POLICY cronogramas_all_update ON public.cronogramas
  FOR UPDATE TO public
  USING (true)
  WITH CHECK (true);


-- ---------- density_benchmarks ----------
CREATE POLICY density_benchmarks_all ON public.density_benchmarks
  FOR ALL TO public
  USING (true)
  WITH CHECK (true);


-- ---------- density_ingest_raw ----------
CREATE POLICY density_ingest_raw_all ON public.density_ingest_raw
  FOR ALL TO public
  USING (true)
  WITH CHECK (true);


-- ---------- instagram_post_insights ----------
CREATE POLICY insights_insert ON public.instagram_post_insights
  FOR INSERT TO anon, authenticated
  WITH CHECK (true);

CREATE POLICY insights_select ON public.instagram_post_insights
  FOR SELECT TO anon, authenticated
  USING (true);

CREATE POLICY insights_update ON public.instagram_post_insights
  FOR UPDATE TO anon, authenticated
  USING (true)
  WITH CHECK (true);


-- ---------- instagram_scheduled_posts ----------
CREATE POLICY ig_sched_anon_all ON public.instagram_scheduled_posts
  FOR ALL TO anon, authenticated
  USING (true)
  WITH CHECK (true);


-- ---------- item_notes ----------
CREATE POLICY "Backend manage item_notes" ON public.item_notes
  FOR ALL TO anon
  USING (true)
  WITH CHECK (true);


-- ---------- item_reviews ----------
CREATE POLICY "Backend manage item_reviews" ON public.item_reviews
  FOR ALL TO anon
  USING (true)
  WITH CHECK (true);


-- ---------- market_heuristics ----------
CREATE POLICY market_heuristics_insert ON public.market_heuristics
  FOR INSERT TO anon
  WITH CHECK (true);

CREATE POLICY market_heuristics_read ON public.market_heuristics
  FOR SELECT TO anon
  USING (true);


-- ---------- nps_responses ----------
CREATE POLICY "Users can insert own nps" ON public.nps_responses
  FOR INSERT TO anon, authenticated
  WITH CHECK (true);

CREATE POLICY "Users can read own nps" ON public.nps_responses
  FOR SELECT TO authenticated
  USING ((auth.uid())::text = user_id);


-- ---------- profiles ----------
CREATE POLICY "Users insert own profile" ON public.profiles
  FOR INSERT TO public
  WITH CHECK ((auth.uid())::text = user_id);

CREATE POLICY "Admin reads all profiles" ON public.profiles
  FOR SELECT TO public
  USING ((auth.jwt() ->> 'email'::text) = 'zarelalopes@gmail.com'::text);

CREATE POLICY "Users read own profile" ON public.profiles
  FOR SELECT TO public
  USING ((auth.uid())::text = user_id);

CREATE POLICY "Users update own profile" ON public.profiles
  FOR UPDATE TO public
  USING ((auth.uid())::text = user_id);


-- ---------- project_cashback_events ----------
CREATE POLICY cashback_events_insert ON public.project_cashback_events
  FOR INSERT TO anon
  WITH CHECK (true);

CREATE POLICY cashback_events_read ON public.project_cashback_events
  FOR SELECT TO anon
  USING (true);


-- ---------- project_clients ----------
CREATE POLICY project_clients_delete ON public.project_clients
  FOR DELETE TO anon
  USING (true);

CREATE POLICY project_clients_insert ON public.project_clients
  FOR INSERT TO anon
  WITH CHECK (true);

CREATE POLICY project_clients_read ON public.project_clients
  FOR SELECT TO anon
  USING (true);

CREATE POLICY project_clients_update ON public.project_clients
  FOR UPDATE TO anon
  USING (true);


-- ---------- project_items ----------
CREATE POLICY "Backend manage project_items" ON public.project_items
  FOR ALL TO anon
  USING (true)
  WITH CHECK (true);


-- ---------- project_supplier_quotes ----------
CREATE POLICY supplier_quotes_delete ON public.project_supplier_quotes
  FOR DELETE TO anon
  USING (true);

CREATE POLICY supplier_quotes_insert ON public.project_supplier_quotes
  FOR INSERT TO anon
  WITH CHECK (true);

CREATE POLICY supplier_quotes_read ON public.project_supplier_quotes
  FOR SELECT TO anon
  USING (true);

CREATE POLICY supplier_quotes_update ON public.project_supplier_quotes
  FOR UPDATE TO anon
  USING (true);


-- ---------- projects ----------
CREATE POLICY "Service can insert projects" ON public.projects
  FOR INSERT TO public
  WITH CHECK (true);

CREATE POLICY "Admin reads all projects" ON public.projects
  FOR SELECT TO public
  USING ((auth.jwt() ->> 'email'::text) = 'zarelalopes@gmail.com'::text);

CREATE POLICY "Backend can select anonymous projects" ON public.projects
  FOR SELECT TO public
  USING ((user_id = 'anonymous'::text) OR (user_id IS NULL) OR (user_id = ''::text));

CREATE POLICY "Users read own projects" ON public.projects
  FOR SELECT TO public
  USING ((auth.uid())::text = user_id);

CREATE POLICY "Service can update projects" ON public.projects
  FOR UPDATE TO public
  USING (true);


-- ---------- sinapi_composicao ----------
CREATE POLICY sinapi_composicao_all ON public.sinapi_composicao
  FOR ALL TO public
  USING (true)
  WITH CHECK (true);


-- ---------- sinapi_insumos ----------
CREATE POLICY sinapi_insumos_insert ON public.sinapi_insumos
  FOR INSERT TO anon
  WITH CHECK (true);

CREATE POLICY sinapi_insumos_read ON public.sinapi_insumos
  FOR SELECT TO anon
  USING (true);


-- ---------- tcpo_composicoes ----------
CREATE POLICY tcpo_comp_delete ON public.tcpo_composicoes
  FOR DELETE TO anon
  USING (true);

CREATE POLICY tcpo_comp_write ON public.tcpo_composicoes
  FOR INSERT TO anon
  WITH CHECK (true);

CREATE POLICY tcpo_comp_read ON public.tcpo_composicoes
  FOR SELECT TO anon, authenticated
  USING (true);

CREATE POLICY tcpo_comp_update ON public.tcpo_composicoes
  FOR UPDATE TO anon
  USING (true);


-- ---------- tcpo_insumos ----------
CREATE POLICY tcpo_ins_delete ON public.tcpo_insumos
  FOR DELETE TO anon
  USING (true);

CREATE POLICY tcpo_ins_write ON public.tcpo_insumos
  FOR INSERT TO anon
  WITH CHECK (true);

CREATE POLICY tcpo_ins_read ON public.tcpo_insumos
  FOR SELECT TO anon, authenticated
  USING (true);

CREATE POLICY tcpo_ins_update ON public.tcpo_insumos
  FOR UPDATE TO anon
  USING (true);


-- ---------- user_credits ----------
CREATE POLICY user_credits_all ON public.user_credits
  FOR ALL TO public
  USING (true)
  WITH CHECK (true);


-- =============================================================================
-- FIM DO ROLLBACK
-- =============================================================================
-- Policies recriadas: 61
-- Validar com:
--   SELECT tablename, policyname, cmd, roles
--   FROM pg_policies WHERE schemaname = 'public'
--   ORDER BY tablename, cmd, policyname;
-- =============================================================================
