# Auditoria do Banco Supabase — AI.arq

**Data:** 09/06/2026
**Projeto:** kqjabzwgbfuivzlcfvvu
**Auditor:** database-reviewer (somente leitura — nenhuma mudança aplicada)

---

## Resumo executivo

O banco está **saudável em dados**: zero jobs travados, zero órfãos, tipos de coluna corretos, todas as 29 tabelas com RLS ligado. Os problemas são de **higiene de schema** (4 tabelas filhas referenciam `job_id` sem foreign key declarada — risco futuro de órfão) e **performance preventiva** (5 FKs sem índice, políticas RLS reavaliando `auth.*()` por linha). A camada de segurança detalhada fica pra lente de segurança, mas o panorama aqui mostra 1 ERRO (view SECURITY DEFINER) e dezenas de WARNs de funções expostas ao `anon`.

**Grade: B** — nada quebrado hoje, mas há dívida de schema que vira problema quando a base crescer.

---

## 📊 Panorama

- **Tabelas no schema `public`:** 29
- **RLS:** 29/29 com RLS ligado (100%). Panorama bom; detalhe de políticas fica pra lente de segurança.
- **Migrations aplicadas:** 76 (tabela `schema_migrations`)

**Maiores tabelas (por linhas vivas):**

| Tabela | Linhas | Observação |
|---|---|---|
| `sinapi_insumos` | 54.529 | catálogo SINAPI (Analítico) — esperado |
| `sinapi_composicao` | 10.284 | catálogo SINAPI — esperado |
| `tcpo_insumos` | 6.733 | catálogo TCPO |
| `tcpo_composicoes` | 1.333 | catálogo TCPO |
| `project_items` | 755 | itens dos projetos dos usuários |
| `density_ingest_raw` | 264 | ingestão de densidade |
| `density_benchmarks` | 244 | benchmarks de densidade |
| `market_heuristics` | 82 | heurísticas de mercado |
| `instagram_scheduled_posts` | 72 | posts agendados |
| `projects` | 83 | projetos dos usuários |
| `profiles` | 12 | usuários (~8-12 reais) |

Os "grandões" são catálogos de referência (SINAPI/TCPO), não dados transacionais inflados. **Nenhuma tabela inchada de lixo.**

---

## 🔴 Críticos

### 1. View `calibration_factors` com SECURITY DEFINER (ERRO do advisor)
Único erro de nível ERROR. A view roda com os privilégios de quem a criou (provavelmente postgres/admin), então qualquer um que a consultar enxerga dados como se fosse dono — fura o RLS. Precisa ser recriada como `security_invoker = true` ou ter o acesso restrito.
Ref: https://supabase.com/docs/guides/database/database-linter?lint=0010_security_definer_view

### 2. Foreign keys faltando entre tabelas filhas e `projects`
`project_items`, `cronogramas`, `item_reviews` e `item_notes` guardam `job_id` mas **não têm FK declarada** apontando pra `projects.job_id`. Hoje não há órfão (verifiquei: 0), mas é só convenção — nada no banco impede um item ficar pendurado se um projeto for apagado. Quando ligar `ON DELETE CASCADE`, a limpeza de projeto vira automática e segura.
> Obs: as FKs por `job_id` que JÁ existem (`project_cashback_events`, `project_clients`, `project_supplier_quotes`) confirmam que `projects.job_id` tem unique — dá pra referenciar.

### 3. Jobs travados — NENHUM (verificado, ok)
Zero projetos em `processing`/`queued`/`pending` há mais de 2h. Na prática o status no banco é só `done` (35) ou `error` (48) — não há estado intermediário persistido. Sem travamento.

### 4. Taxa de erro histórica alta, mas melhorando
48 de 83 projetos (58%) estão em `error` na vida toda. **Porém é cauda de testes antigos**: nos últimos 30 dias foram 15 `done` x 4 `error` (~21% de falha). Não é problema de banco, é qualidade de extração — vale acompanhar, não é crítico de DB.

### 5. Dados órfãos — NENHUM (verificado, ok)
- Projetos concluídos sem `project_items`: **0**
- `project_items` com `job_id` inexistente: **0**
- `cronogramas` órfãos: **0**

---

## 🟡 Performance (P1)

### Índices das queries quentes — já existem (ok)
- `project_items WHERE job_id` → `idx_project_items_job` ✓
- `projects WHERE user_id` → coberto (idx_scan alto, sem seq scan problemático) ✓
- `instagram_scheduled_posts WHERE status + publish_at` → `idx_ig_sched_status_pubat` + `idx_ig_sched_pending_pubat` ✓
- `cronogramas WHERE job_id` → `idx_cronogramas_job_id` ✓

As queries que o pessoal mais roda já estão indexadas. As lacunas abaixo são de FK (joins de catálogo), não das rotas quentes do usuário.

### FKs sem índice de cobertura (5 — advisor performance)
São joins de catálogo/hierarquia. Em tabelas pequenas o impacto hoje é baixo, mas `sinapi_composicao` (10k) merece o índice:

```sql
CREATE INDEX idx_catalog_familia_grupo      ON public.catalog_familia(grupo_id);
CREATE INDEX idx_catalog_grupo_capitulo     ON public.catalog_grupo(capitulo_id);
CREATE INDEX idx_density_ingest_raw_familia ON public.density_ingest_raw(familia_id);
CREATE INDEX idx_ig_insights_slot           ON public.instagram_post_insights(slot_key);
CREATE INDEX idx_sinapi_composicao_familia  ON public.sinapi_composicao(familia_id);  -- prioridade (10k linhas)
```

