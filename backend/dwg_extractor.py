# -*- coding: utf-8 -*-
"""Extrator de dados estruturados de arquivos DWG/DXF para orçamento.

Parte do backend ai.arq.br — gera dados quantitativos a partir de plantas
arquitetônicas em formato DWG/DXF usando a biblioteca ezdxf.

Suporta:
  - Arquivos .dxf diretamente
  - Arquivos .dwg via conversão com ODA File Converter
"""

import ezdxf
import logging
import math
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Optional

# Medição ESTRUTURAL determinística (tabela de aço, pilares, vigas, lajes).
# Import defensivo: se o módulo faltar num deploy parcial, o extrator segue
# funcionando sem a frente estrutural (nunca derruba o fluxo principal).
try:
    from structural_extractor import (
        StructRect,
        extract_structural_measurements,
        structural_prompt_section,
        layer_is_pilar,
    )
except Exception:  # pragma: no cover
    StructRect = None
    extract_structural_measurements = None
    structural_prompt_section = None
    layer_is_pilar = None

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Layers de INFRA LINEAR que podem ser medidos DENTRO de bloco
# ---------------------------------------------------------------------------
# 🔒 Regra nº1: esta lista é ALLOWLIST de propósito. Comprimento medido vira
# linha BRANCA, então termo frouxo aqui INVENTA medição. Só entra vocabulário
# de infraestrutura cuja quantidade legítima É o comprimento.
#
# Nasceu do caso de eletroduto (Engie, 21/07/2026) e por isso só falava a língua
# da ELÉTRICA. Em 04/08/2026 uma cliente de climatização (projeto hospitalar,
# ConfortAr) subiu um DWG com os dutos desenhados DENTRO de blocos: o motor
# achou as camadas `LCVP_DUTOS_INS`, `LCVP_DUTO_RET`, `LCVP_DUTO_EXAUSTAO`,
# `LCVP_TUBUL AAG` e `LCVP_TUB_FRIG`, mas NENHUMA casava aqui — 'duto' não
# existia e 'tubula' não pegava as abreviações. Resultado: 0 metro em todas as
# redes, que era exatamente a pergunta que ela tinha feito antes de se cadastrar.
#
# 🪤 Vive no MÓDULO, não dentro da função, pra poder ser testada. Enquanto
# morava lá dentro nenhum teste a alcançava — foi por isso que envelheceu
# faltando metade do vocabulário sem ninguém perceber.
#
# 🪤 `duto` exige que o caractere anterior NÃO seja letra, senão casa com
# "PRODUTO". Underscore e hífen (separadores de nome de layer) passam.
INFRA_LINEAR_RX = re.compile(
    r'eletrodut|eletrocal|condul|condut|condu[íi]t|conduit|prumad|'
    r'ramal|canaleta|perfilad|barramen|'      # 'leito' removido: colidia com LEITO HOSPITALAR
    r'tubul|'                                 # era 'tubula': não pegava TUBUL_AAG / TUB_FRIG
    r'(?<![a-z])duto|'                        # duto, dutos, dutoflex — mas NÃO produto
    r'(?<![a-z])frig',                        # TUB_FRIG, frigorígena, frigorífica
    re.IGNORECASE)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BlockCount:
    """Contagem de blocos (luminárias, portas, tomadas, etc.)"""
    name: str
    count: int
    layer: str = ""
    positions: list = field(default_factory=list)  # [(x,y)] coordinates
    # Dimensão aproximada em metros (bbox da definição × escala do INSERT médio).
    # Populado só pra blocos de esquadria (portas/janelas) — permite aplicar
    # regra TCPO de vãos (≤2m² não descontam da pintura).
    width_m: float = 0.0
    height_m: float = 0.0


@dataclass
class WallSegment:
    """Segmento de parede/linha com comprimento."""
    layer: str
    length: float  # in meters
    start: tuple = (0, 0)
    end: tuple = (0, 0)
    # ARC/CIRCLE: `length` é o comprimento do ARCO, mas start/end são as pontas
    # da CORDA. Quem faz geometria com start/end precisa saber disso — sem a
    # marca, o pareamento de faces de duto tratava curva como reta e o aviso
    # de "curva ficou de fora" nunca disparava.
    curvo: bool = False


@dataclass
class HatchArea:
    """Área hachurada (pintura, piso, forro)."""
    layer: str
    area: float  # in m²
    pattern: str = ""


@dataclass
class TextAnnotation:
    """Texto/legenda extraído."""
    layer: str
    text: str
    position: tuple = (0, 0)
    height: float = 0


