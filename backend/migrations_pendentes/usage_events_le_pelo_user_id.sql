-- ⏳ PENDENTE — NÃO aplicar sem o ok do Pedro. Ensaiada em 27/09/2026 num DO-block que se desfaz (ver o fim).
--
-- LGPD (auditoria SI de 27/09/2026, minimização): `usage_events` guardava o e-mail junto com o `user_id` em todo
-- evento de conta logada. Medido em 27/09: 5.427 eventos; 4.879 com e-mail, TODOS com `user_id`; 0 com conta
-- apagada; 0 com e-mail diferente do da conta atual. O e-mail era cópia — e dado pessoal a mais.
--
-- Estas 4 RPCs do admin liam `usage_events.user_email`. Passam a achar a pessoa pela CONTA (user_id × auth.users),
-- que dá a mesma resposta hoje e continua dando depois que a coluna for zerada
-- (`usage_events_zera_email_antigo.sql`, que é do Pedro rodar, DEPOIS desta).
--
--   admin_email_retorno   "sem rastro no site": existia evento com aquele e-mail → existe evento de conta com ele
--   admin_filhotes        visitas do cliente depois de liberar: tira o dono pela conta do evento
--   admin_funil_do_site   tira o dono pela conta do evento
--   admin_origem_visitas  idem
--   (usage_events_por_nome não lê e-mail — fica como está.)
--
-- 🔑 A régua do DONO é a mesma de antes: todo e-mail que contém o nome dele (pega os +apelidos). Antes o nome
-- vinha digitado em cada função; agora vem do 1º item de emails_da_casa(), o único lugar onde e-mail da casa é
-- digitado. Conferido no ensaio: o padrão derivado é IDÊNTICO ao que as 3 funções usavam.
-- 🪤 Trocar pela lista inteira de emails_da_casa() mudaria o número (+40 eventos de outra conta da casa, 27/09):
-- é outra decisão, não entra aqui.
-- 🪤 CREATE OR REPLACE, nunca DROP (quebraria quem depende). CREATE OR REPLACE mantém dono e permissões, mas NÃO
-- mantém SECURITY DEFINER nem o search_path — por isso os dois vêm escritos em cada uma.

CREATE OR REPLACE FUNCTION public.admin_email_retorno(dias integer DEFAULT 90, excluir text DEFAULT NULL::text)
 RETURNS json
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
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
), rastro as (
  -- 🔒 27/09/2026 (LGPD): quem tem rastro no site sai pela CONTA do evento (user_id), não pelo e-mail gravado
  -- nele — a coluna vai ser zerada. Medido: todo evento com e-mail tinha o id e o e-mail batia com o da conta.
  select distinct lower(a.email) as email
  from usage_events u
  join auth.users a on a.id::text = u.user_id
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
    not exists (select 1 from rastro r
                 where r.email = p.email)                        as invisivel
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
        coalesce(a.enviados, 0)                 as enviados,
        coalesce(a.pessoas, 0)                  as pessoas,
        coalesce(a.janela_7d_fechada, 0)        as janela_7d_fechada,
        coalesce(a.aguardando_7d, 0)            as aguardando_7d,
        coalesce(a.projeto_7d, 0)               as projeto_7d,
        coalesce(a.projeto_7d_mesma_visita, 0)  as projeto_7d_mesma_visita,
        coalesce(a.janela_14d_fechada, 0)       as janela_14d_fechada,
        coalesce(a.projeto_14d, 0)              as projeto_14d,
        coalesce(a.projeto_antes_7d, 0)         as projeto_antes_7d,
        coalesce(a.sem_rastro_de_site, 0)       as sem_rastro_de_site,
        a.mediana_horas_ate_o_projeto,
        a.ultimo_envio
      from vol v left join agg a on a.kind = v.kind) t), '[]'::json)
);
$function$;

