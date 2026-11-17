# -*- coding: utf-8 -*-
"""AREA_DA_ETIQUETA_NO_TEXTO: piso/forro com a area do ambiente escrita na planta.

🩸 17/11/2026 — medido no banco (90 dias, PDF): 112 linhas de piso em 36 projetos
sairam em branco com a observacao dizendo que LEU a area do ambiente na planta
("Area lida diretamente da planta: 'WC 02 A=3,77m2'"). O ramo da medicao
vetorial so segura o numero quando a prancha foi medida; sem medicao, zera.

O que este arquivo sustenta:
  - a linha so passa quando CITA a propria quantidade como area de UM ambiente
    E o numero esta no texto do PDF da prancha dela;
  - com a chave em 0 nada muda de numero, so a lista anota (o alcance);
  - conta, estimativa e area de resumo seguem em branco.

Tudo sintetico. Roda a `_apply_area_honesty` REAL pela fatia de
`test_area_medida_do_pdf_nao_e_apagada`.
"""
import io
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _AQUI)
sys.path.insert(0, os.path.dirname(_AQUI))

import engine_rules as er  # noqa: E402
import test_area_medida_do_pdf_nao_e_apagada as _base  # noqa: E402

_CHAVE = "AREA_DA_ETIQUETA_NO_TEXTO"
_ARQ = "planta generica.pdf"
_WC = "Piso porcelanato — WC 02 (A=3,77m²) — tipo e fabricante a definir"
_OBS_WC = "Área lida diretamente da planta: 'WC 02 A=3,77m²'."


@pytest.mark.parametrize("desc,obs,q", [
    (_WC, _OBS_WC, 3.77),
    ("Piso cerâmico ou porcelanato — Cozinha", "Área confirmada no quadro de ambientes: A: 9,26 m².", 9.26),
    ("Piso — Banheiro Feminino — revestimento cerâmico", "Área indicada na planta: 10,53 m².", 10.53),
    ("Piso cerâmico — Sala Estar/Jantar", "Legenda: 'SALA ESTAR/JANTAR A=11,27m²'.", 11.27),
    ("Forro de gesso liso — banheiro", "'BANHO A=3,48m²'", 3.48),
    ("Contrapiso em argamassa — Suíte", "SUÍTE A=14,20 m²", 14.2),
    # medida da peca na descricao nao e conta
    ("Porcelanato 90×90 cm — piso do WC", "WC A=3,77 m²", 3.77),
    ("Piso de garagem em concreto", "GARAGEM A=1.284,52 m²", 1284.52),
])
def test_a_linha_cita_a_area_de_um_ambiente(desc, obs, q):
    assert er.area_da_etiqueta_na_linha(desc, obs, q)


@pytest.mark.parametrize("desc,obs,q", [
    # resultado de conta
    ("Piso de WC — banheiros", "Área lida: 'WC A=3,76 m²'. Calculado: 3,76 m² × 4 unidades = 15,04 m².", 15.04),
    ("Piso laminado — dormitórios", "Sala (11,27 m²) + Dormitório 1 (8,40 m²) = 19,67 m²", 19.67),
    # fator ou parcela de conta
    ("Piso cerâmico em banheiros", "4 banheiros × 3,20 m² cada", 3.2),
    ("Piso laminado", "Sala 11,27 m² + Dormitório 8,40 m²", 11.27),
    # estimativa
    ("Piso cerâmico — Banheiro", "Estimativa: ≈ 4,00 m² de piso.", 4.0),
    ("Piso cerâmico — Banheiro", "Área aprox. de 4,00 m².", 4.0),
    # resumo
    ("Piso cerâmico em toda a casa", "Área total construída: 208,00 m².", 208.0),
    ("Contrapiso do pavimento", "Pavimento térreo A=103,25 m²", 103.25),
    ("Piso externo", "Área do terreno = 360,00 m²", 360.0),
    # o numero da linha nao e o citado
    (_WC, _OBS_WC, 7.0),
    # nao e superficie horizontal, ou outra palavra barra
    ("Revestimento de parede do banheiro até o forro", "BWC A=3,37m²", 3.37),
    ("Rodapé do piso do WC", "WC A=3,37m²", 3.37),
    ("Pintura acrílica — Sala", "SALA A=11,27 m²", 11.27),
    ("Bancada do banheiro em granito", "BWC A=3,37m²", 3.37),
    # menor que 1 m2, zero, ilegivel
    ("Piso do shaft", "SHAFT A=0,60 m²", 0.6),
    (_WC, _OBS_WC, 0),
    (_WC, _OBS_WC, "x"),
])
def test_CONTROLE_o_que_nao_e_area_de_um_ambiente(desc, obs, q):
    assert not er.area_da_etiqueta_na_linha(desc, obs, q)


def _item(desc, q, obs, ref=_ARQ):
    it = _base._Item(desc, "m²", q, obs)
    it.ref_sheet = ref
    return it


def _roda(monkeypatch, ligada, itens, numeros=(377,), pdfvec_m2=0.0):
    if ligada:
        monkeypatch.setenv(_CHAVE, "1")
    else:
        monkeypatch.delenv(_CHAVE, raising=False)
    monkeypatch.delenv("PISO_DE_COMODO_DA_ETIQUETA", raising=False)
    h = _base._fatia()["_apply_area_honesty"]
    h(itens, total_area=0, total_area_source="", pe_direito=0, pdfvec_m2=pdfvec_m2,
      numeros_do_texto_por_prancha={(_ARQ, 0): frozenset(numeros)})
    return h


def test_DESLIGADA_zera_como_antes_e_a_lista_anota(monkeypatch):
    wc = _item(_WC, 3.77, _OBS_WC)
    h = _roda(monkeypatch, False, [wc])
    assert _base._valor(wc) == 0, "a chave em 0 mudou número"
    assert "Área NÃO medida" in wc.observations
    assert h.ultimo_area_da_etiqueta == ([(3.77, _WC[:60])], False, 0)


