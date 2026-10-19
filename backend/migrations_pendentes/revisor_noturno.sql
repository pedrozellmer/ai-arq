-- ═══════════════════════════════════════════════════════════════
-- revisor noturno — a ficha de cada projeto de cliente, toda noite
-- (backend/revisor_noturno.py; tick POST /api/revisor/tick; painel
--  GET /api/admin/revisor-noturno, aba Motor do admin).
--
-- Duas tabelas:
--   revisor_noturno_noites  — uma linha por rodada (o resumo e os padrões)
--   revisor_noturno_fichas  — uma linha por projeto por rodada
--
-- 🔒 LGPD: só CONTAGEM e job_id. Nenhum texto do cliente, nome ou e-mail —
--    o recado continua onde já mora (item_reviews), lido na "Voz do cliente".
--    As fichas guardam 90 dias (o próprio tick apaga o que passar), a mesma
--    janela da retenção dos arquivos.
--
-- RLS LIGADA SEM POLICY = só a service_role lê/escreve (padrão das tabelas
-- internas: revision_feedback, error_log).
-- Aplicar via MCP do Supabase — SÓ junto com o deploy do código que grava.
-- ═══════════════════════════════════════════════════════════════

create table if not exists public.revisor_noturno_noites (
  noite          date primary key,              -- dia da rodada, em Brasília
  rodou_em       timestamptz not null default now(),
  janela_dias    integer not null,
  n_projetos     integer not null default 0,
  n_suspeitos    integer not null default 0,
  n_novidades    integer not null default 0,
  -- [{etapa, projetos, com_retorno, com_reacao, exemplos:[job_id]}]
  padroes        jsonb not null default '[]'::jsonb,
  -- leitura que falhou NÃO vira zero: a rodada para e diz qual foi
  falhas         jsonb not null default '[]'::jsonb
);

create table if not exists public.revisor_noturno_fichas (
  noite                    date not null references public.revisor_noturno_noites(noite) on delete cascade,
  job_id                   text not null,
  criado_em                timestamptz,
  nota                     integer not null default 0,
  -- [{codigo, peso, texto}] — o texto é NOSSO ("marcou 2 item(ns) como faltando")
  motivos                  jsonb not null default '[]'::jsonb,
  -- contagens dos 6 sinais (ver revisor_noturno.montar_fichas)
  sinais                   jsonb not null default '{}'::jsonb,
  ultimo_sinal_do_cliente  timestamptz,
  novidade                 boolean not null default false,
  primary key (noite, job_id)
);

create index if not exists idx_revisor_fichas_job on public.revisor_noturno_fichas (job_id);

alter table public.revisor_noturno_noites enable row level security;
alter table public.revisor_noturno_fichas enable row level security;
-- sem policy de propósito.

comment on table public.revisor_noturno_noites is
  'Uma rodada do revisor noturno: quantos projetos, quantos suspeitos, padrões etapa do motor × reação do cliente. Gravada por POST /api/revisor/tick.';
comment on table public.revisor_noturno_fichas is
  'Ficha de um projeto de cliente numa rodada do revisor noturno: nota de suspeita, motivos e contagens dos 6 sinais. Só contagem, sem texto do cliente. Retenção 90 dias.';

-- ─────────────────────────────────────────────────────────────────────────
-- O agendamento: 03:12 de Brasília (06:12 UTC).
-- 🪤 Minuto 12 de propósito: o cadastro-alerta-tick roda a cada 5 min (cai em
-- :00, :05, :10…), o newsletter em :05/:20/:35/:50, e o usage-events-24-meses
-- às 06:40 UTC. Tick com corpo bloqueante não divide minuto com outro.
-- Substitua <TICK_SECRET> pelo valor da env var TICK_SECRET do Render
-- (o repositório é público: o segredo NUNCA entra neste arquivo).
-- ─────────────────────────────────────────────────────────────────────────

select cron.schedule(
  'aiarq_revisor_noturno_tick',
  '12 6 * * *',
  $$
  select net.http_post(
    url     := 'https://ai-arq.onrender.com/api/revisor/tick',
    headers := jsonb_build_object(
                 'Content-Type',  'application/json',
                 'X-Tick-Secret', '<TICK_SECRET>'
               ),
    body    := '{}'::jsonb,
    timeout_milliseconds := 60000
  );
  $$
);

-- Conferir:      select jobname, schedule, active from cron.job order by jobid;
-- Ver a rodada:  select noite, rodou_em, n_projetos, n_suspeitos, falhas
--                from revisor_noturno_noites order by noite desc limit 5;
-- Remover:       select cron.unschedule('aiarq_revisor_noturno_tick');
