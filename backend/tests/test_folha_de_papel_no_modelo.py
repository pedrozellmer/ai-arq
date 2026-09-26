# -*- coding: utf-8 -*-
"""Folha de papel desenhada no MODELO, cada vista numa escala: não é medição.

🩸 26/09/2026 — job 32a27efc (7 DXF de estrutura de muro de arrimo). Cada
prancha era a FOLHA A1 inteira desenhada no modelo em milímetros de papel
($INSUNITS=4, extensão 841×594, nenhuma janela de layout), com a fôrma em
1:125, as seções em 1:25 e os cortes em 1:100. O DIMLFAC de cada cota é a
escala da vista em cm por mm de papel (12,5 → 1:125). O motor usa UM fator por
arquivo: a prancha 0001 saiu 125× menor e SEM ressalva; as outras seis, com o
decímetro que a plausibilidade escolheu — certo numa vista, errado nas outras.

Regras que os guardas prendem:
- A0–A4 no modelo, $INSUNITS 0/4, nenhuma janela, ≥3 cotas e ≥80% delas com
  razão ≠ 1 → a prancha é marcada (`escala_por_vista`);
- a marca é ressalva de ESCALA: m/m²/m³ não saem medidos; kg e un continuam;
- o cliente lê QUAL prancha, as escalas das cotas e o que falta;
- o log `motor:unidade` leva o histograma do DIMLFAC (pra medir o alcance).
Os arquivos do cliente NÃO entram aqui: cada DXF é montado em memória.
"""
import io
import os
import sys
import textwrap

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

import dwg_extractor as dx  # noqa: E402
from engine_rules import (REGUAS_QUE_PROVAM, caveat_atinge_unidade,  # noqa: E402
                          extraction_has_quality_caveat)

_A1 = (841.0, 594.0)


def _folha(insunits=4, tamanho=_A1, cotas=((12.5, 6),), janela=False,
           cabecalho=True, digitadas=0):
    """Folha desenhada no modelo: moldura do tamanho do papel + cotas.

    `cotas`: [(DIMLFAC do estilo, quantas cotas automáticas)].
    `digitadas`: cotas com o número ESCRITO ("19" sobre 9,5 mm — 1:20), num
    estilo de DIMLFAC 1.
    """
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = insunits
    w, h = tamanho
    if cabecalho:
        doc.header["$EXTMIN"] = (0, 0, 0)
        doc.header["$EXTMAX"] = (w, h, 0)
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (w, 0), (w, h), (0, h)], close=True)
    y = 20.0
    for lf, n in cotas:
        nome = "E%g" % lf
        if nome not in doc.dimstyles:
            doc.dimstyles.new(nome, dxfattribs={"dimlfac": lf})
        for k in range(n):
            x0 = 20.0 + 30.0 * k
            msp.add_linear_dim(base=(x0, y + 8), p1=(x0, y), p2=(x0 + 24, y),
                               dimstyle=nome).render()
        y += 20.0
    if digitadas:
        if "E1" not in doc.dimstyles:
            doc.dimstyles.new("E1", dxfattribs={"dimlfac": 1.0})
        for k in range(digitadas):
            x0 = 20.0 + 30.0 * k
            msp.add_linear_dim(base=(x0, y + 8), p1=(x0, y), p2=(x0 + 9.5, y),
                               dimstyle="E1", text="19").render()
    if janela:
        lay = doc.layouts.new("FOLHA 01")
        vp = lay.add_viewport(center=(400, 300), size=(700, 500),
                              view_center_point=(420, 297), view_height=594)
        vp.dxf.view_target_point = (0, 0, 0)
    return doc


# ── o detector ──────────────────────────────────────────────────────────────
def test_folha_A1_no_modelo_com_cotas_em_1_125_E_marcada():
    """🩸 A forma do caso: A1, milímetro, sem janela, DIMLFAC 12,5."""
    r = dx.folha_de_papel_no_modelo(_folha())
    assert r, "a folha de papel no modelo passou sem marca — é o caso 32a27efc"
    assert r["folha"] == "A1", r
    assert r["escalas"] == [(125.0, 6)], r
    assert r["texto"] == "1:125 (6 cotas)", r


