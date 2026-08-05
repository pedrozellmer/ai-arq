# -*- coding: utf-8 -*-
"""Rede de segurança — "régua da prancha": validação da unidade pelas COTAS
(DIMENSION) do DXF (dwg_extractor._validate_unit_by_dimensions + integração no
extract_dxf). Roda em segundos: `python tests/test_cotas_dxf.py`.

O que trava:
  1. Desenho em mm com cotas exibidas em cm (texto literal E "<>" com DIMLFAC)
     VALIDA o fator detectado → metadata + "VALIDADA POR N COTAS" no prompt.
  2. $INSUNITS mentindo (diz metros, desenho em cm) é CORRIGIDO pro fator que
     as cotas provam — medidas saem certas e a correção fica registrada, SEM
     virar "unidade_suspeita" (correção não é suspeita, é fator provado).
  3. Cotas conflitantes → NADA muda (regra nº1: na dúvida, comportamento antigo).
  4. Cota ANGULAR é ignorada (não é régua linear) — e não envenena a contagem.
  5. Override não-numérico ("VER DETALHE") e texto suprimido (" ") ficam fora.

Usa DXF SINTÉTICO criado via ezdxf no próprio teste (sem depender de arquivo
real) — mesmo espírito de tests/test_estrutural.py e tests/test_engine_rules.py.
"""
import io
import os
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import ezdxf  # noqa: E402

from dwg_extractor import (  # noqa: E402
    extract_dxf,
    _validate_unit_by_dimensions,
    correcao_e_absurda,
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


def novo_doc(insunits):
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = insunits
    return doc


def cota_linear(msp, p1, p2, text="<>", dimlfac=None):
    """Cota linear horizontal renderizada (ezdxf exige render pro bloco)."""
    override = {"dimlfac": dimlfac} if dimlfac is not None else None
    dim = msp.add_linear_dim(base=(p1[0], p1[1] + 400), p1=p1, p2=p2,
                             text=text, override=override)
    dim.render()
    return dim


def roundtrip(doc):
    """Salva o doc num DXF temporário e roda o extrator de verdade."""
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "planta_teste.dxf")
        doc.saveas(path)
        return extract_dxf(path)


# ═══════════════════════════════════════════════════════════════════
print("== (i) desenho em mm ($INSUNITS=4) com cotas em cm → VALIDA ==")
# ═══════════════════════════════════════════════════════════════════
# Geometria em milímetros; textos das cotas em centímetros (padrão BR:
# "350" numa residência = 3,50 m). Inclui uma cota SEM override de texto
# ("<>") cujo número exibido vem de DIMLFAC=0.1 (mm → cm no texto).
doc = novo_doc(4)  # mm
msp = doc.modelspace()
msp.add_line((0, 0), (3500, 0), dxfattribs={"layer": "ARQ-PAREDE"})
cota_linear(msp, (0, 0), (3500, 0), text="350")
cota_linear(msp, (0, -1500), (1200, -1500), text="120")
cota_linear(msp, (0, -3000), (4150, -3000), text="415")
cota_linear(msp, (0, -4500), (620, -4500), text="62")
cota_linear(msp, (0, -6000), (2800, -6000), text="<>", dimlfac=0.1)  # exibe 280

ext = roundtrip(doc)
prompt = ext.to_structured_prompt()
check("fator de mm mantido (0.001)", ext.metadata.get("fator_para_metros") == "0.001")
check("metadata: validada por 5 cotas",
      ext.metadata.get("unidade_validada_por_cotas") == 5)
check("metadata: unidade provada = milímetros",
      ext.metadata.get("unidade_nome_provada") == "milímetros")
check("prompt: 'VALIDADA POR 5 COTAS DA PRANCHA'",
      "VALIDADA POR 5 COTAS DA PRANCHA" in prompt)
check("parede de 3500mm mede 3,50 m",
      any(abs(w.length - 3.5) < 0.01 for w in ext.walls))
check("nenhuma correção registrada (fator já estava certo)",
      "unidade_corrigida_por_cotas" not in ext.metadata)

