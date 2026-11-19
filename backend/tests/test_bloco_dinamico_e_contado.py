# -*- coding: utf-8 -*-
"""O bloco DINÂMICO (*U) conta pelo nome do dinâmico — com a chave ligada.

🩸 18/11/2026. Num projeto elétrico, a prancha mostrava 179 tomadas e 79
interruptores, todos blocos dinâmicos do escritório. O motor joga fora todo
bloco cujo nome começa com "*" — e o AutoCAD grava cada inserção dinâmica
modificada como "*U123". As peças da prancha saíram FORA da planilha. Em 90
dias, 45 projetos de 39 clientes tinham dinâmico descartado (esquadria em 12,
elétrica em 7, louça em 5).

🔑 Chave CONTAR_BLOCO_DINAMICO, nasce 0 (muda contagem). Ligada, o *U passa
pelos MESMOS filtros do bloco comum (anotação, layer utilitário, cópia no mesmo
ponto). Sem o vínculo ao dinâmico, ou com "$" no nome achado, segue descartado.

🩸 19/11/2026. Avaliada num prédio, a chave deu 97 janelas com selo onde o
quadro de esquadrias somava 29: o dinâmico era a FOLHA de janelas de 3 a 11
folhas. Esquadria dinâmica (pelo nome achado OU pelo layer) segue fora.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402


@pytest.fixture(autouse=True)
def _sem_leitura_por_folha(monkeypatch):
    monkeypatch.setenv("LEITURA_POR_FOLHA", "0")
    monkeypatch.delenv("CONTAR_BLOCO_DINAMICO", raising=False)


def _dinamico(doc, base, forma=None):
    """Um *U ligado ao dinâmico `base` (o XDATA que o AutoCAD grava)."""
    if "AcDbBlockRepBTag" not in doc.appids:
        doc.appids.new("AcDbBlockRepBTag")
    u = doc.blocks.new_anonymous_block("U")
    (forma or (lambda b: b.add_circle((0, 0), 0.1)))(u)
    doc.block_records.get(u.name).set_xdata(
        "AcDbBlockRepBTag", [(1070, 1), (1005, doc.block_records.get(base).dxf.handle)])
    return u.name


def _arquivo(tmp_path, monta):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    monta(doc, doc.modelspace())
    p = str(tmp_path / "dinamico.dxf")
    doc.saveas(p)
    return p


def _tomadas(doc, msp):
    """5 tomadas: 2 pelo nome, 3 dinâmicas (dois *U diferentes do mesmo dinâmico)."""
    doc.blocks.new("TOMADA_X").add_circle((0, 0), 0.1)
    msp.add_blockref("TOMADA_X", (0, 0))
    msp.add_blockref("TOMADA_X", (1, 0))
    u1 = _dinamico(doc, "TOMADA_X")
    u2 = _dinamico(doc, "TOMADA_X")
    msp.add_blockref(u1, (2, 0))
    msp.add_blockref(u1, (3, 0))
    msp.add_blockref(u2, (4, 0))


# ══════════════════════════════════════════════════════════════════════════
#  1. Com a chave em 0 nada muda
# ══════════════════════════════════════════════════════════════════════════
def test_chave_em_0_o_dinamico_segue_fora(tmp_path):
    ex = dx.extract_dxf(_arquivo(tmp_path, _tomadas))
    assert ex.get_block_summary() == {"TOMADA_X": 2}
    assert ex.metadata["procedencia_blocos"]["dinamicos"] == {"TOMADA_X": 3}
    assert "dinamicos_contados" not in ex.metadata


def test_a_chave_nasce_desligada(monkeypatch):
    import inspect
    fonte = inspect.getsource(dx)
    assert 'os.environ.get("CONTAR_BLOCO_DINAMICO", "0").strip() == "1"' in fonte


# ══════════════════════════════════════════════════════════════════════════
#  2. Com a chave em 1 o *U vira a peça
# ══════════════════════════════════════════════════════════════════════════
def test_chave_em_1_o_dinamico_soma_com_o_bloco_pelo_nome(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTAR_BLOCO_DINAMICO", "1")
    ex = dx.extract_dxf(_arquivo(tmp_path, _tomadas))
    assert ex.get_block_summary() == {"TOMADA_X": 5}
    assert ex.metadata["dinamicos_contados"] == {"TOMADA_X": 3}
    # contado não é mais "descartado"
    assert "dinamicos" not in (ex.metadata.get("procedencia_blocos") or {})
    b = [b for b in ex.blocks if b.name == "TOMADA_X"][0]
    assert len(b.positions) == 5


def test_so_dinamico_sem_bloco_pelo_nome_tambem_conta(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTAR_BLOCO_DINAMICO", "1")

    def monta(doc, msp):
        doc.blocks.new("INTERRUPTOR_X").add_circle((0, 0), 0.1)
        u = _dinamico(doc, "INTERRUPTOR_X")
        for k in range(4):
            msp.add_blockref(u, (k, 0))
    ex = dx.extract_dxf(_arquivo(tmp_path, monta))
    assert ex.get_block_summary() == {"INTERRUPTOR_X": 4}


# ══════════════════════════════════════════════════════════════════════════
#  3. Os mesmos filtros do bloco comum
# ══════════════════════════════════════════════════════════════════════════
def test_dinamico_de_anotacao_nao_conta(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTAR_BLOCO_DINAMICO", "1")

    def monta(doc, msp):
        doc.blocks.new("INDCORTE").add_circle((0, 0), 0.1)
        u = _dinamico(doc, "INDCORTE")
        msp.add_blockref(u, (0, 0))
        msp.add_blockref(u, (5, 0))
    ex = dx.extract_dxf(_arquivo(tmp_path, monta))
    assert ex.get_block_summary() == {}
    assert "dinamicos_contados" not in ex.metadata


def test_dinamico_copiado_no_mesmo_ponto_conta_uma(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTAR_BLOCO_DINAMICO", "1")

    def monta(doc, msp):
        doc.blocks.new("TOMADA_X").add_circle((0, 0), 0.1)
        u = _dinamico(doc, "TOMADA_X")
        msp.add_blockref(u, (2, 2))
        msp.add_blockref(u, (2, 2))
    ex = dx.extract_dxf(_arquivo(tmp_path, monta))
    assert ex.get_block_summary() == {"TOMADA_X": 1}


def test_dinamico_em_layer_utilitario_nao_conta(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTAR_BLOCO_DINAMICO", "1")
    util = "DEFPOINTS"          # um dos layers utilitários do extrator

    def monta(doc, msp):
        doc.blocks.new("TOMADA_X").add_circle((0, 0), 0.1)
        u = _dinamico(doc, "TOMADA_X")
        msp.add_blockref(u, (0, 0), dxfattribs={"layer": util})
    ex = dx.extract_dxf(_arquivo(tmp_path, monta))
    assert ex.get_block_summary() == {}


# ══════════════════════════════════════════════════════════════════════════
#  4. O que segue descartado mesmo com a chave
# ══════════════════════════════════════════════════════════════════════════
def test_U_sem_vinculo_segue_fora(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTAR_BLOCO_DINAMICO", "1")

    def monta(doc, msp):
        u = doc.blocks.new_anonymous_block("U")
        u.add_circle((0, 0), 0.1)
        msp.add_blockref(u.name, (0, 0))
    ex = dx.extract_dxf(_arquivo(tmp_path, monta))
    assert ex.get_block_summary() == {}
    assert ex.metadata["procedencia_blocos"]["anonimos"] == {"*U": 1}


def test_dinamico_com_cifrao_no_nome_segue_fora(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTAR_BLOCO_DINAMICO", "1")

    def monta(doc, msp):
        doc.blocks.new("BASE$0$TOMADA").add_circle((0, 0), 0.1)
        u = _dinamico(doc, "BASE$0$TOMADA")
        msp.add_blockref(u, (0, 0))
    ex = dx.extract_dxf(_arquivo(tmp_path, monta))
    assert ex.get_block_summary() == {}


@pytest.mark.parametrize("nome", ["*X12", "A$C6BFD6B53", "PLANTA$0$MESA"])
def test_outros_anonimos_seguem_fora(tmp_path, monkeypatch, nome):
    monkeypatch.setenv("CONTAR_BLOCO_DINAMICO", "1")

    def monta(doc, msp):
        if nome.startswith("*"):
            b = doc.blocks.new_anonymous_block("X")
            b.add_circle((0, 0), 0.1)
            n = b.name
        else:
            doc.blocks.new(nome).add_circle((0, 0), 0.1)
            n = nome
        msp.add_blockref(n, (0, 0))
    ex = dx.extract_dxf(_arquivo(tmp_path, monta))
    assert ex.get_block_summary() == {}


# ══════════════════════════════════════════════════════════════════════════
#  5. Esquadria dinâmica segue FORA (19/11: a folha não é a janela)
# ══════════════════════════════════════════════════════════════════════════
def test_porta_dinamica_segue_fora(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTAR_BLOCO_DINAMICO", "1")

    def monta(doc, msp):
        doc.blocks.new("PORTA").add_line((0, 0), (0.8, 0))
        u = _dinamico(doc, "PORTA")
        msp.add_blockref(u, (0, 0))
        msp.add_blockref(u, (3, 0))
    ex = dx.extract_dxf(_arquivo(tmp_path, monta))
    assert ex.get_block_summary() == {}
    assert ex.metadata["procedencia_blocos"]["dinamicos"] == {"PORTA": 2}
    assert "dinamicos_contados" not in ex.metadata


def test_folha_de_janela_com_nome_estrangeiro_no_layer_de_esquadria_segue_fora(
        tmp_path, monkeypatch):
    """O nome não diz janela; o layer diz. Era a folha de janelas de 3–11 folhas."""
    monkeypatch.setenv("CONTAR_BLOCO_DINAMICO", "1")

    def monta(doc, msp):
        doc.blocks.new("FOLHA_X").add_line((0, 0), (1.0, 0))
        u = _dinamico(doc, "FOLHA_X")
        for k in range(5):
            msp.add_blockref(u, (k, 0), dxfattribs={"layer": "DM-ESQ-2"})
    ex = dx.extract_dxf(_arquivo(tmp_path, monta))
    assert ex.get_block_summary() == {}
    assert ex.metadata["procedencia_blocos"]["dinamicos"] == {"FOLHA_X": 5}


def test_o_mesmo_dinamico_fora_do_layer_de_esquadria_conta(tmp_path, monkeypatch):
    """Controle: o filtro de cima é o layer, não o bloco."""
    monkeypatch.setenv("CONTAR_BLOCO_DINAMICO", "1")

    def monta(doc, msp):
        doc.blocks.new("FOLHA_X").add_line((0, 0), (1.0, 0))
        u = _dinamico(doc, "FOLHA_X")
        for k in range(5):
            msp.add_blockref(u, (k, 0), dxfattribs={"layer": "MOBILIARIO"})
    ex = dx.extract_dxf(_arquivo(tmp_path, monta))
    assert ex.get_block_summary() == {"FOLHA_X": 5}


def test_porta_comum_pelo_nome_segue_contada(tmp_path, monkeypatch):
    """Só o *U de esquadria fica fora; a porta de bloco comum não muda."""
    monkeypatch.setenv("CONTAR_BLOCO_DINAMICO", "1")

    def monta(doc, msp):
        doc.blocks.new("PORTA").add_line((0, 0), (0.8, 0))
        msp.add_blockref("PORTA", (0, 0))
        msp.add_blockref(_dinamico(doc, "PORTA"), (3, 0))
    ex = dx.extract_dxf(_arquivo(tmp_path, monta))
    assert ex.get_block_summary() == {"PORTA": 1}


# ══════════════════════════════════════════════════════════════════════════
#  6. O contador fica fora do prompt e entra no log
# ══════════════════════════════════════════════════════════════════════════
def test_o_contador_fica_fora_do_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTAR_BLOCO_DINAMICO", "1")
    ex = dx.extract_dxf(_arquivo(tmp_path, _tomadas))
    assert "dinamicos_contados" in ex._METADADOS_FORA_DO_PROMPT
    assert "dinamicos_contados" not in ex.to_structured_prompt()


def test_o_log_diz_quantos_dinamicos_viraram_peca():
    import main as m

    class _Ex:
        metadata = {"dinamicos_contados": {"TOMADA_X": 179, "INTERRUPTOR_X": 79}}
    s = m._procedencia_dos_blocos(_Ex())
    assert "dinamicos_contados=[TOMADA_X=179|INTERRUPTOR_X=79]" in s, s


def test_a_chave_e_avaliavel():
    import main as m
    assert "CONTAR_BLOCO_DINAMICO" in m._CHAVES_AVALIAVEIS
