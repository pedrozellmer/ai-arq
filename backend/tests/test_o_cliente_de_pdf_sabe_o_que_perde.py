# -*- coding: utf-8 -*-
"""Projeto só-PDF diz ao cliente que NADA saiu medido — e quanto o CAD renderia.

🩸 14/09/2026 — o convite ao CAD já existia, e existia DEMAIS: medido na base
(60 dias), **1.319 linhas em 29 de 32 projetos só-PDF** pedem "envie o DXF".
Mil vezes a mesma frase, e nenhuma diz QUANTO se ganha. Um orçamentista lê isso
em 40 linhas e ignora.

📏 O número que faltava (60 dias, 112 projetos concluídos):
  · só-PDF: **0,0%** das linhas medidas do desenho — 32 de 32 projetos com
    ZERO; 46,2% das linhas com algum número (leitura da IA);
  · com DWG/DXF: 23,5% medidas e 72,5% com número.

🔑 O zero não é falha do arquivo do cliente: é regra nossa (`_pdf_downgrade`
rebaixa todo `confirmado` vindo de PDF, porque escala de carimbo é declaração e
não prova — regra dura nº1). Dizer isso na cara é mais honesto que repetir
"envie o DXF" sem explicar.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


class _It:
    def __init__(self, qtd, conf="estimado"):
        self.quantity = qtd
        self.confidence = conf


def _so_pdf(itens):
    return main.aviso_do_projeto_so_pdf(itens, False)


def test_o_aviso_diz_o_numero_DESTE_projeto_e_o_da_base():
    aviso = _so_pdf([_It(10), _It(0), _It(5), _It(0), _It(2)])
    assert aviso, "projeto só-PDF sem nenhuma linha medida ficou sem aviso"
    assert "3 de 5" in aviso, ("o aviso não conta as linhas DESTE projeto: %s" % aviso)
    assert "60%" in aviso, aviso
    assert "23,5" in aviso and "73" in aviso, (
        "o aviso não traz o número do ganho com CAD: %s" % aviso)
    # 🪤 Mutante sobrevivente (14/09): dava pra apagar a PROCEDÊNCIA e manter os
    # números — e número sem fonte é o que a regra de copy pública proíbe. O
    # cliente tem que poder perguntar "medido onde, quando, em quantos?".
    assert "60 dias" in aviso and "projetos" in aviso, (
        "o aviso solta o número sem dizer de onde veio: %s" % aviso)
    assert "não é defeito do seu arquivo" in aviso, (
        "sem isso o cliente lê como culpa do arquivo dele")


def test_o_aviso_explica_POR_QUE_o_PDF_nao_mede():
    """Não basta dizer 'não mediu': tem que dizer que é decisão nossa e por quê,
    senão parece falha da leitura."""
    aviso = _so_pdf([_It(1), _It(0)])
    assert "carimbo" in aviso.lower(), aviso
    assert "declaração" in aviso and "prova" in aviso, aviso


def test_o_aviso_manda_anexar_NO_MESMO_projeto():
    """🪤 Cliente que cria projeto novo pra mandar o CAD perde a comparação — e
    o Carlos, hoje, anexou no mesmo projeto por conta própria e foi o que rendeu."""
    aviso = _so_pdf([_It(1), _It(0)])
    assert "mesmo projeto" in aviso.lower(), aviso


# ── controles: quando o aviso seria MENTIRA ──────────────────────────────
def test_CONTROLE_projeto_com_CAD_nao_recebe_o_aviso():
    assert main.aviso_do_projeto_so_pdf([_It(10), _It(0)], True) == ""


def test_CONTROLE_projeto_que_MEDIU_alguma_coisa_nao_recebe():
    """Se saiu uma linha medida, dizer 'nenhuma foi medida' é falso — e some a
    credibilidade do resto do aviso."""
    assert _so_pdf([_It(10, "confirmado"), _It(0)]) == ""


def test_CONTROLE_projeto_vazio_nao_gera_aviso():
    assert _so_pdf([]) == ""
    assert _so_pdf(None) == ""


def test_CONTROLE_selo_como_enum_tambem_conta_como_medido():
    """O motor usa `Confidence`, não string — o controle acima ficaria cego se a
    regra só entendesse texto."""
    class _Enum:
        value = "confirmado"

    class _ItEnum:
        quantity = 10
        confidence = _Enum()
    assert _so_pdf([_ItEnum(), _It(0)]) == ""


# ── o motor CHAMA o aviso (senão nasce morto) ────────────────────────────
def test_o_process_job_ENTREGA_o_aviso_ao_cliente():
    """🪤 Ponto de chamada: não basta a função existir — o texto tem que entrar
    em `project_data.warnings`, que é o que o cliente lê na tela do projeto."""
    import ast
    import io
    caminho = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
    arv = ast.parse(io.open(caminho, encoding="utf-8").read())
    fn = next((n for n in ast.walk(arv)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == "process_job"), None)
    assert fn is not None

    chamadas = [d for d in ast.walk(fn)
                if isinstance(d, ast.Call) and isinstance(d.func, ast.Name)
                and d.func.id == "aviso_do_projeto_so_pdf"]
    assert chamadas, ("o `process_job` não chama `aviso_do_projeto_so_pdf` — o "
                      "aviso nasceu morto")

    # 🪤 Ancorar pela LINHA da chamada, não por `.index()` do nome: a primeira
    # ocorrência do nome no arquivo é a DEFINIÇÃO da função, e o guarda reprovava
    # o conserto certo por estar lendo o lugar errado.
    linhas = io.open(caminho, encoding="utf-8").read().splitlines()
    ini = min(c.lineno for c in chamadas) - 1
    trecho = "\n".join(linhas[ini:ini + 12])
    assert "project_data.warnings" in trecho, (
        "o aviso é calculado e não entra nos warnings do projeto — ninguém lê:\n%s"
        % trecho)
