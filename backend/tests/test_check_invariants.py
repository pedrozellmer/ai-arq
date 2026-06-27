# -*- coding: utf-8 -*-
"""Testa o CHECADOR de invariantes da camada 2 (evals/check_invariants.py). O
checador precisa pegar resultado ruim — senão a rede de segurança não protege.
Roda: `python tests/test_check_invariants.py`."""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_here, ".."))
sys.path.insert(0, os.path.join(_here, "..", "evals"))

from check_invariants import check_project  # noqa: E402

_passed = 0
_failed = 0


def check(nome, cond):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok  {nome}")
    else:
        _failed += 1
        print(f"  XX  FALHOU: {nome}")


def fails(results):
    return [r[0] for r in results if not r[1]]


SPEC_ARCH = {"min_items": 10, "max_items": 100, "not_all_zero": True}
SPEC_ESTRUT = {"project_type": "estrutura", "min_items": 5, "max_items": 90,
               "must_have_disciplines": ["Estrutura"], "steel_must_be_kg": True}


print("== resultado BOM passa ==")
bom = [{"description": "parede drywall", "unit": "m2", "quantity": 120, "discipline": "Fechamentos Verticais"}] * 20
check("arquitetura boa -> sem falhas", fails(check_project(bom, {"project_type": "arquitetura"}, SPEC_ARCH)) == [])

print("== pega 0 itens (bug Vinicius) ==")
r = check_project([], {"project_type": "arquitetura"}, SPEC_ARCH)
check("0 itens -> falha 'processou com itens'", "processou com itens (nunca 0)" in fails(r))

print("== pega tudo zerado (bug Magno) ==")
zerado = [{"description": "x", "unit": "un", "quantity": 0, "discipline": "Complementares"}] * 12
check("tudo zerado -> falha 'tem quantidade'", "tem quantidade (não 100% zerado)" in [f for f in fails(check_project(zerado, {}, SPEC_ARCH))])

print("== pega faixa de itens fora ==")
poucos = [{"description": "x", "unit": "m2", "quantity": 5}] * 3
check("poucos itens -> falha faixa", any("faixa" in f for f in fails(check_project(poucos, {}, SPEC_ARCH))))

print("== estrutural: aço em m2 e pego (bug Luciano) ==")
estrut_ruim = [
    {"description": "Armadura de aço CA-50 pilares", "unit": "m2", "quantity": 1007, "discipline": "Estrutura"},
    {"description": "Concreto C25", "unit": "m3", "quantity": 10, "discipline": "Estrutura"},
]
check("aço em m2 -> falha 'aço sempre kg'", "aço/armadura sempre em kg" in fails(check_project(estrut_ruim, {"project_type": "estrutura"}, SPEC_ESTRUT)))

print("== estrutural: aço em kg passa ==")
estrut_bom = [
    {"description": "Armadura de aço CA-50 pilares", "unit": "kg", "quantity": 1007, "discipline": "Estrutura"},
    {"description": "Estribos CA-60 vigas", "unit": "kg", "quantity": 50, "discipline": "Estrutura"},
    {"description": "Concreto estrutural C25 pilares", "unit": "m3", "quantity": 10, "discipline": "Estrutura"},
    {"description": "Concreto estrutural C25 vigas", "unit": "m3", "quantity": 8, "discipline": "Estrutura"},
    {"description": "Fôrma compensado", "unit": "m2", "quantity": 60, "discipline": "Estrutura"},
]
check("estrutural certo -> sem falhas", fails(check_project(estrut_bom, {"project_type": "estrutura"}, SPEC_ESTRUT)) == [])

print("== estrutural: sem disciplina Estrutura e pego (bug Magno/Complementares) ==")
sem_estrut = [{"description": "Concreto", "unit": "m3", "quantity": 5, "discipline": "Complementares"}] * 6
check("tudo Complementares -> falha 'tem disciplina Estrutura'", "tem disciplina 'Estrutura'" in fails(check_project(sem_estrut, {"project_type": "estrutura"}, SPEC_ESTRUT)))

print()
print(f"RESULTADO: {_passed} passaram, {_failed} falharam")
sys.exit(1 if _failed else 0)
