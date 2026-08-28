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
