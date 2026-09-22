# -*- coding: utf-8 -*-
"""O e-mail de quem só mandou PDF não promete o que o PDF não dá.

🩸 22/09/2026 — jobs `ee801b82` (estrutura) e `f8d8e6d8` (os MESMOS 7 PDFs de
uma página, reenviados no dia seguinte). A cliente recebeu dois e-mails
"leu_sem_medir" em 14h39 e deu NPS 2. Reproduzido com os builders do repo, o
e-mail de hoje (91 itens, 61 sem número, 0 medidos) dizia:

  · assunto "— sem quantidade medida do CAD", corpo "nenhuma quantidade foi
    medida do CAD", selo "⚠ Sem medição do CAD" — a quem não mandou CAD;
  · "O motivo costuma ser escala" — em PDF nada sai medido, com ou sem
    escala: é regra nossa, e o próprio diagnóstico logo abaixo diz isso;
  · "me diga a área total no upload" — com 1.116,3 m² de medição vetorial no
    job; com medição, a área digitada não vira número em linha NENHUMA;
  · "o peso de aço sai medido quando a prancha tem um quadro/resumo de aço" —
    três pranchas tinham o resumo, e o aço saiu ESTIMADO (PDF nunca é medido);
  · "📏 O que a gente mediu no seu PDF — DE-X: 32 ambiente(s), 892,0 m², na
    escala 1:125 lida do carimbo" — "ambiente" numa prancha estrutural é face
    fechada qualquer (tampa, abertura), e a escala veio do RÓTULO da vista;
  · e o selo de aviso na pílula VERDE de sucesso.

🔑 Cada frase agora sai do que o código de fato faz. O guarda RODA a fatia
real do fim do `process_job` (`_fim_do_job.roda_ate_o_email`) com os números
do caso e confere o HTML que sairia; os controles provam que o texto antigo
continua onde ele é verdade (projeto com CAD, arquitetura, job sem medição).
"""
import os
import re
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _AQUI)
sys.path.insert(0, os.path.dirname(_AQUI))

import engine_rules as er  # noqa: E402
import main  # noqa: E402
from _fim_do_job import roda_ate_o_email  # noqa: E402
from models import BudgetItem, Confidence  # noqa: E402

_VERDE = "#dcfce7"
_AMBAR = "#fef3c7"


def _it(k, desc, unit, q):
    return BudgetItem(item_num="1.%d" % k, description=desc, unit=unit, quantity=q,
                      confidence=Confidence.ESTIMADO, origem="vision_pdf",
                      discipline="Estrutura", ref_sheet="DE-X")


def _itens_do_caso():
    """91 itens, 61 sem número, 30 estimados, 0 medidos — a aritmética do
    f8d8e6d8, com a linha de "Fôrma … laje" que fazia a régua de superfície
    aceitar a área informada (e só a medição vetorial a recusava)."""
    itens = []
    for k in range(40):
        itens.append(_it(k, "Concreto estrutural C30 — estrutura E%d" % k, "m³", 0))
    itens.append(_it(40, "Fôrma — laje de cobertura circular", "m²", 0))
    for k in range(41, 58):
        itens.append(_it(k, "Fôrma de madeira — parede da estrutura E%d" % k, "m²", 0))
    for k in range(58, 61):
        itens.append(_it(k, "Armadura CA-50 — estrutura E%d" % k, "kg", 0))
    for k in range(61, 73):
        itens.append(_it(k, "Armadura CA-50 — resumo da prancha %d" % k, "kg", 100.0 + k))
    for k in range(73, 79):
        itens.append(_it(k, "Controle tecnológico do concreto %d" % k, "vb", 1))
    for k in range(79, 87):
        itens.append(_it(k, "Tampa de inspeção %d" % k, "un", 2))
    for k in range(87, 91):
        itens.append(_it(k, "Impermeabilização da estrutura E%d" % k, "m²", 9.0 + k))
    assert len(itens) == 91
    assert sum(1 for i in itens if i.quantity <= 0) == 61
    return itens


def _prancha(nome, m2, n, esc, src="vista"):
    return {"arquivo": nome, "rooms_m2": m2, "n_rooms": n, "scale": esc,
            "scale_src": src, "escala_validada": False, "cotas_batem": 0,
            "walls_m": 50.0}


