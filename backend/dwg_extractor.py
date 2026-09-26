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
    # Assinatura da DEFINICAO do bloco: tipos de entidade e quantos de cada.
    # Serve pra saber se dois nomes diferentes sao a MESMA peca renomeada.
    # Vazia = nao deu pra calcular; nesse caso NAO se agrupa nada (falha fechada).
    assinatura: str = ""


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
    # Leitura por folha: quantos andares esta linha representa (planta-tipo
    # "4º/5º/6º" → 3). As SOMAS multiplicam; o segmento continua um só, porque
    # quem faz geometria (pareamento de faces, salas) precisa dele uma vez.
    peso: float = 1.0
    # POLILINHA: start/end são o 1º e o último vértice — a forma de verdade
    # (a caixa em "U", o retângulo fechado) só está aqui. Preenchido SÓ em
    # layer candidato a linha dupla (duto/leito/legenda), pra não pesar a
    # memória no resto: tupla de (x, y, bulge) crus, fechada repete o 1º.
    pontos: tuple = ()


@dataclass
class HatchArea:
    """Área hachurada (pintura, piso, forro)."""
    layer: str
    area: float  # in m²
    pattern: str = ""
    # 🔑 Retângulo envolvente (x_min, y_min, x_max, y_max) na unidade do desenho.
    # Serve pra saber QUE TEXTO está DENTRO desta região — é o elo que faltava
    # entre "o rótulo diz PISO CERÂMICO" e "esta região tem 289,97 m²".
    # 🪤 O caminho do polígono fechado já calculava esse bbox e jogava fora.
    # Vazio () quando desconhecido.
    bbox: tuple = ()
    # Quanto da própria caixa a forma ocupa (0..1). 🚨 Calculado AQUI porque só
    # aqui as duas unidades são conhecidas: `area` sai em m² (já multiplicada
    # pelo fator) e `bbox` fica em unidade CRUA do desenho, pra casar com
    # TextAnnotation.position. Dividir um pelo outro lá fora dava 0,000 em 310
    # de 310 hachuras — o mesmo erro de 1000× que persigo o dia todo.
    preenchimento: float = 0.0
    # Leitura por folha: andares que esta região representa (ver WallSegment).
    peso: float = 1.0


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
    #: 🩸 09/09/2026 — por que o contorno fechado foi RECUSADO, por motivo.
    #: Sem isto, `poligonos=0` tinha dois significados opostos ("o desenho não
    #: tem contorno fechado" e "tem, e a peneira de NOME jogou fora") e os dois
    #: viravam a mesma ausência. Só observação: não muda nada do que é medido.
    poly_recusa: dict = field(default_factory=dict)
    poly_layers_recusados: dict = field(default_factory=dict)
    struct_rects: list = field(default_factory=list)  # retângulos/círculos FECHADOS em layer de PILAR (StructRect) — contagem de pilar medida
    # Atributos de bloco (ATTRIB): dado ESTRUTURADO que o projetista escreveu
    # com nome de campo — quadro de áreas, etiqueta de ambiente, carimbo.
    # [{bloco, layer, campos:{tag: valor}}]
    block_attributes: list = field(default_factory=list)
    # 🔬 26/08: por que `blocos` deu o número que deu. Sem isto não dá pra
    # distinguir "o desenho não tem bloco" de "a gente descartou todos"
    # (caso cliente-36, prancha elétrica: blocos=0 com 76.824 linhas).
    # {anonimo, utilitario, anotacao, ilegivel, amostra_anonimo}
    blocos_descartados: dict = field(default_factory=dict)
    # 🔬 27/08: por que `pilares` deu o número que deu. {nome_do_layer,
    # nao_e_4_lados, nao_e_retangulo, fora_de_escala, ilegivel, amostra_layers}
    pilares_descartados: dict = field(default_factory=dict)
    # 🔑 24/09: o desenho que veio COLADO COMO BLOCO (A$C…) e foi aberto na
    # entrada. {abertos, entidades, niveis, falhas, teto} — ver
    # `abrir_blocos_colados`. Vazio quando o arquivo não tinha nenhum.
    blocos_colados: dict = field(default_factory=dict)
    # Leitura por folha: os desenhos do arquivo (planta/esquema/detalhe, andares)
    # e o que mudou na medição. Vazio = não aplicada (ver `motivo`).
    folhas: dict = field(default_factory=dict)

    # -- convenience helpers ------------------------------------------------

    def get_block_summary(self) -> dict:
        """Returns {block_name: total_count}."""
        summary: Counter = Counter()
        for b in self.blocks:
            summary[b.name] += b.count
        return dict(summary)

    def get_walls_by_layer(self) -> dict:
        """Returns {layer_name: total_length_meters} — × andares da planta (leitura por folha)."""
        result: dict[str, float] = defaultdict(float)
        for w in self.walls:
            result[w.layer] += w.length * getattr(w, "peso", 1.0)
        return dict(result)

    def get_areas_by_layer(self) -> dict:
        """Returns {layer_name: total_area_m2} — × andares da planta (leitura por folha)."""
        result: dict[str, float] = defaultdict(float)
        for h in self.hatches:
            result[h.layer] += h.area * getattr(h, "peso", 1.0)
        return dict(result)

    def get_polygon_areas_by_layer(self) -> dict:
        """Returns {layer_name: total_area_m2} de polilinhas FECHADAS (ambientes)."""
        result: dict[str, float] = defaultdict(float)
        for p in self.polygon_areas:
            result[p.layer] += p.area * getattr(p, "peso", 1.0)
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

        # 📄 Leitura por folha: a IA precisa saber que as medidas abaixo JÁ vêm
        # sem o esquema/detalhe e com a planta-tipo multiplicada — senão ela
        # soma de novo o que tiramos, ou multiplica duas vezes.
        _fl = self.folhas or {}
        if _fl.get("aplicada"):
            _ds = _fl.get("desenhos_lista") or []
            _mult = [d for d in _ds if d.get("tipo") == "planta" and (d.get("andares") or 1) > 1]
            _fora = [d for d in _ds if d.get("tipo") == "fora"]
            _planta1 = [d for d in _ds if d.get("tipo") == "planta" and (d.get("andares") or 1) == 1]
            lines.append("DESENHOS DESTE ARQUIVO (lidos pelas folhas — as medidas abaixo JÁ refletem isto):")
            for d in _mult[:12]:
                lines.append(f"  • {d.get('titulo') or d.get('folha')}: vale por {d['andares']} andares — "
                             f"comprimentos, áreas e contagens desta planta JÁ estão × {d['andares']}")
            if _planta1:
                lines.append("  • plantas de um andar só: " + "; ".join(
                    (d.get("titulo") or d.get("folha"))[:50] for d in _planta1[:12]))
            if _fora:
                lines.append(f"  • {len(_fora)} desenho(s) FORA das medidas (esquema, detalhe, corte, "
                             f"situação — o mesmo objeto redesenhado ou recorte típico): " + "; ".join(
                                 (d.get("titulo") or d.get("folha"))[:50] for d in _fora[:8])
                             + ("…" if len(_fora) > 8 else ""))
            _vis = [d for d in _ds if d.get("tipo") == "vista"]
            if _vis and not _planta1 and not _mult:
                # 25/09: a prancha de CORTES do conjunto — a planta está em
                # outro arquivo e o motor lê um arquivo por vez
                lines.append("  • ⚠ esta prancha tem CORTE/ELEVAÇÃO e NENHUMA planta: as peças e "
                             "etiquetas daqui costumam ser as MESMAS da planta de OUTRA prancha "
                             "— NÃO some contagem daqui com a da planta; use só o que a planta "
                             "não mostra")
            if _vis and _fl.get("vista") is not None:
                # 25/09: sem isto a IA vê o leito do corte sumir e "completa"
                lines.append(f"  • {len(_vis)} corte(s)/elevação(ões) — o objeto visto DE LADO: o "
                             f"COMPRIMENTO das linhas delas JÁ está fora das medidas (e, nos "
                             f"cortes, a faixa fina da parede/laje CORTADA); a área de "
                             f"revestimento que aparece nelas ficou: " + "; ".join(
                                 (d.get("titulo") or d.get("folha"))[:40] for d in _vis[:8])
                             + ("…" if len(_vis) > 8 else ""))
            if _fl.get("repetidas"):
                _gr = _fl["repetidas"].get("grupos") or []
                def _versoes(g):
                    vs = g[3] if len(g) > 3 else []
                    return (" (versões: %s)" % " / ".join("%g" % v for v in vs)
                            if len(set(vs)) > 1 else "")
                lines.append("  • plantas TEMÁTICAS do mesmo pavimento (layout, luminotécnica, pontos, "
                             "forro, original…): a base redesenhada nelas JÁ foi contada UMA vez — "
                             "quando as plantas diferem (original × layout), ficou a MAIOR versão"
                             + (" — ex.: " + "; ".join("%s %s m em %d plantas%s" % (g[0], g[1], g[2], _versoes(g))
                                                       for g in _gr[:4]) if _gr else "")
                             + ". Não some as plantas entre si. Esse comprimento é o que está "
                             "DESENHADO numa versão do pavimento: não o chame de parede NOVA/A "
                             "CONSTRUIR — parede nova só com o que o desenho marca como construir.")
            lines.append("  Não some de novo o que está fora nem multiplique de novo a planta-tipo. "
                         "Use o esquema e os detalhes só para ler diâmetro, material e especificação.")
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
                # 🚨 JUNTA O QUE O CONVERSOR FRAGMENTOU (26/08/2026).
                # O libredwg (88% das conversoes) renomeia bloco POR INSTANCIA:
                # num DXF real, 1.202 nomes distintos pra 1.349 pecas. A secao
                # virava 44% do prompt, e na prancha da cliente-16 a entrada chegou a
                # 74.875 tokens com ZERO item de volta. Pior: o cliente via
                # "Viga_1_1: 1 un" 209 vezes em vez de "Viga: 209 un".
                #
                # 🪤 Agrupar so pelo NOME estaria ERRADO — e eu quase shipei
                # assim. `Parede_1_1` e `Parede_2_1` tinham SEIS definicoes
                # geometricas diferentes na amostra: sao trechos distintos, e
                # soma-los repetiria o bug da bitola (Ø8 + Ø16 num numero so,
                # 18.168 kg viraram 508 kg).
                # So junta quando a ASSINATURA da definicao e identica — ai sao
                # comprovadamente a mesma peca, e somar RESTAURA a contagem certa.
                # 🪤 Sem assinatura (nao deu pra ler a definicao) nao agrupa nada:
                # falha fechada, mantem o comportamento antigo.
                _assin = {b.name: getattr(b, "assinatura", "") for b in self.blocks}
                _grupos: dict = {}
                for name, count in other.items():
                    a = _assin.get(name, "")
                    # 🚨 DOIS formatos de fragmentacao, medidos em arquivo real:
                    #  a) Revit/ArchiCAD: "CHUVEIRO - CHUVEIRO-1320392-PORTARIA"
                    #     (FAMILIA - TIPO-<id>-<vista>). Nas pranchas da cliente-16
                    #     os nomes tinham 55 a 61 caracteres e eram 1.570 -- so
                    #     essa secao dava 99.901 chars. Agrupar pela FAMILIA
                    #     derruba pra 17.464 (-83%).
                    #  b) sufixo do conversor: "Viga_12_1" -> "Viga".
                    if " - " in name:
                        raiz = name.split(" - ", 1)[0].strip() or name
                    else:
                        raiz = re.sub(r"(_\d+)+$", "", name) or name
                    chave = (raiz, a) if a else (name, "")
                    if chave in _grupos:
                        _grupos[chave][0] += count
                        _grupos[chave][1] += 1
                    else:
                        _grupos[chave] = [count, 1, raiz if a else name]
                # 🪤 A MESMA raiz pode sobrar em VARIOS grupos — e isso e
                # correto: "Viga" com 3 assinaturas sao 3 pecas diferentes. Mas
                # tres linhas chamadas "Viga" na planilha do cliente sao
                # indistinguiveis. Numera os homonimos pra ele conseguir separar.
                _quantos_por_raiz: dict = {}
                for (_r, _a) in _grupos:
                    _quantos_por_raiz[_r] = _quantos_por_raiz.get(_r, 0) + 1
                _seq: dict = {}
                _juntados = sum(1 for v in _grupos.values() if v[1] > 1)
                lines.append(f"CONTAGEM DE BLOCOS ({len(_grupos)} tipos):")
                for (_r, _a), (count, n_nomes, rotulo) in sorted(
                        _grupos.items(), key=lambda x: -x[1][0]):
                    if _quantos_por_raiz.get(_r, 1) > 1 and _a:
                        _seq[_r] = _seq.get(_r, 0) + 1
                        rotulo = f"{rotulo} (tipo {_seq[_r]})"
                    _nota = f"  [{n_nomes} nomes do conversor, mesma peca]" if n_nomes > 1 else ""
                    lines.append(f"  {rotulo}: {count} un{_nota}")
                if _juntados:
                    lines.append(f"  ({_juntados} grupo(s) tinham nomes duplicados pelo "
                                 f"conversor e foram somados — so quando a definicao "
                                 f"geometrica e IDENTICA. 'tipo 1/2/3' sao pecas "
                                 f"DIFERENTES com o mesmo nome de origem.)")
                lines.append("")

        # Wall lengths
        # 🩸 09/09/2026 — ESTA LISTA IA CRUA PRA IA, E UM QUARTO DELA É TEXTO.
        # `walls` recebe TODA LINE/LWPOLYLINE/POLYLINE/ARC/CIRCLE do modelspace,
        # sem filtro de layer nenhum — enquanto os outros dois caminhos que
        # alimentam `walls` filtram por `INFRA_LINEAR_RX`.
        # 🩸 CORREÇÃO (09/09, mesma noite): eu escrevi aqui que "o bloco de ÁREA
        # logo abaixo tem allowlist E denylist" e ISSO ESTAVA ERRADO. As listas
        # `_AREA_ALLOW`/`_AREA_DENY` valem só pra POLILINHA FECHADA
        # (`_consider_poly`); o laço de HATCH — que é o que alimenta ÁREAS
        # HACHURADAS POR LAYER — não filtra layer nenhum. Ou seja, hachura de
        # layer de anotação também vira área, e eu tinha afirmado o contrário
        # num comentário permanente. Por isso o rótulo abaixo vale pros DOIS.
        # 📏 Medido nos logs `motor:parede-medida` (7 jobs, 98 layers de topo):
        # **18 layers de anotação somando 7.401 m de 29.227 m — 25,3%** do que o
        # motor chama de "comprimento de parede". Num pórtico, `ARQ_TEX-4`
        # sozinha respondia por 88,8% do total do arquivo.
        #
        # 🚫 POR QUE NÃO FILTRAR. Tirar essas layers de `walls` mexeria em
        # `sinal_medido` (`len(blocks)+len(walls)+...`), que é o que decide se a
        # extração é declarada ESTÉRIL — um arquivo legítimo podia passar a ser
        # recusado. E apagar dado é o erro que ninguém vê: a casa já decidiu o
        # contrário no consolidador (*"duplicar é erro que o arquiteto vê,
        # apagar é erro que ele não vê"*).
        # 🔑 Então a lista continua inteira e ganha um RÓTULO. A IA passa a ver
        # qual layer é anotação em vez de ter que adivinhar pelo nome — e o
        # rebaixamento determinístico do selo (`layer_is_anotacao` no main.py)
        # continua sendo a rede embaixo, pra quando ela ignorar o rótulo.
        # 🪤 O import fica FORA dos dois blocos: `_anot` é usado tanto em
        # COMPRIMENTOS quanto em ÁREAS HACHURADAS, e uma prancha pode ter
        # hachura sem ter parede — deixá-lo dentro do `if walls_by_layer`
        # daria NameError justamente nessa prancha.
        try:
            from engine_rules import layer_is_anotacao as _anot
        except Exception:                        # best-effort: sem régua, sem rótulo
            def _anot(_x):
                return False
        walls_by_layer = self.get_walls_by_layer()
        if walls_by_layer:
            lines.append("COMPRIMENTOS POR LAYER:")
            _n_anot = 0
            for layer, length in sorted(walls_by_layer.items()):
                if _anot(layer):
                    _n_anot += 1
                    # 🪤 O texto NÃO pode conter "layer <palavra>": a régua
                    # que lê layer da observação (`_LAYER_RE`, main.py) casa
                    # "layer DE" e captura a preposição como se fosse o nome do
                    # layer. Se a IA ecoasse este aviso, o rebaixamento
                    # determinístico do selo deixaria de disparar — o aviso
                    # desligaria a rede que ele existe pra complementar.
                    lines.append(f"  {layer}: {length:.2f} m"
                                 f"   ⚠ ANOTAÇÃO DO DESENHO (texto/cota/legenda/"
                                 f"hachura) — o comprimento é de letras e setas, "
                                 f"NÃO é elemento de obra: não use como quantidade")
                else:
                    lines.append(f"  {layer}: {length:.2f} m")
            if _n_anot:
                # 🪤 Pede um TOKEN FIXO, não prosa livre: prosa em português
                # perto da palavra "layer" envenena a régua que lê a observação.
                lines.append(f"  ({_n_anot} marcada(s) como ANOTAÇÃO acima. Não crie "
                             f"item a partir delas; se criar, marque 'estimado' e "
                             f"escreva na observação exatamente: origem=anotacao)")
            lines.append("")

        # Hatch areas
        areas_by_layer = self.get_areas_by_layer()
        if areas_by_layer:
            # Conta hachuras por layer: quando um layer tem VÁRIAS hachuras, a área
            # listada é a SOMA — e pode misturar acabamentos diferentes desenhados no
            # MESMO layer (porcelanato + cerâmica em "ARQ-PISO"). A soma não mede
            # nenhum acabamento sozinho, então a IA deve tratar como ESTIMADO, não
            # confirmado (regra nº1 — revisão adversarial 15/07, Finding 1).
            # 🎯 26/08/2026 — O PADRÃO DA HACHURA É QUE SEPARA ACABAMENTO.
            # Até aqui, TODO layer com mais de uma hachura levava a mesma frase
            # "pode ser acabamento MISTO; trate como ESTIMADO" — e no CAD quem
            # distingue porcelanato de cerâmica é o PATTERN, que o extrator já
            # guardava (`HatchArea.pattern`) e o prompt jogava fora.
            #
            # 🔍 Medido: 80 de 88 layers (91%) têm UM padrão só. O alarme
            # disparava nos 91% que NÃO são mistos — alarme sem controle.
            # E o custo era grande: no acervo, área sai medida em 3,8% dos itens
            # (71 de 1.864) contra 36,3% da contagem, e em 10 semanas a área
            # nunca passou de 2,3% enquanto a contagem foi de 15% a 60%.
            #
            # 🪤 O prompt ainda se CONTRADIZIA: a regra global autoriza
            # "Área calculada em ÁREAS HACHURADAS POR LAYER" como 'confirmado',
            # e a anotação por linha mandava tratar como estimado. A instrução
            # específica ganhava da geral.
            #
            # EXPERIMENTO na prancha real (0326.CGR.14.600.PISO, prompt de
            # produção, Sonnet 4.6, temp 0,7, 3 rodadas de cada):
            #       m² MEDIDOS por rodada       confirmados (média)
            #   antes:  0,00 | 225,81 |   0,00        8,3
            #   depois: 225,81 | 225,81 | 229,04     13,3
            # Antes, 2 de 3 rodadas entregavam ZERO m² medido. Depois, mediu nas
            # três e no MESMO valor. E os 225,81 m² são a soma exata dos layers
            # de piso com padrão único — a IA descartou sozinha os dois mistos,
            # que somavam 4.931 m² de ruído. O total de itens não mudou (34,7 →
            # 34,3): não inflou nada, converteu estimativa em medição.
            _hatch_pat: dict[str, dict] = defaultdict(lambda: defaultdict(int))
            for _h in self.hatches:
                _hatch_pat[_h.layer][(getattr(_h, "pattern", "") or "SOLID")] += 1
            lines.append("ÁREAS HACHURADAS POR LAYER:")
            lines.append("  (o PADRÃO da hachura é o que separa acabamento no CAD: porcelanato e"
                         " cerâmica desenhados no MESMO layer têm padrões diferentes. Layer com UM"
                         " padrão só mede UM acabamento; layer com vários mistura acabamentos.)")
            _n_anot_ar = 0
            _em_vista: dict[str, float] = defaultdict(float)
            for _h in self.hatches:
                if getattr(_h, "na_vista", False):
                    _em_vista[_h.layer] += _h.area * getattr(_h, "peso", 1.0)
            for layer, area in sorted(areas_by_layer.items()):
                _pats = _hatch_pat.get(layer, {})
                _n = sum(_pats.values())
                if _em_vista.get(layer, 0) >= 0.01 and not _anot(layer):
                    # 🩸 25/09 (3ª releitura do job 53f0483f): a 1ª redação dizia
                    # "só vale como revestimento de parede" e a IA OBEDECEU —
                    # o concreto cortado de uma subestação virou "revestimento
                    # de parede 11,46 m²" branco.
                    lines.append(f"  {layer}: {area:.2f} m² — ⚠ {_em_vista[layer]:.2f} m² disto estão "
                                 f"DENTRO de corte/elevação: superfície vista DE LADO — NÃO é "
                                 f"piso, laje nem forro (esses se medem na planta). Só vira "
                                 f"quantidade se o projeto ESPECIFICA revestimento de parede "
                                 f"neste layer (azulejo, pastilha, painel); se não especifica "
                                 f"— instalações, estrutura, concreto cortado — IGNORE esta área")
                    continue
                # 🔑 Simetria com COMPRIMENTOS POR LAYER: hachura em layer de
                # anotação é preenchimento de legenda/carimbo, não superfície de
                # obra. O laço de HATCH não filtra layer — este rótulo é a única
                # coisa que diz isso pra IA.
                if _anot(layer):
                    _n_anot_ar += 1
                    lines.append(f"  {layer}: {area:.2f} m²   ⚠ ANOTAÇÃO DO DESENHO "
                                 f"(texto/cota/legenda) — área de preenchimento de "
                                 f"desenho, NÃO é superfície de obra: não use como "
                                 f"quantidade")
                    continue
                if len(_pats) > 1:
                    _top = ", ".join(f"{k} x{v}" for k, v in
                                     sorted(_pats.items(), key=lambda x: -x[1])[:4])
                    lines.append(f"  {layer}: {area:.2f} m² — {_n} hachuras em {len(_pats)} "
                                 f"padrões DIFERENTES ({_top}) — acabamento MISTO no mesmo "
                                 f"layer; trate como ESTIMADO, confira por ambiente")
                elif len(_pats) == 1:
                    _nome = next(iter(_pats))
                    lines.append(f"  {layer}: {area:.2f} m² — {_n} hachura(s), TODAS no padrão "
                                 f"'{_nome}' (acabamento ÚNICO: a soma mede um acabamento só)")
                else:
                    lines.append(f"  {layer}: {area:.2f} m²")
            lines.append("")

        # Áreas de polilinha fechada (ambiente/piso/forro) — m² medido da geometria
        poly_areas = self.get_polygon_areas_by_layer()
        if poly_areas:
            lines.append("ÁREAS DE CONTORNO FECHADO POR LAYER (polilinha fechada — ambiente/piso/forro):")
            lines.append("  (medido da geometria; pode incluir layer não-ambiente — use o nome do layer pra decidir; "
                         "NÃO some com ÁREAS HACHURADAS da MESMA região — é a mesma área medida de outro jeito)")
            _poly_vista: dict[str, float] = defaultdict(float)
            for _p in self.polygon_areas:
                if getattr(_p, "na_vista", False):
                    _poly_vista[_p.layer] += _p.area * getattr(_p, "peso", 1.0)
            for layer, area in sorted(poly_areas.items(), key=lambda x: -x[1]):
                if _poly_vista.get(layer, 0) >= 0.01:
                    lines.append(f"  {layer}: {area:.2f} m² — ⚠ {_poly_vista[layer]:.2f} m² disto "
                                 f"estão DENTRO de corte/elevação (vista DE LADO): NÃO é piso, "
                                 f"laje nem forro; se o projeto não especifica revestimento de "
                                 f"parede neste layer, IGNORE esta área")
                    continue
                lines.append(f"  {layer}: {area:.2f} m²")
            lines.append("")

        # 🔑 ATRIBUTOS DE BLOCO — o quadro que o projetista já preencheu.
        # Único "fazer-agora" que sobreviveu à pesquisa de 09-10/08 (24 propostas,
        # 10 descartadas por cético que rodou DXF real). Valor com NOME DE CAMPO,
        # escrito pelo autor do projeto — não é texto solto pra IA adivinhar.
        # 🪤 NÃO SOMAR ENTRE PRANCHAS: o mesmo quadro repete em várias folhas e o
        # valor às vezes DIVERGE (118,1 × 128,7 m² no CGR). Somar é o caso cliente-70.
        if getattr(self, "block_attributes", None):
            lines.append("QUADROS E ETIQUETAS DO PROJETISTA (atributos de bloco):")
            lines.append("  (o próprio autor do projeto escreveu estes valores com nome de campo."
                         " É a MELHOR fonte depois da geometria. ⚠ Vale só para ESTA prancha —"
                         " o mesmo quadro se repete em outras folhas e às vezes com valor"
                         " diferente; NUNCA some entre pranchas.)")
            _vistos_attr = set()
            for _ba in self.block_attributes[:40]:
                _linha = "; ".join(f"{k}={v}" for k, v in (_ba.get("campos") or {}).items())
                _chave = (_ba.get("bloco", ""), _linha)
                if _chave in _vistos_attr:
                    continue
                _vistos_attr.add(_chave)
                lines.append(f"  [{_ba.get('bloco','?')}] {_linha[:150]}")
            if len(self.block_attributes) > 40:
                lines.append(f"  (+{len(self.block_attributes) - 40} bloco(s) com atributo não listado(s))")
            lines.append("")

        # 🔑 O RÓTULO DE CADA REGIÃO — o elo que faltava (09/08/2026).
        # O prompt já trazia "o texto X existe" e "a região Y tem N m²" em listas
        # SEPARADAS, e a IA tinha que adivinhar qual texto fala de qual região.
        # Aqui vem o par pronto, calculado na geometria: qual rótulo cai DENTRO
        # de cada contorno fechado. É o que ataca a linha zerada — 31,7% das
        # linhas saíam sem quantidade, e 514 delas já citavam a camada.
        try:
            from engine_rules import casar_texto_com_regiao as _casar
            # Hachura JUNTO com contorno fechado: medi em 09/08 que polilinha
            # fechada quase não existe nos projetos reais, e a hachura é a fonte
            # mais comum das medições que funcionam.
            # 🪤 Não duplica: cada região aceita 1 rótulo e cada rótulo casa com
            # UMA região (a menor que o contém) — se a mesma área existe como
            # hachura E como contorno, o texto vai pra uma só.
            _pares = _casar(self.texts, list(self.polygon_areas) + list(self.hatches))
        except Exception:
            _pares = []
        if _pares:
            lines.append("RÓTULO ↔ ÁREA DA REGIÃO (casado na geometria, não é chute):")
            lines.append("  (o texto está DENTRO do contorno fechado, então quase sempre fala DELE."
                         " Use como a quantidade daquele ambiente. ⚠ Continua ESTIMADO: estar dentro"
                         " é indício forte, não prova — e um rótulo solto pode cair em cima de outra"
                         " coisa.)")
            for p in _pares[:60]:
                lines.append(f"  \"{p['texto']}\"  →  {p['area']:.2f} m²"
                             f"  ({p.get('origem', 'região')} no layer {p['layer_da_regiao']})")
            if len(_pares) > 60:
                lines.append(f"  (+{len(_pares) - 60} par(es) não listado(s))")
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
        _cl = (self.folhas or {}).get("legenda_contagem") or []
        if _cl:
            lines.append("CONTAGEM PELO SÍMBOLO DA LEGENDA (a tabela SÍMBOLO | DESCRIÇÃO da prancha")
            lines.append("  deixou a quantidade em branco; o motor contou na PLANTA o MESMO desenho")
            lines.append("  do símbolo, no mesmo tamanho. É contagem do desenho: use ESTE número na")
            lines.append("  linha dessa descrição. Linha da legenda que não está aqui NÃO foi contada")
            lines.append("  — o símbolo na planta é diferente do da tabela; não invente):")
            for _r in _cl:
                _pp = "; ".join("%s: %d" % (k, v) for k, v in _r["por_planta"].items())
                lines.append(f"  {_r['descricao']} = {_r['n']}  ({_pp})")
            lines.append("")
        # 25/09: SIGLA → NOME pela legenda da própria prancha (ver
        # `siglas_da_legenda`) — antes a IA adivinhava e trocava TH/CH/CZ
        _sig = siglas_da_legenda(self.texts)
        if _sig:
            lines.append("SIGLAS DA LEGENDA DESTA PRANCHA (o projetista escreveu o nome de cada")
            lines.append("  sigla — use ESTE nome na descrição do item; não traduza a sigla por conta):")
            for _k, _v in _sig.items():
                lines.append(f"  {_k} = {_v}")
            lines.append("")
        texts_by_layer = self.get_texts_by_layer()
        # 25/09: texto só de corte/detalhe sai do ×N (ver
        # `_marcar_textos_repetidos_da_planta`) e vem listado à parte, no fim
        _txt_vista: dict[str, list] = defaultdict(list)
        if any(getattr(_t, "fora_da_contagem", False) for _t in self.texts):
            texts_by_layer = defaultdict(list)
            for _t in self.texts:
                (_txt_vista if getattr(_t, "fora_da_contagem", False)
                 else texts_by_layer)[_t.layer].append(_t.text)
            texts_by_layer = dict(texts_by_layer)
        if texts_by_layer or _txt_vista:
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
            if _txt_vista:
                lines.append("  TEXTOS QUE ESTÃO SÓ EM CORTE/ELEVAÇÃO/DETALHE (a MESMA peça da planta")
                lines.append("   vista de novo — servem de ESPECIFICAÇÃO; NÃO conte nem some com a")
                lines.append("   planta; por isso vêm sem ×N):")
                _ja = {}
                for _t in self.texts:
                    if getattr(_t, "ja_contada_em", ""):
                        _ja.setdefault(_t.ja_contada_em, set()).add(" ".join(_t.text.split()))
                for _pr, _ts in sorted(_ja.items()):
                    lines.append(f"  ⚠ JÁ CONTADAS NA PLANTA da prancha {_pr[:60]} — NÃO conte de novo "
                                 f"aqui: " + "; ".join(sorted(_ts)[:20]))
                for layer, _ts in sorted(_txt_vista.items()):
                    _uniq = sorted({x.strip() for x in _ts if len(x.strip()) > 1})
                    if not _uniq:
                        continue
                    lines.append(f"  [{layer}]: " + "; ".join(_uniq[:30])
                                 + (f" (+{len(_uniq) - 30})" if len(_uniq) > 30 else ""))
            lines.append("")

        # Dimensions
        if self.dimensions:
            # 🔑 COTA REPETIDA VIRA ×N (10/08/2026). Medido nos DXF reais: a
            # seção de cotas é 53% do prompt na CGR PISO e 44% no DET FORRO — e
            # a repetição é 38% e **76%** (74 cotas distintas de 300). A IA
            # gastava metade do que lê relendo a mesma cota em vez de olhar o
            # resto do desenho.
            # 🪤 NÃO some nem encadeia: verifiquei a proposta de "cadeia de
            # cotas" da pesquisa e ela NÃO se sustenta — as cadeias saem com 2 a
            # 4 parcelas e a maior cobre 4% da largura do desenho. Aqui é só
            # deduplicação literal, que não inventa nada.
            # 🪤 O ×N é informação, não ruído: 8 portas iguais cotadas 8 vezes é
            # contagem, mesma lógica do `contar_textos_repetidos`.
            _cot = {}
            for label, value in self.dimensions:
                _k = f"  {label}: {value}"
                _cot[_k] = _cot.get(_k, 0) + 1
            lines.append("COTAS/DIMENSÕES:")
            if any(n > 1 for n in _cot.values()):
                lines.append("  (×N = a MESMA cota aparece N vezes na prancha —"
                             " para item contável, é evidência de quantidade)")
            for _k, _n in _cot.items():
                lines.append(_k + (f"   ×{_n}" if _n > 1 else ""))

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
# 25/09: leito de cabos, eletrocalha e bandeja são desenhados do mesmo jeito
# (as duas bordas). "eletroduto" continua de fora: é linha ÚNICA.
_RE_DUTO_DUPLO = re.compile(
    r"(?<![a-z])(?:duto|ducto|leito|eletrocalha|bandeja)", re.IGNORECASE)

