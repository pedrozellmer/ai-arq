-- APLICADA em 19/09/2026 (Supabase): `admin_email_retorno_o_email_trouxe_alguem`,
-- `admin_email_retorno_v2_mediana_e_regua_da_casa` e
-- `admin_email_retorno_v3_conta_a_mesma_visita`.
-- Fica aqui como registro do que a Central de E-mails lê — a bancada não roda SQL.
--
-- Item 12 da fila: "a central de e-mails mostra se o e-mail trouxe alguém?".
-- A Central dizia quantos e-mails SAÍRAM e parava aí.
--
-- 📷 Retrato de 19/09/2026, tirado NUMA leitura só desta RPC (v3, 90 dias, por
-- pessoa, janela fechada, sem as contas da casa). "fechada" = pessoas cuja
-- janela de 7 dias já terminou:
--
--   tipo                  fechada   abriu   mesma visita   mediana
--   boas_vindas              95       72         72         0,044 h
--   planilha_pronta          58        1          0        15,467 h
--   newsletter               64        0          0           —
--   calibracao               49        0          0           —
--   proximo_projeto          35        2          0       106,805 h
--   retorno_30d              39        0          0           —
--   complemento_pronto       12        3          3         0,207 h
--   erro_trocar              13       10         10         0,033 h
--   nudge_onboarding         13        0          0           —
--   leu_sem_medir             8        1          0       144,648 h
--   boas_vindas_cadastro      7        0          0           —
--   nudge_cadastro           11        0          0           —
--   leitura_nova              8        1          0         5,952 h
--   nps_relacional            6        0          0           —
--   erro_reprocessar          2        1          1         0,019 h
--   cronograma_checkin        1        0          0           —
--   sem_medida                3        0          0           —
--   leitura_combinada         1        0          0           —
--   reprocesso_pronto         0        0          0           —
--
-- 🔑 Lido de baixo pra cima: em 90 dias houve QUATRO retornos de verdade
-- (proximo_projeto 2, leu_sem_medir 1, leitura_nova 1). Todo o resto do que
-- parecia retorno aconteceu na MESMA VISITA — o e-mail chegou a quem já estava
-- no site. E nos tipos que falam com quem sumiu (retorno_30d, newsletter,
-- calibracao, nudge_*, nps_relacional), ~182 pessoas, ZERO.
--
-- 🩸 O QUE AS DUAS REVISÕES DERRUBARAM (23 + 22 achados confirmados):
-- 1ª — a Central ia imprimir "72 de 95" no Boas-vindas como se fosse o melhor
--      e-mail da casa. Não era retorno: era CO-PRESENÇA (mediana 2,4 min).
-- 2ª — o conserto disso (a mediana) era um escalar sem dispersão: simulando 36
--      pessoas na mesma visita + 36 uma semana depois, a mediana dá 60 h e o
--      aviso SOME. Agora quem conta é `projeto_7d_mesma_visita`, pessoa por
--      pessoa, com o mesmo corte de 1 h que a tela já usava.
--
-- Decisões de método, cada uma corrigindo um jeito de mentir:
--   por PESSOA, não por envio ... quem recebeu 3 newsletters não vale 3; a
--                                 janela é a do ÚLTIMO envio daquele tipo.
--                                 🪤 Isso ESCONDE retorno que tenha acontecido
--                                 depois de um envio anterior: contando
--                                 qualquer envio, calibracao vira 2. A tela diz
--                                 "último envio" no tooltip.
--   só janela FECHADA .......... quem recebeu ontem vai em `aguardando_7d`.
--   sinal = PROJETO NOVO ....... não depende de cookie. O rastro de site é
--                                cego pra 50 das 125 pessoas — por isso
--                                `sem_rastro_de_site` vai junto, contado DENTRO
--                                da janela fechada.
--   `projeto_antes_7d` ......... a MESMA janela ANTES do envio: a taxa-base.
--   régua da casa .............. `eh_projeto_de_cliente()` e `emails_da_casa()`
--                                em vez de reimplementar o filtro aqui.
--   `volume_total` ............. a rota puxava `email_sent_log` INTEIRA pela
--                                rede pra contar em Python. 🪤 Conta TUDO, desde
--                                o início e inclusive a casa — é o número que a
--                                Central já mostrava; o tooltip diz isso.
--   mediana com 3 casas ........ com 2, uma mediana real de 59,8 min virava
--                                1.00 e perdia a marca de mesma visita.
--
-- 🪤 NUNCA `DROP FUNCTION`: o DROP leva o `proacl` (service_role=X) e a Central
--    passa a dizer "não sei" em silêncio.
create or replace function admin_email_retorno(dias integer default 90,
                                               excluir text default null)
