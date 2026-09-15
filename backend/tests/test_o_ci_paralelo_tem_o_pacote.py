# -*- coding: utf-8 -*-
"""Se o CI roda a bancada em paralelo, ele TEM que instalar o pytest-xdist.

🩸 14/09/2026 — par acoplado, e o acoplamento é invisível. `-n auto` sem o
pacote faz o pytest morrer em **"unrecognized arguments: -n"** antes de colher
um único teste. É a mesma falha de 07/09 (dukpy): CI vermelho em 12 segundos,
com a bancada local verde minutos antes.

🪤 E o guarda que existe para isso — `test_dependencia_de_teste_declarada` —
**não pega este caso**: ele cobre o que a bancada IMPORTA, e `xdist` não é
importado por teste nenhum; é opção de linha de comando. Guarda que existe mas
não alcança o caso é pior que guarda nenhum, porque dá sensação de cobertura.

📏 Por que o paralelo entrou: medido em 12 núcleos, 3.710 testes levam **7 min
8 s** com `-n auto` contra **22 a 28 min** sequencial. Bancada cara é bancada
que se passa a pular — e foi ela que pegou, no mesmo dia, o defeito dos eventos
de telemetria que chegariam sem número.
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _corpo import fonte  # noqa: E402

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_YML = os.path.join(_RAIZ, ".github", "workflows", "bancada.yml")


def _workflow():
    assert os.path.exists(_YML), "não achei .github/workflows/bancada.yml"
    return io.open(_YML, encoding="utf-8").read()


def _sem_comentarios_yml(texto):
    """🪤 Linhas de comentário do YAML fora. A 1ª versão deste guarda procurava
    "pytest-xdist" no arquivo INTEIRO e SOBREVIVEU ao mutante que tirava o
    pacote do `pip install`: o nome continuava escrito no comentário que eu
    mesmo havia posto logo acima, explicando o par. O guarda lia a minha
    anotação. Terceira vez que caio nisso no mesmo dia."""
    return "\n".join(l for l in texto.splitlines()
                     if not l.strip().startswith("#"))


def test_se_usa_n_auto_ENTAO_instala_o_xdist():
    """As duas metades do par, na mesma checagem: uma sem a outra derruba o CI."""
    w = _sem_comentarios_yml(_workflow())
    usa_paralelo = re.search(r"pytest[^\n|]*\s-n\s+\S+", w) is not None
    instala = re.search(r"pip install[^\n]*pytest-xdist", w) is not None
    assert usa_paralelo == instala, (
        "par quebrado no bancada.yml — usa `-n`: %s, instala pytest-xdist: %s. "
        "Com `-n` e sem o pacote o CI morre em 'unrecognized arguments' antes "
        "de colher um teste; com o pacote e sem `-n` a bancada volta a levar "
        "meia hora." % (usa_paralelo, instala))


def test_o_passo_do_PISO_continua_sem_paralelo():
    """🪤 O passo que conta os testes colhidos usa `--collect-only`. Ele não
    ganha nada com `-n` e a saída muda de formato — o `tail -1 | grep -oE '^[0-9]+'`
    pararia de achar o número e o piso viraria 0, passando sempre.

    🪤 A 1ª versão lia de `--collect-only` PRA FRENTE e sobreviveu ao mutante:
    `-n auto` cabe ANTES dele na mesma linha. Tem que ser a linha inteira.
    """
    w = _sem_comentarios_yml(_workflow())
    linhas = [l for l in w.splitlines() if "--collect-only" in l]
    assert linhas, "não achei o passo do piso (--collect-only)"
    for l in linhas:
        assert not re.search(r"\s-n\s", l), (
            "o passo do piso ganhou `-n` — a contagem de testes colhidos muda "
            "de formato e o piso para de guardar: %s" % l.strip()[:130])


def test_o_teto_de_tempo_do_job_continua_de_pe():
    """Paralelizar encurta, mas o teto é a rede contra teste que trava. Sem ele
    a falha vira 6 horas de runner e não diz qual teste."""
    w = _workflow()
    m = re.search(r"timeout-minutes:\s*(\d+)", w)
    assert m and int(m.group(1)) >= 10, (
        "o timeout do job sumiu ou ficou apertado demais: %r"
        % (m.group(0) if m else None))


def test_CONTROLE_o_pipefail_sobreviveu():
    """🪤 `pytest | tee` sem `set -o pipefail` devolve o código do TEE, que é
    sempre 0 — bancada vermelha passaria verde. É a mesma armadilha do
    `pytest | tail` que já me enganou quatro vezes num dia."""
    w = _workflow()
    i = w.index("python -m pytest tests/ -q")
    trecho = w[max(0, i - 220):i]
    assert "set -o pipefail" in trecho, (
        "o `set -o pipefail` sumiu do passo do pytest — com o `| tee`, falha "
        "de teste passaria a sair com código 0 e o CI ficaria verde mentindo")


def test_CONTROLE_a_anotacao_publica_de_falha_continua():
    """A falha tem que ser legível SEM login (09/09): o log da Action exige
    autenticação e as anotações de check run são o único canal público."""
    w = _workflow()
    assert "::error::" in w, "o canal público de falha sumiu do workflow"
    assert "if: failure()" in w, "o passo que publica a falha não roda mais"
