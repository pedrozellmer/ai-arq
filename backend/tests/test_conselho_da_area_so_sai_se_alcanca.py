# -*- coding: utf-8 -*-
"""Não pedir ao cliente trabalho que não muda a planilha dele.

🩸 09/09/2026, job 43c52488 — projeto de PÓRTICO (estrutura de entrada de
condomínio, sem cômodos). Não havia área total, e o cliente recebeu:

    "Pra resolver: reenvie informando a área total no campo do envio."

Só que a régua que decide se a área informada CHEGA num item
(`_area_informada_alcancaria`, dentro de `_apply_area_honesty`) só aceita
piso/forro/laje/teto, com **parede bloqueada**. Num pórtico não existe um item
sequer que ela preencheria. O conselho era trabalho pedido ao cliente que não
mudaria uma linha — e ele ainda ia procurar o resultado e não achar.

🪤 É a doença de 08/09 ([[project_conselho_que_a_regua_recusa_20260908]]) outra
vez: lá foram **725 de 936 linhas (77,5%)** com o mesmo conselho recusado pela
régua. Aquele conserto pegou o aviso de ITEM; o aviso de PROJETO ficou de fora
e continuou mandando a mesma coisa. Sétima vez no dia que um conserto foi
aplicado num lado só.

🔑 O aviso continua saindo — a ausência da área é fato e o cliente precisa
saber. O que muda é o FIM da frase: convite quando alcança, explicação honesta
quando não alcança.
"""
import ast
import io
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from engine_rules import (  # noqa: E402
    FLOOR_M2_UNITS,
    is_floor_surface_para_criar,
)


class _It:
    def __init__(s, desc, unit):
        s.description, s.unit = desc, unit


def _alcanca(itens):
    """A MESMA expressão que o `main.py` usa — copiada aqui de propósito?
    Não: chamada às mesmas duas peças públicas de `engine_rules`, que são a
    régua. Reimplementar a régua no teste foi erro meu em 08/09."""
    return any((getattr(i, "unit", "") or "") in FLOOR_M2_UNITS
               and is_floor_surface_para_criar(getattr(i, "description", "") or "")
               for i in itens)


# ══════════════════════════════════════════════════════════════════════════
#  🔑 A régua: quando o convite faz sentido
# ══════════════════════════════════════════════════════════════════════════
def test_projeto_com_PISO_recebe_o_convite():
    assert _alcanca([_It("Piso cerâmico esmaltado", "m²")]) is True


def test_projeto_de_PORTICO_nao_recebe_o_convite():
    """🩸 O caso real, reduzido: pilar, cobertura, rufo, pingadeira — nada que
    a área total preencheria."""
    itens = [_It("Pilar metálico circular diâmetro 90 cm", "un"),
             _It("Rufo metálico — arremate de cobertura", "un"),
             _It("Telha metálica — cobertura da edificação", "m²"),
             _It("Alvenaria de bloco cerâmico 14 cm", "m²")]
    assert _alcanca(itens) is False, (
        "alguma dessas linhas foi tratada como piso/forro/laje — o convite "
        "voltaria a sair sem alcançar ninguém")


def test_PAREDE_em_m2_NAO_conta_como_alcance():
    """🪤 A pegadinha: parede em m² parece que a área total preencheria, e não
    preenche — a régua bloqueia parede de propósito (área de piso não vira
    área de parede sem pé-direito)."""
    assert _alcanca([_It("Alvenaria — paredes internas", "m²")]) is False


def test_lista_vazia_nao_alcanca():
    assert _alcanca([]) is False


# ══════════════════════════════════════════════════════════════════════════
#  🔑 O CALL SITE: o aviso de projeto tem que CONSULTAR a régua
# ══════════════════════════════════════════════════════════════════════════
def _ramo_do_aviso_de_area():
    fonte = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    arv = ast.parse(fonte)
    for n in ast.walk(arv):
        if not isinstance(n, ast.Assign):
            continue
        if not any(getattr(t, "id", None) == "_alcanca" for t in n.targets):
            continue
        return n
    return None


def test_o_aviso_de_projeto_CONSULTA_a_regua():
    """🪤 Ancorado na AST. Comentário citando `_area_informada_alcancaria` — e
    o docstring deste arquivo cita — não pode fazer isto passar."""
    no = _ramo_do_aviso_de_area()
    assert no is not None, (
        "o aviso de área ausente voltou a sair sem perguntar se o conselho "
        "alcança algum item — é trabalho pedido ao cliente que não muda nada")
    usados = {getattr(x, "id", None) or getattr(x, "attr", None)
              for x in ast.walk(no)}
    assert "_FLOOR_M2_UNITS" in usados, (
        "a checagem não usa a unidade de área da régua: %s" % sorted(u for u in usados if u))
    assert "_is_floor_surface_criar" in usados, (
        "a checagem não usa `is_floor_surface_para_criar` — se ela reimplementar "
        "a régua em outro lugar, as duas divergem no primeiro conserto")


def test_os_DOIS_textos_existem_e_dizem_coisas_diferentes():
    """🔑 O convite e a explicação honesta. Ter só um dos dois significa que
    alguém desligou o ramo em vez de consertá-lo."""
    fonte = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = fonte.index("Não encontramos a área total do projeto")
    trecho = fonte[max(0, i - 2500):i + 900]
    assert "reenvie informando a área total" in trecho, (
        "sumiu o CONVITE — quem tem piso/forro precisa dele")
    assert "não mudaria a planilha" in trecho, (
        "sumiu a explicação honesta pra quem o conselho não alcança")


def test_o_aviso_da_AUSENCIA_continua_saindo_sempre():
    """🔒 O conserto não pode virar 'calar o aviso'. A área faltar é FATO e o
    cliente tem que saber — o que muda é só o que se pede a ele."""
    no = _ramo_do_aviso_de_area()
    fonte = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    arv = ast.parse(fonte)
    # 🪤 Mira no `if/else` DO CONSELHO, não em qualquer `if` que o contenha.
    # A 1ª versão usava `ast.walk` e pegava o `elif` externo — que
    # legitimamente contém as duas coisas — e acusava o inocente. Guarda que
    # reprova o certo acaba desligado, então a âncora é estreita: o `if` cujos
    # DOIS ramos atribuem `_conselho` diretamente.
    def _atribui_conselho(corpo):
        return any(isinstance(x, ast.Assign)
                   and any(getattr(t, "id", None) == "_conselho" for t in x.targets)
                   for x in corpo)

    achou_o_if = False
    for n in ast.walk(arv):
        if not isinstance(n, ast.If):
            continue
        if not (_atribui_conselho(n.body) and _atribui_conselho(n.orelse)):
            continue
        achou_o_if = True
        dump = ast.dump(ast.Module(body=n.body + n.orelse, type_ignores=[]))
        assert "Não encontramos a área total" not in dump, (
            "o texto do aviso entrou DENTRO do if do conselho — quem não "
            "recebe o convite passaria a não receber aviso nenhum")
    assert achou_o_if, (
        "não achei o if/else que escolhe o conselho: ou ele sumiu, ou um dos "
        "dois ramos parou de definir `_conselho` (e aí a variável vaza do "
        "escopo anterior, que é pior que o defeito original)")
    assert no is not None
