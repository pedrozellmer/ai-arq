# -*- coding: utf-8 -*-
"""Aviso eficiente: cabe na tela do celular e diz algo antes de ser aberto.

Pedro, 24/08/2026: *"vamos revisar toda parte de email, sempre para termos
avisos eficientes e sem encher com bla bla bla a caixa do cliente"*.

A auditoria dos 17 e-mails achou três coisas que são ganho PURO — melhoram sem
tirar conteúdo nenhum:

1. **Preheader.** É a 2ª linha da caixa de entrada, antes de abrir. 10 dos 14
   não tinham; sem ele o Gmail preenche com o começo do HTML, que nesses
   e-mails é "AI.arq" (marca que já está no remetente), depois o badge, depois
   o título repetindo o assunto. Três pedaços de nada antes de qualquer
   informação.

2. **Assunto.** 7 passavam de 50 caracteres, que é perto de onde o celular
   corta. O pior tinha 80. E quando o nome do projeto fica no FIM, o que sobra
   na tela é justo a metade genérica.

3. **Texto alternativo da imagem.** O Gmail bloqueia imagem por padrão — então
   esse texto VIRA a primeira linha do e-mail. Cinco eram legenda de banco de
   imagem ("Edifício em construção", "Escritório de arquitetura moderno") e
   ainda ficavam ACIMA da saudação.

🚫 O que eu deliberadamente NÃO fiz: cortar palavra por cortar. O
`planilha_pronta` é o mais longo (337 palavras) e boa parte disso é o bloco
"Como lemos o seu projeto" — os avisos que passaram a chegar ao cliente em
24/08. Encurtar aquilo desfaria o conserto.
"""
import html as _hl
import io
import os
import re

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _main():
    return io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def _chamadas_wrap(src):
    """Cada chamada de _email_wrap com parênteses balanceados."""
    fora = []
    for m in re.finditer(r"_email_wrap\(", src):
        i = m.start()
        d, j = 0, i + len("_email_wrap")
        while j < len(src):
            if src[j] == "(":
                d += 1
            elif src[j] == ")":
                d -= 1
                if d == 0:
                    break
            j += 1
        c = src[i:j + 1]
        if "title: str" in c:      # é a definição da função, não uma chamada
            continue
        fora.append((i, c))
    return fora


def _assuntos(src):
    """Assuntos com o nome do projeto substituído por um real, pra medir o que
    o cliente vê de fato."""
    exemplo = "Projeto 24/08/2026"
    saida = []
    for m in re.finditer(r'subject\s*=\s*\(?\s*[fr]?"([^"]{6,140})"', src):
        a = m.group(1)
        for ph in ("{_pn_subj}", "{_pn_raw}", "{proj}", "{project_name}",
                   "{project_name or 'do seu projeto'}", "%s", "{semana}"):
            a = a.replace(ph, exemplo if ph != "{semana}" else "3")
        saida.append((m.group(1), a))
    return saida


# ══════════════════════════════════════════════════════════════════════════
#  🧪 Controles: o detector precisa enxergar o que diz enxergar
# ══════════════════════════════════════════════════════════════════════════
def test_controle_acha_as_chamadas_de_wrap():
    n = len(_chamadas_wrap(_main()))
    assert n >= 10, "só achei %d chamadas de _email_wrap — o parser quebrou" % n


def test_controle_nao_confunde_a_DEFINICAO_com_chamada():
    """A definição tem `title: str` na assinatura e não pode contar como e-mail."""
    for _, c in _chamadas_wrap(_main()):
        assert "title: str" not in c


def test_controle_acha_os_assuntos():
    n = len(_assuntos(_main()))
    assert n >= 10, "só achei %d assuntos — o parser quebrou" % n