def test_duas_vistas_saem_as_duas_escalas_da_mais_comum_pra_menos():
    """A cota solta de outro estilo (a 0001 tinha uma em 1:50) não vira vista."""
    r = dx.folha_de_papel_no_modelo(_folha(cotas=((2.5, 4), (12.5, 7), (5.0, 1))))
    assert r, "não marcou a folha com duas vistas"
    assert r["texto"] == "1:125 (7 cotas), 1:25 (4 cotas)", r["texto"]


def test_escala_quebrada_sai_com_virgula():
    r = dx.folha_de_papel_no_modelo(_folha(cotas=((3.333, 5),)))
    assert r and r["texto"] == "1:33,3 (5 cotas)", r


@pytest.mark.parametrize("insunits,tamanho", [(0, _A1), (4, (297.0, 420.0)),
                                              (4, (1189.0, 841.0))],
                         ids=["sem_unidade", "A3_em_pe", "A0"])
def test_outras_folhas_e_sem_unidade_tambem_marcam(insunits, tamanho):
    assert dx.folha_de_papel_no_modelo(_folha(insunits=insunits, tamanho=tamanho))


@pytest.mark.parametrize("emin,emax", [
    (None, None),                                   # o que o ezdxf grava: +1e20 / −1e20
    ((-1e20, -1e20, -1e20), (1e20, 1e20, 1e20)),    # o do acervo: extensão 2e20
    ((0, 0, 0), (0, 0, 0)),                         # vazio
], ids=["ezdxf_1e20", "acervo_2e20", "zeros"])
def test_cabecalho_invalido_mede_a_extensao_pelas_entidades(emin, emax):
    doc = _folha(cabecalho=False)
    if emin is not None:
        doc.header["$EXTMIN"], doc.header["$EXTMAX"] = emin, emax
    r = dx.folha_de_papel_no_modelo(doc)
    assert r and r["folha"] == "A1", r


def test_cota_DIGITADA_fora_da_medida_tambem_conta():
    """Número escrito "19" sobre 9,5 mm de papel (1:20), estilo com DIMLFAC 1:
    a razão vem do texto. Sem escala no estilo, o texto não inventa uma."""
    r = dx.folha_de_papel_no_modelo(_folha(cotas=(), digitadas=5))
    assert r, "a cota digitada em escala de papel não foi contada"
    assert r["escalas"] == [], r
    assert r["texto"] == "5 de 5 cotas exibem outro número que a medida do desenho", r


def test_80_por_cento_das_cotas_fora_de_1_marca():
    assert dx.folha_de_papel_no_modelo(_folha(cotas=((12.5, 8), (1.0, 2))))


def test_cota_de_comprimento_zero_e_texto_suprimido_nao_derrubam_nem_contam():
    doc = _folha()
    msp = doc.modelspace()
    msp.add_linear_dim(base=(600, 50), p1=(600, 40), p2=(600, 40), dimstyle="E12.5").render()
    msp.add_linear_dim(base=(600, 90), p1=(600, 80), p2=(624, 80), dimstyle="E12.5",
                       text=" ").render()
    msp.add_linear_dim(base=(650, 50), p1=(650, 40), p2=(650, 40), dimstyle="E12.5",
                       text="19").render()
    r = dx.folha_de_papel_no_modelo(doc)
    assert r, "uma cota degenerada derrubou a marca da folha inteira"
    assert r["cotas"] == 6, r
    assert r["texto"] == "1:125 (7 cotas)", r      # suprimida tem estilo; zero não
    assert dx.histograma_dimlfac(doc) == {12.5: 7}


def test_o_teto_de_varredura_das_cotas_vale(monkeypatch):
    monkeypatch.setattr(dx, "_DIM_MAX_SCAN", 2)
    doc = _folha()
    assert dx.histograma_dimlfac(doc) == {12.5: 2}
    assert dx.folha_de_papel_no_modelo(doc) is None, "o detector passou do teto"


# ── controles: o que NÃO pode ser marcado ───────────────────────────────────
def test_CONTROLE_desenho_em_metro_nao_e_folha_de_papel():
    assert dx.folha_de_papel_no_modelo(_folha(insunits=6)) is None


def test_CONTROLE_folha_montada_no_layout_nao_e_marcada():
    """Com janela de viewport a folha está no layout — o modelo é 1:1."""
    assert dx.folha_de_papel_no_modelo(_folha(janela=True)) is None


