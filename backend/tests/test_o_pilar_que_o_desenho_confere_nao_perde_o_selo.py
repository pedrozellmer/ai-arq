# -*- coding: utf-8 -*-
"""A linha de pilar ✓ cujo NÚMERO a contagem geométrica confere não perde o selo
pela ordem das palavras.

🩸 19/10/2026: numa locação de pilares, as 6 linhas de pilar saíram ⚠ ESTIMADO com
a quantidade certa. A IA escreveu "Fonte: MEDIÇÃO DETERMINÍSTICA — layer 'X': 8
retângulos de 25×25 cm. Textos layer […]: '25/25 ×8'", forma que a régua de prova
não reconhece; o "Textos" pôs a linha na rede que rebaixa. Outra rodada, no mesmo
arquivo, escreveu "contados geometricamente" e ficou com o selo.

🔑 Quem prova é o número: "N retângulos/círculos de S cm" com N = a quantidade da
linha = a contagem geométrica da mesma seção no arquivo dela. Aí a observação
ganha na frente a frase que a régua de sempre reconhece. Nunca promove.

Textos e nomes sintéticos (o repositório é público).
"""
import os
import sys
import types

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

import engine_rules as er  # noqa: E402

FOLHA = "locacao-de-pilares.dxf"
CONTAGEM = {FOLHA: {"30x90 cm": 43, "25x25 cm": 8, "Ø25 cm": 7, "25x60 cm": 4}}


def _linha(descr="Pilar de concreto armado — seção 25 × 25 cm", q=8,
           obs="Fonte: MEDIÇÃO DETERMINÍSTICA — layer 'S-COLS-____-OTLN': 8 retângulos de "
               "25×25 cm. Textos layer [S-COLS-____-IDEN]: '25/25 ×8'.",
           conf="confirmado", origem="dxf_geom", unit="un", folha=FOLHA):
    return {"description": descr, "quantity": q, "observations": obs, "confidence": conf,
            "origem": origem, "unit": unit, "ref_sheet": folha}


def _conferidos(itens, mapa=CONTAGEM):
    return [a["indice"] for a in er.pilares_conferidos_pela_geometria(itens, mapa)]


# ── o caso de 19/10 ──────────────────────────────────────────────────────────
def test_CONTROLE_hoje_a_rede_rebaixa_a_linha_certa():
    """Sem a conferência, a linha de pilar com o número certo cai em
    `selos_sem_geometria` — é o defeito."""
    assert [a["indice"] for a in er.selos_sem_geometria([_linha()])] == [0]


def test_a_frase_conferida_tira_a_linha_da_rede():
    it = _linha()
    (a,) = er.pilares_conferidos_pela_geometria([it], CONTAGEM)
    assert a["frase"] == er.MARCA_PILAR_CONFERIDO + ": 8 pilar(es) de 25x25 cm."
    it["observations"] = a["frase"] + " " + it["observations"]
    assert er.selos_sem_geometria([it]) == [], "a régua de sempre não reconheceu a frase"
    assert er._tem_prova_de_geometria(it["observations"]), "uma balança só: o retrato também vê"


@pytest.mark.parametrize("descr, obs, q", [
    ("Pilar circular — seção Ø25 cm", "Fonte: MEDIÇÃO DETERMINÍSTICA — layer 'P': 7 círculos de Ø25 cm.", 7),
    ("Pilar — seção 30×90", "Fonte: medição determinística — 43 retângulos de seção 90 x 30 cm. Texto '30/90'.", 43),
    ("Pilar 25x60", "Fonte: 4 retângulos de 60×25 cm no layer de pilar; legenda confirma.", 4),
])
def test_as_formas_que_o_numero_confere(descr, obs, q):
    assert _conferidos([_linha(descr=descr, obs=obs, q=q)]) == [0]


def test_a_mesma_contagem_citada_duas_vezes_vale():
    """Do caso real: "1 retângulo de 19×40 cm … A geometria registrou apenas 1
    retângulo de 19×40cm" — a mesma contagem, dita duas vezes."""
    obs = ("Fonte: MEDIÇÃO DETERMINÍSTICA — layer 'P': 1 retângulo de 19×40 cm. Textos: '19/239 ×4' — "
           "seções 19×239 e 19×144 podem ser outros pilares. A geometria registrou apenas 1 retângulo de 19×40cm.")
    assert _conferidos([_linha(descr="Pilar 19 × 40", obs=obs, q=1)],
                       {FOLHA: {"19x40 cm": 1}}) == [0]


