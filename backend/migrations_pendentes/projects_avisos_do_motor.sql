-- ✅ APLICADA em 28/09/2026 (migração `projects_avisos_do_motor`), com ok do Pedro.
--
-- Estudo de leitura, achado 25: os avisos do motor só ACUMULAVAM. Desde 04/09 o fim de
-- cada passada grava `_avisos_com(job_id, project_data.warnings)`, que lê o que está no
-- banco e acrescenta. Quando o projeto passa de novo (anexo, nova tentativa, reprocesso),
-- o aviso da passada anterior fica: 9 dos 10 projetos de cliente com mais de uma passada
-- mostravam aviso velho, inclusive "Nenhuma linha deste projeto foi MEDIDA" ao lado de
-- centenas de itens medidos.
--
-- Esta coluna guarda QUAIS avisos o motor gravou na última passada. A passada seguinte,
-- só no caminho de sucesso, tira esses e põe os dela. Aviso gravado por outra rota
-- (prancha perdida da retomada, arquivo extenso do anexo, área informada) não está na
-- lista e fica. A subtração é pela lista gravada, nunca por prefixo de texto.
--
-- 🪤 A RPC `update_project_status` NÃO conhece esta coluna (aceita 7 campos e descarta o
-- resto calada): quem grava é `_projeto_patch`, depois do `warnings`.
-- 🔑 Nula = projeto de antes do conserto: nada a tirar, comportamento de antes.
-- Sem mudança de permissão: herda as da tabela, como `warnings`.

alter table public.projects add column if not exists avisos_do_motor jsonb;

comment on column public.projects.avisos_do_motor is
  'Avisos que o MOTOR gravou na última passada (a próxima passada com sucesso tira estes do warnings e põe os dela). Nulo = anterior a 28/09/2026.';
