# -*- coding: utf-8 -*-
"""O peso nos BLOCOS não derruba a prancha: o resgate esvazia o que o desenho não usa.

🩸 28/09/2026 — caso 18c57c3c. DWG de 59,7 MB, o ODA recusou ("XData size
exceeded"), o libredwg deu um DXF de 511 MB: 493 MB em BLOCKS, que o emagrecedor
copiava INTACTOS. Prancha única do projeto → erro, e a tela prometeu "já estamos
resolvendo". Medido no arquivo: 186 MB de definição que o desenho não insere,
61 MB de OLE, 38 MB de XDATA que o motor não lê. Esvaziando só isso: 511 -> 228
MB, e a extração saiu IDÊNTICA à do arquivo inteiro (campo a campo e o texto que
vai pra IA).

Aqui o mesmo, num DXF de laboratório: o que sai, o que FICA, e a extração igual.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dxf_slim  # noqa: E402
import dwg_extractor  # noqa: E402


def _ole(onde):
    """OLE2FRAME com conteúdo binário de verdade (códigos 310), como o AutoCAD
    grava. O `new_entity` do ezdxf sozinho sai sem nada — não serviria de prova."""
    from ezdxf.lldxf.tags import Tags
    from ezdxf.lldxf.types import DXFBinaryTag, DXFTag, DXFVertex
    binario = bytes(range(256)) * 40
    ole = onde.new_entity("OLE2FRAME", {"layer": "0"})
    ole.acdb_ole2frame = Tags(
        [DXFTag(100, "AcDbOle2Frame"), DXFTag(70, 2), DXFTag(3, "Paintbrush Picture"),
         DXFVertex(10, (0, 3, 0)), DXFVertex(11, (4, 0, 0)), DXFTag(71, 2), DXFTag(72, 0),
         DXFTag(90, len(binario))]
        + [DXFBinaryTag(310, binario[i:i + 127]) for i in range(0, len(binario), 127)]
        + [DXFTag(1, "OLE")])
    return ole


def _laboratorio(pasta, sobra_linhas=400):
    """Modelo com um bloco usado (que usa um neto), uma folha inativa com outro
    bloco, uma cota, e um bloco GRANDE que ninguém insere (que usa outro)."""
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6          # metros
    doc.appids.new("REVIT")
    doc.appids.new("ACAD_OBJECT_CHANGE_GUID")
    msp = doc.modelspace()

    neto = doc.blocks.new("NETO")
    neto.add_circle((0, 0), 0.2, dxfattribs={"layer": "ELE-LUMINARIA"})
    usado = doc.blocks.new("USADO")
    usado.add_line((0, 0), (4, 0), dxfattribs={"layer": "PAREDE"})
    ln = usado.add_line((4, 0), (4, 3), dxfattribs={"layer": "PAREDE"})
    ln.set_xdata("REVIT", [(1000, "x" * 200)])
    ln.set_xdata("ACAD", [(1000, "DSTYLE"), (1002, "{"), (1070, 40), (1040, 0.25), (1002, "}")])
    usado.add_spline([(0, 0), (1, 1), (2, 0), (3, 1)], dxfattribs={"layer": "PAREDE"})
    usado.add_blockref("NETO", (2, 1.5))
    _ole(usado)

    folha_blk = doc.blocks.new("NA_FOLHA")
    folha_blk.add_line((0, 0), (1, 1))

    filho_da_sobra = doc.blocks.new("FILHO_DA_SOBRA")
    filho_da_sobra.add_line((0, 0), (9, 9))
    sobra = doc.blocks.new("SOBRA")
    sobra.block.set_xdata("REVIT", [(1000, "y" * 300)])   # na própria definição
    for i in range(sobra_linhas):
        sobra.add_line((i, 0), (i, 5), dxfattribs={"layer": "RACK"})
    sobra.add_blockref("FILHO_DA_SOBRA", (0, 0))

    for x in (0, 10, 20):
        msp.add_blockref("USADO", (x, 0))
    msp.add_line((0, -1), (30, -1), dxfattribs={"layer": "PAREDE"})
    msp.add_text("PLANTA BAIXA", dxfattribs={"height": 0.3}).set_placement((0, -2))
    msp.add_linear_dim(base=(0, -3), p1=(0, -1), p2=(30, -1)).render()
    msp.new_entity("OLE2FRAME", {"layer": "0"})

    doc.layouts.new("INATIVA").add_blockref("NA_FOLHA", (5, 5))
    caminho = os.path.join(str(pasta), "lab_libredwg.dxf")
    doc.saveas(caminho)
    return caminho


def _conteudo(doc, nome):
    return [e.dxftype() for e in doc.blocks.get(nome)]


# ── o que sai e o que fica ─────────────────────────────────────────────────
def test_o_alcance_segue_o_desenho(tmp_path):
    nomes, alc, _prev = dxf_slim.alcance_dos_blocos(_laboratorio(tmp_path))
    for n in (b"usado", b"neto", b"na_folha", b"*model_space"):
        assert n in alc, (n, sorted(alc))
    assert any(n.startswith(b"*d") for n in alc), "o bloco da cota saiu do alcance"
    assert b"sobra" not in alc and b"filho_da_sobra" not in alc, sorted(alc)


def test_o_resgate_esvazia_so_o_que_o_desenho_nao_usa(tmp_path):
    src = _laboratorio(tmp_path)
    out = str(tmp_path / "lab.slim.dxf")
    _n, alc, prev = dxf_slim.alcance_dos_blocos(src)
    dxf_slim.emagrecer_blocos_por_texto(src, out, alc)
    assert os.path.getsize(out) == prev, "a previsão não bate com o que foi escrito"
    doc = ezdxf.readfile(out)
    assert _conteudo(doc, "SOBRA") == [] and _conteudo(doc, "FILHO_DA_SOBRA") == []
    usado = _conteudo(doc, "USADO")
    assert usado.count("LINE") == 2 and "SPLINE" in usado and "INSERT" in usado, usado
    # 🪤 a ENTIDADE fica (a assinatura do bloco conta o tipo); o binário, não
    ole = [e for e in doc.blocks.get("USADO") if e.dxftype() == "OLE2FRAME"]
    assert len(ole) == 1 and ole[0].binary_data() == b"", "o conteúdo binário do OLE ficou"
    assert tuple(ole[0].bbox().extmax) == (4, 3, 0), "os cantos do OLE sumiram junto"
    orig = [e for e in ezdxf.readfile(src).blocks.get("USADO") if e.dxftype() == "OLE2FRAME"]
    assert len(orig[0].binary_data()) == 10240, "CONTROLE: o laboratório perdeu o binário"
    assert _conteudo(doc, "NETO") == ["CIRCLE"] and _conteudo(doc, "NA_FOLHA") == ["LINE"]
    assert not [e for e in doc.modelspace() if e.dxftype() == "OLE2FRAME"]


def test_o_xdata_que_o_motor_le_fica_e_o_resto_sai(tmp_path):
    src = _laboratorio(tmp_path)
    out = str(tmp_path / "lab.slim.dxf")
    dxf_slim.emagrecer_blocos_por_texto(src, out, dxf_slim.alcance_dos_blocos(src)[1])
    ln = [e for e in ezdxf.readfile(out).blocks.get("USADO") if e.dxftype() == "LINE"][1]
    assert not ln.has_xdata("REVIT")
    assert ln.has_xdata("ACAD"), "o DSTYLE da cota é lido pelo motor — não pode sair"


def test_a_extracao_do_resgatado_e_a_MESMA(tmp_path):
    """🔑 A prova que decide: o motor não pode ver diferença nenhuma."""
    src = _laboratorio(tmp_path)
    out = str(tmp_path / "lab.slim.dxf")
    dxf_slim.emagrecer_blocos_por_texto(src, out, dxf_slim.alcance_dos_blocos(src)[1])
    a = dwg_extractor.extract_from_file(src)
    b = dwg_extractor.extract_from_file(out)
    for campo in vars(a):
        if campo == "filename":
            continue
        assert repr(getattr(a, campo)) == repr(getattr(b, campo)), campo
    ta = a.to_structured_prompt().split("\n", 1)[1]
    tb = b.to_structured_prompt().split("\n", 1)[1]
    assert ta == tb


def test_citacao_por_ponteiro_e_por_nome_sem_caixa(tmp_path):
    """Bloco citado só por ponteiro (340) ao BLOCK_RECORD, ou por nome com outra
    caixa de letra, continua alcançado. Na dúvida, fica."""
    pares = [
        ("0", "SECTION"), ("2", "TABLES"), ("0", "TABLE"), ("2", "BLOCK_RECORD"),
        ("0", "BLOCK_RECORD"), ("5", "1A"), ("2", "Chamada"),
        ("0", "BLOCK_RECORD"), ("5", "1B"), ("2", "Porta"),
        ("0", "BLOCK_RECORD"), ("5", "1C"), ("2", "Esquecido"),
        ("0", "ENDTAB"), ("0", "ENDSEC"),
        ("0", "SECTION"), ("2", "BLOCKS"),
        ("0", "BLOCK"), ("2", "Chamada"), ("0", "LINE"), ("8", "0"), ("0", "ENDBLK"),
        ("0", "BLOCK"), ("2", "Porta"), ("0", "LINE"), ("8", "0"), ("0", "ENDBLK"),
        ("0", "BLOCK"), ("2", "Esquecido"), ("0", "LINE"), ("8", "0"), ("0", "ENDBLK"),
        ("0", "ENDSEC"),
        ("0", "SECTION"), ("2", "ENTITIES"),
        ("0", "MULTILEADER"), ("8", "0"), ("344", "1a"),
        ("0", "INSERT"), ("8", "0"), ("2", "PORTA"),
        ("0", "ENDSEC"), ("0", "EOF"),
    ]
    p = tmp_path / "ponteiro.dxf"
    p.write_bytes("".join("%s\n%s\n" % par for par in pares).encode("ascii"))
    _n, alc, _prev = dxf_slim.alcance_dos_blocos(str(p))
    assert b"chamada" in alc and b"porta" in alc and b"esquecido" not in alc, sorted(alc)


# ── quando age: só acima da trava dura ─────────────────────────────────────
@pytest.fixture
def logs():
    lista = []
    return lista


def _log(lista):
    return lambda stage, msg: lista.append((stage, msg))


def test_acima_da_trava_o_plano_B_resgata_pelos_blocos(tmp_path, monkeypatch, logs):
    """O caminho de TODO DWG do libredwg: o ezdxf quebra e cai no filtro textual."""
    src = _laboratorio(tmp_path, sobra_linhas=3000)
    size = os.path.getsize(src)
    prev = dxf_slim.alcance_dos_blocos(src)[2]
    monkeypatch.setattr(dxf_slim, "_LIMITE_DURO", (size + prev) // 2)
    import ezdxf.addons.iterdxf as _it
    monkeypatch.setattr(_it, "opendxf", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("dictionary handle #X not resolved")))
    novo = dxf_slim.emagrecer_dxf_se_preciso(src, limiar_mb=0, log=_log(logs))
    assert novo and novo.endswith("lab_libredwg.slim.dxf"), novo
    assert os.path.getsize(novo) <= dxf_slim._LIMITE_DURO
    assert not os.path.exists(src), "o original tem que sair assim que o enxuto serve (disco)"
    assert any("RESGATE PELOS BLOCOS" in m for _s, m in logs), logs
    assert ezdxf.readfile(novo).blocks.get("SOBRA") is not None


def test_acima_da_trava_o_caminho_do_ezdxf_tambem_resgata(tmp_path, monkeypatch, logs):
    src = _laboratorio(tmp_path, sobra_linhas=3000)
    size = os.path.getsize(src)
    prev = dxf_slim.alcance_dos_blocos(src)[2]
    monkeypatch.setattr(dxf_slim, "_LIMITE_DURO", (size + prev) // 2)
    novo = dxf_slim.emagrecer_dxf_se_preciso(src, limiar_mb=0, log=_log(logs))
    assert novo and os.path.getsize(novo) <= dxf_slim._LIMITE_DURO, novo
    assert any("RESGATE PELOS BLOCOS" in m for _s, m in logs), logs


def test_se_o_resgate_nao_cabe_nada_e_escrito(tmp_path, monkeypatch, logs):
    src = _laboratorio(tmp_path, sobra_linhas=3000)
    prev = dxf_slim.alcance_dos_blocos(src)[2]
    monkeypatch.setattr(dxf_slim, "_LIMITE_DURO", prev - 1)
    import ezdxf.addons.iterdxf as _it
    monkeypatch.setattr(_it, "opendxf", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    assert dxf_slim.emagrecer_dxf_se_preciso(src, limiar_mb=0, log=_log(logs)) is None
    assert os.path.exists(src)
    assert not [f for f in os.listdir(str(tmp_path)) if f.endswith(".slim.dxf")]
    assert any("NÃO cabe" in m for _s, m in logs), logs


def test_CONTROLE_abaixo_da_trava_os_blocos_nao_sao_tocados(tmp_path, monkeypatch, logs):
    """O caminho que funciona não muda: abaixo da trava dura, nem se mede."""
    src = _laboratorio(tmp_path, sobra_linhas=3000)
    monkeypatch.setattr(dxf_slim, "alcance_dos_blocos",
                        lambda *a, **k: pytest.fail("mexeu nos blocos abaixo da trava"))
    import ezdxf.addons.iterdxf as _it
    monkeypatch.setattr(_it, "opendxf", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    novo = dxf_slim.emagrecer_dxf_se_preciso(src, limiar_mb=0, log=_log(logs))
    if novo:
        assert len(ezdxf.readfile(novo).blocks.get("SOBRA")) == 3001


def test_SPLINE_fica_porque_muda_a_assinatura_do_bloco(tmp_path):
    """🪤 Medido no caso: tirar SPLINE de dentro dos blocos mudou a `assinatura`
    (que casa bloco com legenda). Parece lastro; não é."""
    src = _laboratorio(tmp_path)
    out = str(tmp_path / "lab.slim.dxf")
    dxf_slim.emagrecer_blocos_por_texto(src, out, dxf_slim.alcance_dos_blocos(src)[1])
    assert "SPLINE" in _conteudo(ezdxf.readfile(out), "USADO")