#: a medição por prancha do caso (log pdfvec:por-prancha), com nomes neutros
_PDFVEC_DO_CASO = {
    "a": _prancha("prancha-B.pdf", 892.0, 32, 125),
    "b": _prancha("prancha-E.pdf", 175.1, 2, 25),
    "c": _prancha("prancha-G.pdf", 27.7, 6, 50),
    "d": _prancha("prancha-F.pdf", 16.4, 5, 50),
    "e": _prancha("prancha-C.pdf", 3.0, 1, 25),
    "f": _prancha("prancha-A.pdf", 2.1, 1, 25),
}


def _email(project_type="estrutura", n_pdf=7, n_cad=0, pdfvec=None, itens=None):
    d = roda_ate_o_email(itens if itens is not None else _itens_do_caso(),
                         project_type=project_type, n_pdf=n_pdf, n_cad=n_cad,
                         pdfvec_por_prancha=(_PDFVEC_DO_CASO if pdfvec is None
                                             else pdfvec),
                         nome_projeto="Projeto 22/09/2026", job_id="f8d8e6d8")
    return d["emails"][-1]


def _cor_do_selo(html):
    m = re.search(r"background:(#[0-9a-fA-F]{6});color:#[0-9a-fA-F]{6};font-size:12px;"
                  r"font-weight:700;[^>]*>([^<]*)</span>", html)
    assert m, "não achei o selo no e-mail"
    return m.group(1).lower(), m.group(2)


# ══════════════════════════════════════════════════════════════════════════
#  🩸 O caso, com os números dela
# ══════════════════════════════════════════════════════════════════════════
def test_o_caso_sai_como_leu_sem_medir_com_os_numeros_reais():
    e = _email()
    assert e["kind"] == "leu_sem_medir", e["kind"]
    assert "91 itens" in e["html"], "o total de itens sumiu"
    assert "30 linhas que vieram com número" in e["html"]
    assert "61 ficaram sem número" in e["html"]


def test_quem_so_mandou_PDF_nao_le_CAD_no_assunto_nem_no_selo():
    e = _email()
    assert "CAD" not in e["assunto"], (
        "o assunto fala de CAD a quem só mandou PDF: %r" % e["assunto"])
    assert "nenhuma quantidade foi medida do desenho" in e["html"]
    assert "medida do CAD" not in e["html"], "o corpo ainda fala de CAD"
    assert "direto do CAD" not in e["html"], "o placar do diagnóstico ainda fala de CAD"
    _cor, selo = _cor_do_selo(e["html"])
    assert "CAD" not in selo, selo


def test_o_selo_de_aviso_sai_na_pilula_AMBAR():
    cor, selo = _cor_do_selo(_email()["html"])
    assert "&#9888;" in selo, selo
    assert cor == _AMBAR, (
        "o selo '%s' saiu na pílula %s — verde é a cor de sucesso" % (selo, cor))


def test_o_motivo_e_a_regra_do_PDF_nao_a_escala():
    html = _email()["html"]
    assert "O motivo costuma ser escala" not in html, (
        "voltou a culpar a escala — em PDF nada sai medido, com ou sem escala")
    assert "de PDF a gente nunca marca um número como medido" in html


def test_nao_pede_a_area_total_quando_a_medicao_vetorial_a_recusaria():
    html = _email()["html"]
    assert "área total no upload" not in html, (
        "pediu a área total com 1.116,3 m² de medição vetorial no job — lá ela "
        "não entra em linha nenhuma")


def test_o_aco_de_PDF_nao_e_prometido_como_medido():
    html = _email()["html"]
    assert "sai medido quando a prancha tem" not in html, (
        "prometeu aço medido a quem mandou PDF — o resumo estava lá e o aço "
        "saiu estimado")
    assert "sai como estimativa pra conferir" in html


def test_em_ESTRUTURA_o_bloco_nao_lista_ambientes_nem_m2_do_pdfvec():
    html = _email()["html"]
    assert "O que a gente mediu no seu PDF" not in html
    for proibido in ("892", "ambiente(s)", "175.1", "1:125"):
        assert proibido not in html, (
            "vazou pro e-mail de estrutura: %r" % proibido)


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLES — o texto antigo continua onde é verdade
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_em_ARQUITETURA_o_bloco_sai_e_diz_a_fonte_REAL_da_escala():
    """O f8d8e6d8 saiu como arquitetura: lá o bloco continua, mas a escala da
    prancha-B veio do rótulo da vista — e é isso que o cliente lê."""
    html = _email(project_type="arquitetura")["html"]
    assert "O que a gente mediu no seu PDF" in html, "o bloco sumiu da arquitetura"
    assert "1:125 lida do rótulo escrito ao lado do próprio desenho" in html, html[-3000:]
    assert "lida do carimbo" not in html, "a escala da vista ainda sai como carimbo"


