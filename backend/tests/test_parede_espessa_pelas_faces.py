# -*- coding: utf-8 -*-
"""Parede de mais de 40 cm somada pelas duas faces não sai medida (E12).

🩸 04/10/2026 — conferência da lista de dano, E12. Um estacionamento entregou
"Parede de alvenaria/concreto 647,88 ml ✓" (real ~218 m). Com o eixo do H73 a
soma de hoje é 347,9 — mas a parede de 50 cm do perímetro passa do teto do
par (40 cm) e conta as DUAS faces inteiras, e o eixo tirou o layer da zona
cinza: a soma ia para a chave do selo e voltava ✓; o relato ainda dizia "JÁ
pelo EIXO (… corte e detalhe já fora)".

Regras:
- faces SEM PAR a 40 cm–1 m, sobrepostas em ≥ 1 m, com sobra ≥ 5 m e ≥ 5 % da
  soma do layer → ressalva do layer: fora da chave do selo e do resgate, ⚠ no
  prompt, e a linha ✓ em metro que cita o layer cai para estimado;
- conta o que ficou depois da leitura por folha (corte/detalhe fora);
- SÓ REBAIXA: nenhuma soma muda.
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import dwg_extractor as dx  # noqa: E402
import engine_rules as er  # noqa: E402
import test_desenho_no_modelo as tdm  # noqa: E402


def _ler(tmp_path, desenha, insunits=6):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = insunits
    desenha(doc.modelspace())
    p = str(tmp_path / "parede.dxf")
    doc.saveas(p)
    return dx.extract_dxf(p)


def _linha(msp, layer, a, b, k=1.0):
    msp.add_line((a[0] * k, a[1] * k), (b[0] * k, b[1] * k), dxfattribs={"layer": layer})


def _par(msp, layer, x0, x1, y, esp, k=1.0):
    _linha(msp, layer, (x0, y), (x1, y), k)
    _linha(msp, layer, (x0, y + esp), (x1, y + esp), k)


def _ret(msp, layer, x0, y0, x1, y1, k=1.0):
    for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        _linha(msp, layer, a, b, k)


def _estacionamento(layer="A-WALL", esp=0.50, k=1.0):
    """Perímetro de 30 × 20 m com parede de `esp` pelas 2 faces (sem par) +
    20 paredes internas de 8 m a 15 cm (em par: 62 % do layer, o eixo roda)."""
    def d(m):
        _ret(m, layer, 0, 0, 30, 20, k)
        _ret(m, layer, esp, esp, 30 - esp, 20 - esp, k)
        for x0 in (3, 15):
            for i in range(10):
                _par(m, layer, x0, x0 + 8, 3 + i * 1.5, 0.15, k)
    return d


# ══════════════════════════════════════════════════════════════════════════
#  1. O caso
# ══════════════════════════════════════════════════════════════════════════
def test_o_caso_perimetro_de_50_cm_pelas_faces_ganha_a_ressalva(tmp_path):
    ex = _ler(tmp_path, _estacionamento())
    md = ex.metadata
    esp = (md.get("parede_espessa_pelas_faces") or {}).get("A-WALL")
    # internas pelo eixo (160) + as duas faces do perímetro (100 + 96)
    assert ex.get_walls_by_layer()["A-WALL"] == pytest.approx(356.0, abs=0.5), "nenhuma soma muda"
    assert esp and esp["sobra_m"] == pytest.approx(96.0, abs=1.0), esp
    assert esp["fracao"] == pytest.approx(96.0 / 356.0, abs=0.02)
    # o eixo rodou: o layer NÃO está na zona cinza — é a porta que o H73 abriu
    assert "A-WALL" not in (md.get("parede_zona_cinza") or {})
    assert "A-WALL" in er.layers_que_nao_provam(md)


def test_a_ia_e_avisada_na_linha_do_layer_e_o_registro_nao_vai_cru(tmp_path):
    txt = _ler(tmp_path, _estacionamento()).to_structured_prompt()
    linha = next(l for l in txt.splitlines() if l.strip().startswith("A-WALL:"))
    assert "PAREDE ESPESSA PELAS DUAS FACES" in linha and "não use como medido" in linha, linha
    assert "parede_espessa_pelas_faces" not in txt


def test_o_relato_nao_diz_mais_ja_pelo_eixo_nem_corte_fora(tmp_path, monkeypatch):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    rel = _ler(tmp_path, _estacionamento()).metadata["parede_linha_dupla"]
    assert "JÁ pelo EIXO" not in rel and "corte e detalhe já fora" not in rel, rel
    assert "MAIS de 40 cm" in rel and "NÃO é o comprimento" in rel, rel


def test_desenho_em_milimetro_tambem(tmp_path):
    ex = _ler(tmp_path, _estacionamento(k=1000.0), insunits=4)
    esp = (ex.metadata.get("parede_espessa_pelas_faces") or {}).get("A-WALL")
    assert esp and esp["sobra_m"] == pytest.approx(96.0, abs=1.0), esp


def test_o_muro_so_de_parede_grossa_sem_par_nenhum(tmp_path):
    """O muro em "L" de 50 cm pelas 2 faces: nada pareia a 40 cm, o eixo não
    roda e o layer não entra na zona cinza (0 % em par) — passava calado."""
    def d(m):
        for a, b in (((0, 0), (12, 0)), ((12, 0), (12, 8)), ((0.5, 0.5), (11.5, 0.5)),
                     ((11.5, 0.5), (11.5, 8))):
            _linha(m, "L-SITE-WALL", a, b)
    md = _ler(tmp_path, d).metadata
    assert not (md.get("parede_zona_cinza") or {}).get("L-SITE-WALL")
    assert "L-SITE-WALL" in (md.get("parede_espessa_pelas_faces") or {}), sorted(md)


def test_SOMA_IGUAL_com_e_sem_o_registro():
    """O registro não toca no pareamento: as mesmas paredes, o mesmo número."""
    walls = []
    for y, x0, x1 in ((0, 0, 30), (0.5, 0.5, 29.5), (3, 3, 11), (3.15, 3, 11)):
        walls.append(dx.WallSegment(layer="A-WALL", length=x1 - x0, start=(x0, y), end=(x1, y)))
    a, _ = dx._corrigir_parede_linha_dupla(list(walls), 1.0, {})
    out = []
    b, _ = dx._corrigir_parede_linha_dupla(list(walls), 1.0, {}, out)
    assert [w.length for w in a] == [w.length for w in b]
    assert out and sum(s for _w, s in out) == pytest.approx(29.0, abs=0.01)


@pytest.mark.parametrize("sep,esperado", [(0.30, 0.0), (0.50, 10.0), (0.95, 10.0), (1.20, 0.0)])
def test_a_faixa_da_parede_grossa_e_de_40_cm_a_1_m(sep, esperado):
    """Duas linhas sem par, 10 m sobrepostas: só a 40 cm–1 m são parede grossa."""
    d, t0, t1 = {0: 0.0, 1: sep}, {0: 0.0, 1: 0.0}, {0: 10.0, 1: 10.0}
    sob = dx._sobra_das_faces_espessas([([0, 1], d, t0, t1)], {}, 0.40, 1.00, 1.0)
    assert sum(sob.values()) == pytest.approx(esperado)


def test_cada_face_entra_num_par_so():
    """Três linhas a 50 cm: a do meio é face de UM par (o mais estreito primeiro)."""
    d, t0, t1 = {0: 0.0, 1: 0.5, 2: 1.0}, {0: 0, 1: 0, 2: 0}, {0: 10.0, 1: 10.0, 2: 10.0}
    sob = dx._sobra_das_faces_espessas([([0, 1, 2], d, t0, t1)], {}, 0.40, 1.00, 1.0)
    assert sum(sob.values()) == pytest.approx(10.0)


# ══════════════════════════════════════════════════════════════════════════
#  2. O que NÃO marca
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("esp", [0.15, 0.25, 0.38])
def test_CONTROLE_parede_de_ate_40_cm_em_par_nao_marca(tmp_path, monkeypatch, esp):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    def d(m):
        for i in range(12):
            _par(m, "A-WALL", 0, 10, i * 2.0, esp)
    ex = _ler(tmp_path, d)
    assert not ex.metadata.get("parede_espessa_pelas_faces"), ex.metadata.get("parede_espessa_pelas_faces")
    assert ex.get_walls_by_layer()["A-WALL"] == pytest.approx(120.0, abs=0.5)
    # pelo eixo, sim; mas sem desenho com título não houve corte nem detalhe a tirar
    rel = ex.metadata["parede_linha_dupla"]
    assert "JÁ pelo EIXO" in rel and "corte e detalhe já fora" not in rel, rel


def test_CONTROLE_o_mesmo_perimetro_a_15_cm_nao_marca(tmp_path):
    ex = _ler(tmp_path, _estacionamento(esp=0.15))
    assert not ex.metadata.get("parede_espessa_pelas_faces")


def test_CONTROLE_paredes_a_mais_de_1_m_sao_paredes_diferentes(tmp_path):
    def d(m):
        for i in range(6):
            _linha(m, "A-WALL", (0, i * 1.5), (20, i * 1.5))
    assert not _ler(tmp_path, d).metadata.get("parede_espessa_pelas_faces")


def test_CONTROLE_pilarete_nao_e_parede_grossa(tmp_path):
    """Pilaretes de 0,58 × 0,50: lados a 50–58 cm, mas sobrepostos < 1 m."""
    def d(m):
        for i in range(40):
            _ret(m, "A-WALL", i * 3.0, 0, i * 3.0 + 0.58, 0.50)
        _par(m, "A-WALL", 0, 30, 5, 0.15)
    assert not _ler(tmp_path, d).metadata.get("parede_espessa_pelas_faces")


def test_CONTROLE_shaft_entre_duas_paredes_de_linha_dupla(tmp_path):
    """Duas paredes de 15 cm em par com 60 cm de vão no meio: cada face já
    pareou com a sua — não é parede grossa."""
    def d(m):
        for i in range(4):
            y = i * 5.0
            _par(m, "A-WALL", 0, 20, y, 0.15)
            _par(m, "A-WALL", 0, 20, y + 0.75, 0.15)
    assert not _ler(tmp_path, d).metadata.get("parede_espessa_pelas_faces")


def test_CUSTO_DOCUMENTADO_linhas_soltas_com_parede_fina_no_meio_marcam(tmp_path):
    """Linha solta, parede de 15 cm e outra linha solta a 95 cm. 🩸 04/10
    (revisão da Projetos): a linha DENTRO da faixa não desarma mais — senão o
    revestimento ou o isolamento da parede grossa a escondiam. Este desenho
    não se separa de uma parede de 95 cm com linhas dentro: marca. Custa só o
    ✓ (o número não muda)."""
    def d(m):
        for i in range(3):
            y = i * 4.0
            _linha(m, "A-WALL", (0, y), (10, y))
            _par(m, "A-WALL", 0, 10, y + 0.45, 0.15)
            _linha(m, "A-WALL", (0, y + 0.95), (10, y + 0.95))
    ex = _ler(tmp_path, d)
    assert "A-WALL" in (ex.metadata.get("parede_espessa_pelas_faces") or {})
    assert ex.get_walls_by_layer()["A-WALL"] == pytest.approx(90.0, abs=0.5)


@pytest.mark.parametrize("dentro", [0.08, 0.10, 0.15, 0.25])
def test_linha_de_revestimento_dentro_da_parede_grossa_nao_desarma(tmp_path, dentro):
    """🩸 04/10 (revisão da Projetos): o perímetro de 50 cm com uma linha a
    `dentro` da face (revestimento, isolamento). A face pareava com ela como
    parede fina e o perímetro escapava — o relato voltava a "JÁ pelo EIXO"."""
    def d(m):
        _estacionamento()(m)
        _ret(m, "A-WALL", dentro, dentro, 30 - dentro, 20 - dentro)
    ex = _ler(tmp_path, d)
    esp = (ex.metadata.get("parede_espessa_pelas_faces") or {}).get("A-WALL")
    assert esp and esp["sobra_m"] == pytest.approx(96.0, abs=1.0), ex.metadata.get("parede_espessa_pelas_faces")
    assert "JÁ pelo EIXO" not in (ex.metadata.get("parede_linha_dupla") or "")


def _sobra_um_par(par_a, par_b):
    """Duas faces a 50 cm, 10 m sobrepostas; `par_a`/`par_b` = de que lado cada
    uma ficou em par no eixo (+1 acima, −1 abaixo, 0 sem par)."""
    d, t0, t1 = {0: 0.0, 1: 0.5}, {0: 0.0, 1: 0.0}, {0: 10.0, 1: 10.0}
    em_par = {k: [(0.0, 10.0, lado)] for k, lado in ((0, par_a), (1, par_b)) if lado}
    return sum(dx._sobra_das_faces_espessas([([0, 1], d, t0, t1)], em_par, 0.40, 1.00, 1.0).values())


@pytest.mark.parametrize("par_a,par_b,esperado", [
    (0, 0, 10.0),      # as duas sem par: a parede grossa
    (+1, 0, 10.0),     # a de baixo pareou pra DENTRO (revestimento): ainda é ela
    (0, -1, 10.0),     # a de cima pareou pra dentro: idem
    (-1, 0, 0.0),      # a de baixo pareou pra FORA: é face de outra parede
    (0, +1, 0.0),      # a de cima pareou pra fora: idem
    (+1, -1, 0.0),     # as duas pra dentro: duas paredes finas com um vão (shaft)
])
def test_o_lado_do_par_decide(par_a, par_b, esperado):
    assert _sobra_um_par(par_a, par_b) == pytest.approx(esperado)


# ── 🔒 04/10 (revisão da Projetos): a régua da parede grossa nunca derruba o eixo ──
def _paredes_finas_e_muro():
    W = dx.WallSegment
    ws = []
    for i in range(10):                       # 10 paredes de 15 cm em par: o eixo roda
        ws += [W("PAREDE", 8, (0, i * 3), (8, i * 3)), W("PAREDE", 8, (0, i * 3 + 0.15), (8, i * 3 + 0.15))]
    ws += [W("PAREDE", 30, (0, 40), (30, 40)), W("PAREDE", 30, (0, 40.5), (30, 40.5))]   # muro de 50 cm
    return ws


def test_se_a_regua_falha_o_eixo_continua(monkeypatch):
    ws = _paredes_finas_e_muro()
    sem, _ = dx._corrigir_parede_linha_dupla(list(ws), 1.0, {})

    def _falha(*a, **k):
        raise MemoryError("sonda")
    monkeypatch.setattr(dx, "_sobra_das_faces_espessas", _falha)
    out = []
    com, rel = dx._corrigir_parede_linha_dupla(list(ws), 1.0, {}, out)
    assert sum(w.length for w in com) == pytest.approx(sum(w.length for w in sem)) == pytest.approx(140.0)
    assert out == [] and "PAREDE" in rel


def test_CONTROLE_sem_falha_a_mesma_soma_e_a_marca(monkeypatch):
    out = []
    com, _ = dx._corrigir_parede_linha_dupla(_paredes_finas_e_muro(), 1.0, {}, out)
    assert sum(w.length for w in com) == pytest.approx(140.0)
    assert sum(s for _w, s in out) == pytest.approx(30.0)


def test_acima_do_teto_de_comparacoes_a_marca_nao_e_medida_e_o_eixo_segue(monkeypatch):
    with pytest.raises(dx._EspessaGrandeDemais):
        d, t0, t1 = {0: 0.0, 1: 0.5, 2: 1.0}, {0: 0, 1: 0, 2: 0}, {0: 10.0, 1: 10.0, 2: 10.0}
        dx._sobra_das_faces_espessas([([0, 1, 2], d, t0, t1)], {}, 0.40, 1.00, 1.0, max_comparacoes=1)
    monkeypatch.setattr(dx, "_PAREDE_ESPESSA_MAX_COMPARACOES", 1)
    out = []
    com, _ = dx._corrigir_parede_linha_dupla(_paredes_finas_e_muro(), 1.0, {}, out)
    assert out == [] and sum(w.length for w in com) == pytest.approx(140.0)


@pytest.mark.parametrize("n_finas,grossa", [
    (4, 4.0),      # sobra 4 m (< 5 m) em 48 m: 8 % — barra pelos METROS
    (60, 7.0),     # sobra 7 m em 614 m: 1 % — barra pela FRAÇÃO
])
def test_CONTROLE_pouca_sobra_nao_marca(tmp_path, n_finas, grossa):
    def d(m):
        for i in range(n_finas):
            _par(m, "A-WALL", 0, 10, i * 2.0, 0.15)
        _par(m, "A-WALL", 0, grossa, -10.0, 0.50)
    assert not _ler(tmp_path, d).metadata.get("parede_espessa_pelas_faces")


def test_CONTROLE_layer_que_nao_e_parede_fica_fora(tmp_path):
    md = _ler(tmp_path, _estacionamento(layer="CALCADA")).metadata
    assert not md.get("parede_espessa_pelas_faces")


def test_CUSTO_DOCUMENTADO_duas_paredes_de_linha_unica_com_vao_marcam(tmp_path):
    """Paredes de linha ÚNICA a 60 cm uma da outra (shaft) MARCAM: não dá pra
    separar das faces de uma parede grossa. Custa só o ✓ (o número não muda)."""
    def d(m):
        for i in range(4):
            _linha(m, "A-WALL", (0, i * 5.0), (20, i * 5.0))
            _linha(m, "A-WALL", (0, i * 5.0 + 0.6), (20, i * 5.0 + 0.6))
    ex = _ler(tmp_path, d)
    assert "A-WALL" in (ex.metadata.get("parede_espessa_pelas_faces") or {})
    assert ex.get_walls_by_layer()["A-WALL"] == pytest.approx(160.0, abs=0.5)


# ══════════════════════════════════════════════════════════════════════════
#  3. Depois da leitura por folha: o corte não conta
# ══════════════════════════════════════════════════════════════════════════
def _folha_com_parede_grossa_no_corte(tmp_path):
    p = tdm._folha(tmp_path, titulo_detalhe='%%UCORTE "A-A"')
    doc = ezdxf.readfile(p)
    msp = doc.modelspace()
    _par(msp, "A-WALL", 5, 15, 24.0, 0.15)            # planta: parede fina, pelo eixo
    _par(msp, "A-WALL", 4.5, 11.5, 9.0, 0.50)         # corte: parede de 50 cm
    doc.saveas(p)
    return p


def test_parede_grossa_so_no_corte_nao_marca(tmp_path, monkeypatch):
    monkeypatch.delenv("LEITURA_POR_FOLHA", raising=False)
    ex = dx.extract_dxf(_folha_com_parede_grossa_no_corte(tmp_path))
    assert not ex.metadata.get("parede_espessa_pelas_faces"), ex.metadata.get("parede_espessa_pelas_faces")
    assert ex.get_walls_by_layer()["A-WALL"] == pytest.approx(10.0, abs=0.1)
    # a folha reconheceu o corte: aqui o relato pode dizer que ele já saiu
    assert "corte e detalhe já fora" in ex.metadata["parede_linha_dupla"]


def test_CONTROLE_sem_a_leitura_por_folha_o_corte_fica_e_marca(tmp_path, monkeypatch):
    monkeypatch.setenv("LEITURA_POR_FOLHA", "0")
    ex = dx.extract_dxf(_folha_com_parede_grossa_no_corte(tmp_path))
    esp = (ex.metadata.get("parede_espessa_pelas_faces") or {}).get("A-WALL")
    assert esp and esp["sobra_m"] == pytest.approx(7.0, abs=0.1), ex.metadata.get("parede_espessa_pelas_faces")


def test_o_relato_so_diz_corte_fora_quando_a_folha_reconheceu():
    w = [dx.WallSegment(layer="A", length=5.0, start=(0, 0), end=(5, 0))]
    rel = "A: 10.0m de face -> 5.0m de eixo (1 par(es))"
    assert "corte e detalhe já fora" not in dx._relato_do_eixo_na_soma(rel, w, corte_fora=False)
    assert "corte e detalhe já fora" in dx._relato_do_eixo_na_soma(rel, w, corte_fora=True)
    assert "JÁ pelo EIXO" not in dx._relato_do_eixo_na_soma(rel, w, espessas={"A": {}})


# ══════════════════════════════════════════════════════════════════════════
#  4. O selo
# ══════════════════════════════════════════════════════════════════════════
def test_a_linha_confirmada_em_metro_cai():
    conf, obs, reb = er.selo_apos_parede_espessa(
        "confirmado", "layer A-WALL", "ml", ["A-WALL"], {"A-WALL": {}})
    assert reb and conf == "estimado" and er.MARCA_PAREDE_ESPESSA in obs
    assert er.MARCA_PAREDE_ESPESSA in er.MARCAS_DE_REBAIXAMENTO


@pytest.mark.parametrize("unit,citado", [("m²", ["A-WALL"]), ("un", ["A-WALL"]), ("ml", ["OUTRO"])])
def test_CONTROLE_area_contagem_ou_outro_layer_seguem(unit, citado):
    conf, obs, reb = er.selo_apos_parede_espessa("confirmado", "x", unit, citado, {"A-WALL": {}})
    assert not reb and conf == "confirmado"


# 🩸 04/10 (revisão da Projetos): nomes que o leitor de layers da observação corta
# (espaço, acento, ponto, '$', começa com '-') e a observação sem a palavra "layer"
@pytest.mark.parametrize("layer,obs", [
    ("ARQ_PAREDE EQUIPAMENTOS", "Fonte: layer 'ARQ_PAREDE EQUIPAMENTOS' = 300,00 m."),
    ("EQUIPAMENTO PAREDE", "Fonte: layer EQUIPAMENTO PAREDE = 37,70 m."),
    ("1_PLANTA BAIXA_1_ARQ-ALV.Soco de Alvenaria",
     "Fonte: layer '1_PLANTA BAIXA_1_ARQ-ALV.Soco de Alvenaria' = 141,7 m."),
    ("ARQ-DIVISÓRIA", "Fonte: layer 'ARQ-DIVISÓRIA' = 146,0 m."),
    ("- ARQ - ALVENARIA", "Fonte: layer '- ARQ - ALVENARIA' = 5880 m."),
    ("Intermediário$0$ARQ-ALV-ALT", "Fonte: layer 'Intermediário$0$ARQ-ALV-ALT' = 1532 m."),
    ("A-WALL", "Fonte: comprimento do A-WALL = 347,90 m."),
])
def test_a_trava_acha_o_layer_que_o_leitor_da_observacao_corta(layer, obs):
    from main import _layers_da_obs
    conf, o, reb = er.selo_apos_parede_espessa("confirmado", obs, "m", _layers_da_obs(obs),
                                               {layer.strip().upper()})
    assert reb and conf == "estimado" and er.MARCA_PAREDE_ESPESSA in o, (layer, _layers_da_obs(obs))


@pytest.mark.parametrize("unit", ["metro", "metros", "mts", "m linear", "M", "ML", "m.l."])
def test_a_trava_vale_pra_toda_unidade_de_comprimento(unit):
    conf, _o, reb = er.selo_apos_parede_espessa("confirmado", "layer A-WALL", unit, ["A-WALL"], {"A-WALL"})
    assert reb and conf == "estimado", unit


@pytest.mark.parametrize("marcado,obs,unit", [
    ("ARQ_PAREDE EQUIPAMENTOS", "Fonte: layer 'ARQ_PAREDE' = 300,00 m.", "m"),       # outro layer, sem marca
    ("A-WALL", "Fonte: layer 'A-WALL-PATT' = 63,23 m.", "m"),                         # borda do nome
    ("A-WALL", "Fonte: área hachurada do layer 'A-WALL' = 63,23 m².", "m²"),         # área não é tocada
    ("A-WALL", "Fonte: layer 'A-WALL' = 12 un.", "un"),
])
def test_CONTROLE_a_procura_direta_nao_pega_outro_layer_nem_outra_grandeza(marcado, obs, unit):
    from main import _layers_da_obs
    conf, _o, reb = er.selo_apos_parede_espessa("confirmado", obs, unit, _layers_da_obs(obs),
                                                {marcado.upper()})
    assert not reb and conf == "confirmado", (marcado, obs)


# 🩸 04/10 (medido em linhas ✓ reais): o layer marcado cujo nome é uma PALAVRA
# ("FOLHA", "Alvenaria") casava a palavra solta na observação e derrubava linhas
# de OUTROS layers. Nome só de letras vale só onde a observação cita layer.
@pytest.mark.parametrize("marcado,obs", [
    ("FOLHA", "Fonte: comprimento total do layer 'ELE-T-APARENTE' = 26,68 m. Bitola conforme folha ELE-000."),
    ("Alvenaria", "Fonte: layer 'PINTURA-EXT' = 120,00 m; paredes de alvenaria rebocadas."),
    ("Margem Externa", "Fonte: layer 'MURO' = 40 m, na margem externa do lote."),
])
def test_CONTROLE_nome_que_e_palavra_solta_no_texto_fica(marcado, obs):
    from main import _layers_da_obs
    conf, _o, reb = er.selo_apos_parede_espessa("confirmado", obs, "ml", _layers_da_obs(obs), {marcado.upper()})
    assert not reb and conf == "confirmado", (marcado, obs)


@pytest.mark.parametrize("marcado,obs", [
    ("Alvenaria", "Fonte: comprimento do layer 'Alvenaria' = 3.029,80 m."),
    ("Alvenaria", "Fonte: comprimento do layer ALVENARIA = 3.029,80 m."),
    ("ALVENARIA", "Fonte: comprimento do layer 'alvenária' = 3.029,80 m."),        # caixa e acento
    ("Alvenaria", "Fonte: comprimento de 'ALVENARIA' = 3.029,80 m."),              # entre aspas, sem "layer"
    ("Alvenaria", "Fonte: camada Alvenaria = 3.029,80 m."),
    ("Margem Externa", "Fonte: layer 'Margem  Externa' = 40 m."),                  # espaço duplo
    ("ARQ-DIVISÓRIA", "Fonte: comprimento do ARQ-DIVISORIA = 146,0 m."),           # sem o acento
])
def test_o_nome_citado_como_layer_cai(marcado, obs):
    from main import _layers_da_obs
    conf, _o, reb = er.selo_apos_parede_espessa("confirmado", obs, "ml", _layers_da_obs(obs), {marcado.upper()})
    assert reb and conf == "estimado", (marcado, obs)


def test_o_laco_de_producao_rebaixa_o_layer_com_espaco_no_nome():
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    item = {"item_num": "1", "description": "Parede de alvenaria",
            "unit": "ml", "quantity": 327.96, "confidence": "confirmado",
            "observations": "Fonte: comprimento do layer 'ARQ_PAREDE EQUIPAMENTOS' = 327.96 m."}
    itens, _e, _ = _laco_de_itens_de_producao(
        [item], areas={}, compr={"ARQ_PAREDE EQUIPAMENTOS": 327.96},
        extra={"_esp_ly": {"ARQ_PAREDE EQUIPAMENTOS"}})
    assert itens[0].confidence.value == "estimado" and "PAREDE ESPESSA" in itens[0].observations


def test_o_laco_de_producao_rebaixa_a_linha():
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    item = {"item_num": "1", "description": "Parede de alvenaria/concreto",
            "unit": "ml", "quantity": 347.9, "confidence": "confirmado",
            "observations": "Fonte: comprimento do layer 'A-WALL' = 347.90 m."}
    itens, _e, _ = _laco_de_itens_de_producao(
        [item], areas={}, compr={"A-WALL": 347.9}, extra={"_esp_ly": {"A-WALL"}})
    assert itens[0].confidence.value == "estimado" and "PAREDE ESPESSA" in itens[0].observations


def test_CONTROLE_o_laco_sem_a_marca_segue_como_veio():
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    item = {"item_num": "1", "description": "Parede de alvenaria/concreto",
            "unit": "ml", "quantity": 347.9, "confidence": "confirmado",
            "observations": "Fonte: comprimento do layer 'A-WALL' = 347.90 m."}
    itens, _e, _ = _laco_de_itens_de_producao(
        [item], areas={}, compr={"A-WALL": 347.9}, extra={"_esp_ly": set()})
    assert "PAREDE ESPESSA" not in itens[0].observations


class _Extr:
    def __init__(self, md, walls):
        self.metadata = md
        self._w = walls

    def get_walls_by_layer(self):
        return dict(self._w)

    def get_layers_secao_de_parede(self):
        return set()

    def get_areas_by_layer(self):
        return {}

    def get_polygon_areas_by_layer(self):
        return {}


def _roda(marcador, escopo):
    import _executa
    import main
    esc = dict(vars(main))
    esc.update(escopo)
    return _executa.roda("process_job", marcador, esc, tamanho=1)


_MD = {"parede_espessa_pelas_faces": {"A-WALL": {"sobra_m": 77.2, "fracao": 0.22}}}


def test_a_chave_do_selo_nao_indexa_o_layer_que_saiu_da_zona_cinza_pelo_eixo():
    """O E12: zona cinza vazia (o eixo rodou) — a marca nova é quem segura."""
    ex = _Extr(dict(_MD), {"A-WALL": 347.9, "PAREDE-INT": 30.0})
    esc = _roda("_nao_prova_ig = _layers_que_nao_provam(extraction.metadata)",
                {"extraction": ex, "_indice_geom": {"comprimento": [], "area": [], "contagem": []}})
    assert dict(esc["_indice_geom"]["comprimento"]) == {"PAREDE-INT": 30.0}
    obs = "Fonte: comprimento do layer A-WALL = 347,90 m (pelo eixo)"
    assert er.prova_da_geometria(347.9, "m", obs, esc["_indice_geom"]) == ""


def test_o_resgate_automatico_nao_preenche_com_o_layer():
    ex = _Extr(dict(_MD), {"A-WALL": 347.9, "PAREDE-INT": 30.0})
    esc = _roda("_nao_prova_rs = _layers_que_nao_provam(extraction.metadata)", {"extraction": ex})
    assert set(esc["_compr_ly"]) == {"PAREDE-INT"}, esc["_compr_ly"]


def test_o_laco_le_os_layers_marcados_da_extracao():
    ex = _Extr(dict(_MD), {})
    esc = _roda("_esp_ly = {str(_k).strip().upper() for _k in", {"extraction": ex})
    assert esc["_esp_ly"] == {"A-WALL"}


def _cats_do_cross_check():
    """As categorias do cross-check, recortadas do próprio `process_job`."""
    import _executa
    esc = {}
    _executa.roda("process_job", "_AREA_CATS = {", esc)
    _executa.roda("process_job", "_LEN_CATS = {", esc)
    return {"_AREA_CATS": esc["_AREA_CATS"], "_LEN_CATS": esc["_LEN_CATS"]}


def _item_parede(conf):
    return {"item_num": "1", "description": "Parede de alvenaria/concreto",
            "unit": "ml", "quantity": 347.9, "confidence": conf,
            "observations": "Fonte: comprimento do layer 'A-WALL' = 347.90 m."}


def test_CONTROLE_com_o_cross_check_ligado_a_parede_que_bate_vira_medida(monkeypatch):
    """A armadilha existe: com DXF_CONFIRM_CROSSCHECK=1 (desligado hoje), a linha
    de parede cujo número bate com a geometria é promovida."""
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    monkeypatch.setenv("DXF_CONFIRM_CROSSCHECK", "1")
    itens, _e, _ = _laco_de_itens_de_producao(
        [_item_parede("estimado")], areas={}, compr={"A-WALL": 347.9},
        extra={"_esp_ly": set(), "_hard_len_by_cat": {"paredes": {347.9}}, **_cats_do_cross_check()})
    assert itens[0].confidence.value == "confirmado", itens[0].observations


def test_com_o_cross_check_ligado_a_linha_rebaixada_nao_volta(monkeypatch):
    """A trava marca `_rebaixado_pela_fonte`: o cross-check não desfaz o rebaixamento."""
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    monkeypatch.setenv("DXF_CONFIRM_CROSSCHECK", "1")
    itens, _e, _ = _laco_de_itens_de_producao(
        [_item_parede("confirmado")], areas={}, compr={"A-WALL": 347.9},
        extra={"_esp_ly": {"A-WALL"}, "_hard_len_by_cat": {"paredes": {347.9}}, **_cats_do_cross_check()})
    assert itens[0].confidence.value == "estimado", itens[0].observations


# ══════════════════════════════════════════════════════════════════════════
#  5. O cross-check (DXF_CONFIRM_CROSSCHECK) respeita a marca nova
# ══════════════════════════════════════════════════════════════════════════
_MD_ESP = {"parede_espessa_pelas_faces": {"A-WALL": {"sobra_m": 104.3, "fracao": 0.30}}}


def _paredes_do_caso():
    from test_crosscheck_respeita_as_marcas import _W
    return (_W("A-WALL", 347.9), _W("PAREDE-INT", 30.0))


def test_o_layer_da_marca_nova_nao_vira_medida_dura():
    from test_crosscheck_respeita_as_marcas import _medidas_duras
    comp, _ = _medidas_duras(_MD_ESP, walls=_paredes_do_caso())
    assert comp.get("paredes") == {30.0}, comp


def test_CONTROLE_sem_a_marca_o_layer_vira_medida_dura():
    from test_crosscheck_respeita_as_marcas import _medidas_duras
    comp, _ = _medidas_duras({}, walls=_paredes_do_caso())
    assert comp.get("paredes") == {347.9, 30.0}, comp


def _laco_com_o_cross_check(md):
    """Medidas duras montadas pelos statements reais com `md`; o laço de produção
    com o cross-check LIGADO e uma linha "estimado" com o número do layer."""
    from test_crosscheck_respeita_as_marcas import _Ext, _medidas_duras
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    comp, area = _medidas_duras(md, walls=_paredes_do_caso())
    itens, _e, _ = _laco_de_itens_de_producao(
        [_item_parede("estimado")], areas={}, compr={"A-WALL": 347.9},
        extra={**_cats_do_cross_check(), "_hard_len_by_cat": comp, "_hard_area_by_cat": area,
               "extraction": _Ext(md)})
    return itens[0]


def test_com_o_cross_check_ligado_o_estimado_do_layer_marcado_nao_promove(monkeypatch):
    monkeypatch.setenv("DXF_CONFIRM_CROSSCHECK", "1")
    it = _laco_com_o_cross_check(_MD_ESP)
    assert it.confidence.value == "estimado", it.observations


def test_CONTROLE_com_o_cross_check_ligado_sem_a_marca_promove(monkeypatch):
    monkeypatch.setenv("DXF_CONFIRM_CROSSCHECK", "1")
    it = _laco_com_o_cross_check({})
    assert it.confidence.value == "confirmado", it.observations
