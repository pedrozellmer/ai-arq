# -*- coding: utf-8 -*-
"""O aviso de escala diz quantas das cotas que batem têm número DIGITADO.

🩸 28/09/2026 (job dd52081b): o cliente leu "934 cotas batem com a geometria —
unidade do arquivo corrigida por elas". As 934 batem de fato, mas 931 eram
texto que o CAD escreve da própria medida — prova circular, como o motor já
sabe ("sem número digitado, no máximo confirma"). A prova independente foram 3
cotas digitadas pelo projetista. O cliente lê as duas.
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import main  # noqa: E402

MSG = ("unidade corrigida pelas cotas da prancha: fator 0.001 → 1 (metros) — provado por "
       "934 cotas (texto exibido × medida geométrica, ±2%), 3 delas com número digitado")


def test_o_extrator_conta_as_digitadas_que_provam(tmp_path, monkeypatch):
    # header diz METRO, desenho em cm; 4 cotas digitadas + 2 automáticas ("<>")
    import ezdxf
    import dwg_extractor as dx
    monkeypatch.setenv("LEITURA_POR_FOLHA", "0")
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    msp.add_line((0, 0), (350, 0))
    for k, (comp, txt) in enumerate(((350, "350"), (120, "120"), (415, "415"), (62, "62"),
                                     (280, "<>"), (190, "<>"))):
        # a automática mostra a própria medida (DIMLFAC 1; o estilo do ezdxf usa 100)
        d = msp.add_linear_dim(base=(0, -150 * k + 40), p1=(0, -150 * k), p2=(comp, -150 * k), text=txt,
                               override={"dimlfac": 1.0})
        d.render()
    p = str(tmp_path / "cotas.dxf")
    doc.saveas(p)
    msg = dx.extract_dxf(p).metadata.get("unidade_corrigida_por_cotas", "")
    assert "provado por 6 cotas" in msg and "4 delas com número digitado" in msg, msg


def test_o_resumo_le_as_digitadas():
    r = main._resumo_escala_arquivo("Prefeitura - R16.dxf", {"unidade_corrigida_por_cotas": MSG})
    assert r["n"] == 934 and r["digitadas"] == 3 and r["corrigida"], r


def test_o_aviso_diz_as_duas_coisas():
    r = main._resumo_escala_arquivo("Prefeitura - R16.dxf", {"unidade_corrigida_por_cotas": MSG})
    txt = " ".join(main._linhas_escala_projeto([r]))
    assert "934 cotas batem (3 com número digitado pelo projetista)" in txt, txt


def test_CONTROLE_mensagem_antiga_sem_digitadas_segue_como_era():
    velha = MSG.split(", 3 delas")[0]
    r = main._resumo_escala_arquivo("x.dxf", {"unidade_corrigida_por_cotas": velha})
    txt = " ".join(main._linhas_escala_projeto([r]))
    assert r["digitadas"] is None and "934 cotas batem com a geometria" in txt, txt


def test_CONTROLE_validada_sem_correcao_nao_ganha_o_parentese():
    r = main._resumo_escala_arquivo("x.dxf", {"unidade_validada_por_cotas": 304})
    txt = " ".join(main._linhas_escala_projeto([r]))
    assert "304 cotas batem com a geometria" in txt and "digitado" not in txt, txt
