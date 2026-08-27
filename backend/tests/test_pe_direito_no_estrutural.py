# -*- coding: utf-8 -*-
"""O pé-direito do cliente era jogado fora em projeto ESTRUTURAL.

🏗️ 27/08/2026. Puxando a família nº1 das correções de campo (itens de estrutura
preenchidos à mão), descobri que **o motor estrutural já acerta a parte difícil**.
No job da Cassia (`62c49fe6`) ele detectou 219 pilares e entregou:

    ✓ MEDIDO    Pilar de concreto 14×30 cm   171 un
    ✓ MEDIDO    Pilar de concreto 14×50 cm    37 un
    ⚠ estimado  Concreto em pilares        30,73 m³
                "soma(área_seção × qtd × h_ESTIMADA)"
    ⚠ estimado  Fôrma para pilares        622,8 m²
                "soma(perímetro_seção × qtd × h_ESTIMADA)"

Seção e contagem vêm da geometria — isso é o difícil, e funciona. **A ALTURA é a
única peça que falta.** E é justamente a que o cliente pode informar no upload.

🚨 O código descartava esse dado:

    if _pd_cli > 0 and not is_structural:      # ← o dado inteiro ia pro lixo

Não era só a diretiva de pintura que não servia (essa realmente não serve) — o
VALOR nem chegava ao prompt.

📊 O tamanho do buraco, medido em todos os projetos `project_type='estrutura'`:

    un   (contagem)   60 itens   37 medidos   62%
    kg   (aço)       142 itens    5 medidos    3,5%
    m³   (concreto)   55 itens    0 medidos    0%   ← nunca
    m²   (fôrma)      53 itens    0 medidos    0%   ← nunca

Não é falta de geometria. É falta de altura.

🚨 **Regra nº1 preservada:** altura INFORMADA não é altura MEDIDA. O item segue
`estimado` — o que muda é o número deixar de ser arbitrado e passar a ser o do
cliente, com a conta escrita na observação. Mesmo tratamento do
`user_total_area` ("informada por você, não medida").

📌 Escopo honesto: só **1 dos 15** projetos estruturais informou pé-direito até
hoje. O ganho imediato é pequeno; o que consertei foi a porta estar fechada.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_FONTE = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def _sem_comentarios(txt):
    """🪤 A 1ª versão destes testes lia o COMENTÁRIO junto com o código — e
    reprovava porque o meu próprio comentário explica por que a diretiva de
    pintura não serve aqui. Comentário não é instrução pro modelo."""
    return chr(10).join(l for l in txt.split(chr(10))
                        if not l.strip().startswith("#"))


def _ramo_estrutural():
    i = _FONTE.find("if _pd_cli > 0 and is_structural:")
    assert i > 0, "o ramo estrutural do pé-direito não existe"
    fim = _FONTE.find("elif _pd_cli > 0:", i)
    assert fim > i, "não achei o ramo de arquitetura depois do estrutural"
    return _FONTE[i:fim]


def test_o_pe_direito_NAO_e_mais_descartado_no_estrutural():
    """🚨 O conserto. `and not is_structural` mandava o dado pro lixo."""
    assert "if _pd_cli > 0 and not is_structural:" not in _FONTE, (
        "o pé-direito voltou a ser descartado em projeto estrutural")
    assert "if _pd_cli > 0 and is_structural:" in _FONTE


def test_ARQUITETURA_continua_funcionando():
    """🪤 O conserto não pode ter roubado o caminho que já funcionava — foi ele
    que resolveu o caso Giovani (pintura zerada com pé-direito informado)."""
    assert "elif _pd_cli > 0:" in _FONTE, (
        "o ramo de arquitetura sumiu — a pintura volta a sair zerada")
    i = _FONTE.find("elif _pd_cli > 0:")
    trecho = _FONTE[i:i + 1200]
    assert "pintura" in trecho.lower(), (
        "o ramo de arquitetura perdeu a diretiva de pintura")


def test_a_diretiva_estrutural_fala_de_PILAR_nao_de_pintura():
    """Cada modo tem a sua. Diretiva de pintura em prancha de estrutura é ruído
    que confunde o modelo."""
    t = _sem_comentarios(_ramo_estrutural())
    assert "volume de pilar" in t and "fôrma de pilar" in t, (
        "a diretiva estrutural não diz o que fazer com a altura")
    assert "pintura" not in t.lower(), (
        "a diretiva estrutural fala de pintura — texto do modo errado")


def test_a_diretiva_manda_manter_ESTIMADO():
    """🚨 REGRA DURA Nº1. Altura informada não vira medição. Se esta instrução
    sair, o motor pode carimbar volume de concreto como 'confirmado' — que é o
    erro mais caro que este produto sabe cometer."""
    t = _ramo_estrutural()
    assert "'estimado'" in t and "NUNCA 'confirmado'" in t, (
        "a diretiva não trava o selo — volume derivado de altura informada "
        "poderia sair como MEDIDO")


def test_a_diretiva_manda_a_PRANCHA_ganhar_do_cliente():
    """Se o desenho traz a altura em corte ou quadro, ela vale mais que o campo
    do upload — é medição contra informação."""
    t = _ramo_estrutural()
    assert "PREFIRA a da prancha" in t, (
        "a diretiva não resolve o conflito entre altura da prancha e altura "
        "informada")


def test_a_diretiva_manda_escrever_a_CONTA_na_observacao():
    """A coluna de origem da medição (pedido do Pedro em 24/08) só funciona se
    o item disser de onde veio o número."""
    t = _ramo_estrutural()
    assert "observação" in t and "informado por você" in t, (
        "o item não vai dizer que a altura foi informada — o cliente não tem "
        "como saber que aquele m³ depende de um dado que ELE deu")


def test_os_DOIS_ramos_sao_exclusivos():
    """🪤 `if`/`elif`, não dois `if`. Se os dois rodassem, o prompt levaria as
    duas diretivas e o modelo veria instrução contraditória."""
    i = _FONTE.find("if _pd_cli > 0 and is_structural:")
    j = _FONTE.find("elif _pd_cli > 0:", i)
    entre = _FONTE[i:j]
    assert entre.count("_pd_directive = (") == 1, (
        "o ramo estrutural monta a diretiva mais de uma vez")
    # 🪤 `'if _pd_cli > 0:'` é SUBSTRING de `'elif _pd_cli > 0:'` — a 1ª versão
    # deste teste reprovava o código certo. O que importa é a linha começar com
    # `elif`, não conter o texto.
    linha = _FONTE[j:_FONTE.find(chr(10), j)].strip()
    assert linha.startswith("elif "), (
        "o segundo ramo não é `elif` (%r) — os dois podem rodar juntos e o "
        "prompt levaria diretivas contraditórias" % linha)
