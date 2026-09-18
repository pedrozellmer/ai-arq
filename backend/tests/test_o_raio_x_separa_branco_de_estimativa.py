# -*- coding: utf-8 -*-
"""O Raio-X chamava de "estimativa a confirmar" a linha que estava VAZIA.

🩸 18/09/2026. A tela "Planilha pronta!" mostrava duas caixas: medidos e
"a confirmar", esta última calculada como `total - medido`. Só que `total -
medido` junta duas populações que não se parecem em nada:

  · ESTIMATIVA — tem número, veio de leitura, e o cliente REVISA;
  · EM BRANCO  — não tem número nenhum, o desenho não deu, e o cliente
                 precisa IR MEDIR.

E o botão âmbar, o CTA principal da tela, dizia literalmente
"Confirmar as 30 estimativas agora" contando buraco como estimativa —
mandando o cliente conferir o que não existe.

📏 O tamanho, medido no acervo em 18/09 (projetos de cliente com DWG/DXF,
sem trial): das 1.112 linhas de área, **664 (59,7%) saem EM BRANCO** e apenas
104 (9,4%) são estimativa declarada. A caixa laranja estava seis vezes maior
do que aquilo que ela dizia ser.

🔑 O percentual mudou de denominador junto. "Medido" agora é medido sobre as
linhas QUE TÊM NÚMERO: linha em branco nunca foi candidata a ser medida, e
dividir por ela é se punir por uma pergunta honesta. Na mesma base a taxa vai
de 2,1% para 5,1% em área e de 20,6% para 52,9% em comprimento.

🚨 Estes guardas RODAM o JavaScript da tela (dukpy), não leem o fonte — porque
em 18/09 uma revisão adversarial provou que 19 guardas meus passavam verdes
sobre código morto por lerem AST em vez de executar a decisão.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _jsbancada import fonte_html, funcao_js, motor  # noqa: E402

_TELA = "dashboard.html"


def _regua():
    """A régua REAL da tela, carregada no motor JS."""
    js = motor("")
    js.evaljs(funcao_js("raioXDasLinhas", _TELA))
    return js


def _rx(js, itens):
    import json as _json
    js.evaljs("var __itens = %s;" % _json.dumps(itens, ensure_ascii=False))
    return _json.loads(js.evaljs("JSON.stringify(raioXDasLinhas(__itens))"))


def _itens(medidos, estimados_com_numero, em_branco):
    """Uma planilha com as três populações, do jeito que a API entrega."""
    fora = []
    for _ in range(medidos):
        fora.append({"confidence": "confirmado", "quantity": 12.5})
    for _ in range(estimados_com_numero):
        fora.append({"confidence": "estimado", "quantity": 7.0})
    for _ in range(em_branco):
        fora.append({"confidence": "estimado", "quantity": 0})
    return fora


# ══════════════════════════════════════════════════════════════════════════
#  O julgamento
# ══════════════════════════════════════════════════════════════════════════

def test_o_branco_NAO_e_contado_como_estimativa_a_confirmar():
    """O defeito exato de 18/09, com a proporção real do acervo de área."""
    js = _regua()
    rx = _rx(js, _itens(medidos=23, estimados_com_numero=104, em_branco=664))
    assert rx["aConfirmar"] == 104, (
        "a caixa 'a confirmar' voltou a engolir as linhas em branco: %r" % rx)
    assert rx["emBranco"] == 664
    assert rx["medido"] == 23
    assert rx["aConfirmar"] + rx["emBranco"] + rx["medido"] == rx["total"], (
        "as três caixas não fecham o total — alguma linha some ou conta 2×: %r" % rx)


def test_o_botao_nao_manda_CONFIRMAR_o_que_esta_vazio():
    """🪤 O pior efeito do defeito: o CTA pedia o passo errado."""
    js = _regua()
    so_branco = _rx(js, _itens(medidos=2, estimados_com_numero=0, em_branco=30))
    assert "onfirmar" not in so_branco["ctaLabel"], (
        "sem nenhuma estimativa, o botão ainda manda CONFIRMAR: %r"
        % so_branco["ctaLabel"])
    assert "30" in so_branco["ctaLabel"] and "reench" in so_branco["ctaLabel"], (
        "o botão devia mandar PREENCHER as 30 em branco: %r" % so_branco["ctaLabel"])

    so_estimativa = _rx(js, _itens(medidos=2, estimados_com_numero=5, em_branco=0))
    assert "onfirmar" in so_estimativa["ctaLabel"] and "5" in so_estimativa["ctaLabel"], (
        "com 5 estimativas de verdade o botão tem que mandar confirmar: %r"
        % so_estimativa["ctaLabel"])

    os_dois = _rx(js, _itens(medidos=1, estimados_com_numero=4, em_branco=9))
    assert "4" in os_dois["ctaLabel"] and "9" in os_dois["ctaLabel"], (
        "com os dois casos o botão tem que citar os DOIS números: %r"
        % os_dois["ctaLabel"])


def test_a_taxa_de_medicao_divide_pelo_que_TINHA_numero():
    """23 de 127 com número é 18%; 23 de 791 seria 3%. A diferença é a régua."""
    js = _regua()
    rx = _rx(js, _itens(medidos=23, estimados_com_numero=104, em_branco=664))
    assert rx["comNumero"] == 127
    assert "18%" in rx["frase"], (
        "a frase não traz a taxa sobre o que tem número: %r" % rx["frase"])
    assert "23 medido" in rx["frase"] and "664 em branco" in rx["frase"], (
        "a frase tem que dizer os três números crus, não só o percentual: %r"
        % rx["frase"])


def test_as_barras_somam_exatamente_100():
    """🪤 Três segmentos arredondados soltos deixam fio branco ou estouram a
    barra. O último absorve o resto — por isso o teste varre proporções feias."""
    js = _regua()
    for m, e, b in [(1, 1, 1), (23, 104, 664), (7, 0, 3), (0, 0, 5),
                    (1, 0, 0), (33, 33, 34), (2, 3, 7), (999, 1, 1)]:
        rx = _rx(js, _itens(m, e, b))
        soma = rx["pctMedido"] + rx["pctConfirmar"] + rx["pctBranco"]
        assert soma == 100, (
            "as barras somam %d%% em (%d medidos, %d estimados, %d brancos): %r"
            % (soma, m, e, b, rx))
        assert rx["pctBranco"] >= 0, "barra negativa em %r" % (rx,)


def test_planilha_toda_medida_nao_mostra_botao():
    """Controle de vizinhança: nada a fazer, nada a pedir."""
    js = _regua()
    rx = _rx(js, _itens(medidos=9, estimados_com_numero=0, em_branco=0))
    assert rx["temOQueFazer"] is False
    assert rx["ctaLabel"] == ""


def test_lista_vazia_nao_explode_nem_divide_por_zero():
    js = _regua()
    rx = _rx(js, [])
    assert rx["total"] == 0 and rx["medido"] == 0
    assert rx["pctMedido"] + rx["pctConfirmar"] + rx["pctBranco"] == 100
    assert "%" not in rx["frase"], (
        "sem linha nenhuma a frase não pode afirmar percentual: %r" % rx["frase"])


def test_item_nulo_na_lista_e_ignorado():
    """🪤 A API já entregou `null` no meio da lista — o filtro existia antes e
    tem que continuar existindo."""
    js = _regua()
    rx = _rx(js, [None, {"confidence": "confirmado", "quantity": 3}, None])
    assert rx["total"] == 1 and rx["medido"] == 1


def test_quantidade_NEGATIVA_ou_texto_conta_como_branco():
    """🪤 `Number('')` é 0 e `Number('abc')` é NaN; os dois têm que cair em
    branco, nunca virar estimativa com número."""
    js = _regua()
    rx = _rx(js, [{"confidence": "estimado", "quantity": ""},
                  {"confidence": "estimado", "quantity": "abc"},
                  {"confidence": "estimado", "quantity": -4}])
    assert rx["emBranco"] == 3, "quantidade inválida virou estimativa: %r" % rx
    assert rx["aConfirmar"] == 0


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLES — provar que este arquivo sabe REPROVAR
# ══════════════════════════════════════════════════════════════════════════

def test_CONTROLE_a_conta_ANTIGA_seria_reprovada():
    """`total - medido` é o que estava no ar. Com os números reais do acervo
    ele dá 768 'a confirmar' — 664 deles vazios."""
    js = _regua()
    rx = _rx(js, _itens(medidos=23, estimados_com_numero=104, em_branco=664))
    antiga = rx["total"] - rx["medido"]
    assert antiga == 768
    assert antiga != rx["aConfirmar"], (
        "a régua nova devolve o mesmo que a antiga — não separou nada")


def test_CONTROLE_a_regua_e_mesmo_a_DA_TELA():
    """🪤 Prova de que este guarda mede o arquivo publicado, e não uma cópia:
    o renderizador tem que CHAMAR a régua e usar o que ela devolve."""
    src = fonte_html(_TELA)
    corpo = funcao_js("renderDoneRaiox", _TELA, src)
    assert "raioXDasLinhas(" in corpo, (
        "renderDoneRaiox parou de chamar a régua — a tela e este teste "
        "passaram a medir coisas diferentes")
    for campo in ("rx.medido", "rx.aConfirmar", "rx.emBranco",
                  "rx.frase", "rx.ctaLabel", "rx.temOQueFazer"):
        assert campo in corpo, (
            "o renderizador descartou %s — a régua roda e a tela ignora" % campo)
    assert "total - medido" not in corpo, (
        "a conta antiga voltou pro renderizador")


def test_CONTROLE_os_elementos_existem_no_HTML():
    """🪤 Régua certa escrevendo em elemento que não existe é conserto que não
    chega à tela — e `getElementById` de id errado devolve null e explode."""
    src = fonte_html(_TELA)
    for ident in ("dn-rx-medido", "dn-rx-confirmar", "dn-rx-branco",
                  "dn-rx-bar-medido", "dn-rx-bar-confirmar", "dn-rx-bar-branco",
                  "dn-rx-pct", "dn-rx-cta-label"):
        assert ('id="%s"' % ident) in src, (
            "o elemento %s não existe no HTML da tela" % ident)


def test_CONTROLE_nenhuma_classe_do_cartao_e_INERTE():
    """🪤 `tailwind.min.css` é build ESTÁTICO: classe que não está nele não
    pinta nada — sem erro, sem aviso, sem cor. Já aconteceu nesta casa.

    🩸 A 1ª versão deste guarda conferia uma LISTA que eu mesmo escrevi
    ('grid-cols-3', 'bg-gray-400', …). A sabotagem D11 trocou `bg-gray-400`
    por `bg-gray-500` — que NÃO existe no CSS — e o guarda passou verde,
    porque `bg-gray-400` continuava na minha lista. Enumerar as formas de
    errar é jogo que o mutante ganha sempre.

    Agora o guarda lê as classes DO CARTÃO, no HTML publicado, e cobra cada
    uma. Medido antes de escrever: 67 classes distintas, **0 falso-positivo**.
    """
    import io
    import re
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    css = io.open(os.path.join(raiz, "tailwind.min.css"), encoding="utf-8").read()
    src = fonte_html(_TELA)

    ini, fim = src.find('id="dn-raiox"'), src.find('id="dn-rx-cta-sub"')
    assert 0 < ini < fim, "não achei o cartão do Raio-X no HTML"
    bloco = src[ini:fim]

    usadas = set()
    for m in re.finditer(r'class="([^"]*)"', bloco):
        usadas.update(m.group(1).split())
    assert len(usadas) > 40, (
        "só achei %d classes no cartão — o recorte do bloco quebrou e este "
        "guarda pararia de medir" % len(usadas))

    inertes = []
    for c in sorted(usadas):
        # o Tailwind escapa ponto, dois-pontos, barra e colchete no seletor
        esc = re.sub(r'([./:\[\]])', r'\\\1', c)
        if (".%s" % c) not in css and (".%s" % esc) not in css:
            inertes.append(c)
    assert not inertes, (
        "classe(s) do cartão que NÃO existem no CSS compilado — saem "
        "invisíveis na tela do cliente: %r" % inertes)
