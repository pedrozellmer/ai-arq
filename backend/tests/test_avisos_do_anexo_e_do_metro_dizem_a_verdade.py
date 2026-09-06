# -*- coding: utf-8 -*-
"""Dois avisos pro cliente que mentiam — e o que cada um pode dizer agora.

🩸 05/09/2026, Pedro: *"os dois textos errados pro cliente"*.
  1. Complemento com 0 itens dizia "O arquivo que você anexou (o arquivo) foi lido,
     mas não rendeu nenhum item — pode ser prancha só de layout ou PDF escaneado".
     No caso do cliente-39 (19:24) NADA tinha sido lido (as duas regras do anexo se
     anularam) e o nome virou o placeholder "o arquivo". Chutar causa pra falha
     que a gente não viu é o mesmo defeito do "não consegui medir" de 03/09.
  2. "Preencha esses metros ou mande o DXF que a gente mede" — e "comprimento
     tirado de PDF" — saíam pra quem JÁ tinha mandado o CAD. O mesmo vale pro
     aviso do teto por prancha ("ou envie o DXF pra medirmos").

Regra: o texto sai de UMA função, com o fato na mão (o que entrou, se a leitura
falhou, se tinha CAD). 🧪 Controles: com CAD, nenhuma menção a DXF/PDF; sem CAD,
o pedido do DXF continua — ele é verdadeiro ali.
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import main  # noqa: E402
from _corpo import fonte, sem_comentarios  # noqa: E402

_SRC = sem_comentarios(fonte("main.py"))


# ── 1. complemento sem itens: três situações, três verdades ────────────────
def test_nada_entrou_NAO_diz_que_foi_lido_nem_inventa_nome():
    t = main._aviso_complemento_sem_itens([], [])
    assert "Nenhum arquivo novo entrou" in t
    assert "foi lido" not in t and "(o arquivo)" not in t
    assert "nada foi perdido" in t


def test_leitura_que_falhou_diz_nao_consegui_ler_com_o_nome():
    t = main._aviso_complemento_sem_itens(["/tmp/x/HNSC-A01.dwg"], ["RuntimeError: extração falhou"])
    assert t.startswith("Não consegui ler o arquivo que você anexou (HNSC-A01.dwg)")
    assert "foi lido" not in t and "layout" not in t, "não chuta causa pra falha que não viu"
    assert "nada foi perdido" in t


def test_lido_sem_item_e_o_unico_caso_do_foi_lido():
    t = main._aviso_complemento_sem_itens(["/tmp/x/planta.pdf"], [])
    assert "(planta.pdf) foi lido, mas não rendeu nenhum item" in t
    assert "nada foi perdido" in t


def test_o_process_job_usa_o_texto_unico_e_o_placeholder_morreu():
    assert _SRC.count("_aviso_complemento_sem_itens(") == 2, "def + a chamada no process_job"
    assert "or 'o arquivo'" not in _SRC, "o placeholder 'o arquivo' voltou"
    # a frase também é CITADA na docstring do helper (pra explicar por que só ali cabe);
    # o que tem que ser único é o texto que SAI — a f-string do return.
    assert _SRC.count("foi lido, mas não rendeu nenhum item \"") == 1, "o texto tem que morar num lugar só"


# ── 2. metro sem quantidade: com CAD, sem pedir DXF ────────────────────────
def test_com_cad_NAO_pede_dxf_nem_fala_de_pdf():
    t = main._aviso_lineares_zerados(9, True)
    assert t.startswith("⚠ 9 item(ns) em METRO")
    assert "DXF" not in t and "PDF" not in t
    assert "Preencha esses metros" in t


def test_CONTROLE_sem_cad_o_pedido_do_dxf_continua_porque_e_verdade():
    t = main._aviso_lineares_zerados(9, False)
    assert "mande o DXF que a gente mede" in t and "tirado de PDF" in t


def test_o_process_job_decide_pelo_cad_do_envio():
    assert _SRC.count("_aviso_lineares_zerados(") == 2, "def + a chamada no process_job"
    i = _SRC.find("_aviso_lineares_zerados(_lz, _tem_cad_lz)")
    assert i > 0 and "_tem_cad_lz = bool(cad_paths)" in _SRC[i - 600:i], (
        "a decisão tem que olhar o CAD do envio (cad_paths), não um chute")
    assert _SRC.count("mande o DXF que a gente") == 1, "o texto antigo voltou pro process_job"


def test_o_teto_por_prancha_segue_a_mesma_regra():
    i = _SRC.find("Preencha a metragem na revisão.")
    assert i > 0, "sumiu a variante com CAD do aviso do teto"
    assert "_tem_cad_teto = bool(cad_paths)" in _SRC[i - 1200:i]
    assert 'else "Preencha a metragem ou envie o DXF pra medirmos."' in _SRC[i:i + 200]