# ══════════════════════════════════════════════════════════════════════════
#  1. Preheader em todos
# ══════════════════════════════════════════════════════════════════════════
def test_todo_email_tem_preheader():
    src = _main()
    sem = []
    for i, c in _chamadas_wrap(src):
        if "preheader" not in c:
            titulo = re.search(r'_email_wrap\(\s*[fr]?"([^"]{3,60})"', c)
            sem.append(titulo.group(1) if titulo
                       else "linha %d" % (src[:i].count(chr(10)) + 1))
    assert not sem, (
        "estes e-mails saem sem preheader — a 2ª linha da caixa de entrada fica "
        "com 'AI.arq' repetido em vez de informação: %s" % sem)


def test_o_preheader_nao_repete_o_titulo():
    """Preheader que repete o assunto é pior que nenhum: ocupa o espaço
    fingindo informar."""
    for _, c in _chamadas_wrap(_main()):
        t = re.search(r'_email_wrap\(\s*[fr]?"([^"]{3,60})"', c)
        p = re.search(r'preheader=\(?\s*[fr]?"([^"]{5,})"', c)
        if t and p:
            assert t.group(1).lower().strip(" ?!.") != p.group(1).lower().strip(" ?!."), (
                "preheader igual ao título: %s" % t.group(1))


# ══════════════════════════════════════════════════════════════════════════
#  2. Assunto que cabe na tela
# ══════════════════════════════════════════════════════════════════════════
_TETO_ASSUNTO = 52


def test_nenhum_assunto_estoura_a_tela_do_celular():
    longos = [(a, len(v)) for a, v in _assuntos(_main()) if len(v) > _TETO_ASSUNTO]
    assert not longos, (
        "assunto(s) acima de %d caracteres — o celular corta e o cliente lê pela "
        "metade: %s" % (_TETO_ASSUNTO, longos))


def test_quando_ha_nome_de_projeto_ele_vem_na_FRENTE():
    """Com o nome no fim, o corte do celular entrega só a parte genérica."""
    ruins = []
    for cru, _ in _assuntos(_main()):
        tem = any(p in cru for p in ("{_pn_subj}", "{_pn_raw}", "{proj}", "%s"))
        if tem and not cru.strip().startswith(("{", "%s")):
            ruins.append(cru)
    assert not ruins, "nome do projeto no fim do assunto: %s" % ruins


# ══════════════════════════════════════════════════════════════════════════
#  3. O texto alternativo é a 1ª linha quando a imagem é bloqueada
# ══════════════════════════════════════════════════════════════════════════
_LEGENDAS_DE_BANCO = ("edifício em construção", "escritório de arquitetura moderno",
                      "mesa de trabalho de arquitetura",
                      "interior de projeto de arquitetura")


def test_nenhum_alt_e_legenda_de_banco_de_imagem():
    src = _main()
    ruins = [alt for _, alt in re.findall(r'_email_img\(\s*"([^"]+)"\s*,\s*"([^"]+)"', src)
             if alt.strip().lower() in _LEGENDAS_DE_BANCO]
    assert not ruins, (
        "estes textos alternativos são legenda de banco de imagem e viram a "
        "PRIMEIRA linha do e-mail quando o Gmail bloqueia a foto: %s" % ruins)


def test_todo_alt_diz_alguma_coisa():
    """Controle mais largo que a lista: alt curtíssimo não sustenta a mensagem."""
    src = _main()
    curtos = [(arq, alt) for arq, alt in
              re.findall(r'_email_img\(\s*"([^"]+)"\s*,\s*"([^"]+)"', src)
              if len(alt.split()) < 5]
    assert not curtos, "texto alternativo curto demais pra dizer algo: %s" % curtos


# ══════════════════════════════════════════════════════════════════════════
#  🚫 O que NÃO pode ter sido perdido no corte
# ══════════════════════════════════════════════════════════════════════════
def test_o_diagnostico_de_leitura_continua_no_planilha_pronta():
    """🚨 O e-mail mais longo é o mais longo porque carrega os avisos que
    passaram a chegar ao cliente em 24/08. Encurtar isso seria desfazer."""
    src = _main()
    assert "Como lemos o seu projeto" in src
    assert "extra_body_html" in src


