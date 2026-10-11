# -*- coding: utf-8 -*-
"""No celular o aviso de cookies mostra a frase curta; o texto completo fica a um toque.

📱 11/10/2026 — medido no site no ar, sem consentimento gravado: em 375×812 o aviso tinha ~263 px (um terço da
tela) e ficava em cima do botão principal da home; o toque no meio do botão caía no aviso. Com a frase curta
(aprovada pelo Pedro) ele fica em ~190 px. No computador nada muda.

O que não pode se perder na versão curta, porque é o que o parecer jurídico de 28/09 pediu que o aviso diga:
o que roda SEM o sim (essenciais e a contagem sem cookie) e que o sim alcança as páginas abertas antes da
resposta. E o texto completo tem de continuar existindo, inteiro, pra quem pedir.
"""
import io
import os
import re

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _fonte():
    return io.open(os.path.join(_RAIZ, "cookie-consent.js"), encoding="utf-8").read()


def _trecho(fonte, classe):
    """O texto que o aviso escreve dentro de <span class="classe">, sem as aspas e vírgulas do JS."""
    m = re.search(r"'<span class=\"%s\">',(.*?)'</span>'," % classe, fonte, re.S)
    assert m, "o aviso não tem mais o bloco %s" % classe
    linhas = [l.strip() for l in m.group(1).splitlines() if l.strip() and not l.strip().startswith("//")]
    return " ".join(re.sub(r"^'|',?$", "", l) for l in linhas)


def _o_que_falta_na_curta(curta):
    faltas = []
    if "essenciais" not in curta:
        faltas.append("os cookies essenciais")
    if "contagem de visitas sem cookie" not in curta:
        faltas.append("a contagem sem cookie")
    if "Com seu sim" not in curta or "telemetria de uso" not in curta:
        faltas.append("o que o sim autoriza")
    if "antes de responder" not in curta:
        faltas.append("o alcance do sim sobre as páginas abertas antes")
    return faltas


def test_a_frase_curta_diz_o_que_roda_sem_o_sim_e_o_alcance_do_sim():
    assert _o_que_falta_na_curta(_trecho(_fonte(), "aiarq-cc-curto")) == []


def test_CONTROLE_frase_curta_sem_o_alcance_reprova():
    sem = "Usamos cookies <strong>essenciais</strong> e uma contagem de visitas sem cookie. Com seu sim, coletamos <strong>telemetria de uso</strong>."
    assert _o_que_falta_na_curta(sem) == ["o alcance do sim sobre as páginas abertas antes"]


def test_o_texto_completo_continua_inteiro():
    longa = _trecho(_fonte(), "aiarq-cc-longo")
    for pedaco in ("(sessão e proteção contra robôs)", "contagem de visitas sem cookie, que não identifica você",
                   "sem seu nome nas páginas públicas", "vinculada à sua conta quando você está logado",
                   "incluindo as páginas que você abriu antes de responder"):
        assert pedaco in longa, pedaco


def _visivel(html):
    """O que a pessoa lê: sem as marcas (o "Saber mais" é um botão com estilo embutido, e conta só o rótulo)."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html)).strip()


def test_a_curta_e_menor_que_a_completa():
    f = _fonte()
    curta, longa = _visivel(_trecho(f, "aiarq-cc-curto")), _visivel(_trecho(f, "aiarq-cc-longo"))
    assert curta.endswith("Saber mais ·"), curta[-40:]
    assert len(curta) < 0.6 * len(longa), (len(curta), len(longa))


def test_no_computador_so_aparece_o_texto_completo():
    """Fora da regra de tela estreita, a curta nasce escondida e nada esconde a completa."""
    f = _fonte()
    assert "'#aiarq-cookie-consent .aiarq-cc-curto { display: none; }'," in f
    antes_da_regra = f[:f.index("@media (max-width: 640px)")]
    assert ".aiarq-cc-longo { display: none" not in antes_da_regra


def test_no_celular_a_curta_aparece_ate_a_pessoa_pedir_a_completa():
    f = _fonte()
    i = f.index("@media (max-width: 640px)")
    regra = f[i:f.index("].join", i)]
    assert "#aiarq-cookie-consent:not(.aiarq-cc-aberto) .aiarq-cc-longo { display: none; }" in regra
    assert "#aiarq-cookie-consent:not(.aiarq-cc-aberto) .aiarq-cc-curto { display: inline; }" in regra
    # o "Saber mais" é um botão de verdade (alcançável por teclado) e é ele que abre o texto completo
    assert '<button type="button" id="aiarq-cc-mais"' in f
    j = f.index("getElementById('aiarq-cc-mais')")
    assert "classList.add('aiarq-cc-aberto')" in f[j:j + 260]


def test_os_tres_botoes_de_escolha_continuam_no_aviso_curto():
    """Encurtar o texto não pode custar uma das escolhas — recusar tem de continuar tão fácil quanto aceitar."""
    f = _fonte()
    i = f.index("function renderModeSimples()")
    simples = f[i:f.index("function renderModePersonalizar()")]
    for rotulo in ("btn('Personalizar'", "btn('Só essenciais'", "btn('Aceitar todos'"):
        assert rotulo in simples, rotulo
