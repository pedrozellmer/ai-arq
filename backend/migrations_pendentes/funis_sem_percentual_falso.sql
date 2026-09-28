-- ✅ APLICADA em 27/09/2026 ~21h40 BRT (migração `funis_sem_percentual_falso`, versão 20260928004109) — item 3 do
-- plano de telemetria de 27/09/2026, liberado pelo Pedro ("depois segue com o item 3"). Conferido logo depois: site
-- home_nav 28 / cadastro_nav 26 / cadastro_pela_home_nav 19 (campos antigos iguais); revisão 134/93/41/28/25;
-- SECURITY DEFINER + search_path mantidos; conta logada comum segue SEM acesso ao funil do site.
--
-- 🩸 Auditoria de telemetria (27/09): dois funis do painel mostravam porcentagem entre conjuntos que não se contêm.
--
--   · admin_funil_do_site — "abriram o cadastro: 24 · ~86% da home", mas só 4 dos 24 tinham passado pela home. A
--     pessoa é o user_id quando logada e o navegador (cid) quando não: quem abre a home deslogado e volta do login
--     (Google/Microsoft devolvem pro cadastro.html) vira DUAS pessoas. Todo evento, logado ou não, leva o cid
--     (medido 27/09: 1.149 de 1.149 eventos logados com cid). Novos campos, por NAVEGADOR: home_nav, cadastro_nav e
--     cadastro_pela_home_nav (abriu o cadastro E a home na janela) — subconjunto da home por construção. Medido,
--     7 dias: 28 navegadores na home, 26 no cadastro, 19 nos dois (68%, não ~86%). Os campos antigos continuam (a
--     régua de pessoa segue sendo a do admin_origem_visitas); a régua do DONO é a de hoje (Pedro, 27/09: "mantém a
--     régua de hoje") — mesmo corpo da usage_events_le_pelo_user_id.sql, só com os três campos a mais.
--
--   · funil_revisao — a etapa 5 fazia count(*) no join com revision_feedback: 57 LINHAS que eram 26 PROJETOS (até
--     7 por projeto), e saía maior que as etapas 3 e 4 (a barra dizia 33% quando era 15%). Agora toda etapa conta
--     projeto distinto, só projeto-raiz (reprocesso não é projeto novo — a mesma régua do item 2) e só os criados
--     desde 03/08, quando a abertura da revisão passou a ser medida (os 33 de antes tinham 0 abertura por falta de
--     medida, não de uso). Medido: 172/96/43/29/57 → 134/93/41/28/25.
--     🪤 A assinatura NÃO muda (CREATE OR REPLACE não troca argumento, e DROP quebra quem chama): o piso de 03/08
--     fica escrito, e `p_excluir_emails` segue aceito.
--
-- 🪤 CREATE OR REPLACE mantém dono e GRANT, mas NÃO SECURITY DEFINER nem search_path — os dois vêm escritos.

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
  --
  -- 🩸 27/09/2026 (item 3 da telemetria): a pessoa MUDA de chave no meio do
  -- caminho — deslogada na home (cid), logada no cadastro depois do login
  -- (user_id) — e "cadastro ÷ home" dividia conjuntos que não se contêm (24 no
  -- cadastro, só 4 passaram pela home). O NAVEGADOR (cid) não muda: todo evento
  -- leva o cid, logado ou não. Os campos *_nav contam navegador, e
  -- cadastro_pela_home_nav é a interseção — a única base honesta pra "% da home".
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
  ),
  nav as (
    select u.meta->>'cid' as nav, u.event
    from usage_events u
    where u.created_at >= now() - (greatest(1, least(coalesce(p_dias,7), 120)) || ' days')::interval
      and not exists (select 1 from dono d where d.uid = u.user_id)
      and nullif(u.meta->>'cid','') is not null
  )
  select jsonb_build_object(
    'janela_dias', greatest(1, least(coalesce(p_dias,7), 120)),
    'home',     (select count(distinct pessoa) from base where event = 'view_landing'),
    'cadastro', (select count(distinct pessoa) from base where event = 'view_cadastro'),
    'conta',    (select count(distinct pessoa) from base where event = 'signup_done'),
    -- 🔑 "subiu projeto" NÃO é subconjunto de "criou conta": cliente antigo sobe
    -- sem se cadastrar de novo. Por isso ele viaja aqui, mas a tela não põe
    -- porcentagem em cima dele — seria a mesma mentira, com outro número.
    'projeto',  (select count(distinct pessoa) from base where event = 'start_project'),
    'home_nav',     (select count(distinct nav) from nav where event = 'view_landing'),
    'cadastro_nav', (select count(distinct nav) from nav where event = 'view_cadastro'),
    'cadastro_pela_home_nav', (select count(*) from (
        select nav from nav where event = 'view_cadastro'
        intersect
        select nav from nav where event = 'view_landing') x)
  );
$function$;

CREATE OR REPLACE FUNCTION public.funil_revisao(p_excluir_emails text[] DEFAULT '{}'::text[])
 RETURNS TABLE(etapa text, ordem integer, projetos bigint, clientes bigint)
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
  with base as (
    -- 🔑 02/09/2026: quem é cliente decide a view projetos_de_cliente. Antes
    -- filtrava `projects` por profiles.email e contava 48 avaliações como
    -- projeto de cliente (avaliação tem user_id 'eval', sem perfil).
    -- p_excluir_emails continua aceito (compatibilidade), mas o backend manda {}.
    -- 🩸 27/09/2026 (item 3 da telemetria): só projeto-RAIZ (reprocesso não é
    -- projeto novo) e só os criados desde 03/08, quando a abertura da revisão
    -- passou a ser medida — antes disso "tela aberta" dava 0 por falta de medida.
    select p.job_id, p.user_id
    from public.projetos_de_cliente p
    where p.status = 'done'
      and p.archived_at is null
      and p.parent_job_id is null
      and p.created_at >= timestamptz '2026-08-03 00:00:00-03'
      and not (lower(p.user_email) = any(coalesce(p_excluir_emails, '{}'::text[])))
  ),
  acoes as (
    select job_id,
           count(*) filter (where action in ('edit','reject')) as correcoes
    from item_reviews group by job_id
  )
  -- 🩸 27/09/2026: toda etapa conta PROJETO distinto. A 5 fazia count(*) no join
  -- com revision_feedback (várias planilhas por projeto): 57 linhas eram 26
  -- projetos, e a etapa saía maior que as anteriores.
  select 'projeto concluido'::text, 1,
         count(distinct b.job_id)::bigint, count(distinct b.user_id)::bigint from base b
  union all
  select 'tela de revisao aberta', 2,
         count(distinct b.job_id)::bigint, count(distinct b.user_id)::bigint
    from base b join projects p on p.job_id = b.job_id
   where coalesce(p.revisao_aberturas, 0) > 0
  union all
  select 'alguma acao na revisao', 3,
         count(distinct b.job_id)::bigint, count(distinct b.user_id)::bigint
    from base b join acoes a on a.job_id = b.job_id
  union all
  select 'correcao de verdade (edit/reject)', 4,
         count(distinct b.job_id)::bigint, count(distinct b.user_id)::bigint
    from base b join acoes a on a.job_id = b.job_id
   where a.correcoes > 0
  union all
  select 'planilha revisada enviada', 5,
         count(distinct b.job_id)::bigint, count(distinct b.user_id)::bigint
    from base b join revision_feedback rf on rf.job_id = b.job_id
  order by 2;
$function$;