# ══════════════════════════════════════════════════════════════════════════
#  OS E-MAILS MONTADOS DE VERDADE
#
#  🚨 06/09/2026 — POR QUE MUDOU. Os dois guardas abaixo procuravam a frase no
#  FONTE de `main.py`. Provados cegos:
#    · o bloco do rodapé LGPD virou a variável `_lgpd` (com o texto intacto) e
#      logo depois `_lgpd = ""`: `_email_wrap('T','B')` passa a devolver HTML
#      SEM "Privacidade" e SEM "remover seus dados" — TODOS os e-mails saem
#      sem o rodapé da regra dura nº6 — e o guarda seguia verde porque as duas
#      strings continuavam escritas no arquivo.
#    · o div "Nosso compromisso: cada número diz de onde veio" embrulhado em
#      `("" if True else ...)`: some do e-mail de boas-vindas, string intacta
#      no fonte, guarda verde.
#  🔑 Agora as funções são CHAMADAS e o que se confere é o HTML renderizado.
# ══════════════════════════════════════════════════════════════════════════
import sys                                              # noqa: E402

sys.path.insert(0, _BACKEND)

import main                                             # noqa: E402

# 🚫 Regra dura nº6: nada de nome/e-mail de cliente de verdade na bancada.
_NOME = "cliente-NN"
_PROJ = "Projeto cliente-NN"
_JOB = "job-email-01"
_EMAIL = "cliente-nn@example.com"
_ANTES = {"itens": 10, "medidos": 4}
_DEPOIS = {"itens": 12, "medidos": 9}

# Todo montador de e-mail do produto, com um jogo de argumentos plausível.
# 🪤 Se nascer um `_build_..._email` novo e não entrar aqui, o guarda
# `test_a_lista_de_emails_cobre_TODOS_os_montadores` reprova.
_EMAILS = {
    "_build_calibracao_email": (_NOME, _PROJ, _JOB),
    "_build_cronograma_checkin_email": (_NOME, _PROJ, 3, _JOB),
    "_build_falha_email": (_NOME, _PROJ, True, "dxf ilegivel"),
    "_build_leitura_combinada_email": (_NOME, _PROJ, _JOB, _ANTES, _DEPOIS, ["aviso"]),
    "_build_leitura_nova_email": (_NOME, _PROJ, _JOB, _ANTES, _DEPOIS),
    "_build_leu_sem_medir_email": (_NOME, _PROJ, _JOB, 20, 12, "", _EMAIL),
    "_build_nps_relacional_email": (_NOME, _EMAIL, 2),
    "_build_nudge_email": (_NOME, "sem_projeto", "https://ai.arq.br/x"),
    "_build_planilha_pronta_email": (_NOME, _PROJ, _JOB, 20, "", _EMAIL),
    "_build_proximo_projeto_email": (_NOME, _PROJ),
    "_build_retorno30_email": (_NOME,),
    "_build_sem_medida_email": (_NOME, _PROJ, _JOB, 20, 20, "", _EMAIL),
    "_build_welcome_email": (_NOME,),
}


# 🪤 06/09 — UM jogo de argumentos por montador NÃO é um e-mail por montador.
# `_build_falha_email` carrega DOIS e-mails diferentes dentro dele
# (`reprocessavel` True/False) e o False ainda se abre em TRÊS diagnósticos.
# Com só o True na bancada, o e-mail de "precisamos de outro arquivo" — um dos
# mais enviados — podia perder o rodapé LGPD inteiro (regra dura nº6) com o
# guarda verde. Cada ramo aqui é um e-mail que chega na caixa de alguém.
_RAMOS = {
    "_build_falha_email": {
        "reprocessavel": (_NOME, _PROJ, True, "dxf ilegivel"),
        "dwg_nao_abre": (_NOME, _PROJ, False, "nao foi possivel abrir o DWG (convert)"),
        "arquivo_grande": (_NOME, _PROJ, False, "arquivo grande demais pro limite"),
        "sem_cotas": (_NOME, _PROJ, False, "sem cotas no desenho"),
    },
}


