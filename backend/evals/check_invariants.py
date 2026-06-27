# -*- coding: utf-8 -*-
"""Rede de segurança — camada 2: checa INVARIANTES de um projeto processado de
verdade contra um "gabarito" (golden.json). Diferente da camada 1 (que testa as
regras puras), aqui a gente valida o RESULTADO real do motor: o projeto fechou?
tem itens na faixa esperada? as disciplinas certas? aço em kg? não saiu zerado?

Como a IA varia de rodada pra rodada, NÃO checa número exato — checa FAIXAS e
REGRAS que sempre têm que valer. O checador é puro e testável
(tests/test_check_invariants.py); a busca dos itens vem de fora (via banco).

Uso: python evals/check_invariants.py <itens.json> <chave_do_golden>
  <itens.json>: {"project_type": "...", "items": [{description, unit, quantity, ...}]}
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from engine_rules import should_force_steel_kg  # noqa: E402


def check_project(items, project_meta, spec):
    """Retorna lista de (nome_da_checagem, passou:bool, detalhe:str)."""
    items = items or []
    n = len(items)
    out = []

    out.append(("processou com itens (nunca 0)", n > 0, f"{n} itens"))

    lo = spec.get("min_items", 0)
    hi = spec.get("max_items", 10 ** 9)
    out.append((f"itens na faixa {lo}-{hi}", lo <= n <= hi, f"{n} itens"))

    discs = sorted({(it.get("discipline") or "").strip() for it in items if (it.get("discipline") or "").strip()})
    for d in spec.get("must_have_disciplines", []):
        out.append((f"tem disciplina '{d}'", d in discs, f"disciplinas: {discs}"))

    if spec.get("project_type"):
        pt = (project_meta or {}).get("project_type")
        out.append((f"project_type = {spec['project_type']}", pt == spec["project_type"], f"veio: {pt}"))

    if spec.get("steel_must_be_kg"):
        bad = [it for it in items
               if should_force_steel_kg(it.get("description", "") or "")
               and (it.get("unit") or "").lower() != "kg"]
        amostra = "; ".join((b.get("description", "") or "")[:40] for b in bad[:3])
        out.append(("aço/armadura sempre em kg", not bad, f"{len(bad)} fora de kg. {amostra}"))

    if spec.get("not_all_zero"):
        nonzero = sum(1 for it in items if (it.get("quantity") or 0))
        out.append(("tem quantidade (não 100% zerado)", nonzero > 0, f"{nonzero}/{n} com qty"))

    if "max_zero_ratio" in spec and n:
        zeros = sum(1 for it in items if not (it.get("quantity") or 0))
        ratio = zeros / n
        lim = spec["max_zero_ratio"]
        out.append((f"zerados <= {int(lim*100)}%", ratio <= lim, f"{int(ratio*100)}% zerado"))

    return out


def _main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    if len(sys.argv) < 3:
        print("uso: python evals/check_invariants.py <itens.json> <chave_do_golden>")
        sys.exit(2)
    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)
    golden_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden.json")
    with open(golden_path, encoding="utf-8") as f:
        golden = json.load(f)
    key = sys.argv[2]
    if key not in golden:
        print(f"chave '{key}' não está no golden.json. Disponíveis: {list(golden)}")
        sys.exit(2)
    spec = golden[key]
    results = check_project(data.get("items", []), data, spec)
    print(f"== EVAL: {key} — {spec.get('description', '')} ==")
    n_fail = 0
    for nome, ok, det in results:
        print(f"  {'ok ' if ok else 'XX '} {nome}  [{det}]")
        if not ok:
            n_fail += 1
    print(f"\n{'PASSOU' if not n_fail else f'FALHOU ({n_fail})'}")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    _main()