# ── o lado que não pode mudar ────────────────────────────────────────────────
@pytest.mark.parametrize("mudar, por_que", [
    ({"q": 9}, "a quantidade da linha não é a contada"),
    ({"obs": "Fonte: 9 retângulos de 25×25 cm. Texto '25/25 ×9'.", "q": 9}, "o desenho contou 8, não 9"),
    ({"obs": "Fonte: 8 retângulos de 20×20 cm. Texto.", "q": 8}, "seção que o desenho não contou"),
    ({"obs": "Fonte: 7 retângulos de 25×25 cm. Texto 'Ø25 ×7'.", "q": 7}, "7 é dos círculos, não dos retângulos"),
    ({"obs": "Fonte: 7 círculos de 25×25 cm. Texto.", "q": 7}, "círculo com seção de retângulo"),
    ({"descr": "Estaca hélice contínua Ø25 cm", "obs": "Fonte: 7 círculos de Ø25 cm. Texto.", "q": 7},
     "estaca não é pilar, mesmo com a seção do pilar"),
    ({"conf": "estimado"}, "nunca promove: só a ✓ que a rede ia rebaixar"),
    ({"origem": "vision_pdf"}, "PDF não mede geometria"),
    ({"unit": "m³"}, "volume não é contagem"),
    ({"obs": "Fonte: 8 retângulos de 25×25 cm e 4 retângulos de 25×60 cm. Texto."}, "duas seções citadas"),
    ({"obs": "Fonte: texto '25/25 ×8' no layer de identificação."}, "sem a contagem na observação"),
    ({"folha": "outra.dxf"}, "o arquivo da linha não é o da contagem (e o job tem 2 CAD)"),
])
def test_CONTROLE_o_que_nao_e_conferido(mudar, por_que):
    mapa = dict(CONTAGEM, **{"vizinha.dxf": {"25x25 cm": 8}})
    assert _conferidos([_linha(**mudar)], mapa) == [], por_que


def test_a_linha_que_ja_tem_prova_nao_muda():
    it = _linha(obs="Fonte: 8 retângulos de 25×25 cm contados geometricamente. Texto '25/25'.")
    assert _conferidos([it]) == []


def test_duas_linhas_com_a_mesma_contagem_nenhuma_e_conferida():
    """🩸 Revisão de 19/10: térreo 8 e superior 8, as duas citando os 8
    retângulos 25×25 do MESMO arquivo, sairiam as duas ✓ — 16 na planilha, 8 no
    desenho. Quem disputa a mesma contagem não é conferido."""
    terreo = _linha(descr="Pilar 25×25 cm — térreo")
    superior = _linha(descr="Pilar 25×25 cm — pavimento superior")
    assert _conferidos([terreo, superior]) == []
    assert _conferidos([terreo]) == [0], "controle: sozinha ela é conferida"


@pytest.mark.parametrize("outra, por_que", [
    (dict(conf="estimado"), "a outra está estimada, mas cita a mesma contagem"),
    (dict(obs="Fonte: 8 retângulos de 25×25 cm contados geometricamente."), "a outra já tem prova escrita"),
    (dict(q=5, obs="Fonte: 5 retângulos de 25×25 cm. Texto."), "a outra cita outro número da mesma seção"),
])
def test_qualquer_outra_linha_da_mesma_secao_disputa(outra, por_que):
    assert _conferidos([_linha(), _linha(descr="Pilar 25×25 cm — outro", **outra)]) == [], por_que


def test_a_linha_de_varias_secoes_tambem_disputa():
    """🩸 Re-revisão de 19/10: "Pilares — todos" estimado 12 ("8 retângulos de
    25×25 cm e 4 retângulos de 25×60 cm") ao lado de "Pilar 25×25" ✓ 8: a
    planilha soma 20 contra 12 no desenho. A linha de várias seções não é
    candidata, mas disputa cada seção que cita."""
    mapa = {FOLHA: {"25x25 cm": 8, "25x60 cm": 4}}
    todos = _linha(descr="Pilares — todos", conf="estimado", q=12,
                   obs="Fonte: 8 retângulos de 25×25 cm e 4 retângulos de 25×60 cm. Texto.")
    assert _conferidos([_linha(), todos], mapa) == []
    assert _conferidos([_linha()], mapa) == [0], "controle: sem a linha de todos, ela é conferida"