def _casos_de_email():
    """(id, nome, args) de TODO e-mail que o produto envia — um por RAMO, não
    um por função."""
    fora = []
    for nome in sorted(_EMAILS):
        for rotulo, args in sorted(_RAMOS.get(nome, {"": _EMAILS[nome]}).items()):
            fora.append(("%s[%s]" % (nome, rotulo) if rotulo else nome, nome, args))
    return fora


_CASOS = _casos_de_email()


def _html_de(nome, args):
    r = getattr(main, nome)(*args)
    return str(r[1] if isinstance(r, tuple) else r)


def _html_do_email(nome):
    """Monta o e-mail de verdade e devolve o HTML que sairia pro cliente."""
    return _html_de(nome, _EMAILS[nome])


def test_a_lista_de_emails_cobre_TODOS_os_montadores():
    """🪤 Guarda do guarda. Sem isto, um e-mail novo sem rodapé LGPD passaria
    despercebido — o teste de baixo só olha o que está na lista."""
    achados = {n for n in dir(main)
               if n.startswith("_build_") and n.endswith("_email")
               and callable(getattr(main, n))}
    faltando = achados - set(_EMAILS)
    assert not faltando, (
        "montador de e-mail fora da bancada do rodapé LGPD: %s" % (sorted(faltando),))


@pytest.mark.parametrize("rotulo,nome,args", _CASOS,
                         ids=[c[0] for c in _CASOS])
def test_o_rodape_de_privacidade_continua_em_todos(rotulo, nome, args):
    """Regra dura nº6, no HTML QUE SAI — não no fonte que o monta.

    🪤 "sai do _email_wrap, então basta ele estar em uso" era a justificativa
    do guarda antigo. Só que basta o rodapé virar string vazia dentro do
    próprio `_email_wrap` pra ele sumir de todos os 13 e-mails de uma vez, com
    o texto ainda escrito no arquivo.

    🪤 06/09 — e um montador não é um e-mail: os quatro ramos do
    `_build_falha_email` entram aqui um por um."""
    html = _html_de(nome, args)
    assert "Política de Privacidade" in html, (
        "%s foi montado SEM o link da Política de Privacidade — regra dura "
        "nº6" % (rotulo,))
    assert "Para remover seus dados" in html, (
        "%s foi montado SEM a saída de dados (LGPD): o cliente não tem como "
        "pedir remoção" % (rotulo,))


def test_CONTROLE_os_ramos_da_falha_sao_QUATRO_emails_diferentes():
    """🧪 Sem isto a parametrização acima seria enfeite: quatro linhas verdes
    montando o MESMO e-mail quatro vezes não cobrem ramo nenhum.

    O que separa os ramos é justamente o que o cliente lê primeiro — o assunto
    e o preheader (a linha da caixa de entrada)."""
    ramos = _RAMOS["_build_falha_email"]
    assinaturas = {}
    for rotulo, args in ramos.items():
        assunto, html = main._build_falha_email(*args)
        pre = re.search(r'mso-hide:all;">(.*?)(?:&zwnj;|</div>)', html, re.S)
        assert pre, "%s saiu sem preheader" % rotulo
        assinaturas[rotulo] = (assunto, pre.group(1).strip())
    assert len(set(assinaturas.values())) == len(ramos), (
        "ramos do e-mail de falha que chegam IGUAIS na caixa de entrada: %s"
        % (assinaturas,))
    # E o ramo que não tem reprocessamento não pode oferecer reprocessar.
    for rotulo in ("dwg_nao_abre", "arquivo_grande", "sem_cotas"):
        assert "não resolve" in assinaturas[rotulo][1], (
            "%s: o preheader promete o caminho errado — %r"
            % (rotulo, assinaturas[rotulo][1]))


def test_o_rodape_sai_do_proprio_email_wrap():
    """Fecha a porta na origem: qualquer e-mail futuro herda o rodapé daqui."""
    html = main._email_wrap("Assunto", "<p>corpo</p>")
    assert "Política de Privacidade" in html and "Para remover seus dados" in html, (
        "`_email_wrap` parou de escrever o rodapé LGPD — todos os e-mails do "
        "produto saem sem ele de uma vez só")


