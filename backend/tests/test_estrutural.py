# -*- coding: utf-8 -*-
"""Rede de segurança — medição ESTRUTURAL determinística (structural_extractor.py
+ integração no dwg_extractor). Roda em segundos: `python tests/test_estrutural.py`.

O que trava:
  1. Tabela de aço BR (célula por célula, vírgula decimal) é lida CERTA: kg por
     bitola + total, validados por massa linear NBR 7480 e pela soma × total.
  2. Pilares como retângulos fechados em layer de PILAR são CONTADOS (com seção
     lida da geometria) — antes viravam só "perímetro somado" e a IA não tinha
     como contar (qty=0).
  3. Vigas: comprimento por layer sai como REFERÊNCIA (estimado) — nunca medido,
     porque viga desenhada pelas 2 faces dobra o eixo. Laje: área de contorno
     fechado sai medida (área, NUNCA volume).
  4. HONESTIDADE (regra nº1): quando o layer/tabela NÃO existe, NADA é inventado
     — prancha de arquitetura não ganha seção estrutural, blocos de porta P1/P2
     não viram pilar, leitura inconsistente vira "não confiável" (estimado).

Usa DXF SINTÉTICO criado via ezdxf no próprio teste (sem depender de arquivo
real) — mesmo espírito do tests/test_engine_rules.py.
"""
import io
import math
import os
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from structural_extractor import (  # noqa: E402
    StructRect,
    count_pillars,
    extract_structural_measurements,
    massa_linear_kg_m,
    measure_beams,
    measure_slabs,
    parse_steel_table,
    structural_prompt_section,
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


class T:
    """TextAnnotation fake (duck-typed) pra testar o parser isolado."""
    def __init__(self, text, x=0.0, y=0.0, h=50.0, layer="TAB"):
        self.text = text
        self.position = (x, y)
        self.height = h
        self.layer = layer


class NS:
    """Namespace genérico (BlockCount/WallSegment/HatchArea/extraction fakes)."""
    def __init__(self, **kw):
        self.__dict__.update(kw)


# ═══════════════════════════════════════════════════════════════════
print("== parse_steel_table — tabela célula a célula (vírgula BR) ==")
# ═══════════════════════════════════════════════════════════════════
tab = [
    T("RESUMO DE AÇO - CA-50", 0, 1200),
    T("BITOLA (mm)", 0, 1000), T("COMP. TOTAL (m)", 800, 1000), T("PESO (kg)", 1800, 1000),
    T("Ø 6.3", 0, 800), T("184,50", 800, 800), T("45,20", 1800, 800),
    T("Ø 8.0", 0, 600), T("245,60", 800, 600), T("97,00", 1800, 600),
    T("Ø 10.0", 0, 400), T("393,84", 800, 400), T("243,00", 1800, 400),
    T("TOTAL", 0, 200), T("385,20", 1800, 200),
]
r = parse_steel_table(tab)
check("achou tabela", r is not None)
kg = {e["bitola_mm"]: e["kg"] for e in r["por_bitola"]}
check("kg por bitola certo (vírgula BR)", kg == {6.3: 45.20, 8.0: 97.00, 10.0: 243.00})
comp = {e["bitola_mm"]: e["comp_m"] for e in r["por_bitola"]}
check("comprimento por bitola certo", comp == {6.3: 184.50, 8.0: 245.60, 10.0: 393.84})
check("classe CA-50 propagada", all(e["aco"] == "CA-50" for e in r["por_bitola"]))
check("total lido (385,20)", r["total_kg"] == 385.20)
check("soma bate com total → confiável", r["confiavel"] is True)

print("== parse_steel_table — coluna PESO (kg/m) NÃO vaza pro peso ==")
tab2 = [
    T("BITOLA", 0, 1000), T("PESO (kg/m)", 700, 1000), T("PESO (kg)", 1500, 1000),
    T("Ø 8.0", 0, 800), T("0,395", 700, 800), T("97,00", 1500, 800),
]
r2 = parse_steel_table(tab2)
check("pegou 97,00 (não a massa linear 0,395)",
      r2 and {e["bitola_mm"]: e["kg"] for e in r2["por_bitola"]} == {8.0: 97.00})

print("== parse_steel_table — modo linha (texto único com 'kg') ==")
r3 = parse_steel_table([T("AÇO CA-60 Ø 5.0 - 12,50 kg", 0, 100)])
check("linha única lida", r3 and r3["por_bitola"] == [
    {"bitola_mm": 5.0, "kg": 12.50, "comp_m": None, "aco": "CA-60"}])
r4 = parse_steel_table([T("PESO TOTAL: 1.385,20 kg", 0, 100)])
check("total avulso com milhar BR (1.385,20)", r4 and r4["total_kg"] == 1385.20)

print("== parse_steel_table — honestidade: inconsistência NUNCA vira medido ==")
tab5 = [
    T("BITOLA", 0, 1000), T("PESO (kg)", 1500, 1000),
    T("Ø 8.0", 0, 800), T("97,00", 1500, 800),
    T("TOTAL", 0, 600), T("500,00", 1500, 600),   # total ≠ soma (linhas faltando)
]
r5 = parse_steel_table(tab5)
check("soma ≠ total → confiavel=False", r5 and r5["confiavel"] is False)
tab6 = [
    T("BITOLA", 0, 1000), T("COMP. TOTAL (m)", 700, 1000), T("PESO (kg)", 1500, 1000),
    T("Ø 12.5", 0, 800), T("100,00", 700, 800), T("500,00", 1500, 800),  # 100m de Ø12.5 ≈ 96 kg, não 500
]
r6 = parse_steel_table(tab6)
check("peso incoerente com massa linear → linha descartada + não confiável",
      r6 is None or (not r6["por_bitola"] and r6["confiavel"] is False)
      or (r6["confiavel"] is False and not r6["por_bitola"]))
check("sem texto de aço → None (não inventa)",
      parse_steel_table([T("SALA DE ESTAR"), T("PISO PORCELANATO 60x60")]) is None)
check("massa linear NBR 7480 (Ø10 = 0,617 kg/m)",
      abs(massa_linear_kg_m(10.0) - 0.617) < 0.001)

# ═══════════════════════════════════════════════════════════════════
print("== count_pillars — dedupe + blocos + não inventa ==")
# ═══════════════════════════════════════════════════════════════════
r_a = StructRect(layer="EST-PILAR", w_m=0.19, h_m=0.40, w_raw=190, h_raw=400, cx=0, cy=0)
r_b = StructRect(layer="EST-PILAR", w_m=0.18, h_m=0.39, w_raw=180, h_raw=390, cx=5, cy=5)  # contorno duplo interno
r_c = StructRect(layer="EST-PILAR", w_m=0.19, h_m=0.40, w_raw=190, h_raw=400, cx=3000, cy=0)
ext_p = NS(struct_rects=[r_a, r_b, r_c], texts=[T("P1", 0, 300), T("P7", 3000, 300)],
           blocks=[NS(name="PILAR-MET", count=3, layer="EST-PILARES")])
rp = count_pillars(ext_p)
check("contorno duplo deduplicado (3 rects → 2 pilares)", rp and rp["rects_qtd"] == 2)
check("total soma blocos de pilar (2 + 3)", rp and rp["total"] == 5)
check("seção 19x40 medida da geometria",
      rp and rp["por_secao"][0]["secao_cm"] == "19x40 cm" and rp["por_secao"][0]["qtd"] == 2)
check("nomes P1/P7 associados por proximidade",
      rp and sorted(rp["por_secao"][0]["nomes"]) == ["P1", "P7"])
check("rect em layer não-pilar não conta",
      count_pillars(NS(struct_rects=[StructRect("ARQ-DET", 0.2, 0.4, 200, 400, 0, 0)],
                       texts=[], blocks=[])) is None)
check("bloco de porta P1 em layer de porta NÃO vira pilar",
      count_pillars(NS(struct_rects=[], texts=[],
                       blocks=[NS(name="P1", count=6, layer="ARQ-PORTAS")])) is None)

print("== vigas/lajes — só com geometria clara; nunca volume ==")
ext_v = NS(walls=[NS(layer="EST-VIGAS", length=5.0), NS(layer="EST-VIGAS", length=7.0),
                  NS(layer="ARQ-PAREDE", length=30.0)])
rv = measure_beams(ext_v)
check("viga: soma só o layer de viga (12 m)",
      rv and rv["por_layer"] == [{"layer": "EST-VIGAS", "m": 12.0, "eixo": False}])
check("viga por faces = REFERÊNCIA (eixo=False → estimado)", rv["por_layer"][0]["eixo"] is False)
check("viga em layer de EIXO é medida",
      measure_beams(NS(walls=[NS(layer="EIXO-VIGA", length=10.0)]))["por_layer"][0]["eixo"] is True)
check("sem layer de viga → None (não inventa)",
      measure_beams(NS(walls=[NS(layer="PAREDE", length=50.0)])) is None)
rl = measure_slabs(NS(polygon_areas=[NS(layer="LAJE-10", area=20.0),
                                     NS(layer="PISO", area=80.0)]))
check("laje: só polígono em layer de laje (20 m²)",
      rl and rl["por_layer"] == [{"layer": "LAJE-10", "m2": 20.0, "contornos": 1}])
check("sem layer de laje → None (não inventa)",
      measure_slabs(NS(polygon_areas=[NS(layer="PISO", area=80.0)])) is None)

# ═══════════════════════════════════════════════════════════════════
print("== DXF SINTÉTICO estrutural (ezdxf) — fluxo real do extrator ==")
# ═══════════════════════════════════════════════════════════════════
import ezdxf  # noqa: E402
from dwg_extractor import extract_dxf  # noqa: E402

doc = ezdxf.new("R2018", setup=False)
doc.header["$INSUNITS"] = 4  # milímetros (padrão BR)
msp = doc.modelspace()

# tabela de aço (célula por célula, como sai do CAD de verdade)
_tab_cells = [
    ("RESUMO DE AÇO - CA-50", 20000, 1200),
    ("BITOLA (mm)", 20000, 1000), ("COMP. TOTAL (m)", 20800, 1000), ("PESO (kg)", 21800, 1000),
    ("Ø 6.3", 20000, 800), ("184,50", 20800, 800), ("45,20", 21800, 800),
    ("Ø 8.0", 20000, 600), ("245,60", 20800, 600), ("97,00", 21800, 600),
    ("Ø 10.0", 20000, 400), ("393,84", 20800, 400), ("243,00", 21800, 400),
    ("TOTAL", 20000, 200), ("385,20", 21800, 200),
]
for _txt, _x, _y in _tab_cells:
    msp.add_text(_txt, dxfattribs={"layer": "EST-QUADRO", "height": 50,
                                   "insert": (_x, _y)})

# 4 pilares 19x40 cm como retângulos FECHADOS no layer de pilar + rótulos P1..P4
for i in range(4):
    x0 = i * 4000
    msp.add_lwpolyline([(x0, 0), (x0 + 190, 0), (x0 + 190, 400), (x0, 400)],
                       close=True, dxfattribs={"layer": "EST-PILAR"})
    msp.add_text(f"P{i + 1}", dxfattribs={"layer": "EST-TEXTO", "height": 50,
                                          "insert": (x0 + 95, 600)})

# 2 vigas como polilinhas ABERTAS no layer de viga (5 m + 7 m)
msp.add_lwpolyline([(0, 2000), (5000, 2000)], dxfattribs={"layer": "EST-VIGAS"})
msp.add_lwpolyline([(0, 3000), (7000, 3000)], dxfattribs={"layer": "EST-VIGAS"})

# 1 laje 4x5 m como polilinha FECHADA no layer de laje
msp.add_lwpolyline([(0, 5000), (4000, 5000), (4000, 10000), (0, 10000)],
                   close=True, dxfattribs={"layer": "LAJE-TIPO"})

with tempfile.TemporaryDirectory() as td:
    _dxf_path = os.path.join(td, "forma_teste.dxf")
    doc.saveas(_dxf_path)
    ext = extract_dxf(_dxf_path)

struct = extract_structural_measurements(ext)
check("aço lido do DXF (3 bitolas)", "aco" in struct and len(struct["aco"]["por_bitola"]) == 3)
if "aco" in struct:
    _kg = {e["bitola_mm"]: e["kg"] for e in struct["aco"]["por_bitola"]}
    check("kg por bitola certo no DXF", _kg == {6.3: 45.20, 8.0: 97.00, 10.0: 243.00})
    check("total + consistente no DXF",
          struct["aco"]["total_kg"] == 385.20 and struct["aco"]["confiavel"] is True)
check("4 pilares contados no DXF",
      struct.get("pilares", {}).get("total") == 4 and struct["pilares"]["rects_qtd"] == 4)
if "pilares" in struct:
    _sec = struct["pilares"]["por_secao"][0]
    check("seção 19x40 cm no DXF (unidade mm→m ok)", _sec["secao_cm"] == "19x40 cm" and _sec["qtd"] == 4)
    check("rótulos P1..P4 no DXF", sorted(_sec["nomes"]) == ["P1", "P2", "P3", "P4"])
check("vigas 12 m como referência no DXF",
      struct.get("vigas", {}).get("por_layer") == [{"layer": "EST-VIGAS", "m": 12.0, "eixo": False}])
check("laje 20 m² medida no DXF",
      struct.get("lajes", {}).get("por_layer") == [{"layer": "LAJE-TIPO", "m2": 20.0, "contornos": 1}])

prompt = ext.to_structured_prompt()
check("prompt tem a seção MEDIÇÕES ESTRUTURAIS", "MEDIÇÕES ESTRUTURAIS DETERMINÍSTICAS" in prompt)
check("prompt: aço por bitola [MEDIDO]", "[MEDIDO] Aço CA-50 Ø 8.0 mm: 97.00 kg" in prompt)
check("prompt: pilares [MEDIDO] com contagem", "[MEDIDO] 4 pilares contados" in prompt)
check("prompt: viga é [REFERÊNCIA] (estimado)", "[REFERÊNCIA] layer 'EST-VIGAS': 12.00 m" in prompt)
check("prompt: laje [MEDIDO] em m²", "[MEDIDO] layer 'LAJE-TIPO': 20.00 m²" in prompt)
check("prompt: volume NUNCA medido", "NÃO foram medidos" in prompt and "estimado" in prompt)

# ═══════════════════════════════════════════════════════════════════
print("== DXF SINTÉTICO de ARQUITETURA — NÃO inventa medição estrutural ==")
# ═══════════════════════════════════════════════════════════════════
doc2 = ezdxf.new("R2018", setup=False)
doc2.header["$INSUNITS"] = 4
msp2 = doc2.modelspace()
blk = doc2.blocks.new(name="P1")  # P1 aqui é PORTA (código de esquadria), não pilar
blk.add_line((0, 0), (800, 0))
for i in range(6):
    msp2.add_blockref("P1", (i * 3000, 0), dxfattribs={"layer": "ARQ-PORTAS"})
msp2.add_lwpolyline([(0, 0), (10000, 0)], dxfattribs={"layer": "ARQ-PAREDE"})
msp2.add_lwpolyline([(0, 2000), (4000, 2000), (4000, 6000), (0, 6000)],
                    close=True, dxfattribs={"layer": "ARQ-PISO"})
msp2.add_text("SALA 15,00 m²", dxfattribs={"layer": "ARQ-TEXTO", "height": 50,
                                           "insert": (100, 100)})

with tempfile.TemporaryDirectory() as td:
    _dxf2 = os.path.join(td, "planta_arq.dxf")
    doc2.saveas(_dxf2)
    ext2 = extract_dxf(_dxf2)

struct2 = extract_structural_measurements(ext2)
check("arquitetura → nenhuma medição estrutural inventada", struct2 == {})
check("blocos P1 (porta) seguem contados como bloco normal, não pilar",
      any(b.name == "P1" and b.count == 6 for b in ext2.blocks))
prompt2 = ext2.to_structured_prompt()
check("prompt de arquitetura SEM seção estrutural",
      "MEDIÇÕES ESTRUTURAIS" not in prompt2)

print()

# ══════════════════════════════════════════════════════════════════════
#  DESENHO QUE NUMERA OS LAYERS (Isabelle, 05/08/2026)
# ══════════════════════════════════════════════════════════════════════
# A planta de fôrma de um prédio de 7 pavimentos entregou 1 item medido: os
# layers dela se chamam '02', '4', '5', '100' e layer_is_pilar não casa com
# nada, então a geometria era descartada antes de qualquer medição.
# Quando nenhum layer tem significado, o RÓTULO vira o filtro.
_n1 = StructRect(layer="4", w_m=0.19, h_m=0.40, w_raw=190, h_raw=400, cx=0, cy=0)
_n2 = StructRect(layer="4", w_m=0.19, h_m=0.40, w_raw=190, h_raw=400, cx=3000, cy=0)
_n3 = StructRect(layer="4", w_m=0.25, h_m=0.25, w_raw=250, h_raw=250, cx=6000, cy=0)
_rot = count_pillars(NS(struct_rects=[_n1, _n2, _n3],
                        texts=[T("P10", 0, 0), T("P11", 3000, 0), T("P12", 6000, 0)],
                        blocks=[]))
check("layer numerado: conta pelos rotulos", _rot and _rot["total"] == 3)
check("layer numerado: marca procedencia", _rot and _rot.get("por_rotulo") is True)

# 🔒 O atalho NAO pode disparar quando o layer JA tem significado — ali quem
# manda e o nome, e rotulo solto nao entra.
_ok = count_pillars(NS(struct_rects=[StructRect("EST-PILAR", 0.19, 0.40, 190, 400, 0, 0),
                                     StructRect("EST-PILAR", 0.19, 0.40, 190, 400, 3000, 0)],
                       texts=[T("P1", 0, 0)], blocks=[]))
check("layer com significado: nao usa o atalho", _ok and _ok.get("por_rotulo") is False)

# 🔒 QUADRO DE ESQUADRIAS: celulas retangulares com P1/P2 dentro. E exatamente
# o padrao que o atalho procura — a sanidade de secao tem que barrar.
_cel = [StructRect(layer="3", w_m=6.0, h_m=1.2, w_raw=6000, h_raw=1200, cx=0, cy=0),
        StructRect(layer="3", w_m=6.0, h_m=1.2, w_raw=6000, h_raw=1200, cx=0, cy=1500)]
check("quadro de esquadrias NAO vira pilar",
      count_pillars(NS(struct_rects=_cel,
                       texts=[T("P1", 0, 0), T("P2", 0, 1500)], blocks=[])) is None)

# 🔒 Um retangulo rotulado sozinho e acaso, nao medicao.
check("um rotulo so nao basta",
      count_pillars(NS(struct_rects=[_n1], texts=[T("P10", 0, 0)], blocks=[])) is None)

print(f"RESULTADO: {_passed} ok, {_failed} falhas")
sys.exit(1 if _failed else 0)