_DUTO_ANG_TOL = 3.0      # graus: paralelas de verdade
_DUTO_SEP_MIN = 0.05     # m: abaixo disso é a mesma linha repetida, não um par
_DUTO_SEP_MAX = 1.50     # m: acima disso não é seção de duto, são redes distintas
_DUTO_MIN_SEG = 0.25     # m: trecho menor é legenda/símbolo, não rede
_DUTO_MAX_SEG_LAYER = 3000   # teto anti-O(n²) por layer


_RE_LEGENDA_LINHA_DUPLA = re.compile(
    r"\b(?:leitos?|eletrocalhas?|bandejas?|calhas?|dutos?|ductos?)\b")


def _legenda_de_linha_dupla(msp) -> dict:
    """{layer: [descrição]} do que a LEGENDA diz ser leito/duto em DUAS linhas.

    🩸 25/09/2026, job 53f0483f (subestação): o leito de cabos estava no layer
    "K-04" — código do cliente, sem a palavra "leito". A IA escolheu o leito
    pelo "layer de maior extensão" (palpite, em linha branca) e o comprimento
    saiu com as DUAS bordas somadas. A SIMBOLOGIA da folha dizia tudo: ao lado
    de "- LEITO PARA CABOS", duas linhas paralelas no layer K-04.

    Linha de legenda = texto com a palavra (leito, eletrocalha, bandeja, calha,
    duto), numa COLUNA de pelo menos 3 textos alinhados à esquerda, cada um
    com amostra desenhada à esquerda — é o que distingue legenda de anotação
    solta na planta (medido: "eletrocalha h=3,22m" solto no forro não conta).
    Amostra de linha dupla = 2 segmentos quase horizontais do MESMO layer,
    sobrepostos, afastados de 0,15 a 3 alturas de letra. Na dúvida, {}.
    """
    try:
        textos = []
        for e in msp.query("TEXT MTEXT"):
            try:
                p = e.dxf.insert
                h = float((e.dxf.get("height", 0) if e.dxftype() == "TEXT"
                           else e.dxf.get("char_height", 0)) or 0)
                t = _texto_do_text(e) if e.dxftype() == "TEXT" else e.plain_text()
                t = " ".join((t or "").split())
                if t and h > 0 and len(t) <= 70:
                    textos.append((t, float(p[0]), float(p[1]), h))
            except Exception:
                continue
        from engine_rules import _minusculo_sem_acento, layer_is_anotacao
        # 🔑 A palavra na CABEÇA: "- LEITO PARA CABOS" é o leito;
        # "DIÂMETRO DO DUTO/LARGURA" (a explicação da etiqueta) não é duto.
        chaves = [x for x in textos
                  if _RE_LEGENDA_LINHA_DUPLA.match(_minusculo_sem_acento(x[0]).lstrip("-–—•* ").strip())]
        if not chaves:
            return {}

        def faixa(x, y, h):
            return (x - 60 * h, y - 1.2 * h, x + 0.5 * h, y + 2.2 * h)

        # colunas: vizinhos alinhados à esquerda, mesma letra, perto em y
        linhas = []                     # (texto_chave, [faixas da coluna], faixa_da_chave)
        for t, x, y, h in chaves:
            # 10 alturas: a 1ª linha só tem vizinhas embaixo (na SIMBOLOGIA do
            # caso, a 2ª abaixo do leito estava a 8,01 alturas)
            viz = [v for v in textos if v[0] != t and abs(v[1] - x) <= h
                   and abs(v[2] - y) <= 10 * h and 0.7 * h <= v[3] <= 1.4 * h]
            if len(viz) >= 2:
                linhas.append((t, [faixa(v[1], v[2], v[3]) for v in viz], faixa(x, y, h), h))
        if not linhas:
            return {}
        caixas = [f for _, fs, fk, _ in linhas for f in fs + [fk]]
        gx0 = min(c[0] for c in caixas)
        gy0 = min(c[1] for c in caixas)
        gx1 = max(c[2] for c in caixas)
        gy1 = max(c[3] for c in caixas)
        segs, inserts = [], []
        for e in msp.query("LINE LWPOLYLINE INSERT"):
            try:
                tp = e.dxftype()
                if tp == "INSERT":
                    p = e.dxf.insert
                    if gx0 <= p[0] <= gx1 and gy0 <= p[1] <= gy1:
                        inserts.append((float(p[0]), float(p[1])))
                    continue
                if tp == "LINE":
                    pts = [(e.dxf.start[0], e.dxf.start[1]), (e.dxf.end[0], e.dxf.end[1])]
                else:
                    pts = [(q[0], q[1]) for q in e.get_points("xy")]
                for a, b in zip(pts, pts[1:]):
                    if (gx0 <= min(a[0], b[0]) and max(a[0], b[0]) <= gx1
                            and gy0 <= min(a[1], b[1]) and max(a[1], b[1]) <= gy1):
                        segs.append((e.dxf.layer, (float(a[0]), float(a[1])), (float(b[0]), float(b[1]))))
            except Exception:
                continue

        def dentro(seg, f):
            _, a, b = seg
            return (f[0] <= min(a[0], b[0]) and max(a[0], b[0]) <= f[2]
                    and f[1] <= min(a[1], b[1]) and max(a[1], b[1]) <= f[3])

        def tem_amostra(f):
            return (any(dentro(sg, f) for sg in segs)
                    or any(f[0] <= p[0] <= f[2] and f[1] <= p[1] <= f[3] for p in inserts))

        out = {}
        for t, fs, fk, h in linhas:
            if sum(1 for f in fs if tem_amostra(f)) < 2:
                continue                                # não é coluna de legenda
            horiz = [sg for sg in segs if dentro(sg, fk)
                     and abs(sg[2][1] - sg[1][1]) <= 0.05 * abs(sg[2][0] - sg[1][0])
                     and abs(sg[2][0] - sg[1][0]) >= 2 * h]
            por_layer = {}
            for sg in horiz:
                por_layer.setdefault(sg[0], []).append(sg)
            for lay, ss in por_layer.items():
                if layer_is_anotacao(lay):
                    continue                    # chamada/cota/texto não é o objeto
                achou = False
                for i, a in enumerate(ss):
                    for b in ss[i + 1:]:
                        dy = abs((a[1][1] + a[2][1]) / 2 - (b[1][1] + b[2][1]) / 2)
                        ax0, ax1 = sorted((a[1][0], a[2][0]))
                        bx0, bx1 = sorted((b[1][0], b[2][0]))
                        sob = min(ax1, bx1) - max(ax0, bx0)
                        if 0.15 * h <= dy <= 3 * h and sob >= 0.5 * min(ax1 - ax0, bx1 - bx0):
                            achou = True
                            break
                    if achou:
                        break
                if achou:
                    desc = t.lstrip("-–— ").strip().rstrip(".")
                    out.setdefault(lay, [])
                    if desc not in out[lay]:
                        out[lay].append(desc)
        return out
    except Exception as e:                       # nunca derruba a extração
        logger.warning("_legenda_de_linha_dupla: %s", e)
        return {}


def _corrigir_duto_linha_dupla(walls, unit_factor: float = 1.0, layers_extra=None):
    """Troca a soma das duas faces pelo comprimento do EIXO, em layer de duto.

    `layers_extra`: layers que a LEGENDA da prancha diz serem leito/duto
    desenhado em duas linhas (ver `_legenda_de_linha_dupla`) — o nome do layer
    não precisa dizer.

    Devolve (walls_corrigidos, relato_eixo, ressalva_hachura).
    Sem par encontrado, devolve a lista original — na dúvida, não mexe.

    🪤 As coordenadas de `start`/`end` são CRUAS (unidade do desenho), mas
    `length` já vem em METRO (bruto × unit_factor). Misturar as duas escalas na
    mesma conta foi o defeito da 1ª versão: a separação entre as faces saía
    dividida pelo fator ao quadrado, então em desenho de milímetro dava 600.000
    e NADA pareava. O conserto era inerte em quase todo DXF real — funcionou no
    arquivo de 04/08 só porque aquele estava em metro. Agora toda a geometria é
    feita em unidade bruta e só o resultado vira metro.

    🩸 25/09/2026 (job 53f0483f, leito de subestação): a 2ª versão pareava
    SEGMENTO INTEIRO com segmento inteiro e exigia comprimentos parecidos. No
    desenho real uma borda corre inteira (9 m) e a do outro lado vem quebrada
    em cada caixa de passagem (4,65 + 4,65): nada casava, e 207 m de bordas
    viravam 147 m em vez de ~100. Agora é por TRECHO: ao longo da direção,
    em cada pedaço, as linhas presentes são ordenadas pela distância lateral e
    pareadas vizinha com vizinha (duas bordas de um leito; o do lado forma o
    próprio par). Cada linha pareada num pedaço conta MEIO metro por metro.
    Continua valendo: mesma direção, separação de seção, e o par só existe se
    as duas linhas se sobrepõem em pelo menos metade da menor.
    """
    if not walls:
        return walls, "", ""
    try:
        import copy as _copy
        import dataclasses as _dcs
        from collections import defaultdict as _dd
        uf = float(unit_factor) if unit_factor else 1.0
        extra = set(layers_extra or ())
        por_layer = _dd(list)
        for i, w in enumerate(walls):
            lay = str(getattr(w, "layer", "") or "")
            if lay in extra or _RE_DUTO_DUPLO.search(lay):
                por_layer[w.layer].append(i)
        if not por_layer:
            return walls, "", ""

        sep_min, sep_max = _DUTO_SEP_MIN / uf, _DUTO_SEP_MAX / uf    # em bruto
        fator = {}                     # índice -> fração do comprimento que fica
        relato, ressalva = [], []
        pareados_no_layer = set()
        for layer, idxs in por_layer.items():
            # 🪤 Só pareia segmento com geometria de verdade. O caminho que mede
            # dentro de bloco grava start/end zerados — pareá-los casaria tudo
            # com tudo e destruiria a medição. ARCO fica fora (a corda não é a
            # curva) — ver a ressalva abaixo.
            # 🩸 25/09: POLILINHA vira os seus lados. Antes ia inteira como uma
            # reta do 1º ao último vértice — a caixa de passagem em "U" de
            # 4,65 m virava "uma reta de 1,44 m" e o retângulo fechado (início
            # = fim) nem entrava.
            sub = []                    # (índice do pai, a, b) — cru
            for i in idxs:
                w = walls[i]
                if getattr(w, "curvo", False) or getattr(w, "length", 0) < _DUTO_MIN_SEG:
                    continue
                pts = getattr(w, "pontos", ()) or ()
                if len(pts) >= 2:
                    for p, q in zip(pts, pts[1:]):
                        if len(p) > 2 and p[2]:
                            continue            # lado em arco: fora (ressalva)
                        if (p[0], p[1]) != (q[0], q[1]) and math.hypot(q[0] - p[0], q[1] - p[1]) * uf >= _DUTO_MIN_SEG:
                            sub.append((i, (p[0], p[1]), (q[0], q[1])))
                elif tuple(w.start) != tuple(w.end):
                    sub.append((i, tuple(w.start), tuple(w.end)))
            if len(sub) < 2 or len(sub) > _DUTO_MAX_SEG_LAYER:
                continue
            bruto = sum(walls[i].length for i in {s_[0] for s_ in sub})
            uteis = list(range(len(sub)))
            seg_a = {k: sub[k][1] for k in uteis}
            seg_b = {k: sub[k][2] for k in uteis}
            # direção (0–180°) de cada segmento; grupos de paralelas
            ang = {}
            for i in uteis:
                (ax, ay), (bx, by) = seg_a[i], seg_b[i]
                ang[i] = math.degrees(math.atan2(by - ay, bx - ax)) % 180.0
            ordem = sorted(uteis, key=lambda i: ang[i])
            grupos, atual = [], [ordem[0]]
            for i in ordem[1:]:
                if ang[i] - ang[atual[-1]] <= _DUTO_ANG_TOL:
                    atual.append(i)
                else:
                    grupos.append(atual)
                    atual = [i]
            grupos.append(atual)
            # quase 180° é a mesma direção que quase 0°
            if len(grupos) > 1 and ang[grupos[0][0]] + 180.0 - ang[grupos[-1][-1]] <= _DUTO_ANG_TOL:
                grupos[0] = grupos.pop() + grupos[0]
            pares = set()
            pareado = _dd(float)        # índice -> comprimento BRUTO pareado
            for g in grupos:
                if len(g) < 2:
                    continue
                th = math.radians(ang[g[0]])
                ux, uy = math.cos(th), math.sin(th)
                nx, ny = -uy, ux
                d, t0, t1 = {}, {}, {}
                for i in g:
                    (ax, ay), (bx, by) = seg_a[i], seg_b[i]
                    d[i] = (ax * nx + ay * ny + bx * nx + by * ny) / 2.0
                    sa, sb = ax * ux + ay * uy, bx * ux + by * uy
                    t0[i], t1[i] = min(sa, sb), max(sa, sb)
                # quem pode ser par de quem: separação de seção + sobreposição
                # de pelo menos metade da menor (trecho que nem se olha não é par)
                por_d = sorted(g, key=lambda i: d[i])
                viz = _dd(set)
                for a_pos, a in enumerate(por_d):
                    for b in por_d[a_pos + 1:]:
                        sep = d[b] - d[a]
                        if sep >= sep_max:
                            break
                        if sep <= sep_min:
                            continue
                        sobrep = min(t1[a], t1[b]) - max(t0[a], t0[b])
                        if sobrep >= 0.5 * min(t1[a] - t0[a], t1[b] - t0[b]) and sobrep > 0:
                            viz[a].add(b)
                            viz[b].add(a)
                if not viz:
                    continue
                cand = list(viz)
                cortes = sorted({t for i in cand for t in (t0[i], t1[i])})
                for ta, tb in zip(cortes, cortes[1:]):
                    if tb - ta <= 0:
                        continue
                    tm = (ta + tb) / 2.0
                    ativos = sorted((i for i in cand if t0[i] <= tm <= t1[i]), key=lambda i: d[i])
                    k = 0
                    while k + 1 < len(ativos):
                        a, b = ativos[k], ativos[k + 1]
                        if b in viz[a]:
                            pareado[a] += tb - ta
                            pareado[b] += tb - ta
                            pares.add((min(a, b), max(a, b)))
                            k += 2
                        else:
                            k += 1
            if not pares:
                continue
            # TAMPA: lado curto sem par (até a largura de uma seção) com as
            # DUAS pontas em cima de bordas pareadas — é o fecho do retângulo
            # ou a divisa entre dois trechos, não metro de leito.
            # 🪤 Limite conhecido (25/09, medido na planta do caso): lateral de
            # caixa de passagem e chanfro NÃO são pegos (a ponta encosta em
            # outra peça sem par) — ~30 dos 130 m daquela planta. Tentei "não
            # corre na direção de nenhum trecho pareado": piorou (subida e
            # conectores verticais também pareiam, e a tampa vertical voltou).
            tol = 0.02 / uf

            def _sobre(pt, k):
                (ax, ay), (bx, by) = seg_a[k], seg_b[k]
                vx, vy = bx - ax, by - ay
                L2 = vx * vx + vy * vy
                if L2 <= 0:
                    return False
                f = max(0.0, min(1.0, ((pt[0] - ax) * vx + (pt[1] - ay) * vy) / L2))
                return math.hypot(ax + f * vx - pt[0], ay + f * vy - pt[1]) <= tol
            com_par = [k for k in uteis if pareado.get(k)]
            tampa = {}
            for k in uteis:
                if pareado.get(k):
                    continue
                (ax, ay), (bx, by) = seg_a[k], seg_b[k]
                L = math.hypot(bx - ax, by - ay)
                if L >= sep_max:
                    continue
                if (any(_sobre(seg_a[k], j) for j in com_par)
                        and any(_sobre(seg_b[k], j) for j in com_par)):
                    tampa[k] = L
            # quanto sai de cada linha do desenho (em metro)
            tira = _dd(float)
            for k, p in pareado.items():
                (ax, ay), (bx, by) = seg_a[k], seg_b[k]
                L = math.hypot(bx - ax, by - ay)
                tira[sub[k][0]] += 0.5 * min(p, L) * uf
            for k, L in tampa.items():
                tira[sub[k][0]] += L * uf
            for i, t in tira.items():
                if walls[i].length > 0:
                    fator[i] = max(0.0, 1.0 - t / walls[i].length)
            eixo = bruto - sum(tira.values())
            pareados_no_layer.add(layer)
            relato.append(f"{layer}: {bruto:.1f}m de face -> {eixo:.1f}m de eixo "
                          f"({len(pares)} par(es))")

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
            if layer not in pareados_no_layer:
                continue
            arcos = sum(walls[i].length for i in idxs
                        if getattr(walls[i], "curvo", False))
            if arcos > 0:
                ressalva.append(
                    f"{layer}: {arcos:.1f}m em curva (ARC) ficaram FORA do "
                    f"pareamento — nessas o duto ainda conta as duas faces")

        rel_eixo = " | ".join(relato)
        rel_ressalva = " | ".join(ressalva)
        if not fator:
            return walls, rel_eixo, rel_ressalva

        def _encurta(w, f):
            try:
                return _dcs.replace(w, length=w.length * f)
            except TypeError:                      # não é dataclass (dublê)
                n = _copy.copy(w)
                n.length = w.length * f
                return n
        novos = [(_encurta(w, fator[i]) if i in fator else w) for i, w in enumerate(walls)]
        logger.warning("[duto-linha-dupla] %s %s", rel_eixo, rel_ressalva)
        return novos, rel_eixo, rel_ressalva
    except Exception as e:
        logger.warning("[duto-linha-dupla] falhou, mantendo medição original: %s", e)
        return walls, "", ""


