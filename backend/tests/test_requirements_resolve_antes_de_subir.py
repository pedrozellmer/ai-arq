# -*- coding: utf-8 -*-
"""A bancada é CEGA pro `requirements.txt`. Este guarda cobre o ponto cego.

🩸 08/09/2026. Subi `pdfplumber==0.11.10` por segurança e derrubei o CI **e** o
build do Render no mesmo push — os dois no passo de INSTALAR, antes de qualquer
teste rodar:

    pdfplumber 0.11.10 depends on pypdfium2>=5.9.0
    The user requested pypdfium2==4.30.0
    ERROR: ResolutionImpossible

🔑 O QUE ISSO ENSINA, E É O MOTIVO DESTE ARQUIVO: a bancada tinha fechado com
**3166 testes verdes** minutos antes. Ela não erra — ela é cega por construção,
porque roda contra o que já está instalado na máquina e **nunca instala do
`requirements.txt`**. Arquivo que não resolve é invisível pra ela.

🚫 A correção NÃO é fazer a bancada instalar: `pip` precisa de rede, e teste que
depende de rede fica intermitente — vermelho que não é defeito ensina a ignorar
vermelho. A checagem de verdade mora no pre-push (`scripts/guard_requirements.py`),
que já precisa de rede.

🔑 O que ESTE arquivo cobre é a DECISÃO, que é pura: dado o texto que o pip
cuspiu, isso é conflito, é sucesso, ou é "não sei"? As saídas abaixo são REAIS,
copiadas da execução que quebrou e da que consertou.
Ver [[feedback_nao_reimplemente_a_regua_pergunte_ao_guarda]].
"""
import ast
import io
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.dirname(os.path.dirname(_AQUI))
_GUARDA = os.path.join(_RAIZ, "scripts", "guard_requirements.py")
_DEPLOY = os.path.join(_RAIZ, "scripts", "guard_deploy.py")


def _mod():
    import importlib.util
    spec = importlib.util.spec_from_file_location("_g_req", _GUARDA)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ══════════════════════════════════════════════════════════════════════════
#  Saídas REAIS do pip, de 08/09/2026 — não inventadas
# ══════════════════════════════════════════════════════════════════════════
_PIP_CONFLITO = """\
Collecting pdfminer.six==20260107 (from pdfplumber==0.11.10->-r backend/requirements.txt (line 39))
  Using cached pdfminer_six-20260107-py3-none-any.whl.metadata (4.3 kB)
INFO: pip is looking at multiple versions of pdfplumber to determine which version is compatible with other requirements. This could take a while.
ERROR: Cannot install -r backend/requirements.txt (line 39) and pypdfium2==4.30.0 because these package versions have conflicting dependencies.

The conflict is caused by:
    The user requested pypdfium2==4.30.0
    pdfplumber 0.11.10 depends on pypdfium2>=5.9.0

To fix this you could try to:
1. loosen the range of package versions you've specified
2. remove package versions to allow pip to attempt to solve the dependency conflict

ERROR: ResolutionImpossible: for help visit https://pip.pypa.io/en/latest/topics/dependency-resolution/
"""

_PIP_OK = """\
Collecting pdfplumber==0.11.9 (from -r backend/requirements.txt (line 39))
  Using cached pdfplumber-0.11.9-py3-none-any.whl.metadata (42 kB)
Would install Jinja2-3.1.6 pdfminer.six-20251230 pdfplumber-0.11.9 pillow-12.3.0 pypdfium2-4.30.0 starlette-1.3.1
"""

# 🪤 Rede caída NÃO é conflito de dependência. Se o guarda tratasse os dois
# igual, ele gritaria "conflito" num wi-fi ruim — e guarda que mente vira guarda
# que alguém desativa.
_PIP_SEM_REDE = """\
WARNING: Retrying (Retry(total=4, connect=None, read=None, redirect=None, status=None)) after connection broken by 'NewConnectionError'
ERROR: Could not install packages due to an OSError: [Errno 101] Network is unreachable
"""


def test_CONTROLE_a_saida_que_QUEBROU_e_reprovada():
    """🧪 O controle positivo. Sem ele, um `veredito()` que sempre devolvesse
    "ok" passaria em todo o resto deste arquivo."""
    m = _mod()
    assert m.veredito(_PIP_CONFLITO, 1) == m.CONFLITO


def test_a_saida_que_CONSERTOU_e_aprovada():
    m = _mod()
    assert m.veredito(_PIP_OK, 0) == m.OK


def test_rede_caida_NAO_vira_conflito():
    """🔑 A distinção que mantém o guarda vivo: bloquear os dois casos, sim —
    mas dizendo a verdade sobre qual é qual."""
    m = _mod()
    assert m.veredito(_PIP_SEM_REDE, 1) == m.NAO_SEI


# 🪤 ESCRITOS À MÃO, e é o ponto do teste. A mutação pegou isto: tirar
# "ResolutionImpossible" da lista do guarda ESCAPOU, porque a saída real de
# exemplo também traz "Cannot install" e "conflicting dependencies" — as outras
# marcas cobriam a que sumiu.
#
# 🔑 E parametrizar sobre `_MARCAS_DE_CONFLITO` NÃO resolveria: com a lista
# menor, o teste teria um caso a menos e passaria igual. Guarda que lê a própria
# lista não vigia a lista. Por isso a expectativa mora AQUI, e cada marca é
# provada SOZINHA, num texto que não contém nenhuma outra.
_MARCAS_QUE_TEM_QUE_EXISTIR = (
    "ResolutionImpossible",
    "conflicting dependencies",
    "Cannot install",
    "no matching distribution",
    "could not find a version that satisfies",
)


