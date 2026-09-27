# -*- coding: utf-8 -*-
"""DXF do libredwg com QUEBRA DE LINHA CRUA dentro de um texto: o motor abre.

🩸 27/09/2026 — CLIENTE QUE VOLTOU, A MESMA PLANTA DUAS VEZES. Em 16/09 e hoje
ele subiu a planta + detalhes do projeto (R16 e R17, 955 m²). O ODA recusou pela
tabela de estilos; o libredwg assumiu e leu um MTEXT ("Nº de chapas de gesso /
12,5 ou 15 mm") ALÉM do fim — o lixo de memória trouxe uma quebra de linha crua.
Todo DXF ASCII é uma fila de PARES (código, valor), uma linha cada: a quebra
empurra o resto do arquivo uma linha, e os DOIS degraus caem:

    normal:  Invalid group code "12,5 ou 15 mm…" at line 3015621
    recover: Invalid group code "Embedded Object" at line 3015629

As duas vezes o cliente leu "problema técnico do nosso lado" e desistiu da
planta — mandou só os detalhes avulsos.

🔑 O 4º degrau: depois de cada valor, a linha que NÃO pode ser código de grupo é
continuação do valor e volta pra ele. Provado no arquivo do cliente (com a
quebra injetada, porque o lixo muda de máquina pra máquina): abre e entrega as
mesmas 6.400 entidades, 1.426 blocos e 100 layers do DXF sadio.

🚨 Estes guardas abrem ARQUIVO DE VERDADE (montado com ezdxf, sem nada do
cliente) e o controle positivo é a GEOMETRIA.
"""
import io
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

from dxf_open import (_dxf_com_textos_emendados, _e_codigo_de_grupo,  # noqa: E402
                      recuperar_dxf)

NL = chr(10)
_ESPERADO = ["LINE", "TEXT", "LWPOLYLINE"]


def _dxf_bom(tmp_path, tipo="text", nome="bom.dxf"):
    d = ezdxf.new("R2013")
    msp = d.modelspace()
    msp.add_line((0, 0), (10, 0))
    if tipo == "mtext":
        msp.add_mtext("MARCA_QUEBRA fim do texto")
    else:
        msp.add_text("MARCA_QUEBRA fim do texto")
    msp.add_lwpolyline([(0, 0), (5, 0), (5, 5), (0, 5), (0, 0)])
    p = str(tmp_path / nome)
    d.saveas(p)
    return p


def _quebra(caminho_bom, destino, soltas=1):
    """O texto como o libredwg escreveu: `soltas` linhas a mais, cruas."""
    txt = io.open(caminho_bom, encoding="utf-8").read()
    assert "MARCA_QUEBRA " in txt, "o DXF de teste mudou de forma"
    pedacos = ["Chapas de gesso", "12,5 ou 1 "] + ["lixo %d " % i for i in range(soltas - 1)]
    io.open(destino, "w", encoding="utf-8", newline=NL).write(
        txt.replace("MARCA_QUEBRA ", NL.join(pedacos)))
    return destino


# ── o caso do cliente ──────────────────────────────────────────────────────
@pytest.mark.parametrize("tipo", ["text", "mtext"])
def test_CONTROLE_o_arquivo_quebrado_REALMENTE_derruba_os_dois_degraus(tmp_path, tipo):
    """🧪 Sem isto os guardas de baixo passariam provando que abre um arquivo
    que nunca esteve quebrado — ou que o `recover` já salvava."""
    ruim = _quebra(_dxf_bom(tmp_path, tipo), str(tmp_path / "ruim.dxf"))
    with pytest.raises(Exception) as e1:
        ezdxf.readfile(ruim)
    assert "invalid group code" in str(e1.value).lower()
    import ezdxf.recover as _rec
    with pytest.raises(Exception) as e2:
        _rec.readfile(ruim)
    assert "invalid group code" in str(e2.value).lower(), (
        "o recover passou a salvar este caso — o 4º degrau virou desnecessário")


@pytest.mark.parametrize("tipo", ["text", "mtext"])
def test_o_RECUPERAR_DXF_abre_e_a_geometria_sobrevive_inteira(tmp_path, tipo):
    """É o ponto que TODAS as portas compartilham (a armadilha de 23/09)."""
    bom = _dxf_bom(tmp_path, tipo)
    ruim = _quebra(bom, str(tmp_path / "ruim.dxf"))
    doc = recuperar_dxf(ruim, "DXFStructureError: Invalid group code")
    esperado = [e.dxftype() for e in ezdxf.readfile(bom).modelspace()]
    assert [e.dxftype() for e in doc.modelspace()] == esperado


