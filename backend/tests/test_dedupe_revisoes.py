# -*- coding: utf-8 -*-
"""Regressão do dedupe de revisão do motor (_dedupe_revisoes).

Mesma prancha em várias revisões (só muda o sufixo -RNN) → mantém a mais nova,
senão o quantitativo conta a prancha 2x. CONSERVADOR: nunca descarta prancha sem
sufixo de revisão nem funde bases diferentes (regra nº1 — nada some em silêncio).

Caso motivador: cliente-40/Engefast 21/07 (008 R03+R04, 009 R02+R03)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from main import _dedupe_revisoes  # noqa: E402


def _n(paths):
    mant, desc = _dedupe_revisoes(paths)
    return len(mant), len(desc), [(os.path.basename(v), os.path.basename(k)) for v, k in desc]


def test_caso_rafael_duas_revisoes():
    files = [
        "d/2060-PRJ-ELE-LO-008-GER.PL.TE-R03.dxf",
        "d/2060-PRJ-ELE-LO-008-GER.PL.TE-R04.dxf",
        "d/2060-PRJ-ELE-LO-009-GER.PL.TE-R02.dxf",
        "d/2060-PRJ-ELE-LO-009-GER.PL.TE-R03.dxf",
        "d/2060-PRJ-ELE-LO-010-GER.PL.TE-R00.dxf",
    ]
    mant, desc, pares = _n(files)
    assert mant == 3 and desc == 2
    # descarta as revisões ANTIGAS, mantém as novas
    descartados = {p[0] for p in pares}
    assert descartados == {
        "2060-PRJ-ELE-LO-008-GER.PL.TE-R03.dxf",
        "2060-PRJ-ELE-LO-009-GER.PL.TE-R02.dxf",
    }


def test_tres_revisoes_mantem_a_maior():
    mant, desc, pares = _n(["x/P-R01.dxf", "x/P-R05.dxf", "x/P-R03.dxf"])
    assert mant == 1 and desc == 2
    assert all(k == "P-R05.dxf" for _, k in pares)


def test_rev_underscore_e_prefixo_REV():
    mant, desc, _ = _n(["w/CASA_REV02.dxf", "w/CASA_REV04.dxf"])
    assert mant == 1 and desc == 1


def test_sem_repeticao_nao_mexe():
    mant, desc, _ = _n(["a/PLANTA-R00.dxf", "a/CORTE-R01.dxf"])
    assert mant == 2 and desc == 0


def test_sem_sufixo_nunca_descarta():
    mant, desc, _ = _n(["y/planta_terreo.dxf", "y/planta_superior.dxf"])
    assert mant == 2 and desc == 0


def test_extensao_diferente_nao_funde():
    # DWG e DXF de mesma base são coisas distintas aqui (o dedupe DWG-vs-DXF é outro)
    mant, desc, _ = _n(["z/P-R01.dxf", "z/P-R02.pdf"])
    assert mant == 2 and desc == 0


def test_numero_puro_nao_e_revisao():
    mant, desc, _ = _n(["k/SALA2.dxf", "k/SALA3.dxf"])
    assert mant == 2 and desc == 0


def test_um_com_rev_outro_sem_nao_funde():
    # Conservador: sem sufixo de revisão não vira "revisão 0" de nada
    mant, desc, _ = _n(["m/PLANTA.dxf", "m/PLANTA-R02.dxf"])
    assert mant == 2 and desc == 0


# ── Casos que o agente adversarial levantou: "R"+1 dígito NÃO é revisão ──
# (Rua, modelo de casa/CUB, Raio de curva, eixo). Nunca apagar prancha real.

def test_rua_1digito_nao_descarta():
    # PERFIL-R1/-R2/-R3 = perfis de RUAS diferentes, não revisões
    mant, desc, _ = _n(["u/PERFIL-R1.dxf", "u/PERFIL-R2.dxf", "u/PERFIL-R3.dxf"])
    assert mant == 3 and desc == 0


def test_casa_cub_nao_descarta():
    # CASA-R1/-R8/-R16 = padrões CUB (NBR 12721), não revisões
    mant, desc, _ = _n(["c/CASA-R1.dxf", "c/CASA-R8.dxf", "c/CASA-R16.dxf"])
    assert mant == 3 and desc == 0


def test_raio_curva_1digito_nao_descarta():
    mant, desc, _ = _n(["v/CURVA-R5.dxf", "v/CURVA-R8.dxf"])
    assert mant == 2 and desc == 0


def test_rev_prefixo_1digito_ainda_dedup():
    # "REV" explícito é sinal forte de revisão — pode ter 1 dígito só
    mant, desc, _ = _n(["r/PLANTA-REV1.dxf", "r/PLANTA-REV2.dxf"])
    assert mant == 1 and desc == 1


def test_base_com_espaco_ainda_dedup():
    # Espaçamento inconsistente na mão não deve virar grupos separados
    mant, desc, _ = _n(["s/PLANTA - R01.dxf", "s/PLANTA-R02.dxf"])
    assert mant == 1 and desc == 1


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"[OK ] {name}")
            except Exception:
                fails += 1
                print(f"[FALHOU] {name}")
                traceback.print_exc()
    print("\n=== TODOS OK ===" if not fails else f"\n=== {fails} FALHA(S) ===")
    sys.exit(1 if fails else 0)