def test_CONTROLE_cotas_com_DIMLFAC_1_nao_marcam():
    """Detalhe 1:1 em milímetro do tamanho de uma folha: a cota mostra a
    própria medida."""
    assert dx.folha_de_papel_no_modelo(_folha(cotas=((1.0, 6),))) is None


@pytest.mark.parametrize("tamanho", [(20000.0, 12000.0), (841.0, 300.0)],
                         ids=["planta_1_1", "lado_de_A1_so_de_um_jeito"])
def test_CONTROLE_extensao_que_nao_e_folha(tamanho):
    assert dx.folha_de_papel_no_modelo(_folha(tamanho=tamanho)) is None


def test_CONTROLE_cabecalho_1e20_e_entidades_que_nao_sao_folha():
    assert dx.folha_de_papel_no_modelo(
        _folha(tamanho=(20000.0, 12000.0), cabecalho=False)) is None


def test_CONTROLE_cabecalho_manda_quando_e_valido():
    """Cabeçalho válido que não é folha: não vai atrás das entidades."""
    doc = _folha()
    doc.header["$EXTMAX"] = (20000.0, 12000.0, 0)
    assert dx.folha_de_papel_no_modelo(doc) is None


def test_CONTROLE_cota_de_raio_nao_e_regua_linear():
    doc = _folha(cotas=((12.5, 2),))
    for k in range(4):
        doc.modelspace().add_radius_dim(center=(100 + 40 * k, 300), radius=10, angle=45,
                                        dimstyle="E12.5").render()
    assert dx.folha_de_papel_no_modelo(doc) is None


def test_CONTROLE_menos_de_3_cotas():
    assert dx.folha_de_papel_no_modelo(_folha(cotas=((12.5, 2),))) is None


def test_CONTROLE_70_por_cento_fora_de_1_nao_marca():
    assert dx.folha_de_papel_no_modelo(_folha(cotas=((12.5, 7), (1.0, 3)))) is None


# ── a ressalva é de ESCALA ──────────────────────────────────────────────────
_MD = {"escala_por_vista": "1:125 (54 cotas), 1:25 (48 cotas)"}


@pytest.mark.parametrize("unidade", ["m", "m²", "m³"])
def test_a_marca_nao_deixa_medida_sair_confirmada(unidade):
    assert caveat_atinge_unidade(_MD, unidade) is True
    assert extraction_has_quality_caveat(_MD) is True


@pytest.mark.parametrize("unidade", ["kg", "un"])
def test_contagem_e_kg_nao_dependem_da_escala(unidade):
    assert caveat_atinge_unidade(_MD, unidade) is False


def test_a_marca_nao_e_regua_que_prova():
    assert "escala_por_vista" not in REGUAS_QUE_PROVAM


# ── de ponta a ponta: extract_dxf ───────────────────────────────────────────
def _extrair(doc, tmp_path):
    p = str(tmp_path / "folha.dxf")
    doc.saveas(p)
    return dx.extract_dxf(p).metadata


def test_ponta_a_ponta_a_linha_em_m_nao_sai_medida_e_a_de_kg_sai(tmp_path):
    md = _extrair(_folha(cotas=((12.5, 6), (2.5, 4))), tmp_path)
    assert md.get("escala_por_vista") == "1:125 (6 cotas), 1:25 (4 cotas)", md
    for u in ("m", "m²", "m³"):
        assert caveat_atinge_unidade(md, u), (
            "linha em %s de uma folha de papel no modelo pode sair ✓ MEDIDO" % u)
    for u in ("kg", "un"):
        assert not caveat_atinge_unidade(md, u), (
            "a ressalva de escala rebaixou %s, que não depende de escala" % u)
    assert md.get("lfac_por_cota") == "{12.5:6,2.5:4}", md.get("lfac_por_cota")


def test_CONTROLE_ponta_a_ponta_folha_no_layout_segue_medindo(tmp_path):
    md = _extrair(_folha(janela=True), tmp_path)
    assert "escala_por_vista" not in md, md
    assert not caveat_atinge_unidade(md, "m"), (
        "a folha montada no layout ganhou ressalva: %r" % md)


def test_CONTROLE_ponta_a_ponta_sem_cota_nao_ha_histograma(tmp_path):
    md = _extrair(_folha(cotas=()), tmp_path)
    assert "escala_por_vista" not in md and "lfac_por_cota" not in md, md