def test_o_texto_volta_inteiro_com_o_pedaco_que_tinha_escapado(tmp_path):
    ruim = _quebra(_dxf_bom(tmp_path), str(tmp_path / "ruim.dxf"))
    doc = recuperar_dxf(ruim, "Invalid group code")
    txt = [e.dxf.text for e in doc.modelspace() if e.dxftype() == "TEXT"]
    assert txt == ["Chapas de gesso 12,5 ou 1 fim do texto"], txt


def test_o_caminho_do_MOTOR_abre_o_arquivo_quebrado(tmp_path):
    """🚨 `dwg_extractor.extract_from_file` é o que roda no worker isolado."""
    from dwg_extractor import extract_from_file
    ruim = _quebra(_dxf_bom(tmp_path), str(tmp_path / "ruim_motor.dxf"))
    assert extract_from_file(ruim) is not None


def test_varias_linhas_soltas_voltam_todas(tmp_path):
    bom = _dxf_bom(tmp_path)
    ruim = _quebra(bom, str(tmp_path / "ruim3.dxf"), soltas=3)
    assert _dxf_com_textos_emendados(ruim, str(tmp_path / "em3.dxf")) == 3
    assert [e.dxftype() for e in ezdxf.readfile(str(tmp_path / "em3.dxf")).modelspace()] == _ESPERADO


def test_os_dois_defeitos_no_mesmo_arquivo(tmp_path):
    """Texto quebrado E a SORTENTSTABLE torta (o 3º degrau) juntos."""
    _SORTENTS_TORTA = NL.join([          # como o libredwg escreve: 331 sem o 5
        "0", "SORTENTSTABLE", "5", "2AA", "330", "1F",
        "100", "AcDbSortentsTable", "331", "2AB", "331", "2AC"])
    ruim = _quebra(_dxf_bom(tmp_path), str(tmp_path / "ruim.dxf"))
    txt = io.open(ruim, encoding="utf-8").read()
    i = txt.rfind(NL.join(["0", "ENDSEC"]))
    duplo = str(tmp_path / "duplo.dxf")
    io.open(duplo, "w", encoding="utf-8", newline=NL).write(
        txt[:i] + _SORTENTS_TORTA + NL + txt[i:])
    doc = recuperar_dxf(duplo, "Invalid group code")
    assert [e.dxftype() for e in doc.modelspace()] == _ESPERADO


# ── controles positivos ────────────────────────────────────────────────────
def test_CONTROLE_arquivo_SADIO_sai_identico(tmp_path):
    bom = _dxf_bom(tmp_path)
    saida = str(tmp_path / "igual.dxf")
    assert _dxf_com_textos_emendados(bom, saida) == 0
    assert open(bom, "rb").read() == open(saida, "rb").read(), (
        "mexeu num arquivo que não tinha quebra nenhuma")


def test_CONTROLE_o_que_e_e_o_que_nao_e_codigo_de_grupo():
    for sim in (b"  0\r\n", b"  1\n", b"1071\n", b"999\n", b" 10\r\n"):
        assert _e_codigo_de_grupo(sim), sim
    for nao in (b"12,5 ou 1 \n", b"AcDbText\n", b"1072\n", b"-1\n", b"\n", b"", b"Embedded Object\r\n"):
        assert not _e_codigo_de_grupo(nao), nao


def test_CONTROLE_o_resgate_so_roda_na_causa_CERTA(tmp_path, monkeypatch):
    """🪤 Reescrever 50 MB é caro: recover caído por OUTRO motivo não reescreve."""
    import dxf_open as _mod
    import ezdxf.recover as _rec
    bom = _dxf_bom(tmp_path)
    chamou = {"n": 0}

    def _recover_que_cai(caminho, *a, **k):
        raise ValueError("outra causa qualquer")

    def _espiao(origem, destino):
        chamou["n"] += 1
        return 0

    monkeypatch.setattr(_rec, "readfile", _recover_que_cai)
    monkeypatch.setattr(_mod, "_dxf_com_textos_emendados", _espiao)
    with pytest.raises(ValueError):
        _mod.recuperar_dxf(bom, "motivo qualquer")
    assert chamou["n"] == 0, "reescreveu por uma causa que não é a da quebra"
