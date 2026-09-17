# -*- coding: utf-8 -*-
"""Quem manda PDF fica sabendo o que a gente MEDIU — sem nenhuma linha mentir.

🩸 Medido em 17/09/2026, janela 19/07–16/09: **34 de 34** projetos só-PDF saíram
sem UMA linha marcada como medida — 100%, 31 clientes. E em **19 desses 34** a
gente mediu a geometria e conferiu a escala contra as cotas do próprio desenho.
O cliente concluía "esse produto não mede o meu arquivo". A gente media e
escondia.

🚫 A saída ÓBVIA — marcar a linha como medida — foi REPROVADA em revisão
adversarial no mesmo dia, pelo mesmo furo que aposentou o promotor automático em
15/07: a única prova disponível é "o número desta linha é igual ao total desta
prancha", e como só existe UM total de área por prancha, QUALQUER linha que cite
esse número casa. Demolição pegaria a área do piso novo; rodapé, soleira e dreno
pegariam o mesmo comprimento.

🔑 Então a verdade é dita no nível em que ela se sustenta: a PRANCHA. "Medimos 22
ambientes, 90,9 m²" é fato sobre o desenho e não afirma nada sobre linha nenhuma
da planilha — impossível virar falso-medido, porque não rotula item.

🚨 O guarda do e-mail RODA a fatia real do `process_job`.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import engine_rules as er  # noqa: E402
from _fim_do_job import roda_ate_o_email  # noqa: E402

_PROVADA = {"arquivo": "PLANTA BAIXA.pdf", "rooms_m2": 90.9, "n_rooms": 22,
            "scale": 100, "escala_validada": True, "cotas_batem": 18,
            "walls_m": 3213.7}
_CARIMBO = {"arquivo": "CORTES.pdf", "rooms_m2": 12.4, "n_rooms": 3,
            "scale": 50, "escala_validada": False, "walls_m": 88.0}
_VAZIA = {"arquivo": "FACHADA.pdf", "rooms_m2": 0, "n_rooms": 0, "walls_m": 12.0}


# ── a frase ────────────────────────────────────────────────────────────────
def test_diz_quantos_ambientes_e_quantos_metros():
    t = er.o_que_medimos_na_prancha({"a": _PROVADA})
    assert "22 ambiente(s)" in t and "90.9 m²" in t, t


def test_a_escala_CONFERIDA_e_a_do_carimbo_sao_ditas_diferente():
    """🔑 As duas valem coisas diferentes, então não podem ser ditas igual."""
    conferida = er.o_que_medimos_na_prancha({"a": _PROVADA})
    carimbo = er.o_que_medimos_na_prancha({"a": _CARIMBO})
    assert "18 cota(s)" in conferida, conferida
    assert "sem conferência contra cota" in carimbo, carimbo
    assert "cota(s) escritas" not in carimbo, (
        "prancha sem conferência está se passando por conferida: %r" % carimbo)


def test_NAO_promete_escala_PROVADA():
    """🪤 A revisão adversarial mostrou que a validação aceita 2 pares que podem
    ser a MESMA medida cotada duas vezes, e não confere o eixo. Dizer "bate com
    18 cotas" é afirmar concordância — que é o que a gente sabe. Dizer "escala
    provada" prometeria o que a régua não entrega."""
    t = er.o_que_medimos_na_prancha({"a": _PROVADA}).lower()
    assert "provada" not in t and "garantid" not in t, t


def test_CONTROLE_o_comprimento_de_PAREDE_nunca_aparece():
    """🩸 Medido em 45 dias: `walls_m` chega a 84× o perímetro mínimo da área
    (3.213 m num imóvel de 90 m²). É a soma de todo traço de parede, as duas
    faces e provavelmente hachura. Mostrar ao cliente seria impressionar com um
    número que a gente SABE que está errado."""
    t = er.o_que_medimos_na_prancha({"a": _PROVADA, "b": _CARIMBO})
    for proibido in ("3213", "3.213", "parede", "88.0", "88,0"):
        assert proibido.lower() not in t.lower(), (
            "o comprimento de parede vazou pro cliente: %r em %r" % (proibido, t))