CREATE OR REPLACE FUNCTION public.admin_filhotes()
 RETURNS jsonb
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
  with cont as (
    select job_id, count(*) as itens,
           count(*) filter (where confidence = 'confirmado') as medidos,
           count(*) filter (where coalesce(quantity,0) = 0)  as zerados
    from project_items group by job_id
  ),
  f as (
    select p.job_id, p.parent_job_id, p.status, p.user_id, p.created_at, p.total_area
    from projects p
    where coalesce(p.is_eval,false) = true and p.parent_job_id is not null
    order by p.created_at desc limit 60
  ),
  atos as (
    select job_id, created_at,
           -- 🪤 'desarquivado' ANTES de 'arquivado' não é necessário (o
           -- `ilike 'arquivado%'` exige COMEÇAR com a palavra), mas fica
           -- explícito pra quem ler não precisar deduzir.
           case when message ilike 'revogado%'     then 'revogado'
                when message ilike 'desarquivado%' then 'desarquivado'
                when message ilike 'arquivado%'    then 'arquivado'
                else 'liberado' end as ato
    from error_log
    where job_id is not null
      and ((stage = 'admin:filhote' and (message ilike 'liberado%' or message ilike 'revogado%'
                                      or message ilike 'arquivado%' or message ilike 'desarquivado%'))
        or (stage = 'filhote:auto'  and message ilike 'liberado%'))
  ),
  lib as (
    select job_id,
           max(created_at) filter (where ato = 'liberado') as liberado_em,
           max(created_at) filter (where ato = 'revogado') as revogado_em,
           max(created_at) filter (where ato = 'arquivado') as arquivado_em
    from atos group by job_id
  ),
  ult as (
    select distinct on (job_id) job_id, ato as ato_atual, created_at as ato_em
    from atos order by job_id, created_at desc
  ),
  mail_exato as (
    select job_id, min(created_at) as email_em
    from error_log
    where stage = 'admin:filhote-email' and job_id is not null
      and message ilike '%enviado%' and message not ilike '%falhou%'
    group by job_id
  ),
  cand as (
    select e.id as email_id, e.sent_at, l.job_id
    from lib l
    join projects fp on fp.job_id = l.job_id
    join projects pp on pp.job_id = fp.parent_job_id
    join email_sent_log e on lower(e.email) = lower(pp.user_email)
                         and e.kind = 'leitura_nova'
                         and e.sent_at between l.liberado_em - interval '2 minutes'
                                          and l.liberado_em + interval '10 minutes'
    where l.liberado_em is not null
  ),
  cand_unico as (
    select min(job_id) as job_id, min(sent_at) as email_em
    from cand group by email_id having count(distinct job_id) = 1
  ),
  mail as (
    select job_id, min(email_em) as email_em
    from (select job_id, email_em from mail_exato
          union all
          select job_id, email_em from cand_unico) z
    group by job_id
  ),
  dono_nome as (
    -- 🔒 27/09/2026: a régua do dono é a MESMA de antes (todo e-mail que contém o nome dele — pega os
    -- +apelidos), mas o nome vem do 1º item de emails_da_casa(), o único lugar onde e-mail da casa é digitado.
    select '%' || split_part((public.emails_da_casa())[1], '@', 1) || '%' as padrao
  ),
  dono as (
    -- No evento a régua vale pela CONTA (user_id): o e-mail gravado no evento vai ser zerado (LGPD).
    select a.id::text as uid from auth.users a, dono_nome n where a.email ilike n.padrao
  ),
  volta_nav as (
    select u.job_id,
           count(*) as visitas,
           max(u.created_at) as ultima_visita,
           count(*) filter (where u.event = 'download_xlsx') as downloads
    from usage_events u
    join projects fp2 on fp2.job_id = u.job_id
    join projects pp2 on pp2.job_id = fp2.parent_job_id
    where u.job_id is not null and u.job_id <> ''
      and u.user_id = pp2.user_id
      and not exists (select 1 from dono d where d.uid = u.user_id)
    group by u.job_id
  ),
  volta_srv as (
    select e.job_id,
           count(*) as downloads,
           max(e.created_at) as ultima
    from error_log e
    join projects fp3 on fp3.job_id = e.job_id
    join projects pp3 on pp3.job_id = fp3.parent_job_id
    where e.stage = 'entrega:download'
      and (e.message like '% por=cliente'
           or (e.message not like '% por=%'
               and coalesce(pp3.user_email,'') not ilike (select padrao from dono_nome)))
    group by e.job_id
  ),
  volta as (
    select coalesce(n.job_id, s.job_id) as job_id,
           coalesce(n.visitas, 0) as visitas,
           greatest(n.ultima_visita, s.ultima) as ultima_visita,
           greatest(coalesce(n.downloads, 0), coalesce(s.downloads, 0)) as downloads
    from volta_nav n
    full join volta_srv s on s.job_id = n.job_id
  )
  select coalesce(jsonb_agg(to_jsonb(x) order by x.criado desc), '[]'::jsonb)
  from (
    select f.job_id, f.parent_job_id, f.status, f.created_at as criado,
           coalesce(pai.project_name,'(sem nome)') as projeto,
           coalesce(pai.user_email,'(sem e-mail)') as cliente,
           (f.user_id is not null and f.user_id = pai.user_id) as liberado,
           lib.liberado_em,
           lib.revogado_em,
           coalesce(ult.ato_atual, case when f.user_id = pai.user_id then 'liberado' end) as ato_atual,
           (lib.liberado_em is not null) as ja_liberado,
           -- 🔑 ARQUIVADO é o ATO ATUAL, não "já foi arquivado um dia":
           -- desarquivar tem que devolver o filhote pra fila de decisão.
           (coalesce(ult.ato_atual,'') = 'arquivado') as arquivado,
           lib.arquivado_em,
           mail.email_em,
           coalesce(v.visitas, 0)   as visitas_cliente,
           v.ultima_visita,
           coalesce(v.downloads, 0) as downloads_cliente,
           (lib.liberado_em is not null and v.ultima_visita is not null
            and v.ultima_visita >= lib.liberado_em) as voltou_apos_liberar,
           jsonb_build_object('itens', coalesce(ca.itens,0),
                              'medidos', coalesce(ca.medidos,0),
                              'zerados', coalesce(ca.zerados,0)) as antes,
           jsonb_build_object('itens', coalesce(cd.itens,0),
                              'medidos', coalesce(cd.medidos,0),
                              'zerados', coalesce(cd.zerados,0)) as depois,
           pai.total_area as area_antes, f.total_area as area_depois,
           (coalesce(cd.medidos,0) > coalesce(ca.medidos,0)
            or (coalesce(cd.medidos,0) = coalesce(ca.medidos,0)
                and coalesce(cd.itens,0) > coalesce(ca.itens,0))) as melhorou,
           (coalesce(cd.medidos,0) < coalesce(ca.medidos,0))      as mediu_menos,
           (select count(*) from item_reviews r where r.job_id = f.parent_job_id)
             as revisoes_no_original
    from f
    join projects pai on pai.job_id = f.parent_job_id
    left join cont ca on ca.job_id = f.parent_job_id
    left join cont cd on cd.job_id = f.job_id
    left join lib on lib.job_id = f.job_id
    left join ult on ult.job_id = f.job_id
    left join mail on mail.job_id = f.job_id
    left join volta v on v.job_id = f.job_id
  ) x;
