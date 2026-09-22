# -*- coding: utf-8 -*-
"""O e-mail "leu, mas não mediu" não desmente o próprio bloco nem o próprio DWG.

🩸 22/09/2026 — revisão adversária do conserto dos jobs `ee801b82` e
`f8d8e6d8`. O texto novo tirou "CAD" de quem só mandou PDF e passou a dizer a
regra do PDF. Rodando a fatia real do fim do job, dois furos:

  · ARQUITETURA só-PDF com medição vetorial (o f8d8e6d8 como saiu): o selo
    dizia "⚠ Sem medição do desenho", o corpo "nenhuma quantidade foi medida
    do desenho", o título "não medi as quantidades", o placar "✓ 0 medido(s)
    do desenho" e o motivo "a IA lê a prancha e estima" — e logo abaixo, no
    MESMO e-mail, "📏 O que a gente mediu
    no seu PDF — prancha-B: 32 ambiente(s), 892.0 m²" e "a gente mede a
    geometria da prancha inteira". A doença de 18/09 ("o e-mail se contradizia
    em duas linhas"). 📏 Medido às 15:57 de 22/09 (now() de testemunha): dos 9
    leu_sem_medir com job_id desde 07/09, 8 registraram `pdfvec:por-prancha`
    (a entrada do bloco) e 7 desses não são de estrutura — 6 de arquitetura
    só-PDF + o 95bab8ba abaixo. 🪤 A 1ª contagem desta revisão dizia 6 e 5:
    tinha deixado de fora um job de arquitetura só-PDF com medição vetorial.
  · 1 DWG que NÃO converteu + 5 PDFs (formato do job 95bab8ba, de hoje): o DWG
    que falha deixa `_n_cad = 0`, o job passava por "só PDF", e o motivo dizia
    "uma regra nossa, não um defeito do seu arquivo" logo antes de "⚠ Seu
    arquivo DWG não abriu [...] Era o arquivo que mediria de verdade". O
    motivo de nada ter saído medido era o DWG.
  · E a Central de E-mails mostrava ao Pedro, no preview, a versão do CAD
    ("costuma ser escala", convite da área), que quase ninguém recebe.

🔑 Com o bloco no e-mail, o fato dito é "nenhuma linha da planilha saiu
marcada como medida" (o que o bloco também diz); com DWG que não abriu, o
motivo é o DWG. Sem bloco e sem DWG, o texto do 1º conserto fica.

🧪 Roda a fatia REAL do fim do `process_job` (`_fim_do_job.roda_ate_o_email`)
com os números do caso e nomes neutros. Controles: o texto de cada variante
continua onde ela é verdade.
"""
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _AQUI)
sys.path.insert(0, os.path.dirname(_AQUI))

import main  # noqa: E402
from _fim_do_job import roda_ate_o_email  # noqa: E402
from test_o_email_do_pdf_nao_promete_o_que_o_pdf_nao_da import (  # noqa: E402
    _AMBAR, _PDFVEC_DO_CASO, _cor_do_selo, _email, _itens_do_caso)

_BLOCO = "O que a gente mediu no seu PDF"
_SEM_MEDICAO_DO_DESENHO = "Sem medi&ccedil;&atilde;o do desenho"
_NADA_MEDIDO_DO_DESENHO = "nenhuma quantidade foi medida do desenho"
_NENHUMA_LINHA = "nenhuma linha da planilha saiu marcada como medida"
_REGRA_NOSSA = "uma regra nossa, não um defeito do seu arquivo"
_O_DWG = "O motivo é o arquivo DWG que não abriu"


def _email_dwg(pdfvec):
    """1 DWG que não converteu + 5 PDFs — o que o harness recebe desse envio."""
    d = roda_ate_o_email(_itens_do_caso(), project_type="arquitetura", n_pdf=5,
                         n_cad=0, pdfvec_por_prancha=pdfvec,
                         dwg_failed=["/tmp/x/planta-geral.dwg"],
                         nome_projeto="Projeto 22/09/2026", job_id="95bab8ba")
    return d["emails"][-1]


# ══════════════════════════════════════════════════════════════════════════
#  🩸 Arquitetura só-PDF com o bloco do que medimos
# ══════════════════════════════════════════════════════════════════════════
def test_com_o_bloco_do_PDF_o_selo_e_o_corpo_nao_dizem_que_nada_foi_medido():
    e = _email(project_type="arquitetura")
    html = e["html"]
    assert e["kind"] == "leu_sem_medir", e["kind"]
    assert _BLOCO in html, "o cenário perdeu o bloco — o guarda não mede nada"
    _cor, selo = _cor_do_selo(html)
    assert _SEM_MEDICAO_DO_DESENHO not in selo, (
        "o selo diz 'Sem medição do desenho' em cima do bloco '%s':\n%s"
        % (_BLOCO, selo))
    assert _NADA_MEDIDO_DO_DESENHO not in html, (
        "o corpo diz que nada foi medido do desenho e o bloco lista 892 m² "
        "medidos da prancha")
    assert "não medi as quantidades" not in html, "o título desmente o bloco"
    # o placar do diagnóstico conta LINHAS — "0 medido(s) do desenho" em cima
    # de "892 m² medidos da prancha" era a mesma contradição
    assert "medido(s)</b> do desenho" not in html, "o placar desmente o bloco"
    assert "0 medido(s)</b> na planilha (em branco)" in html, html[:3000]


