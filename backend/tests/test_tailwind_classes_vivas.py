# -*- coding: utf-8 -*-
"""Classe do Tailwind fora do CSS compilado nasce INERTE — e some calada.

🚨 24/08/2026. O botão "Criar projeto combinado" saiu com
`bg-violet-700 text-white`. `bg-violet-700` NÃO está no `tailwind.min.css`.
Resultado: texto branco sobre fundo nenhum, num card branco. O botão estava lá,
funcionava, e era **invisível**. O Pedro clicou em tudo, não achou, e perguntou
"não entendi, faço o que agora?".

O mesmo dia deu um segundo caso, mais antigo e mais silencioso: o botão
"Reprocessar (do cliente)" ganhou `border-amber-400` de manhã pra marcar que é o
botão perigoso. Também não está no build — a borda de alerta **nunca apareceu**,
e ninguém notou, porque falta de cor não dá erro.

🪤 Por que acontece: o `tailwind.min.css` é gerado UMA vez por `gerar-css.bat`
(binário fora do repo) varrendo `./*.html`, `./*.js` e `./blog/**`. Classe nova
usada depois da última geração fica sem estilo até alguém regenerar. O arquivo
em produção é de 04/08.

🚨 A PRIMEIRA VERSÃO DESTE ARQUIVO ACUSOU 103 CLASSES `hover:` MORTAS. Era bug
MEU, não do site: `re.escape("hover:bg-x")` não escapa os dois-pontos, então o
`.replace(r"\\:", ...)` não trocava nada e a busca procurava `:` literal — mas no
CSS a classe está escrita `.hover\\:bg-x`. Casava zero, sempre.

O teste tinha controle positivo pra classe BASE (`bg-indigo-600` existe) e
NENHUM pra variante. Por isso passou verde acusando o site inteiro. O número
real é ZERO. Todo detector precisa de um controle por FORMATO que ele lê, não
um só pro formato mais fácil — é o que as funções `test_controle_*` abaixo
garantem agora.
"""
import io
import os
import re

import pytest

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PAGINAS = ("admin.html", "projeto.html", "dashboard.html", "revisao.html",
            "index.html", "cadastro.html", "login.html", "faq.html",
            "financeiro.html")

# Só cor/fundo/borda: espaçamento inerte se nota na hora, cor inerte deixa
# conteúdo invisível — que é o defeito que originou este arquivo.
_RX_CLASSE = re.compile(
    r"(?:^|[\s\"'])((?:hover:|focus:|active:|group-hover:)?"
    r"(?:bg|text|border|ring)-[a-z]+-\d{2,3})")

_RX_COMENTARIO = re.compile(r"<!--.*?-->|/\*.*?\*/", re.S)


def _css():
    caminho = os.path.join(_RAIZ, "tailwind.min.css")
    if not os.path.exists(caminho):
        pytest.skip("tailwind.min.css não está nesta cópia do repo")
    return io.open(caminho, encoding="utf-8").read()


def _existe(classe, css):
    """No CSS a classe aparece com os dois-pontos ESCAPADOS: `.hover\\:bg-x`.

    🪤 Era exatamente aqui que o detector mentia. O lookahead impede que
    `bg-violet-6` case dentro de `.bg-violet-600`."""
    literal = "." + classe.replace(":", "\\:")
    return re.search(re.escape(literal) + r"(?![\w-])", css) is not None


def _classes_usadas(pagina):
    """🪤 Comentário NÃO é uso. O dashboard tem um comentário que CITA
    `hover:bg-amber-600` pra explicar que ela não existe no build (e resolve com
    CSS puro logo abaixo). Contar isso como uso seria acusar quem acertou."""
    caminho = os.path.join(_RAIZ, pagina)
    if not os.path.exists(caminho):
        pytest.skip("%s não está nesta cópia" % pagina)
    src = _RX_COMENTARIO.sub(" ", io.open(caminho, encoding="utf-8").read())
    return set(_RX_CLASSE.findall(src))


# ══════════════════════════════════════════════════════════════════════════
#  🧪 Um controle por FORMATO que o detector lê
# ══════════════════════════════════════════════════════════════════════════
def test_controle_positivo_classe_base_que_existe():
    assert _existe("bg-indigo-600", _css()), (
        "o detector não achou a cor do botão primário do site — se este falha, "
        "todo 'INERTE' que ele acusar é falso")


def test_controle_positivo_classe_com_VARIANTE_que_existe():
    """🚨 O controle que faltava, e cuja falta me fez acusar 103 classes boas.
    Formato diferente (dois-pontos escapados no CSS) precisa de controle
    próprio."""
    css = _css()
    for c in ("hover:bg-indigo-700", "hover:bg-gray-50", "hover:bg-amber-100"):
        assert _existe(c, css), (
            "o detector não achou %s, que ESTÁ no CSS — ele está cego pra "
            "variantes e vai acusar o site inteiro" % c)


def test_controle_negativo_classe_inventada():
    assert not _existe("bg-batatafrita-999", _css())


def test_controle_negativo_o_caso_real():
    """`bg-violet-600` existe e `bg-violet-700` não — foi essa diferença que
    deixou o botão invisível."""
    css = _css()
    assert _existe("bg-violet-600", css)
    assert not _existe("bg-violet-700", css)


def test_controle_negativo_prefixo_nao_casa_classe_maior():
    assert not _existe("bg-violet-6", _css())


def test_controle_comentario_nao_conta_como_uso():
    src = "<!-- usa bg-batatafrita-999 -->  /* e text-batatafrita-111 */"
    assert not _RX_CLASSE.findall(_RX_COMENTARIO.sub(" ", src))


# ══════════════════════════════════════════════════════════════════════════
#  O guarda
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("pagina", _PAGINAS)
def test_nenhuma_classe_de_cor_inerte(pagina):
    """Base E variante. Medido em 24/08 com o detector já corrigido: zero em
    todas as 8 páginas."""
    css = _css()
    ruins = sorted(c for c in _classes_usadas(pagina) if not _existe(c, css))
    assert not ruins, (
        "%s usa classe(s) de cor que NÃO estão no tailwind.min.css: %s.\n"
        "Elas não dão erro — o elemento sai sem cor, e texto branco sem fundo "
        "fica invisível. Ou troque por uma classe que já exista no build, ou "
        "rode gerar-css.bat (precisa do tailwindcss.exe, fora do repo), ou "
        "escreva a regra em CSS puro como o dashboard fez com .btn-revisar."
        % (pagina, ruins))


def test_o_botao_de_criar_o_merge_tem_fundo_de_verdade():
    """🚨 O caso exato: era o botão PRINCIPAL do fluxo novo e ninguém o via."""
    css = _css()
    src = io.open(os.path.join(_RAIZ, "admin.html"), encoding="utf-8").read()
    i = src.index('onclick="mergeCriar(')
    trecho = src[i:i + 400]
    fundos = [c for c in _RX_CLASSE.findall(trecho) if c.startswith("bg-")]
    assert fundos, "o botão de criar o merge não tem classe de fundo nenhuma"
    for f in fundos:
        assert _existe(f, css), "o fundo %s do botão não existe no build" % f
    assert "text-white" in trecho
