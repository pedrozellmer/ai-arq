# -*- coding: utf-8 -*-
"""A contagem de um tipo de bloco que mora FORA das pranchas não sai medida.

🩸 17/11/2026 — DWG de mercado com 74 % do comprimento fora de toda janela das
pranchas (cópias de trabalho, terreno, versões). A contagem do bloco de porta
de madeira saiu 45 ✓ MEDIDO; o PDF do mesmo projeto mostra bem menos. O aviso
"parte do desenho está fora das pranchas" já saía, mas a contagem por tipo não
lia nada disso, e a cópia de trabalho editada não é a cópia exata que
`copias_em_sombra` reconhece.

🔑 Por TIPO (o símbolo que mora na prancha fica como está), SÓ REBAIXA, e só com
CONTAGEM_FORA_DAS_PRANCHAS_REBAIXA=1 — com 0, o log diz o que faria.
Dados sintéticos, na FORMA do caso.
"""
import os
import sys
import textwrap

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
import engine_rules as er  # noqa: E402
import main  # noqa: E402
from dwg_extractor import BlockCount, blocos_fora_das_pranchas  # noqa: E402

_MAPA = {"folhas": [{"caixa": (0, 0, 40, 30), "tipo": "planta"}], "gerais": 0, "sem_janela": 0}
_DENTRO = [(5.0 + 3 * i, 10.0) for i in range(8)]
_FORA = [(200.0 + 3 * i, 10.0) for i in range(8)]


def _b(nome, pos, count=None):
    return BlockCount(name=nome, count=len(pos) if count is None else count, layer="0",
                      positions=list(pos))


# ══════════════════════════════════════════════════════════════════════════
#  1. A medida por tipo
# ══════════════════════════════════════════════════════════════════════════
def test_o_tipo_com_a_maioria_fora_entra_com_a_conta():
    blocos = [_b("PORTA-MAD", _DENTRO[:2] + _FORA[:6]), _b("TOMADA", _DENTRO[:4])]
    assert blocos_fora_das_pranchas(blocos, _MAPA, 0.5) == {"PORTA-MAD": [6, 8]}


def test_metade_fora_ja_conta():
    assert blocos_fora_das_pranchas([_b("P", _DENTRO[:3] + _FORA[:3])], _MAPA, 0.5) == {"P": [3, 6]}


def test_CONTROLE_a_minoria_fora_nao_entra():
    """Mutação natural: sem a régua dos 50 %, este voltaria."""
    assert blocos_fora_das_pranchas([_b("P", _DENTRO[:5] + _FORA[:2])], _MAPA, 0.5) == {}


def test_bloco_sem_todas_as_posicoes_fica_de_fora():
    assert blocos_fora_das_pranchas([_b("P", _FORA[:3], count=9)], _MAPA, 0.5) == {}


@pytest.mark.parametrize("mapa", [
    {"folhas": []},
    {"folhas": [{"caixa": (0, 0, 40, 30), "tipo": "planta"}], "origem": "modelo"},
    None,
])
def test_CONTROLE_sem_janela_do_papel_nao_ha_fora(mapa):
    assert blocos_fora_das_pranchas([_b("P", _FORA[:4])], mapa, 0.5) == {}


def test_CONTROLE_quem_plota_do_modelo_nao_tem_nada_rebaixado():
    """As janelas mostram menos de 20 % do comprimento E das peças: o
    projetista plota direto do modelo, e 'fora' não quer dizer cópia."""
    blocos = [_b("P", _FORA[:8]), _b("Q", _DENTRO[:1] + _FORA[:7])]
    assert blocos_fora_das_pranchas(blocos, _MAPA, 0.9) == {}


def test_com_o_metro_dentro_a_trava_dos_20_porcento_nao_cala():
    blocos = [_b("P", _FORA[:8]), _b("Q", _DENTRO[:1] + _FORA[:7])]
    assert set(blocos_fora_das_pranchas(blocos, _MAPA, 0.5)) == {"P", "Q"}


def test_nunca_levanta():
    assert blocos_fora_das_pranchas([object()], _MAPA, 0.5) == {}
    assert blocos_fora_das_pranchas(None, _MAPA, 0.5) == {}


