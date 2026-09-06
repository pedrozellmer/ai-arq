# -*- coding: utf-8 -*-
"""Clicar num botão do admin e nada acontecer não pode ser indistinguível de bug.

🩸 04/09/2026, comigo, neste painel. Cliquei em "↻ Refazer planilha" no projeto
da cliente-22. O `confirm()` foi descartado pela automação, a função saiu pela
porta dos fundos (`if (!confirm(...)) return;`) e **nada aconteceu — sem toast,
sem erro, sem linha no log**. Só descobri indo consultar o `error_log` e ver
que a ação não tinha sido registrada.

🔑 Pra quem clica em Cancelar de propósito, sumir em silêncio está certo. O
problema é que "eu cancelei" e "o botão está quebrado" ficam **idênticos na
tela** — e o painel tem DEZ ações assim, várias delas destrutivas ou que
gastam o reprocesso grátis do cliente.

É a família da "gravação que falha calada", agora no admin: ação sem
consequência visível é ação que ninguém sabe se aconteceu.

🪤 Este arquivo NÃO cobra que exista confirmação — disso já cuidam
`test_botoes_reprocessar` e `test_admin_refaz_planilha_entregue`. Aqui a
cobrança é só sobre o que acontece quando a resposta é NÃO.
"""
import io
import os
import re

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ADMIN = io.open(os.path.join(_RAIZ, "admin.html"), encoding="utf-8").read()

# O invólucro, isolado do resto do arquivo.
_RE_HELPER = re.compile(
    r"function\s+_confirmaOuAvisa\s*\([^)]*\)\s*\{(.*?)\n\}", re.S)


def _corpo_do_helper():
    m = _RE_HELPER.search(_ADMIN)
    assert m, ("sumiu `_confirmaOuAvisa` do admin.html — as dez ações voltam a "
               "recusar em silêncio")
    return m.group(1)


def test_o_helper_existe_e_AVISA_quando_a_resposta_e_nao():
    corpo = _corpo_do_helper()
    assert "confirm(" in corpo, "o invólucro parou de perguntar"
    assert "_adminToast(" in corpo, (
        "🩸 O invólucro voltou a recusar CALADO — que é exatamente o defeito "
        "que ele nasceu pra tapar: clique sem consequência visível fica igual "
        "a botão quebrado")
    assert "return false" in corpo


def test_o_aviso_diz_que_NADA_foi_feito():
    """Um toast genérico não resolve: ele tem que dizer que nada aconteceu,
    senão o cliente do painel fica na dúvida se rodou pela metade."""
    corpo = _corpo_do_helper()
    assert "nada foi feito" in corpo.lower(), (
        "o aviso da recusa parou de dizer que NADA foi feito")


def test_nenhuma_acao_do_painel_recusa_em_silencio():
    """🚨 As dez. Se uma escapar, ela é a que vai confundir alguém."""
    cruas = re.findall(r"if\s*\(\s*!\s*confirm\s*\(", _ADMIN)
    assert not cruas, (
        "%d ação(ões) do painel voltaram a chamar `confirm` direto e somem em "
        "silêncio quando a resposta é não" % len(cruas))
    pelo_helper = re.findall(r"if\s*\(\s*!\s*_confirmaOuAvisa\s*\(", _ADMIN)
    assert len(pelo_helper) >= 10, (
        "esperava pelo menos as 10 ações passando pelo invólucro e achei %d — "
        "ou sumiu uma ação, ou alguma voltou a chamar confirm direto"
        % len(pelo_helper))


def test_o_helper_nasce_ANTES_de_quem_ele_usa_estar_definido_nao_importa():
    """🪤 `_confirmaOuAvisa` chama `_adminToast`. Em JS, `function` é içada, então
    a ordem no arquivo não importa — mas se alguém transformar qualquer uma das
    duas em `const ... = () =>`, a ordem passa a importar e o painel quebra na
    primeira recusa. O guarda cobra que as duas sigam sendo `function`."""
    assert re.search(r"function\s+_confirmaOuAvisa\s*\(", _ADMIN), (
        "`_confirmaOuAvisa` deixou de ser `function` — se virou const/arrow, a "
        "ordem de definição passa a importar")
    assert re.search(r"function\s+_adminToast\s*\(", _ADMIN), (
        "`_adminToast` deixou de ser `function` — mesmo risco")


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE POSITIVO — a forma de ANTES, no MESMO julgamento
# ══════════════════════════════════════════════════════════════════════════
_ANTES = """
async function adminRefazerPlanilha(jobId) {
  if (!confirm('Refazer a planilha de ' + jobId + '?')) return;
  _adminToast('Refazendo...', 'warn');
}
"""


def test_CONTROLE_a_forma_ANTIGA_e_reprovada_pelo_mesmo_criterio():
    cruas = re.findall(r"if\s*\(\s*!\s*confirm\s*\(", _ANTES)
    assert cruas, (
        "o critério aprova a forma antiga — ele não está julgando nada e o "
        "teste de cima é verde falso")
    assert not re.findall(r"if\s*\(\s*!\s*_confirmaOuAvisa\s*\(", _ANTES)


def test_CONTROLE_um_helper_MUDO_tambem_e_reprovado():
    """A regressão mais provável não é voltar ao `confirm` direto — é alguém
    "simplificar" o invólucro e tirar o aviso de dentro dele."""
    mudo = "function _confirmaOuAvisa(msg) {\n  return confirm(msg);\n}"
    m = _RE_HELPER.search(mudo)
    assert m, "controle mal montado"
    assert "_adminToast(" not in m.group(1), (
        "o critério não percebe um invólucro sem aviso — foi essa mutação que "
        "passou verde antes deste arquivo existir")
