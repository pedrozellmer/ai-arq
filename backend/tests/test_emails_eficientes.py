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


def test_o_rodape_de_privacidade_continua_em_todos():
    """Regra dura nº6 — sai do _email_wrap, então basta ele estar em uso."""
    src = _main()
    assert "Política de Privacidade" in src
    assert "Para remover seus dados" in src


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


def test_a_linha_de_honestidade_continua_no_primeiro_email():
    """A marca do produto e dizer de onde veio cada numero. Isso vai no PRIMEIRO
    e-mail de proposito e nao entra em corte nenhum."""
    from _corpo import corpo_de
    corpo = corpo_de("_build_welcome_email")
    assert "cada n" in corpo and "de onde veio" in corpo
