# -*- coding: utf-8 -*-
"""`resgate=0` tinha duas leituras, e ninguém conseguia separar.

🩸 18/09/2026. O resgate da medição — que devolve à coluna o número que o motor
já tinha escrito na observação — existe desde **26/08** e NUNCA disparou:
`resgate_pdf=0` em 28 de 28 jobs. Em **07/09** a resposta a esse zero foi
construir um SEGUNDO mecanismo, perguntado noutro momento. Ele também dá zero.

🔑 Dois mecanismos, a mesma premissa, e ninguém mediu a premissa — porque o
log não permitia. "resgate=0" se lê como:

  (a) não havia alvo nenhum (a prancha do item não foi medida), ou
  (b) havia alvo, e o número citado na observação não era o nosso.

São diagnósticos opostos: (a) manda consertar o casamento de prancha, (b) diz
que não há o que resgatar. Sem separar, a casa escolheu (a) — e o conserto de
(a) não existia, porque o casamento JÁ funcionava.

📏 Medido em 18/09, no acervo inteiro: 313 dos 442 itens zerados (71%) estão
numa prancha que o pdfvec mediu — o casamento funciona. Dos 204 conferíveis,
só **16** citam o nosso número, e tirando avaliação, trial, parede e os
barrados pela trava do "um por prancha" sobram **5 itens em 3 jobs**.

O resgate está calado porque não há o que resgatar. `resg_alvos` é o número
que torna essa frase verificável na próxima leitura, em vez de deduzível.
"""
import io
import os
import re
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def _linha_do_log():
    """O `_log_error("motor:honestidade-area", ...)` inteiro, como está no fonte."""
    i = _FONTE.find('_log_error("motor:honestidade-area"')
    assert i > 0, "sumiu a telemetria motor:honestidade-area"
    return _FONTE[i:i + 1400]


def test_a_telemetria_diz_quantos_ALVOS_existiam():
    """Sem isto, `resgate_tardio=0` não distingue 'sem alvo' de 'alvo sem número'."""
    bloco = _linha_do_log()
    assert "resg_alvos=" in bloco, (
        "o log da honestidade de área voltou a dizer só o resultado do resgate, "
        "sem dizer se havia ALVO — as duas leituras de zero voltam a se confundir")


def test_o_contador_de_alvos_e_o_TAMANHO_do_mapa():
    """🪤 Ancorado no FATO: o número publicado tem que sair de `_resg_alvo`,
    não de uma variável solta que alguém pode esquecer de incrementar."""
    i = _FONTE.find("ultimo_resg_alvos")
    assert i > 0, "não achei o contador de alvos"
    trecho = _FONTE[i - 200:i + 200]
    assert "len(_resg_alvo)" in trecho, (
        "o contador de alvos parou de sair do tamanho do mapa — se virar "
        "contador manual, some no primeiro `continue` que alguém acrescentar")


def test_os_DOIS_resgates_continuam_reportados():
    """Controle de vizinhança: o instrumento novo não pode ter comido os velhos.

    São dois mecanismos e dois momentos (26/08 no laço de páginas, 07/09 na
    hora de zerar). Um número só esconderia qual dos dois morreu.
    """
    bloco = _linha_do_log()
    for campo in ("resgate_pdf=", "resgate_tardio=", "zerados=", "preservados="):
        assert campo in bloco, "sumiu %r da telemetria da honestidade de área" % campo


def test_o_alcance_MEDIDO_esta_escrito_ao_lado_do_codigo():
    """🚫 O guarda que impede o TERCEIRO mecanismo.

    O segundo nasceu porque o zero do primeiro foi lido como defeito, sem
    ninguém medir a premissa. A medição de 18/09 (5 itens em 3 jobs) fica
    ESCRITA no ponto onde a próxima pessoa iria mexer — inclusive eu.
    """
    i = _FONTE.find("_resg_alvo = {}")
    assert i > 0, "não achei o pré-passo do resgate"
    cabeca = _FONTE[max(0, i - 2000):i]
    assert "NUNCA disparou" in cabeca, (
        "sumiu do código o registro de que este resgate nunca disparou")
    assert "5 itens" in cabeca, (
        "sumiu o ALCANCE medido — sem o número, a próxima pessoa reconstrói "
        "o mecanismo achando que vale centenas de linhas")
    assert "terceiro mecanismo" in cabeca.lower(), (
        "sumiu o aviso explícito de não construir mais um")


def test_a_regua_RODA_e_publica_o_contador():
    """🔑 O guarda que EXECUTA, e não lê o fonte.

    Os de cima cobram a costura (o campo no log, a origem do número, o aviso
    ao lado do código). Este roda `_apply_area_honesty` de verdade e confere
    que o contador existe depois — se alguém tirar a atribuição, a telemetria
    passa a imprimir o valor da rodada ANTERIOR, que é pior que não imprimir.
    """
    import main
    # a função é tolerante a lista vazia: é o caminho mais curto pra provar
    # que a atribuição acontece em TODA passagem, não só quando há alvo.
    main._apply_area_honesty.ultimo_resg_alvos = 999      # sujeira de propósito
    main._apply_area_honesty([], 0, "")
    assert getattr(main._apply_area_honesty, "ultimo_resg_alvos", None) == 0, (
        "a régua rodou e NÃO reescreveu o contador de alvos — o log vai "
        "publicar o número da rodada anterior, e um job herda o diagnóstico "
        "de outro")


def test_CONTROLE_o_leitor_acha_mesmo_o_bloco():
    """🧪 Guarda que lê fonte e não acha nada passa verde guardando nada."""
    bloco = _linha_do_log()
    assert len(bloco) > 200 and "honestidade-area" in bloco
    assert len(re.findall(r"\w+=", bloco)) >= 6, (
        "o recorte do log pegou pouca coisa — o guarda pararia de medir")
