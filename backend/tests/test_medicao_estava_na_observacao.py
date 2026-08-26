# -*- coding: utf-8 -*-
"""A medição estava escrita na linha e a quantidade vinha ZERO.

🚨 26/08/2026, caso **Alan** (job de 24/08 21:39, 307 itens). De 73 linhas de
área e comprimento, **31 saíram com quantidade zero** — e várias delas traziam
o número medido escrito na própria observação:

    "Forro de gesso acartonado"    qtd 0   "área hachurada do layer -TEFOR
                                            = 26.54 m² (17 hachuras)"
    "Revestimento de parede"       qtd 0   "área hachurada do layer '-TEPAR'
                                            = 268.39 m² (soma de 8 hachuras)"
    "Execução de parede nova"      qtd 0   "comprimento do layer '-TEPAR'
                                            = 302.14 m"

O motor mediu, a IA citou o layer e o valor, e a coluna de quantidade veio
vazia. 268,39 m² de revestimento e 302,14 m de parede nova são as linhas mais
caras do levantamento dele.

Medido no acervo: **126 de 1.579** linhas zeradas de área/comprimento (8,0%)
carregam um número medido na observação.

🔑 ISTO NÃO CONFIA NO TEXTO — e essa é a diferença que faz a coisa ser segura.
A observação só diz ONDE olhar; quem decide é a extração. O valor citado tem
que bater (±1%) com `get_areas_by_layer()` / `get_walls_by_layer()` do MESMO
layer. Layer inexistente, número que não confere ou unidade trocada → a linha
continua zerada.

🪤 **O CAMINHO FÁCIL JÁ FOI TESTADO E REPROVADO.** Em 25/08, proibir
`quantity=0` no prompt destravou 30 de 31 linhas — com **chute redondo** (50,
80, 40, 25, 45 m²), e só 2 a 5 de 30+ batiam com alguma área da prancha.
"Zero pelo menos não mente." Ver [[project_resolucao_espremida_pdf_20260825]].
O que muda aqui é que o número não é da IA: é NOSSO, e é conferido.

🚫 E não promove nada: quem chama mantém o `confidence` que a IA deu. Preencher
a quantidade e carimbar 'medido' são passos diferentes (regra dura nº1).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine_rules import quantidade_da_procedencia as q  # noqa: E402

# a extração REAL da prancha do Alan, do jeito que o motor devolve
AREAS = {"-TEFOR": 26.54, "-TEPAR": 268.39, "-TEDUTO": 12.0}
COMPR = {"-TEPAR": 302.14, "-TEDUTO": 199.08}


def test_o_forro_do_Alan_para_de_sair_zerado():
    obs = "Fonte: área hachurada do layer -TEFOR = 26.54 m² (17 hachuras). Pode ser acaba"
    assert q(obs, "m²", AREAS, COMPR) == 26.54


def test_o_revestimento_com_layer_entre_aspas():
    obs = ("Fonte: área hachurada do layer '-TEPAR' = 268.39 m² (soma de 8 "
           "hachuras). Pode ser acabamento misto.")
    assert q(obs, "m²", AREAS, COMPR) == 268.39, (
        "layer entre aspas não foi reconhecido — é o formato que a IA usa na "
        "maior parte das linhas")


def test_o_comprimento_da_parede_nova():
    obs = "Fonte: comprimento do layer '-TEPAR' = 302.14 m. Inclui paredes novas."
    assert q(obs, "ml", AREAS, COMPR) == 302.14


def test_layer_que_NAO_EXISTE_na_extracao_continua_zerado():
    """🚨 A trava principal. Se o layer não está na extração, o número é da IA."""
    assert q("área hachurada do layer -INVENTADO = 99.90 m²", "m²", AREAS, COMPR) is None


def test_numero_que_NAO_CONFERE_continua_zerado():
    """🚨 A IA cita o layer certo e um valor errado — não entra.

    Sem isto, bastaria a IA escrever o nome de um layer real pra colar qualquer
    número na planilha.
    """
    assert q("área hachurada do layer -TEFOR = 500.00 m²", "m²", AREAS, COMPR) is None
    assert q("área hachurada do layer -TEFOR = 30.00 m²", "m²", AREAS, COMPR) is None


def test_tolerancia_de_1pct_aceita_o_arredondamento_da_IA():
    """26.54 impresso contra 26.5401 medido tem que passar; 10% não."""
    assert q("área hachurada do layer -TEFOR = 26.60 m²", "m²",
             {"-TEFOR": 26.54}, COMPR) == 26.60
    assert q("área hachurada do layer -TEFOR = 29.00 m²", "m²",
             {"-TEFOR": 26.54}, COMPR) is None


def test_unidade_trocada_nao_cola():
    """🪤 Área citada num item de metro linear (e vice-versa) não serve.

    O -TEPAR tem 268,39 m² de hachura E 302,14 m de comprimento. Cruzar os dois
    entregaria m² no lugar de metro.
    """
    obs_area = "área hachurada do layer '-TEPAR' = 268.39 m²"
    obs_comp = "comprimento do layer '-TEPAR' = 302.14 m"
    assert q(obs_area, "ml", AREAS, COMPR) is None, "área virou metro linear"
    assert q(obs_comp, "m²", AREAS, COMPR) is None, "comprimento virou área"
    # e cada um no seu lugar continua funcionando
    assert q(obs_area, "m²", AREAS, COMPR) == 268.39
    assert q(obs_comp, "ml", AREAS, COMPR) == 302.14


def test_layer_com_caixa_diferente_ainda_casa():
    """O nome do layer varia de caixa entre o CAD e o texto da IA."""
    assert q("área hachurada do layer -tefor = 26.54 m²", "m²", AREAS, COMPR) == 26.54


def test_observacao_sem_medicao_devolve_nada():
    """Controle negativo: a maioria dos zeros é HONESTA e tem que continuar zero.

    Dos 1.579 zerados, 92% são assim — "comprimento não extraído", "extração
    geométrica vazia". Transformar esses em número é o erro de 25/08.
    """
    for obs in ("Texto 'AE-10x15' identificado ×6 no layer -tetextos. "
                "Comprimento não extraído da geometria.",
                "Fonte: layer BARRAMENTO identificado no arquivo. Extração "
                "geométrica vazia — verificar em campo.",
                "Item de práxis: administração local de obra.",
                ""):
        assert q(obs, "m²", AREAS, COMPR) is None, (
            "inventou número numa linha honestamente zerada: %r" % obs)


def test_extracao_vazia_nao_quebra_nem_preenche():
    assert q("área hachurada do layer -TEFOR = 26.54 m²", "m²", {}, {}) is None
    assert q("área hachurada do layer -TEFOR = 26.54 m²", "m²", None, None) is None


def test_o_call_site_usa_isso_e_NAO_mexe_no_selo():
    """🪤 Guarda de CALL SITE + regra nº1 no mesmo teste.

    A função pode estar perfeita e nunca ser chamada; e se ela mexesse no
    `confidence`, viraria promoção por texto — que é exatamente o que a regra
    nº1 proíbe.
    """
    import io
    _b = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fonte = io.open(os.path.join(_b, "main.py"), encoding="utf-8").read()
    corpo = chr(10).join(l for l in fonte.split(chr(10))
                         if not l.strip().startswith("#"))
    assert "_quantidade_da_procedencia(" in corpo, (
        "a função existe e nunca é chamada no caminho da extração")
    i = corpo.find("_quantidade_da_procedencia(")
    janela = corpo[i:i + 420]
    assert "_areas_ly" in janela and "_compr_ly" in janela, (
        "chamada sem passar a extração — sem os dicionários ela não tem como "
        "conferir nada e viraria confiança no texto")
    assert "conf =" not in janela and "confidence" not in janela, (
        "o resgate está mexendo no selo — preencher quantidade e carimbar "
        "'medido' são passos diferentes (regra dura nº1)")
    assert "resgate_procedencia=" in corpo, (
        "o resgate não vira linha de log — conserto invisível é o defeito que "
        "custou o dia de hoje três vezes")