# ═══════════════════════════════════════════════════════════════════
print("== (ii) $INSUNITS mente (diz metros, desenho em cm) → CORRIGE ==")
# ═══════════════════════════════════════════════════════════════════
# Geometria em centímetros com cotas em cm (razão 1:1), mas o header jura
# que é metros. As cotas provam cm: "350" = 3,50 m sobre medida 350.
doc2 = novo_doc(6)  # header diz METROS (errado)
msp2 = doc2.modelspace()
msp2.add_line((0, 0), (350, 0), dxfattribs={"layer": "ARQ-PAREDE"})
cota_linear(msp2, (0, 0), (350, 0), text="350")
cota_linear(msp2, (0, -150), (120, -150), text="120")
cota_linear(msp2, (0, -300), (415, -300), text="415")
cota_linear(msp2, (0, -450), (62, -450), text="62")

ext2 = roundtrip(doc2)
prompt2 = ext2.to_structured_prompt()
check("fator corrigido pra cm (0.01)", ext2.metadata.get("fator_para_metros") == "0.01")
check("metadata registra a correção",
      "corrigida" in ext2.metadata.get("unidade_corrigida_por_cotas", "")
      and "4 cotas" in ext2.metadata.get("unidade_corrigida_por_cotas", ""))
check("metadata: unidade provada = centímetros",
      ext2.metadata.get("unidade_nome_provada") == "centímetros")
check("prompt anuncia 'CORRIGIDA PELA PRÓPRIA PRANCHA'",
      "CORRIGIDA PELA PRÓPRIA PRANCHA" in prompt2)
check("parede de 350cm virou 3,50 m (não 350 m)",
      any(abs(w.length - 3.5) < 0.01 for w in ext2.walls))
check("correção NÃO virou 'unidade_suspeita' (não rebaixa pra estimado)",
      "unidade_suspeita" not in ext2.metadata)

# ═══════════════════════════════════════════════════════════════════
print("== (iii) cotas CONFLITANTES entre si → NADA muda (regra nº1) ==")
# ═══════════════════════════════════════════════════════════════════
# Duas cotas apontam pra um mundo (texto = medida/10), duas pra outro
# (texto = medida). Nenhum fator alcança 3 cotas + 80% → abstenção total.
doc3 = novo_doc(4)  # mm
msp3 = doc3.modelspace()
msp3.add_line((0, 0), (3500, 0), dxfattribs={"layer": "ARQ-PAREDE"})
cota_linear(msp3, (0, 0), (3500, 0), text="350")
cota_linear(msp3, (0, -1500), (1200, -1500), text="120")
cota_linear(msp3, (0, -3000), (35, -3000), text="35")
cota_linear(msp3, (0, -4500), (48, -4500), text="48")

ext3 = roundtrip(doc3)
prompt3 = ext3.to_structured_prompt()
check("fator intocado (0.001)", ext3.metadata.get("fator_para_metros") == "0.001")
check("sem selo de validação", "unidade_validada_por_cotas" not in ext3.metadata)
check("sem correção", "unidade_corrigida_por_cotas" not in ext3.metadata)
check("prompt sem 'VALIDADA POR' nem 'CORRIGIDA PELA'",
      "VALIDADA POR" not in prompt3 and "CORRIGIDA PELA" not in prompt3)

# ═══════════════════════════════════════════════════════════════════
print("== (iv) cota ANGULAR é ignorada (não é régua linear) ==")
# ═══════════════════════════════════════════════════════════════════
# 3 cotas lineares válidas + 2 angulares. Se a angular entrasse na conta,
# o "<>" dela (90° × dimlfac do estilo) viraria voto falso e derrubaria a
# maioria de 80% — a validação por exatamente 3 cotas prova o filtro.
doc4 = novo_doc(4)  # mm
msp4 = doc4.modelspace()
msp4.add_line((0, 0), (3500, 0), dxfattribs={"layer": "ARQ-PAREDE"})
cota_linear(msp4, (0, 0), (3500, 0), text="350")
cota_linear(msp4, (0, -1500), (1200, -1500), text="120")
cota_linear(msp4, (0, -3000), (4150, -3000), text="415")
ang1 = msp4.add_angular_dim_3p(base=(500, -6000), center=(0, -6500),
                               p1=(500, -6500), p2=(0, -6000), text="45")
