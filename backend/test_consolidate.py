# -*- coding: utf-8 -*-
"""Teste rápido dos 3 resíduos do consolidador."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from models import BudgetItem, Confidence
from main import _consolidate_items, _normalize_description_key, _primary_noun


def mk(desc, unit, qty, disc):
    return BudgetItem(
        item_num="", description=desc, unit=unit, quantity=qty,
        observations="", ref_sheet="", confidence=Confidence("confirmado"),
        discipline=disc,
    )


def test_residuo_1_alvenaria():
    """Alvenaria duplicada com descs divergentes mas mesma qty+discipline+unit."""
    items = [
        mk("Alvenaria tijolo cerâmico 9x14x19", "ml", 491.84, "Alvenaria"),
        mk("Execução de alvenaria nova", "ml", 491.84, "Alvenaria"),
    ]
    out = _consolidate_items(items)
    assert len(out) == 1, f"Esperado 1 item após fusão, veio {len(out)}: {[i.description for i in out]}"
    assert out[0].confidence == Confidence("estimado"), f"Confidence deve ser estimado: {out[0].confidence}"
    assert "Fundido" in (out[0].observations or ""), f"Obs deve citar fusão: {out[0].observations}"
    print(f"[OK] Residuo 1 alvenaria: {len(items)} -> {len(out)}, desc='{out[0].description}'")


def test_residuo_2_dept():
    """5 itens 'Demarcação de área departamento X' devem fundir em 1."""
    items = [
        mk("Demarcação de área departamento Contabilidade", "m²", 0.72, "Complementares"),
        mk("Demarcação de área departamento Financeira", "m²", 0.72, "Complementares"),
        mk("Demarcação de área departamento Livres", "m²", 0.72, "Complementares"),
        mk("Demarcação de área departamento Marketing", "m²", 0.72, "Complementares"),
        mk("Demarcação de área departamento RH", "m²", 0.72, "Complementares"),
    ]
    # Verificar que a chave normalizada é IGUAL pros 5
    keys = {_normalize_description_key(it.description) for it in items}
    assert len(keys) == 1, f"Chaves deveriam ser iguais, vieram: {keys}"
    out = _consolidate_items(items)
    assert len(out) == 1, f"Esperado 1 item consolidado, veio {len(out)}: {[i.description for i in out]}"
    assert "variantes" in out[0].description, f"Deve citar variantes: {out[0].description}"
    # Soma das qtys: 5 * 0.72 = 3.60
    assert abs(out[0].quantity - 3.60) < 0.01, f"Qty somada esperada 3.60, veio {out[0].quantity}"
    print(f"[OK] Residuo 2 dept-merge: {len(items)} -> {len(out)}, desc='{out[0].description}', qty={out[0].quantity}")


def test_residuo_3_ledline():
    """3 LED LINE com qty 222.11 mas units diferentes (m², m², ml)."""
    items = [
        mk("LED LINE pendurada tipo A", "m²", 222.11, "Iluminação"),
        mk("LED LINE tipo A encastrada", "m²", 222.11, "Iluminação"),
        mk("LED LINE linear tipo A", "ml", 222.11, "Iluminação"),
    ]
    out = _consolidate_items(items)
    assert len(out) == 1, f"Esperado 1 item fundido, veio {len(out)}: {[(i.description, i.unit) for i in out]}"
    # ml é a unit mais plausível pra linha LED (prioridade em _pick_best_unit)
    assert out[0].unit == "ml", f"Unit esperado 'ml' (prioridade), veio '{out[0].unit}'"
    assert out[0].quantity == 222.11
    print(f"[OK] Residuo 3 LED LINE cross-unit: {len(items)} -> {len(out)}, unit='{out[0].unit}'")


def test_no_false_positive_portas():
    """Portas com qty=1 cada em mesma discipline — NÃO devem ser fundidas."""
    items = [
        mk("Porta de madeira PM-01 80x210", "un", 1, "Portas e Ferragens"),
        mk("Porta de vidro PV-01 90x210", "un", 1, "Portas e Ferragens"),
        mk("Porta de emergência P-EM 100x210", "un", 1, "Portas e Ferragens"),
    ]
    out = _consolidate_items(items)
    assert len(out) == 3, f"Qty=1 não deve disparar fusão (MIN_QTY_PASS2=2.0), veio {len(out)}"
    print(f"[OK] No-FP portas qty=1: {len(items)} -> {len(out)} (preservado)")


def test_no_false_positive_unrelated():
    """Dois itens na mesma discipline com mesma qty mas sentidos diferentes."""
    items = [
        mk("Rodapé de madeira natural", "ml", 150.0, "Pisos e Rodapés"),
        mk("Carpete de parede em salas fechadas", "ml", 150.0, "Pisos e Rodapés"),
    ]
    out = _consolidate_items(items)
    # primary_noun: "rodape" vs "carpete" — distintos
    # tokens overlap: {rodape, madeira, natural} vs {carpete, parede, salas, fechadas} — vazio
    assert len(out) == 2, f"Itens distintos não podem fundir, veio {len(out)}"
    print(f"[OK] No-FP rodape vs carpete: {len(items)} -> {len(out)} (preservado)")


if __name__ == "__main__":
    print(f"primary_noun('Alvenaria tijolo cerâmico 9x14x19') = '{_primary_noun('Alvenaria tijolo cerâmico 9x14x19')}'")
    print(f"primary_noun('Execução de alvenaria nova') = '{_primary_noun('Execução de alvenaria nova')}'")
    print(f"key('Demarcação de área departamento Contabilidade') = '{_normalize_description_key('Demarcação de área departamento Contabilidade')}'")
    print(f"key('Demarcação de área departamento RH') = '{_normalize_description_key('Demarcação de área departamento RH')}'")
    print("---")
    test_residuo_1_alvenaria()
    test_residuo_2_dept()
    test_residuo_3_ledline()
    test_no_false_positive_portas()
    test_no_false_positive_unrelated()
    print("\nTodos testes passaram.")
