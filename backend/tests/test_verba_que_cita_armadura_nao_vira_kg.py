# -*- coding: utf-8 -*-
"""Verba que cita "armadura" não vira quilo de aço.

🩸 22/09/2026 — job ee801b82 (estrutura, 7 PDFs). A IA listou "Projeto
executivo complementar (detalhamento de armadura, projetos hidráulicos
referenciados)" em `vb`, quantidade 1. O forçador de aço-em-kg do projeto
estrutural casou a palavra "armadura" e trocou a unidade: a planilha saiu com
**1 kg**, somado no total de aço. O forçador só troca o RÓTULO — nunca converte
—, então verba que vira kg é peso inventado.

📏 llm_cache (começa em 28/08) × project_items, mesma descrição: o forçador
trocou 4 rótulos, nenhum de aço de verdade — esta verba e 3 linhas "sem itens
quantificáveis" com unidade "—" (job 3eb748e3).

🔑 A unidade vai junto pra `should_force_steel_kg`: verba, conjunto, serviço,
tempo e "sem unidade" declarado não viram kg. O caso de origem do forçador
(aço devolvido em m²) continua forçado.
"""
import ast
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402
from engine_rules import should_force_steel_kg  # noqa: E402

_MAIN_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")

_VERBA = ("Projeto executivo complementar (detalhamento de armadura, projetos "
          "hidráulicos referenciados)")


class _It:
    def __init__(self, desc, unit, qty):
        self.description, self.unit, self.quantity = desc, unit, qty


def test_CONTROLE_a_descricao_do_caso_casa_o_padrao_de_aco():
    """Sem a unidade (regra antiga), a verba É tratada como aço — é o defeito."""
    assert should_force_steel_kg(_VERBA) is True


def test_a_verba_do_caso_nao_vira_kg():
    assert should_force_steel_kg(_VERBA, "vb") is False


def test_unidades_que_dizem_o_que_o_numero_e_sem_ser_peso():
    for u in ("vb", "VB", " verba ", "cj", "gl", "global", "conjunto", "sv",
              "serviço", "mês", "h", "—", "-"):
        assert should_force_steel_kg("Espaçadores para armadura", u) is False, u


def test_CONTROLE_aco_de_verdade_noutra_unidade_continua_forcado():
    """O caso que criou o forçador (aço devolvido em m²) não pode voltar."""
    assert should_force_steel_kg("Armadura em aço CA-50 — vigas", "m²") is True
    assert should_force_steel_kg("Estribos ∅5 mm CA-60", "m") is True
    assert should_force_steel_kg("Aço CA-50 ø10", "") is True
    # e fôrma continua fora, com ou sem unidade
    assert should_force_steel_kg("Fôrma de pilar com armadura aparente", "m²") is False


def test_o_laco_do_motor_nao_troca_a_verba_e_troca_o_aco():
    verba = _It(_VERBA, "vb", 1)
    aco = _It("Armadura em aço CA-50 — lajes", "m²", 37)
    ja_kg = _It("Aço CA-60 ø5", "kg", 120)
    forma = _It("Fôrma de viga", "m²", 24.3)
    n = main._forca_aco_em_kg([verba, aco, ja_kg, forma])
    assert n == 1, n
    assert (verba.unit, verba.quantity) == ("vb", 1)
    assert (aco.unit, aco.quantity) == ("kg", 37), "o rótulo troca, o número não"
    assert (ja_kg.unit, forma.unit) == ("kg", "m²")


def test_o_process_job_usa_o_laco_da_funcao_so_em_estrutura():
    """🪤 Guarda de FONTE, assumido: o laço executado acima é o que roda no
    motor, dentro do `if is_structural:` — e não sobrou outra chamada do
    forçador sem a unidade."""
    arv = ast.parse(io.open(_MAIN_PY, encoding="utf-8").read())
    pj = next(n for n in arv.body
              if isinstance(n, ast.FunctionDef) and n.name == "process_job")
    dentro_de_estrutura = []
    for n in ast.walk(pj):
        if (isinstance(n, ast.If) and isinstance(n.test, ast.Name)
                and n.test.id == "is_structural"):
            for m in ast.walk(n):
                if (isinstance(m, ast.Call) and isinstance(m.func, ast.Name)
                        and m.func.id == "_forca_aco_em_kg"):
                    dentro_de_estrutura.append(m.lineno)
    assert len(dentro_de_estrutura) == 1, dentro_de_estrutura
    soltas = [n.lineno for n in ast.walk(pj)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
              and n.func.id == "_should_force_steel_kg"]
    assert not soltas, "o forçador voltou solto no process_job: linhas %s" % soltas


def test_o_eval_de_invariantes_nao_acusa_a_verba():
    """A camada 2 da bancada usa a mesma regra: verba em vb não é 'aço fora de
    kg'; aço em m² continua sendo."""
    sys.path.insert(0, os.path.join(os.path.dirname(_MAIN_PY), "evals"))
    from check_invariants import check_project
    spec = {"steel_must_be_kg": True}

    def _falhou(itens):
        return [n for n, ok, _ in check_project(itens, {}, spec)
                if n == "aço/armadura sempre em kg" and not ok]

    assert not _falhou([{"description": _VERBA, "unit": "vb", "quantity": 1}])
    assert _falhou([{"description": "Armadura CA-50", "unit": "m²", "quantity": 37}])
