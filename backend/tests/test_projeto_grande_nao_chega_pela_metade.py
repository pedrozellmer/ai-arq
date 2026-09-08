# -*- coding: utf-8 -*-
"""Projeto de mais de mil itens não pode chegar na tela pela metade.

🩸 08/09/2026, 11:50 — CHEGOU O PRIMEIRO PROJETO DE 1.044 ITENS.

Um executivo de acessibilidade, 30+ pranchas, 82 minutos de processamento. O
segundo maior projeto do acervo tem **307** itens — o teto real triplicou de
uma vez e passou do corte de 1000 do PostgREST.

O conserto de 25/08 paginou as leituras de TABELA (`_supa_rest_tudo`) e abriu
uma exceção explícita pra leitura de UM projeto, com a justificativa escrita:

    "limitada pelo maior projeto do acervo (307 itens)"

A exceção não estava errada. Estava **datada**. E venceu hoje.

📏 Remedido na produção no mesmo minuto, com a anon key:
`limit=500` → 500 · `limit=1500` → 1000 · `limit=3000` → 1000. Tudo HTTP 200.

## O que quebrava

| | |
|---|---|
| o `.xlsx` | **certo** — a geração usa os itens em memória |
| `/api/items/{job}` (tela de revisão) | mostrava **1.000 de 1.044**, calada |
| `_assinatura_atual` (regra dura nº7) | assinava 1.000 contra planilha de 1.044 |

A segunda é a pior: assinatura que nunca bate = *"planilha desatualizada"* pra
sempre, num projeto em dia. É o aviso que ensina o cliente a ignorar aviso.

🔑 O paginador CONFERE O TOTAL contra o banco em vez de confiar na ordenação.
A RPC ordena por `(sort_order, item_num)` e eu medi que o par é único nos 225
projetos do acervo — mas foi exatamente uma premissa medida que acabou de
vencer, então ela não pode ser a única defesa.
"""
import io
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

_MAIN = os.path.join(_BACKEND, "main.py")
_CORTE = 1000          # o db-max-rows do PostgREST, medido em produção


def _fatia():
    """Executa só o paginador — importar main.py conecta em Supabase."""
    src = io.open(_MAIN, encoding="utf-8").read()
    ini = "def _itens_do_projeto_completos"
    fim = "\ndef _aplicar_admin_local"
    assert src.count(ini) == 1, "a âncora do paginador mudou"
    i = src.index(ini)
    ns = {
        "__name__": "itens_ns",
        "SUPABASE_URL": "https://exemplo.invalido",
        "SUPABASE_KEY": "k",
        "SUPABASE_SERVICE_ROLE_KEY": "s",
        "_SUPA_TETO_POR_PAGINA": _CORTE,
        "_contar_itens_no_banco": lambda j: None,
        "_log_error": lambda *a, **k: None,
        "print": lambda *a, **k: None,
    }
    exec(compile(src[i:src.index(fim, i)], "main_itens_slice", "exec"), ns)
    return ns


class _SupaDeMentira(object):
    """Um PostgREST que CORTA EM 1000 como o de verdade — e devolve 200.

    🪤 Sem o corte, o teste não reproduz nada: uma página só devolveria os 1.044
    e o paginador pareceria certo mesmo sem paginar.
    """

    def __init__(self, total, corte=_CORTE):
        self.total = total
        self.corte = corte
        self.paginas = []          # (limit, offset) de cada chamada

    def __call__(self, req, timeout=None):
        import json as _j
        import urllib.parse as _up
        q = _up.parse_qs(_up.urlparse(req.full_url).query)
        limit = int(q.get("limit", ["25"])[0])
        offset = int(q.get("offset", ["0"])[0])
        self.paginas.append((limit, offset))
        devolve = min(limit, self.corte, max(0, self.total - offset))
        corpo = _j.dumps([{"id": offset + k, "sort_order": offset + k,
                           "item_num": offset + k} for k in range(devolve)])

        class _R(object):
            def read(self_inner):
                return corpo.encode("utf-8")
        return _R()


def _monta(total, contagem=None):
    ns = _fatia()
    fake = _SupaDeMentira(total)
    ns["_ur"].urlopen = fake                      # o módulo importado dentro
    if contagem is not None:
        ns["_contar_itens_no_banco"] = lambda j: contagem
    return ns, fake