### RLS reavaliando `auth.*()` por linha (auth_rls_initplan — 17 políticas)
Políticas em `profiles`, `projects`, `beta_codes`, `calibration`, `nps_responses` chamam `auth.uid()`/`current_setting()` direto, que reexecuta a cada linha. Troca pra subquery resolve. Exemplo do padrão (aplicar em todas):

```sql
-- de:  user_id = auth.uid()
-- pra: user_id = (select auth.uid())
ALTER POLICY "Users read own projects" ON public.projects
  USING (user_id = (select auth.uid())::text);
```
Em escala custa caro; com 83 projetos hoje é imperceptível. Vale arrumar antes de crescer.

### Políticas permissivas múltiplas (multiple_permissive_policies — `beta_codes`, `profiles`, `projects`)
Várias políticas PERMISSIVE pro mesmo role+ação (ex.: `projects` tem 3 SELECT permissivas pro `anon`). Cada query roda todas. Consolidar em uma só por ação melhora performance — mas mexe em segurança, então fazer junto com a revisão de RLS, com cuidado.

### Índices nunca usados (12 — candidatos a remoção futura)
`idx_nps_category`, `idx_projects_archived`, `idx_projects_parent`, `idx_density_bench_*` (3), `idx_agent_conv_user`, `idx_item_notes_job`, `idx_cleanup_log_ran`, `idx_tcpo_comp_codigo`, `market_heuristics_category`, `chat_leads_email`, `idx_contact_status_created`. Muitos são de tabelas com pouquíssimas linhas (uso real ainda não aconteceu) — **não remover agora**, são baratos. Reavaliar quando a base tiver volume.

---

## 🧹 Limpeza sugerida

- **Sem órfãos pra limpar** — banco limpo nesse quesito.
- **Tabelas vazias estruturais** (`project_clients`, `project_supplier_quotes`, `project_cashback_events`, `chat_leads`, `item_notes`, `calibration`): são features da Fase 5 / funil que ainda não receberam dado. Manter — não é lixo.
- **Dead tuples**: `projects` (49 mortas pra 83 vivas) e `flow_state` (auth) têm proporção alta de tuplas mortas. Um `VACUUM ANALYZE public.projects;` ajeita o planner. Autovacuum deve cobrir, mas em tabela pequena às vezes demora a disparar.
- **`density_ingest_raw`** tem 75 mortas pra 264 vivas — mesmo caso, vacuum resolve.

---

## 🛠️ Top fixes (SQL sugerido — NÃO aplicado)

Ordem de prioridade. Tudo via `apply_migration` quando o Pedro autorizar.

```sql
-- 1) CRÍTICO: tirar SECURITY DEFINER da view (fura RLS)
ALTER VIEW public.calibration_factors SET (security_invoker = true);

-- 2) FKs faltando filho->projects (integridade + cascade na limpeza)
ALTER TABLE public.project_items
  ADD CONSTRAINT project_items_job_id_fkey
  FOREIGN KEY (job_id) REFERENCES public.projects(job_id) ON DELETE CASCADE;
ALTER TABLE public.cronogramas
  ADD CONSTRAINT cronogramas_job_id_fkey
  FOREIGN KEY (job_id) REFERENCES public.projects(job_id) ON DELETE CASCADE;
ALTER TABLE public.item_reviews
  ADD CONSTRAINT item_reviews_job_id_fkey
  FOREIGN KEY (job_id) REFERENCES public.projects(job_id) ON DELETE CASCADE;
ALTER TABLE public.item_notes
  ADD CONSTRAINT item_notes_job_id_fkey
  FOREIGN KEY (job_id) REFERENCES public.projects(job_id) ON DELETE CASCADE;
-- (pré-checagem: confirmar 0 órfãos antes de adicionar — hoje está 0)

-- 3) Índice na FK quente do catálogo SINAPI (10k linhas)
CREATE INDEX idx_sinapi_composicao_familia ON public.sinapi_composicao(familia_id);

-- 4) PK na tabela profiles (advisor: no_primary_key)
ALTER TABLE public.profiles ADD PRIMARY KEY (user_id);

-- 5) Higiene: vacuum nas tabelas com muitas tuplas mortas
VACUUM ANALYZE public.projects;
VACUUM ANALYZE public.density_ingest_raw;
```

(As otimizações de RLS `(select auth.uid())` e o restante dos índices de FK ficam num segundo lote, junto da revisão de segurança.)

---

## ❓ Decisão pra Pedro

1. **View `calibration_factors` (SECURITY DEFINER):** essa é a única coisa marcada como ERRO. Ela existe pra um propósito legítimo (dar acesso a fatores de calibração sem expor a tabela crua)? Se sim, dá pra trocar pra `security_invoker` e ajustar as permissões. Se não está mais em uso, pode dropar. **Me confirma o que essa view faz hoje** que eu sugiro o caminho seguro.

2. **Foreign keys com `ON DELETE CASCADE`:** quero adicionar as 4 FKs faltando pra que apagar um projeto limpe automaticamente itens/cronograma/reviews/notas. Hoje isso depende do código fazer na ordem certa. **Topa o CASCADE?** É o comportamento que faz sentido pro "isolamento de projetos", mas confirma que não existe caso onde você quer manter um item sobrevivendo ao projeto.

3. **Os 48 projetos em `error`:** são quase todos de testes antigos. Quer que eu (em outra sessão) investigue as `error_message` deles pra ver se tem padrão de falha recorrente no motor de extração, ou pode arquivar/limpar como ruído de teste?

---

*Auditoria somente-leitura. Nenhum DDL/DML executado, nada commitado. Os SQLs acima são sugestões — aplicar via apply_migration só após sua autorização.*
