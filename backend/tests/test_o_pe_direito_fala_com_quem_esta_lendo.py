# -*- coding: utf-8 -*-
"""O campo do pé-direito falava só a língua da arquitetura.

🩸 18/09/2026. O pé-direito é o campo que mais muda a planilha e ganhou
destaque em 26/08 — mas a explicação inteira fala de PAREDE e PINTURA:

    "parede e pintura só fecham em m² com a altura"
    "Sem ele a parede sai só em metro corrido, e a pintura fica sem base"

Quem sobe projeto de ESTRUTURA não está pensando em pintura. Está pensando em
fôrma, concreto e aço — e é justamente ele que mais precisa da altura.

📏 Medido em 18/09, projetos de cliente concluídos:

    tipo          entregas   mediana de itens   sem NENHUMA medida
    arquitetura      129            43                51,2%
    ESTRUTURA         19            12                68,4%

    pé-direito informado: 1 de 19 em estrutura · 19 de 129 nos outros

🪤 A diferença 5,3% × 14,7% NÃO é afirmada em lugar nenhum — com n=19 ela cabe
no acaso, e hoje mesmo eu li uma amostra pequena como tendência e errei. O que
é FATO: em 18 de 19 entregas de estrutura o motor não tem a altura, e ele
próprio já nomeia a causa (`motor:estrutura-sem-medida`, `ramo=falta-altura`).

🚨 O TEXTO DE ESTRUTURA NÃO HERDA A PROPORÇÃO DA ARQUITETURA. "As linhas em
branco caem quase pela metade" foi medido numa base em que estrutura é 13% das
entregas; repetir isso na caixa de estrutura seria afirmar sobre estrutura uma
medição que não é dela — o mesmo defeito que o e-mail tinha hoje de manhã. O
texto novo diz o MECANISMO (seção × altura = m³ e m² de fôrma), que é verdade
por construção, e nenhum percentual.

🚨 Estes guardas RODAM o JavaScript da tela (dukpy), não leem o fonte.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _jsbancada import fonte_html, funcao_js, motor  # noqa: E402

_TELA = "dashboard.html"

#: percentuais que só valem para a base de arquitetura
_RE_PERCENTUAL = "%"


def _regua():
    js = motor("")
    js.evaljs(funcao_js("textoDoPeDireito", _TELA))
    return js


def _texto(js, tipo):
    import json as _json
    js.evaljs("var __t = %s;" % _json.dumps(tipo))
    return _json.loads(js.evaljs("JSON.stringify(textoDoPeDireito(__t))"))


# ══════════════════════════════════════════════════════════════════════════
#  O julgamento
# ══════════════════════════════════════════════════════════════════════════

def test_estrutura_fala_de_concreto_e_forma_nao_de_pintura():
    """O caso de 18/09: quem sobe estrutura lia sobre pintura."""
    js = _regua()
    t = _texto(js, "estrutura")
    junto = " ".join(t.values()).lower()
    assert "concreto" in junto and "fôrma" in junto, (
        "a caixa de estrutura não fala de concreto/fôrma: %r" % t)
    assert "pintura" not in junto, (
        "a caixa de ESTRUTURA continua falando de pintura: %r" % t)


def test_arquitetura_continua_como_estava():
    """🪤 Controle de vizinhança: o conserto não pode ter mexido no que já
    funcionava — o destaque de 26/08 é o campo mais eficaz da tela.

    🚨 O QUE ESTE GUARDA DEIXA PASSAR, DE PROPÓSITO: ele cobra os CONCEITOS no
    texto inteiro, não em qual parágrafo cada um aparece. A sabotagem P04
    (tirar "e a pintura fica sem base" do reforço) sobrevive, porque "pintura"
    segue no destaque e no mecanismo.

    Fica viva de propósito. Cobrir isso exigiria pinar a redação exata — e foi
    exatamente esse o defeito que este dia consertou em `02fe3d5`: um guarda
    que cobrava literalmente `"71%" in caixa` congelou a copy no dia em que foi
    escrito e segurou uma frase falsa no ar quando a realidade se moveu.
    Guarda de copy cobra o que precisa ser DITO, nunca as palavras exatas.
    """
    js = _regua()
    t = _texto(js, "arquitetura")
    junto = " ".join(t.values()).lower()
    for palavra in ("parede", "pintura", "metade"):
        assert palavra in junto, (
            "sumiu %r do texto de arquitetura: %r" % (palavra, t))


def test_o_texto_de_estrutura_NAO_afirma_percentual():
    """🚨 O defeito de hoje de manhã, pelo avesso.

    A proporção "caem quase pela metade" foi medida numa base em que estrutura
    é 13% das entregas. Repeti-la aqui seria vender sobre estrutura um número
    que não é de estrutura.
    """
    js = _regua()
    t = _texto(js, "estrutura")
    junto = " ".join(t.values())
    assert _RE_PERCENTUAL not in junto, (
        "a caixa de estrutura afirma percentual: %r" % t)
    assert "metade" not in junto.lower(), (
        "a caixa de estrutura herdou a proporção medida em arquitetura: %r" % t)


def test_os_dois_textos_prometem_ESTIMATIVA_e_nunca_medicao():
    """🚨 Regra dura nº1 dentro da copy: a altura é declaração do cliente."""
    js = _regua()
    for tipo in ("arquitetura", "estrutura"):
        junto = " ".join(_texto(js, tipo).values()).lower()
        assert "estimativa" in junto, (
            "o texto de %s não diz que entra como ESTIMATIVA: %r" % (tipo, junto[:200]))
        assert "nunca como medição" in junto, (
            "o texto de %s parou de dizer que NUNCA vira medição" % tipo)


def test_tipo_desconhecido_cai_no_texto_de_arquitetura():
    """🪤 Padrão seguro: tipo novo, vazio ou nulo não pode ficar sem texto."""
    js = _regua()
    for tipo in ("", "paisagismo", "ESTRUTURAL DE VERDADE"):
        t = _texto(js, tipo)
        assert t.get("destaque") and t.get("reforco") and t.get("mecanismo"), (
            "tipo %r ficou sem texto: %r" % (tipo, t))
    # "ESTRUTURAL DE VERDADE" contém 'estrut' → é estrutura, de propósito
    assert "concreto" in " ".join(_texto(js, "ESTRUTURAL DE VERDADE").values()).lower()
    assert "pintura" in " ".join(_texto(js, "paisagismo").values()).lower()


# ══════════════════════════════════════════════════════════════════════════
#  A costura: a régua tem que CHEGAR na tela
# ══════════════════════════════════════════════════════════════════════════

def test_a_tela_APLICA_a_regua_nos_elementos_certos():
    """🔑 Régua certa escrevendo em elemento que não existe é conserto que não
    chega ao cliente."""
    src = fonte_html(_TELA)
    aplica = funcao_js("aplicarTextoDoPeDireito", _TELA, src)
    assert "textoDoPeDireito(" in aplica, (
        "a aplicação parou de chamar a régua")
    for ident in ("pd-destaque", "pd-reforco", "pd-mecanismo"):
        assert ident in aplica, "a aplicação não escreve em %s" % ident
        assert ('id="%s"' % ident) in src, (
            "o elemento %s não existe no HTML da tela" % ident)


def test_trocar_o_tipo_DISPARA_a_troca_de_texto():
    """🪤 Sem o listener, a régua existe e nunca roda — código morto com
    guarda decorativo em cima, que é o erro que este dia inteiro me ensinou."""
    import re
    src = fonte_html(_TELA)
    # 🪤 A 1ª versão deste guarda pegava 400 caracteres a partir da DEFINIÇÃO da
    # função e reprovava porque a janela terminava logo antes do listener —
    # janela de tamanho escolhido a dedo mede o meu chute, não o fato.
    # Agora procura a LIGAÇÃO em si, onde quer que ela esteja no arquivo.
    ligacoes = re.findall(
        r"getElementById\(\s*['\"]project-type['\"]\s*\)[^;]{0,200}?"
        r"addEventListener\(\s*['\"]change['\"]\s*,\s*aplicarTextoDoPeDireito",
        src, re.S)
    assert ligacoes, (
        "sumiu a ligação que troca o texto ao mudar o tipo de projeto — a "
        "régua existiria sem nunca rodar, que é código morto com guarda "
        "decorativo em cima")


def test_CONTROLE_a_regua_devolve_coisas_DIFERENTES():
    """🧪 Prova que morde: se os dois tipos devolverem o mesmo, não separou nada."""
    js = _regua()
    assert _texto(js, "arquitetura") != _texto(js, "estrutura"), (
        "os dois tipos recebem o MESMO texto — a régua não separa nada")