# ── o cliente lê ─────────────────────────────────────────────────────────────
_INI = "import re as _re_escala"
_FIM = "\ndef _regua_da_sombra("


def _fns():
    """Executa o TRECHO REAL do main.py (as duas funções do aviso de escala)."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    assert src.count(_INI) == 1, "a âncora de início mudou"
    i = src.index(_INI)
    trecho = textwrap.dedent(src[i:src.index(_FIM, i)])
    ns = {"__name__": "escala_ns", "os": os}
    exec(compile(trecho, "main_escala_slice", "exec"), ns)
    return ns["_resumo_escala_arquivo"], ns["_linhas_escala_projeto"]


_PLAUS = ("unidade corrigida por PLAUSIBILIDADE: com milímetros o desenho inteiro "
          "mediria 0.29×0.19 m (impossível); em decímetros mede 29.5×18.9 m.")


def test_o_cliente_le_qual_prancha_as_escalas_e_o_que_falta():
    resumo, linhas = _fns()
    a = resumo("/tmp/EST-MUR-0001-R01.dxf", dict(_MD, alerta_unidade=_PLAUS))
    assert a["status"] == "folha", a
    out = linhas([a], n_medidos=5)
    assert len(out) == 1, out
    txt = out[0]
    for pedaco in ("EST-MUR-0001-R01", "ESCALA DE PAPEL",
                   "1:125 (54 cotas), 1:25 (48 cotas)",
                   "comprimento, área e volume destas pranchas NÃO foram medidos",
                   "(un)", "(kg)", "1:1"):
        assert pedaco in txt, "faltou %r no aviso:\n%s" % (pedaco, txt)
    assert "ESCALA SUSPEITA" not in txt and "✅" not in txt, txt


def test_a_folha_vence_a_cota_validada():
    """Cota que bate numa vista não prova as outras: nada de ✅ nessa prancha."""
    resumo, linhas = _fns()
    a = resumo("/tmp/P.dxf", dict(_MD, unidade_validada_por_cotas=54,
                                  unidade_nome_provada="decímetros"))
    assert a["status"] == "folha", a
    assert "Escala conferida" not in " ".join(linhas([a], n_medidos=5))


def test_a_folha_vem_antes_das_outras_linhas_e_lista_ate_4():
    resumo, linhas = _fns()
    folhas = [resumo("/tmp/F%d.dxf" % k, _MD) for k in range(6)]
    sem = {"nome": "OUTRA", "status": "sem_prova", "declarada": "Milímetros"}
    ruim = {"nome": "RUIM", "status": "alerta", "declarada": "Polegadas"}
    out = linhas([sem, ruim] + folhas, n_medidos=0)
    assert len(out) == 3, out
    assert "ESCALA DE PAPEL" in out[0], out[0]
    assert "F3 —" in out[0] and "F4 —" not in out[0], out[0]
    assert "e mais 2" in out[0], out[0]


def test_CONTROLE_sem_a_marca_nao_ha_aviso_de_folha():
    resumo, linhas = _fns()
    a = resumo("/tmp/X.dxf", {"alerta_unidade": _PLAUS})
    assert a["status"] == "alerta", a
    assert "ESCALA DE PAPEL" not in " ".join(linhas([a], n_medidos=0))


# ── o log ────────────────────────────────────────────────────────────────────
def test_o_log_motor_unidade_leva_o_histograma_do_DIMLFAC():
    """📏 Sem o número no banco não dá pra medir quantas pranchas são folha.
    🪤 Guarda que lê o fonte: só confere que a linha do log LÊ a chave; o
    conteúdo da chave é conferido de ponta a ponta acima."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index('"motor:unidade",\n')
    linha = src[i:src.index("job_id)", i)]
    assert "lfac={_md_u.get('lfac_por_cota')" in linha, linha[-300:]


def test_lfac_para_log_do_mais_comum_pro_menos_e_curto():
    assert dx.lfac_para_log({2.5: 48, 12.5: 54, 5.0: 1}) == "{12.5:54,2.5:48,5:1}"
    muitos = {float(k): 20 - k for k in range(1, 11)}
    assert dx.lfac_para_log(muitos) == "{1:19,2:18,3:17,4:16,5:15,6:14,7:13,8:12}"
