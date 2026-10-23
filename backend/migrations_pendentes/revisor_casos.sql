-- ═══════════════════════════════════════════════════════════════
-- revisor_casos — o caso investigado a partir da fila do revisor noturno
-- (parte 3 do revisor, peças A e B — 23/10/2026)
--
-- Uma linha por projeto investigado. Quem grava é a sessão que investiga
-- (por SQL, à mão, no fim de cada caso); o tick da noite LÊ e:
--   - projeto `consertado` / `nao_e_defeito` sai da contagem de suspeitos;
--   - se o cliente fizer algo DEPOIS de `fechado_em`, volta pra fila marcado
--     "voltou depois do conserto".
--
-- 🔒 Repositório público e LGPD: `forma` é a FORMA do defeito numa frase, sem
--    nome de cliente, de arquivo, de bloco ou de layer. Só job_id (opaco).
-- RLS LIGADA SEM POLICY = só a service_role lê/escreve.
-- Aplicar via MCP do Supabase — ANTES do deploy do código que lê.
-- ═══════════════════════════════════════════════════════════════

create table if not exists public.revisor_casos (
  job_id        text primary key,
  estado        text not null check (estado in ('olhando', 'confirmado', 'consertado', 'nao_e_defeito')),
  -- a forma do defeito, numa frase, sem nome de nada ("bloco de porta sem atributo virou contagem 0")
  forma         text not null default '',
  -- o que na ficha levou até ele: código de motivo ("medido_mexido") ou etapa ("motor:spline")
  origem        text not null default '',
  conserto_commit text,               -- commit do conserto (sha curto)
  chave         text,                 -- se o conserto nasceu atrás de chave desligada
  teste         text,                 -- "backend/tests/arquivo.py::funcao"
  -- quando o caso FECHOU (consertado no ar, ou visto que não é defeito). Sinal do
  -- cliente depois disto = "voltou depois do conserto".
  fechado_em    timestamptz,
  criado_em     timestamptz not null default now(),
  atualizado_em timestamptz not null default now(),
  -- caso fechado sem data não teria como saber se "voltou"
  constraint revisor_casos_fechado_tem_data
    check (estado not in ('consertado', 'nao_e_defeito') or fechado_em is not null)
);

alter table public.revisor_casos enable row level security;
-- sem policy de propósito.

comment on table public.revisor_casos is
  'Caso investigado a partir da fila do revisor noturno: estado, forma do defeito (sem nome), commit, chave, teste. Lido pelo POST /api/revisor/tick.';

-- a rodada e a ficha passam a carregar o caso
alter table public.revisor_noturno_noites
  add column if not exists n_tratados integer not null default 0,
  add column if not exists n_voltaram integer not null default 0;
alter table public.revisor_noturno_fichas
  add column if not exists caso jsonb;
