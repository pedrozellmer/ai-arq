# -*- coding: utf-8 -*-
"""Toda biblioteca que a bancada importa está declarada em algum lugar.

🩸 07/09/2026 — O CI QUEBROU EM 12 SEGUNDOS no commit a1cd349, e a bancada
local tinha fechado VERDE com 2.470 testes minutos antes. A diferença: três
módulos novos importam `dukpy` (Duktape, pra rodar o JavaScript do admin de
verdade), eu tinha `dukpy` instalado nesta máquina e o CI não instalava.

Doze segundos é erro de COLETA, não de teste: o pytest nem chegou a rodar.

🔑 O import de `dukpy` é DURO de propósito, e está certo assim: com
`pytest.importorskip` a ausência viraria skip silencioso, e guarda que pula não
guarda — a bancada ficaria verde sem testar nada. O erro não foi o import duro;
foi ninguém cobrar que a dependência estivesse DECLARADA.

🪤 É a armadilha que esta casa já tem escrita: medir com ferramenta que o outro
lado não tem. Ver [[feedback_medir_com_ferramenta_que_a_producao_nao_tem]].

🪤 Dependência de TESTE não vai pro requirements.txt: ela subiria pro Render
sem servir pra nada (dukpy é extensão C). Vai na linha de instalação do CI, que
é onde ela é usada. Este guarda aceita qualquer um dos dois lugares.
"""
import ast
import glob
import io
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
_RAIZ = os.path.dirname(_BACKEND)

def _da_casa():
    """Módulos do próprio backend, LIDOS DA PASTA — não de uma lista minha.

    🪤 A 1ª versão trazia 28 nomes escritos à mão e o guarda acusou seis
    módulos nossos (`pdfvec_carimbo`, `pdfvec_views`, `pdfvec_rooms`…) como se
    fossem biblioteca de terceiro. É o mesmo defeito de lista fechada que esta
    casa passou 06/09 inteiro consertando: a lista cobre o que eu lembrava, e
    o repositório é maior que a minha memória.
    """
    nomes = set()
    # 🪤 A bancada importa script de FORA do backend também: `generate` mora em
    # blog/, e `check_invariants`/`guard_paginas_carregam`/`strip_html_comments`
    # em scripts/. Varrer só o backend acusava os quatro como se fossem
    # biblioteca de terceiro.
    # 🪤 RECURSIVO no backend: `check_invariants` mora em `backend/evals/`, que
    # os testes põem no sys.path. Varrer só o topo o acusava de ser biblioteca
    # de terceiro. Toda vez que eu estreitei o alcance nesta noite, o alcance
    # estreito era o defeito.
    for pasta in (_BACKEND, os.path.join(_RAIZ, "blog"),
                  os.path.join(_RAIZ, "scripts"),
                  os.path.join(_RAIZ, ".github", "scripts")):
        if not os.path.isdir(pasta):
            continue
        for base, dirs, arqs in os.walk(pasta):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "node_modules")]
            nomes |= {a[:-3] for a in arqs if a.endswith(".py")}
            nomes |= {d for d in dirs}
    return nomes


#: 🪤 O nome que se IMPORTA nem sempre é o que se INSTALA. `import PIL` vem de
#: `pillow`, e sem este mapa o guarda acusaria uma dependência que está
#: declarada — e guarda que acusa o certo acaba desligado.
_IMPORT_PRA_PACOTE = {
    "pil": "pillow",
    "yaml": "pyyaml",
    "dateutil": "python-dateutil",
    "dotenv": "python-dotenv",
    "fitz": "pymupdf",
    "cv2": "opencv-python",
    "bs4": "beautifulsoup4",
    "sklearn": "scikit-learn",
}


def _instaladas_no_ci():
    """A linha `pip install ...` do workflow da bancada."""
    p = os.path.join(_RAIZ, ".github", "workflows", "bancada.yml")
    if not os.path.exists(p):
        return set()
    fora = set()
    for linha in io.open(p, encoding="utf-8").read().splitlines():
        s = linha.strip()
        if s.startswith("pip install") and "requirements" not in s:
            for tok in s.split()[2:]:
                if not tok.startswith("-"):
                    fora.add(tok.split("==")[0].split(">=")[0].lower())
    return fora


