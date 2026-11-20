-- ✅ APLICADA em 20/11/2026 (migração `sinapi_composicao_novo`), com ok do Pedro
-- ("Atualizar com avaliação antes" + "Botão no admin que baixa da Caixa").
--
-- Tabela À PARTE pro SINAPI do mês, enchida pela rota POST /api/admin/sinapi-do-mes
-- (sinapi_do_mes.py). O motor NÃO lê daqui: a busca segue em `sinapi_composicao`
-- (03/2026). Serve pra comparar as duas antes de trocar.
-- Mesmas colunas e o mesmo índice de busca da tabela do motor (o de trigramas,
-- pra uma cópia da busca poder rodar nela na comparação).
-- Sem política de RLS: só a chave de serviço (servidor) lê e grava.
CREATE TABLE IF NOT EXISTS public.sinapi_composicao_novo (
  codigo      text PRIMARY KEY,
  descricao   text,
  unidade     text,
  familia_id  integer,
  sync_month  date,
  created_at  timestamptz DEFAULT now()
);
ALTER TABLE public.sinapi_composicao_novo ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.sinapi_composicao_novo FROM anon, authenticated;
CREATE INDEX IF NOT EXISTS idx_sinapi_novo_desc_trgm
  ON public.sinapi_composicao_novo USING gin (lower(public.imm_unaccent(descricao)) gin_trgm_ops);