# ══════════════════════════════════════════════════════════════════════════
#  2. De ponta a ponta no extrator: chave PRÓPRIA, fora do prompt
# ══════════════════════════════════════════════════════════════════════════
def _viewport(lay, janela, centro_papel=(200, 150)):
    x0, y0, x1, y1 = janela
    esc = 10.0
    return lay.add_viewport(center=centro_papel, size=((x1 - x0) * esc, (y1 - y0) * esc),
                            view_center_point=((x0 + x1) / 2, (y0 + y1) / 2), view_height=(y1 - y0))


def _arquivo(tmp_path, folhas=True):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6                  # metros
    msp = doc.modelspace()
    for nome in ("PORTA-MAD", "TOMADA"):
        blk = doc.blocks.new(name=nome)
        blk.add_lwpolyline([(0, 0), (0.8, 0), (0.8, 0.1), (0, 0.1)], close=True)
    for x0 in (0, 200):                          # a planta e a cópia de trabalho
        for y in (5, 10, 15, 20):
            msp.add_line((x0 + 5, y), (x0 + 30, y), dxfattribs={"layer": "PAREDE"})
    for x, y in _DENTRO[:2] + _FORA[:6]:
        msp.add_blockref("PORTA-MAD", (x, y))
    for x, y in _DENTRO[:4]:
        msp.add_blockref("TOMADA", (x, y + 5))
    if folhas:
        _viewport(doc.layouts.new("A1 TERREO"), (0, 0, 40, 30))
    p = str(tmp_path / "planta.dxf")
    doc.saveas(p)
    return p


def test_o_extrator_guarda_os_tipos_numa_chave_propria(tmp_path, monkeypatch):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    ex = dx.extract_dxf(_arquivo(tmp_path))
    assert ex.metadata.get("fora_das_pranchas"), "o aviso do arquivo tem de continuar"
    assert ex.metadata.get("blocos_fora_das_pranchas") == {"PORTA-MAD": [6, 8]}
    assert "blocos" not in ex.metadata["fora_das_pranchas"], \
        "`fora_das_pranchas` vai crua pro prompt — a lista não pode morar nela"
    # só mede: a contagem não muda
    assert ex.get_block_summary().get("PORTA-MAD") == 8


def test_a_lista_nao_vai_pro_prompt(tmp_path, monkeypatch):
    """🪤 Chave nova no metadata sai crua no prompt — e com a chave em 0 a
    leitura da IA não pode mudar."""
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    ex = dx.extract_dxf(_arquivo(tmp_path))
    assert ex.metadata.get("blocos_fora_das_pranchas")
    assert "blocos_fora_das_pranchas" not in ex.to_structured_prompt()


def test_CONTROLE_sem_prancha_nao_ha_lista(tmp_path, monkeypatch):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    ex = dx.extract_dxf(_arquivo(tmp_path, folhas=False))
    assert not ex.metadata.get("blocos_fora_das_pranchas")


# ══════════════════════════════════════════════════════════════════════════
#  3. O selo — só rebaixa, só o tipo de fora, só a contagem que bate
# ══════════════════════════════════════════════════════════════════════════
FORA = {"PORTA DE MADEIRA_D02": [40, 45]}
BLOCOS = {"PORTA DE MADEIRA_D02": 45, "TOMADA": 12}


def _obs(nome, n):
    return "Fonte: %d INSERTs do bloco '%s' em CONTAGEM DE BLOCOS." % (n, nome)


def test_a_contagem_do_tipo_de_fora_sai_laranja_com_a_conta_na_frente():
    conf, obs, mexeu = er.selo_apos_bloco_fora_das_pranchas(
        "confirmado", _obs("PORTA DE MADEIRA_D02", 45), 45, "un", FORA, BLOCOS)
    assert (conf, mexeu) == ("estimado", True)
    assert obs.startswith(er.MARCA_BLOCO_FORA_DAS_PRANCHAS)
    assert "40 das 45" in obs[:110], "o essencial tem de caber no que a revisão mostra"
    assert obs.endswith(_obs("PORTA DE MADEIRA_D02", 45)), "a observação original fica"