def _do_requirements():
    p = os.path.join(_BACKEND, "requirements.txt")
    if not os.path.exists(p):
        return set()
    fora = set()
    for linha in io.open(p, encoding="utf-8").read().splitlines():
        s = linha.split("#")[0].strip()
        if s:
            fora.add(s.split("==")[0].split(">=")[0].split("[")[0].lower())
    return fora


def _importados_pela_bancada():
    """Todo pacote de terceiro que os arquivos de `tests/` importam.

    🪤 Por AST, não por regex: `import x` dentro de string, comentário ou
    docstring não conta, e `from a.b import c` tem que virar `a`. Guarda que lê
    texto erra dos dois lados — foi o tema da noite de 06/09.
    """
    achados = {}
    casa = _da_casa()
    for p in sorted(glob.glob(os.path.join(_AQUI, "*.py"))):
        nome = os.path.basename(p)
        if nome == os.path.basename(__file__):
            continue
        try:
            arvore = ast.parse(io.open(p, encoding="utf-8").read())
        except SyntaxError:
            continue
        for n in ast.walk(arvore):
            mods = []
            if isinstance(n, ast.Import):
                mods = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
                mods = [n.module]
            for m in mods:
                raiz = m.split(".")[0]
                if raiz.startswith("_") or raiz in casa:
                    continue
                if raiz in sys.stdlib_module_names:
                    continue
                achados.setdefault(raiz.lower(), set()).add(nome)
    return achados


def test_toda_dependencia_da_bancada_esta_declarada():
    """🚨 O invariante: se a bancada importa, alguém instala.

    Sem isto o CI quebra na COLETA, que é a falha mais cara de diagnosticar —
    zero teste roda, o log não diz qual arquivo, e a bancada local fica verde
    porque a máquina de quem escreveu tem a biblioteca.
    """
    declaradas = _do_requirements() | _instaladas_no_ci()
    faltando = {}
    for mod, arquivos in _importados_pela_bancada().items():
        if mod in declaradas or _IMPORT_PRA_PACOTE.get(mod) in declaradas:
            continue
        faltando[mod] = sorted(arquivos)[:3]
    assert not faltando, (
        "a bancada importa biblioteca que ninguém instala: %s\n"
        "Declare em .github/workflows/bancada.yml (dependência de TESTE) ou em "
        "backend/requirements.txt (se a produção também usa). O CI vai quebrar "
        "na coleta, em segundos, sem dizer qual arquivo." % faltando)


def test_CONTROLE_o_detector_ACHA_uma_dependencia_nao_declarada():
    """🧪 O guarda tem que saber acusar. Se `_importados_pela_bancada` parasse
    de enxergar imports, o teste acima passaria vazio pra sempre."""
    achados = _importados_pela_bancada()
    assert achados, "o detector não achou import de terceiro NENHUM na bancada"
    # e ele TEM que estar vendo as que a gente sabe que existem
    assert "pytest" in achados, "o detector não vê nem o pytest — quebrou"


def test_CONTROLE_as_declaracoes_sao_LIDAS_dos_dois_lugares():
    """🪤 Se a leitura do workflow ou do requirements devolvesse vazio, o teste
    de cima acusaria tudo e alguém o desligaria. E se devolvesse TUDO, ele
    absolveria tudo. Os dois lados precisam estar vivos."""
    ci, req = _instaladas_no_ci(), _do_requirements()
    assert "pytest" in ci, (
        "não consegui ler a linha `pip install` do workflow da bancada — o "
        "guarda passaria a acusar dependência de teste que ESTÁ declarada")
    assert len(req) >= 5, (
        "requirements.txt veio com %d linhas — leitura quebrada" % len(req))
    assert "dukpy" in (ci | req), (
        "dukpy saiu da declaração — foi ele que quebrou o CI em 07/09, e os "
        "guardas de JavaScript param de rodar sem ele")


def test_CONTROLE_o_detector_NAO_conta_import_dentro_de_texto():
    """Por AST: `import` citado em docstring ou comentário não é dependência.
    Ler por regex acusaria a própria explicação — o defeito que mais se repetiu
    aqui em 06/09."""
    arvore = ast.parse('"""exemplo: import scipy"""\n# import numpy\nimport json\n')
    mods = []
    for n in ast.walk(arvore):
        if isinstance(n, ast.Import):
            mods += [a.name for a in n.names]
    assert mods == ["json"], mods
