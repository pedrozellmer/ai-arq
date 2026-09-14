# -*- coding: utf-8 -*-
"""Os avisos das travas da honestidade de área são DIAGNÓSTICO, não erro.

🩸 14/09/2026 — o painel "Avisos do motor no registro" (admin → Operação) mostra
as 40 linhas mais recentes do `error_log` que a RPC `admin_ops` NÃO classificou
como diagnóstico. Medido na RPC, rodando: 26 dessas 40 linhas eram bookkeeping
do motor — 13 dos três avisos das travas de área e 13 do `cobranca:regua`. É o
mesmo defeito de 23/08 (20 de 40), voltando por outra porta.

🔑 A porta: `severity="warning"`. A lista `_STAGES_DIAGNOSTICO` só rebaixava
quem chamou SEM dizer nada, e estes avisos pedem "warning" explícito — então
pôr o nome na lista não tinha efeito nenhum. Prova viva no banco:
`cobranca:regua` está na lista desde 06/09 e mesmo assim ocupava 13 linhas do
painel de erros.

📐 CRITÉRIO (o que separa bookkeeping de erro que alguém tem que olhar):
    é DIAGNÓSTICO a linha que nasce de um caminho que o motor considera normal
    — a condição já foi tratada, o job seguiu, e ninguém faz nada por causa
    daquela linha; o volume acompanha o número de jobs.
    é ERRO a linha que pede ação: o job parou, entregou errado, ou ela é a
    única pista de uma falha que ninguém mais vai contar.
Os avisos das travas de área são o primeiro caso: a trava fez o trabalho dela e
a linha da planilha ficou vazia DE PROPÓSITO.

🪤 A família não é uma lista minha — sai do próprio código: são os `_log_error`
que vivem no bloco do `process_job` que conta o que `_apply_area_honesty`
deixou nos atributos `ultimo_*`. Aviso novo ali dentro entra sozinho no guarda,
que foi exatamente o que me faltou em 11/09, quando criei o
`motor:geometria-de-outra-prancha` e ele nasceu fora da lista.
"""
import ast
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

_MAIN_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")


def _familia_do_codigo():
    """Stages que o motor grava no bloco de avisos da honestidade de área.

    A região é auto-delimitada: começa na PRIMEIRA leitura de um
    `getattr(_apply_area_honesty, "ultimo_*")` e termina na última. Não há
    número de linha decorado aqui — se o bloco andar ou crescer, a região anda
    junto.
    """
    arv = ast.parse(io.open(_MAIN_PY, encoding="utf-8").read())
    leituras = [
        d.lineno for d in ast.walk(arv)
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "getattr"
        and len(d.args) >= 2 and isinstance(d.args[0], ast.Name)
        and d.args[0].id == "_apply_area_honesty"
        and isinstance(d.args[1], ast.Constant)
        and str(d.args[1].value).startswith("ultimo_")
    ]
    if not leituras:
        return [], (0, 0)
    ini, fim = min(leituras), max(leituras)
    achados = []
    for d in ast.walk(arv):
        if (isinstance(d, ast.Call) and isinstance(d.func, ast.Name)
                and d.func.id == "_log_error" and d.args
                and isinstance(d.args[0], ast.Constant)
                and ini <= d.lineno <= fim):
            pedido = next((k.value.value for k in d.keywords
                           if k.arg == "severity" and isinstance(k.value, ast.Constant)), None)
            achados.append((str(d.args[0].value), pedido, d.lineno))
    return achados, (ini, fim)


def _severity_gravada(stage, **kw):
    """Chama o `_log_error` DE VERDADE e devolve o que chegaria no banco."""
    caixa = []
    antigo = main._supabase_insert
    main._supabase_insert = lambda tabela, dados: caixa.append((tabela, dados))
    try:
        main._log_error(stage, "guarda 14/09", "job-de-mentira", **kw)
    finally:
        main._supabase_insert = antigo
    assert caixa, "o _log_error não gravou nada para o stage %r" % stage
    tabela, dados = caixa[0]
    assert tabela == "error_log", tabela
    return dados.get("severity")


def test_a_familia_da_honestidade_de_area_chega_no_banco_como_DIAGNOSTICO():
    """O guarda CHAMA o `_log_error` com cada stage que o motor grava ali."""
    familia, (ini, fim) = _familia_do_codigo()
    # 🪤 Sem este piso o guarda passaria CEGO: região vazia, nenhum stage, tudo
    # verde. Cinco é o que existe hoje — quatro travas + o resumo.
    assert len(familia) >= 5, (
        "só achei %d aviso(s) no bloco da honestidade de área (linhas %d-%d) — "
        "o guarda perdeu a região que devia cobrir" % (len(familia), ini, fim))
    assert any(s == "motor:honestidade-area" for s, _, _ in familia), (
        "o resumo `motor:honestidade-area` sumiu da região — a âncora do bloco mudou")

    for stage, pedido, linha in familia:
        gravou = _severity_gravada(stage, **({"severity": pedido} if pedido else {}))
        assert gravou == "info", (
            "main.py:%d grava %r como %r e essa linha vai parar no painel "
            "\"Avisos do motor no registro\", entre as falhas de verdade. "
            "É bookkeeping da trava de área: ou entra em _STAGES_DIAGNOSTICO, "
            "ou sai do bloco da honestidade." % (linha, stage, gravou))


def test_CONTROLE_falha_de_verdade_continua_ERRO():
    """Prova que o guarda sabe reprovar: nem tudo vira 'info'."""
    assert _severity_gravada("dxf:extract-falhou") == "error"
    assert _severity_gravada("dwg:convert-fail", severity="warning") == "warning"
    assert _severity_gravada("process_job") == "error"


def test_CONTROLE_escalada_explicita_passa_por_cima_da_lista():
    """🪤 24/08: `critical` num stage de diagnóstico TEM que aparecer — foi o
    caso da planilha que não foi refeita com as correções do cliente."""
    assert _severity_gravada("motor:refaz-planilha-admin", severity="critical") == "critical"
    assert _severity_gravada("motor:teto-por-prancha", severity="critical") == "critical"