def test_o_tipo_que_mora_na_prancha_fica_como_esta():
    r = er.selo_apos_bloco_fora_das_pranchas("confirmado", _obs("TOMADA", 12), 12, "un", FORA, BLOCOS)
    assert r == ("confirmado", _obs("TOMADA", 12), False)


def test_numero_que_nao_e_a_contagem_do_bloco_fica():
    r = er.selo_apos_bloco_fora_das_pranchas(
        "confirmado", _obs("PORTA DE MADEIRA_D02", 45), 7, "un", FORA, BLOCOS)
    assert r[2] is False


@pytest.mark.parametrize("conf", ["estimado", "a_confirmar", ""])
def test_so_mexe_no_medido(conf):
    r = er.selo_apos_bloco_fora_das_pranchas(conf, _obs("PORTA DE MADEIRA_D02", 45), 45, "un",
                                            FORA, BLOCOS)
    assert r[2] is False and r[0] == conf


def test_sem_lista_nao_faz_nada():
    obs = _obs("PORTA DE MADEIRA_D02", 45)
    assert er.selo_apos_bloco_fora_das_pranchas("confirmado", obs, 45, "un", {}, BLOCOS) == \
        ("confirmado", obs, False)


def test_a_marca_trava_a_repromocao():
    assert er.MARCA_BLOCO_FORA_DAS_PRANCHAS in er.MARCAS_DE_REBAIXAMENTO


# ══════════════════════════════════════════════════════════════════════════
#  4. O bloco do process_job, executado de verdade
# ══════════════════════════════════════════════════════════════════════════
_INICIO = "                                if _blocos_fora_pr:\n"
_FIM = "                                # 🩸 12/10/2026: o número ESCRITO num quadro do desenho"


def _bloco():
    with open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8") as f:
        src = f.read().replace("\r\n", "\n")
    i = src.index(_INICIO)
    return textwrap.dedent(src[i:src.index(_FIM, i)])


def _rodar(liga, conf="confirmado", qty=45):
    obs = _obs("PORTA DE MADEIRA_D02", 45)
    ns = {"_blocos_fora_pr": FORA, "_blocos_n": BLOCOS, "_liga_fora_pr": liga,
          "_linhas_fora_pr": [], "_rebaixado_pela_fonte": False,
          "conf": conf, "obs_raw": obs, "qty": qty, "normalized_unit": "un",
          "desc": "Porta de madeira"}
    exec(_bloco(), ns)
    return ns


def test_com_a_chave_em_0_so_conta():
    ns = _rodar(False)
    assert ns["conf"] == "confirmado" and not ns["obs_raw"].startswith("⚠")
    assert ns["_rebaixado_pela_fonte"] is False
    assert ns["_linhas_fora_pr"] == ["Porta de madeira=45"]


def test_com_a_chave_em_1_rebaixa_e_trava():
    ns = _rodar(True)
    assert ns["conf"] == "estimado"
    assert ns["obs_raw"].startswith(er.MARCA_BLOCO_FORA_DAS_PRANCHAS)
    assert ns["_rebaixado_pela_fonte"] is True, "sem a trava, o cross-check re-promoveria"
    assert ns["qty"] == 45, "não mexe no número"


def test_nasce_desligada_e_avaliavel(monkeypatch):
    assert "CONTAGEM_FORA_DAS_PRANCHAS_REBAIXA" in main._CHAVES_AVALIAVEIS
    assert "motor:contagem-fora-das-pranchas" in main._STAGES_DIAGNOSTICO
    monkeypatch.delenv("CONTAGEM_FORA_DAS_PRANCHAS_REBAIXA", raising=False)
    assert main._chave_do_job("abc", "CONTAGEM_FORA_DAS_PRANCHAS_REBAIXA") == "0"


def test_a_regra_roda_depois_da_planta_repetida_e_antes_do_quadro():
    with open(os.path.join(os.path.dirname(_AQUI), "main.py"), encoding="utf-8") as f:
        src = f.read()
    i = src.index("_regra_fora_pr(")
    assert src.index("_regra_copias(") < i < src.index("_regra_quadro(")
