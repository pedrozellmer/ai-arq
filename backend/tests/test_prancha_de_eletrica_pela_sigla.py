# -*- coding: utf-8 -*-
"""A prancha de elétrica codificada com a SIGLA caía no prompt de arquitetura.

🩸 22/09/2026, job 844603fb. Cliente nova mandou 1 PDF de 1 página: planta de
pontos de elétrica de edifício residencial, com legenda de símbolos. O nome
seguia a codificação comum de prancha — <projeto>-ELE-E-<nº>-R01.pdf. O
`identify_sheet_type` só conhecia palavras por extenso (elétrica, pontos,
hidráulica, instalações...), então a prancha virou DESCONHECIDO → fallback de
ARQUITETURA: prompt de fechamentos, revestimentos, portas e pintura, e os
recortes de arquitetura — com PROMPT_PONTOS e os recortes de pontos prontos.

MEDIDO em 60 dias (projetos de cliente, sem avaliação): de 189 nomes de PDF,
12 têm ELE/HID/PPCI como token (6 projetos), TODOS caíam no fallback de
arquitetura, e 259 das 274 linhas que saíram deles (94,5%) são de instalações.
Um filhote re-roda o MESMO classificador (o reprocesso não recebe o tipo da
prancha), então só o conserto aqui muda o prompt do reprocesso.

🔑 Regras deste guarda:
  • a sigla vale EXATAMENTE como a palavra por extenso que ela abrevia — mesma
    posição na ordem de SHEET_PATTERNS (a ordem continua decidindo empate);
  • só TOKEN inteiro: "ele" dentro de "telefonia"/"elevação" não é elétrica;
  • as siglas sem tipo no motor ficam como estão (e o teste diz quais).
Os nomes aqui são neutros: mesmo formato do caso, nenhum nome de cliente.
"""
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import processor  # noqa: E402
from models import SheetType  # noqa: E402

def _padrao_da_sigla():
    (p,) = [p for p in processor.SHEET_PATTERNS[SheetType.PONTOS] if "ppci" in p]
    return p

# Formatos reais de codificação vistos em 60 dias, com nome neutro.
_NOMES_COM_SIGLA = [
    "XX9-ELE-E-001-002-R01.pdf",                # o formato do caso
    "0000-000_OBRA_ELE_XX_100_PIS10-R01.pdf",   # separador _ e sufixo colado
    "ABCD-XXXX-ELE-PB-ILU-A01-R02.pdf",         # planta de iluminação da elétrica
    "OBRA 0000.000 - EX-R00 ELE-ELE ARQ (1).pdf",
    "OBRA 0000.000 - EX-R00 HID-HID ARQ (1).pdf",
    "01 PPCI_OBRA_REV (6).pdf",
    "PRJ.ELET.02.pdf",
    "PRJ HIDR 03.pdf",
    "PRJ-INC-04.pdf",
]


@pytest.mark.parametrize("nome", _NOMES_COM_SIGLA)
def test_a_sigla_de_disciplina_leva_ao_prompt_de_PONTOS(nome):
    assert processor.identify_sheet_type(nome) == SheetType.PONTOS, nome
    # o que muda de verdade no motor: os recortes de pontos (legenda inteira)
    crops = processor.CROP_REGIONS[processor.identify_sheet_type(nome)]
    assert "legenda_completa" in crops, crops


def test_o_prompt_que_a_prancha_do_caso_recebe_e_o_de_PONTOS():
    analyzer = pytest.importorskip("analyzer")
    st = processor.identify_sheet_type("XX9-ELE-E-001-002-R01.pdf")
    assert analyzer.PROMPTS_POR_TIPO[st] is analyzer.PROMPT_PONTOS
    assert analyzer.PROMPTS_POR_TIPO[st] is not analyzer.PROMPT_ARQUITETURA


