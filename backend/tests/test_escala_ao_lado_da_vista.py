# -*- coding: utf-8 -*-
"""`indicadas` não é falha: é o carimbo dizendo ONDE procurar a escala.

🩸 09/09/2026, medido no arquivo REAL de um cliente (job `aec7cac2`, 47
páginas, 22 sem escala). O carimbo daquela prancha diz:

    Escala          Data       Desenho nº
    A3 - A1
    Como se indica  NOV 2025   A3004

*"Como se indica"* é o "ESCALAS INDICADAS" em português de Portugal, e o
`A3 - A1` explica o motivo: a folha imprime em DOIS tamanhos, então a mesma
prancha tem duas escalas reais — uma razão no carimbo seria mentira.

🔑 O motor lia certo e concluía certo ("não há escala aqui") — e desistia.

📏 E as razões EXISTIAM. Na única página com razão no texto havia TRÊS —
`1:100`, `1:50`, `1:50` — todas em **x=5% da largura**, na margem ESQUERDA, uma
por vista. O leitor de carimbo recorta os **18% da DIREITA**: nunca ia achar.

🪤 EU JÁ TINHA "REFUTADO" ESTA IDEIA — em 08/09, com prova de conceito que deu
0 de 17. A refutação era INVÁLIDA: testei em pranchas cujo carimbo TINHA escala
de verdade (1:100, 1:100, 1:50, confiança alta). Nelas o rótulo por vista não
existe porque não precisa. Refutei a ideia certa com o corpus errado.
Ver [[project_onde_a_leitura_de_pdf_perde_20260908]].
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from pdfvec_escala_por_vista import (  # noqa: E402
    recorte_da_vista, normalizar, escala_principal, MARGEM_FRAC)


# ══════════════════════════════════════════════════════════════════════════
#  🪤 A ARMADILHA QUE ME MORDEU: origem do MediaBox fora de (0,0)
# ══════════════════════════════════════════════════════════════════════════
#  No arquivo real o MediaBox é [-1192, -842, 1192, 842] — a folha é CENTRADA
#  na origem. Recorte escrito em coordenada absoluta cai fora da página e
#  devolve papel branco. Foi exatamente assim que a minha primeira análise leu
#  "0 palavras no carimbo" e quase me fez culpar o motor.

_CAIXA_NORMAL = (0.0, 0.0, 2384.0, 1684.0)
_CAIXA_CENTRADA = (-1192.0, -842.0, 1192.0, 842.0)      # o caso real


def test_a_vista_no_MEIO_vira_o_MESMO_recorte_nas_duas_caixas():
    """🔑 O coração: a mesma vista, descrita nas duas convenções de origem,
    tem que virar a MESMA fração de página. Se divergir, o recorte cai fora."""
    # uma vista no centro-direita, metade de cima
    bbox_normal = (1192.0, 842.0, 2146.0, 1516.0)
    bbox_centrada = (0.0, 0.0, 954.0, 674.0)
    a = recorte_da_vista(_CAIXA_NORMAL, bbox_normal)
    b = recorte_da_vista(_CAIXA_CENTRADA, bbox_centrada)
    for x, y in zip(a, b):
        assert abs(x - y) < 1e-6, (a, b)


def test_a_origem_do_eixo_X_tambem_e_tratada():
    """🪤 A MUTAÇÃO PEGOU ESTE BURACO. Como o recorte sempre estende até a
    margem esquerda, o `fx0` vira 0 e a conta da origem em X ficava sem teste —
    quebrá-la não reprovava nada. Aqui a extensão é desligada de propósito, pra
    que o `- px0` do eixo X seja de fato exercitado."""
    bbox_normal = (1192.0, 842.0, 2146.0, 1516.0)
    bbox_centrada = (0.0, 0.0, 954.0, 674.0)
    a = recorte_da_vista(_CAIXA_NORMAL, bbox_normal, ate_a_esquerda=False)
    b = recorte_da_vista(_CAIXA_CENTRADA, bbox_centrada, ate_a_esquerda=False)
    assert abs(a[0] - b[0]) < 1e-6, ("fx0 divergiu entre as duas origens", a, b)
    assert abs(a[0] - (0.5 - MARGEM_FRAC)) < 1e-6, a


def test_CONTROLE_ignorar_a_origem_daria_recorte_ERRADO():
    """🧪 Sem este controle, "eu trato a origem" seria só uma frase.

    Prova que a conta ingênua (dividir a coordenada crua pela largura) manda o
    recorte pro lugar errado — que é o defeito que este módulo evita.
    """
    bbox_centrada = (0.0, 0.0, 954.0, 674.0)
    W = _CAIXA_CENTRADA[2] - _CAIXA_CENTRADA[0]
    ingenuo_fx1 = bbox_centrada[2] / W          # 954/2384 = 40%
    correto = recorte_da_vista(_CAIXA_CENTRADA, bbox_centrada)
    assert abs(correto[2] - 0.9) < 0.05, correto
    assert abs(ingenuo_fx1 - correto[2]) > 0.4, (
        "a conta ingênua e a certa deveriam divergir MUITO — se não divergem, "
        "este controle não prova nada")


def test_o_recorte_vai_ATE_A_MARGEM_ESQUERDA():
    """📏 As três razões do arquivo real estavam em x=5%. Se o recorte parar na
    borda da vista, o rótulo fica de fora e a leitura devolve null."""
    bbox = (1400.0, 400.0, 2100.0, 1000.0)       # vista na direita da folha
    fx0, _fy0, fx1, _fy1 = recorte_da_vista(_CAIXA_NORMAL, bbox)
    assert fx0 == 0.0, "o recorte não chegou na margem esquerda: %r" % fx0
    assert fx1 > 0.85, fx1


def test_CONTROLE_sem_estender_o_recorte_perderia_o_rotulo():
    """🧪 O par do teste acima: com `ate_a_esquerda=False` o recorte para na
    vista, e o rótulo em x=5% fica FORA. É a diferença que o conserto faz."""
    bbox = (1400.0, 400.0, 2100.0, 1000.0)
    fx0, _a, _b, _c = recorte_da_vista(_CAIXA_NORMAL, bbox, ate_a_esquerda=False)
    assert fx0 > 0.5, fx0
    assert fx0 > 0.05, (
        "o rótulo medido estava em x=5%%; um recorte que começa em %.2f o "
        "deixaria de fora" % fx0)


@pytest.mark.parametrize("caixa", [_CAIXA_NORMAL, _CAIXA_CENTRADA])
def test_o_recorte_NUNCA_sai_da_pagina(caixa):
    """🪤 Fração fora de [0,1] vira corte negativo no pypdfium2 — render
    quebrado ou exceção dentro do processamento do cliente."""
    px0, py0, px1, py1 = caixa
    # vista colada nos quatro cantos, pra forçar o clamp
    for bbox in ((px0, py0, px0 + 50, py0 + 50),
                 (px1 - 50, py1 - 50, px1, py1),
                 (px0 - 500, py0 - 500, px1 + 500, py1 + 500)):
        for v in recorte_da_vista(caixa, bbox):
            assert 0.0 <= v <= 1.0, (bbox, v)


def test_a_margem_e_aplicada():
    bbox = (1000.0, 800.0, 1400.0, 1000.0)
    _fx0, fy0, _fx1, fy1 = recorte_da_vista(_CAIXA_NORMAL, bbox)
    H = _CAIXA_NORMAL[3] - _CAIXA_NORMAL[1]
    assert fy0 < (800.0 / H), "a margem de baixo não foi aplicada"
    assert fy1 > (1000.0 / H), "a margem de cima não foi aplicada"
    assert abs(fy1 - (1000.0 / H) - MARGEM_FRAC) < 1e-6


# ══════════════════════════════════════════════════════════════════════════
#  A leitura do modelo — pura, sem rede
# ══════════════════════════════════════════════════════════════════════════
def test_le_a_escala_de_cada_vista():
    bruto = {"vistas": [{"i": 0, "escala": "1:100"}, {"i": 1, "escala": "ESC 1:50"},
                        {"i": 2, "escala": None}]}
    assert normalizar(bruto, 3) == [100, 50, None]


def test_CONTROLE_null_continua_null_e_nao_vira_chute():
    """🚨 Regra nº1 em forma de teste: sem rótulo legível, NADA. Um leitor que
    inventasse 1:100 por padrão passaria em quase tudo e mentiria na planilha."""
    assert normalizar({"vistas": [{"i": 0, "escala": None}]}, 1) == [None]
    assert normalizar({"vistas": []}, 2) == [None, None]
    assert normalizar({}, 2) == [None, None]
    assert normalizar(None, 2) == [None, None]


@pytest.mark.parametrize("lixo", [
    {"vistas": [{"i": 9, "escala": "1:50"}]},          # índice fora da faixa
    {"vistas": [{"i": "x", "escala": "1:50"}]},        # índice não numérico
    {"vistas": [{"i": 0, "escala": "escala grande"}]},  # sem razão
    {"vistas": [{"i": 0, "escala": "1:0"}]},           # denominador zero
    {"vistas": ["1:50"]},                              # item não é dict
])
def test_resposta_torta_do_modelo_NAO_vira_escala(lixo):
    assert normalizar(lixo, 2) == [None, None]


def test_indice_repetido_nao_sobrescreve():
    """🪤 O modelo às vezes repete o índice. A 1ª leitura vale; a 2ª não pode
    apagar nem mudar — senão a ordem da resposta decide o número do cliente."""
    bruto = {"vistas": [{"i": 0, "escala": "1:50"}, {"i": 0, "escala": "1:200"}]}
    assert normalizar(bruto, 1) == [50]


# ══════════════════════════════════════════════════════════════════════════
#  Qual escala manda
# ══════════════════════════════════════════════════════════════════════════
def test_manda_a_escala_da_MAIOR_vista():
    """🔑 Numa prancha 'como se indica' a planta e o pormenor têm escalas
    DIFERENTES de propósito, e é a planta que manda no quantitativo.

    🪤 A MUTAÇÃO PEGOU A FIXTURE ANTERIOR: a maior vista era TAMBÉM a primeira,
    então tirar a ordenação por área não mudava a resposta e o mutante passava.
    Agora a planta é a ÚLTIMA da lista — "maior" e "primeira" discordam.
    """
    por_vista = [20, 20, 50]
    areas = [10000.0, 9000.0, 900000.0]      # a planta é a 3ª
    assert escala_principal(por_vista, areas) == 50, (
        "escolheu a primeira vista em vez da maior")


def test_CONTROLE_frequencia_elegeria_o_POMENOR_e_estaria_errado():
    """🧪 Prova que a regra é ÁREA e não frequência: aqui o 20 aparece duas
    vezes e o 50 uma só — quem contasse voto escolheria o pormenor."""
    por_vista = [20, 20, 50]
    areas = [10000.0, 9000.0, 900000.0]
    from collections import Counter
    mais_frequente = Counter([d for d in por_vista if d]).most_common(1)[0][0]
    assert mais_frequente == 20
    assert escala_principal(por_vista, areas) == 50


def test_sem_leitura_nenhuma_devolve_None():
    assert escala_principal([None, None], [1.0, 2.0]) is None
    assert escala_principal([], []) is None


def test_vista_grande_SEM_rotulo_nao_bloqueia_a_menor_que_tem():
    """A maior não teve rótulo; a que teve manda. Devolver None aqui jogaria
    fora uma leitura boa."""
    assert escala_principal([None, 50], [900000.0, 10000.0]) == 50


# ══════════════════════════════════════════════════════════════════════════
#  Estar escrito não é estar LIGADO
# ══════════════════════════════════════════════════════════════════════════
def test_o_leitor_esta_LIGADO_no_motor_e_SO_com_indicadas():
    """🪤 Guarda de ligação — hoje eu consertei DOIS defeitos que eram conserto
    aplicado em código que a produção não executa. Este nasce ligado, e o teste
    prova que nasce.

    🔑 E prova também o GATILHO: sem `indicadas` seria uma chamada de Vision a
    mais em toda prancha sem escala, inclusive nas que não têm rótulo nenhum.
    """
    import ast
    import io as _io
    fonte = _io.open(os.path.join(_BACKEND, "pdf_vector.py"),
                     encoding="utf-8").read()
    arvore = ast.parse(fonte)
    chamadas = [n for n in ast.walk(arvore)
                if isinstance(n, ast.Call)
                and (getattr(n.func, "id", None) or getattr(n.func, "attr", None))
                == "read_view_scales"]
    assert chamadas, "o pdf_vector.py não chama read_view_scales"

    # o gatilho: o `if` que embrulha a chamada tem que citar `indicadas`
    achou_gatilho = False
    for n in ast.walk(arvore):
        if not isinstance(n, ast.If):
            continue
        tem_chamada = any(
            isinstance(x, ast.Call)
            and (getattr(x.func, "id", None) or getattr(x.func, "attr", None))
            == "read_view_scales" for x in ast.walk(n))
        if tem_chamada and "indicadas" in ast.dump(n.test):
            achou_gatilho = True
    assert achou_gatilho, (
        "a chamada não está protegida por um `if` que exige `indicadas` — "
        "sem isso ela roda em toda prancha sem escala e gasta Vision à toa")


def test_a_fonte_nova_TEM_frase_de_procedencia():
    """🚨 Regra nº7 em miniatura: fonte nova entra com a frase no MESMO commit.
    Sem isto o cliente lê um vazio onde deveria estar 'de onde veio a escala'."""
    import main as M
    assert "vista" in M._FONTE_DA_ESCALA, (
        "scale_src='vista' não tem frase em _FONTE_DA_ESCALA — o cliente "
        "receberia procedência vazia")
    como, ressalva = M._frase_da_escala_sem_prova("vista")
    assert como and ressalva
    assert "declara" in ressalva.lower(), (
        "a ressalva tem que dizer que é DECLARAÇÃO, não medida (regra nº1)")