def test_CONTROLE_escala_do_carimbo_continua_dita_como_carimbo():
    pv = {"a": _prancha("prancha-A.pdf", 90.9, 22, 100, src="carimbo")}
    html = _email(project_type="arquitetura", pdfvec=pv)["html"]
    assert "1:100 lida do carimbo da prancha (sem conferência contra cota)" in html


def test_CONTROLE_sem_medicao_vetorial_o_convite_da_area_volta():
    """Sem pdfvec, a área informada preenche a "Fôrma — laje" — o convite é
    verdade e tem que sair."""
    html = _email(pdfvec={})["html"]
    assert "área total no upload" in html, "o convite da área sumiu sempre"


def test_CONTROLE_projeto_com_CAD_mantem_CAD_e_a_frase_do_aco_do_CAD():
    e = _email(n_pdf=0, n_cad=1)
    assert e["kind"] == "leu_sem_medir", e["kind"]
    assert "do CAD" in e["assunto"], e["assunto"]
    assert "sai medido quando a prancha tem" in e["html"], (
        "a frase do aço medido do CAD sumiu também do CAD")
    assert "O motivo costuma ser escala" in e["html"]


def test_CONTROLE_a_irma_sem_medida_tambem_sai_ambar():
    _s, html = main._build_sem_medida_email("cliente-nn", "p", "j", 30, 27, "",
                                            email="x@example.com")
    cor, _selo = _cor_do_selo(html)
    assert cor == _AMBAR, cor


def test_CONTROLE_a_boa_noticia_continua_verde():
    """Se o âmbar fosse fixo, o guarda de cima passaria sem provar nada."""
    _s, html = main._build_planilha_pronta_email("cliente-nn", "p", "j", 20, "",
                                                 email="x@example.com")
    cor, _selo = _cor_do_selo(html)
    assert cor == _VERDE, cor


# ══════════════════════════════════════════════════════════════════════════
#  As réguas, chamadas direto
# ══════════════════════════════════════════════════════════════════════════
def test_o_que_medimos_devolve_vazio_em_estrutura_e_lista_em_arquitetura():
    assert er.o_que_medimos_na_prancha(_PDFVEC_DO_CASO, project_type="estrutura") == ""
    assert er.o_que_medimos_na_prancha(_PDFVEC_DO_CASO, project_type="Estrutura ") == ""
    t = er.o_que_medimos_na_prancha(_PDFVEC_DO_CASO, project_type="arquitetura")
    assert "32 ambiente(s)" in t, t


def test_cada_fonte_da_escala_e_dita_como_ela_e():
    def frase(src):
        return er.o_que_medimos_na_prancha(
            {"a": _prancha("p.pdf", 10.0, 2, 50, src=src)})
    assert "lida do rótulo escrito ao lado do próprio desenho" in frase("vista")
    assert "lida da caixa de recorte do PDF" in frase("viewport")
    assert "lida do carimbo da prancha" in frase("carimbo")
    cotas = frase("cotas")
    assert "lida das cotas escritas na prancha (por votação)" in cotas, cotas
    assert "sem conferência contra cota" not in cotas, (
        "a frase nega a própria fonte: a escala VEIO das cotas")
    nada = frase(None)
    assert "de origem não identificada" in nada and "carimbo" not in nada, nada


def test_a_procedencia_do_email_e_a_mesma_do_motor():
    """🪤 Duas balanças: `main._FONTE_DA_ESCALA` (prompt e observação da linha)
    e `engine_rules.FONTE_DA_ESCALA_SEM_PROVA` (e-mail). Fonte nova no motor sem
    frase no e-mail cairia em "origem não identificada" calada."""
    assert set(er.FONTE_DA_ESCALA_SEM_PROVA) == set(main._FONTE_DA_ESCALA), (
        "as fontes de escala divergiram entre o motor e o e-mail")
    for src, (fonte, _ressalva) in main._FONTE_DA_ESCALA.items():
        assert er.FONTE_DA_ESCALA_SEM_PROVA[src] == fonte, src


def test_a_regua_da_area_informada_respeita_a_medicao_vetorial():
    itens = _itens_do_caso()
    assert er.area_informada_mudaria_a_planilha(itens, 0) is True
    assert er.area_informada_mudaria_a_planilha(itens, 1116.3) is False
    so_parede = [_it(1, "Alvenaria — paredes internas", "m²", 0)]
    assert er.area_informada_mudaria_a_planilha(so_parede, 0) is False
