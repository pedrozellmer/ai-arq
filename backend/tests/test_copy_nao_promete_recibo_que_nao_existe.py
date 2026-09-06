# -*- coding: utf-8 -*-
"""O site não promete recibo enquanto recibo não existir.

🩸 06/09/2026 — o site pedia CPF/CNPJ dizendo, em cinco lugares, que era "pra
emitir o recibo da transação". Não existe recibo em lugar nenhum do produto:
nenhuma rota, nenhum template, nenhuma tabela. O CPF nem sequer é enviado ao
Stripe (a sessão de checkout não leva `customer_email`, `receipt_email` nem o
documento no metadata).

O tamanho disso, medido no banco: 64 dos 101 perfis têm CPF/CNPJ guardado, e
**54 preencheram DEPOIS de o campo virar opcional** — o mais recente dois dias
antes deste conserto. São 54 pessoas que entregaram documento voluntariamente
acreditando numa finalidade que não se cumpria.

Isso é a regra nº6 (LGPD) na prática: dado coletado com finalidade declarada
que não se realiza. E é o tipo de defeito que ninguém reclama — a pessoa só
descobre se for pedir o recibo.

🔑 O invariante: a copy pode dizer que o CPF SERÁ usado quando a cobrança
começar (é verdade e é o motivo de o campo existir). NÃO pode dizer que já
serve pra emitir recibo, enquanto emissão de recibo não for código.
"""
import glob
import io
import os
import re

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
_RAIZ = os.path.dirname(_BACKEND)

# Onde a promessa vivia. Se ela voltar, volta por aqui.
_PAGINAS = ["faq.html", "privacidade.html", "termos.html", "precos.html",
            "dashboard.html", "index.html", "cadastro.html"]

# 🪤 A mesma frase aparece em três formas no faq.html — JSON-LD, HTML visível e
# o `data-keywords` da busca. Corrigir uma e esquecer as outras deixa o rich
# result do Google servindo a promessa antiga. Por isso o guarda varre o
# arquivo inteiro, não um bloco.
_PROMETE_RECIBO = re.compile(
    r"(pro|para|pra)\s+(o\s+)?recibo"
    r"|emitir\s+o\s+recibo"
    r"|emiss(ã|&atilde;)o\s+do\s+recibo",
    re.I)


def _existe_emissao_de_recibo() -> bool:
    """O FATO que autoriza a promessa: existe emissão de recibo no backend?

    Procura o que um recibo de verdade exigiria: o Stripe mandando o
    comprovante (receipt_email / invoice_creation) ou rota/tabela nossa.
    """
    for arq in glob.glob(os.path.join(_BACKEND, "*.py")):
        txt = io.open(arq, encoding="utf-8", errors="replace").read()
        if "receipt_email" in txt or "invoice_creation" in txt:
            return True
        if re.search(r"def .*recibo|/api/recibo|\"recibos\"", txt):
            return True
    return False


def test_a_copy_NAO_promete_recibo_enquanto_recibo_nao_existe():
    """Guarda de FATO, não de gosto: se o backend passar a emitir recibo, a
    promessa volta a ser verdadeira e este teste para de reclamar sozinho."""
    if _existe_emissao_de_recibo():
        return  # a promessa passou a ser verdade — nada a guardar
    achados = []
    for nome in _PAGINAS:
        caminho = os.path.join(_RAIZ, nome)
        if not os.path.isfile(caminho):
            continue
        txt = io.open(caminho, encoding="utf-8", errors="replace").read()
        for m in _PROMETE_RECIBO.finditer(txt):
            linha = txt[:m.start()].count(chr(10)) + 1
            achados.append("%s:%d" % (nome, linha))
    assert not achados, (
        "estas páginas prometem recibo, e o backend não emite recibo nenhum "
        "(sem receipt_email, sem invoice_creation, sem rota): %s\n"
        "A copy pode dizer que o CPF SERÁ usado quando a cobrança começar. "
        "Não pode dizer que já serve pra emitir recibo." % achados)


def test_CONTROLE_o_padrao_ACHA_a_frase_que_existia():
    """O guarda acima só vale se souber acusar. Aqui rodo o padrão contra as
    cinco frases reais que estavam no ar até hoje."""
    reais = [
        "CPF/CNPJ é pedido só antes do 1º pagamento — precisamos pra emitir o recibo da transação.",
        "(CPF/CNPJ só antes do 1º pagamento, pro recibo — no beta o uso é grátis, sem CPF)",
        "(coletado apenas antes do primeiro pagamento, para emiss&atilde;o do recibo)",
        "Pra emitir o recibo do pagamento, a gente precisa do seu CPF ou CNPJ.",
        "precisamos pra emitir o recibo da transa&ccedil;&atilde;o",
    ]
    for frase in reais:
        assert _PROMETE_RECIBO.search(frase), (
            "o padrão parou de reconhecer uma das frases que existiam: %r" % frase)


def test_CONTROLE_o_padrao_NAO_acusa_a_redacao_nova():
    """E o outro lado: o texto honesto que entrou no lugar não pode ser
    acusado — guarda que reprova o conserto certo acaba desligado."""
    novas = [
        "Ele existe pro dia em que a cobrança começar: aí vamos precisar dele pra "
        "identificar quem pagou no documento fiscal.",
        "(CPF/CNPJ é opcional e só será usado quando a cobrança começar)",
        "Pra identificar quem pagou no documento fiscal, a gente precisa do seu CPF ou CNPJ.",
    ]
    for frase in novas:
        assert not _PROMETE_RECIBO.search(frase), (
            "o padrão acusou a redação NOVA, que é honesta: %r" % frase)


def test_o_gatilho_do_guarda_reconhece_a_emissao_de_recibo():
    """Prova que o `if` de cima não é decorativo: se um dia o código emitir
    recibo, o detector precisa ver."""
    assert not _existe_emissao_de_recibo(), (
        "o backend passou a emitir recibo — ótimo. Reveja a copy: agora ela "
        "PODE prometer, e este guarda deixou de reclamar")


def test_a_pagina_ainda_explica_POR_QUE_pede_o_documento():
    """🪤 Consertar apagando seria pior: o campo continuaria lá, sem explicação
    nenhuma. A copy tem que dizer pra que serve — só que a verdade."""
    txt = io.open(os.path.join(_RAIZ, "faq.html"), encoding="utf-8").read()
    assert "documento fiscal" in txt, (
        "a explicação de por que o CPF é pedido sumiu junto com a promessa "
        "falsa — o cliente ficou sem saber pra que serve o campo")
    assert re.search(r"n(ã|&atilde;)o (é|&eacute;) usado", txt), (
        "a página deixou de dizer que, no beta, o documento não é usado — que "
        "é justamente o que torna a coleta honesta")
