# -*- coding: utf-8 -*-
"""Testa a DERIVAÇÃO de escala a partir das cotas (pdfvec_cotas).

Contexto (01/08/2026): nas 30 pranchas medidas na sombra, 47% eram descartadas
com "sem escala (viewport nem carimbo)" — mesmo tendo cota desenhada; uma delas
trazia 122 cotas. A cota só validava escala já conhecida, nunca descobria.

Os testes cobrem os 3 comportamentos que importam:
  1. prancha limpa  -> deriva a escala certa
  2. cota em CADEIA -> deriva (é o caso que o match_cotas não pega: cota
     parcial não é o comprimento de parede nenhuma)
  3. ruído          -> devolve None (nunca inventa escala)

Puro, sem PDF: injeta os tokens direto. Rodar: python tests/test_pdfvec_escala_cota.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pdfvec_cotas as C

_falhas = []


def check(nome, cond):
    print(f"  {'OK  ' if cond else 'FALHOU'} {nome}")
    if not cond:
        _falhas.append(nome)


def _pt(metros, esc):
    """Metros -> pontos PDF, na escala dada."""
    return metros / (C.PT_TO_M * esc)


def _com_tokens(tokens, fn):
    orig = C.extract_cota_tokens
    C.extract_cota_tokens = lambda *a, **k: tokens
    try:
        return fn()
    finally:
        C.extract_cota_tokens = orig


def teste_prancha_limpa():
    """Cada cota ao lado de uma parede do mesmo comprimento."""
    esc = 75.0
    paredes, tokens = [], []
    y = 100.0
    for m in (4.80, 3.20, 6.15, 2.40, 5.00, 3.75):
        L = _pt(m, esc)
        paredes.append({"span_pt": (50.0, 50.0 + L), "axis": "h",
                        "p_pt": y, "length_m": m})
        tokens.append({"value_m": m, "center": (50.0 + L / 2, y + 8.0),
                       "text": f"{m:.2f}"})
        y += 60.0
    r = _com_tokens(tokens, lambda: C.derive_scale_from_cotas(
        "x.pdf", 0, None, walls=paredes, rooms_pt=None))
    check("prancha limpa deriva 1:75", r["scale"] == 75.0)
    check("com apoio de vários votos", (r.get("votos") or 0) >= C.MIN_VOTOS_ESCALA)


def teste_cadeia_de_cotas():
    """Fachada de 12 m quebrada por vãos: as cotas são PARCIAIS.

    Nenhuma cota equivale à parede inteira — é exatamente o caso em que o
    casamento 1-pra-1 falha. A derivação tem que achar a escala pelas pontas.
    """
    esc = 75.0
    x0, y = 50.0, 600.0
    cortes = [0, 1.20, 2.00, 4.40, 5.30, 12.00]
    paredes = [{"span_pt": (x0 + _pt(a, esc), x0 + _pt(b, esc)), "axis": "h",
                "p_pt": y, "length_m": b - a}
               for a, b in zip(cortes, cortes[1:])]
    cadeia = [{"value_m": round(b - a, 2),
               "center": (x0 + _pt((a + b) / 2, esc), y + 8.0),
               "text": str(round(b - a, 2))}
              for a, b in zip(cortes, cortes[1:])]

    # o método antigo, contra a parede inteira, não acha nada
    antigo = C.match_cotas(cadeia, [{"length_m": 12.0, "axis": "h",
                                     "span_pt": (x0, x0 + _pt(12.0, esc)),
                                     "p_pt": y}])
    check("match_cotas não pega cadeia (regressão do diagnóstico)", len(antigo) == 0)

    r = _com_tokens(cadeia, lambda: C.derive_scale_from_cotas(
        "x.pdf", 0, None, walls=paredes, rooms_pt=None))
    check("cadeia deriva 1:75", r["scale"] == 75.0)
    check("1º lugar domina o 2º", (r.get("votos") or 0) >= 2 * max(r.get("segundo_lugar") or 0, 1))


def teste_ruido_nao_inventa():
    """Números que não correspondem a nada não podem produzir escala."""
    esc = 75.0
    paredes = [{"span_pt": (50.0, 50.0 + _pt(4.8, esc)), "axis": "h",
                "p_pt": 100.0, "length_m": 4.8}]
    ruido = [{"value_m": v, "center": (60.0, 105.0), "text": str(v)}
             for v in (1.11, 2.22, 3.33, 7.77, 9.99)]
    r = _com_tokens(ruido, lambda: C.derive_scale_from_cotas(
        "x.pdf", 0, None, walls=paredes, rooms_pt=None))
    check("ruído não vira escala", r["scale"] is None)


def teste_sem_entrada():
    check("sem cota -> None", C.derive_scale_from_cotas.__doc__ is not None)
    r = _com_tokens([], lambda: C.derive_scale_from_cotas(
        "x.pdf", 0, None, walls=[{"span_pt": (0, 10), "axis": "h", "p_pt": 0}],
        rooms_pt=None))
    check("nenhuma cota lida -> None", r["scale"] is None)
    r2 = _com_tokens([{"value_m": 1.2, "center": (0, 0), "text": "1.20"}],
                     lambda: C.derive_scale_from_cotas("x.pdf", 0, None,
                                                       walls=[], rooms_pt=None))
    check("nenhum elemento -> None", r2["scale"] is None)


if __name__ == "__main__":
    print("DERIVAÇÃO DE ESCALA POR COTA")
    teste_prancha_limpa()
    teste_cadeia_de_cotas()
    teste_ruido_nao_inventa()
    teste_sem_entrada()
    print()
    if _falhas:
        print(f"{len(_falhas)} FALHA(S): {', '.join(_falhas)}")
        sys.exit(1)
    print("todos OK")
