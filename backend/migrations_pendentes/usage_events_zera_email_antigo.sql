-- ✅ EXECUTADO em 27/09/2026 ~21:06 (horário de Brasília), a pedido do Pedro ("faz aí pra mim"). As 3 travas passaram.
-- Depois: 5.468 eventos, 0 com e-mail, e todo user_id acha a conta. Os painéis deram os mesmos números
-- ("sem rastro no site" em 90 dias = 187; seria 504 se algo ainda lesse o e-mail).
-- 21:10: os dois opcionais do fim também rodaram, com ok do Pedro: o índice por e-mail foi apagado (migração
-- `usage_events_sem_indice_de_email`) e o vacuum rodou (0 linhas mortas).
-- NÃO rodar de novo: não sobrou nada para zerar. A trava 3 só serviu para a primeira vez.
--
-- Zera o e-mail dos eventos antigos de `usage_events` (LGPD, minimização). Zerar dado é decisão do Pedro.
--
-- ORDEM (cada passo depende do anterior):
--   1. `usage_events_le_pelo_user_id.sql` APLICADA — as 4 RPCs do admin acham a pessoa pela conta (user_id).
--   2. O backend que para de gravar o e-mail (POST /api/track) e de lê-lo (Atividade, ficha do usuário) NO AR.
--   3. Pelo menos UM evento de conta logada DEPOIS do deploy (a trava 3 abaixo precisa dele pra provar o passo 2).
--   4. Rodar este arquivo inteiro no SQL Editor do Supabase.
--
-- O bloco é uma transação só: se qualquer trava falhar, NADA muda e a mensagem diz qual.
-- Medido em 27/09: 4.879 linhas com e-mail. Na hora de rodar serão mais — cresce até o passo 2 ir ao ar.
-- 🪤 Os backups do Supabase guardam a versão antiga das linhas até vencerem — zerar aqui não apaga o que já está
-- no backup. E as versões mortas das linhas somem da tabela no próximo VACUUM (automático; ou o comando no fim).

do $zera$
declare
  esperado jsonb := '{"admin_email_retorno":  "c54b62ff379e2cc85b6fc38710d52f55",
                      "admin_filhotes":       "b95d9398df1f3231f93f0201e26508cc",
                      "admin_funil_do_site":  "787b4391a0a5a6a2a14cd9d5c100b67d",
                      "admin_origem_visitas": "82737aada4b5ae469d66264a52787038"}';
  f text;
  achado text;
  n_sem_id int;
  ultimo_logado text;
  n int;
  sobra int;
begin
  -- Trava 1: as 4 RPCs são as da migração (md5 do corpo). Se não bater, alguém mexeu nelas depois: conferir se
  -- a versão nova ainda lê pelo user_id antes de atualizar o md5 aqui.
  for f in select jsonb_object_keys(esperado) loop
    select md5(prosrc) into achado from pg_proc
     where pronamespace = 'public'::regnamespace and proname = f;
    if achado is distinct from esperado->>f then
      raise exception 'PARE (trava 1): public.% não é a versão que lê pelo user_id (md5 %). Aplique a migração antes.', f, achado;
    end if;
  end loop;

  -- Trava 2: evento com e-mail e SEM user_id perderia o dono de vez. Em 27/09 eram 0.
  select count(*) into n_sem_id from public.usage_events
   where coalesce(user_email, '') <> '' and coalesce(user_id, '') = '';
  if n_sem_id > 0 then
    raise exception 'PARE (trava 2): % eventos têm e-mail e não têm user_id — zerar apagaria o dono deles.', n_sem_id;
  end if;

  -- Trava 3: o backend novo está no ar — o evento de conta logada mais recente chegou SEM e-mail.
  select user_email into ultimo_logado from public.usage_events
   where coalesce(user_id, '') <> '' order by created_at desc limit 1;
  if coalesce(ultimo_logado, '') <> '' then
    raise exception 'PARE (trava 3): o último evento de conta logada ainda chegou COM e-mail — o backend novo não está no ar (ou ninguém logado usou o site desde o deploy).';
  end if;

  update public.usage_events set user_email = '' where coalesce(user_email, '') <> '';
  get diagnostics n = row_count;

  select count(*) into sobra from public.usage_events where coalesce(user_email, '') <> '';
  if sobra > 0 then
    raise exception 'PARE: sobraram % linhas com e-mail — nada foi gravado.', sobra;
  end if;

  raise notice 'OK: % eventos tiveram o e-mail zerado; 0 com e-mail na tabela.', n;
end
$zera$;

-- Opcionais, DEPOIS do bloco acima, também do Pedro (✅ os dois rodaram em 27/09 às 21:10):
-- O índice por e-mail passa a indexar só texto vazio.
--   drop index if exists public.idx_usage_events_email;
-- Tira da tabela, já, as versões antigas das linhas (fora de transação; o autovacuum faria sozinho mais tarde).
--   vacuum public.usage_events;