def test_CONTROLE_o_detector_do_rodape_sabe_REPROVAR(monkeypatch):
    """🧪 CONTROLE POSITIVO, do jeito que a mutação faria: apaga o rodapé
    DENTRO do `_email_wrap` (as strings continuam no fonte de `main.py`) e
    confere que os guardas de cima acusariam. É a prova de que eles não são
    tautologia."""
    _real = main._email_wrap

    def _sem_rodape(*a, **k):
        html = _real(*a, **k)
        i = html.find("Você está recebendo este e-mail")
        assert i > 0, "o rodapé mudou de forma — o controle precisa ser refeito"
        j = html.find("</div>", i)
        return html[:i] + html[j:]

    monkeypatch.setattr(main, "_email_wrap", _sem_rodape)
    html = _html_do_email("_build_welcome_email")
    assert "Política de Privacidade" not in html and "Para remover seus dados" not in html, (
        "o detector não enxerga a ausência do rodapé — os guardas de cima "
        "estariam passando por qualquer motivo")


def _codigo_dos_emails(src):
    """Só o código que MONTA e-mail.

    🪤 A 1ª versão deste guarda varria o arquivo inteiro e reprovou por causa do
    prompt do chat, que contém a frase justamente pra PROIBIR o robô de dizê-la:
    'NUNCA diga "1º projeto grátis"'. Guarda que não separa a proibição do uso
    ou dá alarme falso, ou me faz apagar a proibição pra calar o alarme —
    exatamente o contrário do que ele existe pra fazer."""
    pedacos = []
    for m in re.finditer(r"def (_build_\w*email\w*|_email_\w+)\(", src):
        i = m.start()
        nl = chr(10)
        fins = [x for x in (src.find(nl + "def ", i + 10),
                            src.find(nl + "@app.", i + 10)) if x > 0]
        pedacos.append(src[i:min(fins)] if fins else src[i:i + 9000])
    return nl.join(pedacos) if pedacos else ""


@pytest.mark.parametrize("proibido", ["1º projeto grátis", "primeiro projeto grátis",
                                      "primeiro é por nossa conta"])
def test_nenhum_email_promete_so_o_primeiro_gratis(proibido):
    """🚫 O beta é ilimitado. Esta promessa está errada desde 22/07."""
    assert proibido.lower() not in _codigo_dos_emails(_main()).lower()


def test_controle_o_recorte_dos_emails_nao_pegou_o_arquivo_inteiro():
    """Se o recorte falhar e devolver tudo, o teste acima vira alarme falso; se
    devolver vazio, vira enfeite que nunca reprova."""
    src = _main()
    rec = _codigo_dos_emails(src)
    assert 2000 < len(rec) < len(src) * 0.5
    assert "Bem-vindo" in rec, "o recorte perdeu os e-mails"
    assert "NUNCA diga" not in rec, "o recorte pegou o prompt do chat"


# ══════════════════════════════════════════════════════════════════════════
#  📏 O que cortar se decide MEDINDO, nao pelo tamanho
# ══════════════════════════════════════════════════════════════════════════
#
# 25/08. A auditoria apontou os 3 e-mails "mais longos" pra encurtar. Medindo
# cada um antes de cortar, o resultado foi o oposto do palpite:
#
#  • planilha_pronta (337 palavras): NAO cortar. As 296 palavras do bloco
#    "o que fazer agora" sao 4 acoes distintas, cada uma amarrada a uma
#    condicao real do projeto. Medido em 109 projetos: dispara 2,1 blocos em
#    media; so 2 projetos dispararam os 4. As 337 sao o PIOR caso, nao o normal.
#
#  • boas_vindas (276): cortar UM bloco — o comparativo de cotacoes. Ele foi
#    anunciado a 59 pessoas e project_supplier_quotes tem ZERO linhas. Nunca
#    foi usado uma vez. E e prematuro por tres passos: exige cotacao de
#    fornecedor pra um projeto que quem le ainda nao subiu.
#    Cronograma (9 usos) e memorial (1) ficam.
def test_o_boas_vindas_nao_anuncia_o_comparativo():
    """🚫 Zero usos em 59 anuncios. Cortar isso e cortar o que a medicao mostrou
    nao converter — nao e cortar porque estava longo."""
    from _corpo import corpo_de
    corpo = corpo_de("_build_welcome_email")
    assert "welcome-comparativo.png" not in corpo
    assert "Comparativo de cota" not in corpo


