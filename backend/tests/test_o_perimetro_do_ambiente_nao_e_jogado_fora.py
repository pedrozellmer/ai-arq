# -*- coding: utf-8 -*-
"""O perímetro de cada ambiente é MEDIDO — e até hoje era jogado fora.

🩸 16/09/2026. O leitor de PDF monta o polígono de cada cômodo, usa o perímetro
dele numa checagem interna (a fração de contorno que é "ponte" de vão de porta)
e então grava só área, centro e caixa envolvente. O perímetro morria junto com
o polígono, na mesma linha.

É ele que fecha a pintura de parede: Σ(perímetro dos ambientes) × pé-direito é
como o orçamentista faz à mão. Medido em 45 dias: **29 projetos** em que o
cliente informou o pé-direito, **11** deles com parede medida no PDF, e nos 11 a
derivação de pintura produziu ZERO — motivo declarado no log: "sem comprimento
de parede", enquanto a prancha tinha a medição.

🪤 E ele NÃO é substituto do `walls_m`, é outro número. Medido nos mesmos 45
dias, `walls_m` chega a **84× o perímetro mínimo** da área (3.213 m num imóvel
de 90 m²): é a soma de todo traço classificado como parede, as duas faces e
provavelmente hachura. Jogar aquilo na fórmula da pintura daria 16.000 m² num
apartamento de 105 m² — o mesmo desastre de 58× que a trava de
`_derive_pintura_pe_direito` existe pra impedir. O perímetro do cômodo conta a
face que dá PRA ELE, então as duas faces saem sozinhas, sem o "×2".

🚨 PASSO 1 DE PROPÓSITO: só REGISTRAR. Nada que o cliente recebe muda até o log
ser lido (~30/09). Estes guardas CHAMAM o detector real.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pdfvec_rooms  # noqa: E402

W, H = 842.0, 595.0
_ESCALA = 100.0                      # 1:100
_M_POR_PT = pdfvec_rooms.PT_TO_M * _ESCALA


def _retangulo(x0, y0, x1, y1):
    return [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)),
            ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]


def _salas(segs):
    return pdfvec_rooms.detect_rooms("", 0, _ESCALA, None, bridge_gaps_m=1.2,
                                     _segments=(segs, W, H))


# ── o número ───────────────────────────────────────────────────────────────
def test_a_sala_traz_o_PERIMETRO_em_metros():
    """Sala de 200 × 150 pt: perímetro = 2·(200+150) pt, convertido pra metro."""
    salas = _salas(_retangulo(100.0, 100.0, 300.0, 250.0))
    assert len(salas) == 1, [s["area_m2"] for s in salas]
    esperado = 2 * (200.0 + 150.0) * _M_POR_PT
    assert "perimetro_m" in salas[0], (
        "o perímetro continua sendo jogado fora: %r" % (sorted(salas[0]),))
    assert math.isclose(salas[0]["perimetro_m"], esperado, rel_tol=0.01), (
        "perímetro %r, esperado ~%.2f m" % (salas[0]["perimetro_m"], esperado))


def test_CONTROLE_mesma_AREA_com_formas_diferentes_da_perimetros_diferentes():
    """🔑 O controle que importa: prova que o número é MEDIDO do contorno, e não
    deduzido da área. Um corredor comprido e um quadrado de MESMA área têm
    perímetros bem diferentes — quem calcular por `4·√área` passa no teste de
    cima e morre aqui.
    """
    quadrado = _salas(_retangulo(100.0, 100.0, 300.0, 300.0))      # 200 × 200
    corredor = _salas(_retangulo(100.0, 100.0, 500.0, 200.0))      # 400 × 100
    assert len(quadrado) == 1 and len(corredor) == 1
    assert math.isclose(quadrado[0]["area_m2"], corredor[0]["area_m2"], rel_tol=0.01), (
        "o cenário perdeu a graça: as áreas têm que ser iguais (%r × %r)"
        % (quadrado[0]["area_m2"], corredor[0]["area_m2"]))
    assert corredor[0]["perimetro_m"] > quadrado[0]["perimetro_m"] * 1.2, (
        "perímetro igual pra formas diferentes = ele está sendo deduzido da "
        "área, não medido (%r × %r)"
        % (corredor[0]["perimetro_m"], quadrado[0]["perimetro_m"]))


def test_o_perimetro_NUNCA_e_zero_numa_sala_que_existe():
    for salas in (_salas(_retangulo(100.0, 100.0, 300.0, 250.0)),
                  _salas(_retangulo(120.0, 120.0, 200.0, 180.0))):
        for s in salas:
            assert float(s.get("perimetro_m") or 0) > 0, s


# ── a conta que este número habilita ───────────────────────────────────────
def test_a_conta_da_PINTURA_cai_em_faixa_plausivel():
    """🪤 O guarda que trava o motivo de tudo isto. Pintura de parede fica, num
    imóvel real, entre ~1,5× e ~5× a área de piso. Se um dia alguém trocar o
    perímetro do cômodo pelo `walls_m`, a razão explode (no caso ao vivo de
    16/09 daria 157× a área) e este teste cai.
    """
    planta = (_retangulo(100.0, 100.0, 300.0, 250.0)
              + _retangulo(310.0, 100.0, 450.0, 250.0))
    salas = _salas(planta)
    assert len(salas) == 2, [s["area_m2"] for s in salas]

    area_piso = sum(s["area_m2"] for s in salas)
    perim = sum(s["perimetro_m"] for s in salas)
    pintura = perim * 2.56                      # pé-direito informado pelo cliente
    razao = pintura / area_piso
    assert 1.2 <= razao <= 5.0, (
        "pintura = %.1f m² pra %.1f m² de piso (%.1f×) — fora de qualquer "
        "imóvel real" % (pintura, area_piso, razao))


# ── a soma que vai pro log ─────────────────────────────────────────────────
def test_a_soma_dos_perimetros_e_SOMA_das_salas_reais():
    """Chama a régua de verdade, com as salas que o detector real devolveu."""
    import pdf_vector
    planta = (_retangulo(100.0, 100.0, 300.0, 250.0)
              + _retangulo(310.0, 100.0, 450.0, 250.0))
    salas = _salas(planta)
    assert len(salas) == 2
    esperado = round(sum(s["perimetro_m"] for s in salas), 1)
    assert pdf_vector.soma_perimetros(salas) == esperado


def test_CONTROLE_a_soma_nao_e_o_MAIOR_nem_a_media():
    """🪤 Um `max` ou uma média no lugar da soma não quebra nada e não aparece:
    produz um número plausível e errado no log em que a decisão vai se apoiar."""
    import pdf_vector
    salas = [{"perimetro_m": 30.0}, {"perimetro_m": 18.0}]
    assert pdf_vector.soma_perimetros(salas) == 48.0


def test_sala_sem_perimetro_nao_derruba_a_soma():
    import pdf_vector
    assert pdf_vector.soma_perimetros(
        [{"perimetro_m": 12.0}, {"area_m2": 9.0}, {"perimetro_m": None}]) == 12.0
    assert pdf_vector.soma_perimetros([]) == 0.0
    assert pdf_vector.soma_perimetros(None) == 0.0


# ── o caminho até o log (guarda de FONTE, e assumido como tal) ─────────────
def test_o_perimetro_ATRAVESSA_o_leitor_e_chega_ao_log():
    """🪤 Guarda de FONTE, declarado: as três emendas entre o detector e o log
    ficam dentro de funções grandes demais pra encenar aqui. O que ele prende é
    que o campo não se perde no meio do caminho — se alguém tirar uma das três,
    o número volta a morrer sem ninguém notar, que é exatamente o defeito que
    este commit conserta.
    """
    import io
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pv = io.open(os.path.join(base, "pdf_vector.py"), encoding="utf-8").read()
    mp = io.open(os.path.join(base, "main.py"), encoding="utf-8").read()

    assert 'out["rooms_perim_m"] = soma_perimetros(rooms)' in pv, (
        "o leitor deixou de somar os perímetros pela régua")
    assert '"rooms_perim_m",' in pv, (
        "o campo saiu da lista do que sobe do leitor — ele some antes do main")
    assert mp.count('"rooms_perim_m": float(_vm.get("rooms_perim_m") or 0)') == 2, (
        "são DOIS lugares que montam a ficha por prancha (leitura normal e "
        "retomada); os dois precisam do campo")
    assert 'r.get("rooms_perim_m") or 0' in mp, (
        "o log `pdfvec:por-prancha` parou de escrever o perímetro — sem ele a "
        "leitura de ~30/09 fica cega")
