# -*- coding: utf-8 -*-
"""O log do motor diz de onde vieram os blocos — e nenhum número muda.

📏 27/09/2026 (estudo de leitura, item 5). Seis consertos aprovados dependem de
medir antes: o descarte por CLASSE (`anonimo=N` juntava *X de hachura com *U
que é porta), o nome do bloco dinâmico por trás do *U, o INSERT espelhado, o
bloco de definição vazia, o que está em layer congelado ou desligado, e o que
as COTAS disseram quando o DIMLFAC ou a plausibilidade decidem a unidade.
"""
import os
import sys

import ezdxf

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402


def test_a_classe_do_anonimo():
    esperado = {"*U12": "*U", "*u3": "*U", "*X7": "*X", "*D4": "*outro",
                "PLANTA$0$MESA": "$0$", "A$C6BFD6B53": "A$C", "X-G$C12": "G$C",
                "zw$porta": "zw$", "BLOCO$1": "$outro"}
    for nome, classe in esperado.items():
        assert dx._classe_do_anonimo(nome) == classe, nome


def _arquivo(tmp_path):
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    doc.appids.new("AcDbBlockRepBTag")
    doc.blocks.new("PORTA-DINAMICA").add_line((0, 0), (0.9, 0))
    u = doc.blocks.new_anonymous_block("U")
    u.add_line((0, 0), (0.9, 0))
    doc.block_records.get(u.name).set_xdata(
        "AcDbBlockRepBTag", [(1070, 1), (1005, doc.block_records.get("PORTA-DINAMICA").dxf.handle)])
    for k in range(3):
        msp.add_blockref(u.name, (5 * k, 0))
    doc.blocks.new("TOMADA").add_circle((0, 0), 0.2)
    msp.add_blockref("TOMADA", (-3, 1), dxfattribs={"extrusion": (0, 0, -1)})
    msp.add_blockref("TOMADA", (4, 1))
    doc.blocks.new("SO-NOME")                     # definição vazia (conversor)
    msp.add_blockref("SO-NOME", (8, 1))
    doc.layers.add("BASE-CONGELADA").freeze()
    doc.blocks.new("PILAR-X").add_circle((0, 0), 0.2)
    msp.add_blockref("PILAR-X", (9, 9), dxfattribs={"layer": "BASE-CONGELADA"})
    p = str(tmp_path / "procedencia.dxf")
    doc.saveas(p)
    return p


def test_a_procedencia_chega_ao_metadata_e_a_contagem_fica(tmp_path, monkeypatch):
    monkeypatch.setenv("LEITURA_POR_FOLHA", "0")
    ex = dx.extract_dxf(_arquivo(tmp_path))
    pb = ex.metadata["procedencia_blocos"]
    assert pb["anonimos"] == {"*U": 3}, pb
    assert pb["dinamicos"] == {"PORTA-DINAMICA": 3}, pb
    assert pb["espelhados"] == {"TOMADA": 1}, pb
    assert pb["def_vazia"] == {"SO-NOME": 1}, pb
    assert ex.metadata["em_layer_desligado"]["blocos"] == 1, ex.metadata.get("em_layer_desligado")
    # só registro: a contagem é a mesma de antes
    assert ex.get_block_summary() == {"TOMADA": 2, "SO-NOME": 1, "PILAR-X": 1}


def test_a_linha_do_log_leva_a_procedencia():
    import main as m

    class _Ex:
        metadata = {"procedencia_blocos": {"anonimos": {"*U": 3, "*X": 40},
                                           "dinamicos": {"PORTA-DINAMICA": 3}},
                    "em_layer_desligado": {"m": 12.5, "m2": 0.0, "blocos": 4}}
    s = m._procedencia_dos_blocos(_Ex())
    assert "anonimos=[*U=3|*X=40]" in s and "dinamicos=[PORTA-DINAMICA=3]" in s, s
    assert "layer_desligado=[m=12.5|m2=0.0|blocos=4]" in s, s

    class _Nada:
        metadata = {}
    assert m._procedencia_dos_blocos(_Nada()) == ""
    assert m._procedencia_dos_blocos(object()) == ""


def test_o_que_as_cotas_disseram_sobrevive_ao_dimlfac(tmp_path, monkeypatch):
    monkeypatch.setenv("LEITURA_POR_FOLHA", "0")
    monkeypatch.setattr(dx, "_validate_unit_by_dimensions",
                        lambda *a, **k: {"status": None, "cotas_utilizaveis": 7,
                                         "motivo": "sem consenso (3/7)"})
    monkeypatch.setattr(dx, "_unidade_por_dimlfac",
                        lambda *a, **k: {"status": "corrigida_lfac", "fator_corrigido": 1.0,
                                         "mensagem": "DIMLFAC prova metro"})
    ex = dx.extract_dxf(_arquivo(tmp_path))
    assert ex.metadata["regua_cotas_antes"] == "-|7|sem consenso (3/7)", ex.metadata.get("regua_cotas_antes")


def test_CONTROLE_sem_troca_de_regua_nao_ha_antes(tmp_path, monkeypatch):
    monkeypatch.setenv("LEITURA_POR_FOLHA", "0")
    ex = dx.extract_dxf(_arquivo(tmp_path))
    assert "regua_cotas_antes" not in ex.metadata
