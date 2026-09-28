-- ✅ APLICADA em 27/09/2026 (migração `sinapi_teto_de_resultados_e_bucket_logos_so_imagem`), com ok do Pedro
-- ("faz os itens baixos"). Conferido depois: as buscas típicas com 60 resultados devolvem EXATAMENTE a mesma lista
-- (md5 igual antes/depois); pedir 1.000 devolve 100; anon/authenticated seguem executando; bucket com os 4 tipos e 2 MB.
--
-- Auditoria SI (27/09/2026), itens baixos.
-- 1) As duas buscas do catálogo SINAPI que qualquer visitante pode chamar não tinham teto de resultados
--    (pedir 1.000 devolvia 1.000). O motor pede no máximo 60 (candidates_for, limit=60): teto de 100.
--    Corpo idêntico ao anterior; muda só o LIMIT. CREATE OR REPLACE mantém as permissões.
CREATE OR REPLACE FUNCTION public.sinapi_candidates(p_query text, p_limit integer DEFAULT 10)
 RETURNS TABLE(codigo text, descricao text, unidade text, familia_id integer, similarity real)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
  v_q text;
BEGIN
  PERFORM set_config('pg_trgm.word_similarity_threshold', '0.25', true);
  v_q := lower(public.imm_unaccent(p_query));
  RETURN QUERY
  SELECT c.codigo, c.descricao, c.unidade, c.familia_id,
         GREATEST(
           similarity(v_q, lower(public.imm_unaccent(c.descricao))),
           word_similarity(v_q, lower(public.imm_unaccent(c.descricao)))
         )::real AS sim
  FROM sinapi_composicao c
  WHERE lower(public.imm_unaccent(c.descricao)) %> v_q
    AND c.descricao !~ '^\('
  ORDER BY sim DESC
  LIMIT least(greatest(coalesce(p_limit, 10), 1), 100);
END;
$function$;

CREATE OR REPLACE FUNCTION public.search_sinapi(p_query text, p_limit integer DEFAULT 5)
 RETURNS TABLE(codigo text, descricao text, unidade text, familia_id integer, similarity real)
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
  v_first_word text;
  v_query_norm text;
BEGIN
  v_query_norm := lower(public.imm_unaccent(p_query));

  v_first_word := regexp_replace(
    regexp_replace(v_query_norm, '^(de|para|em|o|a|os|as|um|uma|do|da|no|na)\s+', '', 'i'),
    '^(\S+).*', '\1'
  );

  RETURN QUERY
  SELECT c.codigo, c.descricao, c.unidade, c.familia_id,
         (
           GREATEST(
             similarity(lower(public.imm_unaccent(c.descricao)), v_query_norm),
             word_similarity(v_query_norm, lower(public.imm_unaccent(c.descricao)))
           )
           + CASE WHEN length(v_first_word) >= 3
                    AND lower(public.imm_unaccent(c.descricao)) LIKE v_first_word || '%'
                  THEN 0.30 ELSE 0 END
           + CASE WHEN length(v_first_word) >= 3
                    AND lower(public.imm_unaccent(c.descricao)) LIKE '%' || v_first_word || '%'
                    AND NOT (lower(public.imm_unaccent(c.descricao)) LIKE v_first_word || '%')
                  THEN 0.08 ELSE 0 END
           + CASE WHEN length(c.descricao) BETWEEN 15 AND 120 THEN 0.03 ELSE 0 END
         )::real AS sim
  FROM sinapi_composicao c
  WHERE (
         lower(public.imm_unaccent(c.descricao)) %> v_query_norm
         OR lower(public.imm_unaccent(c.descricao)) LIKE '%' || v_query_norm || '%'
        )
    AND c.descricao !~ '^\('
  ORDER BY sim DESC
  LIMIT least(greatest(coalesce(p_limit, 5), 1), 100);
END;
$function$;

-- 2) O bucket público `logos` aceitava qualquer tipo e tamanho (hoje vazio). Fica só imagem — os formatos que a
--    tela oferece (PNG, JPG, SVG) e WEBP — até 2 MB.
UPDATE storage.buckets
   SET allowed_mime_types = ARRAY['image/png', 'image/jpeg', 'image/svg+xml', 'image/webp'],
       file_size_limit = 2097152
 WHERE id = 'logos';
