# -*- coding: utf-8 -*-
"""`confirmado + 0` rebaixa o SELO — nunca inventa a quantidade.

🩸 09/09/2026. A mesma decisão vivia em TRÊS lugares e as três divergiram:

    analyzer.py, dentro de `analyze_all_sheets`   → CERTA (rebaixa o selo)
    main.py, caminho DXF/DWG                      → `qty = 1`
    main.py, caminho PDF                          → `qty = 1`

E a única CERTA morava na função que o `main.py` **importa e nunca chama**. O
conserto de 26/08 foi aplicado só nela. Em produção o defeito seguiu vivo — e
PIOR que a versão consertada, porque as cópias vivas mantinham o selo
`confirmado`: o número inventado saía como **MEDIDO** na planilha do cliente.

🚨 Quais itens caem aí: a IA usa `confirmado + 0` justamente pros que o projeto
manda NÃO ORÇAR — "[EXISTENTE — sem intervenção] Porta PE1", "Alvenaria
existente a manter". Ela tem certeza de que existe e certeza de que não há obra.
O `qty = 1` transforma "não orçar" em "orçar 1".

📏 Medido no banco em 09/09: **614 itens** com `qty=1 + confirmado` em 82 jobs;
**13** com descrição explícita de "existente / a manter". Não dá pra separar
daqui quantos dos 614 foram inventados — o que se sabe é que pelo menos 13
estão errados, e que o teto é 614.

🪤 O GUARDA QUE EXISTIA NÃO PEGOU, e o docstring dele explica por quê: em 26/08
eu escrevi *"na 1ª versão chamei `analyze_sheet` e os testes reprovaram sozinhos
— quem sanea é `analyze_all_sheets`"*. Ou seja: eu MOVI o guarda pra dentro da
função morta pra ele passar. Guarda que persegue o código até onde ele passa
deixa de guardar o produto. Ver [[project_guardas_cegos_medidos_20260906]].
"""
import ast
import io
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from analyzer import sanear_qtd_e_selo  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════
#  A régua
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_confirmado_com_zero_REBAIXA_o_selo():
    """🧪 O caso do defeito. Sem este controle, uma régua que devolvesse a
    entrada intacta passaria em quase tudo abaixo."""
    assert sanear_qtd_e_selo(0, "confirmado") == (0, "estimado")


def test_NUNCA_inventa_numero():
    """🚨 O coração. A quantidade que sai é a que entrou — nunca um 1."""
    for entrada in (0, 0.0, None, "", "abc"):
        qty, _conf = sanear_qtd_e_selo(entrada, "confirmado")
        assert float(qty or 0) == 0.0, (
            "inventou %r a partir de %r" % (qty, entrada))


def test_quantidade_de_verdade_passa_intacta():
    """🧪 O outro lado: uma régua que zerasse tudo 'passaria' nos testes acima
    e destruiria todo quantitativo medido."""
    assert sanear_qtd_e_selo(5, "confirmado") == (5, "confirmado")
    assert sanear_qtd_e_selo(0.25, "confirmado") == (0.25, "confirmado")
    assert sanear_qtd_e_selo(880.4, "estimado") == (880.4, "estimado")


def test_negativo_vira_zero_e_nao_um():
    assert sanear_qtd_e_selo(-3, "confirmado") == (0, "estimado")
    assert sanear_qtd_e_selo(-3, "estimado")[0] == 0


def test_zero_ESTIMADO_continua_estimado():
    """🪤 Zero não é estado quebrado: a política já permite `estimado + 0`, e a
    tela de revisão existe pro cliente preencher."""
    assert sanear_qtd_e_selo(0, "estimado") == (0, "estimado")


# ══════════════════════════════════════════════════════════════════════════
#  🔑 O QUE FALTAVA: os call sites de PRODUÇÃO
# ══════════════════════════════════════════════════════════════════════════
def _ast_de(nome):
    return ast.parse(io.open(os.path.join(_BACKEND, nome),
                             encoding="utf-8").read())


@pytest.mark.parametrize("arquivo", ["main.py", "analyzer.py"])
def test_NINGUEM_atribui_qty_igual_a_1(arquivo):
    """🩸 O guarda que teria pegado o defeito. Nenhum lugar pode escrever
    `qty = 1` — foi exatamente essa linha, em DOIS caminhos vivos, que inventou
    número por 14 dias depois de eu 'consertar' só a cópia morta.

    🔑 Lê a AST: comentário e docstring citam `qty = 1` de propósito (pra
    explicar o defeito) e NÃO podem fazer o guarda reprovar. Texto reprovaria.
    """
    arvore = _ast_de(arquivo)
    culpados = []
    for n in ast.walk(arvore):
        if not isinstance(n, ast.Assign):
            continue
        if not (isinstance(n.value, ast.Constant) and n.value.value == 1):
            continue
        for alvo in n.targets:
            if getattr(alvo, "id", None) in ("qty", "quantity"):
                culpados.append(n.lineno)
    assert not culpados, (
        "%s atribui quantidade 1 nas linhas %s. Isso INVENTA um número que "
        "ninguém leu — use `sanear_qtd_e_selo`, que rebaixa o selo e mantém o "
        "zero honesto." % (arquivo, culpados))


def test_CONTROLE_a_leitura_por_AST_ignora_comentario_e_docstring(tmp_path):
    """🧪 Prova que o teste acima não reprovaria pelos comentários que EXPLICAM
    o defeito — sem isto, consertar o código e manter a documentação honesta
    seriam incompatíveis, e alguém apagaria a documentação."""
    p = tmp_path / "so_texto.py"
    p.write_text('"""aqui tinha qty = 1 e era errado."""\n'
                 '# qty = 1\n'
                 'x = 2\n', encoding="utf-8")
    arvore = ast.parse(p.read_text(encoding="utf-8"))
    achou = [n for n in ast.walk(arvore)
             if isinstance(n, ast.Assign)
             and isinstance(n.value, ast.Constant) and n.value.value == 1
             and any(getattr(t, "id", None) == "qty" for t in n.targets)]
    assert not achou, "a leitura por AST casou com comentário — está errada"


def test_os_DOIS_caminhos_vivos_CHAMAM_a_regua():
    """🔑 Não basta não inventar: os dois laços de item do `main.py` (o de
    DXF/DWG e o de PDF) têm que CHAMAR a régua. Se um deles parar de chamar,
    volta a divergir — que é a doença deste arquivo inteiro."""
    arvore = _ast_de("main.py")
    chamadas = [n for n in ast.walk(arvore)
                if isinstance(n, ast.Call)
                and (getattr(n.func, "id", None) or getattr(n.func, "attr", None))
                in ("sanear_qtd_e_selo", "_sanear")]
    assert len(chamadas) >= 2, (
        "o main.py chama a régua %d vez(es); são DOIS caminhos de item "
        "(DXF/DWG e PDF) e os dois precisam chamar" % len(chamadas))


def test_a_copia_do_analyzer_tambem_chama_a_MESMA_regua():
    """🪤 A cópia morta continua no repo (outro assunto, outro commit). Enquanto
    ela existir, tem que usar a MESMA régua — senão volta a divergir e o próximo
    conserto cai no lado errado outra vez."""
    arvore = _ast_de("analyzer.py")
    chamadas = [n for n in ast.walk(arvore)
                if isinstance(n, ast.Call)
                and (getattr(n.func, "id", None) or getattr(n.func, "attr", None))
                == "sanear_qtd_e_selo"]
    assert chamadas, "analyzer.py não chama a própria régua"
