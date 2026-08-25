# -*- coding: utf-8 -*-
"""O PostgREST corta em 1000 linhas e NÃO avisa.

🚨 25/08/2026. O Pedro clicou na simulação do caderno de acabamentos e a tela
disse **"50 de 1000 itens ganhariam especificação"**. A rota pedia `limit=9000`
e o acervo tem **7718** itens: ela leu 13% e apresentou o pedaço como o todo.

Provado com curl na anon key, numa tabela pública, no dia:

    ?limit=1500 → 1000 linhas
    ?limit=3000 → 1000 linhas
    ?limit=9000 → 1000 linhas

Não é o nosso `limit` que manda: é o `db-max-rows` do PostgREST. Pedir mais que
mil é escrever uma intenção que o servidor ignora — e ninguém no caminho vê.

A varredura do dia achou a mesma mentira em outros três lugares, e um deles
era um KPI que o Pedro lê:

  • `spec-backfill`   — 1000 de 7718 itens (13%)
  • `selo-historico`  — 1000 de 1611 confirmados (62%)
  • funil da revisão  — 1000 de 6107 não-confirmados (16%)

🪤 Mesma família do `/api/track` de 22/08, que descartava calado tudo fora de 13
nomes e mediu o funil errado por 7 semanas. Número que chega inteiro na tela sem
avisar que veio pela metade é pior que erro: é erro com cara de medição.
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _corpo import corpo_de, fonte  # noqa: E402

TETO = 1000


# ══════════════════════════════════════════════════════════════════════════
#  O que roda de verdade: a função de paginar, executada
# ══════════════════════════════════════════════════════════════════════════
def _carrega_paginador(respostas):
    """Executa `_supa_rest_tudo` de verdade, com um Supabase de mentira.

    `respostas` é a lista do que cada página devolve: (status, linhas)."""
    chamadas = []

    def _fake(metodo, path, params=None, timeout=15):
        chamadas.append(dict(params or {}))
        i = len(chamadas) - 1
        return respostas[i] if i < len(respostas) else (200, [])

    ns = {"_supa_rest_service": _fake, "_SUPA_TETO_POR_PAGINA": TETO}
    exec(corpo_de("_supa_rest_tudo"), ns)
    return ns["_supa_rest_tudo"], chamadas


def test_le_todas_as_paginas_ate_acabar():
    """1000 + 1000 + 300 = 2300 — e não 1000."""
    paginar, chamadas = _carrega_paginador([
        (200, [{"id": i} for i in range(TETO)]),
        (200, [{"id": i} for i in range(TETO)]),
        (200, [{"id": i} for i in range(300)]),
    ])
    st, linhas = paginar("project_items")
    assert st == 200
    assert len(linhas) == 2300, "leu %d linhas" % len(linhas)
    assert len(chamadas) == 3
    assert [c["offset"] for c in chamadas] == ["0", "1000", "2000"]


def test_controle_positivo_sem_paginar_daria_1000():
    """🧪 A prova de que o teste acima mede algo: a leitura ANTIGA — uma
    chamada só — devolveria exatamente os 1000 que enganaram o Pedro."""
    paginar, _ = _carrega_paginador([(200, [{"id": i} for i in range(TETO)]),
                                     (200, []), (200, [])])
    _, linhas = paginar("project_items")
    assert len(linhas) == TETO, (
        "com uma página cheia seguida de vazia, o total tem que ser 1000 — "
        "se der outra coisa o meu Supabase de mentira não imita o real")


def test_uma_pagina_so_nao_faz_chamada_a_toa():
    """Tabela pequena continua custando 1 request, como antes."""
    paginar, chamadas = _carrega_paginador([(200, [{"id": 1}, {"id": 2}])])
    st, linhas = paginar("cronogramas")
    assert (st, len(linhas), len(chamadas)) == (200, 2, 1)


def test_falha_no_meio_NAO_devolve_meia_tabela_como_se_fosse_inteira():
    """🚨 O ponto todo: se a página 2 morre, quem chama TEM que saber.

    Devolver (200, primeiras mil) seria recriar o bug com outra roupa."""
    paginar, _ = _carrega_paginador([
        (200, [{"id": i} for i in range(TETO)]),
        (502, None),
    ])
    st, linhas = paginar("project_items")
    assert st == 502, "engoliu a falha da página 2 e devolveu %s" % st
    assert len(linhas) == TETO      # devolve o que tinha, mas com o status ruim


def test_sempre_manda_order_senao_a_paginacao_pula_linha():
    """🪤 Sem `order`, o Postgres não promete a mesma sequência entre páginas:
    paginar sem ordenar repete linha e perde linha."""
    paginar, chamadas = _carrega_paginador([(200, [{"id": 1}])])
    paginar("project_items")
    assert chamadas[0].get("order"), "foi sem ORDER: a paginação não é confiável"


def test_order_de_quem_chama_manda():
    paginar, chamadas = _carrega_paginador([(200, [{"id": 1}])])
    paginar("usage_events", params={"order": "created_at.desc,id.asc"})
    assert chamadas[0]["order"] == "created_at.desc,id.asc"


def test_nunca_pede_mais_que_o_teto_por_pagina():
    paginar, chamadas = _carrega_paginador([(200, [{"id": 1}])])
    paginar("project_items", pagina=9000)
    assert int(chamadas[0]["limit"]) <= TETO, (
        "pediu %s numa página — o servidor ia cortar em %d e não avisar"
        % (chamadas[0]["limit"], TETO))


# ══════════════════════════════════════════════════════════════════════════
#  O guarda estático: ninguém volta a escrever um limite que é mentira
# ══════════════════════════════════════════════════════════════════════════
def _limites_mentirosos(src):
    return [int(m.group(1)) for m in re.finditer(r'"limit":\s*"(\d+)"', src)
            if int(m.group(1)) > TETO]


def test_nenhum_limite_acima_de_mil_no_backend():
    """Pedir 5000 e receber 1000 sem saber é o defeito inteiro."""
    achados = _limites_mentirosos(fonte("main.py"))
    assert not achados, (
        "estes `limit` são maiores que o teto de %d do PostgREST e vão ser "
        "cortados em silêncio: %s. Use `_supa_rest_tudo`." % (TETO, achados))


def test_controle_positivo_o_guarda_estatico_PEGA_o_codigo_antigo():
    """🧪 Guarda que não reprova nada é decoração. Este é o código real que
    estava na rota até hoje de manhã."""
    antigo = '''    _st, itens = _supa_rest_service(
        "GET", "project_items",
        params={"select": "id,description", "limit": "9000"})'''
    assert _limites_mentirosos(antigo) == [9000]


def _sem_docstrings(src):
    """Apaga as docstrings, preservando a numeração das linhas.

    🪤 Três vezes esta casa escreveu guarda que acusava a própria explicação:
    a docstring CITA a coisa proibida pra contar por que ela saiu, o teste lê
    a citação e me empurra a apagar a documentação pra calar o alarme."""
    import ast
    linhas = src.splitlines()
    try:
        arvore = ast.parse(src)
    except SyntaxError:
        return src
    for no in ast.walk(arvore):
        corpo = getattr(no, "body", None)
        if not isinstance(corpo, list) or not corpo:
            continue
        p = corpo[0]
        if not (isinstance(p, ast.Expr) and isinstance(getattr(p, "value", None), ast.Constant)
                and isinstance(p.value.value, str)):
            continue
        for n in range(p.lineno - 1, (p.end_lineno or p.lineno)):
            if 0 <= n < len(linhas):
                linhas[n] = ""
    return "\n".join(l for l in linhas if not l.strip().startswith("#"))


def _urls_cruas_acima_do_teto(src):
    """Ocorrências de `limit=N` (N>1000) montadas na mão dentro de f-string.

    Aceita UMA exceção, e ela é uma regra, não uma lista: leitura de UM projeto
    (`job_id=eq.`) é limitada pelo maior projeto do acervo — 307 itens hoje —
    e não pelo tamanho da base."""
    vivo = _sem_docstrings(src)
    fora = []
    for m in re.finditer(r"[?&]limit=(\d+)", vivo):
        if int(m.group(1)) <= TETO:
            continue
        if "job_id=eq." in vivo[max(0, m.start() - 300):m.start()]:
            continue
        fora.append((int(m.group(1)), vivo[max(0, m.start() - 90):m.start() + 12]))
    return fora


def test_nenhuma_URL_crua_global_com_limite_acima_de_mil():
    """🪤 Três leituras da esteira de e-mail montavam a URL na mão, com
    `&limit=5000` dentro de uma f-string — o guarda de params não as via.

    Cortadas em mil, elas mandariam "termine seu cadastro" pra quem já
    terminou e boas-vindas repetido pra quem já recebeu."""
    fora = _urls_cruas_acima_do_teto(fonte("main.py"))
    assert not fora, "URL crua global pedindo mais que %d: %s" % (TETO, fora)


def test_controle_positivo_o_guarda_de_URL_crua_PEGA_a_esteira_antiga():
    """🧪 O código real da esteira de e-mail até hoje de manhã."""
    antigo = 'qw = (f"{S}/rest/v1/email_sent_log?select=email&kind=eq.boas_vindas&limit=5000")'
    assert _urls_cruas_acima_do_teto(antigo), "o guarda não vê a URL montada à mão"


def test_controle_negativo_leitura_de_UM_projeto_pode_passar():
    """E não pode reclamar da leitura por projeto, senão vira ruído."""
    porjob = 'f"{S}/rest/v1/project_items?job_id=eq.{job_id}&select=x&limit=5000"'
    assert not _urls_cruas_acima_do_teto(porjob)


def test_controle_o_guarda_NAO_acusa_a_propria_docstring():
    """🪤 A docstring de `_supa_rest_tudo` cita `?limit=9000` pra explicar o
    bug. Guarda que tropeça nisso me ensina a apagar a explicação."""
    achados_brutos = [int(m.group(1)) for m in
                      re.finditer(r"[?&]limit=(\d+)", fonte("main.py"))
                      if int(m.group(1)) > TETO]
    assert 9000 in achados_brutos, (
        "a docstring que explica o bug sumiu do main.py — sem ela este "
        "controle não prova nada")
    assert not [n for n, _ in _urls_cruas_acima_do_teto(fonte("main.py")) if n == 9000]


@pytest.mark.parametrize("rota,tabela", [
    ("/api/admin/spec-backfill", "project_items"),
    ("/api/admin/selo-historico", "project_items"),
])
def test_as_rotas_que_mentiam_agora_paginam(rota, tabela):
    src = fonte("main.py")
    i = src.index('"%s"' % rota)
    trecho = src[i:i + 4000]
    assert "_supa_rest_tudo" in trecho, (
        "%s voltou a ler %s de uma vez só" % (rota, tabela))


def test_o_funil_da_revisao_pagina():
    """Era o pior dos três: 1000 de 6107, num número que o Pedro lê como
    verdade do produto."""
    src = fonte("main.py")
    i = src.index('"confidence": "neq.confirmado"')
    janela = src[max(0, i - 400):i + 200]
    assert "_supa_rest_tudo" in janela, "a leitura dos estimados voltou a cortar em mil"
