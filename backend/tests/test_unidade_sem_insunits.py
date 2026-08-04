# -*- coding: utf-8 -*-
"""Escolha da unidade quando o desenho NÃO declara ($INSUNITS = 0).

🚨 Este é o teste da função de MAIOR RISCO do extrator. O fator de unidade
multiplica TODO número medido de TODO projeto — errar aqui não estraga uma
linha, estraga a planilha inteira de todo mundo. Por isso os casos que
importam mais aqui são os NEGATIVOS: provar que a regra não encosta em
desenho que já funciona.

Caso que a originou (04/08/2026, cliente ConfortAr — climatização hospitalar):
DWG sem $INSUNITS, desenho em METROS, 425 unidades de largura. O padrão "mm"
transformava o hospital num desenho de 42 cm e dividia todo comprimento por
mil: 169 m de duto de insuflamento viravam 0,17 m, que a IA descartou como
"fragmento de legenda". A cliente tinha perguntado, antes de criar conta, se a
gente media duto.

Conferido contra os 28 DXF reais da máquina: 27 mantiveram o fator, só o dela
mudou.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import ezdxf  # noqa: E402

from dwg_extractor import _detect_unit_factor  # noqa: E402

_passed = 0
_failed = 0


def check(nome, cond):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok  {nome}")
    else:
        _failed += 1
        print(f"  XX  {nome}")


def _doc(insunits, largura_unidades, n_entidades):
    """Monta um DXF sintético com a extensão e a densidade pedidas."""
    d = ezdxf.new("R2010")
    d.header["$INSUNITS"] = insunits
    msp = d.modelspace()
    passo = largura_unidades / max(n_entidades, 1)
    for i in range(n_entidades):
        x = i * passo
        msp.add_line((x, 0), (x + passo, largura_unidades * 0.01))
    d.header["$EXTMIN"] = (0.0, 0.0, 0.0)
    d.header["$EXTMAX"] = (largura_unidades, largura_unidades, 0.0)
    return d


# ── 🔒 O que NÃO pode mudar: desenho que declara a unidade ───────────────────
check("declara mm (4): mantem 0.001", _detect_unit_factor(_doc(4, 20000, 800)) == 0.001)
check("declara cm (5): mantem 0.01", _detect_unit_factor(_doc(5, 2000, 800)) == 0.01)
check("declara m  (6): mantem 1.0", _detect_unit_factor(_doc(6, 30, 800)) == 1.0)

# ── 🔒 Sem declarar, mas o mm é plausível: não encosta ───────────────────────
# Casa de 20 m desenhada em mm = 20.000 unidades. mm dá 20 m: correto, fica.
check("sem declarar + mm plausivel (casa 20m): mantem mm",
      _detect_unit_factor(_doc(0, 20000, 900)) == 0.001)
# Terreno de 300 m em mm = 300.000 unidades.
check("sem declarar + terreno grande em mm: mantem mm",
      _detect_unit_factor(_doc(0, 300000, 900)) == 0.001)

# ── 🔒 Detalhe pequeno: pouca entidade, não arrisca inferir ──────────────────
check("sem declarar + poucas entidades (detalhe): mantem mm",
      _detect_unit_factor(_doc(0, 400, 50)) == 0.001)

# ── ✅ O caso real: prancha densa que em mm vira um desenho absurdo ──────────
# 425 unidades de largura: mm daria 42 cm de hospital. Só metro faz sentido.
check("HOSPITAL sem declarar, 425 un: vira METRO",
      _detect_unit_factor(_doc(0, 425, 900)) == 1.0)

# 🪤 Quando cm E metro são plausíveis, ganha o MENOR fator — subestimar é
# menos grave que inflar (regra nº1). Com 1200 unidades, cm dá um desenho de
# 12 m (apartamento) e metro daria 1.200 m (terreno): os dois existem, então
# fica o conservador. O caso da cliente não tem essa dúvida — cm daria 5,26 m,
# fora da faixa de prancha, e só metro sobra.
check("ambiguo (cm e m plausiveis): fica no MENOR fator",
      _detect_unit_factor(_doc(0, 1200, 900)) == 0.01)

# ── 🔒 Ambíguo demais: devolve o padrão e não inventa ────────────────────────
# 5 unidades de largura: nem cm (5 cm) nem m (5 m) caem na faixa de prancha.
check("largura minuscula e ambigua: mantem mm",
      _detect_unit_factor(_doc(0, 5, 900)) == 0.001)

# ── 🔒 Sem extensão no cabeçalho: não há evidência, mantém padrão ────────────
_sem_ext = ezdxf.new("R2010")
_sem_ext.header["$INSUNITS"] = 0
for _i in range(600):
    _sem_ext.modelspace().add_line((_i, 0), (_i + 1, 1))
_sem_ext.header["$EXTMIN"] = (0.0, 0.0, 0.0)
_sem_ext.header["$EXTMAX"] = (0.0, 0.0, 0.0)
check("sem extensao no cabecalho: mantem mm", _detect_unit_factor(_sem_ext) == 0.001)

print()
print(f"RESULTADO: {_passed} passaram, {_failed} falharam")
sys.exit(1 if _failed else 0)
