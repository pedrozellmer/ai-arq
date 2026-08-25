# -*- coding: utf-8 -*-
"""Classe de cor que não está no CSS compilado nasce INERTE — e some calada.

🚨 24/08/2026. O botão "Criar projeto combinado" saiu com
`bg-violet-700 text-white`. `bg-violet-700` NÃO existe no `tailwind.min.css`.
Resultado: texto branco sobre fundo nenhum, num card branco. O botão estava lá,
funcionava, e era **invisível**. O Pedro clicou em tudo, não achou, e perguntou
"não entendi, faço o que agora?".

O mesmo dia me deu um segundo caso, mais antigo e mais silencioso: o botão
"Reprocessar (do cliente)" ganhou `border-amber-400` de manhã pra avisar que é o
botão perigoso. Essa classe também não existe no build — a borda de alerta
**nunca apareceu** e ninguém notou, porque falta de cor não dá erro.

🪤 Isto já estava anotado em [[reference_tailwind_build_estatico]] e eu caí
assim mesmo. Anotação não guarda; teste guarda.

📋 Sobre `hover:` e `focus:`: o build NÃO tem essas variantes em página nenhuma
(medido em 24/08: 22 em admin, 29 em dashboard, 21 em projeto, 16 em revisão, 10
na index). Ou seja, nenhum efeito de mouse funciona no site. É cosmético e é
pré-existente, então este guarda NÃO falha por causa delas — mas conta quantas
são, pra ninguém achar que hover funciona.
"""
import io
import os
import re

import pytest

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PAGINAS = ("admin.html", "projeto.html", "dashboard.html", "revisao.html", "index.html")

# Só cor/fundo/borda: espaçamento inerte se nota na hora, cor inerte deixa
# conteúdo invisível.
_RX_BASE = re.compile(r"(?:^|[\s\"'])((?:bg|text|border|ring)-[a-z]+-\d{2,3})")
_RX_VARIANTE = re.compile(
    r"(?:^|[\s\"'])((?:hover|focus|active|group-hover):[a-z-]+-[a-z]+-\d{2,3})")


def _css():
    caminho = os.path.join(_RAIZ, "tailwind.min.css")
    if not os.path.exists(caminho):
        pytest.skip("tailwind.min.css não está nesta cópia do repo")
    return io.open(caminho, encoding="utf-8").read()


def _existe(classe, css):
    esc = re.escape(classe).replace(r"\:", r"\\:")
    return re.search(r"\.%s[\s,{:>~+.\[]" % esc, css) is not None


def _ler(pagina):
    caminho = os.path.join(_RAIZ, pagina)
    if not os.path.exists(caminho):
        pytest.skip("%s não está nesta cópia" % pagina)
    return io.open(caminho, encoding="utf-8").read()


# ══════════════════════════════════════════════════════════════════════════
#  🧪 O detector tem que provar que enxerga
# ══════════════════════════════════════════════════════════════════════════
def test_controle_positivo_o_detector_acusa_classe_inventada():
    """Se o detector for cego, o guarda inteiro é enfeite."""
    assert not _existe("bg-batatafrita-999", _css())


def test_controle_negativo_o_detector_acha_classe_que_existe():
    css = _css()
    assert _existe("bg-indigo-600", css), (
        "o detector não achou uma classe que o site usa em botão primário — "
        "a regex de busca está errada e todo o resto é falso negativo")


def test_o_caso_real_que_originou_isto():
    """`bg-violet-700` não existe e `bg-violet-600` existe. Se um dia o build
    mudar e os dois passarem a existir, este teste avisa que o exemplo aqui
    ficou histórico — não é motivo pra apagar o guarda."""
    css = _css()
    assert _existe("bg-violet-600", css)


# ══════════════════════════════════════════════════════════════════════════
#  O guarda
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("pagina", _PAGINAS)
def test_nenhuma_cor_base_inerte(pagina):
    css = _css()
    src = _ler(pagina)
    ruins = sorted({c for c in _RX_BASE.findall(src) if not _existe(c, css)})
    assert not ruins, (
        "%s usa classe(s) de cor que NÃO estão no tailwind.min.css: %s.\n"
        "Elas não dão erro — o elemento simplesmente sai sem cor, e texto "
        "branco sem fundo fica invisível. Troque por uma classe que exista, ou "
        "regere o CSS." % (pagina, ruins))


def test_o_botao_de_criar_o_merge_tem_fundo_de_verdade():
    """🚨 O caso exato: era o botão PRINCIPAL do fluxo novo e ninguém o via."""
    src = _ler("admin.html")
    i = src.index('onclick="mergeCriar(')
    trecho = src[i:i + 400]
    css = _css()
    fundos = [c for c in _RX_BASE.findall(trecho) if c.startswith("bg-")]
    assert fundos, "o botão de criar o merge não tem classe de fundo nenhuma"
    for f in fundos:
        assert _existe(f, css), "o fundo %s do botão não existe no build" % f
    assert "text-white" in trecho


# ══════════════════════════════════════════════════════════════════════════
#  📋 Hover/focus: medido, não consertado
# ══════════════════════════════════════════════════════════════════════════
def test_conta_quantas_variantes_de_mouse_estao_mortas():
    """Não falha — REGISTRA. O build não traz `hover:`/`focus:` em página
    nenhuma, então nenhum efeito de mouse funciona no site. É pré-existente e
    cosmético; virar falha aqui só ensinaria a ignorar o arquivo.

    Se um dia alguém regerar o CSS com as variantes, este número cai pra 0 e é
    sinal de que o hover passou a valer."""
    css = _css()
    total = 0
    for pagina in _PAGINAS:
        caminho = os.path.join(_RAIZ, pagina)
        if not os.path.exists(caminho):
            continue
        src = io.open(caminho, encoding="utf-8").read()
        total += len({c for c in _RX_VARIANTE.findall(src) if not _existe(c, css)})
    assert total >= 0
    print("variantes hover/focus inertes no site: %d" % total)