@pytest.mark.parametrize("nome", _NOMES_COM_SIGLA)
def test_CONTROLE_sem_o_padrao_da_sigla_os_mesmos_nomes_caem_no_fallback(monkeypatch, nome):
    """Prova que é a SIGLA que decide — e não outra palavra do nome. Tirando só o
    padrão novo, todos voltam a DESCONHECIDO (o fallback de arquitetura de 22/09)."""
    sem = [p for p in processor.SHEET_PATTERNS[SheetType.PONTOS] if p != _padrao_da_sigla()]
    assert len(sem) == len(processor.SHEET_PATTERNS[SheetType.PONTOS]) - 1
    monkeypatch.setitem(processor.SHEET_PATTERNS, SheetType.PONTOS, sem)
    assert processor.identify_sheet_type(nome) == SheetType.DESCONHECIDO, nome


@pytest.mark.parametrize("nome", [
    "TELEFONIA-01.pdf",          # "ele" dentro de "tele"
    "ELEVACAO FRONTAL.pdf",      # elevação não é elétrica
    "RELEVO_TERRENO.pdf",
    "HIDDEN LAYER TEST.pdf",     # "hid" dentro de palavra
    "INCORPORADORA - IMPLANTACAO.pdf",
    "PRINCIPAL-01.pdf",          # "inc" no meio
    "ELE01.pdf",                 # colado em número não é token separado
])
def test_CONTROLE_pedaco_de_palavra_nao_e_sigla(nome):
    assert processor.identify_sheet_type(nome) == SheetType.DESCONHECIDO, nome


# sigla -> a palavra por extenso que o motor JÁ reconhecia
_EQUIVALENTE = {"ele": "eletrica", "elet": "eletrico", "hid": "hidraulica",
                "hidr": "hidraulica", "inc": "incendio", "ppci": "incendio"}
# um nome em cada ponto da ordem de SHEET_PATTERNS (antes, junto e depois de PONTOS)
_MOLDES = ["PRJ-{}-01.pdf", "{} - DET BANH SUITE.pdf", "ARQUITETURA - {}.pdf",
           "DEMOLIR {} 01.pdf", "{} - PISO.pdf", "FORRO {}.pdf", "LAYOUT NOVO {}.pdf",
           "MARCENARIA {}.pdf"]


@pytest.mark.parametrize("sigla", sorted(_EQUIVALENTE))
@pytest.mark.parametrize("molde", _MOLDES)
def test_a_sigla_se_comporta_como_a_palavra_em_toda_posicao_da_ordem(sigla, molde):
    """ORDEM IMPORTA (topo de processor.py): a sigla entrou no MESMO lugar da
    palavra, então "ELE - DET BANH" continua detalhe de ambiente, como
    "ELETRICA - DET BANH" sempre foi, e "ARQUITETURA - ELE" continua arquitetura."""
    por_sigla = processor.identify_sheet_type(molde.format(sigla.upper()))
    por_extenso = processor.identify_sheet_type(molde.format(_EQUIVALENTE[sigla].upper()))
    assert por_sigla == por_extenso, (molde, sigla, por_sigla, por_extenso)


@pytest.mark.parametrize("nome,motivo", [
    ("PRJ-ARQ-01.pdf", "ARQ: o fallback já é o prompt de arquitetura; a sigla só apagaria o palpite de ambiente"),
    ("PRJ-EST-01.pdf", "EST: estrutura não é PONTOS; levar EST ao tipo ESTRUTURA é decisão do prompt de estrutura"),
    ("CLIM_OBRA_REV02-P01.pdf", "CLIM: não existe tipo de climatização"),
    ("0000-PE-MEC-XXX-01.pdf", "MEC: idem"),
    ("PRJ-SPDA-01.pdf", "SPDA: nem a palavra por extenso (para-raios) tem tipo"),
    ("PRJ-EL-01-PB-R00.pdf", "EL: também é abreviação de elevação"),
])
def test_as_siglas_SEM_tipo_no_motor_ficam_como_estavam(nome, motivo):
    assert processor.identify_sheet_type(nome) == SheetType.DESCONHECIDO, motivo


def test_SAN_de_nome_proprio_nao_vira_prancha_de_pontos():
    """SAN (sanitário) ficou de fora: "Residencial San Marino - Layout" é nome de
    empreendimento, e PONTOS vem ANTES de LAYOUT_NOVO na ordem."""
    assert processor.identify_sheet_type("RESIDENCIAL SAN MARINO - LAYOUT.pdf") == SheetType.LAYOUT_NOVO
