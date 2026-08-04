# -*- coding: utf-8 -*-
"""Duto desenhado em LINHA DUPLA nao pode virar o dobro de metro.

Caso real (04/08/2026, cliente de climatizacao): o duto no CAD e desenhado
como as DUAS faces, uma de cada lado do eixo. Somando o comprimento do layer,
cada trecho conta duas vezes. Entregamos metro inflado pra cliente de verdade.

O conserto pareia face com face (mesma direcao, separacao compativel com
seccao de duto) e descarta uma das duas, sobrando o equivalente ao eixo.

E tem o caso pior, que o mesmo arquivo mostrou: layer cujo comprimento e
quase todo HACHURA (milhares de pedacinhos e arcos, nenhum trecho longo).
Ali nao da pra parear nada — o certo e AVISAR que o total nao vale, nunca
entregar numero com cara de medicao (regra dura nº1).
"""
import math
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dwg_extractor import _corrigir_duto_linha_dupla  # noqa: E402

ok = falhas = 0


class W:
    """Minimo que a funcao consome de um segmento."""

    def __init__(self, layer, start, end):
        self.layer = layer
        self.start = start
        self.end = end
        self.length = math.dist(start, end)


def checa(titulo, condicao, detalhe=""):
    global ok, falhas
    if condicao:
        ok += 1
        print(f"  ok  {titulo}")
    else:
        falhas += 1
        print(f"  FALHA  {titulo}  {detalhe}")


def soma(walls, layer):
    return sum(w.length for w in walls if w.layer == layer)


def duto_reto(layer, comprimento, y0=0.0, largura=0.40, x0=0.0):
    """As duas faces de um trecho reto de duto."""
    return [
        W(layer, (x0, y0), (x0 + comprimento, y0)),
        W(layer, (x0, y0 + largura), (x0 + comprimento, y0 + largura)),
    ]


print("== DUTO EM LINHA DUPLA: 2 faces viram 1 eixo ==")

walls = duto_reto("HVAC-DUTOS-INS", 10.0)
novos, rel = _corrigir_duto_linha_dupla(walls)
checa("trecho de 10 m desenhado nas 2 faces sai como ~10 m, nao 20 m",
      abs(soma(novos, "HVAC-DUTOS-INS") - 10.0) < 0.01,
      f"saiu {soma(novos, 'HVAC-DUTOS-INS'):.2f} m")
checa("o conserto se explica no relato", "eixo" in rel, rel)

print()
print("== LAYER QUE NAO E DUTO: NAO ENCOSTA ==")

for layer in ("A-WALL", "PAREDE", "ELETRODUTO", "LCVP_TUB_FRIG",
              "PRUMADA-AF", "CANALETA-PISO", "ARQ-PRODUTO"):
    walls = duto_reto(layer, 10.0)
    antes = soma(walls, layer)
    novos, _ = _corrigir_duto_linha_dupla(walls)
    checa(f"{layer}: intacto",
          abs(soma(novos, layer) - antes) < 1e-9,
          f"{antes:.2f} -> {soma(novos, layer):.2f}")

print()
print("== O QUE NAO PODE SER PAREADO ==")

# Duas linhas longe demais: parede e duto, ou dois dutos diferentes.
walls = [W("HVAC-DUTOS-INS", (0, 0), (10, 0)),
         W("HVAC-DUTOS-INS", (0, 4.0), (10, 4.0))]
novos, _ = _corrigir_duto_linha_dupla(walls)
checa("separacao de 4 m nao e seccao de duto: nao pareia",
      abs(soma(novos, "HVAC-DUTOS-INS") - 20.0) < 0.01,
      f"saiu {soma(novos, 'HVAC-DUTOS-INS'):.2f} m")

# Encostadas demais: e a espessura da propria chapa, nao a seccao.
walls = [W("HVAC-DUTOS-INS", (0, 0), (10, 0)),
         W("HVAC-DUTOS-INS", (0, 0.01), (10, 0.01))]
novos, _ = _corrigir_duto_linha_dupla(walls)
checa("separacao de 1 cm e espessura de chapa: nao pareia",
      abs(soma(novos, "HVAC-DUTOS-INS") - 20.0) < 0.01,
      f"saiu {soma(novos, 'HVAC-DUTOS-INS'):.2f} m")

# Cruzadas: direcoes diferentes nunca sao as duas faces do mesmo trecho.
walls = [W("HVAC-DUTOS-INS", (0, 0), (10, 0)),
         W("HVAC-DUTOS-INS", (0, 0.4), (0.4, 10))]
antes = soma(walls, "HVAC-DUTOS-INS")
novos, _ = _corrigir_duto_linha_dupla(walls)
checa("linhas em direcoes diferentes: nao pareia",
      abs(soma(novos, "HVAC-DUTOS-INS") - antes) < 0.01)

# Uma face sozinha (a outra ficou em outro layer, ou o desenho e de eixo).
walls = [W("HVAC-DUTOS-INS", (0, 0), (10, 0))]
novos, _ = _corrigir_duto_linha_dupla(walls)
checa("linha unica (desenho ja em eixo): fica como esta",
      abs(soma(novos, "HVAC-DUTOS-INS") - 10.0) < 0.01)

print()
print("== HACHURA: AVISA EM VEZ DE ENTREGAR NUMERO ==")

# Layer com 400 pedacinhos de 5 cm: e o padrao grafico que preenche o duto.
# No arquivo real, um layer assim somava 169 m sem um unico trecho > 1 m.
walls = [W("IM DUCTO SUMINISTRO", (i * 0.06, 0), (i * 0.06 + 0.05, 0.02))
         for i in range(400)]
novos, rel = _corrigir_duto_linha_dupla(walls)
checa("layer todo em micro-segmento é denunciado como hachura",
      "hachura" in rel and "NÃO confiável" in rel, rel)
checa("mesmo denunciando, nao apaga o dado do cliente",
      len(novos) == len(walls))

# Layer de trechos de verdade nao pode ser acusado de hachura.
walls = duto_reto("HVAC-DUTOS-EXA", 12.0) + duto_reto("HVAC-DUTOS-EXA", 8.0, y0=5.0)
_, rel = _corrigir_duto_linha_dupla(walls)
checa("layer com trecho de verdade nao vira 'hachura'",
      "hachura" not in rel, rel)

print()
print("== DESENHO SEM DUTO NENHUM: SILENCIO ==")
walls = duto_reto("A-WALL", 10.0) + duto_reto("PAREDE", 6.0, y0=3.0)
novos, rel = _corrigir_duto_linha_dupla(walls)
checa("nada de duto: relato vazio e desenho intacto",
      rel == "" and len(novos) == len(walls), repr(rel))

print()
print(f"RESULTADO: {ok} passaram, {falhas} falharam")
sys.exit(1 if falhas else 0)
