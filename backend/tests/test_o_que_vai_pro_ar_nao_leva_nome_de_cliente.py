# -*- coding: utf-8 -*-
"""O que o VISITANTE baixa não pode ter nome de cliente. Zero, sem teto.

🚨 08/09/2026, auditoria de segurança. O guarda de LGPD trata todos os arquivos
versionados igual, com um TETO de dívida herdada (378 hoje). Isso é razoável
pro backend: aquele código não sai da máquina do Render.

Mas `dashboard.html`, `projeto.html`, `cadastro.html` e os `.js` são **copiados
pro `_site` e servidos pelo GitHub Pages**. Qualquer visitante abre o
DevTools — ou pede `view-source:` — e lê o comentário. Não precisa nem clonar
o repositório.

🪤 E o filtro do deploy só tira comentário **HTML** (`<!-- -->`). Comentário
JavaScript (`//`) dentro de `<script>` vai inteiro pro ar.

📏 Medido em 08/09: **11 ocorrências** de 8 primeiros nomes de titulares reais
nesses três arquivos, cada um colado a um fato sobre a pessoa (o que ela subiu,
o que falhou, a data, quantos arquivos tinha o projeto dela). Todas trocadas
por rótulo no mesmo commit.

🔑 Por que este guarda existe SEPARADO do teto: teto é dívida que se paga
devagar. Aqui não há dívida a tolerar — o custo de uma ocorrência é publicação
imediata pra qualquer visitante. **Zero, sem teto**, como o guarda de e-mail.

🪤 DOIS casos NÃO eram vazamento e viraram conserto de outro tipo: um exemplo
sintético de nome em `cadastro.html` (ilustrava o encurtamento de nome) e o
nome de uma CIDADE num comentário do `admin.html`. Os dois casaram com a lista
porque o primeiro nome também existe na base de clientes. Trocar o TEXTO custa
nada; afrouxar o guarda custaria a próxima pessoa de verdade.

🪤 E este docstring já errou uma vez: a 1ª versão CITAVA o exemplo que o commit
tinha acabado de remover, e o guarda acusou o próprio arquivo que o explica —
3 ocorrências. Documentação que reescreve o defeito é a mesma família de
[[feedback_comentario_que_planta_o_defeito]]. Descrever o caso basta; escrever
o nome nunca.
"""
import io
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
_RAIZ = os.path.dirname(_BACKEND)
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

from test_repo_publico_nao_expoe_cliente import (  # noqa: E402
    nomes_no_texto, nomes_completos_no_texto, _RE_PESSOAL, _DO_DONO)


def _servidos():
    """Arquivos que o GitHub Pages entrega ao visitante.

    🔑 Descobertos pelo que EXISTE na raiz, não por lista escrita à mão: página
    nova nasce coberta. Foi uma lista à mão que deixou o blog de fora da captura
    de origem por semanas (31/08).
    """
    fora = {"node_modules", ".git", ".github", "backend", "frontend", ".claude",
            "docs", "instagram_assets", "blog"}
    achados = []
    for base, dirs, arqs in os.walk(_RAIZ):
        dirs[:] = [d for d in dirs if d not in fora and not d.startswith(".")]
        if base != _RAIZ:
            continue          # só a raiz: é o que o Pages publica de fato
        for a in sorted(arqs):
            if a.endswith((".html", ".js")):
                achados.append(a)
    return achados


def test_a_lista_de_servidos_NAO_esta_vazia():
    """🧪 Sem isto, um `_servidos()` que devolvesse [] faria todo teste abaixo
    passar sem olhar arquivo nenhum — verde por ausência."""
    servidos = _servidos()
    assert len(servidos) >= 10, servidos
    for obrigatorio in ("dashboard.html", "index.html", "aiarq-utils.js"):
        assert obrigatorio in servidos, (
            "%s deixou de ser visto como servido: %s" % (obrigatorio, servidos))


@pytest.mark.parametrize("rel", _servidos())
def test_nenhum_nome_de_cliente_no_que_vai_pro_ar(rel):
    src = io.open(os.path.join(_RAIZ, rel), encoding="utf-8",
                  errors="replace").read()
    palavras = nomes_no_texto(src, rel)
    completos = nomes_completos_no_texto(src, rel)
    assert not palavras and not completos, (
        "%s é SERVIDO ao visitante e tem nome de cliente nas linhas %s.\n"
        "Comentário JavaScript vai inteiro pro ar — o filtro do deploy só tira "
        "comentário HTML. Troque pelo rótulo (cliente-NN): o caso continua "
        "ensinando, a pessoa sai."
        % (rel, sorted(set(palavras + [l for l, _n in completos]))[:6]))


@pytest.mark.parametrize("rel", _servidos())
def test_nenhum_email_de_terceiro_no_que_vai_pro_ar(rel):
    src = io.open(os.path.join(_RAIZ, rel), encoding="utf-8",
                  errors="replace").read()
    achados = [e for e in _RE_PESSOAL.findall(src) if e.lower() not in _DO_DONO]
    assert not achados, (
        "%s é servido ao visitante e tem e-mail pessoal de terceiro: %d "
        "ocorrência(s)" % (rel, len(achados)))
