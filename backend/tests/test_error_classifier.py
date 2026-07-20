# -*- coding: utf-8 -*-
"""Rede de regressão do QW2 (20/07): classificação HONESTA de erro.

Trava pra sempre o cenário Rodrigo (19/07): um model-id errado dava 404 em todo
DXF e o sistema carimbava "IA sobrecarregada, reprocesse" → cliente em loop
infinito. Regra nova: só 'transient' com PROVA (429/529/timeout/overloaded);
404/401/403/413/invalid_request/surrogate são 'permanent'; o resto é 'unknown'
(NÃO vira 'sobrecarga'). O default deixou de ser transitório.

Roda direto: `python tests/test_error_classifier.py`.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm_retry import classify_error_text as c  # noqa: E402

CASES = [
    # (texto do erro achatado, veredito esperado)
    ("[status=529] Error code: 529 - overloaded_error", "transient"),
    ("Error code: 429 - rate_limit_error", "transient"),
    ("read timed out", "transient"),
    ("[status=503] service unavailable", "transient"),
    ("connection aborted", "transient"),
    # cenário Rodrigo: model-id errado → 404 → NUNCA 'sobrecarga'
    ("[status=404] Error code: 404 - not_found_error: model xyz", "permanent"),
    ("[status=400] invalid_request_error: invalid high surrogate", "permanent"),
    ("[status=401] authentication_error", "permanent"),
    ("[status=413] request too large", "permanent"),
    ("surrogate quebrado no texto do CAD", "permanent"),
    # desconhecido: default HONESTO (não-transitório)
    ("JSON parse error: Expecting value line 1", "unknown"),
    ("algum erro esquisito sem token conhecido", "unknown"),
    ("", "unknown"),
    (None, "unknown"),
    # permanente vence transitório quando os dois aparecem (nunca culpar provedor
    # havendo prova de erro nosso)
    ("[status=400] invalid_request; connection reset", "permanent"),
]


def main_run():
    falhas = 0
    for texto, esperado in CASES:
        got = c(texto)
        ok = got == esperado
        if not ok:
            falhas += 1
        flag = "ok " if ok else "✗ FALHOU"
        amostra = (str(texto) or "<vazio>")[:52]
        print(f"  {flag}  {esperado:10} <- {amostra}")
    print("\n" + "=" * 46)
    print(f"RESULTADO: {len(CASES) - falhas} ok, {falhas} falhas")
    return falhas


if __name__ == "__main__":
    sys.exit(1 if main_run() else 0)
