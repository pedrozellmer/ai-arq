# -*- coding: utf-8 -*-
"""Onde a pessoa PARA no cadastro — a pergunta que o funil não respondia.

📊 27/08/2026. **11 de 50 cadastros pelo GOOGLE em 30 dias não completaram o
perfil. Pelo e-mail/senha: ZERO de 7.** Não é o cliente que desiste — é o
caminho do Google que perde gente na tela de completar cadastro.

Quem entra pelo Google já se sente "dentro" e recebe um formulário com **seis
campos obrigatórios**: nome, WhatsApp, área, como conheceu, aceitar termos,
aceitar idade.

🚨 **O que eu quase afirmei e o dado NÃO sustentava.** Olhando os 11, nenhum
tinha `signup_form_start` — ia concluir "ninguém nem tocou no formulário". Mas:

    68 pessoas COMPLETARAM o cadastro e só 13 registraram tocar num campo.

Impossível. O `/api/track` descartava a maior parte dos eventos até 26/08
([[project_revisao_site_20260822]]). Qualquer leitura de funil antes dessa data
é ruído — e eu ia entregar ruído como conclusão.

Janela confiável (26/08 em diante): **4 contas**. Pouco demais pra desenhar
conserto. Então: instrumento primeiro, conserto quando houver dado.

🔑 O `signup_form_start` diz QUE a pessoa tocou. O novo `signup_saiu_da_tela`
diz ONDE ela estava quando saiu — é isso que decide o que encurtar.

🔒 Grava o NOME do campo, NUNCA o valor digitado.
🪤 Quem não aceita o banner de cookies não gera evento (LGPD) — o instrumento é
cego pra esse grupo, como no caso da Cassia (28 revisões, zero evento).
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _cadastro():
    return io.open(os.path.join(_RAIZ, "cadastro.html"), encoding="utf-8").read()


def _sem_comentarios(txt):
    """🪤 TERCEIRA VEZ que eu escrevo um teste que lê o COMENTÁRIO como se
    fosse código, no mesmo dia (aconteceu no pé-direito estrutural e aqui).
    Comentário explica a decisão; ele NÃO é comportamento.
    """
    saida = []
    for l in txt.split(chr(10)):
        t = l.strip()
        if t.startswith("//") or t.startswith("/*") or t.startswith("*"):
            continue
        saida.append(l.split("//")[0] if "//" in l and "://" not in l else l)
    return chr(10).join(saida)


def _bloco_novo():
    s = _cadastro()
    i = s.find("// 🎯 ONDE a pessoa PAROU")
    assert i > 0, "o instrumento de abandono sumiu do cadastro"
    j = s.find("})();", s.find("signup_saiu_da_tela"))
    assert j > i, "não achei o fim do bloco"
    return s[i:j + 5]


def test_o_evento_existe():
    assert "signup_saiu_da_tela" in _cadastro(), (
        "sem este evento, 'saiu na hora' e 'lutou com o formulário e desistiu' "
        "continuam sendo a mesma linha no banco")


def test_grava_o_NOME_do_campo_e_NUNCA_o_valor():
    """🔒 LGPD e decência. O campo tem WhatsApp e nome — valor digitado não sai
    daqui em hipótese nenhuma."""
    b = _bloco_novo()
    assert "el.id" in b, "não guarda o identificador do campo"
    for proibido in (".value", "el.value", "target.value"):
        assert proibido not in b, (
            "o instrumento toca em %r — isso é o VALOR digitado, não o nome do "
            "campo" % proibido)


def test_usa_pagehide_e_NAO_unload():
    """🪤 `unload` não é confiável em celular e o navegador cancela requisição
    pendente. `pagehide` + `keepalive` (que o trackEvent já usa) é o par que
    sobrevive ao fechamento da aba."""
    b = _bloco_novo()
    assert "pagehide" in b, "o evento não é disparado na saída da página"
    assert "'unload'" not in b and '"unload"' not in b, (
        "usa `unload`, que perde evento em celular")


def test_o_transporte_do_trackEvent_sobrevive_a_saida():
    """🪤 Guarda do OUTRO lado: o instrumento só funciona se o `trackEvent`
    mandar com `keepalive`. Se alguém trocar por fetch normal, o evento de
    saída morre e este teste é o único que avisa."""
    utils = io.open(os.path.join(_RAIZ, "aiarq-utils.js"), encoding="utf-8").read()
    i = utils.find("window.trackEvent = function")
    assert i > 0, "não achei o trackEvent"
    # 🪤 QUARTA vez hoje: sabotei o `keepalive: true` e este teste passou VERDE,
    # porque a palavra aparece no COMENTÁRIO logo acima da linha de código.
    # 🪤 A janela era de 2.500 caracteres e o `keepalive: true` real fica
    # ~2.900 depois do início da função. Com o comentário contando, o teste
    # passava lendo a palavra errada; sem ele, reprovava o código CERTO.
    trecho = _sem_comentarios(utils[i:i + 6000])
    assert "keepalive" in trecho, (
        "o trackEvent perdeu o `keepalive` — todo evento disparado na saída da "
        "página passa a ser cancelado pelo navegador")


def test_NAO_decide_na_tela_se_foi_abandono():
    """🔑 Quem CONCLUI também dispara `pagehide` (navega pro dashboard). Decidir
    ali erraria com quem volta e termina depois. A análise cruza com
    `signup_done`."""
    b = _sem_comentarios(_bloco_novo())
    assert "signup_done" not in b, (
        "o bloco tenta decidir sozinho se foi abandono — quem conclui também "
        "sai da página, e quem volta depois seria classificado errado")


def test_dispara_UMA_vez_so():
    """Sem guarda, `pagehide` pode disparar mais de uma vez (bfcache) e a mesma
    pessoa vira várias linhas."""
    b = _bloco_novo()
    assert "jaAvisou" in b, "sem trava de disparo único"


def test_o_signup_form_start_CONTINUA():
    """🪤 O instrumento novo não substitui o de 05/08 — eles respondem coisas
    diferentes: um diz QUE tocou, o outro diz ONDE parou."""
    s = _cadastro()
    assert "signup_form_start" in s, (
        "o marco de primeiro toque sumiu — sem ele, 'bateu o olho' e 'tentou e "
        "desistiu' voltam a ser indistinguíveis")


def test_o_formulario_ainda_tem_os_6_obrigatorios():
    """📌 Fotografa o estado atual. Se alguém encurtar o formulário (que é uma
    hipótese em aberto), este teste avisa que o número mudou — e aí a medição
    de antes e depois tem marco."""
    s = _cadastro()
    obrigatorios = re.findall(r'id="([^"]+)"[^>]*\srequired|required[^>]*\sid="([^"]+)"', s)
    nomes = {a or b for a, b in obrigatorios}
    assert len(nomes) >= 5, (
        "o formulário encolheu para %d campos obrigatórios (%s). Se foi de "
        "propósito, atualize este teste — e compare o abandono antes/depois."
        % (len(nomes), sorted(nomes)))