@dataclass
class DXFExtraction:
    """Resultado completo da extração."""
    filename: str
    blocks: list  # list of BlockCount
    walls: list  # list of WallSegment
    hatches: list  # list of HatchArea
    texts: list  # list of TextAnnotation
    layers: list  # list of layer names
    dimensions: list  # list of (label, value) tuples
    metadata: dict = field(default_factory=dict)
    polygon_areas: list = field(default_factory=list)  # áreas de polilinha FECHADA (ambiente/piso/forro) — m² medido, fonte distinta de HATCH
    struct_rects: list = field(default_factory=list)  # retângulos/círculos FECHADOS em layer de PILAR (StructRect) — contagem de pilar medida

    # -- convenience helpers ------------------------------------------------

    def get_block_summary(self) -> dict:
        """Returns {block_name: total_count}."""
        summary: Counter = Counter()
        for b in self.blocks:
            summary[b.name] += b.count
        return dict(summary)

    def get_walls_by_layer(self) -> dict:
        """Returns {layer_name: total_length_meters}."""
        result: dict[str, float] = defaultdict(float)
        for w in self.walls:
            result[w.layer] += w.length
        return dict(result)

    def get_areas_by_layer(self) -> dict:
        """Returns {layer_name: total_area_m2}."""
        result: dict[str, float] = defaultdict(float)
        for h in self.hatches:
            result[h.layer] += h.area
        return dict(result)

    def get_polygon_areas_by_layer(self) -> dict:
        """Returns {layer_name: total_area_m2} de polilinhas FECHADAS (ambientes)."""
        result: dict[str, float] = defaultdict(float)
        for p in self.polygon_areas:
            result[p.layer] += p.area
        return dict(result)

    def get_texts_by_layer(self) -> dict:
        """Returns {layer_name: [text1, text2, ...]}."""
        result: dict[str, list] = defaultdict(list)
        for t in self.texts:
            result[t.layer].append(t.text)
        return dict(result)

    # -- prompt generation --------------------------------------------------

    def to_structured_prompt(self) -> str:
        """Converts extraction to a structured text prompt for Claude."""
        lines: list[str] = []
        lines.append(f"=== DADOS EXTRAÍDOS DO DXF: {self.filename} ===\n")

        # Metadata
        if self.metadata:
            lines.append("METADADOS DO ARQUIVO:")
            for k, v in self.metadata.items():
                lines.append(f"  {k}: {v}")
            lines.append("")

        # Avisos de qualidade da extração — a IA DEVE reagir marcando 'estimado'.
        if self.metadata.get("extracao_esteril"):
            lines.append("⚠ ATENÇÃO: a extração geométrica veio VAZIA (0 blocos/paredes/áreas/cotas). "
                         "NÃO gere itens de práxis como se fossem medidos — marque tudo que sugerir como "
                         "'estimado' (laranja). O arquivo pode estar sem geometria legível (xref, paperspace).")
            lines.append("")
        if self.metadata.get("xref_nao_resolvido"):
            lines.append(f"⚠ ATENÇÃO: este DXF referencia arquivo(s) externo(s) não carregado(s) (xref): "
                         f"{self.metadata['xref_nao_resolvido']}. A geometria do arquitetônico pode estar nesse "
                         f"xref e NÃO foi lida — trate as quantidades como 'estimado'.")
            lines.append("")
        if self.metadata.get("unidade_suspeita"):
            lines.append(f"⚠ ATENÇÃO: a unidade do desenho está suspeita ({self.metadata['unidade_suspeita']}). "
                         f"Comprimentos/áreas podem estar com a escala errada — marque os itens medidos como "
                         f"'estimado' até o usuário confirmar a unidade.")
            lines.append("")
        # "Régua da prancha" — unidade provada pelas próprias COTAS do desenho
        if self.metadata.get("unidade_corrigida_por_cotas"):
            lines.append(f"UNIDADE: CORRIGIDA PELA PRÓPRIA PRANCHA — "
                         f"{self.metadata['unidade_corrigida_por_cotas']}. As cotas (DIMENSION) são "
                         f"dado real do CAD: o texto exibido bateu com a medida geométrica num fator "
                         f"diferente do detectado. Todas as medidas abaixo JÁ usam o fator corrigido.")
            lines.append("")
        elif self.metadata.get("unidade_validada_por_cotas"):
            lines.append(f"UNIDADE: {self.metadata.get('unidade_nome_provada', '?')} — VALIDADA POR "
                         f"{self.metadata['unidade_validada_por_cotas']} COTAS DA PRANCHA "
                         f"(o texto exibido nas cotas bate com a medida geométrica; escala confiável).")
            lines.append("")

        # Layers — com xref prefix removido e deduplicado pra não poluir o prompt
        clean_layers = set()
        for layer in self.layers:
            # Layers de xref tem formato "xrefname|actual_layer" — usamos só a 2ª parte
            clean_name = layer.split("|", 1)[-1].strip()
            if clean_name:
                clean_layers.add(clean_name)
        lines.append(f"LAYERS ENCONTRADOS ({len(clean_layers)} únicos / {len(self.layers)} com xrefs):")
        for layer in sorted(clean_layers):
            lines.append(f"  - {layer}")
        lines.append("")

        # Block counts — separando esquadrias (com dimensão) dos demais
        block_summary = self.get_block_summary()
        if block_summary:
            # Blocos com dimensão extraída (esquadrias)
            esquadria_blocks = [b for b in self.blocks if b.width_m > 0 and b.height_m > 0]
            if esquadria_blocks:
                lines.append("ESQUADRIAS (dimensões aproximadas do bbox × escala do INSERT):")
                # deduplica por nome
                seen = set()
                for b in sorted(esquadria_blocks, key=lambda x: -x.count):
                    if b.name in seen:
                        continue
                    seen.add(b.name)
                    area = b.width_m * b.height_m
                    lines.append(
                        f"  {b.name}: {b.count} un  |  ~{b.width_m:.2f}m × {b.height_m:.2f}m = {area:.2f} m²"
                    )
                lines.append("  Regra TCPO: vãos com área ≤ 2 m² NÃO se desconta da pintura; > 2 m² desconta o excedente.")
                lines.append("")

            # Demais blocos (contagem simples)
            other = {name: count for name, count in block_summary.items()
                     if not any(b.name == name and b.width_m > 0 for b in self.blocks)}
            if other:
                lines.append(f"CONTAGEM DE BLOCOS ({len(other)} tipos):")
                for name, count in sorted(other.items(), key=lambda x: -x[1]):
                    lines.append(f"  {name}: {count} un")
                lines.append("")

        # Wall lengths
        walls_by_layer = self.get_walls_by_layer()
        if walls_by_layer:
            lines.append("COMPRIMENTOS POR LAYER:")
            for layer, length in sorted(walls_by_layer.items()):
                lines.append(f"  {layer}: {length:.2f} m")
            lines.append("")

        # Hatch areas
        areas_by_layer = self.get_areas_by_layer()
        if areas_by_layer:
            # Conta hachuras por layer: quando um layer tem VÁRIAS hachuras, a área
            # listada é a SOMA — e pode misturar acabamentos diferentes desenhados no
            # MESMO layer (porcelanato + cerâmica em "ARQ-PISO"). A soma não mede
            # nenhum acabamento sozinho, então a IA deve tratar como ESTIMADO, não
            # confirmado (regra nº1 — revisão adversarial 15/07, Finding 1).
            _hatch_n: dict[str, int] = defaultdict(int)
            for _h in self.hatches:
                _hatch_n[_h.layer] += 1
            lines.append("ÁREAS HACHURADAS POR LAYER:")
            for layer, area in sorted(areas_by_layer.items()):
                if _hatch_n.get(layer, 1) > 1:
                    lines.append(f"  {layer}: {area:.2f} m² (soma de {_hatch_n[layer]} hachuras — "
                                 f"pode ser acabamento MISTO no mesmo layer; trate como ESTIMADO, "
                                 f"confira o valor por ambiente)")
                else:
                    lines.append(f"  {layer}: {area:.2f} m²")
            lines.append("")

        # Áreas de polilinha fechada (ambiente/piso/forro) — m² medido da geometria
        poly_areas = self.get_polygon_areas_by_layer()
        if poly_areas:
            lines.append("ÁREAS DE CONTORNO FECHADO POR LAYER (polilinha fechada — ambiente/piso/forro):")
            lines.append("  (medido da geometria; pode incluir layer não-ambiente — use o nome do layer pra decidir; "
                         "NÃO some com ÁREAS HACHURADAS da MESMA região — é a mesma área medida de outro jeito)")
            for layer, area in sorted(poly_areas.items(), key=lambda x: -x[1]):
                lines.append(f"  {layer}: {area:.2f} m²")
            lines.append("")

        # Medições ESTRUTURAIS determinísticas (tabela de aço lida dos textos,
        # pilares contados na geometria, vigas/lajes por layer). Auto-limitada:
        # prancha de arquitetura sem esses dados não gera a seção. Defensivo:
        # falha aqui NUNCA derruba o prompt principal.
        if extract_structural_measurements is not None:
            try:
                _struct = extract_structural_measurements(self)
                if _struct:
                    lines.append(structural_prompt_section(_struct))
                    lines.append("")
            except Exception as _e_struct:
                logger.warning("[estrutural] medição determinística falhou: %s", _e_struct)

        # Key texts — COM a contagem de repetição.
        # 🐛 Aqui existia `set(texts)`, que jogava a contagem fora antes da IA ver:
        # "Bebedouro" 7× na prancha chegava como 1 palavra e voltava com qtd 0.
        # Medido em 08/08: 468 das 1.080 linhas zeradas nasciam desse molde.
        # Ver `contar_textos_repetidos` em engine_rules.py.
        texts_by_layer = self.get_texts_by_layer()
        if texts_by_layer:
            try:
                from engine_rules import (contar_textos_repetidos as _contar,
                                          texto_conta_objeto as _conta_obj)
            except Exception:                      # nunca derruba o prompt
                _contar = None
            lines.append("TEXTOS/LEGENDAS:")
            if _contar is not None:
                lines.append("  (×N = quantas vezes o MESMO texto aparece na prancha. É contagem")
                lines.append("   DETERMINÍSTICA feita no arquivo, não estimativa. Para item CONTÁVEL")
                lines.append("   rotulado no desenho — louça, luminária, porta, equipamento — o ×N é a")
                lines.append("   melhor evidência de quantidade que existe: USE. Sem ×N, o texto")
                lines.append("   apareceu 1 vez. ⚠ Conta OCORRÊNCIA DE TEXTO, não objeto: duas")
                lines.append("   etiquetas podem apontar a mesma peça e título se repete por prancha —")
                lines.append("   então marque 'estimado', não 'confirmado', salvo medição na geometria.)")
            for layer, texts in sorted(texts_by_layer.items()):
                if _contar is None:                # comportamento antigo, de emergência
                    unique_texts = list(set(t.strip() for t in texts if len(t.strip()) > 2))
                    if unique_texts:
                        lines.append(f"  [{layer}]:")
                        for t in sorted(unique_texts)[:50]:
                            lines.append(f"    {t}")
                    continue
                contagem = _contar(texts)
                if not contagem:
                    continue
                lines.append(f"  [{layer}]:")
                for t, n in contagem[:50]:
                    # 🪤 Só número (cota/nível) repetido não conta objeto — sai sem ×N.
                    _badge = f"   ×{n}" if (n > 1 and _conta_obj(t)) else ""
                    lines.append(f"    {t}{_badge}")
                if len(contagem) > 50:
                    # honestidade: a IA precisa saber que a lista foi cortada
                    lines.append(f"    (+{len(contagem) - 50} texto(s) desta camada não listado(s))")
            lines.append("")

        # Dimensions
        if self.dimensions:
            lines.append("COTAS/DIMENSÕES:")
            for label, value in self.dimensions:
                lines.append(f"  {label}: {value}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Unit detection / conversion
# ---------------------------------------------------------------------------

# ezdxf header variable $INSUNITS values
_INSUNITS_TO_METERS: dict[int, float] = {
    0: 1.0,       # Unitless — assume meters
    1: 0.0254,    # Inches
    2: 0.3048,    # Feet
    3: 1609.344,  # Miles
    4: 0.001,     # Millimeters
    5: 0.01,      # Centimeters
    6: 1.0,       # Meters
    7: 1000.0,    # Kilometers
    8: 0.0000254, # Microinches
    9: 0.001,     # Mils (= mm)
    10: 0.9144,   # Yards
    11: 1.0e-10,  # Angstroms
    12: 1.0e-9,   # Nanometers
    13: 1.0e-6,   # Microns
    14: 0.01,     # Decimeters (actually 0.1 m)
}
# Fix decimeters
_INSUNITS_TO_METERS[14] = 0.1


# ---------------------------------------------------------------------------
# Duto desenhado pelas DUAS FACES — medir o eixo, não a soma das paralelas
# ---------------------------------------------------------------------------
# Em planta, duto retangular é representado pelas duas faces: duas linhas
# paralelas. Somar o layer conta cada trecho DUAS VEZES. Uma projetista de
# climatização descreveu o padrão dela assim: "duas linhas em paralelo,
# geralmente com cores diferentes — insuflamento em azul escuro e retorno em
# azul claro" (04/08/2026).
#
# Medido no arquivo real dela: insuflamento 1,88× · exaustão 1,98× ·
# ar exterior 1,94× · retorno 2,00×. Quatro grupos independentes, todos perto
# de dobrar.
#
# 🔒 Só age em layer de DUTO. Eletroduto, prumada e canaleta são linha ÚNICA —
# parear ali cortaria pela metade uma medição correta, que é o erro oposto e
# igualmente grave (regra nº1). Parede também é desenhada com duas linhas, mas
# mexer nela mudaria todo projeto de arquitetura que hoje funciona: fora de
# escopo, deliberadamente.
_RE_DUTO_DUPLO = re.compile(r"(?<![a-z])duto|(?<![a-z])ducto", re.IGNORECASE)

_DUTO_ANG_TOL = 3.0      # graus: paralelas de verdade
_DUTO_SEP_MIN = 0.05     # m: abaixo disso é a mesma linha repetida, não um par
_DUTO_SEP_MAX = 1.50     # m: acima disso não é seção de duto, são redes distintas
_DUTO_MIN_SEG = 0.25     # m: trecho menor é legenda/símbolo, não rede
_DUTO_MAX_SEG_LAYER = 3000   # teto anti-O(n²) por layer


def _corrigir_duto_linha_dupla(walls, unit_factor: float = 1.0):
    """Troca a soma das duas faces pelo comprimento do EIXO, em layer de duto.

    Devolve (walls_corrigidos, relato_eixo, ressalva_hachura).
    Sem par encontrado, devolve a lista original — na dúvida, não mexe.

    🪤 As coordenadas de `start`/`end` são CRUAS (unidade do desenho), mas
    `length` já vem em METRO (bruto × unit_factor). Misturar as duas escalas na
    mesma conta foi o defeito da 1ª versão: a separação entre as faces saía
    dividida pelo fator ao quadrado, então em desenho de milímetro dava 600.000
    e NADA pareava. O conserto era inerte em quase todo DXF real — funcionou no
    arquivo de 04/08 só porque aquele estava em metro. Agora toda a geometria é
    feita em unidade bruta e só o resultado vira metro.
    """
    if not walls:
        return walls, "", ""
    try:
        from collections import defaultdict as _dd
        uf = float(unit_factor) if unit_factor else 1.0
        por_layer = _dd(list)
        for i, w in enumerate(walls):
            if _RE_DUTO_DUPLO.search(str(getattr(w, "layer", "") or "")):
                por_layer[w.layer].append(i)
        if not por_layer:
            return walls, "", ""

        def _geo(w):
            """(ax, ay, dx, dy, comprimento_bruto) — tudo na unidade do desenho."""
            (ax, ay), (bx, by) = w.start, w.end
            dx, dy = bx - ax, by - ay
            return ax, ay, dx, dy, math.hypot(dx, dy)

        descartar = set()
        relato, ressalva = [], []
        for layer, idxs in por_layer.items():
            # 🪤 Só pareia segmento com geometria de verdade. O caminho que mede
            # dentro de bloco grava start/end zerados — pareá-los casaria tudo
            # com tudo e destruiria a medição.
            uteis = [i for i in idxs
                     if getattr(walls[i], "length", 0) >= _DUTO_MIN_SEG
                     and walls[i].start != walls[i].end]
            if len(uteis) < 2 or len(uteis) > _DUTO_MAX_SEG_LAYER:
                continue
            bruto = sum(walls[i].length for i in uteis)
            usados = set()
            pares = 0
            for pos, i in enumerate(uteis):
                if i in usados:
                    continue
                ax, ay, adx, ady, alen = _geo(walls[i])
                if alen <= 0:
                    continue
                ux, uy = adx / alen, ady / alen          # direção unitária de A
                melhor, melhor_sobrep = None, 0.0
                for j in uteis[pos + 1:]:
                    if j in usados:
                        continue
                    bx0, by0, bdx, bdy, blen = _geo(walls[j])
                    if blen <= 0:
                        continue
                    # mesma direção?
                    d_ang = abs(math.degrees(math.atan2(ady, adx)) % 180.0
                                - math.degrees(math.atan2(bdy, bdx)) % 180.0)
                    if min(d_ang, 180.0 - d_ang) > _DUTO_ANG_TOL:
                        continue
                    if abs(walls[i].length - walls[j].length) > max(0.4, 0.3 * walls[i].length):
                        continue
                    # separação perpendicular, em METRO
                    sep = abs(adx * (ay - by0) - (ax - bx0) * ady) / alen * uf
                    if not (_DUTO_SEP_MIN < sep < _DUTO_SEP_MAX):
                        continue
                    # 🚨 SOBREPOSIÇÃO ao longo da direção. Sem isso, dois trechos
                    # paralelos que nem se olham (um ramal 60cm ao lado de outro
                    # tronco) viravam "par" e um deles era jogado fora. Pior: o
                    # eixo tracejado desenhado no MESMO layer, por estar mais
                    # perto, ganhava do outro lado do duto — as duas faces
                    # ficavam de pé, o dobro continuava, e o relato ainda
                    # anunciava um conserto que não aconteceu.
                    t0 = 0.0
                    t1 = alen
                    s0 = (bx0 - ax) * ux + (by0 - ay) * uy
                    s1 = (bx0 + bdx - ax) * ux + (by0 + bdy - ay) * uy
                    if s0 > s1:
                        s0, s1 = s1, s0
                    sobrep = min(t1, s1) - max(t0, s0)
                    if sobrep < 0.5 * min(alen, blen):
                        continue
                    # prefere quem mais se sobrepõe, não quem está mais perto
                    if sobrep > melhor_sobrep:
                        melhor, melhor_sobrep = j, sobrep
                if melhor is not None:
                    usados.add(i)
                    usados.add(melhor)
                    descartar.add(melhor)      # fica UMA das duas faces = o eixo
                    pares += 1
            if pares:
                eixo = bruto - sum(walls[k].length for k in descartar if k in uteis)
                relato.append(f"{layer}: {bruto:.1f}m de face -> {eixo:.1f}m de eixo "
                              f"({pares} par(es))")

        # 🚨 Layer dominado por MICRO-SEGMENTO não mede rede, mede HACHURA.
        # No arquivo de 04/08 o layer 'IM DUCTO SUMINISTRO' somava 169 m — e
        # tinha 3.699 linhas, 3.246 arcos e NENHUM segmento acima de 1 m. Os
        # 169 m eram o padrão gráfico que preenche o duto, não o trecho. Somar
        # isso e chamar de comprimento é inventar número (regra nº1), então o
        # certo é avisar em vez de entregar um total com cara de medição.
        # Vai numa chave SEPARADA porque é RESSALVA, não conserto: quem lê
        # rebaixa a procedência do desenho inteiro. O relato de eixo, não.
        for layer, idxs in por_layer.items():
            tot = sum(walls[i].length for i in idxs)
            if tot <= 0:
                continue
            micro = sum(walls[i].length for i in idxs
                        if getattr(walls[i], "length", 0) < _DUTO_MIN_SEG)
            if micro / tot > 0.60:
                ressalva.append(
                    f"{layer}: {micro / tot * 100:.0f}% do comprimento está em "
                    f"segmentos < {_DUTO_MIN_SEG:.2f} m — isso é hachura/padrão "
                    f"gráfico, não trecho de rede; total NÃO confiável")

        # 🚨 ARCO fica FORA do pareamento e isso desequilibra o total: o trecho
        # reto vira eixo (cai pela metade) enquanto o cotovelo continua contando
        # as duas faces. Numa rede com muitas curvas o resultado SUPERESTIMA, e
        # o cliente não tem como saber. Enquanto não parear arco por
        # concentricidade, no mínimo ele fica sabendo.
        for layer, idxs in por_layer.items():
            if not any(k in descartar for k in idxs):
                continue
            arcos = sum(walls[i].length for i in idxs
                        if getattr(walls[i], "curvo", False))
            if arcos > 0:
                ressalva.append(
                    f"{layer}: {arcos:.1f}m em curva (ARC) ficaram FORA do "
                    f"pareamento — nessas o duto ainda conta as duas faces")

        rel_eixo = " | ".join(relato)
        rel_ressalva = " | ".join(ressalva)
        if not descartar:
            return walls, rel_eixo, rel_ressalva
        novos = [w for i, w in enumerate(walls) if i not in descartar]
        logger.warning("[duto-linha-dupla] %s %s", rel_eixo, rel_ressalva)
        return novos, rel_eixo, rel_ressalva
    except Exception as e:
        logger.warning("[duto-linha-dupla] falhou, mantendo medição original: %s", e)
        return walls, "", ""


def _detect_unit_factor(doc) -> float:
    """Return the multiplier to convert drawing units to meters.

    Heuristic order:
      1. $INSUNITS header variable (most reliable)
      2. $MEASUREMENT (0 = imperial, 1 = metric)
      3. Fallback: assume millimeters (most common in Brazilian arch. drawings)
    """
    try:
        insunits = doc.header.get("$INSUNITS", 0)
        if insunits in _INSUNITS_TO_METERS and insunits != 0:
            return _INSUNITS_TO_METERS[insunits]
    except Exception:
        pass

    # Fallback: $MEASUREMENT
    try:
        measurement = doc.header.get("$MEASUREMENT", 1)
        if measurement == 0:
            # Imperial — assume feet
            return 0.3048
    except Exception:
        pass

    # 🚨 Antes de chutar milímetro: com $INSUNITS=0 o desenho não declarou nada,
    # e o chute é CEGO. A extensão do próprio desenho é evidência disponível.
    inferido = _inferir_unidade_sem_insunits(doc)
    if inferido is not None:
        return inferido

    # Default for Brazilian architecture: millimeters
    return 0.001


# Faixa de largura plausível pra uma prancha de edificação/implantação, em metros.
_EXTENSAO_PLAUSIVEL_M = (10.0, 2000.0)
# Abaixo disto o mm é aceito sem discussão (detalhe pequeno, peça, corte).
_MM_ACEITAVEL_ATE_M = 2.0
# Abaixo disto não é prancha, é detalhe — não arriscamos inferir nada.
_MIN_ENTIDADES_PRA_INFERIR = 500


def _inferir_unidade_sem_insunits(doc):
    """Escolhe o fator quando o desenho NÃO declara unidade ($INSUNITS=0).

    🚨 Esta é a função de MAIOR RISCO do extrator: o fator multiplica TODO
    número medido de TODO projeto. Errar aqui não estraga uma linha, estraga a
    planilha inteira. Por isso ela é deliberadamente covarde e só age quando o
    padrão atual (mm) é COMPROVADAMENTE absurdo — em qualquer dúvida devolve
    None e o mm de sempre prevalece. Não existe caso em que ela troque um fator
    que hoje funciona.

    Caso que a originou (04/08/2026, cliente ConfortAr — climatização
    hospitalar): DWG sem $INSUNITS, desenho em METROS, 425 unidades de largura.
    O mm transformava o hospital num desenho de 42 cm e dividia todo comprimento
    por mil — 169 m de duto de insuflamento viravam 0,17 m, que a IA
    corretamente descartou como "fragmento de legenda". A cliente tinha
    perguntado, ANTES de criar conta, se a gente media duto.

    🪤 A rede de proteção que existia (`_validate_unit_factor`) não pegou: ela
    alerta quando o maior elemento fica < 5 cm, e aqui deu 33 cm. Um elemento de
    33 cm passa por plausível — o absurdo só aparece quando se percebe que ele é
    o MAIOR de uma planta hospitalar inteira. Valor isolado não denuncia escala;
    a extensão do desenho denuncia.
    """
    try:
        emin = doc.header.get("$EXTMIN")
        emax = doc.header.get("$EXTMAX")
        if not emin or not emax:
            return None
        largura = max(abs(emax[0] - emin[0]), abs(emax[1] - emin[1]))
        if not (largura > 0) or largura != largura:      # 0, negativo ou NaN
            return None

        # Prancha de verdade tem muita entidade. Detalhe/peça solta não —
        # e num detalhe o mm costuma estar certo. Contagem com teto: só
        # precisamos saber se passa do mínimo, não o total.
        n = 0
        for _ in doc.modelspace():
            n += 1
            if n >= _MIN_ENTIDADES_PRA_INFERIR:
                break
        if n < _MIN_ENTIDADES_PRA_INFERIR:
            return None

        # Se o mm já produz um desenho de tamanho aceitável, ele fica. Este é o
        # freio que garante "nunca mexe em arquivo que hoje funciona".
        if largura * 0.001 >= _MM_ACEITAVEL_ATE_M:
            return None

        lo, hi = _EXTENSAO_PLAUSIVEL_M
        for fator in (0.01, 1.0):                        # cm, depois metros
            if lo <= largura * fator <= hi:
                logger.warning(
                    "[unit-inferida] $INSUNITS=0 e mm daria %.2f m de largura "
                    "(absurdo) — adotando fator %s (%.0f m de largura)",
                    largura * 0.001, fator, largura * fator)
                return fator
        return None
    except Exception:
        return None


# Padrões que indicam bloco de esquadria (porta ou janela).
# Matching case-insensitive via startswith OU contains.
_ESQUADRIA_PATTERNS = (
    "PORT", "PRT", "DOOR",
    "JANE", "JN", "JAN",
    "ESQU", "ESQ-",
    "VIDRO", "GLASS", "WIN",
    # Códigos típicos de projeto (P1, P2, PM3, PJ4 etc.)
)
_ESQUADRIA_CODE_RE = re.compile(r"^(PM|PJ|PD|JN|JL|J[0-9]|P[0-9])", re.IGNORECASE)


def _is_esquadria_block(name: str) -> bool:
    if not name:
        return False
    up = name.upper()
    if any(p in up for p in _ESQUADRIA_PATTERNS):
        return True
    if _ESQUADRIA_CODE_RE.match(name):
        return True
    return False


def _compute_block_bbox(block_layout) -> Optional[tuple[float, float]]:
    """Calcula bounding box (width, height) das entidades dentro de uma definição
    de bloco, em unidades de desenho. Retorna None se não conseguir computar."""
    try:
        xs, ys = [], []
        for ent in block_layout:
            dxftype = ent.dxftype()
            try:
                if dxftype == "LINE":
                    xs.extend([ent.dxf.start.x, ent.dxf.end.x])
                    ys.extend([ent.dxf.start.y, ent.dxf.end.y])
                elif dxftype == "LWPOLYLINE":
                    for p in ent.get_points(format="xy"):
                        xs.append(p[0]); ys.append(p[1])
                elif dxftype == "POLYLINE":
                    for v in ent.vertices:
                        xs.append(v.dxf.location.x); ys.append(v.dxf.location.y)
                elif dxftype == "CIRCLE":
                    c = ent.dxf.center
                    r = ent.dxf.radius
                    xs.extend([c.x - r, c.x + r])
                    ys.extend([c.y - r, c.y + r])
                elif dxftype == "ARC":
                    c = ent.dxf.center
                    r = ent.dxf.radius
                    xs.extend([c.x - r, c.x + r])
                    ys.extend([c.y - r, c.y + r])
            except Exception:
                continue
        if not xs or not ys:
            return None
        return (max(xs) - min(xs), max(ys) - min(ys))
    except Exception:
        return None


def _validate_unit_factor(doc, unit_factor: float) -> tuple[float, list[str]]:
    """Sanity-check + AUTO-CORRIGE o fator de unidade contra a extensão real do
    desenho.

    Antes só AVISAVA (devolvia o mesmo fator). Agora: se o fator detectado produz
    dimensões absurdas (maior elemento >500m ou <5cm — típico de $INSUNITS=0
    caindo em mm quando o desenho é metros) E existe uma correção LIMPA por
    potência de 10 (mm↔cm↔m), aplica e registra. Se for ambíguo (sem correção
    limpa), mantém e avisa FORTE — a quantidade não deve ser confirmada.
    """
    warnings: list[str] = []
    try:
        msp = doc.modelspace()
        max_len = 0.0  # maior elemento JÁ em metros (raw × fator)
        cnt = 0
        for ent in msp.query("LINE"):
            try:
                dx = ent.dxf.end.x - ent.dxf.start.x
                dy = ent.dxf.end.y - ent.dxf.start.y
                v = ((dx * dx + dy * dy) ** 0.5) * unit_factor
                if v > max_len:
                    max_len = v
            except Exception:
                continue
            cnt += 1
            if cnt >= 8000:  # representativo, mas com teto
                break
        cnt = 0
        for ent in msp.query("LWPOLYLINE"):
            try:
                pts = [(p[0], p[1]) for p in ent.get_points()]
                for i in range(len(pts) - 1):
                    dx = pts[i + 1][0] - pts[i][0]
                    dy = pts[i + 1][1] - pts[i][1]
                    v = ((dx * dx + dy * dy) ** 0.5) * unit_factor
                    if v > max_len:
                        max_len = v
            except Exception:
                continue
            cnt += 1
            if cnt >= 4000:
                break

        # Uma planta arquitetônica raramente tem maior elemento > 500m ou < 5cm.
        # NÃO auto-corrigimos chutando a escala (chute errado estraga arquivo
        # correto — visto em teste). Quando a escala está absurda, AVISAMOS forte
        # pra a quantidade entrar como ESTIMADO, não confirmada.
        if max_len > 500:
            warnings.append(
                f"Unidade suspeita: maior elemento mede {max_len:.0f}m (>500m) — "
                f"escala pode estar errada; tratar quantidades como estimado."
            )
        elif 0 < max_len < 0.05:
            warnings.append(
                f"Unidade suspeita: maior elemento mede {max_len*1000:.0f}mm (<5cm) — "
                f"escala pode estar errada; tratar quantidades como estimado."
            )
    except Exception:
        pass
    return unit_factor, warnings


# ---------------------------------------------------------------------------
# "Régua da prancha" — validação da unidade pelas COTAS (DIMENSION)
# ---------------------------------------------------------------------------
# A prancha carrega a própria régua: cada cota linear tem uma medida GEOMÉTRICA
# (distância real entre os pontos cotados, em unidades do desenho) e um TEXTO
# exibido (o número que o arquiteto vê impresso). A razão texto/medida prova a
# unidade do desenho sem heurística — cota é dado REAL do CAD, não suposição.

_CANONICAL_METRIC_FACTORS = (1.0, 0.1, 0.01, 0.001)  # m, dm, cm, mm → metros
_UNIT_FACTOR_NAMES = {1.0: "metros", 0.1: "decímetros",
                      0.01: "centímetros", 0.001: "milímetros"}
# Texto de cota BR: número (vírgula OU ponto decimal) com sufixo de unidade
# opcional. Prefixo de aproximação (~ ≈ ±) tolerado; qualquer outra palavra
# ("VER DETALHE", "VAR.") invalida o uso como régua.
_DIM_TEXT_NUM_RE = re.compile(
    r"^\s*[~≈±]?\s*(\d+(?:[.,]\d+)?)\s*(mm|cm|m)?\s*\.?\s*$", re.IGNORECASE)
_DIM_TEXT_UNIT_SCALE = {"m": 1.0, "cm": 0.01, "mm": 0.001}
_DIM_RATIO_TOL = 0.02        # ±2% — consistência exigida entre texto e medida
_DIM_MIN_COTAS = 3           # mínimo de cotas consistentes pra provar algo
_DIM_MAJORITY = 0.8          # e ≥80% das cotas utilizáveis concordando
_DIM_LEN_MIN, _DIM_LEN_MAX = 0.05, 500.0   # plausibilidade POR COTA (metros)
_DIM_MED_MIN, _DIM_MED_MAX = 0.5, 100.0    # plausibilidade da MEDIANA (metros)
_DIM_MAX_SCAN = 4000         # teto defensivo de cotas varridas


# Guarda de absurdo físico da correção por cotas (05/08/2026). Cota acima disto
# é rara em prancha de edificação — a casa_quadra02, cuja correção é CERTA, tem
# 580 cotas e ZERO acima. Detalhe em mm lido como metro estoura na hora: um
# rodapé de 8 cm vira 80 m.
_DIM_ABSURDO_M = 30.0
_DIM_ABSURDO_FRACAO = 0.10


def correcao_e_absurda(medidas_m) -> bool:
    """True quando as cotas, sob o fator NOVO, viram tamanhos impossíveis.

    Cota acima de 30 m é rara em prancha de edificação. Uma prancha em que
    mais de 10% delas passa disso não é planta: é DETALHE em milímetro lido
    como metro — um rodapé de 8 cm virando 80 m.

    Medido em 05/08/2026 nos arquivos reais, sob o fator que seria adotado:
        casa_quadra02 (correção CERTA) : 580 cotas, mediana 1,20 m,  0% > 30 m
        CX5 / CX6     (erradas)        :   4 cotas, mediana 11,50 m, 25% > 30 m
        CX1           (errada)         :   5 cotas, mediana 34,00 m, 60% > 30 m
    """
    if not medidas_m:
        return False
    gigantes = sum(1 for v in medidas_m if v > _DIM_ABSURDO_M)
    return gigantes > _DIM_ABSURDO_FRACAO * len(medidas_m)


def _dim_effective_dimlfac(doc, dim) -> float:
    """DIMLFAC efetivo de uma cota (fator que multiplica a medida geométrica
    pra virar o texto default). Ordem: override na entidade (XDATA DSTYLE — o
    ezdxf já cai no dimstyle quando não há override) → dimstyle da tabela → 1.0.
    DIMLFAC ≤ 0 só se aplica a cota de paperspace (convenção AutoCAD) — pra
    cota de modelspace vale 1.0."""
    lf = None
    try:
        lf = dim.override().get("dimlfac", None)
    except Exception:
        lf = None
    if lf is None:
        try:
            style = doc.dimstyles.get(dim.dxf.dimstyle)
            if style is not None:
                lf = style.get_dxf_attrib("dimlfac", None)
        except Exception:
            lf = None
    try:
        lf = float(lf) if lf is not None else 1.0
    except (TypeError, ValueError):
        return 1.0
    return lf if lf > 0 else 1.0


# ══════════════════════════════════════════════════════════════════════
#  UNIDADE PELO DIMLFAC — quando o cabeçalho mente e não há cota digitada
# ══════════════════════════════════════════════════════════════════════
# Caso Isabelle (05/08/2026): DXF declara $INSUNITS=4 (mm) e está em METRO.
# Os 36 pilares somem no filtro de seção porque viram 0,34 mm. O validador por
# COTAS não salva: exige ≥3 cotas DIGITADAS à mão e o arquivo tem ZERO.
#
# O DIMLFAC não depende de escala — ele converte UNIDADE (a escala mora no
# DIMSCALE, botão separado). Identidade:
#       unidade_do_desenho = DIMLFAC × unidade_exibida_na_cota
#
# 🔒 POR QUE É SEGURO CONTRA O ERRO DE 1000×: desenho honesto em milímetro,
# cotado em milímetro, tem DIMLFAC = 1 OBRIGATORIAMENTE, por mais ampliado que
# esteja. A regra se abstém nele por CONSTRUÇÃO (passo 5), não por sorte — foi
# assim que ela sobreviveu ao contraexemplo do cético (rodapé em mm ampliado).
#
# 🪤 Ler o $DIMLFAC do CABEÇALHO não serve: nos 7 contraexemplos ele deu 100
# em todos, enquanto o valor EFETIVO por cota (override → estilo → 1) era 1 em
# três deles. Sempre o efetivo.

# DIMLFAC → unidade do desenho, assumindo a unidade exibida mais provável.
# Só entram os DIMLFAC que têm leitura única e usual em projeto brasileiro.
# 🚨 SÓ ENTRA DIMLFAC COM LEITURA ÚNICA. O 1000 ficou de FORA de propósito:
# ele lê como "cota em mm, desenho em m" E como "cota em mícron, desenho em
# mm" — as duas válidas, separadas por mil. Foi assim que o contraexemplo
# CX2_micron_mm_ampliada passou pela plausibilidade: cotas de 18, 3 e 6
# unidades viram 18 m, 3 m e 6 m, que são medidas de cômodo normais.
# Recusar custa pouco (desenho em metro cotado em mm fica como hoje) e evitar
# um erro de 1000× vale muito mais. O caso Isabelle é DIMLFAC=100.
_LFAC_PARA_FATOR = {
    100.0: 1.0,      # cota em cm, desenho em m   ← caso Isabelle
    10.0: 0.01,      # cota em mm, desenho em cm
    0.1: 0.001,      # cota em cm, desenho em mm
    0.01: 0.01,      # cota em m,  desenho em cm
    0.001: 0.001,    # cota em m,  desenho em mm
}
_LFAC_TOL = 0.005            # ±0,5% pra encaixar no canônico
_LFAC_MIN_COTAS = 3
_LFAC_CONSENSO = 0.80
# Plausibilidade sob a unidade escolhida: a cota tem que virar tamanho de obra.
_LFAC_COMP_MIN, _LFAC_COMP_MAX = 0.01, 500.0
_LFAC_MEDIANA_MIN, _LFAC_MEDIANA_MAX = 0.10, 50.0

# Nota de ampliação escrita na prancha ("ESC 10:1"). Se o desenho declara que
# está AMPLIADO, não se mexe na unidade dele.
_RE_ESC_AMPLIADA = re.compile(r"\bESC(?:ALA)?\.?\s*[:\-]?\s*(\d{1,3})\s*[:/]\s*1\b",
                               re.IGNORECASE)
# Vocabulário de desenho MECÂNICO — não é o nosso domínio, e é onde mora o
# milímetro ampliado. 'INOX' e 'TEMPERA' ficam FORA de propósito: aparecem em
# 10 pranchas de arquitetura do acervo (bancada inox, vidro temperado).
_TOKENS_MECANICO = ("TOLERANC", "ISO 2768", "RUGOSID", "TRAT. TERMICO",
                    "TRAT TERMICO", "USINAG", "LISTA DE PECAS", "NBR 8404")


def _unidade_por_dimlfac(doc, unit_factor):
    """Decide a unidade pelo DIMLFAC das cotas. Devolve dict (nunca levanta).

    status: None (abstém) | "corrigida_lfac" | "recusada_<motivo>"
    """
    out = {"status": None}
    try:
        msp = doc.modelspace()

        # VETO A — a prancha declara que está AMPLIADA.
        for e in msp.query("TEXT MTEXT"):
            txt = getattr(e.dxf, "text", "") or getattr(e, "text", "") or ""
            m = _RE_ESC_AMPLIADA.search(str(txt))
            if m and int(m.group(1)) >= 2:
                return {"status": "recusada_ampliada",
                        "motivo": f"prancha declara ampliação {m.group(0)}"}

        # VETO B — vocabulário de desenho mecânico.
        for e in msp.query("TEXT MTEXT"):
            up = str(getattr(e.dxf, "text", "") or getattr(e, "text", "") or "").upper()
            for tok in _TOKENS_MECANICO:
                if tok in up:
                    return {"status": "recusada_mecanico",
                            "motivo": f"vocabulário mecânico: {tok}"}

        # Passo 1-2: DIMLFAC efetivo por cota que imprime número.
        lfacs, medidas = [], []
        for dim in msp.query("DIMENSION"):
            try:
                med = dim.get_measurement()
            except Exception:
                continue
            if not isinstance(med, (int, float)) or abs(med) <= 1e-9:
                continue
            txt = (getattr(dim.dxf, "text", "") or "").strip()
            if txt and txt not in ("<>",):
                # override que NÃO imprime número (ex.: " " suprimido, "VER DET")
                if not re.search(r"\d", txt):
                    continue
            lf = _dim_effective_dimlfac(doc, dim)
            if not isinstance(lf, (int, float)) or lf <= 0:
                lf = 1.0
            lfacs.append(lf)
            medidas.append(abs(med))

        if len(lfacs) < _LFAC_MIN_COTAS:
            return {"status": None, "motivo": f"só {len(lfacs)} cota(s)"}

        # Passo 3: encaixar no canônico e achar o dominante.
        def _encaixa(lf):
            for c in _LFAC_PARA_FATOR:
                if abs(lf / c - 1.0) <= _LFAC_TOL:
                    return c
            if abs(lf - 1.0) <= _LFAC_TOL:
                return 1.0
            return None

        enc = [_encaixa(l) for l in lfacs]
        from collections import Counter as _C
        dom, n_dom = _C([e for e in enc if e is not None]).most_common(1)[0] \
            if any(e is not None for e in enc) else (None, 0)

        # Passo 4: massa e consenso.
        if n_dom < _LFAC_MIN_COTAS or n_dom < _LFAC_CONSENSO * len(lfacs):
            return {"status": None,
                    "motivo": f"sem consenso ({n_dom}/{len(lfacs)})"}

        # Passo 5 — O FREIO CONTRA O ERRO DE 1000×.
        # DIMLFAC = 1 significa "a cota está na unidade do próprio desenho":
        # não há informação de unidade nenhuma ali. É onde cai TODO desenho
        # honesto em mm, ampliado ou não. Abstém, sempre.
        if dom is None or dom == 1.0:
            return {"status": None, "motivo": "DIMLFAC=1 (cota na unidade do desenho)"}

        novo = _LFAC_PARA_FATOR.get(dom)
        if not novo:
            return {"status": None, "motivo": f"DIMLFAC {dom:g} sem leitura única"}

        # Passo 7: plausibilidade sob a unidade escolhida.
        comps = sorted(m * novo for m, e in zip(medidas, enc) if e == dom)
        if not comps:
            return {"status": None, "motivo": "sem medida no dominante"}
        dentro = sum(1 for c in comps if _LFAC_COMP_MIN <= c <= _LFAC_COMP_MAX)
        med_c = comps[len(comps) // 2]
        # 🚨 MESMA guarda de absurdo físico do validador por cotas. Sem ela esta
        # regra corrigia os contraexemplos CX1 (esquadria em mm ampliada, 60% das
        # cotas acima de 30 m) e CX2 — exatamente o erro de 1000× que ela existe
        # pra evitar. Medido em 05/08 antes de ligar no fluxo.
        if correcao_e_absurda(comps):
            return {"status": "recusada_absurdo",
                    "motivo": f"sob {novo:g} as cotas viram tamanhos impossíveis"}
        if dentro < 0.80 * len(comps) or not (_LFAC_MEDIANA_MIN <= med_c <= _LFAC_MEDIANA_MAX):
            return {"status": "recusada_implausivel",
                    "motivo": (f"sob {novo:g} a mediana das cotas daria "
                               f"{med_c:.2f} m")}

        # Passo 8: só troca no degrau de 1000×. 100× e 10× ficam de fora —
        # o degrau menor é onde moram os falsos positivos, e recusar é o
        # comportamento de hoje, que é seguro.
        razao = novo / unit_factor if unit_factor else 0
        if abs(razao - 1000.0) > 1.0:
            return {"status": None,
                    "motivo": f"degrau {razao:g}× (só 1000× é corrigido)"}

        return {
            "status": "corrigida_lfac",
            "fator_original": unit_factor,
            "fator_corrigido": novo,
            "n_cotas": n_dom,
            "dimlfac": dom,
            "unidade_nome": _UNIT_FACTOR_NAMES.get(novo, str(novo)),
            "mensagem": (
                f"unidade corrigida pelo DIMLFAC das cotas: fator {unit_factor:g} → "
                f"{novo:g} ({_UNIT_FACTOR_NAMES.get(novo, novo)}) — DIMLFAC {dom:g} "
                f"em {n_dom} de {len(lfacs)} cotas, mediana {med_c:.2f} m"),
        }
    except Exception as exc:
        logger.warning("[unit-lfac] falhou (ignorado): %s", exc)
        return {"status": None, "motivo": f"erro {exc}"}

def _dim_displayed_number(doc, dim, measurement: float):
    """Número que a cota EXIBE na prancha, ou None se não serve como régua.

    Retorna (valor, escala_explícita | None):
      - texto vazio ou contendo "<>" → medida formatada pelo dimstyle:
        measurement × DIMLFAC ("<> VAR." mantém o número medido embutido)
      - texto " " (um espaço) → texto SUPRIMIDO — sem número na prancha, fora
      - número literal ("350", "3,50", "12.5", "350 cm") → o número (vírgula BR
        ok); sufixo m/cm/mm vira escala explícita do texto
      - override não-numérico ("VER DETALHE") → None (fora)
    """
    try:
        raw = dim.dxf.text
    except Exception:
        raw = ""
    if raw is None:
        raw = ""
    if raw == " ":          # convenção DXF: espaço único = suprime o texto
        return None
    stripped = raw.strip()
    if stripped == "" or "<>" in stripped:
        # 🚨 AUTOMÁTICO: o número exibido É a medida geométrica formatada. Isso
        # NÃO é evidência independente de escala — comparar "texto × geometria"
        # aqui é circular e "prova" qualquer fator que se assuma. Serve pra
        # CONFIRMAR, nunca pra CORRIGIR. (auto=True; ver caso marcenaria 30/07.)
        return (measurement * _dim_effective_dimlfac(doc, dim), None, True)
    m = _DIM_TEXT_NUM_RE.match(stripped)
    if not m:
        return None
    try:
        value = float(m.group(1).replace(",", "."))
    except ValueError:
        return None
    suffix = m.group(2)
    scale = _DIM_TEXT_UNIT_SCALE.get(suffix.lower()) if suffix else None
    # Número DIGITADO por quem desenhou = evidência independente da geometria.
    return (value, scale, False)


def _validate_unit_by_dimensions(doc, unit_factor: float) -> dict:
    """A RÉGUA DA PRANCHA: usa as cotas lineares (DIMENSION linear/aligned) pra
    validar ou corrigir o fator de unidade detectado por heurística.

    Pra cada cota utilizável: o texto exibido D, lido em metros sob cada unidade
    de texto plausível (m / cm / mm — ou a explícita, se o texto tem sufixo),
    dividido pela medida geométrica M implica um fator unidade→metros. Se esse
    fator implícito casa (±2%) com um fator métrico canônico (m/dm/cm/mm) e o
    comprimento real resultante é plausível (5cm–500m), a cota SUPORTA aquele
    fator. Um fator fica PROVADO quando ≥3 cotas E ≥80% das utilizáveis o
    suportam E a mediana dos comprimentos reais é de escala arquitetônica
    (0,5m–100m — é o que desempata a ambiguidade cm×mm de razão 1:1).

    Saídas (regra nº1 — só o que as cotas PROVAM; na dúvida, nada muda):
      {"status": "validada", ...}   fator detectado é o ÚNICO provado
      {"status": "corrigida", ...}  detectado NÃO se sustenta e há UM ÚNICO
                                    fator provado → usar fator_corrigido
      {"status": "ambigua"|None}    sem prova exclusiva → comportamento antigo
    """
    out: dict = {"status": None, "cotas_utilizaveis": 0}
    try:
        msp = doc.modelspace()
        evidence: list[tuple[float, float, Optional[float]]] = []
        scanned = 0
        for dim in msp.query("DIMENSION"):
            if scanned >= _DIM_MAX_SCAN:
                break
            scanned += 1
            try:
                if dim.dimtype not in (0, 1):
                    continue  # angular/diâmetro/raio/ordenada NÃO é régua linear
            except Exception:
                continue
            try:
                meas = dim.get_measurement()
            except Exception:
                continue
            if not isinstance(meas, (int, float)):
                continue  # tipos exóticos devolvem vetor — fora
            meas = float(meas)
            if meas <= 1e-9:
                continue
            shown = _dim_displayed_number(doc, dim, meas)
            if shown is None:
                continue
            value, explicit_scale, auto_text = shown
            if value <= 0:
                continue
            evidence.append((meas, value, explicit_scale, auto_text))

        # Suporte por fator canônico: {fator: [comprimentos reais das cotas]}
        support: dict[float, list[float]] = {f: [] for f in _CANONICAL_METRIC_FACTORS}
        usable = 0
        n_digitadas = 0   # cotas com número DIGITADO — a única prova independente
        for meas, value, explicit_scale, auto_text in evidence:
            scales = (explicit_scale,) if explicit_scale is not None else (1.0, 0.01, 0.001)
            cand: dict[float, float] = {}
            for s in scales:
                real_len = value * s              # metros que o TEXTO afirma
                if not (_DIM_LEN_MIN <= real_len <= _DIM_LEN_MAX):
                    continue
                implied = real_len / meas         # fator unidade→m implicado
                for f in _CANONICAL_METRIC_FACTORS:
                    if abs(implied / f - 1.0) <= _DIM_RATIO_TOL:
                        cand[f] = real_len
            if not cand:
                continue
            usable += 1
            if not auto_text:
                n_digitadas += 1
            for f, real_len in cand.items():
                support[f].append(real_len)

        out["cotas_utilizaveis"] = usable
        if usable < _DIM_MIN_COTAS:
            return out

        def _median_of(xs: list) -> float:
            s = sorted(xs)
            n = len(s)
            return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0

        def _proven(f: float) -> bool:
            lens = support[f]
            if len(lens) < _DIM_MIN_COTAS or len(lens) < _DIM_MAJORITY * usable:
                return False
            return _DIM_MED_MIN <= _median_of(lens) <= _DIM_MED_MAX

        proven = [f for f in _CANONICAL_METRIC_FACTORS if _proven(f)]

        detected = None  # fator detectado ancorado no canônico métrico (±2%)
        for f in _CANONICAL_METRIC_FACTORS:
            if abs(unit_factor / f - 1.0) <= _DIM_RATIO_TOL:
                detected = f
                break

        if detected is not None and detected in proven:
            if len(proven) == 1:
                out.update({
                    "status": "validada",
                    "fator": detected,
                    "n_cotas": len(support[detected]),
                    "unidade_nome": _UNIT_FACTOR_NAMES[detected],
                })
            else:
                # Compatível com o detectado, mas OUTRO fator também qualificou
                # (ex.: cotas cm×mm com razão 1:1) — prova não é exclusiva.
                out["status"] = "ambigua"
            return out

        # Contradição consistente: o detectado não se provou E existe UM ÚNICO
        # fator provado pelas cotas → correção honesta (cota é dado real do CAD).
        # Fator não-métrico detectado (imperial) nunca é corrigido — abstém.
        # 🚨 SÓ CORRIGE COM PROVA INDEPENDENTE (caso marcenaria, 30/07/2026).
        # Cota com texto "<>" exibe a PRÓPRIA medida geométrica: comparar as duas
        # é circular e "prova" qualquer fator. Numa prancha de marcenaria (mediana
        # 40 cm) isso derrubou o $INSUNITS=cm do desenho e cravou METROS, porque
        # 0,40 m ficou abaixo do piso de plausibilidade (0,5 m) e 40 m coube nele.
        # Resultado: 346 KM de parede. Sem número digitado, no máximo confirma.
        if detected is not None and len(proven) == 1 and n_digitadas >= _DIM_MIN_COTAS:
            novo = proven[0]
            n = len(support[novo])
            # 🚨 GUARDA DE ABSURDO FÍSICO (05/08/2026) — fecha um erro de 1000×
            # que estava ARMADO aqui. Num desenho de DETALHE em milímetro
            # (rodapé, esquadria) o texto da cota diz "80" e a geometria mede 80
            # unidades: este código concluía METRO e trocava 0,001 por 1,0.
            # Reproduzido no contraexemplo CX5_rodape_mm_lfac1.dxf, com
            # $INSUNITS=4 honesto e cotas digitadas em mm.
            # 🪤 DIMLFAC NÃO serve de guarda: medido, o rodapé (correção errada)
            # e a casa_quadra02 (correção CERTA) têm os dois LFAC efetivo = 1.
            # O que separa é a física. Sob o fator novo:
            #     casa_quadra02 (certa) : 580 cotas, mediana 1,20 m, 0% > 30 m
            #     CX5/CX6     (erradas) :   4 cotas, mediana 11,50 m, 25% > 30 m
            #     CX1         (errada)  :   5 cotas, mediana 34,00 m, 60% > 30 m
            # Cota de mais de 30 m é rara em prancha de edificação; uma prancha
            # em que um quarto delas passa disso é detalhe lido como metro.
            _sob_novo = [abs(v) * novo for v in support[novo]]
            _gigantes = sum(1 for v in _sob_novo if v > _DIM_ABSURDO_M)
            if correcao_e_absurda(_sob_novo):
                logger.warning(
                    "[unit-cotas] correção RECUSADA: sob o fator %g, %d de %d cotas "
                    "passariam de %g m — é detalhe lido como metro, não prancha",
                    novo, _gigantes, len(_sob_novo), _DIM_ABSURDO_M)
                out["status"] = "recusada_absurdo"
                out["motivo"] = (
                    f"cotas implausíveis sob o fator {novo:g}: {_gigantes} de "
                    f"{len(_sob_novo)} passariam de {_DIM_ABSURDO_M:g} m")
                return out
            out.update({
                "status": "corrigida",
                "fator_original": unit_factor,
                "fator_corrigido": novo,
                "n_cotas": n,
                "unidade_nome": _UNIT_FACTOR_NAMES[novo],
                "mensagem": (
                    f"unidade corrigida pelas cotas da prancha: fator {unit_factor:g} → {novo:g} "
                    f"({_UNIT_FACTOR_NAMES[novo]}) — provado por {n} cotas "
                    f"(texto exibido × medida geométrica, ±2%)"
                ),
            })
        return out
    except Exception as exc:  # defensivo: a régua NUNCA derruba a extração
        logger.warning("[unit-cotas] validação por cotas falhou (ignorada): %s", exc)
        return {"status": None, "cotas_utilizaveis": 0}


# ---------------------------------------------------------------------------
# DWG -> DXF conversion via ODA File Converter
# ---------------------------------------------------------------------------

_ODA_SEARCH_PATHS = [
    # Linux (servidor Render)
    "/usr/bin/ODAFileConverter",
    "/usr/local/bin/ODAFileConverter",
    "/opt/ODAFileConverter/ODAFileConverter",
    # Windows (desenvolvimento local)
    r"C:\Program Files\ODA\ODAFileConverter 27.1.0\ODAFileConverter.exe",
    r"C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe",
    r"C:\Program Files (x86)\ODA\ODAFileConverter\ODAFileConverter.exe",
]


def _find_oda_converter() -> Optional[str]:
    """Locate ODAFileConverter executable on disk."""
    import shutil
    # Primeiro tentar via PATH (funciona em Linux e Windows)
    which = shutil.which("ODAFileConverter")
    if which:
        return which
    # Depois tentar caminhos conhecidos
    for p in _ODA_SEARCH_PATHS:
        path = Path(p)
        if path.is_file():
            return str(path)
        if path.is_dir():
            for name in ["ODAFileConverter", "ODAFileConverter.exe"]:
                exe = path / name
                if exe.is_file():
                    return str(exe)
    return None


# Motivo da última falha de conversão, por nome de arquivo. Preenchido em
# convert_dwg_to_dxf e lido por main.py via dwg_failure_reason() — serve pra
# mensagem de erro dizer a verdade em vez de listar hipóteses.
_FALHA_MOTIVO: dict = {}


def dwg_failure_reason(dwg_path: str) -> str:
    """Por que este DWG não converteu: 'truncado' ou '' (não classificado).

    'truncado' = o arquivo chegou incompleto/corrompido (o leitor bateu no fim do
    arquivo antes do esperado). O conselho certo é reabrir no CAD e salvar de
    novo — NÃO é 'exporte pra DXF', que não resolve arquivo quebrado.
    """
    return _FALHA_MOTIVO.get(os.path.basename(str(dwg_path)), "")


def convert_dwg_to_dxf(dwg_path: str) -> Optional[str]:
    """Attempt to convert a DWG file to DXF using ODA File Converter.

    Returns:
        Path to the resulting .dxf file, or None if conversion failed.
    """
    dwg_path = os.path.abspath(dwg_path)
    if not os.path.isfile(dwg_path):
        logger.error("Arquivo DWG não encontrado: %s", dwg_path)
        return None

    oda_exe = _find_oda_converter()
    if oda_exe is None:
        logger.warning(
            "ODA File Converter não encontrado. "
            "Para converter arquivos .dwg, instale o ODA File Converter gratuito em: "
            "https://www.opendesign.com/guestfiles/oda_file_converter  "
            "Instale em C:\\Program Files\\ODA\\ODAFileConverter"
        )
        return None

    input_dir = os.path.dirname(dwg_path)
    output_dir = tempfile.mkdtemp(prefix="arq_dxf_")
    filename = os.path.basename(dwg_path)

    # ODAFileConverter <input_dir> <output_dir> <output_version> <output_type>
    #   <recurse> <audit> [filter]
    # output_type: 0 = DWG, 1 = DXF, 2 = DXB
    # output_version: "ACAD2018" is safe for ezdxf
    cmd = [
        oda_exe,
        input_dir,
        output_dir,
        "ACAD2018",  # output version
        "DXF",       # output file type
        "0",         # no recurse
        "1",         # audit & fix
        filename,    # filter — only this file
    ]

    logger.info("Convertendo DWG -> DXF: %s", " ".join(cmd))
    # ODA usa Qt/xcb que precisa de display X11. Usar xvfb-run pra simular.
    env = os.environ.copy()
    # Remover offscreen se estiver setado — queremos xcb com xvfb
    env.pop("QT_QPA_PLATFORM", None)

    # Tentar com xvfb-run (simula display X11)
    import shutil
    if shutil.which("xvfb-run"):
        cmd = ["xvfb-run", "--auto-servernum", "--server-args=-screen 0 1024x768x24"] + cmd

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5min — DWGs grandes com imagens embutidas precisam mais
            env=env,
        )
        # Salvar log do ODA num arquivo pra poder ler via API
        oda_log = f"rc={result.returncode}\nstdout={result.stdout[:500]}\nstderr={result.stderr[:500]}\ncmd={' '.join(cmd)}\noutput_dir={output_dir}\nfiles_in_output={os.listdir(output_dir) if os.path.isdir(output_dir) else 'DIR NOT FOUND'}"
        log_path = os.path.join(os.path.dirname(dwg_path), "_oda_log.txt")
        with open(log_path, 'w') as lf:
            lf.write(oda_log)
        print(f"[ODA] {oda_log}")
        if result.returncode != 0:
            # NÃO retorna aqui (bug corrigido 15/07): o ODA às vezes gera um DXF
            # USÁVEL mesmo com código≠0 (audit com warnings), e mesmo quando não
            # gera, ainda queremos tentar o fallback libredwg — que existe justo
            # pra DWG com objetos fora do padrão (MEP/elétrica). Antes o return
            # aqui pulava o plano B inteiro. Segue pro procura-DXF + libredwg.
            logger.warning(
                "ODA File Converter code %d (segue pra procurar DXF/fallback): %s",
                result.returncode,
                (result.stderr or result.stdout or "")[:300],
            )
    except FileNotFoundError:
        logger.error("Executável ODA não acessível: %s", oda_exe)
        return None
    except subprocess.TimeoutExpired:
        logger.error("Conversão DWG excedeu o tempo limite de 300s — arquivo grande demais ou complexo.")
        return None

    # Look for the converted file
    stem = Path(filename).stem
    dxf_path = os.path.join(output_dir, stem + ".dxf")
    if os.path.isfile(dxf_path):
        logger.info("DXF gerado em: %s", dxf_path)
        return dxf_path

    # Procurar .dxf.err — ODA cria isso quando falha em arquivos corrompidos/truncados.
    err_path = os.path.join(output_dir, stem + ".dxf.err")
    oda_failed_with_err = os.path.isfile(err_path)
    if oda_failed_with_err:
        try:
            with open(err_path, 'r', errors='replace') as ef:
                err_content = ef.read()[:500]
        except Exception:
            err_content = ""
        logger.warning("ODA gerou .dxf.err (DWG inválido/corrompido): %s", err_content)
        # Classifica a causa pra main.py dar o conselho CERTO em vez de chutar
        # "versão nova do AutoCAD ou objetos especiais" — que foi o que o cliente
        # Thalison leu em 29/07 quando o problema real era arquivo INCOMPLETO
        # (ODA: "Unexpected end of file"). Conselho errado = ele reenviou o mesmo
        # arquivo 2x e desistiu da prancha.
        _low_err = (err_content or "").lower()
        if ("unexpected end of file" in _low_err
                or "invalid system section page map" in _low_err
                or "premature end" in _low_err):
            _FALHA_MOTIVO[os.path.basename(dwg_path)] = "truncado"
        # 🪤 Sem isto a CAUSA se perde: o .err mora num tempdir que o Render apaga,
        # e o _oda_log.txt (o que /api/debug/oda-log devolve) é escrito ANTES desta
        # checagem. Resultado: "DWG não converteu" sem nunca dizer por quê — caso
        # Walter 29/07, em que o ODA saiu com rc=0 e só deixou o .err pra trás.
        try:
            with open(os.path.join(os.path.dirname(dwg_path), "_oda_log.txt"), "a") as _lf:
                _lf.write(f"\n--- conteudo do .dxf.err ---\n{err_content}\n")
        except Exception:
            pass

    # Try case-insensitive search in output dir (caso ODA tenha gerado com nome diferente)
    for f in os.listdir(output_dir):
        if f.lower().endswith(".dxf") and not f.lower().endswith(".dxf.err"):
            found = os.path.join(output_dir, f)
            logger.info("DXF gerado em: %s", found)
            return found

    # FALLBACK: ODA falhou. Tenta libredwg (open-source) — pega ~15-20% dos casos
    # onde ODA falhou (DWGs com objetos não-padrão, alguns DWGs corrompidos parciais).
    logger.info("ODA falhou — tentando fallback libredwg-cli (dwg2dxf)...")
    fallback_dxf = _try_libredwg_convert(dwg_path, output_dir)
    if fallback_dxf:
        logger.info("DXF gerado via libredwg fallback: %s", fallback_dxf)
        return fallback_dxf

    if oda_failed_with_err:
        logger.error("Tanto ODA quanto libredwg falharam. DWG provavelmente corrompido.")
    else:
        logger.error("Nenhum arquivo .dxf gerado no diretório de saída: %s", output_dir)
    return None


def _try_libredwg_convert(dwg_path: str, output_dir: str) -> Optional[str]:
    """Tenta converter DWG → DXF usando libredwg-cli (dwg2dxf).

    libredwg é open-source, mais permissivo que ODA pra DWGs com problemas
    parciais. Funciona como fallback quando ODA falha.

    Retorna path do .dxf gerado, ou None se falhar.
    """
    import shutil
    dwg2dxf = shutil.which("dwg2dxf")
    if not dwg2dxf:
        logger.info("libredwg (dwg2dxf) não instalado — pulando fallback")
        return None

    # 🚨 TRAVA DE QUALIDADE (29/07/2026) — regra dura nº1.
    # O binário passou a existir de verdade (antes o apt-get falhava em silêncio),
    # mas a QUALIDADE da conversão ainda não foi medida contra os DWGs reais que já
    # processamos. Um conversor que devolve DXF que ABRE mas com geometria errada é
    # PIOR que um que falha: gera número branco ("medido") falso. Enquanto não houver
    # a comparação item a item contra o ODA, ele fica desligado.
    # Pra ligar depois de validar: LIBREDWG_FALLBACK=1 no Render.
    if os.getenv("LIBREDWG_FALLBACK", "0").strip().lower() not in ("1", "true", "on", "sim"):
        logger.info("libredwg instalado mas DESLIGADO (LIBREDWG_FALLBACK != 1) — "
                    "aguardando validação de qualidade antes de virar fallback real")
        return None

    stem = Path(dwg_path).stem
    out_path = os.path.join(output_dir, stem + "_libredwg.dxf")

    try:
        result = subprocess.run(
            [dwg2dxf, "-y", "-o", out_path, dwg_path],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0 and os.path.isfile(out_path):
            return out_path
        logger.warning("libredwg dwg2dxf retornou %d: %s",
                       result.returncode, result.stderr[:300])
    except subprocess.TimeoutExpired:
        logger.warning("libredwg dwg2dxf excedeu timeout 300s")
    except Exception as e:
        logger.warning("libredwg dwg2dxf erro: %s", e)
    return None


def dwg_has_aec_markers(dwg_path: str) -> bool:
    """Detecta se o DWG contém objetos AEC (AutoCAD Architecture/MEP) por marcadores
    no binário. Esses 'objetos inteligentes' (proxy) não são lidos pelos conversores
    livres (ODA File Converter / libredwg) — é a causa nº1 de DWG que não abre.

    Serve pra dar um aviso PRECISO ("é arquivo MEP/Architecture") em vez de genérico,
    e pra alertar o usuário na hora. Lê em blocos (cap de memória) com sobreposição
    pra pegar marcador entre blocos. Best-effort: erro → False.

    OBS: no DWG os nomes de dicionário (AEC_VARS_*, AEC_OVERRIDES) ficam em UTF-16LE
    (wide chars), não ASCII — por isso checamos as DUAS codificações."""
    _words = ("AEC_VARS", "AEC_OVERRIDES", "AEC_LAYERKEY", "AEC_DISP", "AecDbDwg")
    markers = []
    for _w in _words:
        markers.append(_w.encode("latin1"))          # ASCII
        markers.append(_w.encode("utf-16-le"))         # UTF-16LE (o que o AutoCAD usa)
    try:
        tail = b""
        with open(dwg_path, "rb") as fh:
            while True:
                chunk = fh.read(1 << 20)  # 1 MB por vez
                if not chunk:
                    break
                buf = tail + chunk
                if any(m in buf for m in markers):
                    return True
                tail = chunk[-32:]  # sobreposição pra marcador cortado no limite do bloco
        return False
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------

_MTEXT_FORMAT_CODES_RE = re.compile(
    r"""
    \\[fF][^;]*;       # \fArial|b0|i0|c0|p34;
    | \\[cC][0-9]+;    # \C256; (color)
    | \\[LlOoKk]        # \L \l \O \o \K \k (underline/strike toggles)
    | \\[Pp]            # \P (newline)
    | \\[SsQqHhWwTt][^;]*;   # \S2/3; \H1.5x; \Q15; etc (superscript, height, etc.)
    | \\~               # non-breaking space
    | [{}]              # grupos MTEXT
    """,
    re.VERBOSE,
)


def _strip_mtext_codes(raw: str) -> str:
    """Remove códigos de formatação de MTEXT deixando só o texto legível.
    Fallback pra quando mtext.plain_text() não está disponível."""
    if not raw:
        return ""
    cleaned = _MTEXT_FORMAT_CODES_RE.sub(" ", raw)
    # Converter \P (que pode ter sobrado) em newline
    cleaned = cleaned.replace("\\P", "\n").replace("\\p", "\n")
    # Compactar espaços múltiplos
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned.strip()


def _line_length(start, end) -> float:
    """Euclidean distance between two 2D/3D points."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    dz = (end[2] - start[2]) if len(start) > 2 and len(end) > 2 else 0
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _arc_length_from_bulge(p1, p2, bulge: float) -> float:
    """Comprimento real do arco entre dois pontos, dado o parâmetro bulge do DXF.
    bulge = tan(ângulo_de_abertura / 4). bulge=0 → reta."""
    if abs(bulge) < 1e-9:
        return _line_length(p1, p2)
    chord = _line_length(p1, p2)
    if chord < 1e-9:
        return 0.0
    # ângulo de abertura total do arco (em radianos)
    theta = 4.0 * math.atan(abs(bulge))
    # raio via relação chord = 2·r·sin(θ/2)
    try:
        r = chord / (2.0 * math.sin(theta / 2.0))
    except Exception:
        return chord
    return abs(r * theta)


def _lwpolyline_length(entity) -> float:
    """Total length of an LWPOLYLINE incluindo interpolação de bulges (arcos)."""
    try:
        pts = list(entity.get_points(format="xyb"))  # (x, y, bulge)
    except Exception:
        try:
            pts_xy = list(entity.get_points(format="xy"))
            pts = [(p[0], p[1], 0.0) for p in pts_xy]
        except Exception:
            return 0.0
    if len(pts) < 2:
        return 0.0
    total = 0.0
    for i in range(len(pts) - 1):
        p1 = (pts[i][0], pts[i][1])
        p2 = (pts[i + 1][0], pts[i + 1][1])
        bulge = pts[i][2] if len(pts[i]) > 2 else 0.0
        total += _arc_length_from_bulge(p1, p2, bulge)
    if entity.closed and len(pts) >= 3:
        p1 = (pts[-1][0], pts[-1][1])
        p2 = (pts[0][0], pts[0][1])
        bulge = pts[-1][2] if len(pts[-1]) > 2 else 0.0
        total += _arc_length_from_bulge(p1, p2, bulge)
    return total


def _polyline_length(entity) -> float:
    """Total length of a 2D/3D POLYLINE."""
    try:
        points = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
    except Exception:
        return 0.0
    if len(points) < 2:
        return 0.0
    total = 0.0
    for i in range(len(points) - 1):
        total += _line_length(points[i], points[i + 1])
    if entity.is_closed and len(points) >= 3:
        total += _line_length(points[-1], points[0])
    return total


def _hatch_area(entity) -> float:
    """Calculate area of a HATCH entity.

    Abordagem em 3 camadas, todas usando APIs nativas do ezdxf (mais confiável
    que amostragem manual de bulges):

    1. Tenta make_path() + flattening() em cima da hatch inteira — lida com
       arcos, bulges e splines automaticamente.
    2. Se falhar, normaliza boundary paths via polyline_to_edge_paths() e roda
       make_path() por path individual.
    3. Último recurso: shoelace nos vértices brutos (perde precisão em arcos
       mas nunca crasha).
    """
    # --- Camada 1: API unificada ---
    try:
        from ezdxf import path as ezdxf_path
        path_result = ezdxf_path.make_path(entity)
        if path_result:
            paths_list = path_result if isinstance(path_result, list) else [path_result]
            total = 0.0
            for p in paths_list:
                try:
                    vertices = list(p.flattening(0.5))  # distância 0.5 = bom equilíbrio precisão/custo
                    pts = [(v.x, v.y) for v in vertices]
                    if len(pts) >= 3:
                        total += abs(_shoelace_area(pts))
                except Exception:
                    continue
            if total > 0:
                return total
    except Exception:
        pass

    # --- Camada 2: normalizar polyline→edge paths e processar por boundary ---
    try:
        from ezdxf import path as ezdxf_path
        # polyline_to_edge_paths converte in-place; operamos numa cópia defensiva
        try:
            entity.paths.polyline_to_edge_paths()
        except Exception:
            pass
        total = 0.0
        for bpath in entity.paths:
            try:
                p = ezdxf_path.from_hatch_boundary_path(bpath)
                if p is None:
                    continue
                vertices = list(p.flattening(0.5))
                pts = [(v.x, v.y) for v in vertices]
                if len(pts) >= 3:
                    total += abs(_shoelace_area(pts))
            except Exception:
                continue
        if total > 0:
            return total
    except Exception:
        pass

    # --- Camada 3: shoelace bruto (último recurso, perde arcos) ---
    total_area = 0.0
    try:
        for bpath in entity.paths:
            pts: list[tuple[float, float]] = []
            if hasattr(bpath, "vertices") and bpath.vertices:
                pts = [(v[0], v[1]) for v in bpath.vertices]
            elif hasattr(bpath, "edges"):
                for edge in bpath.edges:
                    if hasattr(edge, "start"):
                        try:
                            pts.append((edge.start[0], edge.start[1]))
                        except Exception:
                            continue
            if len(pts) >= 3:
                total_area += abs(_shoelace_area(pts))
    except Exception:
        pass
    return total_area


def _sample_arc_from_bulge_DEPRECATED(p1, p2, bulge: float, segments: int = 8) -> list:
    """DEPRECATED — substituído por APIs nativas do ezdxf em _hatch_area.
    Mantido temporariamente pra compatibilidade mas não é mais usado."""
    if abs(bulge) < 1e-9:
        return []
    chord = _line_length(p1, p2)
    if chord < 1e-9:
        return []
    theta = 4.0 * math.atan(abs(bulge))
    try:
        r = chord / (2.0 * math.sin(theta / 2.0))
    except Exception:
        return []
    # ponto médio do chord
    mx = (p1[0] + p2[0]) / 2.0
    my = (p1[1] + p2[1]) / 2.0
    # vetor perpendicular ao chord (direção do centro do arco)
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-9:
        return []
    nx = -dy / length
    ny = dx / length
    # distância do ponto médio até o centro
    h = r * math.cos(theta / 2.0)
    if bulge < 0:
        h = -h
    cx = mx + nx * h
    cy = my + ny * h
    # ângulos dos endpoints relativos ao centro
    a1 = math.atan2(p1[1] - cy, p1[0] - cx)
    a2 = math.atan2(p2[1] - cy, p2[0] - cx)
    # sentido do arco baseado no sinal de bulge
    if bulge > 0:
        if a2 < a1:
            a2 += 2 * math.pi
    else:
        if a2 > a1:
            a2 -= 2 * math.pi
    # amostra pontos (exclui endpoints, esses já foram adicionados pelo chamador)
    result = []
    for k in range(1, segments):
        t = k / segments
        ang = a1 + (a2 - a1) * t
        result.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return result


def _shoelace_area(points: list) -> float:
    """Shoelace formula for polygon area from a list of (x, y) tuples."""
    n = len(points)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += points[i][0] * points[j][1]
        area -= points[j][0] * points[i][1]
    return area / 2.0


def extract_dxf(filepath: str, unit_factor_override: Optional[float] = None) -> DXFExtraction:
    """Main extraction function — reads a .dxf file and returns structured data.

    Args:
        filepath: Path to a .dxf file.
        unit_factor_override: escala (fator p/ metros) PROVADA por cota em OUTRA
            prancha do mesmo projeto (consenso de unidade). Só é usada quando ESTA
            prancha NÃO tem cota própria que prove a escala — cota local sempre
            vence. Evita "pés" numa prancha BR sem cota (caso Rafael 21/07).

    Returns:
        DXFExtraction with all extracted elements.

    Raises:
        FileNotFoundError: if the file does not exist.
        ezdxf.DXFError: if the file is not a valid DXF.
    """
    filepath = os.path.abspath(filepath)
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"Arquivo não encontrado: {filepath}")

    # Guarda de memória (auditoria 06/07): ezdxf.readfile carrega o DXF INTEIRO
    # na RAM. No Render (2 GB) um DXF gigante — comum no arquivo expandido pela
    # conversão ODA — estoura antes de qualquer processamento (SIGKILL sem stack
    # trace, aparece como "servidor reiniciou"). Recusa com mensagem clara acima
    # de um teto seguro em vez de derrubar o processo inteiro.
    try:
        _sz = os.path.getsize(filepath)
    except OSError:
        _sz = 0
    _MAX_DXF_BYTES = 150 * 1024 * 1024  # 150 MB — prancha normal é <20 MB
    if _sz > _MAX_DXF_BYTES:
        raise RuntimeError(
            f"DXF grande demais pra processar com segurança "
            f"({_sz // (1024 * 1024)} MB, limite {_MAX_DXF_BYTES // (1024 * 1024)} MB). "
            f"Exporte só a prancha necessária ou divida o arquivo em partes."
        )

    # Try UTF-8 first, then latin-1 (common in Brazilian CAD files)
    doc = None
    for encoding in ("utf-8", "latin-1", None):
        try:
            kwargs = {}
            if encoding is not None:
                kwargs["encoding"] = encoding
            doc = ezdxf.readfile(filepath, **kwargs)
            break
        except UnicodeDecodeError:
            continue
        except Exception as exc:
            # For non-encoding errors, re-raise immediately
            if encoding is None:
                raise
            # On last attempt (None), let ezdxf pick encoding
            if encoding == "latin-1":
                try:
                    doc = ezdxf.readfile(filepath)
                    break
                except Exception:
                    raise exc
            continue

    if doc is None:
        raise RuntimeError(f"Não foi possível abrir o DXF com nenhum encoding: {filepath}")

    msp = doc.modelspace()
    unit_factor = _detect_unit_factor(doc)
    unit_factor, unit_warnings = _validate_unit_factor(doc, unit_factor)
    # ── "Régua da prancha": as COTAS (DIMENSION) validam/corrigem a unidade ──
    # Cota é dado REAL do CAD: o texto exibido × a medida geométrica provam o
    # fator. Só 3 saídas (regra nº1 — nunca promover por suposição):
    #   validada  → ≥3 cotas consistentes confirmam o fator detectado como ÚNICO
    #               plausível; a suspeita heurística de extensão é superada por
    #               dado medido (fica rastreada em metadata, não some);
    #   corrigida → o detectado não se sustenta e ≥3 cotas provam OUTRO fator
    #               único — upgrade honesto, correção registrada;
    #   (nada)    → cotas insuficientes/ambíguas/conflitantes: tudo como antes.
    dim_check = _validate_unit_by_dimensions(doc, unit_factor)
    if dim_check.get("status") == "corrigida":
        unit_factor = dim_check["fator_corrigido"]
        logger.warning("[unit-cotas] %s", dim_check["mensagem"])
        # os avisos antigos foram computados com o fator ERRADO — refaz a
        # heurística de extensão com o fator provado pelas cotas
        _, unit_warnings = _validate_unit_factor(doc, unit_factor)
    elif dim_check.get("status") is None:
        # Cotas não decidiram (sem número digitado, sem consenso). Última régua:
        # o DIMLFAC, que converte UNIDADE e não depende de escala de plotagem.
        # Caso Isabelle (05/08): 28 cotas com DIMLFAC=100 provam metro num
        # arquivo que declara milímetro — e sem isso os 36 pilares somem.
        _lfac = _unidade_por_dimlfac(doc, unit_factor)
        if _lfac.get("status") == "corrigida_lfac":
            unit_factor = _lfac["fator_corrigido"]
            logger.warning("[unit-lfac] %s", _lfac["mensagem"])
            dim_check = _lfac
            _, unit_warnings = _validate_unit_factor(doc, unit_factor)
    elif dim_check.get("status") == "validada" and unit_warnings:
        # fator PROVADO por cota: a heurística de extensão vira rastro em
        # metadata em vez de rebaixar tudo pra estimado
        dim_check["heuristica_superada"] = " | ".join(unit_warnings)
        unit_warnings = []
    # ── CONSENSO DE UNIDADE DO PROJETO ──────────────────────────────────────
    # Se ESTA prancha NÃO tem cota que prove a escala e a detecção local dela é
    # FRACA (chutou pela extensão / caiu em pés por $MEASUREMENT, sem $INSUNITS
    # explícito), usa a escala PROVADA por cota em outra prancha do projeto.
    # Cota PRÓPRIA sempre vence. E — crucial (revisão adversarial 21/07) — NÃO
    # sobrescreve prancha cujo $INSUNITS afirma explicitamente a unidade: senão um
    # detalhe legítimo em mm (sem cota) num projeto provado em metros seria inflado
    # ×1000. Após aplicar, RE-VALIDA a extensão contra a nova escala: se ficar
    # implausível, o warning rebaixa pra estimado (a escala foi inferida, não
    # provada NESTA prancha) — regra nº1.
    _unit_consenso = None
    try:
        _insunits_local = int(doc.header.get("$INSUNITS", 0) or 0)
    except Exception:
        _insunits_local = 0
    _deteccao_local_forte = (_insunits_local in _INSUNITS_TO_METERS
                             and _insunits_local != 0 and not unit_warnings)
    if (unit_factor_override and unit_factor_override > 0
            and dim_check.get("status") not in ("validada", "corrigida")
            and not _deteccao_local_forte
            and abs(unit_factor_override - unit_factor) > 1e-9):
        _unit_consenso = (unit_factor, unit_factor_override)
        unit_factor = unit_factor_override
        # re-valida a extensão sob a escala nova (não zera às cegas): se a extensão
        # ficar implausível, o warning rebaixa pra estimado — honesto.
        _, unit_warnings = _validate_unit_factor(doc, unit_factor)
        logger.info("[unit-consenso] %s: fator %s -> %s (escala provada por cota em "
                    "outra prancha do projeto)", os.path.basename(filepath),
                    _unit_consenso[0], _unit_consenso[1])
    for w in unit_warnings:
        logger.warning("[unit-sanity] %s", w)
    area_factor = unit_factor * unit_factor  # for m² conversion

    # ---- Metadata ---------------------------------------------------------
    metadata: dict = {}
    try:
        metadata["versão_dxf"] = doc.dxfversion
    except Exception:
        pass
    try:
        acad_ver = doc.header.get("$ACADVER", "")
        if acad_ver:
            metadata["versão_autocad"] = acad_ver
    except Exception:
        pass
    try:
        insunits = doc.header.get("$INSUNITS", 0)
        unit_names = {
            0: "Sem unidade", 1: "Polegadas", 2: "Pés", 4: "Milímetros",
            5: "Centímetros", 6: "Metros", 7: "Quilômetros",
        }
        metadata["unidade_desenho"] = unit_names.get(insunits, f"Código {insunits}")
        metadata["fator_para_metros"] = f"{unit_factor}"
        if unit_warnings:
            metadata["alerta_unidade"] = " | ".join(unit_warnings)
    except Exception:
        pass
    # "Régua da prancha" — resultado da validação da unidade pelas cotas.
    # Correção NÃO entra em unidade_suspeita (não é suspeita, é fator provado).
    try:
        _dim_status = dim_check.get("status")
        if _dim_status == "validada":
            metadata["unidade_validada_por_cotas"] = dim_check["n_cotas"]
            metadata["unidade_nome_provada"] = dim_check["unidade_nome"]
            if dim_check.get("heuristica_superada"):
                metadata["heuristica_extensao_superada_por_cotas"] = \
                    dim_check["heuristica_superada"]
        elif _dim_status == "corrigida":
            metadata["unidade_corrigida_por_cotas"] = dim_check["mensagem"]
            metadata["unidade_nome_provada"] = dim_check["unidade_nome"]
        if _unit_consenso:
            metadata["unidade_por_consenso_projeto"] = (
                f"prancha sem cota própria: usei a escala provada por cota em outra "
                f"prancha do projeto (fator {_unit_consenso[1]} no lugar do chute "
                f"{_unit_consenso[0]})")
    except Exception:
        pass

    # ---- Layers -----------------------------------------------------------
    layer_names = [layer.dxf.name for layer in doc.layers]

    # ---- Blocks (INSERT entities) -----------------------------------------
    # Nota sobre blocos aninhados: msp.query("INSERT") é NÃO-recursivo — retorna só
    # INSERTs do modelspace. INSERTs dentro de outros blocos (BLOCK_RECORD) ficam
    # na definição daquele bloco, não aqui, então não há dupla contagem.
    # Layers utilitárias do AutoCAD (DEFPOINTS, viewports, etc.) são filtradas
    # pois contêm blocos auxiliares de cotação que não são itens do projeto.
    _UTILITY_LAYERS_UPPER = {
        "DEFPOINTS", "0-DEFPOINTS", "DEFPOINTS_NO_PLOT",
        "VIEWPORTS", "VIEWPORT", "VP",
        "_GRADE", "GRADE", "GRID",
    }
    # Regex pra identificar blocos de ANOTAÇÃO/CALLOUT — não são itens orçáveis.
    # Casa nomes tipo "ANNO_Section_A2", "leg mb", "TAG-porta", "AREA3", etc.
    # Tolera separador _/- ou espaço entre o token e o resto do nome.
    _ANNOTATION_NAME_RE = re.compile(
        r"^(ANNO|ANNOTATION|NOTE|NOTES|"
        r"LEG|LEGEND|LEGENDA|"
        r"TAG|"
        r"SECTION|ELEVATION|DETAIL|DET|"
        r"ARROW|CALLOUT|"
        r"NORTH|NORTE|ROSA_DOS_VENTOS|"
        r"TITLE|TITLEBLOCK|CARIMBO|"
        r"REVISION|REVISAO|"
        r"ADCADD|"
        r"FORMA|FORM|"  # "forma 12", "form-01" — marcadores de formato em plantas
        r"NIVEL|NIV|LEVEL|"  # marcadores de nivel/cota
        r"CHNIVP|CHNIV|CHNIVEL|"  # cota de nível de piso (padrão BR: marcação com triângulo)
        r"AREA[0-9])(?:[\s_\-]|$)",
        re.IGNORECASE
    )
    # Nomes curtos de símbolos de cota/nível que não têm separador no final
    _ANNOTATION_EXACT_NAMES = {
        "CHNIVP", "CHNIV", "CHNIVEL",
        "INDNORTE", "INDNIVEL", "INDCORTE", "INDETALHE",
    }
    # Nomes que são claramente xrefs/referências externas (arquivo com extensão ou GUID no nome)
    _XREF_NAME_RE = re.compile(r"\.(dwg|dxf)$|\.xref|^xref", re.IGNORECASE)

    def _is_annotation_block(name: str) -> bool:
        if not name:
            return False
        if _ANNOTATION_NAME_RE.match(name):
            return True
        if _XREF_NAME_RE.search(name):
            return True
        if name.upper() in _ANNOTATION_EXACT_NAMES:
            return True
        return False

    block_counter: dict[str, dict] = {}  # {name: {"count": n, "layer": l, "positions": [...], "widths": [], "heights": []}}
    # Cache de bbox por nome de bloco (definição) para não recalcular
    _block_def_bbox_cache: dict[str, Optional[tuple[float, float]]] = {}

    def _bbox_for_block_def(bname: str) -> Optional[tuple[float, float]]:
        if bname in _block_def_bbox_cache:
            return _block_def_bbox_cache[bname]
        try:
            block = doc.blocks.get(bname)
            bbox = _compute_block_bbox(block) if block is not None else None
        except Exception:
            bbox = None
        _block_def_bbox_cache[bname] = bbox
        return bbox

    for insert in msp.query("INSERT"):
        try:
            bname = insert.dxf.name
            layer = insert.dxf.layer
            x = insert.dxf.insert.x
            y = insert.dxf.insert.y
        except Exception:
            continue

        # Skip anonymous / internal blocks (names starting with * or contendo $)
        # Blocos dinâmicos do AutoCAD têm sufixos tipo "A$C6BFD6B53" — filtrar.
        if bname.startswith("*") or "$" in bname:
            continue
        # Skip utility / system layers that don't represent real items
        if layer and layer.upper() in _UTILITY_LAYERS_UPPER:
            continue
        # Skip annotation / callout blocks (legendas, TAGs, cortes, elevações)
        if _is_annotation_block(bname):
            continue

        if bname not in block_counter:
            block_counter[bname] = {
                "count": 0, "layer": layer, "positions": [],
                "widths": [], "heights": [],
            }
        block_counter[bname]["count"] += 1
        block_counter[bname]["positions"].append((round(x, 2), round(y, 2)))

        # Se parece ser esquadria (porta/janela), armazena dimensão em metros
        if _is_esquadria_block(bname):
            bbox = _bbox_for_block_def(bname)
            if bbox is not None:
                try:
                    xscale = getattr(insert.dxf, "xscale", 1.0) or 1.0
                    yscale = getattr(insert.dxf, "yscale", 1.0) or 1.0
                    w_m = abs(bbox[0] * xscale * unit_factor)
                    h_m = abs(bbox[1] * yscale * unit_factor)
                    # Sanity: rejeitar bbox absurdos (0 ou >10m) que indicam problema
                    if 0.1 < w_m < 10 and 0.1 < h_m < 10:
                        block_counter[bname]["widths"].append(w_m)
                        block_counter[bname]["heights"].append(h_m)
                except Exception:
                    pass

    def _median(xs: list) -> float:
        if not xs:
            return 0.0
        s = sorted(xs)
        n = len(s)
        return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0

    blocks = [
        BlockCount(
            name=name,
            count=info["count"],
            layer=info["layer"],
            positions=info["positions"],
            width_m=round(_median(info.get("widths", [])), 2),
            height_m=round(_median(info.get("heights", [])), 2),
        )
        for name, info in block_counter.items()
    ]

    if not blocks:
        logger.warning("Nenhum bloco (INSERT) encontrado no DXF: %s", filepath)

    # ---- Lines / polylines (wall segments) --------------------------------
    walls: list[WallSegment] = []

    for line in msp.query("LINE"):
        try:
            start = (line.dxf.start.x, line.dxf.start.y)
            end = (line.dxf.end.x, line.dxf.end.y)
            length = _line_length(start, end) * unit_factor
            if length > 0:
                walls.append(WallSegment(
                    layer=line.dxf.layer,
                    length=length,
                    start=start,
                    end=end,
                ))
        except Exception:
            continue

    for lwpoly in msp.query("LWPOLYLINE"):
        try:
            length = _lwpolyline_length(lwpoly) * unit_factor
            if length > 0:
                pts = list(lwpoly.get_points(format="xy"))
                start = pts[0] if pts else (0, 0)
                end = pts[-1] if pts else (0, 0)
                walls.append(WallSegment(
                    layer=lwpoly.dxf.layer,
                    length=length,
                    start=start,
                    end=end,
                ))
        except Exception:
            continue

    for poly in msp.query("POLYLINE"):
        try:
            length = _polyline_length(poly) * unit_factor
            if length > 0:
                verts = [(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
                start = verts[0] if verts else (0, 0)
                end = verts[-1] if verts else (0, 0)
                walls.append(WallSegment(
                    layer=poly.dxf.layer,
                    length=length,
                    start=start,
                    end=end,
                ))
        except Exception:
            continue

    # ARCs como segmentos (paredes curvas, trechos circulares de circulação)
    for arc in msp.query("ARC"):
        try:
            r = arc.dxf.radius
            start_angle = math.radians(arc.dxf.start_angle)
            end_angle = math.radians(arc.dxf.end_angle)
            if end_angle < start_angle:
                end_angle += 2 * math.pi
            length_raw = abs(r * (end_angle - start_angle))
            length = length_raw * unit_factor
            if length > 0:
                c = arc.dxf.center
                walls.append(WallSegment(
                    layer=arc.dxf.layer,
                    length=length,
                    start=(c.x + r * math.cos(start_angle), c.y + r * math.sin(start_angle)),
                    end=(c.x + r * math.cos(end_angle), c.y + r * math.sin(end_angle)),
                    curvo=True,
                ))
        except Exception:
            continue

    # CIRCLEs fechados (2πr)
    for circle in msp.query("CIRCLE"):
        try:
            r = circle.dxf.radius
            length = (2 * math.pi * r) * unit_factor
            if length > 0:
                c = circle.dxf.center
                walls.append(WallSegment(
                    layer=circle.dxf.layer,
                    length=length,
                    start=(c.x, c.y),
                    end=(c.x, c.y),
                ))
        except Exception:
            continue

    # ---- Comprimento de INFRA LINEAR dentro de BLOCOS ----------------------
    # O laço acima só vê o MODELSPACE. Em muitos projetos de instalação o
    # eletroduto/eletrocalha/tubulação é desenhado DENTRO de blocos (MATRIZ,
    # blocos anônimos), então o comprimento sai ZERO e o item vem sem metro
    # (caso Fábio/Engie 21/07: eletroduto nos blocos MATRIZ-*, 0 no modelspace).
    #
    # Regra nº1 (nunca inflar/forjar): NÃO explodimos tudo — bloco de móvel,
    # símbolo ou legenda inflaria parede/piso. Só percorremos blocos pra medir
    # linha em layers CLARAMENTE de infra linear (allowlist abaixo), onde o
    # comprimento é a quantidade legítima. Pulamos blocos de anotação/carimbo.
    # Interruptor de emergência: DXF_MEASURE_BLOCK_INFRA=0 desliga sem deploy.
    if os.getenv("DXF_MEASURE_BLOCK_INFRA", "1") != "0":
        _INFRA_LINEAR_RX = INFRA_LINEAR_RX
        _MAX_BLOCK_WALLS = 40000     # teto de segmentos adicionados (anti-explosão)
        _MAX_BLOCK_SCAN = 400000     # teto de entidades varridas dentro de blocos
        _n_block_walls = 0
        _n_scanned = 0
        # Silencia o spam "copy process ignored ACAD_PROXY_OBJECT" do ezdxf ao
        # explodir blocos com objetos de app AEC (dezenas de linhas por prancha).
        _ezlog = logging.getLogger("ezdxf")
        _ez_prev = _ezlog.level
        _ezlog.setLevel(max(_ez_prev or logging.WARNING, logging.ERROR))
        # try/finally: esta é uma feature ADITIVA — jamais pode derrubar a prancha
        # (perder parede/piso já medidos = viola regra nº1) nem deixar o logger
        # global do ezdxf silenciado. O finally SEMPRE restaura o nível.
        try:
            for insert in msp.query("INSERT"):
                if _n_block_walls >= _MAX_BLOCK_WALLS or _n_scanned >= _MAX_BLOCK_SCAN:
                    break
                try:
                    _bn = insert.dxf.name or ""
                    if _is_annotation_block(_bn):   # legenda/carimbo/corte — não mede
                        continue
                    try:
                        _vents = insert.virtual_entities()   # explode 1 nível, com transform
                    except Exception:
                        continue
                    # A explosão do ezdxf é LAZY: cada next() pode estourar (ex.:
                    # MLEADER degenerado → ZeroDivisionError). next() protegido pra
                    # um bloco ruim não derrubar a prancha (caso Rafael 004, 21/07).
                    while True:
                        try:
                            _e = next(_vents)
                        except StopIteration:
                            break
                        except Exception:
                            break   # ezdxf falhou explodindo este bloco — pula o resto
                        _n_scanned += 1
                        if _n_block_walls >= _MAX_BLOCK_WALLS or _n_scanned >= _MAX_BLOCK_SCAN:
                            break
                        _et = _e.dxftype()
                        if _et not in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC"):
                            continue
                        _lay = _e.dxf.layer
                        if not _INFRA_LINEAR_RX.search(str(_lay)):
                            continue
                        try:
                            if _et == "LINE":
                                _L = _line_length((_e.dxf.start.x, _e.dxf.start.y),
                                                  (_e.dxf.end.x, _e.dxf.end.y))
                            elif _et == "LWPOLYLINE":
                                _L = _lwpolyline_length(_e)
                            elif _et == "POLYLINE":
                                _L = _polyline_length(_e)
                            else:  # ARC
                                _r = _e.dxf.radius
                                _a0 = math.radians(_e.dxf.start_angle)
                                _a1 = math.radians(_e.dxf.end_angle)
                                if _a1 < _a0:
                                    _a1 += 2 * math.pi
                                _L = abs(_r * (_a1 - _a0))
                            _L *= unit_factor
                        except Exception:
                            continue
                        if _L > 0:
                            walls.append(WallSegment(layer=_lay, length=_L, start=(0, 0), end=(0, 0)))
                            _n_block_walls += 1
                except Exception:
                    continue   # bloco problemático nunca derruba a prancha (regra nº1)
        finally:
            _ezlog.setLevel(_ez_prev)   # SEMPRE restaura o logger global do ezdxf
        if _n_block_walls:
            logger.info("[infra-bloco] +%d segmentos de infra linear medidos dentro de blocos",
                        _n_block_walls)

    # ---- Geometria dentro de ACAD_PROXY_ENTITY (AEC/MEP) --------------------
    # 🎯 08/08/2026 — a maior perda medida do DWG. Desenho de AutoCAD
    # Architecture/MEP guarda parede/duto como ACAD_PROXY_ENTITY: um invólucro
    # que carrega uma CÓPIA da geometria dentro (é assim que visualizador sem
    # AutoCAD consegue desenhar). O motor nunca varreu esse tipo — só
    # LINE/LWPOLYLINE/POLYLINE/ARC/CIRCLE/INSERT/TEXT/MTEXT/DIMENSION/HATCH.
    #
    # Medido: AEC/MEP é 13 das 25 falhas de DWG de cliente, e quando o DWG abre
    # direito ele mede bem (18 de 27). Explica o caso do João (07/08): o
    # libredwg abriu, o texto virou 41 itens e a geometria não apareceu —
    # estava toda dentro dos proxies.
    #
    # 🪤 O código JÁ SABIA que eles existem: logo acima há um comentário
    # silenciando o aviso "copy process ignored ACAD_PROXY_OBJECT" do ezdxf.
    # A gente calava o aviso e seguia sem ler.
    #
    # 🚨 RISCO = CONTAGEM DOBRADA. A proxy graphic pode repetir geometria que
    # também está como entidade normal. Por isso esta 1ª versão é ESTREITA de
    # propósito: só camadas de INFRA LINEAR (o mesmo filtro do bloco de INSERT
    # acima), mesmos tetos, e um log que diz QUANTO veio daqui — pra dar pra
    # medir a contribuição antes de alargar. Kill switch: DXF_MEASURE_PROXY_AEC=0.
    if os.getenv("DXF_MEASURE_PROXY_AEC", "1") != "0":
        _PX_RX = INFRA_LINEAR_RX
        _MAX_PX_WALLS, _MAX_PX_SCAN = 40000, 400000
        _n_px_walls = _n_px_scan = _n_px_ents = 0
        _ezlog2 = logging.getLogger("ezdxf")
        _ez_prev2 = _ezlog2.level
        _ezlog2.setLevel(max(_ez_prev2 or logging.WARNING, logging.ERROR))
        try:
            for _px in msp.query("ACAD_PROXY_ENTITY"):
                _n_px_ents += 1
                if _n_px_walls >= _MAX_PX_WALLS or _n_px_scan >= _MAX_PX_SCAN:
                    break
                try:
                    try:
                        _pv = _px.virtual_entities()
                    except Exception:
                        continue
                    # next() protegido: a explosão do ezdxf é LAZY e um proxy
                    # degenerado não pode derrubar a prancha (regra nº1 — perder
                    # o que já foi medido é pior que não ganhar o novo).
                    while True:
                        try:
                            _pe = next(_pv)
                        except StopIteration:
                            break
                        except Exception:
                            break
                        _n_px_scan += 1
                        if _n_px_walls >= _MAX_PX_WALLS or _n_px_scan >= _MAX_PX_SCAN:
                            break
                        _pt = _pe.dxftype()
                        if _pt not in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC"):
                            continue
                        _play = _pe.dxf.layer
                        if not _PX_RX.search(str(_play)):
                            continue
                        try:
                            if _pt == "LINE":
                                _pL = _line_length((_pe.dxf.start.x, _pe.dxf.start.y),
                                                   (_pe.dxf.end.x, _pe.dxf.end.y))
                            elif _pt == "LWPOLYLINE":
                                _pL = _lwpolyline_length(_pe)
                            elif _pt == "POLYLINE":
                                _pL = _polyline_length(_pe)
                            else:
                                _pr = _pe.dxf.radius
                                _pa0 = math.radians(_pe.dxf.start_angle)
                                _pa1 = math.radians(_pe.dxf.end_angle)
                                if _pa1 < _pa0:
                                    _pa1 += 2 * math.pi
                                _pL = abs(_pr * (_pa1 - _pa0))
                            _pL *= unit_factor
                        except Exception:
                            continue
                        if _pL > 0:
                            walls.append(WallSegment(layer=_play, length=_pL,
                                                     start=(0, 0), end=(0, 0)))
                            _n_px_walls += 1
                except Exception:
                    continue
        except Exception:
            pass          # query pode nem existir no doc — nunca derruba
        finally:
            _ezlog2.setLevel(_ez_prev2)
        # 🕳️ 08/08 — a 1ª versão disto era `logger.info`, que só existe no fluxo
        # do Render e NÃO é consultável. Reprocessei o arquivo do João pra medir
        # o conserto e fiquei sem saber se ele achou proxy ou não — instrumento
        # feito, evidência jogada fora. É a armadilha de
        # [[feedback-evidencia-nao-sobrevive]], e foi ela que fez o log de
        # unidade nascer (sem ele, o cabeçalho mentiroso da Isabelle só apareceu
        # abrindo o arquivo na mão).
        #
        # Agora vai pro `metadata`, que o main.py grava no error_log — o mesmo
        # caminho de `motor:unidade`. Grava SEMPRE que houver proxy, mesmo com 0
        # medido: "achou 300 proxies e mediu 0" e "não tem proxy nenhum" são
        # diagnósticos OPOSTOS e sem isso viram a mesma linha em branco.
        if _n_px_ents:
            metadata["proxy_aec_entidades"] = _n_px_ents
            metadata["proxy_aec_varridas"] = _n_px_scan
            metadata["proxy_aec_segmentos"] = _n_px_walls
            logger.info("[proxy-aec] %d ACAD_PROXY_ENTITY na prancha · %d entidades "
                        "varridas · +%d segmentos de infra linear medidos",
                        _n_px_ents, _n_px_scan, _n_px_walls)

    # ---- Áreas de polilinha FECHADA — SÓ camadas de superfície física -------
    # Conservador de propósito (regra nº1: nunca inflar/forjar medida):
    #  - ALLOWLIST: só conta polilinha fechada em layer claramente de piso/forro/laje.
    #  - exclui quadro/memorial/zona de áreas (sobreposição de CÁLCULO, não superfície).
    #  - DEDUPE aninhamento: descarta contorno contido em outro maior já aceito,
    #    pra não somar piso + cada cômodo dentro + versão existente/nova da mesma área.
    polygon_areas: list[HatchArea] = []
    # "flor" REMOVIDO (revisão adversarial 15/07): casava FLOREIRA/FLORAL/FLORES
    # (paisagismo) → contorno decorativo virava área de piso. "floor" real já é
    # coberto por piso/pavimenta/deck. Nunca inflar medida (regra nº1).
    _AREA_ALLOW = ("piso", "forro", "laje", "teto", "contrapiso", "cobertura",
                   "revestimento", "pavimenta", "deck", "impermeab", "ambiente")
    _AREA_DENY = ("trama", "pagina", "rotulo", "rótulo", "legenda", "cota", "carimbo",
                  "titulo", "título", "hachura", "eixo", "memorial", "quadro", "zona")
    _poly_cands: list = []  # (area_m2, bbox, layer)

    def _consider_poly(layer_name, pts):
        try:
            if len(pts) < 3:
                return
            clean = layer_name.split("|", 1)[-1].lower()
            if any(t in clean for t in _AREA_DENY):
                return
            if not any(t in clean for t in _AREA_ALLOW):
                return  # allowlist: só superfície física reconhecível
            a = abs(_shoelace_area(pts)) * area_factor
            if a < 0.5:
                return
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            _poly_cands.append((a, (min(xs), min(ys), max(xs), max(ys)), layer_name))
        except Exception:
            return

    for _lw in msp.query("LWPOLYLINE"):
        try:
            if getattr(_lw, "closed", False):
                _consider_poly(_lw.dxf.layer, list(_lw.get_points(format="xy")))
        except Exception:
            continue
    for _pl in msp.query("POLYLINE"):
        try:
            if getattr(_pl, "is_closed", False):
                _consider_poly(_pl.dxf.layer, [(v.dxf.location.x, v.dxf.location.y) for v in _pl.vertices])
        except Exception:
            continue

    def _bbox_inside(b, B, tol=0.5):
        return b[0] >= B[0]-tol and b[1] >= B[1]-tol and b[2] <= B[2]+tol and b[3] <= B[3]+tol

    _accepted: list = []
    for _cand in sorted(_poly_cands, key=lambda x: -x[0]):
        if any(_bbox_inside(_cand[1], _acc[1]) for _acc in _accepted):
            continue  # contido em um maior já aceito → aninhado, não soma
        _accepted.append(_cand)
    for _a, _bb, _ly in _accepted:
        polygon_areas.append(HatchArea(layer=_ly, area=_a, pattern="contorno fechado"))

    # ---- PILARES: retângulos/círculos FECHADOS em layer de PILAR ------------
    # Medição estrutural determinística (regra nº1): pilar em planta de fôrma é
    # um retângulo pequeno fechado. Antes ele virava só "perímetro somado" no
    # layer e a IA não tinha COMO contar → qty=0. Aqui a contagem é geométrica.
    # Conservador: só layer que NOMEIA pilar, só contorno fechado de 4 lados
    # (ou círculo), com lado 8cm–2,5m e área ≤ 3 m². Nada disso roda em prancha
    # de arquitetura sem layer de pilar.
    struct_rects: list = []
    if StructRect is not None:
        def _consider_pilar_poly(layer_name, pts):
            try:
                if not layer_is_pilar(layer_name):
                    return
                # remove ponto final repetido (polilinha fechada com 1º=último)
                if len(pts) >= 2 and abs(pts[0][0] - pts[-1][0]) < 1e-9 \
                        and abs(pts[0][1] - pts[-1][1]) < 1e-9:
                    pts = pts[:-1]
                if len(pts) != 4:
                    return
                d = [_line_length(pts[i], pts[(i + 1) % 4]) for i in range(4)]
                if min(d) <= 0:
                    return
                # lados opostos ~iguais (retângulo/paralelogramo, tolerância 15%)
                if abs(d[0] - d[2]) > 0.15 * max(d[0], d[2]):
                    return
                if abs(d[1] - d[3]) > 0.15 * max(d[1], d[3]):
                    return
                w_raw = (d[0] + d[2]) / 2.0
                h_raw = (d[1] + d[3]) / 2.0
                w_m, h_m = w_raw * unit_factor, h_raw * unit_factor
                if not (0.08 <= min(w_m, h_m) and max(w_m, h_m) <= 2.5
                        and w_m * h_m <= 3.0):
                    return
                cx = sum(p[0] for p in pts) / 4.0
                cy = sum(p[1] for p in pts) / 4.0
                struct_rects.append(StructRect(layer=layer_name, w_m=w_m, h_m=h_m,
                                               w_raw=w_raw, h_raw=h_raw, cx=cx, cy=cy))
            except Exception:
                return

        for _lw in msp.query("LWPOLYLINE"):
            try:
                if getattr(_lw, "closed", False):
                    _consider_pilar_poly(_lw.dxf.layer, list(_lw.get_points(format="xy")))
            except Exception:
                continue
        for _pl in msp.query("POLYLINE"):
            try:
                if getattr(_pl, "is_closed", False):
                    _consider_pilar_poly(_pl.dxf.layer,
                                         [(v.dxf.location.x, v.dxf.location.y) for v in _pl.vertices])
            except Exception:
                continue
        for _ci in msp.query("CIRCLE"):
            try:
                _ly_ci = _ci.dxf.layer
                if not layer_is_pilar(_ly_ci):
                    continue
                _d_raw = 2.0 * _ci.dxf.radius
                _d_m = _d_raw * unit_factor
                if 0.08 <= _d_m <= 1.5:
                    struct_rects.append(StructRect(layer=_ly_ci, w_m=_d_m, h_m=_d_m,
                                                   w_raw=_d_raw, h_raw=_d_raw,
                                                   cx=_ci.dxf.center.x, cy=_ci.dxf.center.y,
                                                   circular=True))
            except Exception:
                continue
        if len(struct_rects) > 5000:  # teto defensivo de memória
            struct_rects = struct_rects[:5000]

    # ---- Hatches ----------------------------------------------------------
    hatches: list[HatchArea] = []

    for hatch in msp.query("HATCH"):
        try:
            area = _hatch_area(hatch) * area_factor
            pattern = ""
            try:
                pattern = hatch.dxf.pattern_name
            except Exception:
                pass
            if area > 0:
                hatches.append(HatchArea(
                    layer=hatch.dxf.layer,
                    area=area,
                    pattern=pattern,
                ))
        except Exception:
            continue

    # ---- Texts ------------------------------------------------------------
    texts: list[TextAnnotation] = []

    for text in msp.query("TEXT"):
        try:
            content = text.dxf.text.strip()
            if content:
                pos = (text.dxf.insert.x, text.dxf.insert.y)
                height = text.dxf.height if hasattr(text.dxf, "height") else 0
                texts.append(TextAnnotation(
                    layer=text.dxf.layer,
                    text=content,
                    position=pos,
                    height=height,
                ))
        except Exception:
            continue

    for mtext in msp.query("MTEXT"):
        try:
            # Tentar primeiro o .plain_text() do ezdxf (já strip da formatação)
            try:
                content = mtext.plain_text(split=False).strip()
            except Exception:
                content = _strip_mtext_codes(mtext.text).strip()
            if content:
                pos = (mtext.dxf.insert.x, mtext.dxf.insert.y)
                height = mtext.dxf.char_height if hasattr(mtext.dxf, "char_height") else 0
                texts.append(TextAnnotation(
                    layer=mtext.dxf.layer,
                    text=content,
                    position=pos,
                    height=height,
                ))
        except Exception:
            continue

    # ---- Dimensions -------------------------------------------------------
    dims: list[tuple] = []

    for dim in msp.query("DIMENSION"):
        try:
            measurement = None
            label = ""
            # Try to get the actual measurement value
            try:
                measurement = dim.dxf.actual_measurement
            except Exception:
                pass
            # actual_measurement é "optional and often not present" (doc ezdxf);
            # get_measurement() recalcula da geometria e recupera cota que sumia.
            if measurement is None:
                try:
                    measurement = dim.get_measurement()
                    if not isinstance(measurement, (int, float)):
                        measurement = None  # angular/obj — ignora
                except Exception:
                    measurement = None
            # Try to get overridden text
            try:
                label = dim.dxf.text.strip()
            except Exception:
                pass
            if measurement is not None:
                value_m = measurement * unit_factor
                # Pular cotas vazias (0 ou muito pequenas — provavelmente dim sem valor real)
                if abs(value_m) < 0.001:
                    continue
                display_label = label if label else "cota"
                dims.append((display_label, f"{value_m:.3f} m"))
            elif label and label != "0" and label != "":
                dims.append((label, label))
        except Exception:
            continue

    # ── Sinais de qualidade da extração (#6 estéril/xref + #4 unidade) ──
    # Mede se a extração realmente leu geometria. Se ZERO, a IA NÃO deve
    # "preencher" com itens de práxis como se fossem medidos sem o usuário saber.
    measured_signal = len(blocks) + len(walls) + len(hatches) + len(dims) + len(polygon_areas)
    metadata["sinal_medido"] = measured_signal
    if measured_signal == 0:
        metadata["extracao_esteril"] = True
    # xref: layers vêm com prefixo "arquivo|layer". Se há xref referenciado mas
    # quase nenhuma geometria, a referência externa provavelmente NÃO foi
    # resolvida (ezdxf não carrega xref externo) — o arquitetônico pode estar lá.
    try:
        _xref_files = sorted({ln.split("|", 1)[0] for ln in layer_names if "|" in ln})
    except Exception:
        _xref_files = []
    if _xref_files and measured_signal < 5:
        metadata["xref_nao_resolvido"] = "; ".join(_xref_files[:5])
    if unit_warnings:
        metadata["unidade_suspeita"] = " | ".join(unit_warnings)

    # Duto desenhado pelas DUAS FACES: mede o eixo, não a soma das paralelas.
    # 🪤 unit_factor é OBRIGATÓRIO aqui: start/end são coordenadas cruas e
    # length já está em metro. Sem o fator, a separação entre as faces sai
    # errada por ordens de grandeza e nada pareia em desenho de milímetro.
    walls, _rel_duto, _ress_duto = _corrigir_duto_linha_dupla(walls, unit_factor)
    if _rel_duto:
        metadata["duto_linha_dupla"] = _rel_duto
    # Chave SEPARADA e com leitor: entra em extraction_has_quality_caveat, que
    # rebaixa o desenho todo pra estimado. A de cima é informativa; esta é
    # ressalva de qualidade — sem leitor, o aviso morria no log e o número
    # saía carimbado como MEDIDO (regra dura nº1).
    if _ress_duto:
        metadata["duto_medicao_suspeita"] = _ress_duto

    # ── ÁREA lida do quadro por REGRA, não por IA (08/08/2026) ──────────────
    # 🚨 A área total sai hoje só da IA lendo o quadro de áreas. Medido: o MESMO
    # arquivo, rodado 2× no mesmo motor, deu 458,54 m² e 177 m². E a temperatura
    # já é 0 (conferido no /api/health) — temperatura zero é decodificação
    # gulosa, não garantia de determinismo. Não há flag que conserte.
    #
    # O quadro de áreas é TEXTO, e o texto está aqui. Ler por regra é
    # determinístico: o mesmo arquivo dá sempre o mesmo número.
    #
    # ⚠️ NÃO substitui a IA — entra como leitura ADICIONAL no consenso do
    # main.py (`_pick_area_consensus`, que agrupa por ±5% e tira a moda). Se o
    # quadro não existir, nada muda.
    try:
        from engine_rules import areas_do_texto_da_prancha as _areas_regra
        _cand = _areas_regra([getattr(t, "text", "") for t in texts])
        if _cand:
            metadata["areas_do_quadro_texto"] = _cand
            logger.info("[area-regra] %d candidato(s) de área lidos do texto: %s",
                        len(_cand), _cand[:6])
    except Exception as _ea:
        logger.warning("[area-regra] falhou (não-fatal): %s", _ea)

    return DXFExtraction(
        filename=os.path.basename(filepath),
        blocks=blocks,
        walls=walls,
        hatches=hatches,
        texts=texts,
        layers=layer_names,
        dimensions=dims,
        metadata=metadata,
        polygon_areas=polygon_areas,
        struct_rects=struct_rects,
    )


# ---------------------------------------------------------------------------
# Architectural element identification via layer naming conventions
# ---------------------------------------------------------------------------

# Matching é feito por TOKEN: o nome do layer é dividido em partes (por -, _, ., /
# etc.) e cada parte é comparada aos aliases. Match = token EQUALS alias ou token
# STARTS WITH alias. Isso pega tanto nomes AIA ("A-WALL-INT"), numéricos
# ("04-PAREDES_DRYWALL"), portugueses ("FOR-GESSO") quanto curtos ("LUM-01").
_LAYER_PATTERNS: list[tuple[list[str], str]] = [
    (["LUM", "LUMI", "LUMINARIA", "ILUM", "ILU", "LIGHT", "LT", "LGT"],                           "luminarias"),
    (["PAR", "PARED", "PAREDE", "WALL", "DRY", "DRYWALL", "GESS", "GYP", "DIV", "DVR"],           "paredes"),
    (["FOR", "FORR", "FORRO", "CEIL", "TET", "TETO"],                                             "forro"),
    (["PIS", "PISO", "FLOOR", "FLR", "PAV", "CARPE", "CARPET", "RODA", "RODAP", "SKIRT"], "piso"),
    (["PORT", "PORTA", "PRT", "DOOR", "DR"],                                                      "portas"),
    (["SPK", "SPRINK", "SPRINKLER", "INC", "INCEND", "INCENDIO", "FIRE", "PPCI"],                 "incendio"),
    (["ELET", "ELETR", "ELE", "ELEC", "POWR", "POWER", "TOMAD", "TOM", "TOMADA", "INTER", "CIRC"], "eletrica"),
    (["HVAC", "COND", "CLIMA", "DUTO", "DIFUS", "FRIG", "EVAP", "SPLIT", "CHILL", "ARCOND"],      "ar_condicionado"),
    (["DAD", "DADOS", "DATA", "REDE", "LOG", "VOIP", "RJ", "CAT6", "WIFI", "ACCESS"],             "dados"),
    (["DEM", "DEMOL", "DEMO", "DEMOLIR"],                                                         "demolicao"),
    (["PINT", "PINTURA", "PAINT", "PNT"],                                                         "pintura"),
]

_LAYER_SPLIT_RE = re.compile(r"[-_\s./\\|:]+")


def _layer_matches_category(layer_name: str, keywords: list[str]) -> bool:
    """Return True se algum token do layer_name casa com algum keyword.
    Match via EQUALS ou STARTS WITH (case-insensitive)."""
    if not layer_name:
        return False
    tokens = [t.upper() for t in _LAYER_SPLIT_RE.split(layer_name) if t]
    for tok in tokens:
        for kw in keywords:
            if tok == kw or tok.startswith(kw):
                return True
    return False


def identify_architectural_elements(extraction: DXFExtraction) -> dict:
    """Map extraction data to architectural categories based on layer AND block names.

    Classificação em dois passos:
    1. Layer → categoria (primary)
    2. Block name → categoria (fallback quando o layer é genérico ex. "0" ou xref)

    Returns:
        dict mapping category name to a dict with keys:
            - "layers": list of matching layer names
            - "blocks": list of BlockCount categorized (via layer OR nome)
            - "walls": list of WallSegment on matching layers
            - "hatches": list of HatchArea on matching layers
            - "texts": list of TextAnnotation on matching layers
    """
    result: dict = {}

    for keywords, category in _LAYER_PATTERNS:
        matching_layers = [
            lyr for lyr in extraction.layers
            if _layer_matches_category(lyr, keywords)
        ]
        layer_set = set(matching_layers)

        # Blocks classificados por layer
        blocks_by_layer = [b for b in extraction.blocks if b.layer in layer_set]
        # Blocks classificados pelo NOME (rodape, porta_PM3, lum-R4) — só se
        # o layer ainda não casou, evita dupla categorização
        blocks_by_name = [
            b for b in extraction.blocks
            if b.layer not in layer_set
            and _layer_matches_category(b.name, keywords)
        ]
        blocks_combined = blocks_by_layer + blocks_by_name

        if not matching_layers and not blocks_by_name:
            continue

        result[category] = {
            "layers": matching_layers,
            "blocks": blocks_combined,
            "walls": [w for w in extraction.walls if w.layer in layer_set],
            "hatches": [h for h in extraction.hatches if h.layer in layer_set],
            "texts": [t for t in extraction.texts if t.layer in layer_set],
        }

    return result


def category_for_layer(layer_name: str) -> str | None:
    """Retorna a categoria arquitetônica de UM layer (piso/forro/paredes/...),
    ou None se não casar. Mesma regra de token de identify_architectural_elements.
    Usado pelo cross-check pra categorizar polígonos fechados por layer."""
    for keywords, category in _LAYER_PATTERNS:
        if _layer_matches_category(layer_name, keywords):
            return category
    return None


# ---------------------------------------------------------------------------
# Entry point — handles both .dxf and .dwg
# ---------------------------------------------------------------------------

def probe_unit(filepath: str) -> Optional[float]:
    """Sondagem LEVE de unidade: lê o DXF e retorna o fator (p/ metros) PROVADO
    por COTA nesta prancha, ou None se ela não tem cotas suficientes. Usado no
    consenso de unidade por projeto (process_job) — barato de rodar em algumas
    pranchas até achar uma com cota, sem extrair geometria. Nunca levanta: em
    qualquer erro (arquivo grande/ilegível) devolve None e o consenso segue."""
    try:
        filepath = os.path.abspath(filepath)
        if not os.path.isfile(filepath) or Path(filepath).suffix.lower() != ".dxf":
            return None
        if os.path.getsize(filepath) > 150 * 1024 * 1024:
            return None
        doc = None
        for enc in ("utf-8", "latin-1", None):
            try:
                doc = ezdxf.readfile(filepath, **({"encoding": enc} if enc else {}))
                break
            except UnicodeDecodeError:
                continue
            except Exception:
                if enc is None:
                    return None
        if doc is None:
            return None
        uf = _detect_unit_factor(doc)
        uf, _ = _validate_unit_factor(doc, uf)
        dim = _validate_unit_by_dimensions(doc, uf)
        st = dim.get("status")
        if st == "corrigida":
            return dim.get("fator_corrigido")
        if st == "validada":
            return uf
        return None
    except Exception:
        return None


def extract_from_file(filepath: str, unit_factor_override: Optional[float] = None) -> DXFExtraction:
    """High-level entry point: extract structured data from a DWG or DXF file.

    Args:
        filepath: Path to .dwg or .dxf file.
        unit_factor_override: escala provada por cota em outra prancha do projeto
            (consenso). Repassada ao extract_dxf — só usada se a prancha não tem
            cota própria.

    Returns:
        DXFExtraction with all extracted elements.

    Raises:
        ValueError: If the file extension is not .dwg or .dxf.
        FileNotFoundError: If the file does not exist.
        RuntimeError: If DWG conversion fails and no DXF is available.
    """
    filepath = os.path.abspath(filepath)
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"Arquivo não encontrado: {filepath}")

    ext = Path(filepath).suffix.lower()

    if ext == ".dxf":
        return extract_dxf(filepath, unit_factor_override=unit_factor_override)

    if ext == ".dwg":
        dxf_path = convert_dwg_to_dxf(filepath)
        if dxf_path is None:
            raise RuntimeError(
                f"Não foi possível converter o arquivo DWG: {filepath}. "
                "Instale o ODA File Converter (gratuito) para converter arquivos .dwg, "
                "ou exporte o arquivo como .dxf no AutoCAD/BricsCAD."
            )
        try:
            return extract_dxf(dxf_path, unit_factor_override=unit_factor_override)
        finally:
            # Clean up the temporary DXF
            try:
                os.unlink(dxf_path)
            except OSError:
                pass

    raise ValueError(
        f"Formato de arquivo não suportado: '{ext}'. "
        "Use arquivos .dxf ou .dwg."
    )


# ---------------------------------------------------------------------------
# Budget data generation
# ---------------------------------------------------------------------------

# Map architectural category -> discipline name (matching models.py)
_CATEGORY_TO_DISCIPLINE: dict[str, str] = {
    "luminarias":        "Iluminação",
    "paredes":           "Fechamentos Verticais",
    "forro":             "Forros",
    "piso":              "Pisos e Rodapés",
    "portas":            "Portas e Ferragens",
    "incendio":          "Prevenção e Combate a Incêndio",
    "eletrica":          "Instalações Elétricas",
    "ar_condicionado":   "Ar-Condicionado",
    "dados":             "Instalações Elétricas e Dados",
    "demolicao":         "Demolição e Remoção",
    "pintura":           "Revestimentos",
}


def generate_budget_data(extraction: DXFExtraction) -> dict:
    """Convert extracted DXF data into a budget-ready dict of items.

    The output format is compatible with the BudgetItem model defined in
    models.py (fields: description, unit, quantity, discipline, confidence).

    Returns:
        dict with key "items" containing a list of budget item dicts.
    """
    items: list[dict] = []
    elements = identify_architectural_elements(extraction)

    # --- Blocks: count by category -----------------------------------------
    for category, data in elements.items():
        discipline = _CATEGORY_TO_DISCIPLINE.get(category, category.title())
        for block in data["blocks"]:
            items.append({
                "description": f"{block.name}",
                "unit": "un",
                "quantity": block.count,
                "discipline": discipline,
                "confidence": "estimado",  # desarmado: era 'confirmado' hardcoded — só a trava de procedência confirma
                "source": "DXF block count",
            })

    # --- Walls: sum lengths by category ------------------------------------
    for category, data in elements.items():
        discipline = _CATEGORY_TO_DISCIPLINE.get(category, category.title())
        total_length = sum(w.length for w in data["walls"])
        if total_length > 0:
            desc_map = {
                "paredes": "Parede drywall nova",
                "demolicao": "Demolição de parede existente",
            }
            description = desc_map.get(category, f"Comprimento linear — {category}")
            items.append({
                "description": description,
                "unit": "m",
                "quantity": round(total_length, 2),
                "discipline": discipline,
                "confidence": "estimado",  # desarmado: era 'confirmado' hardcoded — só a trava de procedência confirma
                "source": "DXF line measurement",
            })

    # --- Hatches: sum areas by category ------------------------------------
    for category, data in elements.items():
        discipline = _CATEGORY_TO_DISCIPLINE.get(category, category.title())
        total_area = sum(h.area for h in data["hatches"])
        if total_area > 0:
            desc_map = {
                "pintura": "Pintura (área hachurada)",
                "piso": "Piso (área hachurada)",
                "forro": "Forro (área hachurada)",
            }
            description = desc_map.get(category, f"Área — {category}")
            items.append({
                "description": description,
                "unit": "m²",
                "quantity": round(total_area, 2),
                "discipline": discipline,
                "confidence": "estimado",  # desarmado: era 'confirmado' hardcoded — só a trava de procedência confirma
                "source": "DXF hatch area",
            })

    # --- Uncategorized blocks (not on recognized layers) -------------------
    categorized_block_names = set()
    for data in elements.values():
        for b in data["blocks"]:
            categorized_block_names.add(b.name)

    for block in extraction.blocks:
        if block.name not in categorized_block_names:
            items.append({
                "description": f"{block.name}",
                "unit": "un",
                "quantity": block.count,
                "discipline": "",
                "confidence": "verificar",
                "source": "DXF block count (sem categoria identificada)",
            })

    # --- Dimension texts: look for room area annotations -------------------
    for label, value in extraction.dimensions:
        items.append({
            "description": f"Cota: {label}",
            "unit": "m",
            "quantity": 0,
            "discipline": "",
            "confidence": "verificar",
            "source": f"DXF dimension: {value}",
        })

    return {"items": items}


# ---------------------------------------------------------------------------
# CLI testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if len(sys.argv) > 1:
        target = sys.argv[1]
        result = extract_from_file(target)
        print(result.to_structured_prompt())
        print(f"\n=== RESUMO ===")
        print(f"Blocos: {len(result.blocks)} tipos")
        print(f"Paredes: {len(result.walls)} segmentos")
        print(f"Áreas: {len(result.hatches)} hachuras")
        print(f"Textos: {len(result.texts)} anotações")

        budget = generate_budget_data(result)
        if budget["items"]:
            print(f"\n=== ITENS DE ORÇAMENTO ({len(budget['items'])}) ===")
            for item in budget["items"]:
                print(f"  [{item['discipline'] or '?'}] {item['description']}: "
                      f"{item['quantity']} {item['unit']} "
                      f"({item['confidence']})")
    else:
        print("Uso: python dwg_extractor.py <arquivo.dxf|dwg>")
