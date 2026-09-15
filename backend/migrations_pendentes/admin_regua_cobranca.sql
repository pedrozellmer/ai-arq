-- admin_regua_cobranca — o painel da régua de cobrança (Financeiro do admin).
--
-- 🩸 15/09/2026 — ESTE ARQUIVO NASCEU HOJE, e a função é de 06/09. Ela vivia
-- SÓ no banco (migração 20260906190435), sem cópia no repositório: quem
-- quisesse saber o que a tela do dinheiro calcula tinha que perguntar ao
-- Postgres. Aplicada com `CREATE OR REPLACE`; o arquivo é a cópia fiel.
--
-- 🪤 NUNCA `DROP FUNCTION` aqui. A função é RETURNS json (escalar), então
-- acrescentar chave no json_build_object não muda assinatura e o REPLACE
-- basta. Um DROP apagaria o `proacl` (service_role=X/postgres) e a régua
-- sumiria da tela EM SILÊNCIO — `_regua_cobranca_resumo` engole o erro e
-- devolve None.
--
-- 🪤 `nullif(linhas_total, 0)`: existe projeto com linhas_total = 0 na base.
-- Divisão por zero aqui não derruba só a faixa nova — derruba a função
-- INTEIRA, e o painel perde junto os números que já funcionavam.
--
-- 🔑 Por que a distribuição existe (achado de 14/09): a régua corta em >= 1
-- linha medida. O docstring dela diz que nasceu porque "a entrega é uma RIFA
-- ... os dois pagariam os mesmos R$97 e nenhum dos dois tinha como saber,
-- antes de pagar, de que lado ia cair". Com corte em 1, ela tirou da rifa o
-- bilhete ZERO e deixou o bilhete de 1 linha valendo o mesmo que o de 92.
-- Medido em 15/09: 8 das 66 cobráveis mediram 2 linhas ou menos.
-- O corte é decisão do Pedro — esta função só põe os casos na mesa.

CREATE OR REPLACE FUNCTION public.admin_regua_cobranca(meses integer DEFAULT 6)
 RETURNS json
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
with base as (
  select date_trunc('month', created_at) as mes, cobravel, linhas_medidas, linhas_total
  from public.projects
  where status = 'done'
    and coalesce(is_eval, false) = false
    and user_id not in ('eval','anonymous') and user_id is not null
    and parent_job_id is null
    and created_at >= date_trunc('month', now()) - make_interval(months => greatest(0, least(meses, 24)) - 1)
),
cob as (
  select linhas_medidas, linhas_total,
         linhas_medidas::numeric / nullif(linhas_total, 0) as fracao
  from base where cobravel
)
select json_build_object(
  'preco_base', 97,
  'por_mes', (select coalesce(json_agg(x order by x.mes), '[]'::json) from (
      select to_char(mes,'YYYY-MM') as mes,
             count(*) as entregas,
             count(*) filter (where cobravel) as cobraveis,
             -- NULL nao e false: entrega nao avaliada aparece separada, senao
             -- some pro lado do "nao cobra" e o numero fica falsamente pessimista.
             count(*) filter (where cobravel is null) as nao_avaliadas,
             round(count(*) filter (where cobravel) * 97.0, 2) as receita_a_97
      from base group by mes) x),
  'total_entregas', (select count(*) from base),
  'total_cobraveis', (select count(*) filter (where cobravel) from base),
  'total_nao_avaliadas', (select count(*) filter (where cobravel is null) from base),
  'mediana_linhas_medidas', (select percentile_cont(0.5) within group (order by linhas_medidas)
                               from base where cobravel is not null),
  -- o que a decisao do corte precisa (15/09/2026). A mediana de cima inclui as
  -- NAO-cobraveis e por isso vale 0: verdadeira, e inutil pra escolher o corte.
  'mediana_linhas_cobravel', (select percentile_cont(0.5) within group (order by linhas_medidas) from cob),
  'mediana_pct_cobravel', (select round((100.0 * percentile_cont(0.5)
                              within group (order by fracao))::numeric, 1) from cob),
  'cobraveis_ate_2_linhas', (select count(*) from cob where linhas_medidas <= 2),
  'faixas', (select coalesce(json_agg(f order by f.ordem), '[]'::json) from (
      select 1 as ordem, 'ate 10%' as rotulo,
             (select count(*) from cob where fracao < 0.10) as n
      union all select 2, '10 a 25%',  (select count(*) from cob where fracao >= 0.10 and fracao < 0.25)
      union all select 3, '25 a 50%',  (select count(*) from cob where fracao >= 0.25 and fracao < 0.50)
      union all select 4, 'mais de 50%', (select count(*) from cob where fracao >= 0.50)
      -- Faixa propria pra quem nao tem base de comparacao. Sem ela, projeto com
      -- linhas_total = 0 sumiria da distribuicao e a soma das faixas nao
      -- bateria com o total de cobraveis: ausencia virando afirmacao.
      union all select 5, 'sem base', (select count(*) from cob where fracao is null)
  ) f)
);
$function$;