def test_mas_o_cronograma_e_o_memorial_CONTINUAM():
    """Controle negativo: a regra e 'cortar o que nao converte', nao 'cortar'.
    Cronograma tem 9 usos e memorial 1 — ficam."""
    from _corpo import corpo_de
    corpo = corpo_de("_build_welcome_email")
    assert "Cronograma f" in corpo
    assert "Memorial descritivo" in corpo


def test_o_planilha_pronta_NAO_foi_encurtado():
    """🚨 Guarda ao contrario: este e-mail e o mais longo E deve continuar. As
    296 palavras do 'o que fazer agora' sao 4 acoes distintas, e a media medida
    e de 2,1 blocos por projeto. Encurtar aqui tira orientacao de verdade."""
    src = _main()
    assert "_next_steps_html" in src
    from _corpo import corpo_de
    passos = corpo_de("_next_steps_html")
    for acao in ("complemente com o CAD", "sem quantidade",
                 "aviso de unidade", "em laranja"):
        assert acao in passos, "sumiu um caminho do 'o que fazer agora': %s" % acao


# ── O que o cliente LÊ, não o que está escrito no HTML ────────────────────
# 🪤 06/09 — este guarda conferia `"medido" in html and "estimativa" in html`
# no e-mail INTEIRO. As duas palavras existem em outros dois pontos do mesmo
# e-mail (a prosa "cada item dizendo se foi medido ou estimado" e o alt da
# imagem "itens medidos e estimativas rotuladas"), então dava pra apagar a
# REGRA de dentro da linha de honestidade — deixando só o slogan "cada número
# diz de onde veio" — e o guarda seguia verde. E qualquer truque que mantenha
# a string no HTML mas a esconda do leitor (comentário, display:none) também
# passava. Agora o que se lê é o BLOCO, e só o que fica visível nele.
_ESTILO_OCULTO = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|mso-hide\s*:\s*all"
    r"|font-size\s*:\s*0(?![.\d])", re.I)
_TAGS_DE_BLOCO = r"div|span|p|td|tr|table|section|a"


def _fim_do_elemento(h, pos, tag):
    """Índice logo depois do fechamento que casa com a abertura terminada em
    `pos` (aninhamento contado)."""
    padrao = re.compile(r"</?%s\b" % tag, re.I)
    profundidade = 1
    while profundidade:
        m = padrao.search(h, pos)
        if not m:
            return len(h)
        profundidade += -1 if h[m.start():m.start() + 2] == "</" else 1
        pos = m.end()
    j = h.find(">", pos)
    return len(h) if j < 0 else j + 1


def _sem_ocultos(h):
    """Tira o que o leitor não enxerga: bloco com display:none e companhia."""
    while True:
        for m in re.finditer(r"<(%s)\b[^>]*>" % _TAGS_DE_BLOCO, h, re.I):
            estilo = re.search(r'style\s*=\s*"([^"]*)"', m.group(0), re.I)
            if estilo and _ESTILO_OCULTO.search(estilo.group(1)):
                h = h[:m.start()] + " " + h[_fim_do_elemento(h, m.end(), m.group(1)):]
                break
        else:
            return h


def _texto_visivel(h):
    """O e-mail como chega nos olhos: sem comentário HTML, sem bloco
    escondido, sem tag, com as entidades resolvidas."""
    h = re.sub(r"<!--.*?-->", " ", h, flags=re.S)
    h = _sem_ocultos(h)
    h = re.sub(r"<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", _hl.unescape(h)).strip()


