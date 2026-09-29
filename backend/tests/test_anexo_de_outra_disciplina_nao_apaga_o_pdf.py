# -*- coding: utf-8 -*-
"""Anexar o CAD de OUTRA disciplina não apaga o PDF que já estava no projeto.

🩸 29/09/2026 — job a5d54b42: projeto com o PDF da elétrica; a cliente anexou o
DWG da hidráulica. O anexo processa "só o CAD e descarta os PDFs" e a planilha
trocou 29 linhas de elétrica por 23 de hidráulica.
🔑 Descartar continua certo no caso comum (medido em 25 projetos com PDF e CAD
juntos): um DWG com todas as folhas + um PDF por folha, com nomes que não batem.
O que separa é a DISCIPLINA escrita nos dois nomes.
(Nomes de arquivo sintéticos, com a MESMA forma dos reais — nome de arquivo de
cliente é nome de cliente.)
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import engine_rules as er  # noqa: E402


def test_o_caso_eletrica_em_pdf_e_hidraulica_em_dwg():
    pdf = "/tmp/j/00000-PE-ELE-BLD-11111-ARC-P01-R00.pdf"
    dwg = "/tmp/j/00000-PE-HID-BLD-22222-EAP-P01-R01.dwg"
    assert er.pdfs_de_outra_disciplina([pdf], [dwg]) == [pdf]


@pytest.mark.parametrize("pdfs,cads", [
    # a mesma prancha em PDF e em CAD
    (["OBRA-ARQ-PL-003-A1-R01.pdf"], ["OBRA-ARQ-PL-003-A1-R01.dwg"]),
    # mesma disciplina, folhas diferentes: o DWG "geral" pode ter todas
    (["1000-SEG-EX-001-IMP-R00.pdf", "1000-SEG-EX-005-POR-R00.pdf"], ["1000-SEG-EX-000-GER-R00.dwg"]),
    (["1000-ELE-PL-005-DET-R00.pdf"], ["1000-ELE-PL-001-SIT-R00.dwg", "1000-ELE-PL-004-DET-R00.dwg"]),
    # um DWG com tudo, PDFs por folha, sem código de disciplina
    (["OBRA_2025_001_AMPLIACAO-R00-F02.pdf"], ["OBRA_2025_001_AMPLIACAO-R00.dwg"]),
    (["Folha 03.pdf", "MEMORIAL.PDF"], ["PROJETO 01 Rev B.dwg"]),
    # código num lado só: vale a regra antiga
    (["2_4_PLANTAS_assinado.pdf"], ["100001-OBRA-AP-EST-LOCFUN-R01.dwg"]),
    (["00000-PE-ELE-BLD-11111-ARC-P01-R00.pdf"], ["planta nova.dwg"]),
])
def test_CONTROLE_o_caso_comum_continua_descartando(pdfs, cads):
    assert er.pdfs_de_outra_disciplina(pdfs, cads) == []


def test_CONTROLE_um_dos_cads_da_mesma_disciplina_basta_pra_descartar():
    pdf = "X-ELE-01.pdf"
    assert er.pdfs_de_outra_disciplina([pdf], ["X-HID-02.dwg", "X-ELE-01.dwg"]) == []


def test_codigo_colado_em_numero_nao_conta_como_disciplina():
    """'HID05' é outro código (a folha 05 da hidráulica em outro padrão)."""
    assert er.disciplinas_no_nome("OBRA-PE-HID05-R03-TERREO.pdf") == frozenset()
    assert er.disciplinas_no_nome("/x/00000-PE-HID-BLD-22222.dwg") == frozenset({"HID"})
