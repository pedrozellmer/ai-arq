-- ✅ APLICADA em 27/09/2026 ~22h15 BRT (migração `admin_list_all_signups_com_origem`, versão 20260928011634) —
-- item 5 do plano de telemetria de 27/09/2026, liberado pelo Pedro ("depois segue com o item 5"). Conferido logo
-- depois: 191 linhas (as mesmas), 142 com `src`, SECURITY DEFINER, executa só authenticated e service_role.
--
-- 🩸 O 1º toque técnico da conta (`src`, `src_ref`, `src_campaign`, `src_landing` em auth.users.raw_user_meta_data)
-- estava em 84 de 84 fichas de 30/08 a 27/09 — e a lista do admin não devolvia. "Declarou × chegou por" (Dashboard)
-- e "Chegou por" (ficha do cliente) passam a ler daqui.
--
-- 🪤 Mudar o RETURNS TABLE exige DROP + CREATE (CREATE OR REPLACE não troca o tipo de retorno) — e o DROP leva as
-- permissões junto, e o CREATE dá EXECUTE a PUBLIC por padrão. Por isso, na MESMA transação: DROP, CREATE, e as
-- permissões de hoje de volta (só authenticated e service_role; a função confere o admin por dentro).
-- 🪤 Ninguém depende dela no banco (corpo plpgsql não é dependência); quem chama é o admin.html e o admin-usuario.html.
-- 🔑 Troca TEXTUAL sobre a definição que está no banco, com contagem (para inteira se o trecho não estiver lá
-- exatamente uma vez) — e o e-mail de admin que mora no corpo da função não precisa ser escrito aqui (repo público).
-- As 4 colunas novas vão no FIM: quem lê por nome não muda nada.

do $mig$
declare
  d text;
  n int;
  v_ret constant text := 'conta_da_casa boolean)';
  n_ret constant text := 'conta_da_casa boolean, src text, src_ref text, src_campaign text, src_landing text)';
  v_sel constant text := '(lower(au.email::text) = any(public.emails_da_casa())) as conta_da_casa';
  n_sel constant text := '(lower(au.email::text) = any(public.emails_da_casa())) as conta_da_casa,'
    || ' (au.raw_user_meta_data ->> ''src'')::text as src,'
    || ' (au.raw_user_meta_data ->> ''src_ref'')::text as src_ref,'
    || ' (au.raw_user_meta_data ->> ''src_campaign'')::text as src_campaign,'
    || ' (au.raw_user_meta_data ->> ''src_landing'')::text as src_landing';
begin
  d := pg_get_functiondef('public.admin_list_all_signups()'::regprocedure);
  n := (length(d) - length(replace(d, v_ret, ''))) / length(v_ret);
  if n <> 1 then raise exception 'admin_list_all_signups: retorno achado % vezes', n; end if;
  n := (length(d) - length(replace(d, v_sel, ''))) / length(v_sel);
  if n <> 1 then raise exception 'admin_list_all_signups: última coluna achada % vezes', n; end if;
  drop function public.admin_list_all_signups();
  execute replace(replace(d, v_ret, n_ret), v_sel, n_sel);
  revoke execute on function public.admin_list_all_signups() from public, anon;
  grant execute on function public.admin_list_all_signups() to authenticated, service_role;
end
$mig$;