returns json
language sql
security definer
set search_path = public
as $$
with vol as (
  select kind, count(*)::int as volume_total
  from email_sent_log where coalesce(kind, '') <> '' group by kind
), env as (
  select lower(email) as email, kind, sent_at
  from email_sent_log
  where sent_at > now() - make_interval(days => greatest(coalesce(dias, 90), 1))
    and coalesce(email, '') <> ''
    and not (lower(email) = any(public.emails_da_casa()))
    and (excluir is null or lower(email) <> lower(excluir))
), pessoa as (
  select kind, email, max(sent_at) as ultimo, count(*)::int as envios
  from env group by 1, 2
), marcada as (
  select p.kind, p.email, p.ultimo, p.envios,
    (p.ultimo <= now() - interval '7 days')  as fechou_7d,
    (p.ultimo <= now() - interval '14 days') as fechou_14d,
    (select min(x.created_at) from projects x
      where lower(x.user_email) = p.email
        and eh_projeto_de_cliente(x.is_eval, x.user_email)
        and x.created_at >  p.ultimo
        and x.created_at <= p.ultimo + interval '7 days')       as primeiro_depois,
    exists (select 1 from projects x where lower(x.user_email) = p.email
              and eh_projeto_de_cliente(x.is_eval, x.user_email)
              and x.created_at >  p.ultimo
              and x.created_at <= p.ultimo + interval '14 days') as proj_dep_14,
    exists (select 1 from projects x where lower(x.user_email) = p.email
              and eh_projeto_de_cliente(x.is_eval, x.user_email)
              and x.created_at <  p.ultimo
              and x.created_at >= p.ultimo - interval '7 days')  as proj_antes_7,
    not exists (select 1 from usage_events u
                 where lower(u.user_email) = p.email)            as invisivel
  from pessoa p
), agg as (
  select kind,
    sum(envios)::int                                                    as enviados,
    count(*)::int                                                       as pessoas,
    count(*) filter (where fechou_7d)::int                              as janela_7d_fechada,
    count(*) filter (where not fechou_7d)::int                          as aguardando_7d,
    count(*) filter (where fechou_7d and primeiro_depois is not null)::int as projeto_7d,
    count(*) filter (where fechou_7d and primeiro_depois is not null
                       and primeiro_depois <= ultimo + interval '1 hour')::int
                                                                        as projeto_7d_mesma_visita,
    count(*) filter (where fechou_14d)::int                             as janela_14d_fechada,
    count(*) filter (where fechou_14d and proj_dep_14)::int             as projeto_14d,
    count(*) filter (where fechou_7d and proj_antes_7)::int             as projeto_antes_7d,
    count(*) filter (where fechou_7d and invisivel)::int                as sem_rastro_de_site,
    round((percentile_cont(0.5) within group (
             order by extract(epoch from (primeiro_depois - ultimo)) / 3600.0)
           filter (where fechou_7d and primeiro_depois is not null))::numeric, 3)
                                                                        as mediana_horas_ate_o_projeto,
    max(ultimo)                                                         as ultimo_envio
  from marcada group by kind
)
select json_build_object(
  'dias', greatest(coalesce(dias, 90), 1),
  'gerado_em', now(),
  'por_tipo', coalesce((select json_agg(t order by t.volume_total desc) from (
      select v.kind, v.volume_total,
        coalesce(a.enviados, 0)           as enviados,
        coalesce(a.pessoas, 0)            as pessoas,
        coalesce(a.janela_7d_fechada, 0)  as janela_7d_fechada,
        coalesce(a.aguardando_7d, 0)      as aguardando_7d,
        coalesce(a.projeto_7d, 0)               as projeto_7d,
        coalesce(a.projeto_7d_mesma_visita, 0)  as projeto_7d_mesma_visita,
        coalesce(a.janela_14d_fechada, 0) as janela_14d_fechada,
        coalesce(a.projeto_14d, 0)        as projeto_14d,
        coalesce(a.projeto_antes_7d, 0)   as projeto_antes_7d,
        coalesce(a.sem_rastro_de_site, 0) as sem_rastro_de_site,
        a.mediana_horas_ate_o_projeto,
        a.ultimo_envio
      from vol v left join agg a on a.kind = v.kind) t), '[]'::json)
);
$$;

revoke all on function admin_email_retorno(integer, text) from public, anon, authenticated;
grant execute on function admin_email_retorno(integer, text) to service_role;

-- 97% do trabalho da RPC era ler projeto e jogar fora. A tabela é pequena hoje
-- (374 linhas), mas o custo é o PRODUTO de dois volumes que crescem juntos:
-- e-mails na janela × projetos por pessoa.
create index if not exists projects_user_email_lower_created_idx
  on projects (lower(user_email), created_at);
