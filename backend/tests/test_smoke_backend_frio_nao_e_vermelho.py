# -*- coding: utf-8 -*-
"""Backend reiniciando não pode virar build vermelho.

🩸 02/09/2026. O commit `2f848ce` tocou `backend/main.py`, o Render reiniciou, e
o smoke rodou logo em seguida. O passo que abre `projeto.html` esperava
`networkidle` — a rede ficar quieta por meio segundo — e falhava DURO no
timeout. Os fetches da página ficaram pendurados no backend que subia, a rede
nunca calou, e 30 s depois o build ficou vermelho com:

    projeto.html?job_id=0de29633 não carregou em 30s

Medida na mão no mesmo minuto, a página respondia em **0,45 s**, HTTP 200. E o
commit seguinte (`e6635b5`), com o MESMO `projeto.html`, passou verde.

📏 MEDIDO: 1 falha em 40 runs do smoke, e foi exatamente essa.

🪤 A incoerência estava escrita duas telas acima, no mesmo arquivo: o passo do
dashboard JÁ tolera o mesmo atraso — o comentário dele diz "fetch ao backend
pode demorar se o Render estava dormindo" — e segue em frente. Na página do
projeto, a mesma causa era fatal.

🔑 `networkidle` é contrato errado pra uma página que consulta o backend. A
prova de que ela carregou não é a rede calar: é o botão "Baixar XLSX" ficar
visível e clicável. E o passo 3 já cobra exatamente isso, com timeout próprio e
mensagem própria. Aqui basta ABRIR a página.

🚨 Por que isso importa mais do que um build vermelho: alarme que é sempre
falso é alarme que se aprende a ignorar — e este arquivo nasceu do mesmo
princípio que o `test_smoke_nao_mente_a_causa`, que existe porque uma mensagem
de falha errada mandou a gente investigar o backend quando o problema era uma
vista escondida no HTML.
"""
import io
import os

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_E2E = os.path.join(_RAIZ, ".github", "scripts", "smoke_test_e2e.py")


def _fonte():
    return io.open(_E2E, encoding="utf-8").read()


def _trecho_da_abertura(n=900):
    src = _fonte()
    return src[src.index("page.goto(href,"):][:n]


def test_o_projeto_html_nao_exige_rede_quieta_pra_APROVAR():
    """🩸 A linha que pintou o CI de vermelho sem defeito nenhum."""
    assert 'wait_until="domcontentloaded"' in _trecho_da_abertura(200), (
        "voltou a exigir a rede quieta pra aprovar a abertura do projeto — "
        "backend reiniciando vira build vermelho de novo")


def test_a_folga_pra_pagina_se_acalmar_CONTINUA_existindo():
    """🧪 CONTROLE: tirar o `networkidle` do caminho de aprovação não pode
    virar 'não espera nada'. A folga continua lá — só não derruba o build."""
    depois = _trecho_da_abertura()
    assert 'wait_for_load_state("networkidle"' in depois, (
        "sumiu a folga pra página se acalmar antes de procurar o botão")


def test_a_folga_NAO_reprova():
    """O ponto do conserto: esperar sim, reprovar não."""
    depois = _trecho_da_abertura()
    i = depois.index('wait_for_load_state("networkidle"')
    assert "failures.append" not in depois[i:i + 320], (
        "a folga voltou a reprovar — é justamente o que causou o vermelho")


def test_CONTROLE_a_abertura_da_pagina_AINDA_pode_reprovar():
    """Se a página não abrir de jeito nenhum, o smoke tem que gritar. Afrouxar
    o critério não pode virar teste que aprova qualquer coisa."""
    assert "failures.append" in _trecho_da_abertura(400), (
        "a abertura do projeto não reprova mais em hipótese nenhuma")


def test_o_botao_continua_sendo_a_PROVA_de_que_carregou():
    """🔑 O conserto só é honesto porque o passo 3 existe: ele espera o
    #btn-download VISÍVEL e clicável. Se alguém tirar isso, afrouxar a abertura
    passa a ser afrouxar o teste inteiro."""
    src = _fonte()
    assert 'wait_for_selector("#btn-download", state="visible"' in src, (
        "sumiu a espera pelo botão — sem ela, abrir a página não prova nada")
    assert "pointerEvents !== 'none'" in src, (
        "sumiu a checagem de que o botão está clicável, não só visível")
