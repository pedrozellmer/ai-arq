# -*- coding: utf-8 -*-
"""A rota de revisão não pode responder "ok" sem ter gravado.

🚨 24/08/2026 (2ª validação): `/api/items/{job}/review/{item}` devolvia
200 {"status":"ok"} mesmo quando NADA tinha sido escrito. O insert de
`item_reviews` tinha o retorno descartado, e o PATCH de `project_items` e o
DELETE do reject viviam cada um num `try/except` que só escrevia num log mudo.

Dois estragos medidos:
  (a) a aprovação em massa contava "12 itens salvos" com zero escritas — o
      conserto que eu fiz em 23/08 no revisao.html confere `r.ok`, que era
      sempre verdadeiro. Consertei o lado errado.
  (b) o cliente via "Salvo", fechava o navegador, e a correção existia só em
      `item_reviews`. Na releitura, a fusão lê o PAI, encontra o número velho
      do motor e o entrega escrito "Mantido da sua revisão anterior".

Este arquivo confere pelo CÓDIGO (a rota exige Supabase e sessão pra rodar de
verdade), com controle positivo que reprova a forma antiga.
"""
import io
import os
import re

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _rota():
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index('@app.post("/api/items/{job_id}/review/{item_id}")')
    j = src.index("\n@app.", i + 10)
    return src[i:j]


def test_o_retorno_do_insert_nao_e_jogado_fora():
    corpo = _rota()
    assert re.search(r"_rev_gravou\s*=\s*_supabase_insert\(\"item_reviews\"", corpo), (
        "o insert de item_reviews voltou a ter o retorno descartado")


def test_o_patch_e_o_delete_marcam_se_pegaram():
    corpo = _rota()
    assert corpo.count("_tentou_escrever = True") >= 2, (
        "PATCH e DELETE precisam marcar que TENTARAM escrever")
    assert corpo.count("_escreveu = True") >= 2, (
        "PATCH e DELETE precisam marcar que a escrita CONFIRMOU")


def test_a_rota_falha_quando_a_escrita_nao_pegou():
    corpo = _rota()
    assert "if _tentou_escrever and not _escreveu:" in corpo, (
        "a rota voltou a responder ok sem conferir se gravou")
    assert "502" in corpo and "NÃO foi gravada" in corpo, (
        "a mensagem tem que dizer ao cliente que a alteração NÃO foi salva")


def test_nao_da_502_quando_nao_havia_nada_pra_escrever():
    """Controle negativo: uma edição sem campo válido não tenta escrever, e não
    pode virar erro na cara do cliente."""
    corpo = _rota()
    i = corpo.index("if _tentou_escrever and not _escreveu:")
    # a condição depende de TER tentado — não de `action`
    assert "action in (" not in corpo[i:i + 120], (
        "a condição voltou a ser por `action`: uma edição sem mudança nenhuma "
        "passaria a devolver 502 à toa")


def test_o_controle_prova_que_a_forma_antiga_seria_reprovada():
    """A forma antiga era um `return` incondicional. Se ela voltar, os dois
    testes acima falham — aqui a gente prova que o padrão é detectável."""
    antigo = '    return {"status": "ok", "action": action}\n'
    corpo = _rota()
    assert antigo not in corpo, (
        "o return incondicional voltou: a rota responde ok sem saber se gravou")
    # e o guarda pega mesmo? (controle positivo sobre um texto sintético)
    assert "if _tentou_escrever and not _escreveu:" not in antigo
