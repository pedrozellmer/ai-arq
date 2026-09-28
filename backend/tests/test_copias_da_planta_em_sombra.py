# -*- coding: utf-8 -*-
"""A planta repetida no modelo é CONTADA no log — e nenhum número muda.

📏 28/09/2026 (estudo de leitura, D1, 1º passo). No elétrico do 73c6f0ed a
prancha aparece em faixas do modelo: arquitetura ×3, pontos elétricos ×2, com
selo. Antes de tirar selo ou peça, duas semanas de sombra no log. Cada trava
do verificador tem aqui um controle que REPROVA sem ela.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

from dwg_extractor import BlockCount, copias_em_sombra  # noqa: E402

# uma "planta": 6 nomes, cada um com 2 a 4 peças espalhadas em ~12 × 10 m
PLANTA = {
    "TOMADA": [(1.0, 1.0), (4.0, 2.5), (9.5, 7.0), (11.0, 3.0)],
    "INTERRUPTOR": [(0.5, 6.0), (7.0, 9.0)],
    "LUMINARIA": [(3.0, 3.0), (6.0, 3.0), (9.0, 8.0)],
    "AR-COND": [(2.0, 9.5), (10.5, 9.5)],
    "QUADRO": [(0.2, 0.2), (5.5, 8.5)],
    "PONTO-TV": [(8.0, 1.5), (2.5, 5.0), (11.5, 6.0)],
}


def _blocos(copias, extra=None):
    pos = {n: [] for n in PLANTA}
    for vx, vy in copias:
        for n, ps in PLANTA.items():
            pos[n] += [(x + vx, y + vy) for x, y in ps]
    for n, ps in (extra or {}).items():
        pos[n] = pos.get(n, []) + ps
    return [BlockCount(name=n, count=len(ps), layer="0", positions=ps) for n, ps in pos.items()]


def test_a_planta_desenhada_duas_vezes_e_achada():
    c = copias_em_sombra(_blocos([(0, 0), (0, -60)]), 1.0)
    assert c and c["pecas"] == 16, c                    # 16 peças na cópia
    assert [v[:2] for v in c["vetores"]] == [[0.0, 60.0]], c
    assert c["vetores"][0][3] == 6, c


def test_a_planta_tres_vezes_sao_duas_copias():
    c = copias_em_sombra(_blocos([(0, 0), (0, -52), (0, -104)]), 1.0)
    assert c and c["pecas"] == 32, c                    # n − cópias = uma planta


def test_nome_nos_dois_andares_soma_os_dois_vetores():
    # como no elétrico: térreo e superior lado a lado, cada um copiado com o
    # seu vetor; "HH" tem 3 peças no térreo e 7 no superior. No vetor do
    # térreo ele casa 3 de 20 — por vetor cairia; junto, casa as 20.
    v_t, v_s = (5.0, -52.6), (1.75, -52.55)
    pos = {}
    for n, ps in PLANTA.items():
        pos[n + "_T"] = ps + [(x + v_t[0], y + v_t[1]) for x, y in ps]
        pos[n + "_S"] = [(x + 30, y) for x, y in ps] + [(x + 30 + v_s[0], y + v_s[1]) for x, y in ps]
    hh_t = [(1.0, 5.0), (6.0, 6.0), (10.0, 1.5)]
    hh_s = [(31.0 + 1.5 * i, 1.0 + 1.2 * i) for i in range(7)]
    pos["HH"] = (hh_t + [(x + v_t[0], y + v_t[1]) for x, y in hh_t]
                 + hh_s + [(x + v_s[0], y + v_s[1]) for x, y in hh_s])
    blocos = [BlockCount(name=n, count=len(ps), layer="0", positions=ps) for n, ps in pos.items()]
    c = copias_em_sombra(blocos, 1.0)
    assert c and c["nomes"].get("HH") == 10, c
    assert sorted(v[:2] for v in c["vetores"]) == [[1.75, -52.55], [5.0, -52.6]], c


def test_a_peca_que_so_existe_numa_copia_fica():
    # TV/telefone só na faixa C: sem par, não é cópia
    c = copias_em_sombra(_blocos([(0, 0), (0, -60)], {"TELEFONE": [(3.0, -55.0), (6.0, -52.0)]}), 1.0)
    assert "TELEFONE" not in c["nomes"], c


def test_o_vetor_e_em_metros_nao_em_unidade_do_desenho():
    # a mesma planta em mm: 60 m viram 60.000 no desenho
    mm = [BlockCount(name=b.name, count=b.count, layer="0",
                     positions=[(x * 1000, y * 1000) for x, y in b.positions])
          for b in _blocos([(0, 0), (0, -60)])]
    c = copias_em_sombra(mm, 0.001)
    assert c and c["pecas"] == 16 and [v[:2] for v in c["vetores"]] == [[0.0, 60.0]], c


def test_CONTROLE_quatro_nomes_e_um_de_carona_nao_votam():
    # 4 nomes copiados inteiros e 1 com 7 peças de que só 1 casa: ele vota
    # no vetor, mas não conta como cópia — sobram 4 nomes
    pos = dict(list(PLANTA.items())[:4])
    blocos = [BlockCount(name=n, count=2 * len(ps), layer="0",
                         positions=ps + [(x, y - 60) for x, y in ps]) for n, ps in pos.items()]
    carona = [(1.5 * i, 2.0 + 0.5 * i) for i in range(6)] + [(0.0, -58.0)]
    blocos.append(BlockCount(name="CARONA", count=7, layer="0", positions=carona))
    assert copias_em_sombra(blocos, 1.0) == {}


def test_CONTROLE_andares_diferentes_que_so_dividem_o_nucleo():
    # dois andares DIFERENTES lado a lado: 3 nomes iguais nos dois (a planta
    # se repete ali) e 3 que só batem nas 2 peças do núcleo (shaft, escada)
    # de 10. No vetor os 6 votam; no fim, 3 nomes não sustentam uma cópia.
    v = (0.0, 60.0)
    blocos = []
    for k, (n, ps) in enumerate(list(PLANTA.items())[:3]):
        blocos.append(BlockCount(name=n, count=2 * len(ps), layer="0",
                                 positions=ps + [(x + v[0], y + v[1]) for x, y in ps]))
    for k in range(3):
        nucleo = [(5.0 + k * 0.5, 4.0), (6.0 + k * 0.5, 7.0)]
        resto_a = [(0.5 + 1.3 * i, 0.4 + 0.2 * k) for i in range(8)]
        resto_b = [(0.9 + 1.4 * i, 64.5 + 0.3 * k + 0.1 * i) for i in range(8)]
        ps = nucleo + resto_a + [(x + v[0], y + v[1]) for x, y in nucleo] + resto_b
        blocos.append(BlockCount(name=f"NUCLEO{k}", count=len(ps), layer="0", positions=ps))
    assert copias_em_sombra(blocos, 1.0) == {}


def test_o_par_solto_de_um_nome_nao_sustenta_outro_vetor():
    # a planta (6 nomes) copiada por (0, 60); ao lado da de baixo, 4 nomes
    # copiados por (0, 40) — e a TOMADA, que é da planta, tem 1 peça solta
    # que por acaso cai a (0, 40) da TOMADA de baixo. Esse 2º vetor tem 4
    # nomes de verdade e um carona: não vale.
    blocos = _blocos([(0, 0), (0, -60)], {"TOMADA": [(1.0, -19.0)]})
    grupo = {"A1": [(40, -60), (44, -55), (50, -51)], "A2": [(41, -58), (47, -59), (52, -52)],
             "A3": [(43, -53), (49, -56)], "A4": [(45, -57), (51, -54), (42, -51)]}
    for n, ps in grupo.items():
        ps = [(float(x), float(y)) for x, y in ps]
        blocos.append(BlockCount(name=n, count=2 * len(ps), layer="0",
                                 positions=ps + [(x, y + 40) for x, y in ps]))
    c = copias_em_sombra(blocos, 1.0)
    assert [v[:2] for v in c["vetores"]] == [[0.0, 60.0]], c
    assert c["nomes"]["TOMADA"] == 4, c


def test_CONTROLE_quatro_nomes_nao_votam():
    pos = dict(list(PLANTA.items())[:4])
    blocos = [BlockCount(name=n, count=2 * len(ps), layer="0",
                         positions=ps + [(x, y - 60) for x, y in ps]) for n, ps in pos.items()]
    assert copias_em_sombra(blocos, 1.0) == {}


@pytest.mark.parametrize("fator", [1.0, 0.001])          # metro e milímetro
def test_CONTROLE_pecas_perto_nao_sao_planta_repetida(fator):
    # bacias lado a lado a 0,85 m (o cliente aprovou 3): vetor curto — em
    # METROS; em mm, 850 unidades de desenho passariam num piso de 2
    # banheiros empilhados numa coluna: as caixas não se cruzam e a faixa
    # entre as bacias é vazia — só o piso em metros segura
    s = 1.0 / fator
    blocos = [BlockCount(name=f"LOUCA{k}", count=2, layer="0",
                         positions=[(0.0, 10.0 * k * s), (0.85 * s, 10.0 * k * s)]) for k in range(6)]
    assert copias_em_sombra(blocos, fator) == {}


def test_CONTROLE_uma_peca_de_cada_nome_longe_nao_e_copia():
    # cada nome tem 5 peças aqui e UMA lá longe, alinhada: o vetor casa 1 de 6
    # por nome — não é a planta repetida. (Nome de 1–2 peças repetido numa
    # ampliação É peça contada duas vezes: esse a sombra deve mostrar.)
    blocos = [BlockCount(name=f"PECA{k}", count=6, layer="0",
                         # a planta fica ABAIXO da peça casada: a faixa até a
                         # de longe é vazia, só a cobertura segura
                         positions=[(2.0 * i + k, -1.5 * i) for i in range(5)] + [(k, 60.0)])
              for k in range(6)]
    assert copias_em_sombra(blocos, 1.0) == {}


def test_CONTROLE_fileiras_paralelas_na_diagonal_nao_sao_copia():
    # duas fileiras de luminárias na diagonal, a 3 m uma da outra: na direção
    # do vetor não se sobrepõem, mas é o MESMO desenho (as caixas se cruzam)
    # (os nomes correm na MESMA diagonal: só o teste da caixa segura)
    blocos = [BlockCount(name=f"LUM{k}", count=8, layer="0",
                         positions=[(6.0 * i + k, 6.0 * i + k) for i in range(4)]
                         + [(6.0 * i + k + 3, 6.0 * i + k - 3) for i in range(4)]) for k in range(6)]
    assert copias_em_sombra(blocos, 1.0) == {}


def test_CONTROLE_a_grade_regular_nao_encadeia():
    # 6 nomes numa grade de 3 m: o passo da grade é votado por todos, mas
    # originais e cópias ficam na mesma caixa — não são dois desenhos
    blocos = [BlockCount(name=f"MESA{k}", count=8, layer="0",
                         positions=[(3.0 * i, 1.0 * k) for i in range(8)]) for k in range(6)]
    assert copias_em_sombra(blocos, 1.0) == {}


def test_CONTROLE_sem_escala_nao_mede():
    assert copias_em_sombra(_blocos([(0, 0), (0, -60)]), 0) == {}


def test_a_linha_do_log_leva_as_copias():
    import main as m

    class _Ex:
        metadata = {"copias_sombra": {"pecas": 16, "vetores": [[0.0, 60.0, 16, 6, ["TOMADA"]]],
                                      "nomes": {"TOMADA": 4, "LUMINARIA": 3}}}
    s = m._procedencia_dos_blocos(_Ex())
    assert "copias=[pecas=16 v=0.0,60.0:16/6 nomes=TOMADA=4|LUMINARIA=3]" in s, s
