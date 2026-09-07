-- 002 — tabela do token da Meta + cron de renovação
--
-- Roda no projeto Supabase do AI.arq (kqjabzwgbfuivzlcfvvu).
--
-- POR QUE ESTA TABELA EXISTE: até 06/09/2026 o token do Instagram vinha só de
-- META_ACCESS_TOKEN no Render. Um processo não altera de forma durável a
-- própria env var, então renovação automática era impossível — o token novo
-- morreria no primeiro deploy. Sem esta tabela, o cron abaixo seria teatro.
--
-- E o relógio corre: token de Instagram Login que passa 60 dias sem refresh
-- morre em definitivo e só volta com Business Login manual.

begin;

create table if not exists public.meta_token (
  conta        text primary key,          -- 'aiarq' | 'dizemfontes'
  token        text not null,
  expira_em    timestamptz,               -- null = validade desconhecida
  renovado_em  timestamptz not null default now(),
  criado_em    timestamptz not null default now()
);

comment on table public.meta_token is
  'Token de longa duração da Meta por conta. Fonte de verdade; META_ACCESS_TOKEN vira apenas semente.';
comment on column public.meta_token.expira_em is
  'now() + expires_in devolvido pelo refresh. Null antes da primeira renovação pelo cron.';

-- Só o service role toca nisto. É segredo.
alter table public.meta_token enable row level security;
revoke all on public.meta_token from anon, authenticated;

commit;


-- ─────────────────────────────────────────────────────────────────────────
-- CRON DE RENOVAÇÃO
--
-- Roda 1x por dia às 08:00 UTC (05:00 BRT). O endpoint decide se renova: só
-- age quando faltam menos de 30 dias. Rodar todo dia e decidir do lado do
-- servidor é de propósito — cron mensal tem uma chance por mês de acertar, e
-- se falhar naquele dia ninguém percebe até o token morrer.
--
-- 🪤 08:00 e não 09:00 de propósito: o aiarq_metricas_tick já ocupa as 09:00, e
-- estes ticks têm corpo bloqueante. Dois no mesmo minuto competem pelo mesmo
-- servidor — que já congelou 33s por causa de um tick sozinho (ver o comentário
-- do /api/emails/auto/tick em main.py).
--
-- Substitua <TICK_SECRET> pelo valor da env var TICK_SECRET do Render.
-- ─────────────────────────────────────────────────────────────────────────

select cron.schedule(
  'aiarq_token_tick',
  '0 8 * * *',
  $$
  select net.http_post(
    url     := 'https://ai-arq.onrender.com/api/token/tick',
    headers := jsonb_build_object(
                 'Content-Type',  'application/json',
                 'X-Tick-Secret', '<TICK_SECRET>'
               ),
    body    := '{}'::jsonb,
    timeout_milliseconds := 20000
  );
  $$
);

-- Conferir:      select jobname, schedule, active from cron.job order by jobid;
-- Ver execuções: select * from cron.job_run_details
--                where jobid = (select jobid from cron.job where jobname='aiarq_token_tick')
--                order by start_time desc limit 10;
-- Remover:       select cron.unschedule('aiarq_token_tick');