$function$;

CREATE OR REPLACE FUNCTION public.admin_funil_do_site(p_dias integer DEFAULT 7)
 RETURNS jsonb
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
  -- O caminho até o projeto, medido com UMA RÉGUA SÓ.
  --
  -- 🚨 18/09/2026: o painel dividia CONTAS DO BANCO por ENDEREÇOS DO CLOUDFLARE
  -- e exibia "criaram conta: 18 · 180% de quem abriu o cadastro". Numerador e
  -- denominador vinham de sistemas diferentes, contando populações diferentes:
  -- o banco conta toda conta criada; o Cloudflare conta endereços de IP que
  -- bateram na página, só das 12 páginas do topo e só de quem ele viu. Isso não
  -- é taxa de conversão. Num funil, cada etapa tem que ser subconjunto da
  -- anterior — e 180% é a prova aritmética de que não era.
  --
  -- 🪤 pessoa = user_id (logado) senão meta->>'cid' (navegador). user_id de
  -- anônimo chega como '' e não NULL: sem o nullif, TODO anônimo vira uma
  -- pessoa só. Medido 02/09: 36 pessoas com a chave errada, 83 com a certa.
  -- É a MESMA régua de admin_origem_visitas, de propósito: duas cópias da mesma
  -- régua é o defeito que a casa já pagou duas vezes (as duas réguas do retry).
  --
  -- 🪤 E exclui o dono: sem isso o Pedro entra no próprio funil toda vez que
  -- abre o site pra olhar o painel.
  -- 🔒 27/09/2026 (LGPD): o dono sai pela CONTA do evento (user_id), não pelo
  -- e-mail gravado nele, que vai ser zerado. A régua é a mesma de antes (todo
  -- e-mail que contém o nome dele — pega os +apelidos); o nome vem do 1º item
  -- de emails_da_casa(), o único lugar onde e-mail da casa é digitado.
  with dono as (
    select a.id::text as uid
    from auth.users a
    where a.email ilike '%' || split_part((public.emails_da_casa())[1], '@', 1) || '%'
  ),
  base as (
    select coalesce(nullif(u.user_id,''), u.meta->>'cid') as pessoa, u.event
    from usage_events u
    where u.created_at >= now() - (greatest(1, least(coalesce(p_dias,7), 120)) || ' days')::interval
      and not exists (select 1 from dono d where d.uid = u.user_id)
      and coalesce(nullif(u.user_id,''), u.meta->>'cid') is not null
  )
  select jsonb_build_object(
    'janela_dias', greatest(1, least(coalesce(p_dias,7), 120)),
    'home',     (select count(distinct pessoa) from base where event = 'view_landing'),
    'cadastro', (select count(distinct pessoa) from base where event = 'view_cadastro'),
    'conta',    (select count(distinct pessoa) from base where event = 'signup_done'),
    -- 🔑 "subiu projeto" NÃO é subconjunto de "criou conta": cliente antigo sobe
    -- sem se cadastrar de novo. Por isso ele viaja aqui, mas a tela não põe
    -- porcentagem em cima dele — seria a mesma mentira, com outro número.
    'projeto',  (select count(distinct pessoa) from base where event = 'start_project')
  );