def test_LIGADA_a_linha_fica_estimada_com_a_frase(monkeypatch):
    wc = _item(_WC, 3.77, _OBS_WC)
    h = _roda(monkeypatch, True, [wc])
    assert _base._valor(wc) == 3.77
    assert str(getattr(wc.confidence, "value", wc.confidence)) == "estimado"
    assert wc.observations.startswith(er.MARCA_AREA_DA_ETIQUETA)
    assert "não medimos o desenho" in wc.observations
    assert "Área NÃO medida" not in wc.observations
    assert h.ultimo_area_da_etiqueta == ([(3.77, _WC[:60])], True, 1)


def test_LIGADA_numero_que_o_texto_do_pdf_nao_tem_zera(monkeypatch):
    wc = _item(_WC, 3.77, _OBS_WC)
    h = _roda(monkeypatch, True, [wc], numeros=(1420, 2140))
    assert _base._valor(wc) == 0
    assert h.ultimo_area_da_etiqueta == ([], True, 0)


def test_LIGADA_sem_texto_nenhum_da_prancha_zera(monkeypatch):
    wc = _item(_WC, 3.77, _OBS_WC, ref="outra prancha.pdf")
    h = _roda(monkeypatch, True, [wc])
    assert _base._valor(wc) == 0
    assert h.ultimo_area_da_etiqueta == ([], True, 0)


def test_LIGADA_a_mesma_area_duas_vezes_na_mesma_familia_fica_uma_so(monkeypatch):
    a = _item(_WC, 3.77, _OBS_WC)
    b = _item("Piso/revestimento — WC 02 A=3,77m²; material a definir", 3.77, _OBS_WC)
    forro = _item("Forro de gesso — WC 02", 3.77, "Etiqueta da planta: 'WC 02 A=3,77m²'.")
    h = _roda(monkeypatch, True, [a, b, forro])
    assert (_base._valor(a), _base._valor(b), _base._valor(forro)) == (3.77, 0, 3.77)
    assert h.ultimo_area_da_etiqueta[2] == 2


def test_LIGADA_resultado_de_conta_segue_em_branco(monkeypatch):
    conta = _item("Piso de WC — banheiros",
                  15.04, "Área lida: 'WC A=3,76 m²'. Calculado: 3,76 m² × 4 unidades = 15,04 m².")
    h = _roda(monkeypatch, True, [conta], numeros=(376, 1504))
    assert _base._valor(conta) == 0
    assert h.ultimo_area_da_etiqueta == ([], True, 0)


def test_o_alcance_nao_conta_a_linha_que_outro_ramo_ja_segurava(monkeypatch):
    """Com a prancha medida, a suíte fica pelo ramo de sempre ('cabe na
    geometria'): não entra na lista desta chave, ligada ou não."""
    suite = _item("Piso em porcelanato — Suíte (A=14,20 m²)", 14.2,
                  "Área extraída da etiqueta: 'SUÍTE A=14,20m²'.")
    for ligada in (False, True):
        suite.quantity = 14.2
        h = _roda(monkeypatch, ligada, [suite], numeros=(1420,), pdfvec_m2=90.0)
        assert _base._valor(suite) == 14.2
        assert h.ultimo_area_da_etiqueta == ([], ligada, 0)


def test_a_chave_e_avaliavel_e_a_etapa_e_diagnostico():
    src = io.open(os.path.join(_base._BACKEND, "main.py"), encoding="utf-8").read()
    assert '_chave_do_job(job_id, "%s")' % _CHAVE in src
    assert '"%s"' % _CHAVE in src[src.index("_CHAVES_AVALIAVEIS = frozenset"):][:6000]
    _lista = src[:src.index('"motor:passo7-ambiguo"')].replace("\r\n", "\n")
    assert '    "motor:area-da-etiqueta-no-texto",\n' in _lista
    assert '_log_error("motor:area-da-etiqueta-no-texto"' in src


# ── a grade só no layout novo ─────────────────────────────────────────────
def test_grade_so_no_layout_novo(monkeypatch):
    import main
    from models import SheetType
    assert "PLANTA_EM_GRADE_NO_LAYOUT_NOVO" in main._CHAVES_AVALIAVEIS
    monkeypatch.delenv("PLANTA_EM_GRADE", raising=False)
    monkeypatch.delenv("PLANTA_EM_GRADE_NO_LAYOUT_NOVO", raising=False)
    todos = list(SheetType)
    assert not any(main._liga_planta_em_grade("job-x", t) for t in todos), "nasce desligada"
    monkeypatch.setenv("PLANTA_EM_GRADE_NO_LAYOUT_NOVO", "1")
    assert [t for t in todos if main._liga_planta_em_grade("job-x", t)] == [SheetType.LAYOUT_NOVO]
    assert not main._liga_planta_em_grade("job-x", None)
    # a chave geral continua valendo pra toda prancha
    monkeypatch.setenv("PLANTA_EM_GRADE", "1")
    monkeypatch.delenv("PLANTA_EM_GRADE_NO_LAYOUT_NOVO", raising=False)
    assert all(main._liga_planta_em_grade("job-x", t) for t in todos)


def test_o_laco_de_pdf_pergunta_pelo_tipo_da_prancha():
    src = io.open(os.path.join(_base._BACKEND, "main.py"), encoding="utf-8").read()
    assert "if _liga_planta_em_grade(job_id, sheet_type):" in src
    assert src.count('_chave_do_job(job_id, "PLANTA_EM_GRADE")') == 1, (
        "a chave geral só é lida dentro de `_liga_planta_em_grade`")
