# -*- coding: utf-8 -*-
"""A seção desenhada em OUTRA escala chega à IA pelos rótulos colados nela.

🩸 06/10/2026 — job de estrutura: o quadro "FORMA E ARM. DOS PILARES" desenha
as seções a 1:25 numa folha em cm de papel, e o motor leu 1 unidade = 1 m. O
retângulo 1,0 × 4,8 virou "pilar-parede 100 × 480 cm" → 142,56 m³ (no mesmo
job em modo arquitetura, 1.425,6 m³). Ao lado de cada retângulo: "25" e "120".
A seção é 25 × 120 cm.

🔑 k = rótulo ÷ lado, o MESMO nos dois lados, em ≥ 5 retângulos e ≥ 50 % dos
olhados; discordando do motor em cm, m e mm, e com o motor lendo MAIOR, a IA
recebe a seção PELOS RÓTULOS. Cada rótulo é do retângulo de centro mais perto
e só vale FORA dele; rótulo em layer de título/carimbo não vale; o lado menor
pelos rótulos tem ≥ 5 cm.

🪤 Nomes FICTÍCIOS (repositório público, regra nº6).
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402


def _quadro(n=11, lados=(1.0, 4.8), rotulos=("25", "120"), rotulados=None, layer_rot="TEXTO",
            como_cota=False, passo=10.0):
    """n retângulos s1 × s2 (unidade do desenho) no layer "2", a cada `passo`, cada um com os
    rótulos colados: o 1º ao lado do lado MENOR, o 2º ao lado do MAIOR. 🪤 Peça maior que o
    passo SOBREPÕE a vizinha, e o rótulo cai dentro dela (não vale): o controle fica vazio."""
    d = ezdxf.new("R2018")
    msp = d.modelspace()
    s1, s2 = lados
    for i in range(n):
        x, y = passo * i, 50.0
        msp.add_lwpolyline([(x, y), (x + s1, y), (x + s1, y + s2), (x, y + s2)], close=True,
                           dxfattribs={"layer": "2"})
        if rotulados is not None and i >= rotulados:
            continue
        if como_cota:
            # o texto da cota na escala da folha (0,25), como no desenho real — com o
            # padrão do ezdxf (2,5) o meio do texto cairia DENTRO da peça de 1 unidade
            ov = {"dimtxt": 0.25, "dimgap": 0.05, "dimasz": 0.1, "dimexe": 0.1, "dimexo": 0.05}
            dm = msp.add_linear_dim(base=(x, y - 0.6), p1=(x, y), p2=(x + s1, y), text=rotulos[0],
                                    override=ov, dxfattribs={"layer": layer_rot})
            dm.render()
            dm = msp.add_linear_dim(base=(x - 0.6, y), p1=(x, y), p2=(x, y + s2), angle=90, text=rotulos[1],
                                    override=ov, dxfattribs={"layer": layer_rot})
            dm.render()
            continue
        for k, rot in enumerate(rotulos):
            pos = (x + 0.2, y - 0.5) if k == 0 else (x - 1.2, y + s2 / 2)
            msp.add_text(rot, dxfattribs={"height": 0.25, "layer": layer_rot, "insert": pos})
    return msp


def _peca(msp, uf=1.0):
    ob = dx.objetos_repetidos_sem_bloco(msp, uf)
    ps = ob.get("2") or []
    assert len(ps) == 1, ob
    return ps[0]


# ══════════════════════════════════════════════════════════════════════════
#  O caso
# ══════════════════════════════════════════════════════════════════════════
def test_o_caso_a_secao_vem_dos_rotulos_e_nao_do_desenho():
    p = _peca(_quadro())
    assert (p["a_cm"], p["b_cm"]) == (100.0, 480.0), "a medida do desenho continua no registro"
    assert (p["rot_a_cm"], p["rot_b_cm"]) == (25.0, 120.0), p
    assert p["escala_k"] == 25.0 and p["escala_apoio"] == 11


def test_a_ia_le_a_secao_pelos_rotulos_e_ve_a_medida_do_desenho():
    p = _peca(_quadro())
    ext = dx.DXFExtraction(filename="p.dxf", blocks=[], walls=[], hatches=[], texts=[], layers=["2"],
                           dimensions=[], metadata={"objetos_sem_bloco": {"2": [p]}})
    txt = ext.to_structured_prompt()
    assert ("2: 11 retângulos de 25 × 120 cm PELOS RÓTULOS da vista (o desenho mede 100 × 480 cm: a vista "
            "está em outra escala) — use o rótulo") in txt, txt


def test_o_rotulo_que_vem_de_COTA_tambem_vale():
    p = _peca(_quadro(como_cota=True, layer_rot="COTAS"))
    assert (p.get("rot_a_cm"), p.get("rot_b_cm")) == (25.0, 120.0), p


def test_o_k_e_o_que_mais_retangulos_sustentam_nao_o_primeiro_par_achado():
    """🪤 06/10 (A/B): com mais de um par de rótulos coerente, o 1º par achado
    dependia da ordem dos textos. Aqui 6 dos 11 retângulos têm, À ESQUERDA (achado
    primeiro), um par distrator "10"/"48" (k = 10): vale o k = 25, que os 11 têm."""
    msp = _quadro()
    for i in range(6):
        x, y = 10.0 * i, 50.0
        msp.add_text("10", dxfattribs={"height": 0.25, "layer": "TEXTO", "insert": (x - 1.9, y - 0.4)})
        msp.add_text("48", dxfattribs={"height": 0.25, "layer": "TEXTO", "insert": (x - 1.8, y + 1.0)})
    p = _peca(msp)
    assert (p.get("rot_a_cm"), p.get("rot_b_cm")) == (25.0, 120.0), p


def test_k_quase_iguais_de_rotulos_diferentes_somam_apoio():
    """O apoio conta o k a ± 3 % (a tolerância do par), não o idêntico. 12
    retângulos: 4 com k 25, 4 com 25,4 e 4 com 24,6 — nenhum k idêntico chega à
    metade; a ± 3 %, os 12."""
    d = ezdxf.new("R2018")
    msp = d.modelspace()
    for i, (r1, r2) in enumerate([("25", "120")] * 4 + [("25,4", "122")] * 4 + [("24,6", "118")] * 4):
        x, y = 10.0 * i, 50.0
        msp.add_lwpolyline([(x, y), (x + 1.0, y), (x + 1.0, y + 4.8), (x, y + 4.8)], close=True,
                           dxfattribs={"layer": "2"})
        msp.add_text(r1, dxfattribs={"height": 0.25, "layer": "TEXTO", "insert": (x + 0.2, y - 0.5)})
        msp.add_text(r2, dxfattribs={"height": 0.25, "layer": "TEXTO", "insert": (x - 1.2, y + 2.4)})
    p = _peca(msp)
    assert p.get("escala_apoio") == 12 and p.get("rot_a_cm") == 25.0, p


def test_metade_dos_retangulos_com_rotulo_basta():
    p = _peca(_quadro(n=12, rotulados=6))
    assert p.get("rot_a_cm") == 25.0, p


# ══════════════════════════════════════════════════════════════════════════
#  CONTROLES — o que fica como o desenho mede
# ══════════════════════════════════════════════════════════════════════════
def _sem_rotulo(p):
    return not any(k in p for k in ("rot_a_cm", "rot_b_cm", "escala_k", "escala_apoio"))


def test_CONTROLE_sem_rotulo_o_registro_e_o_de_sempre():
    p = _peca(_quadro(rotulados=0))
    assert p == {"forma": "retângulo", "a_cm": 100.0, "b_cm": 480.0, "n": 11, "borda_m": 127.6,
                 "concentrada": False}, p


def test_CONTROLE_rotulo_em_layer_de_titulo_nao_vale():
    """A data e o número da folha ("22", "04") casavam com o retângulo do formato."""
    assert _sem_rotulo(_peca(_quadro(layer_rot="Q TEXTO TÍTULO")))
    assert _sem_rotulo(_peca(_quadro(layer_rot="CARIMBO")))


def test_CONTROLE_rotulo_que_confere_em_cm_e_em_metro():
    # o desenho em cm, lido em cm (1 cm por unidade): 25 × 120 com rótulos 25 e 120
    assert _sem_rotulo(_peca(_quadro(lados=(25.0, 120.0), passo=300.0), uf=0.01))
    # o desenho em m, lido em m, com rótulos em METRO
    assert _sem_rotulo(_peca(_quadro(rotulos=("1,00", "4,80"))))


def test_CONTROLE_peca_grande_cotada_em_metro_confere():
    """Desenho em cm, peça de 6 × 8 m cotada em METRO ("6,00", "8,00"): o rótulo
    confere com o motor. Sem a leitura em m, 6 × 8 cm passaria no piso de 5 cm."""
    assert _sem_rotulo(_peca(_quadro(lados=(600.0, 800.0), rotulos=("6,00", "8,00"), passo=2000.0), uf=0.01))


def test_CONTROLE_motor_MENOR_que_o_rotulo_fica():
    """O outro sentido só apareceu em arquitetura (unidade), marcado legenda."""
    assert _sem_rotulo(_peca(_quadro(rotulos=("250", "1200"))))


def test_CONTROLE_pouco_apoio():
    assert _sem_rotulo(_peca(_quadro(n=11, rotulados=4)))            # < 5 retângulos
    assert _sem_rotulo(_peca(_quadro(n=12, rotulados=5)))            # < 50 % dos olhados


def test_CONTROLE_cinco_retangulos_no_minimo_mesmo_com_metade():
    """O grupo do motor tem ≥ 10 peças, e aí "metade" já dá 5. A trava dos 5 vale
    se o mínimo do grupo baixar — testada na função, com 8 retângulos."""
    centros = [(10.0 * i, 50.0) for i in range(8)]
    cantos = [[(x - 0.5, y - 2.4), (x + 0.5, y - 2.4), (x + 0.5, y + 2.4), (x - 0.5, y + 2.4)] for x, y in centros]
    rot = sorted([(10.0 * i, 47.0, 25.0) for i in range(4)] + [(10.0 * i - 1.2, 50.0, 120.0) for i in range(4)])
    assert dx.escala_da_vista_pelos_rotulos(centros, 1.0, 4.8, rot, 100.0, cantos) is None      # 4 de 8
    rot5 = sorted(rot + [(40.0, 47.0, 25.0), (38.8, 50.0, 120.0)])
    assert dx.escala_da_vista_pelos_rotulos(centros, 1.0, 4.8, rot5, 100.0, cantos) == (25.0, 5)  # 5 de 8


def test_CONTROLE_um_rotulo_so_vale_pro_retangulo_mais_perto():
    """🩸 06/10 (A/B): paginação de fachada desenhada em cm, faixas de 157 × 820
    empilhadas. UM "15" e a cota da meia placa ("78,5", repetida) ficavam no raio
    de quase todas as faixas: 15 ÷ 157 = 78,5 ÷ 820 por acaso, e a régua dizia
    "15 × 78 PELOS RÓTULOS". O rótulo é do retângulo de centro mais perto."""
    d = ezdxf.new("R2018")
    msp = d.modelspace()
    for pilha in range(2):
        x0 = 100.0 * pilha
        for i in range(10):
            y = 2.96 * i
            msp.add_lwpolyline([(x0, y), (x0 + 8.2, y), (x0 + 8.2, y + 1.57), (x0, y + 1.57)], close=True,
                               dxfattribs={"layer": "2"})
        for rot, pos in (("15", (x0 + 9.6, 14.0)), ("78,5", (x0 + 9.6, 14.6)), ("78,5", (x0 + 9.7, 14.6))):
            msp.add_text(rot, dxfattribs={"height": 0.25, "layer": "COTAS", "insert": pos})
    assert _sem_rotulo(_peca(msp))


def test_CONTROLE_rotulo_DENTRO_da_peca_nao_e_a_cota_dela():
    """🩸 06/10 (A/B): a MOLDURA de cada detalhe de viga (4,81 × 5,98) tem os
    números do detalhe dentro dela; "16" e "20" no fundo davam 16 × 20 por acaso,
    e 21 detalhes iguais repetiam o acaso. A cota da seção fica FORA da peça."""
    msp = _quadro(lados=(4.81, 5.98), rotulos=())
    for i in range(11):
        cx, cy = 10.0 * i + 2.405, 50.0 + 2.99
        msp.add_text("16", dxfattribs={"height": 0.25, "layer": "TEXTO", "insert": (cx + 0.2, cy + 0.3)})
        msp.add_text("20", dxfattribs={"height": 0.25, "layer": "TEXTO", "insert": (cx - 0.5, cy - 1.0)})
    assert _sem_rotulo(_peca(msp))
    # o mesmo par, FORA (abaixo e à esquerda de cada peça), é a cota (k 3,34 → 16,1 × 20)
    p = _peca(_quadro(lados=(4.81, 5.98), rotulos=("16", "20")))
    assert (p.get("rot_a_cm"), p.get("rot_b_cm")) == (16.1, 20.0), p


def test_CONTROLE_so_um_lado_ou_lados_que_nao_concordam():
    assert _sem_rotulo(_peca(_quadro(rotulos=("25",))))
    assert _sem_rotulo(_peca(_quadro(rotulos=("25", "100"))))        # k 25 × 20,8


def test_CONTROLE_numero_de_item_minusculo_nao_e_secao():
    assert _sem_rotulo(_peca(_quadro(rotulos=("2", "9,6"))))         # 2 × 9,6 cm


def test_CONTROLE_quadrado_nao_diz_qual_lado_e_qual():
    assert _sem_rotulo(_peca(_quadro(lados=(1.0, 1.0), rotulos=("25", "25"))))


def test_a_falha_dos_rotulos_nao_derruba_a_contagem(monkeypatch):
    def _quebra(_msp):
        raise RuntimeError("texto ilegível")
    monkeypatch.setattr(dx, "_rotulos_numericos_da_vista", _quebra)
    p = _peca(_quadro())
    assert p["n"] == 11 and _sem_rotulo(p)


@pytest.mark.parametrize("nome, esperado", [("Q TEXTO TÍTULO", True), ("A-TITLE", True), ("SELO", True),
                                            ("FORMATO A1", True), ("COTAS", False), ("TEXTO", False)])
def test_layer_de_carimbo_do_rotulo(nome, esperado):
    assert dx._layer_de_carimbo_do_rotulo(nome) is esperado
