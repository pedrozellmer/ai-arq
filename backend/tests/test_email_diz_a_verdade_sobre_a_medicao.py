# -*- coding: utf-8 -*-
"""O e-mail fala a mesma língua da régua: entrega sem medição não é comemorada.

🩸 06/09/2026, VISTO AO VIVO. Um cliente novo (cliente-15, job 40550d3e) subiu 3
PDFs de uma guarita e recebeu:
  · nas boas-vindas: "seu projeto vira planilha MEDIDA"
  · na entrega:      "sua planilha está PRONTA"
E a planilha tinha **124 itens com ZERO medidos do CAD** — 124 laranjas, 53 em
branco. Dois e-mails prometendo medição para uma entrega que não mediu nada.

POR QUE A IRMÃ DE MÁ NOTÍCIA NÃO PEGOU: `_build_sem_medida_email` só sai quando
≥80% das linhas estão EM BRANCO. Ali eram 53 de 124 (43%) — as outras tinham
número, só que ESTIMADO. O critério olhava linha VAZIA; o que importa é linha
MEDIDA. Neste projeto as duas respostas eram opostas.

🔑 O invariante: quando `_n_med == 0`, o cliente NÃO pode receber comemoração.
É a mesma condição que faz `_carimbar_regua_de_cobranca` marcar `cobravel =
false` — ou seja, o e-mail passa a dizer o mesmo que a cobrança diria.

🚫 As guardas da irmã continuam intocadas: a condição `_n_geo_nm == 0` foi posta
em 03/09 com caso documentado (mandar "não consegui ler seu arquivo" a quem TEVE
o desenho lido o faz procurar um arquivo melhor que não existe).
"""
import io
import os
import re
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import main  # noqa: E402