_RE_RELATO_EIXO = re.compile(r"^(.*): [\d.]+m de face -> [\d.]+m de eixo \(\d+ par\(es\)\)$")


def _relato_do_eixo_na_soma(relato: str, walls) -> str:
    """Reescreve o relato do eixo com o que FICOU na soma (depois da folha).

    Sem número de antes: número que não está na soma vira quantidade na mão
    da IA. Trecho que não casa o formato fica como veio."""
    try:
        novos = []
        for trecho in (relato or "").split(" | "):
            m = _RE_RELATO_EIXO.match(trecho.strip())
            if not m:
                novos.append(trecho)
                continue
            lay = m.group(1)
            atual = sum(w.length * getattr(w, "peso", 1.0) for w in walls if w.layer == lay)
            if atual < 0.05:
                novos.append(f"{lay}: desenhado em 2 linhas, mas todo o traçado desta prancha "
                             f"está em corte/detalhe/planta-chave — NADA deste layer entra "
                             f"na soma desta prancha")
            else:
                novos.append(f"{lay}: {atual:.1f}m na soma, JÁ pelo EIXO (as 2 bordas contadas "
                             f"uma vez; corte e detalhe já fora)")
        return " | ".join(novos)
    except Exception as e:                       # nunca derruba a extração
        logger.warning("_relato_do_eixo_na_soma: %s", e)
        return relato


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

    # Fallback: $MEASUREMENT=0 ("imperial") → pés, MAS só com corroboração.
    # 🚨 21/08/2026: $MEASUREMENT=0 é o que o template imperial padrão do
    # AutoCAD (acad.dwt) grava. Projetista brasileiro que parte desse template
    # entrega um DWG "imperial" desenhado em metros. Em 20/08 os DOIS clientes
    # reais do dia caíram aqui; a prancha de fôrma do cliente-17 (42 × 35 unidades,
    # DIMLFAC=100 — assinatura de metro com cota em cm) virou 12,8 × 10,7 m:
    # erro de 3,28× em TODO comprimento. E pés é o único palpite que NENHUMA
    # régua conserta: a das cotas abstém de fator não-métrico por desenho, e a
    # do DIMLFAC só troca no degrau de 1000×. Um palpite métrico errado ainda
    # tem 4 réguas atrás dele; o de pés não tem nenhuma.
    # O que distingue imperial de verdade é o FORMATO das cotas: $LUNITS /
    # $DIMLUNIT 3 (engineering, 1'-2.5") ou 4 (architectural, 1'-2 1/2").
    # Sem isso, $MEASUREMENT=0 é ruído de template e o fluxo segue pra
    # inferência por extensão (e, na dúvida, mm — o comportamento métrico).
    try:
        measurement = doc.header.get("$MEASUREMENT", 1)
        if measurement == 0:
            _fmt = set()
            for _k in ("$LUNITS", "$DIMLUNIT"):
                try:
                    _fmt.add(int(doc.header.get(_k, 2) or 2))
                except Exception:
                    pass
            if _fmt & {3, 4}:
                return 0.3048          # formato pés-polegadas: imperial de verdade
            logger.warning(
                "[unit-pes] $MEASUREMENT=0 sem formato imperial (LUNITS/DIMLUNIT=%s) "
                "— tratado como ruído de template, NÃO assume pés", sorted(_fmt))
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


