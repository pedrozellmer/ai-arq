# -*- coding: utf-8 -*-
"""O site diz quem está por trás dele — e o contrato diz quem presta o serviço.

🩸 06/09/2026 — o AI.arq era anônimo. Não havia CNPJ, razão social nem endereço
em lugar nenhum; o rodapé de 15 páginas dizia só "© 2026 ai.arq.br". As 13
menções a CNPJ nas páginas públicas eram todas sobre o CNPJ do CLIENTE.

Pior: **os Termos não nomeavam o prestador**. O contrato vinculava o usuário a
um serviço sem dizer quem o presta.

🔑 O erro de leitura que eu mesmo cometi e que a verificação corrigiu: achei que
isso só valia pra quem cobra. Não vale. O gatilho do art. 2º do Decreto
7.962/2013 é "sítios eletrônicos utilizados para OFERTA ou conclusão de contrato
de consumo" — oferta, não pagamento. O AI.arq já publica tabela de preço, já
vincula o usuário a ela nos Termos e já faz aceitar contrato de adesão no
cadastro. O dever já está ligado no beta gratuito; o que chega no dia da
cobrança é a consequência, não a obrigação.

🚫 SEM NÚMERO DE DOCUMENTO, de propósito. O Pedro é pessoa física e vai abrir
MEI. Publicar CPF integral trocaria um problema por outro (LGPD/fraude), e a
regra é não escrever número nenhum antes de ele existir. Quando o CNPJ sair,
entram razão social + CNPJ + endereço nos mesmos pontos.
"""
import glob
import io
import os
import re

_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.dirname(os.path.dirname(_AQUI))

_ASSINATURA = re.compile(r"Servi(ç|&ccedil;)o prestado por")
_RESPONSAVEL = "Pedro Zellmer"
_CONTATO = "contato@ai.arq.br"


def _paginas_com_rodape():
    """Toda página pública que já tem a linha de copyright — é onde a
    identificação tem que estar, 'em local de destaque'."""
    achadas = []
    alvos = (sorted(glob.glob(os.path.join(_RAIZ, "*.html")))
             + sorted(glob.glob(os.path.join(_RAIZ, "blog", "*.html")))
             + sorted(glob.glob(os.path.join(_RAIZ, "blog", "posts", "*.html"))))
    for f in alvos:
        txt = io.open(f, encoding="utf-8", errors="replace").read()
        if "Todos os direitos reservados" in txt:
            achadas.append((os.path.relpath(f, _RAIZ), txt))
    return achadas


def test_toda_pagina_com_rodape_identifica_quem_presta_o_servico():
    """🚨 Página nova nasce anônima se ninguém olhar. Este guarda é o que
    impede isso — e cobre o blog gerado junto, que é onde o esquecimento
    costuma morar."""
    paginas = _paginas_com_rodape()
    assert len(paginas) >= 15, (
        "a varredura achou só %d páginas com rodapé — o padrão de busca parou "
        "de enxergar" % len(paginas))
    sem = [nome for nome, txt in paginas if not _ASSINATURA.search(txt)]
    assert not sem, (
        "estas páginas têm rodapé mas não dizem quem presta o serviço: %s\n"
        "Se for página nova, acrescente a linha de identificação. Se for do "
        "blog, edite blog/generate.py e rode `python blog/generate.py`." % sem)


def test_a_identificacao_traz_nome_e_canal_de_contato():
    """Nome sozinho não identifica ninguém: o art. 2º pede também o endereço
    eletrônico. Confiro nas páginas de entrada, que são as que o cliente vê
    antes de decidir subir a planta do cliente DELE aqui."""
    for nome in ("index.html", "precos.html", "termos.html", "cadastro.html"):
        caminho = os.path.join(_RAIZ, nome)
        if not os.path.isfile(caminho):
            continue
        txt = io.open(caminho, encoding="utf-8", errors="replace").read()
        assert _RESPONSAVEL in txt, "%s não nomeia o responsável" % nome
        assert _CONTATO in txt, "%s não traz canal de contato" % nome


def test_os_TERMOS_nomeiam_o_prestador():
    """🚨 O buraco mais grave dos três: o contrato vinculava o usuário sem
    dizer quem era a contraparte."""
    txt = io.open(os.path.join(_RAIZ, "termos.html"), encoding="utf-8").read()
    # a seção 1 é onde a aceitação acontece — é lá que o prestador tem que estar
    i = txt.find("Aceita")
    assert i > 0, "não achei a seção de aceitação dos Termos"
    trecho = txt[i:i + 4000]
    assert _RESPONSAVEL in trecho, (
        "os Termos voltaram a vincular o usuário sem nomear quem presta o "
        "serviço")
    assert _CONTATO in trecho, "os Termos nomeiam o prestador mas não dizem como falar com ele"


def test_NAO_publicamos_numero_de_documento_que_ainda_nao_existe():
    """🚫 Guarda ao contrário: enquanto o MEI não existir, NENHUMA página pode
    publicar CNPJ. Um número inventado ou copiado de outro lugar é pior que a
    ausência — e CPF integral no rodapé troca um problema por outro."""
    padrao_cnpj = re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")
    padrao_cpf = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
    ruins = []
    for nome, txt in _paginas_com_rodape():
        # a máscara de input do documento DO CLIENTE usa zeros — não é publicação
        for m in list(padrao_cnpj.finditer(txt)) + list(padrao_cpf.finditer(txt)):
            if set(m.group(0)) <= set("0./-"):
                continue          # 00.000.000/0000-00 é placeholder
            ruins.append("%s: %s" % (nome, m.group(0)))
    assert not ruins, (
        "documento publicado no site: %s\nSe o MEI saiu, ótimo — atualize este "
        "guarda junto, com razão social e endereço. Se não saiu, o número não "
        "pode estar aí." % ruins)


def test_CONTROLE_a_varredura_ACHA_uma_pagina_anonima():
    """O guarda principal só vale se souber acusar. Aqui provo que uma página
    com rodapé e sem identificação é pega."""
    falsa = "<footer>&copy; 2026 ai.arq.br · Todos os direitos reservados</footer>"
    assert "Todos os direitos reservados" in falsa
    assert not _ASSINATURA.search(falsa), (
        "a peneira parou de distinguir rodapé identificado de rodapé anônimo")


def test_CONTROLE_a_varredura_APROVA_o_rodape_novo():
    """E o outro lado, nas duas grafias que o site usa (· literal e &middot;)."""
    for meio in ("·", "&middot;"):
        boa = ("&copy; 2026 ai.arq.br %s Todos os direitos reservados<br>"
               "Serviço prestado por <strong>Pedro Zellmer</strong> %s "
               "Rio de Janeiro/RJ %s contato@ai.arq.br" % (meio, meio, meio))
        assert _ASSINATURA.search(boa), boa


def test_o_blog_e_gerado_do_TEMPLATE_e_nao_na_mao():
    """🪤 São 31 posts. Editar um a um é garantia de esquecer alguns e de o
    próximo post nascer sem a linha. O template é a fonte."""
    gen = io.open(os.path.join(_RAIZ, "blog", "generate.py"), encoding="utf-8").read()
    assert _ASSINATURA.search(gen), (
        "o template do blog perdeu a identificação — todo post novo nasceria "
        "anônimo")
