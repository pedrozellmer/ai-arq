# -*- coding: utf-8 -*-
"""Rede de segurança — camada 1: testa as REGRAS DETERMINÍSTICAS do motor
(engine_rules.py) sem chamar a IA. Roda em segundos: `python tests/test_engine_rules.py`.

Cada teste trava um comportamento que JÁ quebrou ou que NÃO pode quebrar. Vários
codificam bugs reais de 27/06 (caso Luciano/Ademir/Magno) pra nunca voltarem.
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from engine_rules import (  # noqa: E402
    extract_balanced_obj,
    salvage_truncated_json,
    normalize_items_payload,
    should_force_steel_kg,
    is_likely_wrong_type,
    extraction_has_quality_caveat,
    extract_block_name,
    is_nonsense_item,
    extract_type_code,
    response_truncated,
)

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


print("== extract_balanced_obj ==")
obj, end = extract_balanced_obj('{"a":1}', 0)
check("objeto balanceado simples", obj == '{"a":1}' and end == 7)
obj, _ = extract_balanced_obj('{"a":1', 0)
check("truncado -> None", obj is None)
obj, _ = extract_balanced_obj('{"a":"x}y"}', 0)
check("chave } dentro de string nao fecha cedo", obj == '{"a":"x}y"}')
obj, _ = extract_balanced_obj('{"a":"esc\\"}", "b":1}', 0)
check("aspas escapada respeitada", obj == '{"a":"esc\\"}", "b":1}')

print("== salvage_truncated_json (caso Ademir: JSON cortado no teto) ==")
trunc = ('{"project_data": {"name": "SSP-PE", "total_area": 1200}, "items": [\n'
         '  {"item_num":"1","description":"parede drywall {especial}","unit":"m","quantity":120},\n'
         '  {"item_num":"2","description":"piso 60x60","unit":"m2","quantity":340},\n'
         '  {"item_num":"3","description":"forro de gesso cor')
r = salvage_truncated_json(trunc)
check("recupera 2 itens completos do truncado", len(r["items"]) == 2)
check("ignora o 3o item cortado", all(i["item_num"] in ("1", "2") for i in r["items"]))
check("chave-em-string nao confunde o parser", r["items"][0]["quantity"] == 120)
check("recupera project_data", r.get("project_data", {}).get("name") == "SSP-PE")
full = '{"items":[{"item_num":"1","quantity":1},{"item_num":"2","quantity":2}]}'
check("json completo -> todos os itens", len(salvage_truncated_json(full)["items"]) == 2)
check("lixo -> items vazio (nunca lanca)", salvage_truncated_json("xpto")["items"] == [])

print("== normalize_items_payload (caso Luciano: 'list' object has no attribute get) ==")
check("array cru vira {items:[...]}", normalize_items_payload([{"a": 1}, {"b": 2}]) == {"items": [{"a": 1}, {"b": 2}]})
check("dict passa intacto", normalize_items_payload({"items": [1]}) == {"items": [1]})
check("None -> items vazio", normalize_items_payload(None) == {"items": []})
check("string -> items vazio", normalize_items_payload("xpto") == {"items": []})

print("== should_force_steel_kg (caso Luciano: aco sempre kg, nunca m2) ==")
check("estribos -> forca kg", should_force_steel_kg("Estribos ∅5 mm CA-50 — Vigas Piso 1") is True)
check("aco S-400 -> forca kg", should_force_steel_kg("Aço S-400 — Pilar tipo peso unitário 20,5 kg") is True)
check("armadura em aco -> forca kg", should_force_steel_kg("Pilares de concreto armado — armadura em aço CA-50") is True)
check("forma NAO vira kg (e m2)", should_force_steel_kg("Vigas de concreto armado — fôrma em compensado") is False)
check("forma com armadura no texto ainda e forma", should_force_steel_kg("Fôrma de pilar com armadura aparente") is False)
check("concreto NAO vira kg (e m3)", should_force_steel_kg("Pilares de concreto armado — fck C25/30 — concreto") is False)
check("item de arquitetura nao vira kg", should_force_steel_kg("Piso porcelanato 60x60") is False)
check("vazio nao vira kg", should_force_steel_kg("") is False)

print("== is_likely_wrong_type (caso Magno: estrutural que e arquitetura) ==")
check("Magno 6/6 zerado -> dispara", is_likely_wrong_type([0, 0, 0, 0, 0, 0]) is True)
luciano = [0] * 15 + [1.5] * 19   # 34 itens, 44% zerado (estrutural REAL)
check("Luciano 44% zerado -> NAO dispara", is_likely_wrong_type(luciano) is False)
check("tudo medido -> NAO dispara", is_likely_wrong_type([1, 2, 3, 4]) is False)
check("lista vazia -> NAO dispara", is_likely_wrong_type([]) is False)
check("exatamente 75% -> dispara (>=)", is_likely_wrong_type([0, 0, 0, 1]) is True)
check("None na qty conta como zero", is_likely_wrong_type([None, None, None, 5]) is True)

print("== extraction_has_quality_caveat (trava de procedencia, regra no1) ==")
check("metadata vazio -> sem ressalva", extraction_has_quality_caveat({}) is False)
check("None -> sem ressalva", extraction_has_quality_caveat(None) is False)
check("extracao normal -> sem ressalva", extraction_has_quality_caveat({"sinal_medido": 50}) is False)
check("esteril -> ressalva (forca estimado)", extraction_has_quality_caveat({"extracao_esteril": True}) is True)
check("unidade suspeita -> ressalva", extraction_has_quality_caveat({"unidade_suspeita": "x"}) is True)
check("alerta de unidade -> ressalva", extraction_has_quality_caveat({"alerta_unidade": "maior 600m"}) is True)
check("xref nao resolvido -> ressalva", extraction_has_quality_caveat({"xref_nao_resolvido": "arq.dwg"}) is True)

print("== extract_block_name (dedup de bloco — bug HWB: cadeira contada 2x) ==")
check("bloco CAD aspas simples", extract_block_name("Cadeira ... bloco CAD 'cad-escr-02'") == "cad-escr-02")
check("bloco aspas simples", extract_block_name("Geladeira (bloco 'geladeira010')") == "geladeira010")
check("bloco com acento", extract_block_name("Fogao, bloco 'fogão'") == "fogão")
check("case-insensitive vira chave minuscula", extract_block_name("bloco CAD 'Geladeira'") == "geladeira")
check("sem bloco -> None", extract_block_name("Piso vinilico em m2") is None)
check("alvenaria bloco ceramico SEM aspas -> None", extract_block_name("Alvenaria de bloco ceramico ou de concreto") is None)
check("descricao vazia -> None", extract_block_name("") is None)

print("== is_nonsense_item / extract_type_code (caso Thamiry: drywall inflado 284 itens) ==")
check("secao transversal -> nonsense", is_nonsense_item("Area de secao transversal de paredes drywall") is True)
check("area de secao -> nonsense", is_nonsense_item("área de seção de parede no layer A-WALL") is True)
check("item normal -> NAO nonsense", is_nonsense_item("Divisoria drywall DRY 07") is False)
check("DRY 07 -> tipo 'DRY 07'", extract_type_code("Divisoria drywall tipo DRY 07 — espessura 95mm") == "DRY 07")
check("DW-12 -> tipo 'DW 12'", extract_type_code("Parede DW-12 chapa dupla") == "DW 12")
check("PAREDE (sem num) -> None", extract_type_code("Parede de alvenaria comum") is None)
check("vedacao generica -> None (nao funde sem codigo)", extract_type_code("sistema de vedacao em drywall") is None)

print("== response_truncated (#7 leitura incompleta: corte no teto de tokens) ==")
check("max_tokens -> truncado (avisa incompleta)", response_truncated("max_tokens") is True)
check("end_turn -> NAO truncado", response_truncated("end_turn") is False)
check("stop_sequence -> NAO truncado", response_truncated("stop_sequence") is False)
check("None -> NAO truncado (nao falsea aviso)", response_truncated(None) is False)
check("vazio -> NAO truncado", response_truncated("") is False)
check("espaco em volta nao engana", response_truncated(" max_tokens ") is True)

print()
print(f"RESULTADO: {_passed} passaram, {_failed} falharam")
sys.exit(1 if _failed else 0)
