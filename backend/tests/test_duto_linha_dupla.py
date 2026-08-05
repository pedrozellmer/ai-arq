# -*- coding: utf-8 -*-
"""Duto desenhado em LINHA DUPLA nao pode virar o dobro de metro.

Caso real (04/08/2026, cliente de climatizacao): o duto no CAD e desenhado
como as DUAS faces, uma de cada lado do eixo. Somando o comprimento do layer,
cada trecho conta duas vezes. Entregamos metro inflado pra cliente de verdade.

═══ O QUE A REVISAO ADVERSARIAL DE 04/08 PEGOU, e que a 1ª versao deste
    arquivo NAO conseguia reprovar ═══

1. UNIDADE. start/end sao coordenadas CRUAS, mas `length` ja vem em METRO.
   A 1ª versao dividia um produto vetorial cru por `length` em metro: a
   separacao saia dividida pelo fator ao quadrado. Em desenho de milimetro dava
   600.000 e NADA pareava -- o conserto era inerte em quase todo DXF real.
   O teste antigo nao pegava porque montava tudo com unit_factor = 1.
2. SOBREPOSICAO. Sem exigir que os dois segmentos se sobreponham ao longo da
   direcao, um eixo tracejado no mesmo layer (mais perto) ganhava da face
   oposta: as duas faces ficavam de pe, o dobro continuava, E o relato ainda
   anunciava um conserto que nao aconteceu.
3. ARCO. Cotovelo nunca pareia (o filtro de comprimento parecido reprova arcos
   concentricos). Reto vira eixo, curva continua em dobro -> superestima.
4. HACHURA. O aviso existia mas ninguem lia: morria no log e o item saia
   carimbado MEDIDO. Agora vai em chave separada, com leitor.
"""
import math
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dwg_extractor import _corrigir_duto_linha_dupla  # noqa: E402

ok = falhas = 0


class W:
    """Minimo que a funcao consome. `length` em METRO, start/end CRUS.

    🪤 Esta e a mudanca que faz o teste conseguir reprovar o defeito nº1: o
    comprimento nasce do desenho bruto MULTIPLICADO pelo fator, como no motor.
    """

    def __init__(self, layer, start, end, uf=1.0, curvo=False, length=None):
        self.layer = layer
        self.start = start
        self.end = end
        self.curvo = curvo
        self.length = length if length is not None else math.dist(start, end) * uf


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


def duto_reto(layer, comprimento_m, uf=1.0, y0=0.0, largura_m=0.40, x0=0.0):
    """As duas faces de um trecho reto, desenhadas na unidade do arquivo."""
    c = comprimento_m / uf                      # bruto
    larg = largura_m / uf
    return [
        W(layer, (x0, y0), (x0 + c, y0), uf),
        W(layer, (x0, y0 + larg), (x0 + c, y0 + larg), uf),
    ]


print("== 1) FUNCIONA EM QUALQUER UNIDADE DE DESENHO ==")
# Este bloco e o que reprova o defeito nº1. Antes, so uf=1.0 passava.
for nome, uf in [("metro", 1.0), ("decimetro", 0.1), ("centimetro", 0.01),
                 ("milimetro", 0.001)]:
    walls = duto_reto("HVAC-DUTOS-INS", 10.0, uf=uf)
    novos, rel, _ = _corrigir_duto_linha_dupla(walls, uf)
    saiu = soma(novos, "HVAC-DUTOS-INS")
    checa(f"desenho em {nome}: 10 m nas 2 faces sai ~10 m, nao 20 m",
          abs(saiu - 10.0) < 0.05, f"saiu {saiu:.2f} m")

print()
print("== 2) NAO PAREIA O QUE NAO SE SOBREPOE ==")

# O eixo tracejado no MESMO layer: esta mais PERTO de uma face que a outra face.
# Escolher por menor separacao casava face+eixo e deixava as duas faces de pe.
walls = [
    W("HVAC-DUTOS-INS", (0, 0.0), (10, 0.0)),      # face de baixo
    W("HVAC-DUTOS-INS", (0, 0.6), (10, 0.6)),      # face de cima
    W("HVAC-DUTOS-INS", (0, 0.3), (10, 0.3)),      # eixo tracejado
]
novos, rel, _ = _corrigir_duto_linha_dupla(walls, 1.0)
saiu = soma(novos, "HVAC-DUTOS-INS")
checa("com eixo tracejado junto, o duto de 10 m nao sai valendo 20 m",
      saiu <= 20.5, f"saiu {saiu:.2f} m")

# Dois trechos paralelos que nem se olham: um termina onde o outro comeca.
walls = [
    W("HVAC-DUTOS-EXA", (0, 0), (10, 0)),
    W("HVAC-DUTOS-EXA", (30, 0.5), (40, 0.5)),     # 20 m adiante, sem sobrepor
]
antes = soma(walls, "HVAC-DUTOS-EXA")
novos, rel, _ = _corrigir_duto_linha_dupla(walls, 1.0)
checa("trechos paralelos SEM sobreposicao longitudinal: nao pareia",
      abs(soma(novos, "HVAC-DUTOS-EXA") - antes) < 0.01,
      f"{antes:.1f} -> {soma(novos, 'HVAC-DUTOS-EXA'):.1f}")

# Sobreposicao pequena demais (10%) tambem nao vale.
walls = [
    W("HVAC-DUTOS-EXA", (0, 0), (10, 0)),
    W("HVAC-DUTOS-EXA", (9, 0.5), (19, 0.5)),
]
antes = soma(walls, "HVAC-DUTOS-EXA")
novos, _, _ = _corrigir_duto_linha_dupla(walls, 1.0)
checa("sobreposicao de so 10%: nao pareia",
      abs(soma(novos, "HVAC-DUTOS-EXA") - antes) < 0.01)

