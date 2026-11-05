# -*- coding: utf-8 -*-
"""Arquivo com " (1)" no NOME acha a legenda da própria prancha.

🩸 05/11/2026 — job 0dce4d2b: "…ACABAMENTO (1).pdf" (o nome que o navegador dá
ao baixar o mesmo arquivo de novo). O `ref_sheet` é "<arquivo> (<título>)" e a
honestidade cortava no 1º " (": sobrava "…ACABAMENTO", que não é chave de
nada, e a legenda "PISO VINÍLICO … 62,37m²" nunca era achada — escritos=0,
piso zerado. 📏 90 dias: 36 jobs de cliente com arquivo assim (41 PDFs).

🛑 Nasce DESLIGADA (ARQUIVO_COM_PARENTESE=1 liga): com 0 a planilha não muda e
a etapa `motor:arquivo-com-parentese` lista o que ficaria.

🪤 Nomes de arquivo e textos FICTÍCIOS (repositório público, regra nº6).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402
import engine_rules as er  # noqa: E402

ARQ = "Planta-de-Acabamento (1).pdf"
LEGENDA = ("LEGENDA PISO\n01- PISO VINÍLICO - (MARCA E MODELO A DEFINIR) - 62,37m²\n"
           "PISO TETO X X X\n")
_LIDO = "Quantidade lida da legenda da prancha. | Estimativa: lido de PDF, não medido em geometria"


class _Item:
    def __init__(self, desc, unit, qty, ref_sheet=ARQ + " (Planta de Acabamento 00)"):
        self.description = desc
        self.unit = unit
        self.quantity = qty
        self.observations = _LIDO
        self.ref_sheet = ref_sheet
        self.origem = "vision_pdf"
        self.confidence = "estimado"


def _mapa(arq=ARQ, texto=LEGENDA):
    return {(arq.lower(), 0): er.numeros_escritos_com_material(texto)}


def _roda(monkeypatch, liga, itens, mapa=None):
    monkeypatch.setenv("ARQUIVO_COM_PARENTESE", "1" if liga else "0")
    main._apply_area_honesty(itens, numeros_com_material_por_prancha=(
        _mapa() if mapa is None else mapa))
    return main._apply_area_honesty.ultimo_arquivo_com_parentese


def _piso(**kw):
    return _Item("Piso vinílico — marca e modelo a definir", "m²", 62.37, **kw)


# ══════════════════════════════════════════════════════════════════════════
#  A régua do nome
# ══════════════════════════════════════════════════════════════════════════
def test_o_nome_inteiro_vence_o_corte_no_primeiro_parentese():
    assert er.arquivo_do_ref_sheet(ARQ + " (Planta)", {ARQ.lower()}) == ARQ


def test_o_mais_longo_que_serve_vence():
    conhecidos = {"planta.pdf", "planta (1).pdf"}
    assert er.arquivo_do_ref_sheet("Planta (1).pdf (p2 · X)", conhecidos) == "Planta (1).pdf"
    assert er.arquivo_do_ref_sheet("Planta.pdf (p2 · X)", conhecidos) == "Planta.pdf"


def test_prefixo_que_nao_termina_no_limite_nao_serve():
    """"planta" abre "planta-b.pdf (…)", mas o nome não termina ali."""
    assert er.arquivo_do_ref_sheet("planta-b.pdf (X)", {"planta"}) == "planta-b.pdf"


def test_sem_conhecido_fica_o_corte_de_antes():
    assert er.arquivo_do_ref_sheet("x.pdf (Planta)") == "x.pdf"
    assert er.arquivo_do_ref_sheet("x (1).pdf (Planta)", {"outro.pdf"}) == "x"
    assert er.arquivo_do_ref_sheet("", {"x.pdf"}) == ""


def test_a_caixa_do_ref_sheet_e_mantida():
    assert er.arquivo_do_ref_sheet("ACAB (1).PDF (P)", {"acab (1).pdf"}) == "ACAB (1).PDF"


# ══════════════════════════════════════════════════════════════════════════
#  A chave
# ══════════════════════════════════════════════════════════════════════════
def test_desligada_o_piso_zera_como_antes_e_a_lista_diz_que_ficaria(monkeypatch):
    it = _piso()
    vistos, liga = _roda(monkeypatch, False, [it])
    assert it.quantity == 0, "com a chave em 0 a planilha não pode mudar"
    assert liga is False
    assert vistos == [(62.37, "Piso vinílico — marca e modelo a definir")]


def test_ligada_o_piso_fica_estimado_com_o_trecho(monkeypatch):
    it = _piso()
    vistos, liga = _roda(monkeypatch, True, [it])
    assert it.quantity == 62.37, "a legenda da própria prancha não foi achada"
    assert str(getattr(it.confidence, "value", it.confidence)) == "estimado"
    assert it.observations.startswith(er.MARCA_VALOR_ESCRITO)
    assert "62,37m²" in it.observations
    assert liga is True and len(vistos) == 1
    assert main._apply_area_honesty.ultimo_escritos_preservados == 1


def test_arquivo_sem_parentese_nao_entra_na_lista(monkeypatch):
    """Controle: o caso que já funcionava não muda e não é contado."""
    arq = "Planta-de-Acabamento.pdf"
    it = _piso(ref_sheet=arq + " (Planta de Acabamento 00)")
    vistos, _ = _roda(monkeypatch, False, [it], _mapa(arq))
    assert it.quantity == 62.37, "o caso sem parêntese já ficava"
    assert vistos == []


def test_numero_que_nao_esta_na_legenda_segue_zerado_mesmo_ligada(monkeypatch):
    it = _Item("Piso vinílico — marca e modelo a definir", "m²", 70.0)
    vistos, _ = _roda(monkeypatch, True, [it])
    assert it.quantity == 0
    assert vistos == []


def test_material_que_a_linha_nao_cita_segue_zerado_mesmo_ligada(monkeypatch):
    it = _Item("Forro de gesso liso", "m²", 62.37)
    vistos, _ = _roda(monkeypatch, True, [it])
    assert it.quantity == 0
    assert vistos == []


# ══════════════════════════════════════════════════════════════════════════
#  Guardas do fonte
# ══════════════════════════════════════════════════════════════════════════
_SRC = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "main.py"), encoding="utf-8").read()


def test_a_chave_e_avaliavel_e_a_etapa_e_de_diagnostico():
    assert "ARQUIVO_COM_PARENTESE" in main._CHAVES_AVALIAVEIS
    assert "motor:arquivo-com-parentese" in main._STAGES_DIAGNOSTICO


def test_a_etapa_e_gravada_no_job():
    assert '_log_error("motor:arquivo-com-parentese"' in _SRC
