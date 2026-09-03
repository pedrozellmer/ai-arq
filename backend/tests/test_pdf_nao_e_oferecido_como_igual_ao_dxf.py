# -*- coding: utf-8 -*-
"""PDF e DXF não são caminhos equivalentes — e a copy oferecia como se fossem.

🩸 03/09/2026, FÁBIO SHIRAISHI. O DWG dele não abriu e ele recebeu, às 14:02,
o e-mail com esta frase:

    "O ideal é reenviar em DXF ou PDF vetorial"

Ele subiu um PDF às **14:04** — dois minutos depois — e recebeu **19 de 19
linhas ZERADAS**. Nós o mandamos para o caminho que não mede.

🔑 MEDIDO em 118 projetos de cliente concluídos (03/09/2026):

    só CAD  →  72 projetos, 73,6% com algum item MEDIDO, média 14,3
    só PDF  →  37 projetos,  5,4% com algum item MEDIDO, média  0,1
                             ↑ 35 de 37 receberam ZERO

Oferecer os dois lado a lado, com "ou", é recomendar um caminho que falha 18
vezes em 19 — com a nossa assinatura em cima. E havia uma frase pior ainda,
prometendo que de PDF "a gente mede pela geometria".

🪤 Isto NÃO é "parar de aceitar PDF". PDF é topo de funil e entrega valor real
(identifica e estima, e o cliente decide). O que não pode é ser apresentado
como equivalente a DXF na hora em que o cliente está escolhendo o que reenviar.
"""
import io
import os
import re

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()

_B = chr(92)
_NL = _B + "n"
# Cola literais grudados: a frase do cliente não existe inteira no fonte.
_COLA = re.compile('"' + _B + 's*' + _NL + _B + 's*f?"')


def _copy(src=None):
    src = src if src is not None else _FONTE
    linhas = [l for l in src.splitlines() if not l.strip().startswith("#")]
    return _COLA.sub("", chr(10).join(linhas))


def _oferece_pdf_como_igual(src=None):
    """Frases que põem PDF e DXF no mesmo nível como resposta ao 'o que mando?'.

    🪤 A 1ª versão deste guarda acusava a LISTA DE FORMATOS ACEITOS ("envie ao
    menos um arquivo: DWG, DXF ou PDF"), que é legítima e precisa existir —
    aceitar PDF é topo de funil. O que este guarda cuida é da RECOMENDAÇÃO
    feita depois de uma falha, quando o cliente está escolhendo o que reenviar.
    Duas absolvições, as duas necessárias:
      • a frase cita os TRÊS formatos → é lista do que se aceita, não conselho
        entre dois caminhos;
      • a frase DIZ que de PDF a gente estima → é o conserto, não o defeito.
    """
    txt = _copy(src)
    ruins = []
    for m in re.finditer("[^" + _NL + "]{0,140}DXF[^" + _NL + "]{0,60}PDF"
                         "[^" + _NL + "]{0,80}", txt, re.I):
        t = m.group(0)
        if re.search("estim|n[ãa]o mede|sem.{0,12}medi|zerad", t, re.I):
            continue
        # 🪤 A 2ª versão excluía qualquer frase que contivesse "DWG" — e a frase
        # do Fábio contém ("salvar o DWG numa versão mais antiga"), então o
        # guarda absolvia justamente o defeito. Foi o controle positivo que
        # pegou. O que caracteriza LISTA é os três nomes ADJACENTES, separados
        # só por vírgula/ou/e: "DWG, DXF ou PDF".
        if re.search(r"(DWG|DXF|PDF)\s*[,/]?\s*(ou|e|,)?\s*(DWG|DXF|PDF)"
                     r"\s*[,/]?\s*(ou|e|,)?\s*(DWG|DXF|PDF)", t, re.I):
            continue
        if re.search(r"\b(ou|,|e)\s+(o\s+)?PDF", t, re.I):
            ruins.append(t.strip())
    return ruins


def test_a_copy_nao_oferece_PDF_como_alternativa_igual_ao_DXF():
    """🩸 A frase que o Fábio leu dois minutos antes de subir um PDF."""
    ruins = _oferece_pdf_como_igual()
    assert not ruins, (
        "a copy voltou a oferecer PDF e DXF como equivalentes — medido, só-PDF "
        "entrega item medido em 5,4% dos projetos contra 73,6% do CAD:"
        + _NL + "  " + (_NL + "  ").join(r[:110] for r in ruins))


def test_CONTROLE_o_guarda_REPROVA_a_frase_que_o_fabio_leu():
    """Sem isto o teste acima passa por não achar nada, não por estar limpo."""
    antiga = ('    fix = ("O ideal é <b>reenviar em DXF ou PDF vetorial</b>, ou '
              'salvar o DWG numa versão mais antiga")' + chr(10))
    assert _oferece_pdf_como_igual(antiga), (
        "o guarda não reprova a frase que de fato foi entregue ao Fábio")


def test_CONTROLE_o_guarda_ACEITA_a_frase_honesta():
    """Dizer que PDF estima é o conserto — não pode ser acusado."""
    boa = ('    fix = ("O ideal é reenviar em DXF. Se não der, dá pra mandar o '
           'PDF vetorial — mas aí a gente identifica e estima, não mede.")' + chr(10))
    assert not _oferece_pdf_como_igual(boa), (
        "o guarda acusou a frase CERTA — ele proibiria o conserto")


def test_nao_prometemos_que_medimos_pela_geometria_do_PDF():
    """Havia uma frase prometendo medição de PDF: 35 de 37 saíram com zero."""
    txt = _copy()
    proibida = re.search(
        "PDF[^" + _NL + "]{0,120}a gente mede pela geometria", txt, re.I)
    assert not proibida, (
        "voltou a prometer que mede pela geometria do PDF: medido, 35 de 37 "
        "projetos só-PDF receberam ZERO item medido")


def test_CONTROLE_a_recomendacao_de_DXF_continua_de_pe():
    """Consertar a equivalência não pode virar 'não recomenda nada'.

    DXF é o formato nº1 desta casa desde 20/07 e a recomendação tem que
    continuar explícita — é ela que leva o cliente pro caminho de 73,6%.
    """
    txt = _copy()
    assert re.search("reenviar em <b>DXF</b>|reenviar em DXF", txt, re.I), (
        "sumiu a recomendação de reenviar em DXF")
