-- ✅ APLICADA em 27/09/2026 ~22h BRT, ANTES do deploy (migração `metricas_origens_amostra`) — item 4 do plano de
-- telemetria de 27/09/2026, liberado pelo Pedro ("depois segue com o item 4"). Conferido: coluna numeric, nullable.
--
-- O Cloudflare AMOSTRA o Web Analytics: pedida a semana de 20–26/09 de uma vez, veio com sampleInterval 10 (números
-- em múltiplos de 10); dia a dia, entre 1,2 e 2. `origens_amostra` guarda o MAIOR sampleInterval do dia (1 = contou
-- tudo; nulo = dia antigo, sem a medida) — acima de 1, o painel diz que é estimativa.
-- 🪤 ORDEM: esta coluna ANTES do backend novo. O tick manda `origens_amostra` na linha do dia; sem a coluna o
-- PostgREST recusa a linha INTEIRA e o dia não é gravado.
-- Aditiva (nullable, sem default): não mexe em linha nenhuma que já existe.

alter table public.metricas_diarias add column if not exists origens_amostra numeric;
comment on column public.metricas_diarias.origens_amostra is
  'Maior sampleInterval do Web Analytics (Cloudflare) no dia das origens. 1 = contou tudo; >1 = estimativa; nulo = não medido.';