def _bloco_com(h, marca):
    """O <div> que contém `marca` — vazio se a marca só existe dentro de um
    comentário HTML (ou seja: se ela não está mais no e-mail)."""
    h = re.sub(r"<!--.*?-->", " ", h, flags=re.S)
    k = h.find(marca)
    if k < 0:
        return ""
    i = h.rfind("<div", 0, k)
    if i < 0:
        return ""
    return h[i:_fim_do_elemento(h, h.find(">", i) + 1, "div")]


def test_a_linha_de_honestidade_continua_no_primeiro_email():
    """A marca do produto é dizer de onde veio cada número. Isso vai no PRIMEIRO
    e-mail de propósito e não entra em corte nenhum.

    🪤 A versão antiga lia o CORPO da função no fonte. Embrulhar o div em
    `("" if True else ...)` tira a frase do e-mail e deixa o texto no arquivo:
    a assinatura da regra dura nº1 sumia do primeiro contato com o cliente e o
    guarda não acusava. Aqui o e-mail é montado — e lido."""
    html = _html_do_email("_build_welcome_email")
    lido = _texto_visivel(html)
    assert "Nosso compromisso" in lido, (
        "o e-mail de boas-vindas chegou SEM a linha de honestidade visível — a "
        "promessa da regra dura nº1 sumiu do primeiro contato com o cliente")

    linha = _texto_visivel(_bloco_com(html, "Nosso compromisso"))
    assert linha and linha in lido, (
        "o bloco da linha de honestidade está no HTML mas não chega ao leitor "
        "(escondido ou dentro de um bloco escondido): %r" % (linha[:120],))
    assert "de onde veio" in linha, (
        "a linha perdeu a promessa — sobrou o rótulo sem o compromisso")
    # A linha só vale se disser a REGRA, e a regra tem que estar NELA.
    # 🪤 "medido" e "estimativa" existem em outros pontos do mesmo e-mail: se a
    # conferência for no HTML inteiro, ela absolve a linha vazia de conteúdo.
    for palavra in ("medido", "estimativa"):
        assert palavra in linha, (
            "a linha de honestidade ficou sem %r — a distinção medido × "
            "estimativa É o conteúdo dela; sem isso é slogan, não "
            "compromisso. Linha lida: %r" % (palavra, linha))


def test_CONTROLE_o_leitor_de_texto_visivel_sabe_esconder():
    """🧪 Controle positivo do leitor: se `_texto_visivel` não enxergasse a
    diferença entre "está no HTML" e "o cliente lê", o guarda de cima voltaria
    a ser cego dos dois jeitos que ele existe pra pegar."""
    aberto = '<div style="color:#333">Nosso compromisso: medido e estimativa</div>'
    assert "compromisso" in _texto_visivel(aberto)
    assert "compromisso" not in _texto_visivel(
        '<div style="display:none;">%s</div>' % aberto), "display:none passou"
    assert "compromisso" not in _texto_visivel(
        "<!-- %s -->" % aberto), "comentário HTML passou"
    assert _bloco_com("<!-- %s -->" % aberto, "Nosso compromisso") == "", (
        "o recorte do bloco achou a frase dentro de um comentário")
    # E não pode comer o que é visível: o irmão de um bloco oculto continua.
    dois = '<div style="display:none;">some</div><div>fica aqui</div>'
    assert "fica aqui" in _texto_visivel(dois) and "some" not in _texto_visivel(dois)


def test_CONTROLE_a_linha_de_honestidade_sabe_sumir(monkeypatch):
    """🧪 Sem isto, o guarda acima poderia estar lendo qualquer HTML."""
    _real = main._email_wrap

    def _sem_compromisso(title, body_html, *a, **k):
        i = body_html.find("Nosso compromisso")
        assert i > 0, "a frase mudou de lugar — o controle precisa ser refeito"
        j = body_html.find("</div>", i)
        return _real(title, body_html[:i] + body_html[j:], *a, **k)

    monkeypatch.setattr(main, "_email_wrap", _sem_compromisso)
    html = _html_do_email("_build_welcome_email")
    assert "Nosso compromisso" not in html and "de onde veio" not in html
