-- ✅ APLICADA em 04/10/2026 ~13h30 BRT (migração `busca_organica`), ANTES do backend que grava nela.
-- Pedro (04/10): "segue com o Search Console e Bing no tick". Ensaiada num DO-block desfeito: o upsert por
-- (fonte, dia, tipo, chave) regrava a linha; anon não lê.
-- Uma linha por (fonte, dia, tipo, chave): total do dia, consulta ou página. Só o backend (service_role) lê e grava.

create table if not exists public.busca_organica (
  fonte text not null check (fonte in ('google', 'bing')),
  dia date not null,
  periodo text not null default 'dia' check (periodo in ('dia', 'semana')),
  tipo text not null check (tipo in ('total', 'consulta', 'pagina')),
  chave text not null default '',
  cliques integer not null default 0,
  impressoes integer not null default 0,
  posicao numeric,
  coletado_em timestamptz not null default now(),
  primary key (fonte, dia, tipo, chave)
);
alter table public.busca_organica enable row level security;
revoke all on public.busca_organica from anon, authenticated;
comment on table public.busca_organica is
  'Busca orgânica (Google Search Console D-3..D-5 e Bing Webmaster): cliques, impressões e posição por dia (Bing: consultas/páginas por semana). Gravada pelo tick diário de métricas.';