print()
print("== 3) CURVA (ARC) FICA DE FORA — E O CLIENTE FICA SABENDO ==")

walls = duto_reto("HVAC-DUTOS-INS", 10.0)
# cotovelo de 90 graus: faces concentricas de raio 1,0 e 1,4
walls += [
    W("HVAC-DUTOS-INS", (0, 0), (1.0, 1.0), curvo=True, length=math.pi / 2 * 1.0),
    W("HVAC-DUTOS-INS", (0, 0), (1.4, 1.4), curvo=True, length=math.pi / 2 * 1.4),
]
novos, rel, ress = _corrigir_duto_linha_dupla(walls, 1.0)
checa("curva de duto e denunciada como fora do pareamento",
      "curva" in ress.lower() and "ARC" in ress, ress)
checa("o trecho reto continua sendo corrigido mesmo com curva no layer",
      "eixo" in rel, rel)

print()
print("== 4) HACHURA: RESSALVA SEPARADA, COM LEITOR ==")

# 400 pedacinhos de 5 cm: e o padrao grafico que preenche o duto.
walls = [W("IM DUCTO SUMINISTRO", (i * 0.06, 0), (i * 0.06 + 0.05, 0.02))
         for i in range(400)]
novos, rel, ress = _corrigir_duto_linha_dupla(walls, 1.0)
checa("layer todo em micro-segmento vira RESSALVA, nao relato informativo",
      "hachura" in ress and "NÃO confiável" in ress, ress)
checa("a ressalva NAO se mistura com o relato de eixo",
      "hachura" not in rel, rel)
checa("mesmo denunciando, nao apaga o dado do cliente",
      len(novos) == len(walls))

# Layer de trecho de verdade nao pode ser acusado de hachura.
walls = duto_reto("HVAC-DUTOS-EXA", 12.0) + duto_reto("HVAC-DUTOS-EXA", 8.0, y0=5.0)
_, _, ress = _corrigir_duto_linha_dupla(walls, 1.0)
checa("layer com trecho de verdade nao vira 'hachura'", "hachura" not in ress, ress)

print()
print("== 5) A RESSALVA CHEGA NA TRAVA DE PROCEDENCIA (regra dura nº1) ==")
from engine_rules import extraction_has_quality_caveat  # noqa: E402

checa("hachura de duto rebaixa o desenho pra estimado",
      extraction_has_quality_caveat({"duto_medicao_suspeita": "x"}) is True)
checa("o relato informativo de eixo NAO rebaixa (nao e ressalva)",
      extraction_has_quality_caveat({"duto_linha_dupla": "x"}) is False)

print()
print("== 6) LAYER QUE NAO E DUTO: NAO ENCOSTA ==")
for layer in ("A-WALL", "PAREDE", "ELETRODUTO", "LCVP_TUB_FRIG",
              "PRUMADA-AF", "CANALETA-PISO", "ARQ-PRODUTO"):
    walls = duto_reto(layer, 10.0)
    antes = soma(walls, layer)
    novos, _, _ = _corrigir_duto_linha_dupla(walls, 1.0)
    checa(f"{layer}: intacto", abs(soma(novos, layer) - antes) < 1e-9)

print()
print("== 7) O QUE NAO PODE SER PAREADO ==")

walls = [W("HVAC-DUTOS-INS", (0, 0), (10, 0)), W("HVAC-DUTOS-INS", (0, 4.0), (10, 4.0))]
novos, _, _ = _corrigir_duto_linha_dupla(walls, 1.0)
checa("separacao de 4 m nao e secao de duto: nao pareia",
      abs(soma(novos, "HVAC-DUTOS-INS") - 20.0) < 0.01)

walls = [W("HVAC-DUTOS-INS", (0, 0), (10, 0)), W("HVAC-DUTOS-INS", (0, 0.01), (10, 0.01))]
novos, _, _ = _corrigir_duto_linha_dupla(walls, 1.0)
checa("separacao de 1 cm e espessura de chapa: nao pareia",
      abs(soma(novos, "HVAC-DUTOS-INS") - 20.0) < 0.01)

walls = [W("HVAC-DUTOS-INS", (0, 0), (10, 0)), W("HVAC-DUTOS-INS", (0, 0.4), (0.4, 10))]
antes = soma(walls, "HVAC-DUTOS-INS")
novos, _, _ = _corrigir_duto_linha_dupla(walls, 1.0)
checa("linhas em direcoes diferentes: nao pareia",
      abs(soma(novos, "HVAC-DUTOS-INS") - antes) < 0.01)

walls = [W("HVAC-DUTOS-INS", (0, 0), (10, 0))]
novos, _, _ = _corrigir_duto_linha_dupla(walls, 1.0)
checa("linha unica (desenho ja em eixo): fica como esta",
      abs(soma(novos, "HVAC-DUTOS-INS") - 10.0) < 0.01)

print()
print("== 8) DESENHO SEM DUTO NENHUM: SILENCIO ==")
walls = duto_reto("A-WALL", 10.0) + duto_reto("PAREDE", 6.0, y0=3.0)
novos, rel, ress = _corrigir_duto_linha_dupla(walls, 1.0)
checa("nada de duto: relato e ressalva vazios, desenho intacto",
      rel == "" and ress == "" and len(novos) == len(walls))

print()
print(f"RESULTADO: {ok} passaram, {falhas} falharam")
sys.exit(1 if falhas else 0)
