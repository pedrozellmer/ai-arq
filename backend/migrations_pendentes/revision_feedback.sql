-- ═══════════════════════════════════════════════════════════════
-- revision_feedback — "onde a IA mais erra"
-- Uma row por planilha REVISADA que o cliente sobe
-- (/api/projects/{job_id}/revised-sheet/upload). Gravada pelo
-- backend/revision_feedback.py via service_role.
--
-- RLS LIGADA SEM POLICY = só a service_role lê/escreve (padrão das
-- tabelas internas do motor: calibration, error_log, market_heuristics).
-- Aplicar via MCP do Supabase.
-- ═══════════════════════════════════════════════════════════════

create table if not exists public.revision_feedback (
  id                     bigint generated always as identity primary key,
  job_id                 text not null,
  arquivo                text not null default '',
  created_at             timestamptz not null default now(),

  -- contagens da comparação (original = project_items; revisada = XLSX do cliente)
  n_originais            integer not null default 0,
  n_revisados            integer not null default 0,
  n_mantidos             integer not null default 0,
  n_alterados            integer not null default 0,
  n_removidos            integer not null default 0,
  n_adicionados          integer not null default 0,

  -- mediana do |delta %| dos itens alterados (null se nada alterado)
  mediana_abs_delta_pct  numeric,

  -- agregados prontos: {"Pisos e Rodapés": {n_itens, n_alterados, ...}, ...}
  por_disciplina         jsonb not null default '{}'::jsonb,
  -- a pergunta de ouro: {"confirmado": {...}, "estimado": {...}}
  por_confidence         jsonb not null default '{}'::jsonb,
  -- detalhe por item (cap 400): [{descricao, disciplina, confidence,
  --   qty_original, qty_revisada, delta_pct, acao}, ...]
  itens                  jsonb not null default '[]'::jsonb
);

create index if not exists idx_revision_feedback_job_id
  on public.revision_feedback (job_id);
create index if not exists idx_revision_feedback_created_at
  on public.revision_feedback (created_at desc);

alter table public.revision_feedback enable row level security;
-- sem policy de propósito: anon e authenticated não enxergam nada;
-- só o backend (service_role) escreve e o admin lê via endpoint próprio.

comment on table public.revision_feedback is
  'Comparação planilha gerada pela IA × planilha revisada pelo cliente. Mede onde a IA mais erra (por disciplina e por confidence medido/estimado). Gravada por backend/revision_feedback.py; lida por GET /api/admin/revision-feedback.';