@pytest.mark.parametrize("marca", _MARCAS_QUE_TEM_QUE_EXISTIR)
def test_cada_marca_SOZINHA_ja_reprova(marca):
    """Cada marca tem que bastar por si. O pip nem sempre imprime todas."""
    m = _mod()
    texto = "Collecting alguma-coisa\nERROR: %s aconteceu aqui\n" % marca
    assert m.veredito(texto, 1) == m.CONFLITO, (
        "a marca %r deixou de reprovar sozinha — se o pip imprimir só ela, o "
        "guarda fica cego e o push quebrado passa" % marca)


def test_CONTROLE_texto_SEM_marca_nenhuma_nao_e_conflito():
    """🧪 Sem isto, um `veredito()` que devolvesse CONFLITO pra qualquer texto
    passaria em todos os casos acima."""
    m = _mod()
    assert m.veredito("Collecting tudo\nSuccessfully resolved\n", 0) == m.OK


def test_a_mensagem_MOSTRA_o_par_em_conflito():
    """Mensagem que só diz 'não resolve' obriga a pessoa a rodar o pip na mão.
    O par culpado tem que aparecer."""
    m = _mod()
    linhas = " | ".join(m.linhas_do_conflito(_PIP_CONFLITO))
    assert "pypdfium2" in linhas and "pdfplumber" in linhas, linhas


def test_returncode_zero_com_marca_de_conflito_ainda_e_CONFLITO():
    """🪤 O pip já saiu 0 imprimindo aviso de resolução. A marca no texto vale
    mais que o código de saída — é o texto que descreve o que aconteceu."""
    m = _mod()
    assert m.veredito(_PIP_CONFLITO, 0) == m.CONFLITO


# ══════════════════════════════════════════════════════════════════════════
#  Estar escrito não é estar LIGADO
# ══════════════════════════════════════════════════════════════════════════
def test_o_guarda_esta_LIGADO_na_cadeia_do_pre_push():
    """🪤 Guarda que ninguém chama não guarda nada — e eu já escrevi cinco
    guardas hoje que casavam com o próprio COMENTÁRIO que os explicava.

    🔑 Por isso este teste lê a AST, não o texto: comentário não vira nó de
    AST. Se o nome só aparecer num `#`, este teste reprova — que é o certo.
    """
    fonte = io.open(_DEPLOY, encoding="utf-8").read()
    arvore = ast.parse(fonte)
    literais = [n.value for n in ast.walk(arvore)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert "guard_requirements.py" in literais, (
        "o guarda do requirements não é CHAMADO por guard_deploy.py — está só "
        "escrito, ou só citado em comentário")


def test_CONTROLE_a_leitura_por_AST_ignora_COMENTARIO(tmp_path):
    """🧪 Prova que o teste acima não passaria por um comentário. Sem isto,
    "leio a AST" seria só uma frase bonita no docstring."""
    p = tmp_path / "so_comentario.py"
    p.write_text("# guard_requirements.py\nx = 1\n", encoding="utf-8")
    arvore = ast.parse(p.read_text(encoding="utf-8"))
    literais = [n.value for n in ast.walk(arvore)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert "guard_requirements.py" not in literais


def test_o_guarda_vigia_o_arquivo_CERTO():
    m = _mod()
    assert m.ALVO == "backend/requirements.txt"


def test_usa_ignore_installed():
    """🪤 Sem `--ignore-installed` o pip aceita o que já está na máquina e o
    conflito SOME — o guarda ficaria verde pelo mesmo motivo que a bancada
    ficou. Este é o argumento que faz o guarda medir a coisa certa.

    🔑 Ancorado na LISTA de argumentos dentro da AST, não no texto do arquivo:
    a explicação disso está num comentário logo acima, e casar com ela seria
    exatamente o defeito que este arquivo inteiro documenta.
    """
    arvore = ast.parse(io.open(_GUARDA, encoding="utf-8").read())
    achou = False
    for n in ast.walk(arvore):
        if not isinstance(n, ast.List):
            continue
        itens = [e.value for e in n.elts
                 if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        if "--dry-run" in itens and "--ignore-installed" in itens:
            achou = True
    assert achou, (
        "a chamada do pip não passa --ignore-installed junto de --dry-run")


@pytest.mark.skipif(not os.path.exists(_GUARDA), reason="guarda ausente")
def test_o_guarda_roda_como_processo_sem_explodir():
    """Executa de verdade. Ele sai 0 quando o requirements não mudou neste
    push — o que é o caminho normal e o que a maioria dos pushes vai ver."""
    import subprocess
    r = subprocess.run([sys.executable, _GUARDA], cwd=_RAIZ,
                       capture_output=True, text=True, timeout=420)
    assert r.returncode in (0, 1), (r.returncode, r.stdout[-500:], r.stderr[-500:])