def test_com_o_bloco_o_fato_dito_e_nenhuma_LINHA_marcada_como_medida():
    e = _email(project_type="arquitetura")
    assert _NENHUMA_LINHA in e["html"], e["html"][:3000]
    cor, selo = _cor_do_selo(e["html"])
    assert "Nada marcado como medido" in selo, selo
    assert cor == _AMBAR, cor
    assert "sem quantidade medida" not in e["assunto"], e["assunto"]


def test_com_o_bloco_o_motivo_nao_diz_que_a_IA_so_estima_a_prancha():
    html = _email(project_type="arquitetura")["html"]
    assert "a IA lê a prancha e <b>estima</b>" not in html, (
        "o motivo diz que a prancha só foi estimada e o bloco diz que a gente "
        "mediu a geometria dela")
    assert "mesmo quando a gente mede a geometria da prancha" in html


def test_o_bloco_que_falha_nao_derruba_o_email(monkeypatch):
    """🪤 O montador agora pergunta se o bloco saiu. Se a régua do bloco
    quebrar, o `try` dela engole o erro — e o nome `_medimos` tem que existir
    mesmo assim, senão o `NameError` derruba o e-mail inteiro no `except` de
    fora (o cliente fica sem aviso nenhum)."""
    import engine_rules

    def _quebra(*a, **k):
        raise RuntimeError("régua do bloco quebrou (dublê)")
    monkeypatch.setattr(engine_rules, "o_que_medimos_na_prancha", _quebra)
    e = _email(project_type="arquitetura")
    assert e["kind"] == "leu_sem_medir", e["kind"]
    assert _BLOCO not in e["html"]
    assert _NADA_MEDIDO_DO_DESENHO in e["html"], (
        "sem o bloco, o fato é o do 1º conserto")


# ── 🧪 CONTROLES: sem o bloco, o texto do 1º conserto continua ─────────────
def test_CONTROLE_arquitetura_SEM_medicao_vetorial_diz_nada_medido_do_desenho():
    e = _email(project_type="arquitetura", pdfvec={})
    assert _BLOCO not in e["html"]
    assert _NADA_MEDIDO_DO_DESENHO in e["html"]
    assert "a IA lê a prancha e <b>estima</b>" in e["html"]
    _cor, selo = _cor_do_selo(e["html"])
    assert _SEM_MEDICAO_DO_DESENHO in selo, selo


def test_CONTROLE_estrutura_nao_tem_bloco_e_mantem_nada_medido_do_desenho():
    """O ee801b82: o bloco some em estrutura, então o fato é o de antes."""
    e = _email(project_type="estrutura")
    assert _BLOCO not in e["html"]
    assert _NADA_MEDIDO_DO_DESENHO in e["html"]
    _cor, selo = _cor_do_selo(e["html"])
    assert _SEM_MEDICAO_DO_DESENHO in selo, selo


# ══════════════════════════════════════════════════════════════════════════
#  🩸 1 DWG que não abriu + PDFs (95bab8ba)
# ══════════════════════════════════════════════════════════════════════════
def test_DWG_que_nao_abriu_e_o_motivo_nao_a_regra_do_PDF():
    e = _email_dwg(_PDFVEC_DO_CASO)
    html = e["html"]
    assert "Seu arquivo DWG não abriu" in html, "o cenário perdeu o aviso do DWG"
    assert _REGRA_NOSSA not in html, (
        "disse 'regra nossa, não um defeito do seu arquivo' a quem mandou um DWG "
        "que não abriu — o motivo é o DWG")
    assert _O_DWG in html, html[:3000]


def test_DWG_que_nao_abriu_sem_bloco_fala_de_CAD():
    """Sem o bloco, quem mandou DWG lê CAD: nada foi medido DO CAD dele."""
    e = _email_dwg({})
    assert "do CAD" in e["assunto"], e["assunto"]
    assert "nenhuma quantidade foi medida do CAD" in e["html"]
    assert _O_DWG in e["html"]
    assert "O motivo costuma ser escala" not in e["html"]


def test_CONTROLE_so_PDF_sem_DWG_continua_com_a_regra_do_PDF():
    e = _email(project_type="arquitetura", pdfvec={})
    assert _REGRA_NOSSA in e["html"]
    assert _O_DWG not in e["html"]


def test_CONTROLE_job_MISTO_com_CAD_lido_nao_e_so_PDF():
    """🪤 1 PDF + 1 DXF lido: não é "só PDF" — o assunto e o motivo são os do CAD."""
    e = _email(n_pdf=1, n_cad=1)
    assert e["kind"] == "leu_sem_medir", e["kind"]
    assert "do CAD" in e["assunto"], e["assunto"]
    assert "O motivo costuma ser escala" in e["html"]
    assert _REGRA_NOSSA not in e["html"]


# ══════════════════════════════════════════════════════════════════════════
#  🩸 O preview da Central mostra o que o cliente recebe
# ══════════════════════════════════════════════════════════════════════════
def test_o_preview_da_central_e_a_versao_so_PDF():
    assunto, html = main._render_email_by_type("leu_sem_medir")
    assert "CAD" not in assunto, assunto
    assert "O motivo costuma ser escala" not in html, (
        "o preview mostra a versão do CAD, que quase ninguém recebe")
    assert "área total no upload" not in html, (
        "o preview convida a informar a área — recusado onde há medição vetorial")
    assert "de PDF a gente nunca marca um número como medido" in html


def test_CONTROLE_o_montador_sem_parametro_segue_com_a_versao_do_CAD():
    """Prova que é o preview que escolhe a variante (e não o montador fixo)."""
    assunto, html = main._build_leu_sem_medir_email(
        "cliente-nn", "p", "j", 124, 53, "", email="x@example.com")
    assert "do CAD" in assunto, assunto
    assert "O motivo costuma ser escala" in html
