# -*- coding: utf-8 -*-
"""O JSON-LD da landing tem que PARSEAR — e tem que dizer onde mais a gente existe.

🩸 05/09/2026. Duas coisas de uma vez.

**1. Schema quebrado morre calado.** Um JSON-LD com vírgula sobrando não dá erro
em lugar nenhum: o navegador ignora, o site abre normal, e o Google
simplesmente para de ler os dados estruturados. Ninguém percebe até o
ranqueamento cair. Não havia guarda nenhum na landing — só no FAQ.

**2. `sameAs` é o que amarra "este perfil e este site são a mesma empresa".**
📏 MEDIDO em 31/08: buscando "AI.arq", **tudo** que aparece é do nosso próprio
domínio — corroboração externa ZERO. Modelo de IA recomenda com mais segurança o
que várias fontes independentes descrevem; sendo uma fonte só, a gente não é
citado. O cadastro no Capterra (publicado em 02/09) é o primeiro link externo, e
a nota de 31/08 já avisava: *"sem o `sameAs`, metade do valor do cadastro se
perde"*.

🪤 Só entra URL que eu ABRI e vi carregar. `sameAs` apontando pra página que não
existe é pior que ausente: afirma uma ligação que não resolve. GetApp e Software
Advice fazem parte da mesma rede e devem publicar também — quando publicarem,
conferir a URL no navegador ANTES de acrescentar aqui.
"""
import io
import json
import os
import re

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_RE_LD = re.compile(
    r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S | re.I)


def _blocos(arquivo):
    txt = io.open(os.path.join(_RAIZ, arquivo), encoding="utf-8").read()
    return _RE_LD.findall(txt)


def test_o_jsonld_da_landing_PARSEIA():
    """🪤 O modo de falhar é silencioso: vírgula sobrando e o Google para de ler."""
    blocos = _blocos("index.html")
    assert blocos, "a landing perdeu o bloco de dados estruturados"
    for i, b in enumerate(blocos):
        try:
            json.loads(b)
        except ValueError as e:
            raise AssertionError(
                "bloco JSON-LD %d da landing está QUEBRADO (%s). O site abre "
                "normal e o Google para de ler os dados estruturados, sem "
                "erro em lugar nenhum." % (i + 1, e))


def _schema_da_landing():
    for b in _blocos("index.html"):
        d = json.loads(b)
        if d.get("@type") == "SoftwareApplication":
            return d
    raise AssertionError("a landing não tem mais o SoftwareApplication")


def test_a_landing_diz_onde_mais_a_gente_existe():
    d = _schema_da_landing()
    same = d.get("sameAs") or []
    assert same, (
        "o `sameAs` sumiu — é ele que amarra os perfis externos a este site. "
        "Sem ele, metade do valor do cadastro em diretório se perde, e a "
        "corroboração externa volta a ser zero")


def test_todo_sameAs_e_url_absoluta_e_https():
    """URL relativa ou http aqui não amarra nada — e não dá erro visível."""
    for u in (_schema_da_landing().get("sameAs") or []):
        assert u.startswith("https://"), (
            "sameAs com URL que não é https absoluta: %r" % u)
        assert " " not in u.strip(), "sameAs com espaço na URL: %r" % u


def test_nao_repete_o_proprio_dominio_no_sameAs():
    """🪤 `sameAs` existe pra apontar pra FORA. Listar ai.arq.br ali é dizer
    "este site é o mesmo que este site" — ruído que não corrobora nada, e foi
    justamente a falta de fonte externa que a medição de 31/08 apontou."""
    for u in (_schema_da_landing().get("sameAs") or []):
        assert "ai.arq.br" not in u, (
            "sameAs aponta pro próprio domínio (%r) — corroboração externa é "
            "outra fonte, não nós mesmos" % u)


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLES POSITIVOS — o MESMO julgamento nos casos ruins
# ══════════════════════════════════════════════════════════════════════════
def _sameas_de(bloco_json):
    return json.loads(bloco_json).get("sameAs") or []


def test_CONTROLE_json_quebrado_e_pego():
    quebrado = '{"@type":"SoftwareApplication","name":"AI.arq",}'
    try:
        json.loads(quebrado)
    except ValueError:
        return
    raise AssertionError("o controle está mal montado — este JSON é inválido")


def test_CONTROLE_sameAs_relativo_e_reprovado():
    ruim = _sameas_de('{"sameAs":["/perfil-capterra"]}')
    assert ruim and not ruim[0].startswith("https://"), (
        "o controle está mal montado")


def test_CONTROLE_sameAs_do_proprio_dominio_e_reprovado():
    ruim = _sameas_de('{"sameAs":["https://ai.arq.br/precos.html"]}')
    assert ruim and "ai.arq.br" in ruim[0], "o controle está mal montado"