# ══════════════════════════════════════════════════════════════════════════
#  O defeito de 08/09
# ══════════════════════════════════════════════════════════════════════════
def test_projeto_de_1044_itens_chega_INTEIRO():
    ns = _fatia()
    fake = _SupaDeMentira(1044)
    import urllib.request as _ur
    _antigo = _ur.urlopen
    _ur.urlopen = fake
    try:
        ns["_contar_itens_no_banco"] = lambda j: 1044
        linhas, ok = ns["_itens_do_projeto_completos"]("job-grande")
    finally:
        _ur.urlopen = _antigo

    assert len(linhas) == 1044, (
        "chegaram %d de 1044 — é o corte de 1000 de volta" % len(linhas))
    assert ok is True
    assert len(fake.paginas) == 2, (
        "esperava 2 páginas (1000 + 44), foram %d: %s"
        % (len(fake.paginas), fake.paginas))
    assert fake.paginas[1][1] == 1000, "a 2ª página tem que começar no 1000"


def test_CONTROLE_o_supabase_de_mentira_CORTA_mesmo():
    """🧪 Se o duble não cortasse, todos os testes daqui passariam sem provar
    nada — foi por isso que o defeito real durou até um projeto grande chegar."""
    fake = _SupaDeMentira(1044)

    class _Req(object):
        full_url = "https://x/rest/v1/rpc/list_project_items?limit=5000&offset=0"
    import json as _j
    assert len(_j.loads(fake(_Req()).read())) == 1000, (
        "o duble devolveu mais de 1000 — ele não imita o PostgREST")


# ══════════════════════════════════════════════════════════════════════════
#  Falha FECHADA — meia lista nunca se apresenta como lista inteira
# ══════════════════════════════════════════════════════════════════════════
def test_quando_o_total_NAO_bate_a_leitura_se_declara_incompleta():
    """A ordenação da RPC é única HOJE nos 225 projetos. Se um dia empatar,
    paginar pula linha — e é a conferência de total que segura."""
    ns = _fatia()
    fake = _SupaDeMentira(1044)
    import urllib.request as _ur
    _antigo = _ur.urlopen
    _ur.urlopen = fake
    try:
        ns["_contar_itens_no_banco"] = lambda j: 1050    # banco diz 1050
        linhas, ok = ns["_itens_do_projeto_completos"]("job-x")
    finally:
        _ur.urlopen = _antigo

    assert ok is False, "li 1044 mas o banco tem 1050 e me declarei completo"
    assert len(linhas) == 1044, "as linhas lidas continuam voltando"


def test_projeto_pequeno_continua_numa_pagina_so():
    """CONTROLE POSITIVO: paginar não pode custar chamada extra em 99% dos
    projetos — o 2º maior do acervo tem 307 itens."""
    ns = _fatia()
    fake = _SupaDeMentira(307)
    import urllib.request as _ur
    _antigo = _ur.urlopen
    _ur.urlopen = fake
    try:
        ns["_contar_itens_no_banco"] = lambda j: 307
        linhas, ok = ns["_itens_do_projeto_completos"]("job-pequeno")
    finally:
        _ur.urlopen = _antigo

    assert len(linhas) == 307 and ok is True
    assert len(fake.paginas) == 1, "projeto pequeno não pode virar 2 chamadas"


def test_projeto_vazio_nao_vira_erro():
    ns = _fatia()
    fake = _SupaDeMentira(0)
    import urllib.request as _ur
    _antigo = _ur.urlopen
    _ur.urlopen = fake
    try:
        ns["_contar_itens_no_banco"] = lambda j: 0
        linhas, ok = ns["_itens_do_projeto_completos"]("job-vazio")
    finally:
        _ur.urlopen = _antigo
    assert linhas == [] and ok is True


# ══════════════════════════════════════════════════════════════════════════
#  As duas leituras que quebravam TÊM que usar o paginador
# ══════════════════════════════════════════════════════════════════════════
def test_as_duas_leituras_de_itens_paginam():
    """🪤 Guarda de fonte, e assumido: prova que não sobrou chamada crua da RPC.
    Sem ele, alguém remonta o `urlopen` inline e os testes de cima seguem
    verdes falando de uma função que ninguém chama."""
    src = io.open(_MAIN, encoding="utf-8").read()
    assert src.count("_itens_do_projeto_completos(") >= 3, (
        "esperado: a definição + /api/items + a assinatura — achei %d"
        % src.count("_itens_do_projeto_completos("))

    import ast
    cruas = []
    for no in ast.walk(ast.parse(src)):
        if isinstance(no, ast.JoinedStr):
            lit = "".join(p.value for p in no.values
                          if isinstance(p, ast.Constant) and isinstance(p.value, str))
            if "rpc/list_project_items" in lit and "limit=" not in lit:
                cruas.append(getattr(no, "lineno", "?"))
    assert not cruas, (
        "chamada da RPC de itens SEM limit/offset (volta o corte em 1000): %s"
        % cruas)