$function$;

CREATE OR REPLACE FUNCTION public.admin_origem_visitas(p_dias integer DEFAULT 30)
 RETURNS jsonb
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
  -- De onde veio quem ACEITOU o cookie de analytics nos últimos p_dias.
  -- 🪤 pessoa = user_id (logado) senão meta->>'cid' (navegador). user_id de
  -- anônimo é '' (não NULL): sem o nullif, todo anônimo vira UMA pessoa.
  -- Medido 02/09: 36 pessoas com a chave errada, 83 com a certa.
  -- 🔒 27/09/2026 (LGPD): o dono sai pela CONTA do evento (user_id), não pelo
  -- e-mail gravado nele, que vai ser zerado. Mesma régua e mesma fonte do nome
  -- que admin_funil_do_site.
  with dono as (
    select a.id::text as uid
    from auth.users a
    where a.email ilike '%' || split_part((public.emails_da_casa())[1], '@', 1) || '%'
  ),
  base as (
    select coalesce(nullif(u.user_id,''), u.meta->>'cid') as pessoa,
           nullif(u.meta->>'src','') as origem,
           u.path
    from usage_events u
    where u.created_at >= now() - (greatest(1, least(coalesce(p_dias,30), 120)) || ' days')::interval
      and not exists (select 1 from dono d where d.uid = u.user_id)
      and coalesce(nullif(u.user_id,''), u.meta->>'cid') is not null
  ),
  por_origem as (
    select coalesce(origem,'(sem origem)') as origem, count(distinct pessoa) as pessoas
    from base group by 1
  )
  select jsonb_build_object(
    'janela_dias', greatest(1, least(coalesce(p_dias,30), 120)),
    'pessoas', (select count(distinct pessoa) from base),
    'pessoas_com_origem', (select count(distinct pessoa) from base where origem is not null),
    'pessoas_na_home', (select count(distinct pessoa) from base where path in ('/','/index.html')),
    'origens', (select coalesce(jsonb_agg(jsonb_build_object('origem', origem, 'pessoas', pessoas) order by pessoas desc, origem), '[]'::jsonb) from por_origem)
  );
$function$;
