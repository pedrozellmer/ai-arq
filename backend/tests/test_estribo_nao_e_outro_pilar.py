# -*- coding: utf-8 -*-
"""O estribo desenhado dentro da seção do pilar não vira um 2º tipo de pilar.

🩸 07/10/2026 — filhote do job de estrutura de 30 DWG, já com a escala da vista
pelos rótulos: a prancha dos pilares saiu com 25 × 120 e 25 × 240 (certos) e
uma 3ª linha "pilar 19 × 114 cm, 11 un" — o ESTRIBO, retângulo concêntrico dentro
de cada seção, com folga de 3 cm nos dois lados (o cobrimento). +6,4 m³ e +79 m²
de fôrma que não existem.

🔑 Sai o grupo cujos retângulos estão DENTRO dos de outro grupo, concêntricos,
com a mesma folga nos dois lados, e essa folga, na escala dos rótulos do de fora,
é um cobrimento (1,5–6 cm).
🧪 Controles: folga desigual (furo de graute no bloco), de fora SEM escala pelos
rótulos (caixilho dentro da janela, na planta de arquitetura), lado a lado (dois
tipos de pilar diferentes), folga grande demais pra cobrimento, e a régua que
quebra não derruba a contagem.

🪤 Anatomia do caso real (medida no DXF da prancha): 11 seções 1,00 × 4,80 no
layer "2", rótulos "25"/"120", estribo 0,74 × 4,54. Nomes FICTÍCIOS.
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import dwg_extractor as dx  # noqa: E402
from test_secao_pela_escala_dos_rotulos import _quadro  # noqa: E402

_N, _PASSO, _Y = 11, 10.0, 50.0


def _com_dentro(msp, lados=(0.74, 4.54), fora=(1.0, 4.8), desloca=(0.0, 0.0), layer="2"):
    """Um retângulo dentro de cada seção de `_quadro` (centro + `desloca`)."""
    s1, s2 = lados
    for i in range(_N):
        cx = _PASSO * i + fora[0] / 2 + desloca[0]
        cy = _Y + fora[1] / 2 + desloca[1]
        msp.add_lwpolyline([(cx - s1 / 2, cy - s2 / 2), (cx + s1 / 2, cy - s2 / 2),
                            (cx + s1 / 2, cy + s2 / 2), (cx - s1 / 2, cy + s2 / 2)],
                           close=True, dxfattribs={"layer": layer})
    return msp


def _ret(msp, uf=1.0):
    ob = dx.objetos_repetidos_sem_bloco(msp, uf)
    return sorted(((p["a_cm"], p["b_cm"]) for p in ob.get("2") or [] if p["forma"] == "retângulo"))


# ══════════════════════════════════════════════════════════════════════════
#  O caso
# ══════════════════════════════════════════════════════════════════════════
def test_o_estribo_dentro_da_secao_sai_da_contagem():
    assert _ret(_com_dentro(_quadro())) == [(100.0, 480.0)]


def test_a_secao_continua_pelos_rotulos():
    ob = dx.objetos_repetidos_sem_bloco(_com_dentro(_quadro()), 1.0)
    (p,) = ob["2"]
    assert (p["rot_a_cm"], p["rot_b_cm"], p["n"]) == (25.0, 120.0, 11), p


def test_a_ia_nao_ve_mais_o_segundo_pilar():
    ob = dx.objetos_repetidos_sem_bloco(_com_dentro(_quadro()), 1.0)
    ext = dx.DXFExtraction(filename="p.dxf", blocks=[], walls=[], hatches=[], texts=[], layers=["2"],
                           dimensions=[], metadata={"objetos_sem_bloco": ob})
    txt = ext.to_structured_prompt()
    assert txt.count("retângulos de") == 1, txt
    assert "25 × 120 cm PELOS RÓTULOS" in txt and "74 × 454" not in txt, txt


def test_o_estribo_em_outro_layer_tambem_sai():
    msp = _com_dentro(_quadro(), layer="ESTRIBOS")
    ob = dx.objetos_repetidos_sem_bloco(msp, 1.0)
    assert "ESTRIBOS" not in ob, ob
    assert [(p["a_cm"], p["b_cm"]) for p in ob["2"]] == [(100.0, 480.0)]


# ══════════════════════════════════════════════════════════════════════════
#  Controles
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_folga_desigual_fica():
    """Furo de graute dentro do bloco: dentro e concêntrico, mas folga diferente
    em cada lado — é outra peça, e se conta. 🪤 As duas folgas (1,5 e 5 cm) caem
    na faixa do cobrimento: o que segura é SÓ a folga desigual."""
    assert _ret(_com_dentro(_quadro(), lados=(0.88, 4.4))) == [(88.0, 440.0), (100.0, 480.0)]


def test_CONTROLE_sem_escala_pelos_rotulos_fica():
    """Caixilho dentro da janela, na planta em escala real: a geometria é igual à
    do estribo, mas sem rótulo dizendo outra escala não há cobrimento a medir."""
    msp = _com_dentro(_quadro(rotulados=0))
    assert _ret(msp) == [(74.0, 454.0), (100.0, 480.0)]


def test_CONTROLE_lado_a_lado_fica():
    """Dois tipos de pilar no mesmo quadro: tamanhos com a folga do estribo,
    mas um NÃO está dentro do outro."""
    msp = _com_dentro(_quadro(), desloca=(3.0, 0.0))
    assert _ret(msp) == [(74.0, 454.0), (100.0, 480.0)]


def test_CONTROLE_fora_do_centro_fica():
    """Dentro da seção e com a folga do estribo (3 cm), mas deslocado: não é o
    estribo daquela seção. 🪤 Só o centro segura este caso."""
    msp = _com_dentro(_quadro(), lados=(0.76, 4.56), desloca=(0.08, 0.0))
    assert _ret(msp) == [(76.0, 456.0), (100.0, 480.0)]


def test_CONTROLE_folga_grande_demais_para_cobrimento_fica():
    """0,3 × 25 = 7,5 cm: não é cobrimento de estribo (pode ser um pilar dentro
    da base, um nicho, outra peça)."""
    assert _ret(_com_dentro(_quadro(), lados=(0.4, 4.2))) == [(40.0, 420.0), (100.0, 480.0)]


def test_CONTROLE_a_falha_da_regua_nao_derruba_a_contagem(monkeypatch):
    def _quebra(*a, **k):
        raise RuntimeError("régua quebrada")
    monkeypatch.setattr(dx, "_grupos_de_estribo", _quebra)
    assert _ret(_com_dentro(_quadro())) == [(74.0, 454.0), (100.0, 480.0)]
