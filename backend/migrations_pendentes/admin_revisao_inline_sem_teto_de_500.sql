-- APLICADA em 19/09/2026 (Supabase, migration `admin_revisao_inline_sem_teto_de_500`).
-- Fica aqui como registro do que o painel de revisões passou a ler — a bancada
-- não roda SQL.
--
-- Item 13 da fila: "a lista de revisões do painel corta em 500".
--
-- 🩸 Quando a fila registrou o risco o acervo tinha 433 registros e o teto
-- parecia folgado. Medido em 19/09/2026:
--
--   no banco .............................. 624
--   dentro da janela de 500 ............... 500
--   JOGADOS FORA EM SILÊNCIO .............. 124   (20%)
--   crescimento ..................... ~193 por semana
--
-- Dos 124 que ficavam de fora: 75 `approve` e 49 `edit`. Nenhum `reject`,
-- nenhum `faltou`, nenhum recado humano — os sinais RAROS ainda estavam
-- dentro da janela. Em uma semana não estariam. O dano de hoje era as
-- CONTAGENS mentirem para menos, sem ninguém ter como perceber.
--
-- 🩸 v2 (mesma data, depois da revisão adversarial): a v1 montava AQUI o
--    retrato do item apagado (descricao/unidade/quantidade/disciplina/selo,
--    extraídos de `edits->_antes`). Parecia mais limpo e APAGAVA a cobertura
--    de dois guardas (05/09 e 31/08) que exigem esses campos no bloco Python
--    — a bancada não roda SQL. Agora o SQL só CONTA (que é o que só ele faz)
--    e as linhas raras vêm CRUAS; a montagem e as réguas ficam no Python.
--
-- 🪤 A RÉGUA DO RECADO NÃO MORA AQUI. Quem distingue o texto que o cliente
--    escreveu do texto que a NOSSA tela escreve é `main.recado_digitado` —
--    reimplementá-la em SQL criaria uma segunda verdade que diverge calada
--    (a lição de `feedback_nao_reimplemente_a_regua_pergunte_ao_guarda`).
--    Como só 8 registros em 624 têm texto, a função devolve TODOS eles em
--    `candidatos_a_recado` e o Python aplica a régua. Um lugar só.
-- 🪤 NUNCA `DROP FUNCTION`: o DROP leva o `proacl` (service_role=X) e o painel
--    passa a dizer "não consegui ler", em silêncio.
create or replace function admin_revisao_inline(limite_listas integer default 20)
returns json
language sql
security definer
set search_path = public
as $$
with tot as (
  select
    count(*) filter (where action = 'approve')::int as aprovacoes,
    count(*) filter (where action = 'edit')::int    as edicoes,
    count(*) filter (where action = 'reject')::int  as exclusoes,
    count(*) filter (where action = 'faltou')::int  as faltou,
    count(*)::int                                   as total,
    count(distinct job_id)::int                     as projetos
  from item_reviews
), lim as (select greatest(coalesce(limite_listas, 20), 1) as n)
select json_build_object(
  'total_no_banco', (select total from tot),
  'aprovacoes',     (select aprovacoes from tot),
  'edicoes',        (select edicoes from tot),
  'exclusoes',      (select exclusoes from tot),
  'faltou',         (select faltou from tot),
  'projetos',       (select projetos from tot),
  -- CRUAS: quem monta o retrato e o Python (main._antes_do_item), onde os
  -- guardas de 31/08 e 05/09 conseguem executar a montagem.
  'exclusoes_cruas', coalesce((select json_agg(x) from (
      select job_id, item_id, action, edits, comment, reviewed_at
      from item_reviews where action = 'reject'
      order by reviewed_at desc limit (select n from lim)) x), '[]'::json),
  'faltou_cruas', coalesce((select json_agg(x) from (
      select job_id, item_id, action, edits, comment, reviewed_at
      from item_reviews where action = 'faltou'
      order by reviewed_at desc limit (select n from lim)) x), '[]'::json),
  'edits_crus', coalesce((select json_agg(x) from (
      select job_id, item_id, action, edits, comment, reviewed_at
      from item_reviews where action = 'edit'
      order by reviewed_at desc limit greatest((select n from lim) / 2, 1)) x), '[]'::json),
  'candidatos_a_recado', coalesce((select json_agg(x) from (
      select job_id, item_id, action, edits, comment, reviewed_at
      from item_reviews where coalesce(trim(comment), '') <> ''
      order by reviewed_at desc) x), '[]'::json)
);
$$;

revoke all on function admin_revisao_inline(integer) from public, anon, authenticated;
grant execute on function admin_revisao_inline(integer) to service_role;
