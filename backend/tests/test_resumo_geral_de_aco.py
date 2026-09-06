# -*- coding: utf-8 -*-
"""O resumo geral era somado como se fosse mais um quadro de aço.

🚨 28/08/2026. O Pedro mandou investigar o aço, a maior família do estrutural.
O banco dizia: **361 itens em kg, 5 medidos (1,4%)**. E o contraste entre
unidades conta a história do motor inteiro:

    un   90 itens   61,1% medidos     ← contar, ele conta
    m    23 itens   52,2% medidos     ← medir comprimento, ele mede
    kg  361 itens    1,4% medidos     ← peso, quase nunca
    m³  120 itens    0,0% medidos
    m²  105 itens    1,0% medidos

Os 5 que deram certo vieram TODOS do mesmo lugar: o quadro/resumo de aço
impresso na prancha. Nenhum foi calculado da geometria — peso de armadura exige
comprimento × bitola × massa linear, e a prancha não desenha barra por barra.

🔑 **E os 356 que falharam não falharam por falta de dado.** Classificando as
observações que o próprio motor escreveu:

    303 de 356 CITAM o quadro de aço da prancha
      2 de 356 dizem que não há quadro

Ou seja: o dado estava lá, o motor leu, e rebaixou sozinho. Por causa:

    127 itens · 105 TONELADAS  "inconsistência / mesma bitola em mais de um quadro"
     79 itens                  veio de PDF (regra manda estimar — correto)
      7 itens                  divergência peso × massa linear

🩸 **A CAUSA, provada em experimento controlado (não por leitura):** prancha
estrutural traz um quadro por elemento (vigas, lajes) MAIS um RESUMO GERAL que
repete tudo. O código somava os três. Daí saíam dois estragos opostos:

    quadros SEM linha TOTAL  → soma dobrava, total não → 5% reprovava → ESTIMADO
    quadros COM linha TOTAL  → os dois dobravam juntos → batiam → CONFIRMADO
                                com o DOBRO do aço da obra

O segundo é pior: é a **regra dura nº1** quebrada, número inventado carimbado de
MEDIDO. Não foi observado em cliente (os 5 confirmados vêm de prancha com quadro
único), mas o mecanismo estava vivo.

🔑 **O sinal que separa resumo de quadro-a-mais:** um resumo geral é a SOMA dos
outros, logo é ESTRITAMENTE MAIOR que cada um. Dois quadros legítimos de 250 kg
não têm ninguém estritamente maior — e é isso que impede o falso positivo.

🪤 Quando são exatamente dois valores IGUAIS não dá pra decidir ("vigas 250 +
lajes 250" é indistinguível de "quadro 250 + seu resumo 250"). Aí a resposta é
dizer que não sabe: marca estimado. Chutar seria escolher entre entregar metade
ou o dobro do aço, e um dos dois erros sai carimbado de medido.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from structural_extractor import parse_steel_table  # noqa: E402


class _T:
    """Texto de CAD como o extrator espera: .text, .position, .height."""

    def __init__(self, text, x, y, h=2.5):
        self.text = text
        self.position = (x, y)
        self.height = h


def _quadro(titulo, y0, linhas, com_total=True):
    """Um quadro de ferragens: título, cabeçalho, linhas e (opcional) TOTAL.

    🪤 `%%c` é como o AutoCAD escreve o Ø. Na primeira versão deste fixture eu
    escrevi `"%%c %s" % bit` e o próprio `%` do Python comeu um par: virou
    `%c`, que o extrator não reconhece. O experimento acusou "0 kg lidos" e eu
    quase concluí que o motor não lia quadro nenhum — o errado era o fixture.
    """
    out = [_T(titulo, 0, y0),
           _T("BITOLA", 0, y0 - 5), _T("COMPR. (m)", 30, y0 - 5),
           _T("PESO (kg)", 60, y0 - 5)]
    y = y0 - 10
    for bit, comp, kg in linhas:
        out += [_T("%%%%c %s" % bit, 0, y), _T("%.2f" % comp, 30, y),
                _T("%.2f" % kg, 60, y)]
        y -= 5
    if com_total:
        out += [_T("TOTAL", 0, y),
                _T("%.2f" % sum(k for _, _, k in linhas), 60, y)]
    return out


# Massa linear NBR 7480 — o comprimento tem que bater com o peso, senão a
# validação interna descarta a linha e o teste passaria pelo motivo errado.
#   Ø8 = 0,395   Ø10 = 0,617   Ø12,5 = 0,963 kg/m
VIGAS = [(10.0, 162.1, 100.0), (12.5, 207.7, 200.0)]                      # 300
LAJES = [(8.0, 379.7, 150.0), (10.0, 81.0, 50.0)]                         # 200
RESUMO = [(8.0, 379.7, 150.0), (10.0, 243.1, 150.0), (12.5, 207.7, 200.0)]  # 500

PILARES_250 = [(10.0, 405.2, 250.0)]                                      # 250
ESCADA_250 = [(12.5, 259.6, 250.0)]                                       # 250


def _ler(*quadros):
    txt = []
    for q in quadros:
        txt += q
    r = parse_steel_table(txt)
    assert r is not None, "o extrator não reconheceu quadro nenhum"
    return r


def _soma(r):
    return round(sum(e["kg"] for e in r["por_bitola"]), 2)


# ───────────────────────── o caso que estava quebrado ─────────────────────────

def test_resumo_geral_NAO_e_somado_como_quadro_a_mais():
    """🚨 O conserto. Vigas 300 + Lajes 200 + Resumo 500 = obra de 500 kg.
    Antes o motor lia 1000."""
    r = _ler(_quadro("VIGAS", 100, VIGAS),
             _quadro("LAJES", 60, LAJES),
             _quadro("RESUMO GERAL", 20, RESUMO))
    assert _soma(r) == 500.0, (
        "leu %.2f kg numa obra de 500 — o resumo geral voltou a ser somado "
        "em cima dos quadros" % _soma(r))
    assert r["total_kg"] == 500.0, (
        "o TOTAL declarado virou %s — os totais de cada quadro estão sendo "
        "somados com o total geral" % r["total_kg"])


def test_e_o_item_sai_MEDIDO_e_nao_estimado():
    """🔑 O ganho pro cliente: 127 itens e 105 toneladas que hoje saem laranja
    porque o motor desconfiou de uma soma que ele mesmo dobrou."""
    r = _ler(_quadro("VIGAS", 100, VIGAS),
             _quadro("LAJES", 60, LAJES),
             _quadro("RESUMO GERAL", 20, RESUMO))
    assert r["confiavel"] is True, (
        "continua rebaixando pra estimado. Avisos: %s" % r["avisos"])


def test_o_caso_PIOR_nao_carimba_o_dobro_como_medido():
    """🚨 REGRA DURA Nº1. Com linha TOTAL em cada quadro, os dois lados dobravam
    juntos, batiam entre si e o item saía CONFIRMADO com 1000 kg numa obra de
    500 — número inventado com selo de medido."""
    r = _ler(_quadro("VIGAS", 100, VIGAS, com_total=True),
             _quadro("LAJES", 60, LAJES, com_total=True),
             _quadro("RESUMO GERAL", 20, RESUMO, com_total=True))
    assert not (r["confiavel"] and _soma(r) > 500.0 * 1.05), (
        "CARIMBOU %0.2f kg como MEDIDO numa obra de 500 kg — regra dura nº1"
        % _soma(r))
    assert _soma(r) == 500.0, "leu %.2f kg" % _soma(r)


# ─────────────────── controles negativos: não pode ter quebrado ───────────────

def test_CONTROLE_dois_quadros_LEGITIMOS_continuam_somando():
    """🧪 O risco do conserto é o oposto do bug: passar a tratar quadro
    legítimo como resumo e entregar MENOS aço do que a obra tem.
    Vigas 300 + Lajes 200, sem resumo nenhum = 500 kg, somados."""
    r = _ler(_quadro("VIGAS", 100, VIGAS),
             _quadro("LAJES", 60, LAJES))
    assert _soma(r) == 500.0, (
        "leu %.2f kg — dois quadros legítimos deixaram de ser somados, o "
        "cliente receberia aço A MENOS" % _soma(r))
    assert r["confiavel"] is True, r["avisos"]


def test_CONTROLE_quadro_UNICO_nao_muda_em_nada():
    """🧪 O caso mais comum, e o único que hoje funciona (os 5 medidos no
    banco vieram assim). Não pode ter sido tocado."""
    r = _ler(_quadro("QUADRO DE FERRAGENS", 100, VIGAS))
    assert _soma(r) == 300.0, "leu %.2f kg" % _soma(r)
    assert r["total_kg"] == 300.0
    assert r["confiavel"] is True, r["avisos"]


def test_CONTROLE_dois_quadros_de_peso_IGUAL_viram_estimado():
    """🪤 O empate que não dá pra desempatar: Pilares 250 + Escada 250 é
    indistinguível de um quadro de 250 com seu próprio resumo.

    A saída certa é dizer que não sabe. Chutar aqui é escolher entre entregar
    250 (metade) ou 500 (dobro) — e um dos dois sairia com selo de MEDIDO.
    É a mesma lição da régua de escala em 26/08: empate falso é pior que
    resposta nenhuma, porque parece resposta.
    """
    r = _ler(_quadro("PILARES", 100, PILARES_250),
             _quadro("ESCADA", 60, ESCADA_250))
    assert r["confiavel"] is False, (
        "decidiu sozinho num empate que a prancha não desempata — leu %.2f kg "
        "e carimbou de medido" % _soma(r))
    assert any("não dá pra decidir" in a for a in r["avisos"]), (
        "rebaixou sem dizer por quê, e aí o cliente não sabe o que conferir: %s"
        % r["avisos"])


def test_CONTROLE_prancha_sem_quadro_nenhum_continua_devolvendo_None():
    """🚨 Regra dura nº1: sem quadro, o extrator NUNCA inventa."""
    assert parse_steel_table([_T("PLANTA BAIXA", 0, 0),
                              _T("ESCALA 1:50", 0, -5)]) is None
    assert parse_steel_table([]) is None


def test_CONTROLE_o_aviso_explica_o_que_foi_feito():
    """Sem o aviso, o cliente vê um número menor do que a soma dos quadros da
    prancha dele e não tem como saber que foi de propósito."""
    r = _ler(_quadro("VIGAS", 100, VIGAS),
             _quadro("LAJES", 60, LAJES),
             _quadro("RESUMO GERAL", 20, RESUMO))
    assert any("RESUMO GERAL" in a for a in r["avisos"]), (
        "não avisou que descartou os quadros individuais: %s" % r["avisos"])


# ───────── o quadro tem BORDA: o desenho em volta não é linha da tabela ──────

# 🚨 29/08/2026 — CASO EDUARDA, e é o mais caro dos dois.
#
# O quadro dela é PERFEITO. Conferi as 6 linhas contra a NBR 7480 uma por uma
# (852 m × 0,154 = 131,2 e o quadro diz 131; e assim as seis). A planilha saiu
# com ZERO medido mesmo assim.
#
# 🔑 O último cabeçalho da prancha usava `y_min = -infinito`: as "linhas de
# dados" do quadro iam até o fim do desenho. Medido no arquivo real
# (0653-KZ-EST-PE-1052): o desenho vai de y=82 a y=-227, o quadro fica em y≈60,
# e abaixo dele há 1.728 textos — 118 deles marcações de ferro (`%%c 5`,
# `2 %%c 12.5`) espalhadas pela planta, a até 94 unidades do quadro.
#
# A escolha de coluna era `min(anchors, key=distância)` SEM TETO. Um ferro
# desenhado no meio da planta sempre "pertencia" a alguma coluna. Os números
# dele viravam peso e comprimento, a massa linear reprovava, a linha era
# descartada — e uma descartada marca o quadro INTEIRO como não-confiável.
#
# 🩸 Seis linhas certas viraram laranja por causa de um ferro a 94 unidades.

# O quadro real da cliente-20, com as posições do DXF dela.
_QUADRO_EDUARDA = [
    ("AÇO", 102.12, 60.08), ("BIT", 104.23, 60.08),
    ("COMPR", 106.21, 60.08), ("PESO", 109.84, 60.08),
    ("mm", 104.55, 59.60), ("m", 106.92, 59.65), ("kgf", 110.30, 59.65),
    ("60", 101.56, 59.27), ("5", 103.73, 59.28), ("852", 105.97, 59.27), ("131", 109.82, 59.27),
    ("50", 101.56, 58.92), ("6.3", 103.73, 58.93), ("206", 105.97, 58.92), ("50", 109.82, 58.92),
    ("50", 101.56, 58.57), ("8", 103.73, 58.58), ("157", 105.97, 58.57), ("62", 109.82, 58.57),
    ("50", 101.56, 58.22), ("10", 103.73, 58.23), ("123", 105.97, 58.22), ("76", 109.82, 58.22),
    ("50", 101.56, 57.87), ("12.5", 103.73, 57.88), ("409", 105.97, 57.87), ("394", 109.82, 57.87),
    ("50", 101.56, 57.52), ("16", 103.73, 57.53), ("65", 105.97, 57.52), ("103", 109.82, 57.52),
    # 🪤 A prancha dela declara DOIS totais, um por classe de aço — e o valor vem
    # com a unidade colada. Era o `_num("685 kgf") -> None` que fazia o total
    # sumir. A 1ª versão deste fixture esqueceu estas duas linhas e eu quase
    # tomei o `total_kg=None` resultante como bug do motor: era buraco do teste.
    ("Peso Total         60 =", 101.19, 57.10), ("131 kgf", 108.56, 57.10),
    ("Peso Total         50 =", 101.19, 56.66), ("685 kgf", 108.56, 56.66),
]
# As marcações de ferro DESENHADAS na planta, longe do quadro — como no arquivo.
_FERROS_NA_PLANTA = [
    ("%%c 5", 32.0, 51.0), ("13", 29.9, 52.8), ("74", 29.7, 51.0), ("1", 30.6, 51.2),
    ("%%c 5", 38.0, 54.0), ("24", 36.5, 53.6), ("13", 36.7, 54.4),
    ("2 %%c 12.5", 43.0, 46.0), ("114", 45.5, 51.7), ("6", 46.3, 52.0),
    ("%%c 10", 55.0, -30.0), ("308", 57.0, -30.0),
    ("%%c 16", 20.0, -150.0), ("1250", 22.0, -150.0),
]


def _texto(tuplas):
    return [_T(t, x, y, 0.20) for t, x, y in tuplas]


def test_o_quadro_da_EDUARDA_sozinho_e_lido_e_confiavel():
    """📌 Controle: sem a planta em volta, o quadro dela sempre funcionou.
    É isso que prova que o problema é o CONTEXTO, não a tabela."""
    r = parse_steel_table(_texto(_QUADRO_EDUARDA))
    assert r is not None, "não reconheceu o quadro dela"
    assert r["confiavel"] is True, r["avisos"]
    assert _soma(r) == 816.0, (
        "leu %.2f kg; o quadro dela soma 131+50+62+76+394+103 = 816" % _soma(r))


def test_FERRO_DESENHADO_NA_PLANTA_nao_derruba_o_quadro():
    """🚨 O caso cliente-20. Mesmo quadro, agora com a planta em volta — que é
    como o arquivo dela realmente é. Antes deste conserto: tudo [REFERÊNCIA]."""
    r = parse_steel_table(_texto(_QUADRO_EDUARDA + _FERROS_NA_PLANTA))
    assert r is not None, "não reconheceu o quadro"
    assert r["confiavel"] is True, (
        "o desenho em volta derrubou o quadro de novo — a planilha dela volta a "
        "sair 100%% laranja. Avisos: %s" % r["avisos"])
    assert _soma(r) == 816.0, (
        "leu %.2f kg em vez de 816 — número de ferro da planta entrou na tabela"
        % _soma(r))


def test_a_borda_nao_e_tao_apertada_que_corte_o_proprio_quadro():
    """🧪 O erro simétrico: borda estreita demais jogaria fora célula
    desalinhada do próprio quadro, e aí o quadro sairia INCOMPLETO — que é pior
    que sair laranja, porque sai com número menor parecendo certo."""
    torto = [(t, x + (0.9 if t in ("131", "394") else 0.0), y)
             for t, x, y in _QUADRO_EDUARDA]
    r = parse_steel_table(_texto(torto))
    assert _soma(r) == 816.0, (
        "célula levemente desalinhada foi cortada: leu %.2f de 816" % _soma(r))


def test_CONTROLE_POSITIVO_a_sabotagem_da_borda_reprova():
    """🧪 Sem isto eu não saberia se o teste acima passa pelo motivo certo.
    Empurra um ferro da planta PARA DENTRO da faixa de colunas: aí ele é
    indistinguível de linha do quadro e TEM que estragar."""
    # 🪤 A 1ª versão punha o intruso em y=57,2, que fica a 0,10 da linha
    # "Peso Total" (y=57,10). O agrupamento por linha usa tolerância de 0,15 —
    # os dois viravam a MESMA linha, e o intruso era lido como total, não como
    # dado. O teste falhava por colisão de fixture, não por defeito do código.
    # y=58,75 fica a 0,18 e 0,17 dos vizinhos: linha própria.
    intruso = _QUADRO_EDUARDA + [("%%c 5", 104.2, 58.75), ("9999", 109.8, 58.75)]
    r = parse_steel_table(_texto(intruso))
    assert not (r["confiavel"] and _soma(r) == 816.0), (
        "um intruso DENTRO das colunas passou despercebido — a borda virou "
        "peneira e o teste de cima estava passando por sorte. Leu %.0f kg"
        % _soma(r))


def test_PESO_TOTAL_e_linha_de_total_e_NAO_cabecalho_de_quadro_novo():
    """🚨 O conserto que a sabotagem revelou estar DESCOBERTO.

    O rodapé do quadro da cliente-20 é "Peso Total 50 = 685 kgf". Como contém a
    palavra *peso*, o detector de cabeçalho o tratava como início de um QUADRO
    NOVO. Dois estragos de uma vez:

      1. o total declarado nunca era lido (virou cabeçalho);
      2. esse quadro fantasma era o ÚLTIMO da prancha — e o último não tem
         limite embaixo, então varria o desenho inteiro atrás de "linhas".

    🪤 Escrevi quatro testes achando que cobriam isto e a sabotagem provou que
    NÃO cobriam: com o filtro de borda em pé, os ferros da planta já ficavam de
    fora, então desfazer este conserto não mudava nada nos outros testes. O que
    denuncia é o TOTAL — e nenhum teste olhava pra ele.
    """
    r = parse_steel_table(_texto(_QUADRO_EDUARDA))
    assert r["total_kg"] == 816.0, (
        "o TOTAL declarado veio %s. As duas linhas 'Peso Total' voltaram a ser "
        "lidas como cabeçalho de quadro novo — e aí o último 'quadro' varre a "
        "prancha inteira." % r["total_kg"])
    assert r["n_quadros"] == 1, (
        "achou %s quadros numa prancha que tem UM. Cada 'Peso Total' virou um "
        "quadro fantasma." % r["n_quadros"])


def test_e_a_soma_das_bitolas_BATE_com_o_total_declarado():
    """📌 O fecho: 131+50+62+76+394+103 = 816, e a prancha declara 131+685=816.
    Quando os dois batem, o quadro é confiável e o aço sai MEDIDO."""
    r = parse_steel_table(_texto(_QUADRO_EDUARDA))
    assert _soma(r) == r["total_kg"] == 816.0
    assert r["confiavel"] is True, r["avisos"]


# ── o buraco que a régua do próprio motor não enxergava ──────────────────────

def _quadro_da_eduarda(duplicado=False, com_total=True):
    """Monta o quadro real dela, opcionalmente com as linhas REPETIDAS logo
    abaixo — que é como fica quando a prancha traz o resumo geral colado embaixo
    do mesmo cabeçalho, sem cabeçalho novo."""
    cab = [t for t in _QUADRO_EDUARDA if t[2] >= 59.6]
    dados = [t for t in _QUADRO_EDUARDA if 57.4 < t[2] < 59.6]
    tots = [t for t in _QUADRO_EDUARDA if t[2] < 57.4]
    fora = list(dados)
    if duplicado:
        fora += [(t, x, y - 2.5) for t, x, y in dados]
    return _texto(cab + fora + (tots if com_total else []))


def test_bitola_REPETIDA_sem_total_pra_conferir_NAO_pode_ser_medido():
    """🚨 REGRA DURA Nº1, e este é o caso que eu quase deixei passar.

    Eu tinha "conferido" os 38 itens da cliente-20 recalculando comprimento ×
    massa linear e comparando com o peso. Passaram 37 de 38 dentro de 1,3%, e
    eu chamei isso de prova.

    🩸 Era TAUTOLOGIA. Quando a mesma bitola cai em mais de um quadro, a
    consolidação soma o `kg` E o `comp_m` juntos — a razão continua sendo
    exatamente a massa linear da norma. Medido com o quadro dela duplicado:

        soma lida 1632 kg (a verdade é 816), confiavel=True
        Ø5,0   262 kg / 1704 m → NBR 262,8  desvio -0,32%
        Ø12,5  788 kg /  818 m → NBR 788,6  desvio -0,08%

    Seis de seis passando com folga, e a obra recebendo o DOBRO com selo de
    MEDIDO. Conferi o motor com a régua do próprio motor.
    """
    r = parse_steel_table(_quadro_da_eduarda(duplicado=True, com_total=False))
    assert r["confiavel"] is False, (
        "leu %.0f kg num quadro de 816 e carimbou de MEDIDO. Sem TOTAL "
        "declarado, soma repetida é indistinguível de leitura em dobro."
        % _soma(r))
    assert any("dobro" in a for a in r["avisos"]), (
        "rebaixou sem dizer por quê: %s" % r["avisos"])


def test_CONTROLE_com_TOTAL_declarado_a_conferencia_e_INDEPENDENTE():
    """🧪 O outro lado: quando a prancha declara o peso total, existe âncora de
    verdade. Foi ela que salvou 5 das 6 pranchas da cliente-20 — leitura em dobro
    não bate com o total impresso, e aí o rebaixamento vem pelo motivo certo."""
    r = parse_steel_table(_quadro_da_eduarda(duplicado=True, com_total=True))
    assert r["confiavel"] is False
    assert any("difere do TOTAL declarado" in a for a in r["avisos"]), (
        "com total declarado, o motivo do rebaixamento tem que ser a "
        "divergência contra ele: %s" % r["avisos"])


def test_CONTROLE_quadro_NORMAL_dela_nao_foi_afetado():
    """🧪 O risco do conserto é rebaixar quadro honesto. O dela tem uma linha
    por bitola — nenhuma repetição — e continua MEDIDO, com os 816 kg."""
    r = parse_steel_table(_quadro_da_eduarda(duplicado=False, com_total=True))
    assert r["confiavel"] is True, r["avisos"]
    assert _soma(r) == 816.0 and r["total_kg"] == 816.0


def test_CONTROLE_dois_quadros_legitimos_SEM_total_continuam_medidos():
    """🧪 O erro simétrico: vigas Ø10+Ø12,5 e lajes Ø8+Ø10 sem total nenhum.
    A Ø10 repete entre eles, mas são elementos DIFERENTES — somar está certo.

    🪤 Este caso É rebaixado agora, e de propósito: sem total declarado o código
    não tem como distinguir 'vigas + lajes' de 'quadro + seu resumo'. Prefiro
    entregar laranja a entregar o dobro carimbado de medido. O teste existe pra
    fotografar essa escolha — se um dia alguém achar um sinal melhor, este
    número muda e a decisão é consciente."""
    r = _ler(_quadro("VIGAS", 100, VIGAS, com_total=False),
             _quadro("LAJES", 60, LAJES, com_total=False))
    assert _soma(r) == 500.0, "a soma em si continua certa: %.0f" % _soma(r)
    assert r["confiavel"] is False, (
        "sem total pra conferir, bitola repetida não pode virar MEDIDO")