def test_prancha_sem_ambiente_medido_fica_de_fora():
    assert er.o_que_medimos_na_prancha({"c": _VAZIA}) == ""
    t = er.o_que_medimos_na_prancha({"a": _PROVADA, "c": _VAZIA})
    assert "FACHADA" not in t, t


def test_sem_medicao_nenhuma_a_frase_nao_existe():
    assert er.o_que_medimos_na_prancha({}) == ""
    assert er.o_que_medimos_na_prancha(None) == ""


def test_a_maior_prancha_vem_primeiro():
    t = er.o_que_medimos_na_prancha({"b": _CARIMBO, "a": _PROVADA})
    assert t.index("PLANTA BAIXA") < t.index("CORTES"), t


# ── a outra metade da verdade ──────────────────────────────────────────────
def test_o_porque_diz_as_DUAS_coisas():
    """🔑 Sozinha, a frase de cima engana ao contrário: o cliente leria
    "mediram 90 m²" e perguntaria por que a planilha está toda laranja."""
    t = er.porque_nada_saiu_medido_no_pdf()
    assert "MEDIDA" in t, t
    assert "DWG" in t and "DXF" in t, "não diz o caminho pra medir de verdade"
    assert "estimativa" in t.lower(), t


def test_o_porque_NAO_culpa_o_arquivo_do_cliente():
    """🪤 Regra da casa: 53 de 74 falhas eram NOSSAS e a mensagem culpava o
    arquivo. Aqui a limitação é nossa e o texto diz isso."""
    t = er.porque_nada_saiu_medido_no_pdf().lower()
    for culpa in ("seu arquivo não", "arquivo ruim", "arquivo de baixa",
                  "problema no seu"):
        assert culpa not in t, t
    assert "não consegue" in t or "não der pra" in t, t


# ── o e-mail: guarda de CHAMADA, roda a fatia real ─────────────────────────
class _It(object):
    def __init__(self, conf="estimado"):
        self.description = "piso ceramico"
        self.unit = "m2"
        self.quantity = 10.0
        self.confidence = conf
        self.discipline = "Pisos"
        self.origem = "vision_pdf"


def test_o_EMAIL_de_quem_mandou_PDF_leva_o_que_medimos():
    diario = roda_ate_o_email([_It(), _It()], n_pdf=1, n_cad=0,
                              pdfvec_por_prancha={"a": _PROVADA})
    html = diario["emails"][-1]["html"]
    assert "22 ambiente(s)" in html, "o bloco não chegou no e-mail"
    assert "18 cota(s)" in html
    assert "Nenhuma linha da planilha saiu marcada como MEDIDA" in html, (
        "saiu só a metade boa da verdade")


def test_CONTROLE_projeto_de_CAD_nao_recebe_esse_bloco():
    """O texto fala de PDF. Num projeto de CAD ele seria ruído — e mentira,
    porque lá a medição SAI por item."""
    diario = roda_ate_o_email([_It(), _It()], n_pdf=0, n_cad=1,
                              pdfvec_por_prancha={"a": _PROVADA})
    html = diario["emails"][-1]["html"]
    assert "O que a gente mediu no seu PDF" not in html, html[:300]


def test_CONTROLE_PDF_sem_medicao_nenhuma_nao_ganha_bloco_vazio():
    diario = roda_ate_o_email([_It(), _It()], n_pdf=1, n_cad=0,
                              pdfvec_por_prancha={"c": _VAZIA})
    html = diario["emails"][-1]["html"]
    assert "O que a gente mediu no seu PDF" not in html


def test_o_bloco_NAO_marca_item_nenhum_como_medido():
    """🚨 O guarda que trava o motivo da reprovação de 17/09: dizer o que
    medimos NÃO pode virar selo em linha nenhuma."""
    diario = roda_ate_o_email([_It(), _It()], n_pdf=1, n_cad=0,
                              pdfvec_por_prancha={"a": _PROVADA})
    ns = diario["ns"]
    for it in ns["all_items"]:
        assert str(getattr(it.confidence, "value", it.confidence)) == "estimado", (
            "o bloco informativo promoveu um item — é exatamente o que a "
            "revisão adversarial reprovou")
