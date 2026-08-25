# -*- coding: utf-8 -*-
"""O clique no botão apagado tem que dizer alguma coisa — e ser MEDIDO.

🚨 25/08/2026. O Pedro perguntou "tudo firme com o site? mexemos um monte hoje
e zero clientes". Fui olhar o funil e achei o que interessa: **dois clientes
escolheram arquivo e sumiram**.

  ialves943@gmail.com          25/08 14:07  PDF  — já tinha 4 projetos
  estudosmaraligrupo@gmail.com 24/08 22:10  PDF  — fez o tour inteiro, 0 projetos

Nos dois o rastro é idêntico: `arquivo_escolhido` e depois **silêncio**.

A explicação estava escrita no próprio rastreador de cliques, em
`aiarq-utils.js`: *"por especificação o navegador não dispara evento nenhum em
`<button disabled>`"*. Depois de escolher o arquivo, o botão "Processar
Projeto" fica desabilitado até o cliente marcar o checkbox dos Termos — e
`disabled:opacity-40` é tudo que ele vê. Clica, não acontece nada, **nem aviso
nem evento**. A desistência era literalmente invisível pra nós.

O conserto tem duas metades, e a segunda é a que importa mais:
  1. `pointer-events:none` no botão desabilitado faz o clique cair no
     envelope `#process-guard`, que diz o que falta e destaca o checkbox;
  2. o envelope REGISTRA (`processar_bloqueado`, com `meta.motivo`). Mesmo
     que minha hipótese esteja errada, em poucos dias o número diz qual é o
     motivo real — em vez de eu continuar adivinhando.

🪤 E o guarda da allowlist do `/api/track` — que existe justamente pra impedir
evento descartado em silêncio — **não viu** o evento novo: a regex dele era
`trackEvent\\(` e eu escrevi `trackEvent?.(`. O guarda contra falha silenciosa
tinha ele próprio um ponto cego silencioso. Consertado junto.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _corpo import fonte  # noqa: E402


def _dash():
    return fonte("dashboard.html")


# ══════════════════════════════════════════════════════════════════════════
#  As três peças. Faltando UMA, o conserto inteiro é código morto.
# ══════════════════════════════════════════════════════════════════════════
def test_o_botao_desabilitado_deixa_o_clique_passar():
    """🚨 Sem `pointer-events:none` o clique morre no próprio botão e o
    envelope nunca é acionado — tudo o resto vira decoração."""
    assert re.search(r"#btn-process:disabled\s*\{[^}]*pointer-events\s*:\s*none",
                     _dash()), (
        "sumiu o `pointer-events:none` do botão desabilitado — o clique volta "
        "a morrer sem aviso e sem evento")


def test_o_envelope_ENVOLVE_o_botao():
    """Envelope depois do botão não recebe clique nenhum."""
    src = _dash()
    i_env = src.index('id="process-guard"')
    i_btn = src.index('id="btn-process"')
    assert i_env < i_btn, "o envelope tem que abrir ANTES do botão"
    # e o botão precisa estar dentro do mesmo bloco
    assert "</button>" in src[i_btn:i_btn + 1500]


def test_o_envelope_explica_E_registra():
    src = _dash()
    i = src.index("process-guard')?.addEventListener('click'")
    # 🪤 `src.index("});", i)` parava no `});` de DENTRO do `scrollIntoView`.
    # O fim do listener é o `});` na indentação dele — 2 espaços.
    corpo = src[i:src.index("\n  });", i)]
    assert "Termos de Uso" in corpo, "o cliente continua sem saber o que falta"
    assert "processar_bloqueado" in corpo, (
        "o envelope avisa mas não MEDE — a desistência segue invisível e eu "
        "sigo adivinhando o motivo")
    assert "motivo" in corpo, "sem `meta.motivo` não dá pra separar as causas"


def test_o_envelope_nao_atrapalha_quando_o_botao_esta_ativo():
    """🧪 Controle: se o envelope agisse sempre, ele engoliria o clique bom."""
    src = _dash()
    i = src.index("process-guard')?.addEventListener('click'")
    # 🪤 `src.index("});", i)` parava no `});` de DENTRO do `scrollIntoView`.
    # O fim do listener é o `});` na indentação dele — 2 espaços.
    corpo = src[i:src.index("\n  });", i)]
    assert "if (!btnProcess.disabled) return;" in corpo


def test_marcar_os_termos_apaga_o_aviso():
    """Aviso que não some depois de resolvido vira ruído permanente."""
    src = _dash()
    i = src.index("terms-checkbox')?.addEventListener('change'")
    corpo = src[i:i + 700]
    assert "process-motivo" in corpo and "pisca-termos" in corpo


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE POSITIVO: o guarda tem que REPROVAR a tela de antes
# ══════════════════════════════════════════════════════════════════════════
_TELA_ANTIGA = '''
  <button id="btn-process" data-track="processar-projeto" disabled
          class="mt-3 w-full disabled:opacity-40 disabled:cursor-not-allowed">
    Processar Projeto
  </button>
'''


def test_controle_positivo_a_tela_de_antes_nao_passaria():
    """O código que estava no ar: botão apagado, sem envelope, sem regra de
    ponteiro e sem evento."""
    assert "process-guard" not in _TELA_ANTIGA
    assert not re.search(r"pointer-events\s*:\s*none", _TELA_ANTIGA)
    assert "processar_bloqueado" not in _TELA_ANTIGA


def test_o_destaque_do_checkbox_nao_depende_do_tailwind():
    """🪤 O Tailwind daqui é build ESTÁTICO: classe que não está no CSS gerado
    é INERTE e não dá erro nenhum. `ring-amber-400`, que era a escolha óbvia,
    NÃO existe no build — conferido. Por isso o destaque é CSS próprio."""
    src = _dash()
    assert re.search(r"\.pisca-termos\s*\{[^}]*outline", src), (
        "o destaque do checkbox voltou a depender de classe utilitária — se "
        "ela não estiver no build estático, não acontece nada e ninguém vê")