def _corpo_do_process_job():
    """O trecho que escolhe qual e-mail sai."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index("_nada_medido = (len(all_items) > 0")
    return src[i:i + 4000], src


# ─────────────────────────────────────────────────────────────────────────────
#  O texto existe e diz a verdade
# ─────────────────────────────────────────────────────────────────────────────

def test_o_terceiro_email_existe_e_nao_comemora():
    """Nem 'está pronta', nem 'não consegui ler seu arquivo'. O meio."""
    assunto, html = main._build_leu_sem_medir_email(
        "cliente-15", "orçamento são lourenço", "40550d3e", 124, 53,
        email="x@y.com")
    assert "pronta" not in assunto.lower(), assunto
    baixo = html.lower()
    # não pode prometer medição
    assert "planilha está pronta" not in baixo
    # tem que dizer o fato central
    assert "não consegui medir" in baixo or "nenhuma quantidade foi medida" in baixo, baixo[:400]


def test_o_email_traz_os_NUMEROS_reais_do_projeto():
    """🪤 Sem número, o cliente não sabe o tamanho do problema — e a frase vira
    genérica igual às outras. Com 124 itens e 53 em branco, as duas contas
    (71 com número, 53 sem) precisam aparecer."""
    _a, html = main._build_leu_sem_medir_email(
        "cliente-15", "guarita", "40550d3e", 124, 53, email="x@y.com")
    assert "124" in html, "o total de itens sumiu do texto"
    assert "53" in html, "as linhas em branco sumiram do texto"
    assert "71" in html, ("as linhas COM número estimado sumiram — é o número "
                          "que explica por que a irmã de má notícia não pegou")


def test_o_email_diz_o_que_o_cliente_FAZ_agora():
    """Má notícia sem saída é só má notícia. O DXF é o caminho conhecido."""
    _a, html = main._build_leu_sem_medir_email("x", "p", "j", 100, 40, email="e@e")
    assert "DXF" in html
    assert "de graça" in html or "gratis" in html.lower()


def test_o_email_NAO_promete_o_que_nao_temos():
    """🚨 Regra da casa: a copy não promete o que o código não faz. Ele não pode
    dizer que vamos medir depois, nem que alguém vai olhar manualmente."""
    _a, html = main._build_leu_sem_medir_email("x", "p", "j", 100, 40, email="e@e")
    for proibido in ("nossa equipe vai", "vamos medir pra você", "em breve",
                     "estamos corrigindo"):
        assert proibido not in html.lower(), proibido


# ─────────────────────────────────────────────────────────────────────────────
#  Está LIGADO no motor, e na ordem certa
# ─────────────────────────────────────────────────────────────────────────────

def test_o_motor_escolhe_o_terceiro_email_quando_nao_mediu_nada():
    """Guarda de FATO, EXECUTADO: com ZERO medidos, o e-mail que SAI é o do
    meio — nem comemoração, nem "não consegui ler seu arquivo".

    🚨 06/09/2026 — a versão anterior deste guarda lia o fonte e passava com o
    defeito aberto: bastou `elif _n_med == 0 and len(all_items) > 0 and False:`
    pra o terceiro e-mail virar código morto. A regex casava igual, o
    `_build_leu_sem_medir_email(` continuava no corpo, 11/11 verdes — e o
    cliente com zero medição voltava a receber "sua planilha está pronta",
    que é o caso visto ao vivo em 06/09.
    """
    from _fim_do_job import roda_ate_o_email
    d = roda_ate_o_email(_itens_do_caso_real(), nome_projeto="guarita")
    enviado = d["emails"][-1]
    assert enviado["kind"] == "leu_sem_medir", (
        "com ZERO medidos o motor mandou o e-mail %r — o do meio virou código "
        "morto:\n%s" % (enviado["kind"], enviado["assunto"]))
    assert "pronta" not in enviado["assunto"].lower(), (
        "o assunto comemora uma entrega que não mediu nada: " + enviado["assunto"])
    assert "planilha está pronta" not in enviado["html"].lower(), (
        "o corpo comemora uma entrega que não mediu nada")
    assert any("motor:leu-sem-medir" in l for l in d["logs"]), (
        "a troca de e-mail aconteceu sem rastro: %r" % (d["logs"][-4:],))


def _itens_do_caso_real():
    """A aritmetica exata do job 40550d3e: 124 itens, ZERO medidos, 53 zerados."""
    from models import BudgetItem, Confidence
    return [BudgetItem(item_num="1.%d" % k, description="Servico %d" % k,
                       unit="m²", quantity=(0.0 if k < 53 else 12.5 + k),
                       confidence=Confidence.ESTIMADO, origem="vision_pdf")
            for k in range(124)]


def test_CONTROLE_quem_MEDIU_continua_recebendo_a_planilha_pronta():
    """O outro lado, no MESMO caminho executado."""
    from _fim_do_job import roda_ate_o_email
    from models import BudgetItem, Confidence
    itens = [BudgetItem(item_num="1.%d" % k, description="Servico %d" % k,
                        unit="m²", quantity=(0.0 if k < 12 else 12.5 + k),
                        confidence=(Confidence.CONFIRMADO if k < 88
                                    else Confidence.ESTIMADO),
                        origem="dxf_geom")
             for k in range(108)]
    d = roda_ate_o_email(itens, nome_projeto="projeto medido")
    assert d["emails"][-1]["kind"] == "planilha_pronta", (
        "um projeto com 88 linhas medidas recebeu %r"
        % d["emails"][-1]["kind"])


def test_a_irmã_de_ma_noticia_continua_INTOCADA():
    """🚫 As três condições de `_nada_medido` não podem ter sido afrouxadas pra
    caber o caso novo. A `_n_geo_nm == 0` foi posta em 03/09 com caso real."""
    corpo, _src = _corpo_do_process_job()
    assert "_n_geo_nm == 0" in corpo, (
        "a guarda de 03/09 sumiu — voltaria a dizer 'não consegui ler seu "
        "arquivo' pra quem TEVE o desenho lido")
    assert "_LIMITE_BRANCO" in corpo, "o limite de 80% sumiu"


def test_o_log_do_envio_distingue_os_TRES_casos():
    """Sem isso não dá pra contar quantos clientes receberam cada versão — e foi
    contando que a gente descobriu os 41 'planilha pronta' com zero medição."""
    corpo, _src = _corpo_do_process_job()
    for kind in ('"sem_medida"', '"leu_sem_medir"', '"planilha_pronta"'):
        assert kind in corpo, "o log de envio não distingue %s" % kind


def test_o_aviso_novo_NAO_entope_o_painel_de_erros():
    _corpo, src = _corpo_do_process_job()
    i = src.index("_STAGES_DIAGNOSTICO = frozenset({")
    bloco = src[i:src.index("})", i)]
    assert '"motor:leu-sem-medir"' in bloco, (
        "o stage novo vai empurrar erro de verdade pra fora do painel")


def test_a_central_de_emails_conhece_o_texto_novo():
    """🪤 Em 05/09 cinco e-mails estavam 'fora do catálogo' da Central: sem
    ficha, sem preview, invisíveis pra quem revisa a copy. Texto novo entra no
    catálogo no MESMO commit em que nasce."""
    _corpo, src = _corpo_do_process_job()
    assert 'if key == "leu_sem_medir"' in src, (
        "o e-mail novo nasceu fora do catálogo da Central")
    # e pelo MESMO builder do envio real, não por uma cópia do texto
    i = src.index('if key == "leu_sem_medir"')
    assert "_build_leu_sem_medir_email(" in src[i:i + 400], (
        "a Central monta o preview por outro caminho — os dois textos vão "
        "divergir")


# ─────────────────────────────────────────────────────────────────────────────
#  O caso real, reproduzido
# ─────────────────────────────────────────────────────────────────────────────

def test_CONTROLE_o_caso_do_Devair_NAO_cairia_mais_na_comemoracao():
    """Reproduz a aritmética exata do job 40550d3e: 124 itens, 53 em branco,
    zero medidos. Com o limite de 80%, a irmã de má notícia NÃO pega — e é por
    isso que o terceiro caminho precisa existir."""
    n_total, n_zerado, n_med = 124, 53, 0
    _LIMITE = 0.8
    nada_medido = (n_total > 0 and n_med == 0 and n_zerado >= _LIMITE * n_total)
    assert nada_medido is False, (
        "a irmã de má notícia passou a pegar este caso — então o terceiro "
        "e-mail virou código morto e este guarda perdeu o sentido")
    # e o caminho novo pega
    assert (n_med == 0 and n_total > 0) is True


def test_CONTROLE_entrega_que_MEDIU_continua_comemorando():
    """O outro lado: quem teve medição de verdade não pode receber má notícia."""
    n_total, n_zerado, n_med = 108, 12, 88   # o SMARTFIT, melhor projeto de setembro
    _LIMITE = 0.8
    nada_medido = (n_total > 0 and n_med == 0 and n_zerado >= _LIMITE * n_total)
    assert nada_medido is False
    assert (n_med == 0 and n_total > 0) is False, (
        "um projeto com 88 linhas medidas cairia no e-mail de má notícia")
