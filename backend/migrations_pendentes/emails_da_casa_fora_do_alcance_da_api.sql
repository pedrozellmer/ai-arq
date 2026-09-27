-- ✅ APLICADA em 27/09/2026 (migração `emails_da_casa_fora_do_alcance_da_api`), com ok do Pedro.
-- Ensaiada antes num DO-block que se desfaz: authenticated perde o EXECUTE da lista; a view projetos_de_cliente
-- segue lendo as mesmas 240 linhas; e-mail de fora continua contando como cliente.
--
-- Auditoria SI (27/09/2026): qualquer conta logada chamava /rest/v1/rpc/emails_da_casa e levava a lista de e-mails
-- da casa (inclusive de quem não é funcionário). A permissão existia só porque a view projetos_de_cliente
-- (security_invoker, lida pelo admin com o login dele) chama eh_projeto_de_cliente, que chamava a lista com a
-- permissão de quem lê. Agora eh_projeto_de_cliente roda com a permissão do dono (já tinha search_path fixo) e a
-- lista deixa de ser executável por quem entra pela API. admin_email_retorno e admin_list_all_signups já eram
-- SECURITY DEFINER e seguem lendo a lista.
-- 🪤 Nada de DROP (quebraria quem depende): só ALTER e REVOKE.

alter function public.eh_projeto_de_cliente(boolean, text) security definer;
revoke execute on function public.emails_da_casa() from public, anon, authenticated;