ang1.render()
ang2 = msp4.add_angular_dim_3p(base=(2500, -6000), center=(2000, -6500),
                               p1=(2500, -6500), p2=(2000, -6000))
ang2.render()

ext4 = roundtrip(doc4)
check("validada por EXATAMENTE 3 cotas (angulares fora)",
      ext4.metadata.get("unidade_validada_por_cotas") == 3)
check("fator de mm mantido (0.001)", ext4.metadata.get("fator_para_metros") == "0.001")

# ═══════════════════════════════════════════════════════════════════
print("== (v) override 'VER DETALHE' e texto suprimido ficam FORA ==")
# ═══════════════════════════════════════════════════════════════════
doc5 = novo_doc(4)  # mm
msp5 = doc5.modelspace()
msp5.add_line((0, 0), (3500, 0), dxfattribs={"layer": "ARQ-PAREDE"})
cota_linear(msp5, (0, 0), (3500, 0), text="350")
cota_linear(msp5, (0, -1500), (1200, -1500), text="120")
cota_linear(msp5, (0, -3000), (4150, -3000), text="415")
cota_linear(msp5, (0, -4500), (7777, -4500), text="VER DETALHE")
cota_linear(msp5, (0, -6000), (8888, -6000), text="VARIÁVEL")
cota_linear(msp5, (0, -7500), (9999, -7500), text=" ")  # texto suprimido

ext5 = roundtrip(doc5)
check("validada por EXATAMENTE 3 cotas (overrides não-numéricos fora)",
      ext5.metadata.get("unidade_validada_por_cotas") == 3)
check("fator de mm mantido (0.001)", ext5.metadata.get("fator_para_metros") == "0.001")

print()


# ══════════════════════════════════════════════════════════════════════
#  DETALHE EM MILÍMETRO NÃO PODE VIRAR METRO (erro de 1000×)
# ══════════════════════════════════════════════════════════════════════
# Achado em 05/08/2026 por contraexemplo adversarial: num desenho de DETALHE
# honesto em mm (rodapé, esquadria), o texto da cota diz "80" e a geometria
# mede 80 unidades — o validador concluía METRO e trocava 0,001 por 1,0,
# multiplicando a planilha por mil. Estava ARMADO em produção (nunca disparou:
# 0 de 132 projetos CAD).
# 🪤 DIMLFAC não separa os casos: o rodapé (correção errada) e a casa_quadra02
# (correção CERTA) têm os dois LFAC efetivo = 1. Quem separa é a física.
# Números medidos nos arquivos REAIS, sob o fator que seria adotado:
#     casa_quadra02 (certa)   : 580 cotas, mediana 1,20 m,  0% acima de 30 m
#     CX5 / CX6     (erradas) :   4 cotas, mediana 11,50 m, 25% acima de 30 m
#     CX1           (errada)  :   5 cotas, mediana 34,00 m, 60% acima de 30 m
check("rodape em mm lido como metro e recusado",
      correcao_e_absurda([80.0, 45.0, 66.0, 15.0]) is True)
check("esquadria em mm lida como metro e recusada",
      correcao_e_absurda([34.0, 38.0, 45.0, 30.5, 33.0]) is True)
# 🔒 O legitimo NAO pode ser barrado — casa_quadra02 tem cotas de comodo e
# nenhuma passa de 30 m.
check("planta de casa continua sendo corrigida",
      correcao_e_absurda([1.2, 2.8, 4.1, 6.15, 22.55, 3.0]) is False)
check("galpao com vao grande nao e barrado (1 de 12 acima de 30 m)",
      correcao_e_absurda([2.0, 3.5, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0,
                          15.0, 20.0, 28.0, 42.0]) is False)
check("lista vazia nao quebra", correcao_e_absurda([]) is False)

print(f"RESULTADO: {_passed} ok, {_failed} falhas")
sys.exit(1 if _failed else 0)