def _diag_unidade_cabecalho(doc) -> dict:
    """SOMBRA da unidade (21/08/2026) — só leitura, nada muda pro cliente.

    Por que existe: `_detect_unit_factor` assume PÉS quando $INSUNITS=0 e
    $MEASUREMENT=0. Mas $MEASUREMENT=0 é o que o template imperial padrão do
    AutoCAD (acad.dwt) grava — um projetista brasileiro que começa do template
    errado entrega um DWG "imperial" desenhado em metros. Em 20/08/2026 os DOIS
    clientes reais do dia (galpão de 800 m²; fôrma do 1º pavimento de outro)
    caíram nessa regra, e a régua das cotas NÃO consegue corrigir fator
    não-métrico (abstém de propósito). Antes de trocar a regra — função que
    multiplica TODO número de TODO projeto — precisamos de N: o que o cabeçalho
    diz ($LUNITS/$DIMLUNIT 3-4 = formato imperial de verdade) e qual fator a
    cadeia daria sem a regra dos pés. Este dict vai pro log motor:unidade.
    """
    d: dict = {}
    try:
        h = doc.header
        for k in ("$INSUNITS", "$MEASUREMENT", "$LUNITS", "$DIMLUNIT", "$DIMLFAC"):
            try:
                v = h.get(k, None)
                if v is not None:
                    d[k.lstrip("$").lower()] = v
            except Exception:
                pass
        try:
            emin = h.get("$EXTMIN")
            emax = h.get("$EXTMAX")
            if emin and emax:
                d["ext"] = (round(abs(emax[0] - emin[0]), 1),
                            round(abs(emax[1] - emin[1]), 1))
        except Exception:
            pass
        try:
            if (int(d.get("insunits", 0) or 0) == 0
                    and int(d.get("measurement", 1) or 0) == 0):
                inf = _inferir_unidade_sem_insunits(doc)
                d["sem_regra_pes"] = inf if inf is not None else 0.001
        except Exception:
            pass
    except Exception:
        pass
    return d


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
# 🚨 COMENTÁRIO ENTRE PARÊNTESES depois do número é comum e NÃO invalida a
# cota (17/08/2026, caso cliente-81): o arquivo dele tem "11.70 (RGI)" e
# "35.70 (RGI)" — o projetista anota a fonte da medida. O `$` no fim exigia
# que o texto ACABASSE no número, então TODAS essas cotas eram descartadas,
# a régua da prancha não rodava, e o cabeçalho mentiroso ($INSUNITS=4, mm,
# num desenho em METRO) passava batido: 143 hachuras somaram 0,0019 m² e o
# cliente recebeu alvenaria/revestimento zerados.
# 🪤 O parêntese só é tolerado DEPOIS do número. "VER DETALHE", "VAR." e
# qualquer palavra ANTES continuam invalidando — a cota tem que começar com
# a medida pra servir de régua.
_DIM_TEXT_NUM_RE = re.compile(
    r"^\s*[~≈±]?\s*(\d+(?:[.,]\d+)?)\s*(mm|cm|m)?\s*\.?\s*(?:\([^)]*\))?\s*$",
    re.IGNORECASE)
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
# Caso cliente-82 (05/08/2026): DXF declara $INSUNITS=4 (mm) e está em METRO.
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
# um erro de 1000× vale muito mais. O caso cliente-82 é DIMLFAC=100.
_LFAC_PARA_FATOR = {
    100.0: 1.0,      # cota em cm, desenho em m   ← caso cliente-82
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
    out: dict = {"status": None, "cotas_utilizaveis": 0, "motivo": "nao-avaliada"}
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
        out["cotas_digitadas"] = n_digitadas
        if usable < _DIM_MIN_COTAS:
            # 🔍 26/08/2026 — o log gravava só `cotas=-`, e esse traço juntava
            # CINCO desfechos diferentes: desenho sem cota, cota de menos, cota
            # que não fecha, empate entre fatores e correção recusada por
            # absurdo. Medido no acervo: 27 pranchas de 21 projetos têm 8.370
            # cotas que o motor leu e não usou — e não dava pra saber por quê.
            out["motivo"] = ("nenhuma cota linear utilizável no desenho"
                             if not evidence else
                             "%d cota(s) lida(s), %d utilizável(is) — mínimo %d"
                             % (len(evidence), usable, _DIM_MIN_COTAS))
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
                return out
            # ⚠ MAIS DE UM FATOR QUALIFICOU. Antes isto encerrava em "ambigua" e
            # a prancha inteira saía "sem prova de escala" pro cliente.
            #
            # 🔍 26/08/2026: medido que o empate costuma ser FALSO. A faixa de
            # plausibilidade da MEDIANA vai até 100 m — larga o bastante pra um
            # desenho em centímetro também "qualificar" como METRO:
            #   0326.CGR.14.600.PISO (376 cotas, $INSUNITS=cm)
            #      fator 1,0  → mediana 100,00 m | 218 de 311 cotas > 30 m (70,1%)
            #      fator 0,01 → mediana   1,48 m |   4 de 369 cotas > 30 m ( 1,1%)
            #   0326.CGR.14.700.FORRO (16 cotas)
            #      fator 1,0  → mediana  82,24 m | 75,0% das cotas > 30 m
            #      fator 0,01 → mediana   0,82 m |  0,0%
            # Prancha cuja cota MEDIANA tem 100 m não existe em edificação.
            #
            # O desempate usa `correcao_e_absurda` — o MESMO guarda que já
            # governa o ramo "corrigida" desde 05/08. Não é critério novo: é o
            # critério existente aplicado de forma consistente.
            #
            # 🚨 DUAS TRAVAS pra isto nunca ser promoção por suposição (regra nº1):
            #   1. só roda no EMPATE (len(proven) > 1). Prancha com candidato
            #      único não é tocada — nada que valida hoje passa a falhar.
            #   2. só CONFIRMA o fator já DETECTADO. Nunca corrige, nunca troca
            #      unidade, nunca muda uma quantidade.
            # 🪤 Controle positivo medido: AFP-AQ-LO-229 (metro de verdade, 3
            # cotas, mediana 1,18 m) tem 0,0% de cotas acima de 30 m — o guarda
            # NÃO mata o metro legítimo.
            # 🪤 E o nível de prova não baixou: "validada" JÁ sai hoje com cota
            # de texto automático (o AFP tem 0 cotas digitadas e valida). O que
            # esta trecho corrige é a prancha com 376 cotas ser tratada PIOR que
            # a de 3, só porque um fator fisicamente impossível também passou.
            fisicos = [f for f in proven if not correcao_e_absurda(support[f])]
            if len(fisicos) == 1 and fisicos[0] == detected:
                caidos = ", ".join("%g" % f for f in proven if f not in fisicos)
                out.update({
                    "status": "validada",
                    "fator": detected,
                    "n_cotas": len(support[detected]),
                    "unidade_nome": _UNIT_FACTOR_NAMES[detected],
                    "desempatada_por_fisica": (
                        "%d fatores qualificaram; %s caiu(ram) por cota implausível "
                        "(acima de %g m em mais de %.0f%% das cotas)"
                        % (len(proven), caidos, _DIM_ABSURDO_M,
                           _DIM_ABSURDO_FRACAO * 100)),
                })
                logger.info("[unit-cotas] empate desfeito por física: %s",
                            out["desempatada_por_fisica"])
                return out
            # Empate REAL — nenhum sobrou, sobrou mais de um, ou o que sobrou não
            # é o detectado. A prova não é exclusiva: fica calada, mas DIZENDO.
            out["status"] = "ambigua"
            out["motivo"] = ("empate entre os fatores %s (%d cotas utilizáveis, "
                             "%d com número digitado)"
                             % (", ".join("%g" % f for f in proven), usable,
                                n_digitadas))
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
        # 🔍 27/08/2026 — A SEXTA SAÍDA, QUE O CONSERTO DE ONTEM DEIXOU PASSAR.
        # Ontem o `cotas=-` juntava cinco desfechos e ganhou motivo em cada um.
        # Sobrou ESTA: cair fora do `if` acima devolve `out` com o motivo
        # INICIAL, "nao-avaliada" — e aí o log afirma que a régua não rodou,
        # quando ela rodou e não achou prova.
        # 🪤 Visto no job `evaa4391` (avaliação do cliente-71, prancha estrutural):
        #     regua=nao-decidiu utilizaveis=1104 porque=nao-avaliada
        # Mil e cento e quatro cotas lidas, e o log dizendo "não avaliada".
        # É a mesma família do instrumento que mente — só que agora era o MEU.
        if out.get("motivo") == "nao-avaliada":
            out["motivo"] = (
                "avaliada e sem prova exclusiva: %d cota(s) utilizável(is), "
                "%d com número digitado, %d fator(es) qualificaram%s"
                % (usable, n_digitadas, len(proven),
                   (" (" + ", ".join("%g" % f for f in proven) + ")")
                   if proven else " — nenhum"))
        return out
    except Exception as exc:  # defensivo: a régua NUNCA derruba a extração
        logger.warning("[unit-cotas] validação por cotas falhou (ignorada): %s", exc)
        # 🪤 Sem `motivo`, o log cai no traço e a falha vira indistinguível de
        # "não tinha cota". A régua não pode derrubar a extração — mas também
        # não pode sumir sem dizer que quebrou.
        return {"status": None, "cotas_utilizaveis": 0,
                "motivo": "a régua falhou e foi ignorada: %s: %s"
                          % (type(exc).__name__, str(exc)[:80])}


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


#: Texto do `.dxf.err` por arquivo — o que o ODA de fato disse, numa linha.
#: 🩸 14/09/2026: medido em 45 dias, 49 de 60 jobs com DWG caíram no libredwg
#: e o log só dizia "(ODA recusou)". Com isso não dá pra saber se é versão do
#: CAD, objeto AEC ou arquivo quebrado — ou seja, não dá pra decidir se vale
#: consertar. O motivo existia: morria no tempdir que o Render apaga.
_FALHA_DETALHE: dict = {}


def _chave_da_falha(dwg_path) -> str:
    """Chave dos mapas de falha: o CAMINHO COMPLETO, nunca o nome do arquivo.

    🚨 18/09/2026, revisão adversarial da 2ª vaga. Estes mapas eram indexados por
    `os.path.basename`, e isso só era seguro enquanto UM projeto processava por
    vez. Com dois no ar, dois clientes dividem a mesma entrada — e "PRANCHA 01 -
    ARQUITETURA.dwg" é dos nomes mais banais que existem em arquitetura. O
    segundo sobrescreve, e o primeiro passa a ler o motivo da falha DO OUTRO.
    Não é só diagnóstico trocado: a mensagem do ODA começa com "OdError thrown
    during readFile of drawing <caminho>", então o CAMINHO do arquivo alheio
    entraria no texto que este cliente lê. Isolamento entre projetos é regra
    dura nº2, e nome de arquivo de cliente é LGPD (nº6).

    O caminho completo já carrega o diretório de trabalho do job, que é único —
    então o isolamento sai de graça, sem passar job_id por seis assinaturas.
    """
    try:
        return os.path.normcase(os.path.abspath(str(dwg_path)))
    except Exception:
        return str(dwg_path)


def detalhe_do_err(err_content: str) -> str:
    """Texto do `.dxf.err` em UMA linha, com o motivo REAL preservado.

    🪤 A 1ª linha do ODA é genérica ("OdError thrown during readFile of drawing
    ... :") e o motivo vem DEPOIS. Ficar só com a primeira devolve uma frase que
    termina em dois-pontos — foi assim que o log do Render mostrou o erro o dia
    inteiro sem dizer nada. Junta todas com ` · ` pra caber numa linha do banco.
    🔑 Função de módulo porque é o que o guarda consegue CHAMAR: enquanto isto
    era um bloco dentro de `convert_dwg_to_dxf` (que precisa do ODA instalado),
    o teste só conseguia repetir a lógica — e teste que repete a régua não
    reprova quando a régua muda.
    """
    linhas = [l.strip() for l in str(err_content or "").splitlines() if l.strip()]
    return " · ".join(linhas)[:240]


def dwg_failure_detail(dwg_path: str) -> str:
    """O que o ODA disse ao recusar este DWG, em UMA linha (ou "")."""
    return _FALHA_DETALHE.get(_chave_da_falha(dwg_path), "")


#: basename do DWG -> por que o libredwg (plano B) não converteu
#: 🩸 16/09/2026: quando os DOIS conversores falham, o `dwg:convert-fail` do
#: motor registra só o nome do arquivo. O motivo do ODA já era guardado
#: (`_FALHA_DETALHE`), mas o do libredwg só existia num `logger.warning` — e o
#: log do Render é descartado. É justamente o caso PIOR (o cliente não recebe
#: medição nenhuma) e o único em que a gente ficava sem saber por quê. Em 60
#: dias foram 28 jobs assim.
_FALHA_LIBREDWG: dict = {}


def _anotar_falha_libredwg(dwg_path: str, motivo: str) -> None:
    """Guarda, em UMA linha, por que o plano B não converteu este DWG."""
    try:
        _linha = " · ".join(l.strip() for l in str(motivo or "").splitlines() if l.strip())
        _FALHA_LIBREDWG[_chave_da_falha(dwg_path)] = _linha[:240]
    except Exception:
        pass


def libredwg_failure_detail(dwg_path: str) -> str:
    """Por que o libredwg não converteu este DWG, em UMA linha (ou "")."""
    return _FALHA_LIBREDWG.get(_chave_da_falha(dwg_path), "")


def dwg_failure_reason(dwg_path: str) -> str:
    """Por que este DWG não converteu: 'truncado' ou '' (não classificado).

    'truncado' = o arquivo chegou incompleto/corrompido (o leitor bateu no fim do
    arquivo antes do esperado). O conselho certo é reabrir no CAD e salvar de
    novo — NÃO é 'exporte pra DXF', que não resolve arquivo quebrado.
    """
    return _FALHA_MOTIVO.get(_chave_da_falha(dwg_path), "")


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
        # 🚨 Aqui saia `return None` - e o plano B NUNCA rodava. O
        # fallback dependia do principal EXISTIR, que e o oposto de um
        # fallback: no dia em que o ODA saisse do container (o risco de
        # licenca esta aberto), o DWG morreria inteiro com o dwg2dxf
        # instalado do lado, sem nunca ser chamado.
        # Medido em 25/08: dos 26 DWGs de cliente que abriram nos ultimos
        # 22 dias, 23 vieram do libredwg e 3 do ODA. Quem carrega o
        # caminho hoje e o plano B.
        logger.warning(
            "ODA File Converter nao encontrado - indo direto pro libredwg "
            "(dwg2dxf). Pra reinstalar: "
            "https://www.opendesign.com/guestfiles/oda_file_converter"
        )
        return _try_libredwg_convert(dwg_path,
                                     tempfile.mkdtemp(prefix="arq_dxf_"))

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
        # Mesma causa do bloco la de cima: sem ODA utilizavel, o certo e
        # tentar o plano B, nao desistir.
        # 🩤 O TimeoutExpired logo abaixo NAO cai aqui de proposito:
        # la o ODA ja segurou a vez por 300s, e emendar outra conversao
        # estouraria o orcamento de tempo do job.
        logger.error("Executavel ODA nao acessivel (%s) - tentando libredwg",
                     oda_exe)
        return _try_libredwg_convert(dwg_path, output_dir)
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
        # 🔑 O motivo vive DEPOIS do "OdError thrown ... :" — quase sempre na
        # linha seguinte. Junta tudo numa linha só pra caber no log do banco:
        # quebra de linha vira ` · `, e o que interessa deixa de morrer no
        # tempdir.
        try:
            _FALHA_DETALHE[_chave_da_falha(dwg_path)] = detalhe_do_err(err_content)
        except Exception:
            pass
        # Classifica a causa pra main.py dar o conselho CERTO em vez de chutar
        # "versão nova do AutoCAD ou objetos especiais" — que foi o que o cliente
        # cliente-101 leu em 29/07 quando o problema real era arquivo INCOMPLETO
        # (ODA: "Unexpected end of file"). Conselho errado = ele reenviou o mesmo
        # arquivo 2x e desistiu da prancha.
        _low_err = (err_content or "").lower()
        if ("unexpected end of file" in _low_err
                or "invalid system section page map" in _low_err
                or "premature end" in _low_err):
            _FALHA_MOTIVO[_chave_da_falha(dwg_path)] = "truncado"
        # 🪤 Sem isto a CAUSA se perde: o .err mora num tempdir que o Render apaga,
        # e o _oda_log.txt (o que /api/debug/oda-log devolve) é escrito ANTES desta
        # checagem. Resultado: "DWG não converteu" sem nunca dizer por quê — caso
        # cliente-30 29/07, em que o ODA saiu com rc=0 e só deixou o .err pra trás.
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
        _anotar_falha_libredwg(dwg_path, "dwg2dxf não instalado no servidor")
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
        _anotar_falha_libredwg(dwg_path, "plano B desligado (LIBREDWG_FALLBACK != 1)")
        return None

    stem = Path(dwg_path).stem
    out_path = os.path.join(output_dir, stem + "_libredwg.dxf")

    try:
        # 🩸 24/09/2026 (jobs a62f7ae3, 09e2e640): o dwg2dxf escreve na tela os
        # nomes dos estilos de texto do DWG, que em arquivo brasileiro vêm em
        # cp1252. Sem `errors`, ler essa conversa levantava UnicodeDecodeError
        # e o DXF que ele JÁ tinha gerado ia pro lixo — erro terminal pro
        # cliente. A conversa só serve pro log; o arquivo é o que importa.
        result = subprocess.run(
            [dwg2dxf, "-y", "-o", out_path, dwg_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        if result.returncode == 0 and os.path.isfile(out_path):
            # 🚫 RESGATE POR --minimal DESLIGADO EM 18/08/2026, horas depois de
            # ligado, por medição própria. `_resgatar_dxf_gigante` continua aqui
            # (testada, funciona) mas NÃO é chamada: o `-m` apaga a seção BLOCKS
            # e com ela TODA a geometria de dentro dos blocos.
            # Medido em 5 arquivos reais: 3.762 blocos com definição -> 0, e
            # 198.461 entidades que saíam da explosão -> 0. Cem por cento.
            # 🪤 A bancada anterior disse "5 de 5 IGUAL" porque comparava
            # hachura, texto e área — tudo do NÍVEL DE CIMA. O que mora dentro
            # do bloco não aparecia na comparação. Bloco nomeado é como as 385
            # estacas da cliente-20 foram medidas.
            # Entregar planilha sem isso pareceria completa e não seria: pior
            # que a falha honesta que o cliente recebe hoje (ver a mensagem de
            # `motor:prancha-grande-demais`).
            # ⚰️ `--as r12` foi testado como alternativa que preserva BLOCKS:
            # o libredwg não converte esses arquivos pra R12 (não gera saída).
            # Pra religar: resolver a perda de bloco OU avisar o cliente de
            # forma inescapável E rebaixar tudo da prancha resgatada a
            # 'estimado'. Nada disso está feito.
            return out_path
        logger.warning("libredwg dwg2dxf retornou %d: %s",
                       result.returncode, result.stderr[:300])
        # 🪤 rc=0 sem arquivo é caso diferente de rc≠0: um é "converteu e sumiu",
        # o outro é "recusou". Quem lê o log em 21/09 precisa distinguir.
        _anotar_falha_libredwg(
            dwg_path,
            ("dwg2dxf saiu 0 mas não gerou arquivo"
             if result.returncode == 0 else
             "dwg2dxf saiu %d: %s" % (result.returncode,
                                      (result.stderr or result.stdout or "sem mensagem")[:180])))
    except subprocess.TimeoutExpired:
        logger.warning("libredwg dwg2dxf excedeu timeout 300s")
        _anotar_falha_libredwg(dwg_path, "dwg2dxf excedeu o tempo (300 s)")
    except Exception as e:
        logger.warning("libredwg dwg2dxf erro: %s", e)
        _anotar_falha_libredwg(dwg_path, "dwg2dxf quebrou: %s: %s" % (type(e).__name__, e))
    return None


# Teto duro de DXF que o extrator aceita carregar. Era LOCAL dentro de
# extract_dxf; virou de módulo em 18/08/2026 porque o resgate por --minimal
# precisa saber se o arquivo enxuto ficou abaixo dele. Duas cópias do mesmo
# número em arquivos diferentes é como um limite vira mentira com o tempo.
# 🚨 250 MB, medido em 26/08/2026 — era 150 MB, calibrado quando o Render tinha
# 2 GB. O plano subiu pra 4 GB em 21/07 e o teto nunca foi revisitado.
#
# O que a extracao gasta de RAM, medido nas 4 pranchas reais do caso cliente-16:
#     DXF  27,1 MB ->   215 MB de pico   (7,9x)
#     DXF  45,7 MB ->   374 MB           (8,2x)
#     DXF  53,8 MB ->   461 MB           (8,6x)
#     DXF 176,5 MB -> 1.476 MB           (8,4x)
# Fator estavel de ~8,6x no pior caso. A 250 MB o pico fica em ~2,15 GB, 52% do
# container de 4 GB.
#
# A prancha 01 da cliente-16 (176,5 MB) era DESCARTADA por este teto e roda
# completa em 82s, sobrando 64% do container.
#
# 🪤 O teto de DXF sozinho nao protege: quem explode primeiro e a CONVERSAO,
# que gasta 45 a 53x o tamanho do DWG e nao tinha trava nenhuma. Ver
# _MAX_DWG_BYTES logo abaixo — os dois andam juntos.
_MAX_DXF_BYTES = 250 * 1024 * 1024  # 250 MB — prancha normal é <20 MB

# 🚨 TETO DE DWG (novo, 26/08/2026). NAO EXISTIA — e e o lado que derruba o
# servidor. O upload aceita 450 MB no total; um unico DWG de 100 MB pediria
# ~5 GB so pra converter e mataria o container de 4 GB antes de qualquer
# medicao. Medido, pico do dwg2dxf:
#     DWG  3,1 MB ->   165 MB   (53x)
#     DWG  5,4 MB ->   249 MB   (46x)
#     DWG  6,4 MB ->   337 MB   (53x)
#     DWG 24,6 MB -> 1.056 MB   (43x)
#
# 🩸 03/09/2026 — O TETO RECUSOU UM ARQUIVO QUE A GENTE LÊ. Caso cliente-48 (job 75dab573, "BRB Estadio"), primeiro projeto dele: DWG de
# 44,5 MB recusado, com o log dizendo "converter pediria ~2227 MB de RAM e
# derrubaria o servidor; nem tentei". Baixei o arquivo dele e medi:
#
#     conversão: pico  836 MB (18,8x) em 27 s   ← previsto: 2.227 MB
#     DXF gerado: 248,3 MB
#     extração:  pico 1.964 MB (7,9x o DXF) em 87 s, exit 0
#
# Ou seja: cabia FOLGADO, nas três etapas. Ele reagiu subindo um PDF, que é o
# caminho que só estima. Recusa errada não devolve o cliente pro lugar certo.
#
# 🔑 POR QUE A PREVISÃO ERRAVA: todas as medidas acima são de arquivo PEQUENO
# (3,1 a 24,6 MB). O fator CAI conforme o arquivo cresce — parte do custo da
# conversão é fixa. Medido nos grandes, no mesmo dia:
#     DWG 11,7 MB -> ~29x   (produção, Render, amostragem de 30 s)
#     DWG 44,5 MB ->  18,8x
#     DWG 53,2 MB ->  26x
# Extrapolar 53x de um arquivo de 3 MB pra um de 44 MB errou por 2,7 vezes.
#
# 🪤 A trava de memória do FILHO (2,5 GB) continua sendo o juiz da extração —
# este teto só protege a CONVERSÃO, que roda no processo do servidor e não tem
# trava nenhuma. A 60 MB, com o pior fator medido nos grandes (29x), o pico
# fica em ~1,7 GB; com um pessimista 35x, em 2,1 GB — a mesma folga que o teto
# antigo se propunha a deixar, agora sobre número medido e não sobre
# extrapolação.
_MAX_DWG_BYTES = 60 * 1024 * 1024  # 60 MB de DWG ≈ 1,7 GB na conversão (medido)


# Fator em metros por $INSUNITS, lido direto do TEXTO do cabeçalho (sem ezdxf).
_RX_INSUNITS = re.compile(r"\$INSUNITS\s*\n\s*70\s*\n\s*(\d+)")


def unidade_do_cabecalho_dxf(dxf_path: str, limite_bytes: int = 2_000_000):
    """Lê $INSUNITS lendo só o COMEÇO do DXF, sem carregar o arquivo.

    O HEADER é a primeira seção do DXF, então o dado que decide a escala de
    TODO o projeto custa alguns KB de leitura. Medido em 6 arquivos reais:
    64 KB bastaram em todos.

    Devolve o fator em metros, ou None quando o desenho não declara unidade.
    """
    dados = b""
    try:
        with open(dxf_path, "rb") as f:
            while len(dados) < limite_bytes:
                ch = f.read(65536)
                if not ch:
                    break
                dados += ch
                if b"$INSUNITS" in dados and b"ENDSEC" in dados:
                    break
    except OSError:
        return None
    m = _RX_INSUNITS.search(dados.decode("latin-1", "replace"))
    if not m:
        return None
    ins = int(m.group(1))
    if ins and ins in _INSUNITS_TO_METERS:
        return _INSUNITS_TO_METERS[ins]
    return None


def _resgatar_dxf_gigante(dwg2dxf: str, dwg_path: str, cheio: str, output_dir: str):
    """Reconverte com `--minimal` o DXF que passou da trava dura, e devolve o enxuto.

    🎯 Caso cliente-93 (18/08/2026): 5 DWG de ~50 MB viraram DXF de **370 MB** cada.
    A trava de 150 MB do extrator recusou as 5 e o cliente recebeu ZERO. O
    `dwg2dxf -m` grava só $ACADVER, HANDSEED e ENTITIES — medido em 6 arquivos
    reais, encolhe **90 a 96%** e derruba a RAM da extração de 77-202 MB para
    ~45 MB, praticamente CONSTANTE em vez de crescer com o arquivo.

    🚨 O `-m` joga fora o cabeçalho, e com ele o $INSUNITS. Sem isso a extração
    cai no chute de milímetro e a área sai **100× errada** — medido, 5 de 6
    arquivos. Por isso a unidade é lida ANTES, do arquivo cheio, e devolvida
    junto: quem chama TEM que repassar como `unit_factor_override`.
    🪤 Sem unidade declarada não há resgate: entregar geometria com escala
    adivinhada violaria a regra dura nº1. Melhor a falha honesta.

    Só age em arquivo que HOJE já resulta em zero — o caminho que funciona não
    muda em nada.

    Devolve o caminho do enxuto, ou None (aí o chamador segue com o cheio).
    """
    try:
        tam = os.path.getsize(cheio)
    except OSError:
        return None
    if tam <= _MAX_DXF_BYTES:
        return None                      # cabe no caminho normal — não mexe

    fator = unidade_do_cabecalho_dxf(cheio)
    if fator is None:
        logger.warning("[resgate-minimal] %s tem %d MB mas NÃO declara $INSUNITS "
                       "— sem unidade não há resgate (regra dura nº1)",
                       os.path.basename(cheio), tam // 1048576)
        return None

    enxuto = os.path.join(output_dir, Path(dwg_path).stem + "_libredwg_min.dxf")
    try:
        r = subprocess.run([dwg2dxf, "-y", "-m", "-o", enxuto, dwg_path],
                           capture_output=True, text=True, timeout=300)
    except Exception as e:
        logger.warning("[resgate-minimal] dwg2dxf -m falhou: %s", e)
        return None
    if r.returncode != 0 or not os.path.isfile(enxuto):
        logger.warning("[resgate-minimal] dwg2dxf -m retornou %d", r.returncode)
        return None

    novo = os.path.getsize(enxuto)
    if novo > _MAX_DXF_BYTES:
        logger.warning("[resgate-minimal] %s: %d MB -> %d MB, ainda acima do "
                       "limite de %d MB", os.path.basename(cheio), tam // 1048576,
                       novo // 1048576, _MAX_DXF_BYTES // 1048576)
        try: os.remove(enxuto)
        except OSError: pass
        return None

    # 🪤 O arquivo cheio some AGORA. São centenas de MB por prancha e o disco do
    # Render estava em 83% no dia do caso — 5 pranchas dessas enchem 1,85 GB.
    try:
        os.remove(cheio)
    except OSError:
        pass
    logger.info("[resgate-minimal] %s: %d MB -> %d MB (unidade %.4f m do cabeçalho)",
                os.path.basename(dwg_path), tam // 1048576, novo // 1048576, fator)
    _UNIDADE_DE_RESGATE[os.path.abspath(enxuto)] = fator
    return enxuto


# Fator de unidade descoberto no resgate, por caminho de arquivo. O `-m` apaga o
# cabeçalho, então esta é a ÚNICA fonte de escala pro arquivo enxuto.
_UNIDADE_DE_RESGATE: dict = {}


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


def _texto_do_text(e) -> str:
    """O texto de um TEXT/ATTRIB como se LÊ na folha, sem os códigos de controle
    do AutoCAD: `%%U` (sublinhado) e `%%O` somem, `%%C` vira Ø, `%%D` vira °,
    `%%P` vira ±.

    🩸 25/09/2026 — os títulos de uma folha industrial vinham `%%UCORTE "A-A"`:
    a regra de título (que exige COMEÇAR pelo tipo) não os reconhecia, e a IA
    recebia o código cru. Medido no acervo local: 1 texto em 27 arquivos."""
    try:
        return (e.plain_text() or "").strip()
    except Exception:
        return (e.dxf.get("text", "") or "").strip()


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


def _hatch_bbox(entity):
    """Retângulo envolvente (x_min, y_min, x_max, y_max) de um HATCH, em
    COORDENADA CRUA do desenho — a mesma de `TextAnnotation.position`, senão o
    casamento rótulo↔área compararia unidades diferentes.

    🔑 Por que existe (09/08/2026): o casamento rótulo↔área só funcionava em
    polilinha fechada, e medi que os projetos reais quase não têm — 0 região em
    2 de 3 pranchas de cliente. A área que de fato mede vem de HACHURA
    ("Fonte: área hachurada do layer X" é o padrão mais comum das medições que
    dão certo), e ela não guardava posição nenhuma.

    Reusa a MESMA travessia de `_hatch_area` (make_path + flattening), então o
    que mede a área é o que dá o contorno — sem segunda interpretação da
    geometria. Devolve () quando não conseguir; nunca levanta.
    """
    try:
        from ezdxf import path as ezdxf_path
        pr = ezdxf_path.make_path(entity)
        if pr:
            xs, ys = [], []
            for p in (pr if isinstance(pr, list) else [pr]):
                try:
                    for v in p.flattening(0.5):
                        xs.append(v.x)
                        ys.append(v.y)
                except Exception:
                    continue
            if len(xs) >= 3:
                return (min(xs), min(ys), max(xs), max(ys))
    except Exception:
        pass
    # Último recurso: vértices crus dos boundary paths (perde arco, serve pro bbox)
    try:
        xs, ys = [], []
        for _p in entity.paths:
            for _v in (getattr(_p, "vertices", None) or []):
                xs.append(_v[0])
                ys.append(_v[1])
        if len(xs) >= 3:
            return (min(xs), min(ys), max(xs), max(ys))
    except Exception:
        pass
    return ()


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


#: Amostra de legenda: quadradinho de material, pequeno e repetido.
_AMOSTRA_MAX_M2 = 5.0
_AMOSTRA_MIN_LAYERS = 3
_AMOSTRA_TOL = 0.005
_AMOSTRA_RETANGULO = 0.98      # preenchimento do bbox: retângulo ≈ 1


def separar_amostras_de_legenda(hatches):
    """Tira das hachuras as AMOSTRAS DA LEGENDA. Devolve (hachuras, amostras).

    🩸 24/09/2026, job b6df4f3d (prancha de PISO): 15 hachuras de
    exatamente 1,73 m², em 15 layers diferentes (PIS-CAR-01..09,
    PIS-CER-01..03, PIS-VINIL, PIS-EXT, ARQ-ALV-HTC) — os quadradinhos que
    mostram cada material na legenda. O motor mediu como piso: a planilha
    saiu com "Piso vinílico 1,73 m² ✓ MEDIDO" (não existe vinílico na obra)
    e o porcelanato com 28,39 m² (a geometria real é 24,92; o resto eram
    duas amostras).

    🔑 O retrato da legenda: ≥3 layers DIFERENTES com hachura RETANGULAR da
    MESMA área (±0,5%), pequena (≤ 5 m²). Piso de ambiente real não se
    repete assim em três materiais. Mesma área no MESMO layer (os 10
    banheiros iguais de um hotel) não conta — é um layer só.
    """
    cand = [h for h in (hatches or [])
            if 0 < float(getattr(h, "area", 0) or 0) <= _AMOSTRA_MAX_M2
            and float(getattr(h, "preenchimento", 0) or 0) >= _AMOSTRA_RETANGULO]
    fora = set()
    usados = set()
    for h in cand:
        if id(h) in usados:
            continue
        a = float(h.area)
        grupo = [x for x in cand if abs(float(x.area) - a) <= _AMOSTRA_TOL * max(a, float(x.area))]
        if len({x.layer for x in grupo}) >= _AMOSTRA_MIN_LAYERS:
            fora.update(id(x) for x in grupo)
        usados.update(id(x) for x in grupo)
    if not fora:
        return list(hatches or []), []
    return ([h for h in hatches if id(h) not in fora],
            [h for h in hatches if id(h) in fora])


#: Nome que o AutoCAD dá ao bloco criado por "Colar como bloco" (PASTEBLOCK):
#: "A$C" + hexadecimal. Não é bloco de biblioteca (porta, louça): é um pedaço
#: do DESENHO que alguém colou. O nome não diz nada — o conteúdo diz tudo.
_RE_BLOCO_COLADO = re.compile(r"^A\$C[0-9A-F]+$", re.IGNORECASE)

#: Teto de entidades criadas ao abrir (anti-explosão de memória). O caso que
#: motivou tem 75.472; o teto é o mesmo da explosão de parede (~400k).
_MAX_ENTIDADES_COLADAS = 400000
#: Colado dentro de colado: o caso real tinha 2.700 A$C aninhados.
_MAX_NIVEIS_COLADOS = 12


def abrir_blocos_colados(doc) -> dict:
    """Abre (EXPLODE) no modelspace todo bloco `A$C…` — o desenho colado como
    bloco — nível por nível, até não sobrar nenhum.

    🩸 24/09/2026, job 09e2e640. Um prédio de 12 pavimentos em 10 pranchas
    chegou com 2.070 entidades soltas e **75.472 dentro de 140 blocos A$C**
    (2.700 deles aninhados): portas P70/P80/P90 centenas de vezes, 5.985
    cotas, 2.206 hachuras, layer de pilar. O motor só lê o modelspace e
    descarta `A$C` na contagem (`$` no nome = "lixo do AutoCAD") — saiu com
    0 medidas e 36 de 42 linhas em branco, com o desenho INTEIRO no arquivo.
    Em 120 dias: 15 de 74 jobs com CAD tinham A$C (10 clientes).

    🔑 Abre SÓ `A$C`. Bloco com nome de gente (P80, CAMA80) continua INSERT —
    é assim que ele é CONTADO pelo nome; a explosão só leva ele pro lugar
    certo, com a transformação do pai. Abrir na ENTRADA (antes das réguas de
    unidade e de tudo que lê o modelspace) faz o desenho colado valer igual
    ao desenho solto — nem mais, nem menos: nenhuma régua ganha exceção.

    🪤 Não há contagem dobrada com a explosão de parede de infra (~3160): ela
    varre os INSERTs do modelspace, e depois daqui não sobra INSERT de A$C.

    Kill switch: DXF_ABRIR_BLOCOS_COLADOS=0. Nunca levanta.
    """
    info = {"abertos": 0, "entidades": 0, "niveis": 0, "falhas": 0, "teto": False}
    if os.getenv("DXF_ABRIR_BLOCOS_COLADOS", "1").strip() == "0":
        return {}
    # O ezdxf avisa "copy process ignored DIMASSOC" a cada cota copiada — no
    # caso real, centenas de linhas. Mesmo silêncio (e mesmo finally) da
    # explosão de parede: o nível do logger global SEMPRE volta.
    _ezlog = logging.getLogger("ezdxf")
    _ez_prev = _ezlog.level
    _ezlog.setLevel(max(_ez_prev or logging.WARNING, logging.ERROR))
    # quem não abriu não volta pra fila: sem isto o mesmo bloco era tentado
    # (e contado como falha) em cada um dos 12 níveis — achado do guarda.
    _recusados = set()
    try:
        msp = doc.modelspace()
        for nivel in range(_MAX_NIVEIS_COLADOS):
            colados = [e for e in msp.query("INSERT")
                       if id(e) not in _recusados
                       and _RE_BLOCO_COLADO.match(str(e.dxf.get("name", "") or ""))]
            if not colados:
                break
            info["niveis"] = nivel + 1
            for ins in colados:
                if info["entidades"] >= _MAX_ENTIDADES_COLADAS:
                    info["teto"] = True
                    break
                try:
                    novos = ins.explode()
                    info["abertos"] += 1
                    info["entidades"] += len(novos)
                except Exception:
                    # bloco que o ezdxf não explode (escala não-uniforme em
                    # entidade que não aceita): fica como estava — o mesmo
                    # resultado de antes deste conserto, nunca pior.
                    info["falhas"] += 1
                    _recusados.add(id(ins))
            if info["teto"]:
                break
    except Exception as e:
        logger.warning("abrir_blocos_colados: %s", e)
        info["falhas"] += 1
    finally:
        _ezlog.setLevel(_ez_prev)
    return info if (info["abertos"] or info["falhas"]) else {}


# ---------------------------------------------------------------------------
# Leitura por FOLHA — cada desenho do modelspace pelo que ele é
# ---------------------------------------------------------------------------
# 🩸 24/09/2026 — job `0a999117`: 12 folhas num DWG só — plantas do térreo ao
# 8º, ESQUEMA VERTICAL, detalhes. O modelspace tem todos esses desenhos lado a
# lado e a extração somava o layer do arquivo inteiro: 1.088 m de tubo "✓
# MEDIDO" = plantas UMA vez + 837 m do esquema vertical (o mesmo tubo de novo) +
# 33 m de detalhes. Pelas plantas × andares o prédio tem ~518 m. E a planta
# "QUARTO/QUINTO/SEXTO PAVIMENTO", desenhada uma vez, vale por três.
# 🔑 O arquivo diz as duas coisas: cada VIEWPORT de folha mostra um retângulo do
# modelspace (alvo + centro da vista ± tamanho/escala) e o TÍTULO do desenho diz
# o que é. `engine_rules.tipo_do_desenho` e `andares_do_titulo` leem o título;
# aqui fica só a geometria.
# 🪤 A janela é `view_target_point + view_center_point`. Sem o alvo ela sai
# deslocada (31 m no arquivo real) e o tubo cai na folha errada — foi o 1º erro
# do estudo, e só apareceu porque os títulos não batiam com o que eu achava.
_RE_TAG_TITULO = re.compile(r"TITUL|TITLE", re.IGNORECASE)


def _janela_da_viewport(vp):
    """(x0, y0, x1, y1) do modelspace que a viewport mostra, ou None."""
    d = vp.dxf
    if d.get("id", 2) == 1:              # a própria folha, não uma janela
        return None
    vh, h, w = d.get("view_height", 0), d.get("height", 0), d.get("width", 0)
    if not (vh and h and w) or vh <= 0 or h <= 0 or w <= 0:
        return None
    if abs(d.get("view_twist_angle", 0) or 0) > 1e-6:
        return None                      # vista girada: não sei o retângulo — neutro
    dv = d.get("view_direction_vector", (0, 0, 1))
    if abs(dv[0]) > 1e-6 or abs(dv[1]) > 1e-6:
        return None                      # vista 3D/isométrica da viewport — neutro
    esc = h / vh
    alvo = d.get("view_target_point", (0, 0, 0))
    c = d.get("view_center_point", (0, 0))
    cx, cy = alvo[0] + c[0], alvo[1] + c[1]
    mw, mh = w / esc, vh
    return (cx - mw / 2, cy - mh / 2, cx + mw / 2, cy + mh / 2)


def _dentro(p, cx):
    return cx[0] <= p[0] <= cx[2] and cx[1] <= p[1] <= cx[3]


_RE_SO_ESCALA = re.compile(r"^\s*(?:esc(?:ala)?\.?\s*:?\s*)?1\s*[:/]\s*\d{1,4}\s*$", re.IGNORECASE)


def _titulo_no_papel(papel, textos) -> str:
    """O título da vista escrito no PAPEL, logo abaixo da janela ('' se não há).

    🩸 25/09/2026 — job `42f99f4f` (esgoto e pluvial exportados do REVIT): 16
    janelas por folha e NENHUM título achado, porque o Revit escreve o título
    de cada vista no espaço do papel (layer `G-ANNO-TTLB`): o nome junto do
    canto de baixo-esquerdo da janela e a escala ("1 : 20") numa linha logo
    abaixo. Entre as vistas havia três "3D - Térreo - …": o isométrico da
    tubulação, somado como planta — 83% do tubo "medido" da folha 1.

    Pega o texto MAIOR na faixa logo abaixo da janela (até 15% da altura dela),
    começando perto da borda esquerda; a linha só de escala não vale.
    """
    if not papel or not textos:
        return ""
    x0, y0, x1, y1 = papel
    w, h = (x1 - x0), (y1 - y0)
    if w <= 0 or h <= 0:
        return ""
    cand = [t for t in textos
            if y0 - 0.15 * h <= t[2] <= y0 + 0.02 * h
            and x0 - 0.05 * w <= t[1] <= x0 + 0.6 * w
            and not _RE_SO_ESCALA.match(t[0]) and len(t[0]) <= 90]
    if not cand:
        return ""
    cand.sort(key=lambda t: (-t[3], abs(t[2] - y0) + abs(t[1] - x0)))
    return cand[0][0]


def _desenhos_no_modelo(msp, caixa=None) -> list:
    """Desenhos lado a lado no MODELO, achados pelo título de cada um.

    🩸 25/09/2026 — job `53f0483f` (elétrica industrial, 3 DWG): cada arquivo é
    uma folha A1 INTEIRA desenhada no modelspace — moldura, carimbo, planta,
    cortes e detalhes lado a lado — com UMA janela mostrando tudo. Sem janela
    por desenho, `mapa_de_folhas` só achava o título do carimbo ("DISTRIBUIÇÃO
    DE FORÇA…"), que não diz o que é, e o DETALHE típico (99,5 m de
    "eletroduto", os leitos dos níveis 3 e 4) entrou na soma como percurso.

    O desenho é o bloco de geometria logo ACIMA do seu título (é como se
    desenha: título e escala embaixo). Título = a mesma regra do resto: começa
    pelo que o desenho é e é a letra GRANDE da folha.

    v1 conservadora, de propósito: só 'fora' tira da soma. 'vista' vai pro log
    (continua na soma, como decidido em 24/09). 'planta' entra só como PROTEÇÃO
    — caixa de detalhe/corte que CRUZA a caixa de uma planta não vale — e nunca
    multiplica andar: a região vem de proximidade de geometria, e um ×N errado
    custa caro. Na dúvida devolve [] (fica como era).
    """
    from engine_rules import parece_titulo_de_desenho, tipo_do_desenho
    try:
        def _na_caixa(x, y):
            return caixa is None or _dentro((x, y), caixa)

        textos = []
        for e in msp.query("TEXT MTEXT"):
            try:
                p = e.dxf.insert
                if not _na_caixa(p[0], p[1]):
                    continue
                h = float((e.dxf.get("height", 0) if e.dxftype() == "TEXT"
                           else e.dxf.get("char_height", 0)) or 0)
                t = _texto_do_text(e) if e.dxftype() == "TEXT" else e.plain_text()
                t = " ".join((t or "").split())
                if t and h > 0:
                    textos.append((t, p[0], p[1], h))
            except Exception:
                continue
        if not textos:
            return []
        hmax = max(t[3] for t in textos)
        titulos = []
        for t, x, y, h in textos:
            if len(t) > 90 or h < 0.8 * hmax:
                continue
            tipo = tipo_do_desenho(t)
            if tipo in ("fora", "vista") and parece_titulo_de_desenho(t):
                titulos.append((t, x, y, h, tipo))
            elif tipo == "planta":
                titulos.append((t, x, y, h, tipo))      # só proteção
        # só 'vista' não tira nada da soma, mas vai pro log o quanto pesa (é o
        # dado que decide se corte sai da soma — ver engine_rules)
        if not any(tt[4] in ("fora", "vista") for tt in titulos):
            return []

        # Geometria: segmentos (e o ponto de inserção dos blocos).
        segs = []
        for e in msp.query("LINE LWPOLYLINE ARC CIRCLE INSERT"):
            try:
                tp = e.dxftype()
                if tp == "LINE":
                    pts = [(e.dxf.start[0], e.dxf.start[1]), (e.dxf.end[0], e.dxf.end[1])]
                elif tp == "LWPOLYLINE":
                    pts = [(p[0], p[1]) for p in e.get_points("xy")]
                elif tp in ("ARC", "CIRCLE"):
                    c, r = e.dxf.center, float(e.dxf.radius)
                    pts = [(c[0] - r, c[1]), (c[0] + r, c[1])]
                else:
                    p = e.dxf.insert
                    pts = [(p[0], p[1]), (p[0], p[1])]
                for a, b in zip(pts, pts[1:]):
                    if _na_caixa(*a) and _na_caixa(*b):
                        segs.append((a, b))
            except Exception:
                continue
        if not segs:
            return []
        xs = [c for s in segs for c in (s[0][0], s[1][0])]
        ys = [c for s in segs for c in (s[0][1], s[1][1])]
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        lado = max(x1 - x0, y1 - y0)
        if lado <= 0:
            return []
        cel = lado / 150.0
        # Moldura e linhas de carimbo atravessam a folha e colariam tudo.
        # 🩸 25/09 (mesmo job): a 1ª régua era "mais de 40% do lado" — e o
        # leito de um corte industrial corre 57% da folha. Sem as linhas
        # compridas, o CORTE A-A virou um pedaço de 6 m de largura e 291 m de
        # leito caíram fora dele. Moldura é o que atravessa a FOLHA TODA na
        # sua direção (a de margem tem ~96%); desenho comprido não é moldura.
        larg, alt = (x1 - x0) or 1.0, (y1 - y0) or 1.0
        ocup = set()
        for (ax, ay), (bx, by) in segs:
            L = math.hypot(bx - ax, by - ay)
            if abs(bx - ax) > 0.85 * larg or abs(by - ay) > 0.85 * alt:
                continue
            n = max(1, int(L / cel) + 1)
            for k in range(n + 1):
                f = k / n
                ocup.add((int((ax + f * (bx - ax) - x0) / cel),
                          int((ay + f * (by - ay) - y0) / cel)))
        def _componentes(vao):
            """Blocos de desenho: células vizinhas, tolerando `vao` células de vão."""
            comp_de, comps = {}, []
            passos = range(-vao, vao + 1)
            for c0 in ocup:
                if c0 in comp_de:
                    continue
                idx, pilha, cel_comp = len(comps), [c0], []
                comp_de[c0] = idx
                while pilha:
                    cx, cy = pilha.pop()
                    cel_comp.append((cx, cy))
                    for dx in passos:
                        for dy in passos:
                            v = (cx + dx, cy + dy)
                            if v in ocup and v not in comp_de:
                                comp_de[v] = idx
                                pilha.append(v)
                gx = [c[0] for c in cel_comp]
                gy = [c[1] for c in cel_comp]
                comps.append((x0 + min(gx) * cel, y0 + min(gy) * cel,
                              x0 + (max(gx) + 1) * cel, y0 + (max(gy) + 1) * cel))
            return comp_de, comps
        # 1 célula de vão tolerada (2 de passo); a de vão 0 só se precisar
        malhas = {2: _componentes(2)}
        area_folha = (x1 - x0) * (y1 - y0) or 1.0
        out = []
        for t, x, y, h, tipo in titulos:
            # O que está logo ACIMA do título — ao longo da LARGURA dele, não só
            # do ponto de inserção. 🩸 25/09 (mesmo job): o "CORTE 'D-D'" começa
            # 1,4 m à esquerda do desenho; olhando só a coluna do 1º caractere,
            # nada acima, e o corte inteiro ficou na soma. Mais perto em altura
            # ganha; empate, a coluna mais perto do MEIO do título.
            ix, iy = int((x - x0) / cel), int((y + 0.5 * h - y0) / cel)
            ifim = int((x + 0.75 * h * len(t) - x0) / cel)
            meio = (ix + ifim) / 2.0
            colunas = sorted(range(ix - 2, ifim + 3), key=lambda c: abs(c - meio))
            caixa_t = None
            # 🩸 25/09 (mesmo job): na folha da PLANTA, uma divisória da coluna
            # de notas emendava planta, notas e planta-chave num bloco só (85%
            # da folha) e a planta-chave — 30 m no layer do leito — ficava na
            # soma. Se o 1º bloco é a folha toda, tenta de novo sem tolerar vão.
            for vao in (2, 1):
                if vao not in malhas:
                    malhas[vao] = _componentes(vao)
                comp_de, comps = malhas[vao]
                achado = None
                for passo in range(0, 21):
                    for cx in colunas:
                        v = (cx, iy + passo)
                        if v in comp_de:
                            achado = comp_de[v]
                            break
                    if achado is not None:
                        break
                if achado is None:
                    break
                bx0, by0, bx1, by1 = comps[achado]
                if (bx1 - bx0) * (by1 - by0) <= 0.6 * area_folha:
                    caixa_t = (bx0, by0, bx1, by1)
                    break                       # senão "o desenho" seria a folha toda
            if caixa_t is None:
                continue
            bx0, by0, bx1, by1 = caixa_t
            out.append({"folha": "modelo", "caixa": (bx0, by0, bx1, by1),
                        "titulo": t[:160], "tipo": tipo, "andares": 1,
                        "como": "modelo"})
        # 🪤 Uma linha que emenda o detalhe na planta estica a caixa do detalhe
        # por cima da planta — e o que da planta caísse ali sairia da soma.
        # Caixa de detalhe/corte que CRUZA caixa de planta: não vale (fica 1).
        plantas = [f["caixa"] for f in out if f["tipo"] == "planta"]

        def _cruza(a, b):
            return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
        out = [f for f in out
               if f["tipo"] == "planta" or not any(_cruza(f["caixa"], p) for p in plantas)]
        return out if any(f["tipo"] in ("fora", "vista") for f in out) else []
    except Exception as e:                       # nunca derruba a extração
        logger.warning("_desenhos_no_modelo: %s", e)
        return []


def mapa_de_folhas(doc) -> dict:
    """Os desenhos do modelspace, pelas folhas: [{folha, titulo, tipo, andares, caixa}].

    tipo 'fora' = não entra na soma (esquema, detalhe, corte…); 'planta' = entra,
    multiplicada por `andares`; '' = não sei, fica como está. Nunca levanta.
    """
    from engine_rules import andares_do_titulo, parece_titulo_de_desenho, tipo_do_desenho
    out = {"folhas": [], "gerais": 0, "sem_janela": 0}
    try:
        janelas = []
        textos_papel = {}                # folha → [(texto, x, y, altura)] do PAPEL
        for lay in doc.layouts:
            if lay.name.lower() == "model":
                continue
            for vp in lay.query("VIEWPORT"):
                cx = _janela_da_viewport(vp)
                if cx is None:
                    if vp.dxf.get("id", 2) != 1:
                        out["sem_janela"] += 1
                    continue
                c, w, h = vp.dxf.center, float(vp.dxf.width), float(vp.dxf.height)
                janelas.append({"folha": lay.name, "caixa": cx,
                                "papel": (c[0] - w / 2, c[1] - h / 2, c[0] + w / 2, c[1] + h / 2)})
            tp = []
            for t in lay.query("TEXT MTEXT"):
                try:
                    s = _texto_do_text(t) if t.dxftype() == "TEXT" else t.plain_text()
                    s = " ".join((s or "").split())
                    alt = float((t.dxf.get("height", 0) if t.dxftype() == "TEXT"
                                 else t.dxf.get("char_height", 0)) or 0)
                    if s:
                        tp.append((s, t.dxf.insert[0], t.dxf.insert[1], alt))
                except Exception:
                    continue
            textos_papel[lay.name] = tp
        if not janelas:
            return out
        # Janela GERAL: a que mostra o desenho todo (contém o centro de 3+
        # outras). No arquivo real, toda folha tinha uma, 1:1000, cobrindo tudo.
        centros = [((j["caixa"][0] + j["caixa"][2]) / 2, (j["caixa"][1] + j["caixa"][3]) / 2)
                   for j in janelas]
        uteis = []
        for i, j in enumerate(janelas):
            dentro = sum(1 for k, c in enumerate(centros) if k != i and _dentro(c, j["caixa"]))
            if dentro >= 3:
                out["gerais"] += 1
            else:
                uteis.append(j)
        # Títulos: atributo de bloco TITULO* primeiro; senão, o maior texto
        # que diga o que é o desenho.
        attrs, textos = [], []
        msp = doc.modelspace()
        for ins in msp.query("INSERT"):
            try:
                for a in ins.attribs:
                    _ta = _texto_do_text(a)
                    if _RE_TAG_TITULO.search(a.dxf.tag or "") and _ta:
                        p = a.dxf.insert
                        attrs.append((" ".join(_ta.split()), p[0], p[1]))
            except Exception:
                continue
        alturas = []                     # (x, y, altura) de TODO texto
        for e in msp.query("TEXT MTEXT"):
            try:
                p = e.dxf.insert
                alt = float((e.dxf.get("height", 0) if e.dxftype() == "TEXT"
                             else e.dxf.get("char_height", 0)) or 0)
                alturas.append((p[0], p[1], alt))
                t = _texto_do_text(e) if e.dxftype() == "TEXT" else e.plain_text()
                t = " ".join((t or "").split())
                if t and len(t) <= 90 and parece_titulo_de_desenho(t) and tipo_do_desenho(t):
                    textos.append((t, p[0], p[1], alt))
            except Exception:
                continue
        n_plantas_na_folha = {}
        for j in uteis:
            x0, y0, x1, y1 = j["caixa"]
            m = 0.12 * (y1 - y0)                 # título costuma ficar logo abaixo
            larga = (x0, y0 - m, x1, y1)
            tits = [a[0] for a in attrs if _dentro((a[1], a[2]), j["caixa"])]
            if not tits:
                tits = [a[0] for a in attrs if _dentro((a[1], a[2]), larga)]
            if not tits:
                # 🩸 Título é a LETRA GRANDE da janela. No acervo, o marcador
                # "DET.XX" (altura 0,1, numa legenda cuja maior letra é 0,3)
                # virou título e tirou 448 m. Compara com TODO texto da janela,
                # não só com os que parecem título.
                hs = [a[2] for a in alturas if _dentro((a[0], a[1]), j["caixa"])]
                hmax = max(hs) if hs else 0.0
                cand = [t for t in textos if _dentro((t[1], t[2]), j["caixa"])]
                tits = [t[0] for t in cand if hmax > 0 and t[3] >= 0.8 * hmax]
            if not tits:
                # 25/09: o Revit escreve o título da vista no PAPEL, logo
                # abaixo da janela — não no modelo, onde se procurava até aqui
                _tp = _titulo_no_papel(j.get("papel"), textos_papel.get(j["folha"], []))
                if _tp:
                    tits = [_tp]
                    j["titulo_no_papel"] = True
            tipos = {tipo_do_desenho(t) for t in tits} - {""}
            j["titulo"] = " | ".join(dict.fromkeys(tits))[:160]
            j["tipo"] = tipos.pop() if len(tipos) == 1 else ""
            j["andares"], j["como"] = 1, ""
            if j["tipo"] == "planta":
                n_plantas_na_folha[j["folha"]] = n_plantas_na_folha.get(j["folha"], 0) + 1
                if len(tits) == 1:
                    j["andares"], j["como"] = andares_do_titulo(tits[0])
        # O NOME da folha ("4 - 5 E 6 PAV.") também diz os andares — mas só
        # vale pra planta se ela for a ÚNICA planta daquela folha.
        for j in uteis:
            if j["tipo"] != "planta" or n_plantas_na_folha.get(j["folha"]) != 1:
                continue
            nf, como_f = andares_do_titulo(j["folha"])
            if nf <= 1:
                continue
            if j["como"] == "":                 # o título não diz andar nenhum
                j["andares"], j["como"] = nf, "nome da folha"
            elif j["andares"] != nf:            # título diz 1 (ou outro N), folha diz N
                j["andares"], j["como"] = 1, "conflito folha×titulo"
        # 25/09: nenhuma janela disse o que mostra (ex.: UMA janela com a folha
        # A1 inteira desenhada no modelo) → procura os desenhos pelo título.
        if uteis and not any(j.get("tipo") for j in uteis):
            _mod = _desenhos_no_modelo(msp, uteis[0]["caixa"] if len(uteis) == 1 else None)
            if _mod:
                uteis = _mod
                out["origem"] = "modelo"
        out["folhas"] = uteis
    except Exception as e:                   # nunca derruba a extração
        logger.warning("mapa_de_folhas: %s", e)
        out["erro"] = str(e)[:200]
    return out


# Título de planta TEMÁTICA do mesmo pavimento (layout, luminotécnica, pontos,
# forro, piso, demolir/construir, original…) — a base do pavimento redesenhada
# pra outro assunto. E o que diz que são pavimentos/unidades DIFERENTES.
_RE_PLANTA_TEMATICA = re.compile(
    r"(?i)layout|lumin|el[eé]tric|pontos|tomada|forro|piso|pagina[cç]|demoli|constru|"
    r"original|existente|reforma|hidr[aá]ul|mobili|ilumina|\bop\.|op[cç][aã]o|"
    r"acabamento|gesso|marcenaria|revestimento|ar.?condicionado|climatiza")
_RE_PAVIMENTO_OU_UNIDADE = re.compile(
    r"(?i)t[eé]rreo|superior|subsolo|cobertura|mezanino|\d+\s*[ºª°o]?\s*(?:pav|andar)|"
    r"pavimento\s+\d|\bbloco\b|\btorre\b|\bcasa\s+\d|\bunidade\b|\bapto?\.?\s*\d")


def _mesmo_pavimento(t1, t2) -> bool:
    """Dois títulos de planta falam do MESMO pavimento redesenhado?

    Só quando nenhum dos dois diz pavimento/unidade (andar diferente é quantidade
    de verdade, nunca repetição) E os títulos são iguais ou um deles é temático."""
    t1, t2 = (t1 or "").strip(), (t2 or "").strip()
    if not t1 or not t2:
        return False
    if _RE_PAVIMENTO_OU_UNIDADE.search(t1) or _RE_PAVIMENTO_OU_UNIDADE.search(t2):
        return False
    return t1.upper() == t2.upper() or bool(
        _RE_PLANTA_TEMATICA.search(t1) or _RE_PLANTA_TEMATICA.search(t2))


def _descartar_plantas_repetidas(walls, hatches, polygon_areas, blocks, regs) -> dict:
    """A base do pavimento redesenhada em várias plantas temáticas conta UMA vez.

    🩸 25/09/2026 — job `befab5aa` (projeto de interiores, 1 DWG): 5 plantas do
    MESMO apartamento — original, luminotécnica, pontos elétricos e duas opções
    de layout —, todas 'planta' de um andar, então a leitura por folha dizia
    "nada muda" e o motor SOMAVA as cinco. O guarda-corpo tinha 25,93 m em CADA
    planta e saiu 129,64 m "✓ MEDIDO" (5×); janela 42,32 m ×3; parede ×2.
    Medido no acervo local: o mesmo acontece nas plantas-chave "PONTOS / FORRO /
    PISO / PLANTA BAIXA" de folhas de elevação (18–22% do comprimento).

    🔑 Regra: um layer (ou bloco) presente (≥ 1 m; área ≥ 1 m²; contagem ≥ 1)
    em 2+ plantas do mesmo pavimento — e em pelo menos METADE delas — é a base
    redesenhada: fica UMA versão, a MAIOR (empate ±0,5%: a da primeira planta),
    as outras saem. Em menos da metade, só o valor IGUAL (±0,5%) é repetição;
    o diferente (o circuito que só a luminotécnica e a de pontos têm, cada uma
    o seu) é complemento e FICA inteiro. Pavimento/unidade diferente no título
    nunca junta. Muta as listas; devolve o que tirou. Nunca levanta.

    🩸 26/09/2026 — a 1ª regra (25/09) só juntava valor IGUAL, pra "não perder a
    parede nova do layout". Na releitura do mesmo job a camada PAREDE tinha
    633 / 420 / 257 / 254 / 254 m nas cinco plantas (original × layouts): só as
    duas iguais saíram e a planilha trouxe "construção de paredes novas
    1.589 ml" (× pé-direito = 4.768 m²). A camada inteira muda de uma versão
    pra outra, não só a parede nova — somar versões conta a base várias vezes.
    """
    out = {"m": 0.0, "m2": 0.0, "blocos": 0, "grupos": []}
    try:
        plantas = [f for f in regs if f.get("tipo") == "planta" and int(f.get("andares", 1) or 1) == 1]
        if len(plantas) < 2:
            return out

        def dona(p):
            """Índice da ÚNICA planta que contém p (ou None)."""
            if p is None:
                return None
            ks = [k for k, f in enumerate(plantas) if _dentro(p, f["caixa"])]
            return ks[0] if len(ks) == 1 else None

        def versoes(vals, minimo):
            """Grupos [fica, sai, sai…] das plantas do mesmo pavimento que têm o
            layer: 2+ plantas e pelo menos METADE das plantas daquele pavimento.
            Fica a versão maior (empate ±0,5%: a de menor índice)."""
            ks = [k for k, v in vals.items() if v >= minimo]
            grupos, usados = [], set()
            for k0 in sorted(ks, key=lambda k: (-vals[k], k)):
                if k0 in usados:
                    continue
                pav = [k for k in range(len(plantas)) if k == k0 or _mesmo_pavimento(
                    plantas[k0].get("titulo"), plantas[k].get("titulo"))]
                g = [k for k in ks if k in pav and k not in usados]
                if len(g) < 2:
                    continue
                if 2 * len(g) < len(pav):
                    # em poucas plantas: só o IGUAL (±0,5%) é repetição — o
                    # diferente é complemento (o circuito que só 2 de 5 têm)
                    g = [k for k in g if abs(vals[k] - vals[k0]) <= 0.005 * vals[k0]]
                    if len(g) < 2:
                        continue
                topo = max(vals[k] for k in g)
                fica = min(k for k in g if vals[k] >= topo * (1 - 0.005))
                usados.update(g)
                grupos.append([fica] + sorted(k for k in g if k != fica))
            return grupos

        def _meio(w):
            if tuple(w.start) == (0, 0) and tuple(w.end) == (0, 0):
                return None
            return ((w.start[0] + w.end[0]) / 2, (w.start[1] + w.end[1]) / 2)

        # comprimento por layer × planta
        por = {}
        for w in walls:
            k = dona(_meio(w))
            if k is not None:
                por.setdefault(w.layer, {}).setdefault(k, 0.0)
                por[w.layer][k] += w.length
        tirar_w = set()
        for lay, vals in por.items():
            for g in versoes(vals, 1.0):
                tirar_w.update((lay, k) for k in g[1:])
                out["grupos"].append((lay, round(vals[g[0]], 2), len(g),
                                      [round(vals[k], 1) for k in g]))
        if tirar_w:
            novas = []
            for w in walls:
                if (w.layer, dona(_meio(w))) in tirar_w:
                    out["m"] += w.length
                    continue
                novas.append(w)
            walls[:] = novas
        # área por layer × planta
        for lista in (hatches, polygon_areas):
            por_a = {}
            for h in lista:
                bb = getattr(h, "bbox", ()) or ()
                k = dona(((bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2)) if len(bb) == 4 else None
                if k is not None:
                    por_a.setdefault(h.layer, {}).setdefault(k, 0.0)
                    por_a[h.layer][k] += h.area
            tirar_a = set()
            for lay, vals in por_a.items():
                for g in versoes(vals, 1.0):
                    tirar_a.update((lay, k) for k in g[1:])
            if tirar_a:
                novas = []
                for h in lista:
                    bb = getattr(h, "bbox", ()) or ()
                    k = dona(((bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2)) if len(bb) == 4 else None
                    if (h.layer, k) in tirar_a:
                        out["m2"] += h.area
                        continue
                    novas.append(h)
                lista[:] = novas
        # contagem por bloco × planta
        novos = []
        for b in blocks:
            pos = list(getattr(b, "positions", None) or [])
            if len(pos) != b.count:
                novos.append(b)                          # posições incompletas: neutro
                continue
            cont = {}
            for p in pos:
                k = dona(p)
                if k is not None:
                    cont[k] = cont.get(k, 0) + 1
            tirar_b = set()
            for g in versoes({k: float(v) for k, v in cont.items()}, 1.0):
                tirar_b.update(g[1:])
            if tirar_b:
                fica = [p for p in pos if dona(p) not in tirar_b]
                out["blocos"] += b.count - len(fica)
                b.positions, b.count = fica, len(fica)
            if b.count > 0:
                novos.append(b)
        blocks[:] = novos
    except Exception as e:                       # nunca derruba a extração
        logger.warning("_descartar_plantas_repetidas: %s", e)
    out["m"], out["m2"] = round(float(out["m"]), 2), round(float(out["m2"]), 2)
    return out


_RE_SIGLA = re.compile(r"^[A-Z]{1,5}(?:-?\d{1,4})?[º°]?$")
_RE_SIGLA_IGUAL = re.compile(r"^([A-Z]{1,5}(?:-?\d{1,4}[º°]?)?)\s*=\s*([^=]{4,60})$")


def siglas_da_legenda(texts) -> dict:
    """{SIGLA: NOME} lido da legenda: a sigla e, NA MESMA LINHA logo à direita,
    o nome por extenso ("CH-90º   CURVA HORIZONTAL 90°"); ou "L = LEITO".

    🩸 25/09/2026, job 53f0483f (subestação): a tabela de acessórios dizia
    TH-90º = TÊ HORIZONTAL, CH-90º = CURVA HORIZONTAL, CZ-90º = CRUZETA — e a
    IA, lendo os textos soltos, trocou os três em quatro releituras ("TH"
    virou curva, cruzeta e até condulete). Mesma linha = diferença de altura
    até meia letra; à direita = até 25 letras de distância, a MAIS PERTO;
    nome = 2+ palavras com letras, que não é outra sigla. Nunca levanta.
    """
    try:
        itens = []
        for t in texts or []:
            txt = " ".join(str(getattr(t, "text", "") or "").split())
            p = getattr(t, "position", None)
            h = float(getattr(t, "height", 0) or 0)
            if not txt or not p or len(p) < 2 or h <= 0:
                continue
            itens.append((txt, float(p[0]), float(p[1]), h))
        def _nome(x):
            """Nome por extenso: começa por LETRA e é quase todo letra. 🪤 Medido
            no acervo: "PD=255cm", "A=4,20m²" e "H=70cm…" são MEDIDA, não nome."""
            x = x.strip().lstrip("-–—•* ").strip().rstrip(".")
            if not x or not x[0].isalpha():
                return ""
            if sum(c.isalpha() for c in x) < 0.6 * len(x.replace(" ", "")):
                return ""
            return x

        def _e_sigla(x):
            """Na tabela, sigla tem número/hífen ou é curta. 🪤 "RALO", "BACIA",
            "DUPLA" ao lado de um texto são rótulo, não sigla."""
            return (bool(_RE_SIGLA.match(x)) and len(x) >= 2
                    and (any(c.isdigit() for c in x) or "-" in x or len(x) <= 3))

        out = {}
        for txt, x, y, h in itens:
            m = _RE_SIGLA_IGUAL.match(txt)
            if m and _nome(m.group(2)):
                out.setdefault(m.group(1), _nome(m.group(2)))
        for txt, x, y, h in itens:
            if not _e_sigla(txt):
                continue
            melhor = None
            for t2, x2, y2, h2 in itens:
                if abs(y2 - y) > 0.5 * h or not (0 < x2 - x <= 25 * h):
                    continue
                n2 = _nome(t2)
                if _RE_SIGLA.match(t2) or not n2 or len(n2.split()) < 2 or len(n2) > 60:
                    continue
                # 🪤 cabeçalho de tabela ("QTD   DESCRIÇÃO - LUMINÁRIA") não é sigla
                if _RE_CAB_DESCRICAO.match(n2) or txt.upper() in ("QTD", "QTDE", "ITEM", "COD", "UN"):
                    continue
                if melhor is None or x2 - x < melhor[0]:
                    melhor = (x2 - x, n2)
            if melhor:
                out.setdefault(txt, melhor[1])
        return dict(list(out.items())[:40])
    except Exception as e:
        logger.warning("siglas_da_legenda: %s", e)
        return {}


def _peca_do_simbolo(e):
    """(tipo, tamanho, centro) de uma peça — tamanho que não muda com rotação."""
    t = e.dxftype()
    try:
        if t == "CIRCLE":
            return ("C", float(e.dxf.radius), (float(e.dxf.center[0]), float(e.dxf.center[1])))
        if t == "ARC":
            span = (e.dxf.end_angle - e.dxf.start_angle) % 360 or 360
            return ("A%d" % round(span / 15), float(e.dxf.radius),
                    (float(e.dxf.center[0]), float(e.dxf.center[1])))
        if t == "LINE":
            a, b = e.dxf.start, e.dxf.end
            return ("L", math.hypot(b[0] - a[0], b[1] - a[1]), ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
        if t == "LWPOLYLINE":
            pts = [(p[0], p[1]) for p in e.get_points("xy")]
            if len(pts) < 2:
                return None
            if e.closed:
                pts.append(pts[0])
            L = sum(math.dist(p, q) for p, q in zip(pts, pts[1:]))
            return ("P", L, (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)))
    except Exception:
        return None
    return None


_RE_CAB_SIMBOLO = re.compile(r"^s[ií]mbolo", re.IGNORECASE)
_RE_CAB_DESCRICAO = re.compile(r"^descri", re.IGNORECASE)


def contagem_pela_legenda(doc, mapa) -> list:
    """CONT.SE da tabela da legenda: cada SÍMBOLO desenhado na tabela, contado
    na PLANTA onde aparece o MESMO desenho, na mesma escala.

    🩸 25/09/2026, job 73c6f0ed (orçamentista, projeto elétrico/luminotécnico):
    a LEGENDA LUMINOTÉCNICO era uma tabela SÍMBOLO | QTD ("00") | DESCRIÇÃO —
    o projetista deixa a quantidade pra quem orça contar. O símbolo é desenho
    SOLTO (círculos, arcos, linhas), não bloco, e o motor — que conta bloco —
    entregou as luminárias com ZERO; o cliente contou à mão. Pedro: "é um
    CONT.SE no Excel".
    Regras (medidas contra o que o cliente digitou):
    - só vale desenho IGUAL: mesmas peças, mesmo tamanho (±3%), mesmas
      distâncias — aceita rotação. No caso, jardim 11 e AR111 6 = cliente.
      🪤 Aceitar escala livre achava demais (jardim 32): em outra escala
      sempre aparece um desenho parecido por acaso. Símbolo que o projetista
      redesenhou diferente na planta fica SEM contagem — nunca chuta;
    - símbolo de 2+ peças (um traço solto é genérico demais);
    - só dentro das janelas de PLANTA com título; sem elas, não conta (as
      cópias temáticas da planta triplicavam: jardim 33 no modelo, 11 na
      planta). A caixa da própria legenda não conta.
    Devolve [{"descricao", "n", "por_planta": {titulo: n}}] só com n > 0.
    Nunca levanta.
    """
    try:
        msp = doc.modelspace()
        textos = []
        for e in msp.query("TEXT MTEXT"):
            try:
                t = _texto_do_text(e) if e.dxftype() == "TEXT" else e.plain_text()
                t = " ".join((t or "").split())
                h = float((e.dxf.get("height", 0) if e.dxftype() == "TEXT"
                           else e.dxf.get("char_height", 0)) or 0)
                if t and h > 0:
                    textos.append((t, float(e.dxf.insert[0]), float(e.dxf.insert[1]), h))
            except Exception:
                continue
        cabecalhos = [x for x in textos if _RE_CAB_SIMBOLO.match(x[0])]
        if not cabecalhos:
            return []
        plantas = [f for f in (mapa or {}).get("folhas", []) if f.get("tipo") == "planta"]
        if not plantas:
            return []              # atalho: sem planta nada conta (evita explodir blocos)
        pecas = []
        for e in msp:
            tp = e.dxftype()
            if tp in ("LINE", "LWPOLYLINE", "CIRCLE", "ARC"):
                pecas.append(_peca_do_simbolo(e))
            elif tp == "INSERT":
                try:
                    b = doc.blocks.get(e.dxf.name)
                    if b is None or len(b) > 60:
                        continue
                    for v in e.virtual_entities():
                        if v.dxftype() in ("LINE", "LWPOLYLINE", "CIRCLE", "ARC"):
                            pecas.append(_peca_do_simbolo(v))
                except Exception:
                    continue
        pecas = [p for p in pecas if p and p[1] > 0]
        G = 0.25 * max(x[3] for x in cabecalhos) / 0.1       # grade na ordem do símbolo
        grade = {}
        for p in pecas:
            grade.setdefault((p[0], int(p[2][0] // G), int(p[2][1] // G)), []).append(p)

        def perto(tipo, c, r):
            out = []
            for gx in range(int((c[0] - r) // G), int((c[0] + r) // G) + 1):
                for gy in range(int((c[1] - r) // G), int((c[1] + r) // G) + 1):
                    out.extend(grade.get((tipo, gx, gy), ()))
            return out

        resultado = []
        for cab, cx, cy, ch in cabecalhos:
            desc = [d for d in textos if _RE_CAB_DESCRICAO.match(d[0])
                    and abs(d[2] - cy) <= ch and 0 < d[1] - cx < 40 * ch]
            if not desc:
                continue
            dx_ = min(desc, key=lambda d: d[1] - cx)[1]
            linhas = sorted([q for q in textos if abs(q[1] - dx_) <= 2 * ch
                             and cy - 80 * ch < q[2] < cy - 0.2 * ch and len(q[0]) > 3
                             and any(c.isalpha() for c in q[0])], key=lambda q: -q[2])
            if not linhas:
                continue
            leg = (cx - 3 * ch, min(q[2] for q in linhas) - 3 * ch, dx_ + 80 * ch, cy + 3 * ch)
            for i, (nome, lx, ly, lh) in enumerate(linhas):
                topo = (ly + linhas[i - 1][2]) / 2 if i else ly + 2 * lh
                base = (ly + linhas[i + 1][2]) / 2 if i + 1 < len(linhas) else ly - 2 * lh
                am = [p for p in pecas if cx - 1.5 * ch <= p[2][0] <= dx_ - 2 * ch
                      and base < p[2][1] < topo and p[1] < 3 * (topo - base)]
                if len(am) < 2:
                    continue
                am.sort(key=lambda p: (p[0] == "L", p[0] == "P", -p[1]))
                anc = am[0]
                rel = [(p[0], p[1], math.dist(p[2], anc[2])) for p in am[1:]]
                vistos = set()
                por_planta = {}
                for cand in [q for q in pecas if q[0] == anc[0]]:
                    if abs(cand[1] - anc[1]) > 0.03 * anc[1]:
                        continue
                    c = cand[2]
                    if leg[0] <= c[0] <= leg[2] and leg[1] <= c[1] <= leg[3]:
                        continue
                    k = (round(c[0], 3), round(c[1], 3))
                    if k in vistos:
                        continue
                    if not all(any(abs(q[1] - tam) <= 0.03 * tam
                                   and abs(math.dist(q[2], c) - d) <= 0.05 * max(d, anc[1])
                                   for q in perto(tp, c, d + anc[1]) if q is not cand)
                               for tp, tam, d in rel):
                        continue
                    vistos.add(k)
                    donas = [f for f in plantas if _dentro(c, f["caixa"])]
                    if len(donas) != 1:
                        continue
                    t_ = (donas[0].get("titulo") or donas[0].get("folha") or "planta")[:60]
                    por_planta[t_] = por_planta.get(t_, 0) + 1
                n = sum(por_planta.values())
                if n > 0:
                    resultado.append({"descricao": nome[:80], "n": n, "por_planta": por_planta})
        return resultado[:60]
    except Exception as e:                       # nunca derruba a extração
        logger.warning("contagem_pela_legenda: %s", e)
        return []


def _chave_de_texto(x) -> str:
    return " ".join(str(x or "").split()).lower()


def prancha_so_de_vista(extraction) -> bool:
    """A prancha tem corte/elevação e NENHUMA planta — a "prancha de cortes" do
    conjunto, cuja planta está em outro arquivo."""
    try:
        fl = getattr(extraction, "folhas", None) or {}
        if not fl.get("aplicada"):
            return False
        ds = fl.get("desenhos_lista") or []
        return (any(d.get("tipo") == "vista" for d in ds)
                and not any(d.get("tipo") == "planta" for d in ds))
    except Exception:
        return False


def etiquetas_contadas(extraction) -> dict:
    """{chave: (texto, n)} dos textos que ENTRAM na contagem ×N desta prancha
    (fora de corte/detalhe) e que contam objeto."""
    from engine_rules import texto_conta_objeto
    out = {}
    for t in getattr(extraction, "texts", None) or []:
        if getattr(t, "fora_da_contagem", False):
            continue
        k = _chave_de_texto(t.text)
        if not k or not texto_conta_objeto(t.text):
            continue
        out[k] = (" ".join(str(t.text).split()), out.get(k, ("", 0))[1] + 1)
    return out


def marcar_etiquetas_ja_contadas(extraction, contadas: dict) -> list:
    """Na prancha SÓ de corte, o texto que a planta de outra prancha do MESMO
    job já contou sai do ×N (`fora_da_contagem`, `ja_contada_em`).

    🩸 25/09/2026, job 53f0483f: "TH-90°" ×18 na planta (folha 2/4) e de novo
    ×12 e ×14 nos cortes (3/4 e 4/4). O aviso "não some com a planta de outra
    prancha" foi IGNORADO pela IA em duas releituras. O motor lê um arquivo por
    vez; `contadas` é o que as pranchas com planta já contaram neste job
    ({chave: (texto, n, prancha)}). 🪤 Depende da ORDEM: corte processado antes
    da planta não é pego. Devolve as chaves marcadas. Nunca levanta.
    """
    try:
        if not contadas or not prancha_so_de_vista(extraction):
            return []
        marcadas = set()
        for t in getattr(extraction, "texts", None) or []:
            k = _chave_de_texto(t.text)
            if k in contadas and not getattr(t, "fora_da_contagem", False):
                t.fora_da_contagem = True
                t.ja_contada_em = str(contadas[k][2] if len(contadas[k]) > 2 else "")
                marcadas.add(k)
        return sorted(marcadas)
    except Exception as e:                       # nunca derruba a extração
        logger.warning("marcar_etiquetas_ja_contadas: %s", e)
        return []


def _marcar_textos_repetidos_da_planta(texts, mapa) -> int:
    """Marca o texto de detalhe/vista que repete a planta (`fora_da_contagem`).

    🩸 25/09/2026 (releitura do job 53f0483f): a etiqueta de cada acessório de
    leito ("TH-90°", "CH-90°") aparece na planta e DE NOVO nos cortes; a IA
    somou as pranchas. O comprimento e o bloco da vista já saíam; o texto não.
    Continua na lista (traz especificação), mas fora do ×N.
    - DETALHE ('fora'): sai sempre — é o recorte típico redesenhado.
    - CORTE/ELEVAÇÃO: sai só se o MESMO texto é contado fora da vista neste
      arquivo. 🪤 Medido no acervo: nos cortes de interiores "nicho ×29",
      "prateleira ×5" e a "papeleira ×2" da elevação só existem ali — é a
      mesma regra do bloco (o único registro fica).
    Com planta junto, fica como era. Devolve quantos marcou. Nunca levanta.
    """
    try:
        regs = [f for f in (mapa or {}).get("folhas", [])
                if f.get("tipo") in ("fora", "vista", "planta")]
        if not any(f["tipo"] in ("fora", "vista") for f in regs):
            return 0

        def _chave(x):
            return " ".join(str(x or "").split()).lower()
        onde = []
        fora_da_vista = set()
        for t in texts:
            p = getattr(t, "position", None)
            tipos = set()
            if p and len(p) >= 2 and tuple(p[:2]) != (0, 0):
                tipos = {f["tipo"] for f in regs if _dentro(p, f["caixa"])}
            onde.append(tipos)
            if not (tipos and tipos <= {"fora", "vista"}):
                fora_da_vista.add(_chave(t.text))
        n = 0
        for t, tipos in zip(texts, onde):
            if not tipos or not tipos <= {"fora", "vista"}:
                continue
            if "fora" in tipos or _chave(t.text) in fora_da_vista:
                t.fora_da_contagem = True
                n += 1
        return n
    except Exception as e:                       # nunca derruba a extração
        logger.warning("_marcar_textos_repetidos_da_planta: %s", e)
        return 0


def aplicar_leitura_por_folha(walls, hatches, polygon_areas, blocks, mapa) -> dict:
    """Tira da medição o que está em desenho 'fora' e dá peso N à planta de N andares.

    Muta as listas no lugar. Posição que cai em desenhos que DISCORDAM (um fora,
    outro planta; plantas com andares diferentes) fica peso 1 — como era antes.
    Posição desconhecida (segmento explodido de bloco, hachura sem caixa) fica 1.

    VISTA (corte/elevação) — 🩸 25/09, job 53f0483f: os cortes de uma
    subestação somaram ~1,4 km de leito visto de lado ao da planta. Onde SÓ
    vista toca (nenhuma planta/fora junto — aí vale a regra de antes):
    comprimento sai; área FICA (revestimento de parede só existe na vista,
    24/09) — menos, no CORTE, a SEÇÃO CORTADA: faixa fina (lado curto ≤ 0,5 m,
    6× mais comprida que larga) é parede/laje cortada, não superfície (a
    "laje 31 m²" do caso). 🪤 Tirar TODA a área do corte levava junto o
    azulejo e o painel que o corte de interiores mostra ao fundo (medido: 60
    dos 81 m² de um arquivo de cortes). Bloco sai se o mesmo bloco aparece
    fora de vista neste arquivo (senão é o único registro dele — a papeleira
    que só a elevação mostra — e fica).
    """
    regs = [f for f in (mapa or {}).get("folhas", [])
            if f.get("tipo") in ("fora", "planta", "vista")]
    res = {"aplicada": False, "motivo": "", "desenhos": len(regs)}
    if not regs:
        res["motivo"] = "nenhum desenho com título que diga o que é"
        return res

    def _totais():
        return {"comprimento": round(sum(w.length * getattr(w, "peso", 1.0) for w in walls), 2),
                "area": round(sum(h.area * getattr(h, "peso", 1.0) for h in hatches)
                              + sum(p.area * getattr(p, "peso", 1.0) for p in polygon_areas), 2),
                "blocos": sum(b.count for b in blocks)}

    # 25/09: a base do pavimento redesenhada em plantas temáticas conta 1×
    antes = _totais()
    _rep = _descartar_plantas_repetidas(walls, hatches, polygon_areas, blocks, regs)
    if _rep["m"] or _rep["m2"] or _rep["blocos"]:
        res["repetidas"] = _rep
    tem_vista = any(f["tipo"] == "vista" for f in regs)
    if not tem_vista and not any(f["tipo"] == "fora" or f.get("andares", 1) > 1 for f in regs):
        if "repetidas" in res:
            res.update(aplicada=True, antes=antes, depois=_totais())
        else:
            res["motivo"] = "só plantas de um andar — nada muda"
        return res
    from engine_rules import vista_e_corte
    corte = {id(f): vista_e_corte(f.get("titulo", "")) for f in regs if f["tipo"] == "vista"}
    _NA_VISTA = -1                  # bloco: decide depois, pelo resto do arquivo

    ultimo = {"vista": False}       # o peso que acabou de sair veio da regra da vista?

    def peso(p, grandeza):
        """grandeza: 'm' (comprimento), 'm2' (área) ou 'bl' (bloco)."""
        ultimo["vista"] = False
        if p is None:
            return 1
        tocam = [f for f in regs if _dentro(p, f["caixa"])]
        if not tocam:
            return 1
        tipos = {f["tipo"] for f in tocam}
        # 🔒 Com planta/fora junto, a vista não opina: é a regra de antes.
        sem_vista = [f for f in tocam if f["tipo"] != "vista"]
        if sem_vista:
            tipos = {f["tipo"] for f in sem_vista}
            if tipos == {"fora"}:
                return 0
            if tipos == {"planta"}:
                ns = {int(f.get("andares", 1) or 1) for f in sem_vista}
                return ns.pop() if len(ns) == 1 else 1
            return 1
        ultimo["vista"] = True
        if grandeza == "m":
            return 0
        if grandeza == "m2":
            return 0 if all(corte[id(f)] for f in tocam) else 1
        return _NA_VISTA

    tirou = {"m": 0.0, "m2": 0.0, "blocos": 0}
    novas = []
    for w in walls:
        if tuple(w.start) == (0, 0) and tuple(w.end) == (0, 0):
            novas.append(w)                          # sem posição: neutro
            continue
        pk = peso(((w.start[0] + w.end[0]) / 2, (w.start[1] + w.end[1]) / 2), "m")
        if pk == 0:
            if ultimo["vista"]:
                tirou["m"] += w.length
            continue
        w.peso = float(pk)
        novas.append(w)
    walls[:] = novas
    def _secao_cortada(h):
        """Faixa fina: lado curto ≤ 0,5 m e 6× mais comprida que larga.
        O lado curto sai da ÁREA (m²) e da proporção da caixa — sem precisar
        da unidade do desenho."""
        bb = getattr(h, "bbox", ()) or ()
        if len(bb) != 4:
            return False
        w, t = abs(bb[2] - bb[0]), abs(bb[3] - bb[1])
        if min(w, t) <= 0:
            return True
        r = max(w, t) / min(w, t)
        return r >= 6 and math.sqrt(max(float(h.area), 0.0) / r) <= 0.5

    for lista in (hatches, polygon_areas):
        novas = []
        for h in lista:
            bb = getattr(h, "bbox", ()) or ()
            pk = peso(((bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2), "m2") if len(bb) == 4 else 1
            if pk == 0 and ultimo["vista"] and not _secao_cortada(h):
                pk = 1                               # corte: revestimento ao fundo fica
            if pk and ultimo["vista"]:
                # 🩸 25/09 (releitura do mesmo job): a área cheia que ficou no
                # corte saiu BRANCA como "piso de equipamentos 11,46 m²". A IA
                # precisa saber que ela foi vista DE LADO.
                h.na_vista = True
            if pk == 0:
                if ultimo["vista"]:
                    tirou["m2"] += h.area
                continue
            h.peso = float(pk)
            novas.append(h)
        lista[:] = novas
    # Bloco na vista: sai se o MESMO bloco é contado fora de vista no arquivo.
    pesos_de, fora_da_vista = {}, set()
    for b in blocks:
        pos = list(getattr(b, "positions", None) or [])
        if len(pos) != b.count:
            fora_da_vista.add(b.name)                # posições incompletas: conta
            continue
        pesos_de[id(b)] = [peso(p, "bl") for p in pos]
        if any(k > 0 for k in pesos_de[id(b)]):
            fora_da_vista.add(b.name)
    novos = []
    for b in blocks:
        if id(b) not in pesos_de:
            novos.append(b)                          # posições incompletas: neutro
            continue
        pos = list(b.positions)
        na_vista = 0 if b.name in fora_da_vista else 1
        pesos = [na_vista if k == _NA_VISTA else k for k in pesos_de[id(b)]]
        tirou["blocos"] += sum(1 for k in pesos_de[id(b)] if k == _NA_VISTA) * (1 - na_vista)
        b.positions = [p for p, k in zip(pos, pesos) if k > 0]
        b.count = int(sum(pesos))
        if b.count > 0:
            novos.append(b)
    blocks[:] = novos
    if tem_vista:
        res["vista"] = {"m": round(float(tirou["m"]), 1), "m2": round(float(tirou["m2"]), 1),
                        "blocos": tirou["blocos"]}
    depois = {"comprimento": round(sum(w.length * getattr(w, "peso", 1.0) for w in walls), 2),
              "area": round(sum(h.area * getattr(h, "peso", 1.0) for h in hatches)
                            + sum(p.area * getattr(p, "peso", 1.0) for p in polygon_areas), 2),
              "blocos": sum(b.count for b in blocks)}
    res.update(aplicada=True, antes=antes, depois=depois)
    return res


def medir_por_folha(walls, hatches, polygon_areas, blocks, mapa) -> dict:
    """Quanto pesa o que a leitura por folha deixa como estava — SÓ MEDE.

    📏 24/09/2026 (Pedro: "segue"). O log contava QUANTAS vistas havia, não
    quanto elas pesam; e o que nenhuma folha mostra (7 fogões num desenho solto,
    no caso do gás) nem aparecia. Os arquivos são apagados depois do job, então
    sem isto a próxima decisão seria no escuro. Chamar ANTES de
    `aplicar_leitura_por_folha` (mede a geometria original). Não muta nada.

    Devolve {'vista'|'neutro'|'sem_folha': {'m', 'm2', 'blocos'}}; vazio quando
    o arquivo não tem janela de folha nenhuma (aí tudo seria "sem folha").
    """
    folhas = (mapa or {}).get("folhas") or []
    if not folhas:
        return {}
    med = {k: {"m": 0.0, "m2": 0.0, "blocos": 0} for k in ("vista", "neutro", "sem_folha")}

    def onde(p):
        tocam = [f for f in folhas if _dentro(p, f["caixa"])]
        if not tocam:
            return "sem_folha"
        tipos = {f.get("tipo", "") for f in tocam}
        if tipos == {"vista"}:
            return "vista"
        if tipos == {""}:
            return "neutro"
        return None                     # planta/fora/mistura: já é da leitura

    for w in walls:
        if tuple(w.start) == (0, 0) and tuple(w.end) == (0, 0):
            continue                    # sem posição: não sei onde está
        k = onde(((w.start[0] + w.end[0]) / 2, (w.start[1] + w.end[1]) / 2))
        if k:
            med[k]["m"] += w.length
    for lista in (hatches, polygon_areas):
        for h in lista:
            bb = getattr(h, "bbox", ()) or ()
            if len(bb) != 4:
                continue
            k = onde(((bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2))
            if k:
                med[k]["m2"] += h.area
    for b in blocks:
        pos = list(getattr(b, "positions", None) or [])
        if len(pos) != b.count:
            continue
        for p in pos:
            k = onde(p)
            if k:
                med[k]["blocos"] += 1
    for v in med.values():
        # float() porque área de hachura pode chegar como np.float64
        v["m"], v["m2"] = round(float(v["m"]), 1), round(float(v["m2"]), 1)
    return med


def extract_dxf(filepath: str, unit_factor_override: Optional[float] = None) -> DXFExtraction:
    """Main extraction function — reads a .dxf file and returns structured data.

    Args:
        filepath: Path to a .dxf file.
        unit_factor_override: escala (fator p/ metros) PROVADA por cota em OUTRA
            prancha do mesmo projeto (consenso de unidade). Só é usada quando ESTA
            prancha NÃO tem cota própria que prove a escala — cota local sempre
            vence. Evita "pés" numa prancha BR sem cota (caso cliente-40 21/07).

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
    # 🔑 ARQUIVO RESGATADO NÃO TEM CABEÇALHO. O `dwg2dxf -m` grava só
    # $ACADVER, HANDSEED e ENTITIES: o $INSUNITS foi embora junto. Sem repor a
    # unidade aqui, a extração cai no chute de milímetro e a área sai 100×
    # errada — medido em 5 de 6 arquivos, 18/08/2026. A escala foi lida do
    # arquivo CHEIO antes de ele ser apagado e guardada por caminho.
    # 🪤 Não sobrescreve override de quem chama: cota PROVADA em outra prancha
    # continua valendo mais que o cabeçalho (o cabeçalho mente, 05/08).
    if unit_factor_override is None:
        _f_resgate = _UNIDADE_DE_RESGATE.get(os.path.abspath(filepath))
        if _f_resgate:
            unit_factor_override = _f_resgate
            logger.info("[resgate-minimal] usando unidade %.4f m/unidade guardada "
                        "para %s", _f_resgate, os.path.basename(filepath))

    if _sz > _MAX_DXF_BYTES:
        raise RuntimeError(
            f"DXF grande demais pra processar com segurança "
            f"({_sz // (1024 * 1024)} MB, limite {_MAX_DXF_BYTES // (1024 * 1024)} MB). "
            f"Exporte só a prancha necessária ou divida o arquivo em partes."
        )

    # Try UTF-8 first, then latin-1 (common in Brazilian CAD files)
    doc = None
    _erro_estrutura = None
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
            # 🚨 24/08: erro de ESTRUTURA (não de encoding) subia direto e
            # matava a prancha. Agora ele é guardado pra o `ezdxf.recover`
            # abaixo ter a chance de consertar o arquivo. Trocar troca de
            # encoding não resolve KeyError de layout.
            _erro_estrutura = f"{type(exc).__name__}: {exc}"
            if encoding is None:
                break
            if encoding == "latin-1":
                try:
                    doc = ezdxf.readfile(filepath)
                    break
                except Exception:
                    break
            continue

    if doc is None or _erro_estrutura is not None:
        # 🚨 24/08/2026 (caso cliente-19, job e1c48ed7): o readfile normal morre em
        # ezdxf/layouts/layouts.py:219 com KeyError do NOME DO LAYOUT. As três
        # ocorrências do MESMO job:
        #     KeyError: 'DO'
        #     KeyError: '00-Ã\x8dNDICE DO PROJETO'   (o "Í" lido como latin-1)
        #     KeyError: 'LAYOUT'
        # 🪤 A minha primeira leitura foi "é nome acentuado" — ERRADA: 'LAYOUT'
        # e 'DO' não têm acento. O que há em comum é o libredwg escrever
        # entradas de layout que o ezdxf não resolve de volta na própria tabela;
        # o acento é UM dos casos, não a causa.
        # Custou 3 das 7 pranchas do cliente (43%), incluindo as DUAS de
        # arquitetura, que são as que mais importam.
        #
        # `ezdxf.recover` é o remédio documentado pra arquivo de escritor
        # não-Autodesk: relê tolerando inconsistência estrutural. Roda só depois
        # que o caminho normal já falhou, então não muda nada de quem funciona.
        # 🪤 É mais lento e come mais RAM — mas esta função já vive num
        # subprocesso isolado (`dxf_extract_worker`), então o pior caso é o
        # filho morrer, que é exatamente o que acontece hoje sem tentar.
        try:
            # 24/08: o recover mora em dxf_open.py — o preview abria DXF por
            # outra porta e morria no MESMO KeyError. Consertar "o" lugar nao e
            # consertar; agora ha um lugar so.
            from dxf_open import recuperar_dxf
            doc = recuperar_dxf(filepath, str(_erro_estrutura))
        except Exception as _erec:
            if doc is None:
                raise RuntimeError(
                    f"Não foi possível abrir o DXF nem com ezdxf.recover: "
                    f"{filepath} — normal: {_erro_estrutura} | recover: {_erec}")

    if doc is None:
        raise RuntimeError(f"Não foi possível abrir o DXF com nenhum encoding: {filepath}")

    # 🔑 24/09: desenho colado como bloco vira desenho solto ANTES de qualquer
    # leitura — inclusive das réguas de unidade, que ganham as cotas de dentro.
    _colados = abrir_blocos_colados(doc)
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
    elif dim_check.get("status") in (None, "ambigua"):
        # 🚨 26/08/2026 — "ambigua" ESTAVA FORA desta cascata, e isso fazia a
        # prancha com MAIS evidência receber MENOS tentativa: prancha sem cota
        # nenhuma cai aqui e ganha duas réguas de reserva (DIMLFAC e
        # plausibilidade); prancha com 376 cotas virava "ambigua" e não ganhava
        # nenhuma. Provado por execução em 0326.CGR.14.600.PISO.
        # 🪤 Nos arquivos locais as duas reservas devolveram "nada" — então o
        # ganho medido aqui é ZERO. Está consertado porque é inconsistência
        # real, não porque rendeu número.
        # Cotas não decidiram (sem número digitado, sem consenso). Última régua:
        # o DIMLFAC, que converte UNIDADE e não depende de escala de plotagem.
        # Caso cliente-82 (05/08): 28 cotas com DIMLFAC=100 provam metro num
        # arquivo que declara milímetro — e sem isso os 36 pilares somem.
        _lfac = _unidade_por_dimlfac(doc, unit_factor)
        if _lfac.get("status") == "corrigida_lfac":
            unit_factor = _lfac["fator_corrigido"]
            logger.warning("[unit-lfac] %s", _lfac["mensagem"])
            dim_check = _lfac
            _, unit_warnings = _validate_unit_factor(doc, unit_factor)
        else:
            # 4ª e ÚLTIMA régua (17/08/2026, caso cliente-81): cota e DIMLFAC se
            # calaram — o desenho, na unidade declarada, é fisicamente
            # possível? Núcleo denso de 1,2 cm × 2,1 cm num prédio de 4
            # apartamentos não é. Corrige SÓ no regime impossível e a
            # correção NÃO é prova: entra como ressalva (nada sai
            # 'confirmado') e o cliente lê a procedência.
            _plaus = _unidade_por_plausibilidade(doc, unit_factor)
            if _plaus.get("status") == "corrigida_plausibilidade":
                unit_factor = _plaus["fator_corrigido"]
                logger.warning("[unit-plausibilidade] %s", _plaus["mensagem"])
                dim_check = _plaus
                _, unit_warnings = _validate_unit_factor(doc, unit_factor)
                unit_warnings.append(_plaus["mensagem"])
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
    # ── Unidade IMPERIAL em projeto brasileiro: desconfiar, nunca corrigir ────
    # Medido em 10/08/2026 no `error_log` (stage motor:unidade): 9 pranchas
    # declararam Polegadas — 6 da escola pública da cliente-16 (349e75a5, todas as
    # elétricas) e 3 de outros clientes. Nas NOVE, `cotas=-`: nenhuma tinha
    # cota pra confirmar ou desmentir o cabeçalho, e nenhuma foi corrigida.
    # Projeto de escola pública brasileira não é desenhado em polegada — é o
    # template do CAD que nunca foi configurado. Se o desenho está em mm e a
    # gente aplica 0,0254, cada medida sai 25,4× maior.
    #
    # 🚨 SÓ AVISA — não mexe no fator (regra dura nº3). Adivinhar "deve ser mm"
    # seria copiar valor de outro contexto, e foi exatamente o tipo de conserto
    # esperto que 3 céticos derrubaram hoje de manhã no resgate da linha zerada.
    # Quem prova escala aqui é a cota da prancha; sem ela, o cliente decide.
    #
    # 🪤 Fica DEPOIS do bloco de consenso de propósito: `unit_warnings` entra em
    # `_deteccao_local_forte` (linha ~2002), e avisar antes mudaria qual fator o
    # projeto escolhe. Aviso não pode ter efeito colateral de medição.
    try:
        from engine_rules import aviso_unidade_imperial as _aviso_imperial
        _av_imp = _aviso_imperial(_insunits_local, dim_check.get("status"))
        if _av_imp:
            unit_warnings.append(_av_imp)
    except Exception as _eai:      # regra nunca pode derrubar a extração
        logger.warning("[unit-imperial] checagem falhou: %s", _eai)

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
    try:
        metadata["diag_unidade"] = _diag_unidade_cabecalho(doc)
    except Exception:
        pass
    # "Régua da prancha" — resultado da validação da unidade pelas cotas.
    # Correção NÃO entra em unidade_suspeita (não é suspeita, é fator provado).
    try:
        _dim_status = dim_check.get("status")
        # 🔍 PROCEDÊNCIA DA RÉGUA (26/08/2026): antes, o log só dizia `cotas=-`,
        # e esse traço juntava cinco desfechos opostos. Sem isto, "o desenho não
        # tem cota" e "a régua desistiu com 1.163 cotas na mão" são a MESMA
        # linha — e o segundo é conserto possível, o primeiro não.
        # 🪤 Só REGISTRA. Não muda fator, selo nem quantidade.
        metadata["regua_cotas_status"] = _dim_status or "nao-decidiu"
        if dim_check.get("motivo"):
            metadata["regua_cotas_motivo"] = str(dim_check["motivo"])[:200]
        if dim_check.get("cotas_utilizaveis") is not None:
            metadata["regua_cotas_utilizaveis"] = dim_check["cotas_utilizaveis"]
        if dim_check.get("desempatada_por_fisica"):
            metadata["regua_cotas_desempate"] = dim_check["desempatada_por_fisica"]
        if _dim_status == "validada":
            metadata["unidade_validada_por_cotas"] = dim_check["n_cotas"]
            metadata["unidade_nome_provada"] = dim_check["unidade_nome"]
            if dim_check.get("heuristica_superada"):
                metadata["heuristica_extensao_superada_por_cotas"] = \
                    dim_check["heuristica_superada"]
        elif _dim_status in ("corrigida", "corrigida_lfac"):
            # corrigida_lfac (caso cliente-82) não deixava rastro no metadata — 21/08
            metadata["unidade_corrigida_por_cotas"] = dim_check["mensagem"]
            metadata["unidade_nome_provada"] = dim_check["unidade_nome"]
        elif _dim_status == "provada_por_rotulo":
            # 5ª RÉGUA: o rótulo de área da própria prancha bate com a
            # geometria. Prova de verdade (dado escrito × dado medido, mesma
            # natureza da cota) — então NÃO vira ressalva e a medição pode
            # sair 'confirmado'.
            metadata["unidade_provada_por_rotulo"] = dim_check["mensagem"]
            metadata["unidade_nome_provada"] = dim_check.get("unidade_nome", "")
        elif _dim_status == "corrigida_plausibilidade":
            # 🚨 NÃO é prova — vai pra `alerta_unidade`, que entra em
            # `extraction_has_quality_caveat`: nenhum item deste DXF sai
            # 'confirmado'. É medição destravada COM ressalva, não promoção.
            metadata["unidade_corrigida_por_plausibilidade"] = dim_check["mensagem"]
            metadata["alerta_unidade"] = dim_check["mensagem"]
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

    # Assinatura da definicao do bloco (tipos de entidade + quantos de cada).
    # 🚨 26/08/2026: o libredwg — que faz 88% das conversoes — renomeia bloco POR
    # INSTANCIA. Num DXF real: 1.202 nomes distintos pra 1.349 pecas, e a secao
    # CONTAGEM DE BLOCOS virou 44% do prompt. Na prancha da cliente-16 isso levou a
    # entrada a 74.875 tokens e a leitura devolveu ZERO item.
    # 🪤 Agrupar so pelo NOME estava errado e eu quase shipei: `Parede_1_1` e
    # `Parede_2_1` tinham 6 definicoes geometricas diferentes na amostra. Somar
    # aquilo seria o bug da bitola (Ø8 + Ø16 virando um numero so). A assinatura
    # e o que separa "mesma peca renomeada" de "pecas diferentes".
    _assin_cache: dict[str, str] = {}

    def _assinatura_do_bloco(bname: str) -> str:
        if bname in _assin_cache:
            return _assin_cache[bname]
        a = ""
        try:
            b = doc.blocks.get(bname)
            if b is not None:
                cont: Counter = Counter(e.dxftype() for e in b)
                if cont:
                    a = "|".join("%s:%d" % (k, v) for k, v in sorted(cont.items()))
                    # 🪤 So contar TIPO de entidade colide: dois chuveiros
                    # diferentes com "LINE:4" cada teriam a mesma assinatura e
                    # seriam somados. O tamanho da definicao separa. Medido nas
                    # pranchas da cliente-16: custa 2 pontos de reducao e separa
                    # 32 e 59 grupos que estavam sendo juntados errado.
                    _bb = _bbox_for_block_def(bname)
                    if _bb:
                        a += "|bb:%.1fx%.1f" % (round(_bb[0], 1), round(_bb[1], 1))
        except Exception:
            a = ""
        _assin_cache[bname] = a
        return a

    # ── ATRIBUTOS DE BLOCO (ATTRIB) — dado ESTRUTURADO pelo projetista ───────
    # 🔑 Quando o arquiteto usa bloco com atributo (quadro de áreas, etiqueta de
    # ambiente, carimbo), o valor vem com NOME DE CAMPO — não é texto solto pra
    # IA interpretar. Medido em 09/08 nos 26 DXF de teste: 3.158 ATTRIB em 1.215
    # INSERTs. O bloco 'area' da prancha HWB 201 traz 5 ambientes somando
    # 85,20 m², e NADA disso existe como TEXT/MTEXT — hoje era perdido inteiro.
    #
    # 🚨 PASSADA PRÓPRIA, ANTES DOS FILTROS. O laço de contagem abaixo pula
    # bloco de anotação (`_is_annotation_block`) e bloco com "$" no nome — e é
    # justamente aí que mora o quadro de áreas (AREA3, em todo o projeto CGR).
    # Ler junto com a contagem devolveria zero, calado.
    block_attributes: list = []
    try:
        for _ins in msp.query("INSERT"):
            try:
                _ats = list(getattr(_ins, "attribs", None) or [])
                if not _ats:
                    continue
                _campos = {}
                for _a in _ats:
                    _tag = str(getattr(_a.dxf, "tag", "") or "").strip()
                    _val = " ".join(str(getattr(_a.dxf, "text", "") or "").split())
                    if _tag and _val:
                        _campos[_tag[:40]] = _val[:80]
                if _campos:
                    block_attributes.append({
                        "bloco": str(getattr(_ins.dxf, "name", "") or "")[:60],
                        "layer": str(getattr(_ins.dxf, "layer", "") or "")[:60],
                        "campos": _campos,
                    })
            except Exception:
                continue
    except Exception as _eat:
        logger.warning("[attrib] leitura falhou: %s", _eat)

    # 🔬 26/08/2026 — CONTADOR DE DESCARTE. Caso cliente-36 (prancha ELÉTRICA de
    # 78 MB, job d5dbe1ed): `blocos=0` com `paredes=76824`. Prancha elétrica é
    # FEITA de bloco — luminária, tomada, ponto — e contar bloco é a única coisa
    # que o motor faz muito bem. Mas o log dizia só o total FINAL, então não
    # dava pra distinguir "o desenho não tem bloco" de "a gente jogou todos
    # fora". Metade de todas as pranchas (70 de 134) sai com blocos=0: se for
    # filtro nosso, é o defeito mais caro do motor; se for arquivo, é limite
    # honesto. Sem contar o descarte, a pergunta não tem resposta.
    # 🚨 Isto NÃO muda comportamento — só passa a contar. Trocar o filtro no
    # palpite é como eu perdi 5 de 5 ideias em 10/08.
    _desc = {"anonimo": 0, "utilitario": 0, "anotacao": 0, "ilegivel": 0}
    _amostra_anonimo = []

    # 🩸 25/09/2026, job 73c6f0ed (projeto elétrico exportado do Revit): a
    # tomada, o ponto de ar e as luminárias eram INSERIDOS a até 2 km da casa
    # — a definição do bloco trazia o desenho deslocado da base, e ele caía no
    # lugar certo só depois de escalar e girar. O motor situava cada bloco pelo
    # ponto de inserção: todos ficaram "fora de qualquer desenho" e a leitura
    # por folha não conseguiu separar planta de corte nem as plantas temáticas.
    # Quando o desenho está LONGE da base (mais de 5× o tamanho dele), a
    # posição passa a ser o centro do desenho levado pela inserção. Bloco
    # normal (desenho em volta da base) não muda.
    from ezdxf import bbox as _ezbbox
    _centro_cache: dict = {}
    _bbox_cache = _ezbbox.Cache()

    def _centro_do_desenho(ins):
        """(x, y) de onde o bloco APARECE, ou None quando o insert já serve."""
        n = ins.dxf.name
        if n not in _centro_cache:
            c = None
            try:
                b = doc.blocks.get(n)
                eb = _ezbbox.extents(b, cache=_bbox_cache) if b is not None else None
                if eb is not None and eb.has_data:
                    cx = (eb.extmin.x + eb.extmax.x) / 2
                    cy = (eb.extmin.y + eb.extmax.y) / 2
                    diag = math.hypot(eb.extmax.x - eb.extmin.x, eb.extmax.y - eb.extmin.y)
                    bp = b.block.dxf.base_point
                    if diag > 0 and math.hypot(cx - bp[0], cy - bp[1]) > 5 * diag:
                        c = (cx, cy)
            except Exception:
                c = None
            _centro_cache[n] = c
        c = _centro_cache[n]
        if c is None:
            return None
        try:
            w = ins.matrix44().transform((c[0], c[1], 0))
            return (w[0], w[1])
        except Exception:
            return None

    for insert in msp.query("INSERT"):
        try:
            bname = insert.dxf.name
            layer = insert.dxf.layer
            x = insert.dxf.insert.x
            y = insert.dxf.insert.y
        except Exception:
            _desc["ilegivel"] += 1
            continue

        # Skip anonymous / internal blocks (names starting with * or contendo $)
        # Blocos dinâmicos do AutoCAD têm sufixos tipo "A$C6BFD6B53" — filtrar.
        if bname.startswith("*") or "$" in bname:
            _desc["anonimo"] += 1
            # guarda alguns nomes: é o que diz se são lixo do AutoCAD ou item
            # de verdade renomeado na conversão (o caso que a gente suspeita)
            if len(_amostra_anonimo) < 5 and bname not in _amostra_anonimo:
                _amostra_anonimo.append(bname)
            continue
        # Skip utility / system layers that don't represent real items
        if layer and layer.upper() in _UTILITY_LAYERS_UPPER:
            _desc["utilitario"] += 1
            continue
        # Skip annotation / callout blocks (legendas, TAGs, cortes, elevações)
        if _is_annotation_block(bname):
            _desc["anotacao"] += 1
            continue

        if bname not in block_counter:
            block_counter[bname] = {
                "count": 0, "layer": layer, "positions": [],
                "widths": [], "heights": [],
            }
        block_counter[bname]["count"] += 1
        _onde = _centro_do_desenho(insert)
        if _onde is not None:
            x, y = _onde
            metadata["blocos_pelo_desenho"] = metadata.get("blocos_pelo_desenho", 0) + 1
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
            assinatura=_assinatura_do_bloco(name),
        )
        for name, info in block_counter.items()
    ]

    if not blocks:
        logger.warning(
            "Nenhum bloco (INSERT) usado no DXF: %s — descartados: %s%s",
            filepath, _desc,
            (" amostra=" + ", ".join(_amostra_anonimo)) if _amostra_anonimo else "")

    # ---- Lines / polylines (wall segments) --------------------------------
    walls: list[WallSegment] = []
    # 25/09: o que a LEGENDA da prancha diz ser leito/duto desenhado em duas
    # linhas (o nome do layer pode ser só um código, "K-04")
    _legenda_dupla = _legenda_de_linha_dupla(msp)
    _layers_linha_dupla = set(_legenda_dupla)

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
                _pontos = ()
                if lwpoly.dxf.layer in _layers_linha_dupla or _RE_DUTO_DUPLO.search(str(lwpoly.dxf.layer)):
                    _xyb = [(p[0], p[1], p[2]) for p in lwpoly.get_points(format="xyb")]
                    if lwpoly.closed and _xyb:
                        _xyb.append(_xyb[0])
                    _pontos = tuple(_xyb)
                walls.append(WallSegment(
                    layer=lwpoly.dxf.layer,
                    length=length,
                    start=start,
                    end=end,
                    pontos=_pontos,
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
    # (caso cliente-73/Engie 21/07: eletroduto nos blocos MATRIZ-*, 0 no modelspace).
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
                    # um bloco ruim não derrubar a prancha (caso cliente-40 004, 21/07).
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
    # direito ele mede bem (18 de 27). Explica o caso do cliente-83 (07/08): o
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
        # do Render e NÃO é consultável. Reprocessei o arquivo do cliente-83 pra medir
        # o conserto e fiquei sem saber se ele achou proxy ou não — instrumento
        # feito, evidência jogada fora. É a armadilha de
        # [[feedback-evidencia-nao-sobrevive]], e foi ela que fez o log de
        # unidade nascer (sem ele, o cabeçalho mentiroso da cliente-82 só apareceu
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
    # 🩸 09/09/2026 — O DESCARTE ERA MUDO, E ISSO PRODUZIU DIAGNÓSTICO ERRADO.
    # No job 43c52488 o log dizia `poligonos=0` nos dois arquivos e eu li como
    # "o desenho não tem contorno fechado". O código não permite afirmar isso:
    # a allowlist abaixo só aceita a palavra POR EXTENSO ("piso", "cobertura"),
    # e os layers daquele projeto eram `ARQ_COB`, `A-ROOF`, `ARQ_ALV` — nenhuma
    # abreviação BR usual nem termo em inglês casa. "Não tem" e "tem e a
    # peneira de NOME jogou fora" viram a MESMA ausência.
    # 🚫 NÃO ampliar a lista antes de ter o número. E ao ampliar, 🪤 nunca
    # acrescentar "for": neste acervo FOR é ambíguo — significa FÔRMA, e na
    # convenção do próprio prompt "FOR-" é layer de projeto NOVO, não forro.
    _poly_recusa = {"deny": 0, "fora_da_allowlist": 0, "area_minima": 0,
                    "poucos_pontos": 0}
    _poly_layers_recusados: dict = {}

    def _consider_poly(layer_name, pts):
        try:
            if len(pts) < 3:
                _poly_recusa["poucos_pontos"] += 1
                return
            clean = layer_name.split("|", 1)[-1].lower()
            if any(t in clean for t in _AREA_DENY):
                _poly_recusa["deny"] += 1
                return
            if not any(t in clean for t in _AREA_ALLOW):
                _poly_recusa["fora_da_allowlist"] += 1
                _poly_layers_recusados[layer_name] = (
                    _poly_layers_recusados.get(layer_name, 0) + 1)
                return  # allowlist: só superfície física reconhecível
            a = abs(_shoelace_area(pts)) * area_factor
            if a < 0.5:
                _poly_recusa["area_minima"] += 1
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
        # 🔑 `_bb` já era calculado aqui pra descartar polígono aninhado e era
        # jogado fora. Guardando: é o que permite casar o RÓTULO do ambiente com
        # a ÁREA dele (ver `casar_texto_com_regiao` em engine_rules).
        _w_p, _h_p = _bb[2] - _bb[0], _bb[3] - _bb[1]
        # 🪤 `_a` já vem em m² (multiplicado por area_factor em _consider_poly) e
        # `_bb` está cru — normaliza antes de dividir, senão dá 0 sempre.
        _fill_p = min(1.0, (_a / area_factor) / (_w_p * _h_p)) if (_w_p > 0 and _h_p > 0 and area_factor) else 0.0
        polygon_areas.append(HatchArea(layer=_ly, area=_a, pattern="contorno fechado",
                                       bbox=tuple(_bb), preenchimento=round(_fill_p, 4)))

    # ---- PILARES: retângulos/círculos FECHADOS em layer de PILAR ------------
    # Medição estrutural determinística (regra nº1): pilar em planta de fôrma é
    # um retângulo pequeno fechado. Antes ele virava só "perímetro somado" no
    # layer e a IA não tinha COMO contar → qty=0. Aqui a contagem é geométrica.
    # Conservador: só layer que NOMEIA pilar, só contorno fechado de 4 lados
    # (ou círculo), com lado 8cm–2,5m e área ≤ 3 m². Nada disso roda em prancha
    # de arquitetura sem layer de pilar.
    struct_rects: list = []
    # 🔬 27/08/2026 — CONTADOR DE DESCARTE DO PILAR. Caso do arquivo
    # `005-1515-1PV-FOR-R03 levantamento volume.dxf` ("FOR" = FÔRMA, a prancha
    # que é literalmente feita de retângulo de pilar e viga):
    #     hachuras=51 paredes=2545 cotas=198 textos=390  ->  pilares=0
    # São CINCO filtros em série aqui, e o log contava só o resultado final:
    # não dava pra separar "a prancha não tem pilar" de "o nome do layer não
    # bateu" ou "o tamanho caiu fora da faixa". Mesma cegueira do `blocos=0`
    # de 26/08, que só foi resolvida quando passou a contar o descarte.
    # 🔑 A amostra de NOMES é o que decide: `_PILAR_TOKENS` conhece só "PILAR"
    # e "COLUMN", casando por prefixo de token — `PILARES` passa, mas `PIL`,
    # `P` ou `EST-P` não. Sem ver os nomes reais, mexer no filtro é palpite.
    # 🚨 Isto NÃO muda comportamento — só conta.
    _desc_pil = {"nome_do_layer": 0, "nao_e_4_lados": 0, "nao_e_retangulo": 0,
                 "fora_de_escala": 0, "ilegivel": 0}
    _amostra_layers = {}          # {layer: quantos} dos recusados POR NOME
    if StructRect is not None:
        def _consider_pilar_poly(layer_name, pts):
            try:
                if not layer_is_pilar(layer_name):
                    # só conta o que TEM cara de pilar (contorno fechado de 4
                    # lados) — senão todo traço solto entraria e a amostra
                    # viraria ruído
                    _pp = pts[:-1] if (len(pts) >= 2
                                       and abs(pts[0][0] - pts[-1][0]) < 1e-9
                                       and abs(pts[0][1] - pts[-1][1]) < 1e-9) else pts
                    if len(_pp) == 4:
                        _desc_pil["nome_do_layer"] += 1
                        _k = str(layer_name)[:40]
                        _amostra_layers[_k] = _amostra_layers.get(_k, 0) + 1
                    return
                # remove ponto final repetido (polilinha fechada com 1º=último)
                if len(pts) >= 2 and abs(pts[0][0] - pts[-1][0]) < 1e-9 \
                        and abs(pts[0][1] - pts[-1][1]) < 1e-9:
                    pts = pts[:-1]
                if len(pts) != 4:
                    _desc_pil["nao_e_4_lados"] += 1
                    return
                d = [_line_length(pts[i], pts[(i + 1) % 4]) for i in range(4)]
                if min(d) <= 0:
                    _desc_pil["nao_e_retangulo"] += 1
                    return
                # lados opostos ~iguais (retângulo/paralelogramo, tolerância 15%)
                if abs(d[0] - d[2]) > 0.15 * max(d[0], d[2]):
                    _desc_pil["nao_e_retangulo"] += 1
                    return
                if abs(d[1] - d[3]) > 0.15 * max(d[1], d[3]):
                    _desc_pil["nao_e_retangulo"] += 1
                    return
                w_raw = (d[0] + d[2]) / 2.0
                h_raw = (d[1] + d[3]) / 2.0
                w_m, h_m = w_raw * unit_factor, h_raw * unit_factor
                if not (0.08 <= min(w_m, h_m) and max(w_m, h_m) <= 2.5
                        and w_m * h_m <= 3.0):
                    # 🪤 É AQUI que pilar some quando a UNIDADE está errada: com
                    # fator de polegada, 36 pilares viram 0,34 mm e caem todos
                    # neste filtro (ver nota na linha ~1133).
                    _desc_pil["fora_de_escala"] += 1
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
            _area_crua = _hatch_area(hatch)          # unidade do desenho²
            area = _area_crua * area_factor          # m²
            pattern = ""
            try:
                pattern = hatch.dxf.pattern_name
            except Exception:
                pass
            if area > 0:
                # 🔑 Sem o bbox o casamento rótulo↔área fica dormente: medi em
                # 09/08 que polilinha fechada quase não existe nos projetos
                # reais (0 região em 2 de 3 pranchas), enquanto a hachura é a
                # fonte mais comum das medições que dão certo.
                _bb = _hatch_bbox(hatch)
                _fill = 0.0
                if _bb and len(_bb) == 4:
                    _w, _h = _bb[2] - _bb[0], _bb[3] - _bb[1]
                    if _w > 0 and _h > 0:
                        # CRUA / CRUA — as duas na unidade do desenho.
                        _fill = min(1.0, _area_crua / (_w * _h))
                hatches.append(HatchArea(
                    layer=hatch.dxf.layer,
                    area=area,
                    pattern=pattern,
                    bbox=_bb,
                    preenchimento=round(_fill, 4),
                ))
        except Exception:
            continue
    hatches, _amostras = separar_amostras_de_legenda(hatches)
    if _amostras:
        # rastro: sem isto "a legenda virou piso" só se descobre baixando o arquivo
        metadata["amostras_legenda"] = "%d em %d layer(s), %.2f m2" % (
            len(_amostras), len({h.layer for h in _amostras}),
            sum(h.area for h in _amostras))

    # ---- Texts ------------------------------------------------------------
    texts: list[TextAnnotation] = []

    for text in msp.query("TEXT"):
        try:
            content = _texto_do_text(text)
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
    walls, _rel_duto, _ress_duto = _corrigir_duto_linha_dupla(
        walls, unit_factor, layers_extra=_layers_linha_dupla)
    if _rel_duto:
        metadata["duto_linha_dupla"] = _rel_duto
    if _legenda_dupla:
        # a IA precisa saber o que o layer É — antes era palpite ("o layer de
        # maior extensão") — e que o comprimento dele JÁ é o eixo
        metadata["legenda_linha_dupla"] = "; ".join(
            "%s = %s (na legenda: desenhado com 2 linhas — o comprimento do layer "
            "abaixo JÁ é o eixo)" % (lay, " / ".join(ds[:3]))
            for lay, ds in sorted(_legenda_dupla.items()))
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
        from engine_rules import (areas_do_texto_da_prancha_rotuladas
                                  as _areas_regra_rot)
        _pares = _areas_regra_rot([getattr(t, "text", "") for t in texts])
        _cand = [_v for _r, _v in _pares]
        if _cand:
            metadata["areas_do_quadro_texto"] = _cand
            # 🚨 20/09/2026 — os RÓTULOS, alinhados em ordem e tamanho com a
            # lista acima. Sem eles não dá pra separar AMBIENTE de linha de
            # TOTAL do quadro, e a régua do recorte lê o total do autor como se
            # fosse um ambiente gigante (ver `linha_do_quadro_de_areas`).
            # 🔒 Rótulo normalizado e curto, nunca o texto do autor.
            metadata["areas_do_quadro_rotulos"] = [_r for _r, _v in _pares]
            logger.info("[area-regra] %d candidato(s) de área lidos do texto: %s",
                        len(_cand), _cand[:6])
    except Exception as _ea:
        logger.warning("[area-regra] falhou (não-fatal): %s", _ea)

    # ── 5ª RÉGUA: o RÓTULO DE ÁREA confere com a geometria? ────────────────
    # 🚨 Roda no FIM, porque precisa das hachuras e dos textos já medidos com o
    # fator escolhido. Não muda o fator — VERIFICA. Se ≥2 rótulos que dizem
    # "57,16m²" caem em regiões que medem 57,16 m², a escala está PROVADA pelo
    # próprio desenho (dado escrito × dado medido, mesma natureza da cota).
    #
    # 💰 O que isso destrava (medido em 30 dias): de 492 linhas em m², só 2
    # saíram MEDIDAS — 0,4%. Contar bloco funciona (28%), medir superfície não.
    # Com a prova do rótulo, a ressalva de escala cai e o m² pode sair medido.
    #
    # 🪤 Só derruba ressalva de ESCALA. Extração estéril e xref não resolvido
    # continuam valendo — o rótulo prova a régua, não a completude do desenho.
    try:
        from engine_rules import (casar_texto_com_regiao as _casar5,
                                  unidade_provada_por_rotulo as _prova5)
        _p5 = _casar5(texts, list(polygon_areas) + list(hatches))
        _v5 = _prova5(_p5)
        if _v5.get("provada"):
            _ex = "; ".join(f'"{e["texto"]}"={e["medida"]}' for e in _v5["exemplos"][:3])
            metadata["unidade_provada_por_rotulo"] = (
                f"{_v5['n_batem']} rótulo(s) de área da própria prancha conferem "
                f"com a geometria medida ({_ex}) — escala provada pelo desenho.")
            # a prova supera a ressalva de ESCALA (não as outras)
            for _k in ("unidade_suspeita", "alerta_unidade"):
                if metadata.get(_k):
                    metadata[f"{_k}_superada_por_rotulo"] = metadata.pop(_k)
            logger.info("[unit-rotulo] %s", metadata["unidade_provada_por_rotulo"])
        elif _v5.get("n_rotulos_area"):
            metadata["rotulos_area_sem_prova"] = (
                f"{_v5['n_rotulos_area']} rótulo(s) de área na prancha, "
                f"{_v5['n_batem']} conferem com a geometria")
        # 📊 SOMBRA DA CONCORDÂNCIA (19/08/2026) — guarda SEMPRE, prove ou não.
        # A pergunta que decide se área lida do quadro pode virar "medido" é:
        # quando o rótulo diz 57,16 m² E a região que ele rotula MEDE 57,16, os
        # dois concordam com que frequência? São fontes independentes —
        # declaração do projetista × geometria medida por nós.
        # 🚨 Até aqui só ficava registro quando a prova DAVA CERTO. As
        # DISCORDÂNCIAS — que são exatamente o que diria se promover é
        # perigoso — não deixavam rastro. Contar só o sucesso é a forma mais
        # fácil de provar o que já se quer acreditar.
        # 🪤 Sombra pura: não muda fator, não muda selo, não muda quantidade.
        # Só acumula evidência pra decidir com N, e não com 4 casos de um
        # arquivo só (foi onde meu experimento local empacou).
        metadata["concordancia_rotulo"] = {
            "rotulos": int(_v5.get("n_rotulos_area") or 0),
            "batem": int(_v5.get("n_batem") or 0),
        }
    except Exception as _e5:
        logger.warning("[unit-rotulo] falhou (não-fatal): %s", _e5)

    # 📄 LEITURA POR FOLHA (24/09/2026, Pedro: "vamos ensinar ele a fazer
    # isso"). O esquema/detalhe sai da medição; a planta-tipo vale por N
    # andares. Ver `mapa_de_folhas`. Chave: LEITURA_POR_FOLHA=0 desliga sem
    # deploy. Qualquer falha aqui deixa a medição como estava.
    _folhas = {}
    if os.environ.get("LEITURA_POR_FOLHA", "1") != "0":
        try:
            _mapa = mapa_de_folhas(doc)
            _medida = medir_por_folha(walls, hatches, polygon_areas, blocks, _mapa)
            _folhas = aplicar_leitura_por_folha(walls, hatches, polygon_areas, blocks, _mapa)
            _n_txt = _marcar_textos_repetidos_da_planta(texts, _mapa)
            # 25/09: CONT.SE da tabela da legenda (ver `contagem_pela_legenda`)
            _cont_leg = contagem_pela_legenda(doc, _mapa)
            if _cont_leg:
                _folhas["legenda_contagem"] = _cont_leg
            if _n_txt:
                _folhas["textos_fora_da_contagem"] = _n_txt
            _folhas["medida"] = _medida
            _folhas["desenhos_lista"] = [
                {"folha": f["folha"][:40], "titulo": f.get("titulo", "")[:90],
                 "tipo": f.get("tipo", ""), "andares": f.get("andares", 1),
                 "como": f.get("como", "")}
                for f in _mapa.get("folhas", [])]
            _folhas["janelas_gerais"] = _mapa.get("gerais", 0)
            # 25/09: "modelo" = desenhos achados pelo título dentro do modelspace
            _folhas["origem"] = _mapa.get("origem", "")
            _folhas["sem_janela"] = _mapa.get("sem_janela", 0)
            # 🩸 25/09 (releitura do job 53f0483f): o relato do eixo é feito
            # ANTES da folha e dizia "431 m de face -> 230,5 m de eixo" numa
            # prancha que era só corte. O layer na soma dava ZERO, mas a IA
            # leu o relato e entregou 212,5 m de leito BRANCO. Depois da folha,
            # o relato só fala do que ficou na soma (sem folha aplicada nada
            # saiu — o número é o mesmo, muda só a redação).
            if metadata.get("duto_linha_dupla"):
                metadata["duto_linha_dupla"] = _relato_do_eixo_na_soma(
                    metadata["duto_linha_dupla"], walls)
        except Exception as _efl:
            logger.warning("[leitura-por-folha] falhou (não-fatal): %s", _efl)
            _folhas = {"aplicada": False, "motivo": "erro: %s" % str(_efl)[:120]}

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
        poly_recusa=dict(_poly_recusa),
        poly_layers_recusados=dict(
            sorted(_poly_layers_recusados.items(), key=lambda kv: -kv[1])[:8]),
        struct_rects=struct_rects,
        block_attributes=block_attributes,
        blocos_descartados=dict(_desc, amostra_anonimo=list(_amostra_anonimo)),
        blocos_colados=dict(_colados or {}),
        folhas=_folhas,
        pilares_descartados=dict(
            _desc_pil,
            amostra_layers=sorted(_amostra_layers.items(),
                                  key=lambda kv: -kv[1])[:5]),
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
        _erro = None
        for enc in ("utf-8", "latin-1", None):
            try:
                doc = ezdxf.readfile(filepath, **({"encoding": enc} if enc else {}))
                break
            except UnicodeDecodeError:
                continue
            except Exception as _e:
                _erro = f"{type(_e).__name__}: {_e}"
                if enc is None:
                    break
        if doc is None:
            # 24/08: erro de ESTRUTURA (KeyError de layout, caso cliente-19) devolvia
            # None calado e esta leitura sumia do consenso de area sem deixar
            # rastro. Agora tenta o recover, igual as outras portas.
            if _erro is None:
                return None
            try:
                from dxf_open import recuperar_dxf
                doc = recuperar_dxf(filepath, _erro)
            except Exception:
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


# ---------------------------------------------------------------------------
# Régua da PLAUSIBILIDADE FÍSICA — a última, quando cota e DIMLFAC não decidem
# ---------------------------------------------------------------------------
# 🚨 Por que existe (17/08/2026, caso cliente-81 75a774af): o arquivo declara
# MILÍMETRO ($INSUNITS=4) e está desenhado em METRO. O fator errado entra ao
# QUADRADO na área: as 143 hachuras somaram 0,0019 m² e o cliente recebeu
# alvenaria, revestimento e forro zerados — foi ele que digitou "100" de
# frustração em 14 linhas.
#
# As três réguas anteriores não decidiram, cada uma por um motivo legítimo:
#   cotas   — 3 de 5 concordam (60% < 80% exigido) → recusa, corretamente;
#   DIMLFAC — 1,0 em 253 de 253 cotas → não diz nada;
#   maior elemento — 16,6 cm, acima do piso de 5 cm → não dispara.
#
# Esta olha o NÚCLEO DENSO do desenho (percentis 25–75, que ignora carimbo e
# geometria perdida longe da planta). Medido no arquivo dele: 12,1 × 21,3
# unidades — a pegada de um prédio de 4 apartamentos de ~57 m². Em metro
# fecha; em milímetro seria 1,2 cm × 2,1 cm, fisicamente impossível.
#
# 🪤 Só corrige no regime IMPOSSÍVEL, nunca no meramente suspeito, e exige
# volume de desenho (detalhe de dobradiça é legitimamente pequeno e tem pouca
# entidade). O resultado NÃO é prova: entra como ressalva, então nenhum item
# sai 'confirmado' (regra dura nº1) e o cliente lê a procedência.

_PLAUS_CORE_MAX_M = 0.5      # núcleo denso menor que isto = impossível
_PLAUS_OK_MIN_M, _PLAUS_OK_MAX_M = 2.0, 200.0   # faixa plausível pós-correção
_PLAUS_MIN_PONTOS = 1000     # volume mínimo — detalhe pequeno não qualifica


def _nucleo_denso(doc, limite_pontos: int = 20000):
    """(largura, altura) do núcleo denso do desenho em unidades CRUAS.

    Percentis 25–75 dos pontos de LINE/LWPOLYLINE/TEXT. Ignora carimbo e
    entidade solta longe da planta, que inflam a extensão total (no arquivo do
    cliente-81: total 2.837 × 610, núcleo 12,1 × 21,3).
    """
    xs: list = []
    ys: list = []
    try:
        msp = doc.modelspace()
        for ent in msp:
            if len(xs) >= limite_pontos:
                break
            try:
                t = ent.dxftype()
                if t == "LINE":
                    xs.extend((ent.dxf.start.x, ent.dxf.end.x))
                    ys.extend((ent.dxf.start.y, ent.dxf.end.y))
                elif t == "LWPOLYLINE":
                    for p in ent.get_points():
                        xs.append(p[0]); ys.append(p[1])
                elif t in ("TEXT", "MTEXT"):
                    xs.append(ent.dxf.insert.x); ys.append(ent.dxf.insert.y)
            except Exception:
                continue
    except Exception:
        return None
    if len(xs) < _PLAUS_MIN_PONTOS or len(ys) < _PLAUS_MIN_PONTOS:
        return None
    xs.sort(); ys.sort()
    def _p(v, q):
        return v[min(len(v) - 1, int(len(v) * q))]
    return (_p(xs, 0.75) - _p(xs, 0.25), _p(ys, 0.75) - _p(ys, 0.25))


def _unidade_por_plausibilidade(doc, unit_factor: float) -> dict:
    """Última régua: o desenho, na unidade declarada, é fisicamente possível?

    Devolve {'status': 'corrigida_plausibilidade', 'fator_corrigido', 'mensagem'}
    ou {'status': None, 'motivo'}. Nunca lança.
    """
    try:
        nucleo = _nucleo_denso(doc)
        if not nucleo:
            return {"status": None, "motivo": "desenho pequeno demais pra julgar"}
        larg_m, alt_m = nucleo[0] * unit_factor, nucleo[1] * unit_factor
        if not (0 < larg_m < _PLAUS_CORE_MAX_M and 0 < alt_m < _PLAUS_CORE_MAX_M):
            return {"status": None,
                    "motivo": f"núcleo {larg_m:.2f}×{alt_m:.2f} m é plausível"}
        for fator in _CANONICAL_METRIC_FACTORS:
            if fator <= unit_factor:
                continue
            nl, na = nucleo[0] * fator, nucleo[1] * fator
            if (_PLAUS_OK_MIN_M <= nl <= _PLAUS_OK_MAX_M
                    and _PLAUS_OK_MIN_M <= na <= _PLAUS_OK_MAX_M):
                return {
                    "status": "corrigida_plausibilidade",
                    "fator_corrigido": fator,
                    "mensagem": (
                        f"unidade corrigida por PLAUSIBILIDADE: com "
                        f"{_UNIT_FACTOR_NAMES.get(unit_factor, unit_factor)} o "
                        f"desenho inteiro mediria {larg_m:.2f}×{alt_m:.2f} m "
                        f"(impossível); em "
                        f"{_UNIT_FACTOR_NAMES.get(fator, fator)} mede "
                        f"{nl:.1f}×{na:.1f} m. NÃO é prova — quantidades entram "
                        f"como estimado, confira a escala do seu arquivo."),
                }
        return {"status": None,
                "motivo": f"núcleo {larg_m:.3f}×{alt_m:.3f} m sem correção limpa"}
    except Exception as e:
        return {"status": None, "motivo": f"falhou: {type(e).__name__}"}
