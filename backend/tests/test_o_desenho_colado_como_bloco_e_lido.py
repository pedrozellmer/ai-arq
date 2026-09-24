# -*- coding: utf-8 -*-
"""O desenho colado como bloco (A$C…) é lido como se estivesse solto.

🩸 24/09/2026, job 09e2e640. Prédio de 12 pavimentos, 10 pranchas: 2.070
entidades soltas e 75.472 dentro de 140 blocos A$C (o "Colar como bloco" do
AutoCAD), aninhados até 4 níveis. O motor só lia o modelspace e descartava
`A$C` na contagem de bloco — 0 medidas, 36 de 42 linhas em branco.
Medido no arquivo real com o conserto: hachuras 1 → 1.660, cotas 5 → 2.399
(a régua da unidade passou a validar o metro com 2.322), pilares 0 → 299,
portas P70/P80/P90 contadas pelo nome (72/57/34).

Estes guardas montam um DXF de verdade e passam pelo `extract_dxf` inteiro.
"""
import os
import sys

import ezdxf
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dwg_extractor as dx  # noqa: E402


def _dxf_colado(tmp_path, com_porta_solta=False):
    """Folha com uma planta COLADA: A$C externo → A$C interno → porta P80.

    - hachura de 3 m × 4 m (12 m²) dentro do A$C externo;
    - uma porta P80 no externo e outra no interno (2 portas no total);
    - o externo entra no modelspace deslocado de (100, 0).
    """
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6            # metros
    porta = doc.blocks.new("P80")
    porta.add_line((0, 0), (0.8, 0))
    interno = doc.blocks.new("A$C00ABC123")
    interno.add_blockref("P80", (5, 5))
    interno.add_line((0, 0), (6, 0), dxfattribs={"layer": "PAREDE"})
    externo = doc.blocks.new("A$C4D0C1EB0")
    h = externo.add_hatch(dxfattribs={"layer": "PISO"})
    h.paths.add_polyline_path([(0, 0), (3, 0), (3, 4), (0, 4)], is_closed=True)
    externo.add_blockref("P80", (1, 1))
    externo.add_blockref("A$C00ABC123", (10, 0))
    msp = doc.modelspace()
    msp.add_blockref("A$C4D0C1EB0", (100, 0))
    if com_porta_solta:
        msp.add_blockref("P80", (200, 0))
    p = tmp_path / "planta-colada.dxf"
    doc.saveas(p)
    return str(p)


def _portas(ext):
    return sum(b.count for b in (ext.blocks or []) if b.name == "P80")


def _area(ext):
    return sum(getattr(h, "area", 0) or 0 for h in (ext.hatches or []))


def test_o_desenho_COLADO_e_lido_como_se_estivesse_solto(tmp_path, monkeypatch):
    monkeypatch.setenv("DXF_ABRIR_BLOCOS_COLADOS", "1")
    ext = dx.extract_dxf(_dxf_colado(tmp_path))
    assert _portas(ext) == 2, "as duas portas P80 (uma em cada nível) — %r" % ext.blocks
    assert abs(_area(ext) - 12.0) < 0.01, "a hachura de 12 m² de dentro do bloco"
    assert ext.blocos_colados.get("abertos") == 2, ext.blocos_colados
    assert ext.blocos_colados.get("niveis") == 2, ext.blocos_colados
    assert ext.blocos_colados.get("falhas") == 0, ext.blocos_colados


def test_CONTROLE_sem_abrir_o_bloco_o_desenho_some(tmp_path, monkeypatch):
    """O mesmo arquivo com a chave desligada: é o motor de antes. Se este
    passar a achar as portas, o guarda de cima deixou de provar o conserto."""
    monkeypatch.setenv("DXF_ABRIR_BLOCOS_COLADOS", "0")
    ext = dx.extract_dxf(_dxf_colado(tmp_path))
    assert _portas(ext) == 0
    assert _area(ext) == 0
    assert ext.blocos_colados == {}


def test_a_porta_SOLTA_nao_dobra_ao_lado_da_colada(tmp_path, monkeypatch):
    """Bloco com nome de verdade continua bloco: é contado UMA vez pelo nome,
    seja solto na folha ou vindo de dentro do colado."""
    monkeypatch.setenv("DXF_ABRIR_BLOCOS_COLADOS", "1")
    ext = dx.extract_dxf(_dxf_colado(tmp_path, com_porta_solta=True))
    assert _portas(ext) == 3, "1 solta + 2 de dentro do colado — %r" % ext.blocks


def test_so_A_C_e_aberto_bloco_dinamico_e_bloco_com_cifrao_ficam(tmp_path):
    doc = ezdxf.new("R2018")
    for nome in ("*U7", "MEU$BLOCO", "A$Cxyz"):   # A$Cxyz: não é hexadecimal
        try:
            b = doc.blocks.new(nome)
        except Exception:
            continue
        b.add_line((0, 0), (1, 0))
        doc.modelspace().add_blockref(nome, (0, 0))
    antes = len(doc.modelspace().query("INSERT"))
    assert dx.abrir_blocos_colados(doc) == {}
    assert len(doc.modelspace().query("INSERT")) == antes


def test_bloco_que_nao_explode_fica_como_estava_e_nao_derruba(tmp_path, monkeypatch):
    doc = ezdxf.readfile(_dxf_colado(tmp_path))

    def _recusa(self, *a, **k):
        raise ezdxf.DXFError("escala não-uniforme")

    monkeypatch.setattr(ezdxf.entities.Insert, "explode", _recusa)
    info = dx.abrir_blocos_colados(doc)
    assert info.get("falhas") == 1 and info.get("abertos") == 0, info
    assert len(doc.modelspace().query("INSERT")) == 1, "o colado continua lá, intacto"


def test_o_teto_de_entidades_para_a_abertura(tmp_path, monkeypatch):
    monkeypatch.setattr(dx, "_MAX_ENTIDADES_COLADAS", 1)
    doc = ezdxf.readfile(_dxf_colado(tmp_path))
    info = dx.abrir_blocos_colados(doc)
    assert info.get("teto") is True, info
    assert info.get("abertos") == 1, "abriu o externo e parou antes do interno — %r" % info


@pytest.mark.parametrize("valor", ["0"])
def test_a_chave_desliga_sem_deploy(tmp_path, monkeypatch, valor):
    monkeypatch.setenv("DXF_ABRIR_BLOCOS_COLADOS", valor)
    doc = ezdxf.readfile(_dxf_colado(tmp_path))
    assert dx.abrir_blocos_colados(doc) == {}
    assert len(doc.modelspace().query("INSERT")) == 1


def test_o_log_do_motor_diz_quanto_foi_aberto():
    import types
    import main
    ext = types.SimpleNamespace(blocos_colados={"abertos": 979, "entidades": 40580,
                                                "niveis": 4, "falhas": 0, "teto": False})
    txt = main._blocos_colados_abertos(ext)
    assert "abertos=979" in txt and "niveis=4" in txt and txt.startswith(" colados=["), txt
    assert main._blocos_colados_abertos(types.SimpleNamespace(blocos_colados={})) == ""
