-- ✅ APLICADA em 27/09/2026 ~21h10 BRT (migração `regua_unica_da_casa_nos_contadores`, versão 20260928001244) —
-- item 2 do plano de telemetria de 27/09/2026, liberado pelo Pedro ("depois segue com o item 2").
-- Conferido logo depois, no banco: retenção 16/53/81, resto da qualidade com o mesmo md5, cobrança set 40 / jul 13.
--
-- 🩸 Auditoria de telemetria (27/09): os contadores não concordavam sobre quem é cliente. Aqui, os dois do banco que
-- só leem `projects`:
--   · admin_qualidade_semanal — a retenção contava o REPROCESSO do cliente como "voltou outro dia". Passa a contar
--     só projeto-raiz: voltaram_outro_dia 17 → 16, dois_ou_mais_projetos 57 → 53, so_um_projeto 77 → 81;
--     'clientes_voltaram' por semana também só com raiz (soma igual hoje: 10).
--   · admin_regua_cobranca — projeto da casa saía como entrega cobrável, e esse nunca seria cobrado: setembro
--     41 → 40 cobráveis, julho 15 → 13, junho 7 → 6; em abril 9 das 10 "entregas" eram nossas.
-- Medido antes, 27/09 ~19h40 BRT, e ensaiado num bloco que se desfaz (raise no fim): os números acima saíram iguais,
-- e o resto de admin_qualidade_semanal (semanas, formatos, CAD, plano B) com resposta byte a byte igual (md5).
--
-- 🚧 FORA daqui, DE PROPÓSITO:
--   · admin_funil_do_site, admin_origem_visitas e admin_filhotes: nos EVENTOS só o dono sai da conta. Pedro,
--     27/09, perguntado sobre tirar a outra conta da casa (funil 7d 'cadastro' 25 → 24, +40 eventos): "mantém a
--     régua de hoje". As três foram reescritas por `usage_events_le_pelo_user_id.sql` (LGPD) com essa régua.
--   · admin_list_all_signups: a lista dela é de QUEM PODE chamar, não um filtro de contagem.
--   · admin_custo_ia_resumo: custo por entrega — projeto da casa gasta IA de verdade, e o divisor tem que continuar
--     igual ao do custo fixo do painel (`_projetos_para_custo_30d`).
--
-- 🔑 Troca TEXTUAL sobre a definição que está no banco, com contagem: se o trecho não estiver lá exatamente o
-- número de vezes esperado, a migração inteira para (nada de "aplicou pela metade" calado).
-- 🪤 Nada de DROP (quebraria quem depende e as permissões): CREATE OR REPLACE via pg_get_functiondef, que traz
-- SECURITY DEFINER e search_path junto.

do $mig$
declare
  d text;
  n int;
  q_base_v constant text := 'select p.job_id, p.status, p.created_at, p.completed_at, p.user_id,';
  q_base_n constant text := 'select p.job_id, p.parent_job_id, p.status, p.created_at, p.completed_at, p.user_id,';
  q_ret_v  constant text := 'from j group by cliente) t';
  q_ret_n  constant text := 'from j where parent_job_id is null group by cliente) t';
  q_vol_v  constant text := 'filter (where prim.sem1 < g.semana)  as clientes_voltaram';
  q_vol_n  constant text := 'filter (where prim.sem1 < g.semana and j.parent_job_id is null) as clientes_voltaram';
  r_v constant text := E'    and parent_job_id is null\n    and created_at >= date_trunc(''month'', now())';
  r_n constant text := E'    and parent_job_id is null\n    and not (lower(coalesce(user_email,'''')) = any(public.emails_da_casa()))\n    and created_at >= date_trunc(''month'', now())';
begin
  -- 1) qualidade semanal: retenção e "voltaram" só com projeto-raiz
  d := pg_get_functiondef('public.admin_qualidade_semanal()'::regprocedure);
  n := (length(d) - length(replace(d, q_base_v, ''))) / length(q_base_v);
  if n <> 1 then raise exception 'admin_qualidade_semanal: base achada % vezes', n; end if;
  n := (length(d) - length(replace(d, q_ret_v, ''))) / length(q_ret_v);
  if n <> 1 then raise exception 'admin_qualidade_semanal: retencao achada % vezes', n; end if;
  n := (length(d) - length(replace(d, q_vol_v, ''))) / length(q_vol_v);
  if n <> 1 then raise exception 'admin_qualidade_semanal: clientes_voltaram achado % vezes', n; end if;
  execute replace(replace(replace(d, q_base_v, q_base_n), q_ret_v, q_ret_n), q_vol_v, q_vol_n);

  -- 2) régua de cobrança: projeto da casa nunca seria cobrado
  d := pg_get_functiondef('public.admin_regua_cobranca(integer)'::regprocedure);
  n := (length(d) - length(replace(d, r_v, ''))) / length(r_v);
  if n <> 1 then raise exception 'admin_regua_cobranca: trecho achado % vezes', n; end if;
  execute replace(d, r_v, r_n);
end
$mig$;