def test_secoes_ou_arquivos_diferentes_nao_disputam():
    mapa = {FOLHA: {"25x25 cm": 8, "25x60 cm": 4}, "vizinha.dxf": {"25x25 cm": 8}}
    secoes = [_linha(), _linha(descr="Pilar 25×60", q=4, obs="Fonte: 4 retângulos de 25×60 cm. Texto.")]
    assert _conferidos(secoes, mapa) == [0, 1]
    arquivos = [_linha(), _linha(descr="Pilar 25×25 — bloco B", folha="vizinha.dxf")]
    assert _conferidos(arquivos, mapa) == [0, 1]


def test_com_dois_cad_vale_o_arquivo_da_linha():
    """Cada linha confere com a contagem do SEU arquivo, não com a da vizinha."""
    mapa = {FOLHA: {"25x25 cm": 8}, "vizinha.dxf": {"25x25 cm": 3}}
    assert _conferidos([_linha()], mapa) == [0]
    assert _conferidos([_linha(folha="vizinha.dxf")], mapa) == [], "a vizinha contou 3, não 8"


def test_um_cad_so_vale_mesmo_sem_o_nome_da_folha():
    """A IA às vezes escreve outro nome na folha; com UM CAD no job não há dúvida."""
    assert _conferidos([_linha(folha="Planta de locação")]) == [0]
    assert _conferidos([_linha(folha="Planta de locação")],
                       dict(CONTAGEM, **{"vizinha.dxf": {"25x25 cm": 8}})) == []


# ── o motor ──────────────────────────────────────────────────────────────────
def test_o_main_poe_a_frase_na_frente_e_a_rede_deixa_o_selo(monkeypatch):
    import main
    from models import BudgetItem, Confidence
    logs = []
    monkeypatch.setattr(main, "_log_error", lambda etapa, msg, *a, **k: logs.append((etapa, msg)))
    itens = [BudgetItem(item_num="1", description="Pilar — seção 25×25 cm", unit="un", quantity=8,
                        observations=_linha()["observations"], ref_sheet=FOLHA,
                        confidence=Confidence.CONFIRMADO, origem="dxf_geom"),
             BudgetItem(item_num="2", description="Estaca Ø25", unit="un", quantity=7,
                        observations="Fonte: 7 círculos de Ø25 cm. Texto 'Ø25 ×7'.", ref_sheet=FOLHA,
                        confidence=Confidence.CONFIRMADO, origem="dxf_geom")]
    assert main._selo_do_pilar_conferido(itens, CONTAGEM, "job-nn") == 1
    assert itens[0].observations.startswith(er.MARCA_PILAR_CONFERIDO)
    assert [a["indice"] for a in er.selos_sem_geometria(itens)] == [1], (
        "o pilar conferido fica com o selo; a estaca, sem conferência, cai como antes")
    assert logs and logs[0][0] == "motor:pilar-conferido"


def test_o_main_nao_derruba_o_job_se_a_conferencia_falhar(monkeypatch):
    import main
    monkeypatch.setattr(er, "pilares_conferidos_pela_geometria",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("dublê")))
    assert main._selo_do_pilar_conferido([types.SimpleNamespace()], CONTAGEM, "job-nn") == 0


def test_a_contagem_por_secao_sai_do_desenho(tmp_path):
    import ezdxf
    import main
    from dwg_extractor import extract_dxf
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6
    doc.layers.add("PILAR")
    msp = doc.modelspace()
    for x in (0, 2):
        msp.add_lwpolyline([(x, 0), (x + 0.2, 0), (x + 0.2, 0.4), (x, 0.4)], close=True,
                           dxfattribs={"layer": "PILAR"})
    msp.add_circle((6, 0), 0.15, dxfattribs={"layer": "PILAR"})
    cam = str(tmp_path / "forma.dxf")
    doc.saveas(cam)
    assert main._pilares_por_secao(extract_dxf(cam)) == {"20x40 cm": 2, "Ø30 cm": 1}


def test_o_process_job_confere_antes_de_rebaixar():
    """A ordem importa: depois da rede, a linha já estaria rebaixada."""
    import inspect
    import main
    fonte = inspect.getsource(main.process_job)
    guarda = fonte.index("_pilares_por_folha[_dxf_nome] = _pilares_por_secao(extraction)")
    confere = fonte.index("_selo_do_pilar_conferido(all_items, _pilares_por_folha, job_id)")
    rebaixa = fonte.index("_sem_geo = _ssg(all_items)")
    assert guarda < confere < rebaixa
