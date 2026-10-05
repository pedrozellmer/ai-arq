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
import bisect
import math
import os
import re
import statistics
import subprocess
import sys
import tempfile
import unicodedata
from bisect import bisect_left, bisect_right
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
    # 🩸 26/09/2026 (job 32a27efc): quantas das `count` inserções são o SÍMBOLO
    # desenhado na legenda da prancha, não peça (ver `amostras_de_legenda`).
    # Continuam contadas: o selo é que não pode sair "medido" (main.py).
    amostras_legenda: int = 0
    # 30/09/2026: {layer: inserções}. `layer` é o da PRIMEIRA inserção; a régua
    # da marca de anotação decide pela MAIORIA (sprinkler: X3 = 82 no SPK e 3
    # no 0-PILAR — a primeira podia ser a do pilar).
    camadas: dict = field(default_factory=dict)


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
    # 🩸 27/09/2026 — faixa fina em layer de parede: a ESPESSURA da parede
    # cortada na planta, não uma superfície (ver `_hachura_e_secao_de_parede`).
    secao_de_parede: bool = False


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

    def get_layers_secao_de_parede(self) -> set:
        """Layers cuja área hachurada é, em ≥ 80%, SEÇÃO de parede cortada.

        🩸 27/09/2026 — a soma desses layers é a espessura da parede na planta,
        não superfície: não prova m² nenhum (a chave do selo não usa) e a IA
        é avisada no rótulo. Ver `_hachura_e_secao_de_parede`."""
        tot: dict[str, float] = defaultdict(float)
        sec: dict[str, float] = defaultdict(float)
        for h in self.hatches:
            tot[h.layer] += h.area
            if getattr(h, "secao_de_parede", False):
                sec[h.layer] += h.area
        return {ly for ly, a in tot.items() if a > 0 and sec[ly] >= 0.8 * a}

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

    #: registros de máquina que a IA NÃO lê crus (vão ditos em português)
    _METADADOS_FORA_DO_PROMPT = frozenset({"copias_sombra", "planta_repetida",
                                           # 30/09: ditos nas seções próprias
                                           "objetos_sem_bloco", "layers_de_cota",
                                           "layers_de_borda",
                                           # 30/09 (H10): o comprimento já está
                                           # no layer; isto é registro do log
                                           "splines_medidas",
                                           # 30/09 (H34): dito na linha do layer
                                           "tubos_em_face_dupla",
                                           # 01/10 (H76): idem
                                           "layers_contorno_de_peca",
                                           # 01/10 (H79): idem
                                           "layers_moldura_ou_limite",
                                           # 02/10 (H88): idem
                                           "layers_esteira_por_travessa",
                                           # 04/10 (E14): idem
                                           "layers_grade_de_tabela",
                                           # 05/10 (E07): idem
                                           "layers_em_faixa",
                                           # 01/10 (H84): rastro; a soma já é 1×
                                           "copias_exatas",
                                           # 30/09 (H13): seção própria
                                           "pecas_no_vinculo",
                                           # 02/10 (H94): rastro; a prova já vai
                                           # em `unidade_provada_por_rotulo`
                                           "prova_por_rotulo_de_comodo",
                                           # 04/10 (E12): dito na linha do layer
                                           "parede_espessa_pelas_faces"})

    def to_structured_prompt(self) -> str:
        """Converts extraction to a structured text prompt for Claude."""
        lines: list[str] = []
        lines.append(f"=== DADOS EXTRAÍDOS DO DXF: {self.filename} ===\n")

        # Metadata
        if self.metadata:
            lines.append("METADADOS DO ARQUIVO:")
            for k, v in self.metadata.items():
                # 🩸 29/09: o registro do detector de cópias, cru, fazia a IA
                # duvidar de TODA contagem ("~35 por planta" nas 70 luminárias
                # que eram 70). Vai dito em português, logo abaixo.
                if k in self._METADADOS_FORA_DO_PROMPT:
                    continue
                lines.append(f"  {k}: {v}")
            lines.append("")

        # 🩸 29/09/2026 (caso 18c57c3c): com as vistas aplicadas, a IA via só o
        # dicionário cru dos metadados e escrevia "confirmar se a contagem já
        # está deduplicada" na tomada e "pode estar inflada" nos quadros — que o
        # motor já tinha contado 1× (11 → 7). Dito em português, como a folha.
        _vb = (self.metadata or {}).get("vistas_da_mesma_base") or {}
        if _vb.get("aplicada"):
            _rep = _vb.get("repetidos") or {}
            _saiu = ", ".join("%s de '%s'" % (n, k) for k, n in list(_rep.items())[:8])
            lines.append(
                "VISTAS DA MESMA PLANTA (as contagens abaixo JÁ refletem isto): o arquivo desenha "
                "o mesmo pavimento em %s vistas temáticas. A peça que aparece em mais de uma "
                "vista, no mesmo ponto, já foi contada UMA vez%s. NÃO desconte de novo e NÃO "
                "escreva que a contagem pode estar inflada ou duplicada por causa das vistas."
                % (_vb.get("vistas"), (" (saíram as repetições: %s)" % _saiu) if _saiu else ""))
            lines.append("")

        # 🩸 29/09/2026 (job 6437838e): a planta repetida no modelo, dita em
        # português — QUAIS tipos estão nas cópias. Com o dicionário cru, a IA
        # rebaixou as 70 luminárias da vista de iluminação (que só existem lá)
        # e escreveu "estimativa: ~35 un por planta".
        _pr_md = self.metadata or {}
        _cp = _pr_md.get("copias_sombra") or {}
        _tc = _cp.get("tipos_copiados") or _cp.get("nomes") or {}
        if _pr_md.get("planta_repetida") and _tc:
            _nomes_cp = list(_tc)
            lines.append(
                "PLANTA REPETIDA NO MODELO: a mesma planta-base aparece desenhada mais de uma "
                "vez neste arquivo (uma cópia por prancha, ou um andar por cópia). Estes tipos "
                "de bloco têm peças NAS CÓPIAS, e a contagem deles soma as cópias: %s%s. Use a "
                "contagem como ela está — NÃO divida e NÃO estime 'por planta': o motor marca "
                "essas linhas como estimativa e explica ao cliente. Os DEMAIS tipos de bloco "
                "aparecem numa cópia só: a contagem deles vale como está. Comprimento de layer e "
                "área de hachura deste arquivo somam as cópias."
                % (", ".join("'%s'" % n for n in _nomes_cp[:20]),
                   " (e mais %d)" % (len(_nomes_cp) - 20) if len(_nomes_cp) > 20 else ""))
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
            # 28/09: e o grosso do desenho está nas vistas — ver `_o_conteudo_e_das_vistas`
            if _vis and not _planta1 and not _mult and _o_conteudo_e_das_vistas(_fl):
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
                        f"{_nota_da_legenda(getattr(b, 'amostras_legenda', 0))}"
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
                # 26/09 (job 32a27efc): o símbolo da legenda vai na MESMA linha
                _amo_nome = Counter()
                for b in self.blocks:
                    _amo_nome[b.name] += getattr(b, "amostras_legenda", 0) or 0
                _amo_grupo = Counter()
                # a raiz: receita em engine_rules — as regras que casam o nome
                # citado pela IA usam a MESMA (29/09)
                from engine_rules import raiz_do_nome_do_bloco as _raiz_bloco
                from engine_rules import e_vinculo_de_modelo as _e_vinc_nome
                for name, count in other.items():
                    a = _assin.get(name, "")
                    # 🩸 30/09/2026 (H60 do estudo do acervo): "CONDOMINIO X - TORRE
                    # _vinculo__rvt-1-TORRE B" — a raiz corta no " - " e o "_rvt"
                    # some: o vínculo COM conteúdo (tem assinatura) saía "CONDOMINIO X
                    # (tipo 1): 1 un" SEM a marca, e só o vazio era marcado. Uma
                    # entrega saiu "7 un ✓". Nome de vínculo não junta pela raiz.
                    if a and _e_vinc_nome(name):
                        a = ""
                    # 🚨 DOIS formatos de fragmentacao, medidos em arquivo real:
                    #  a) Revit/ArchiCAD: "CHUVEIRO - CHUVEIRO-1320392-PORTARIA"
                    #     (FAMILIA - TIPO-<id>-<vista>). Nas pranchas da cliente-16
                    #     os nomes tinham 55 a 61 caracteres e eram 1.570 -- so
                    #     essa secao dava 99.901 chars. Agrupar pela FAMILIA
                    #     derruba pra 17.464 (-83%).
                    #  b) sufixo do conversor: "Viga_12_1" -> "Viga".
                    raiz = _raiz_bloco(name)
                    chave = (raiz, a) if a else (name, "")
                    _amo_grupo[chave] += _amo_nome[name]
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
                from engine_rules import e_vinculo_de_modelo as _vinc
                from engine_rules import nota_de_bloco_de_anotacao as _anotacao
                # 30/09: os layers das inserções, pra régua decidir pela maioria
                _camadas_bloco = {b.name: getattr(b, "camadas", None)
                                  for b in (self.blocks or [])}
                # 🩸 29/09/2026 (caso 18c57c3c): o mesmo bloco com ATRIBUTO diferente
                # por inserção — 'DISJ-3F' 4 un, 2 com 63A=63A e 2 com 63A=D-32A. A
                # lista de atributos (mais abaixo) junta as linhas iguais sem dizer
                # quantas, e a planilha saiu "63A" nos 4 (noutra rodada, "×1" cada).
                # A quebra vai AQUI, na linha da contagem da PEÇA — não na lista de
                # atributos, onde a mesma etiqueta de área escrita 2× viraria área
                # dobrada. Só quando o bloco tem 2+ valores e a quebra soma a
                # contagem (depois das vistas, 11 inserções viram 7 peças: não bate).
                # 🪤 E só quando o atributo é TIPO de peça: no acervo, a etiqueta de
                # área ('area' 5 un, uma sala e seus m² em cada), a marca de nível
                # (COTAV 94 un, 19 cotas) e o ponto topográfico ganhavam a quebra — e
                # "separe por valor" viraria uma linha por sala. Tipo se REPETE (no
                # máximo metade de valores distintos) e não é MEDIDA (decimal).
                _attr_por_bloco: dict = {}
                _attr_medida: set = set()
                for _ba in (getattr(self, "block_attributes", None) or []):
                    _cps = _ba.get("campos") or {}
                    _l_ba = "; ".join(f"{k}={v}" for k, v in _cps.items())
                    _attr_por_bloco.setdefault(_ba.get("bloco", ""), Counter())[_l_ba] += 1
                    if any(re.match(r"^[+-]?\d+[.,]\d+$", str(v).strip()) for v in _cps.values()):
                        _attr_medida.add(_ba.get("bloco", ""))
                for (_r, _a), (count, n_nomes, rotulo) in sorted(
                        _grupos.items(), key=lambda x: -x[1][0]):
                    _qa = _attr_por_bloco.get(rotulo)
                    _nota_attr = ""
                    if _qa and len(_qa) >= 2 and sum(_qa.values()) == count \
                            and 2 * len(_qa) <= count and rotulo not in _attr_medida:
                        _nota_attr = ("  [atributo por inserção: "
                                      + " · ".join(f"{_l[:40]} ×{_n}" for _l, _n in _qa.most_common(4))
                                      + (f" · +{len(_qa) - 4} valor(es)" if len(_qa) > 4 else "")
                                      + " — separe por valor; não descreva todas com um valor só]")
                    _nota_anot = _anotacao(rotulo, _a, _camadas_bloco.get(rotulo))
                    if _quantos_por_raiz.get(_r, 1) > 1 and _a:
                        _seq[_r] = _seq.get(_r, 0) + 1
                        rotulo = f"{rotulo} (tipo {_seq[_r]})"
                    _nota = f"  [{n_nomes} nomes do conversor, mesma peca]" if n_nomes > 1 else ""
                    _nota += _nota_attr
                    _nota += _nota_da_legenda(_amo_grupo[(_r, _a)])
                    # 🩸 29/09 (caso 18c57c3c): marca de fiação e nuvem de revisão
                    _nota += _nota_anot
                    if _vinc(rotulo):
                        _nota += ("  ⚠ VÍNCULO DE MODELO (outro arquivo do Revit/IFC colado "
                                  "como bloco) — NÃO é peça: não conte como quantidade")
                        # 🪤 30/09 (H13): o "o conteúdo está abaixo" ia em CADA linha
                        # de vínculo — 152 linhas num pavimento, 2/3 do que a seção
                        # acrescentava, e apontava também pras vistas NÃO somadas.
                        # Vai uma vez, no cabeçalho da seção.
                    lines.append(f"  {rotulo}: {count} un{_nota}")
                if _juntados:
                    lines.append(f"  ({_juntados} grupo(s) tinham nomes duplicados pelo "
                                 f"conversor e foram somados — so quando a definicao "
                                 f"geometrica e IDENTICA. 'tipo 1/2/3' sao pecas "
                                 f"DIFERENTES com o mesmo nome de origem.)")
                lines.append("")

        # 🩸 30/09/2026 (H13): o vínculo do Revit da MESMA disciplina traz o
        # próprio projeto — as peças de dentro, ditas uma vez por instância
        _pv = (self.metadata or {}).get("pecas_no_vinculo") or {}
        if _pv:
            lines.append(
                "PEÇAS DENTRO DO VÍNCULO DO REVIT DA MESMA DISCIPLINA (o arquivo traz o PRÓPRIO "
                "projeto dentro do bloco de vínculo; contadas UMA vez por instância, só na vista "
                "de PLANTA). Contagem SEM selo: marque 'estimado' e escreva 'vínculo' na "
                "observação. A FASE está no nome da peça (DEMOLIR / A DEMOLIR / EXISTENTE / "
                "NOVO) e decide o serviço: peça a DEMOLIR é demolição/retirada — nunca "
                "fornecimento e instalação; EXISTENTE não se compra. Na CONTAGEM DE BLOCOS "
                "estes vínculos aparecem como '⚠ VÍNCULO DE MODELO': o conteúdo deles é ESTE.")
            for _base, _d in sorted(_pv.items(), key=lambda kv: -sum(kv[1]["pecas"].values())):
                _outras = _d.get("outras_vistas") or []
                lines.append(f"  • {_base} ({_d['disciplina']}, {_d['instancias']} instância(s), "
                             f"vista: {_d.get('vista', '')}"
                             + (f"; outras vistas da mesma base NÃO somadas: {', '.join(_outras)}"
                                if _outras else "") + "):")
                for _nome, _n in _d["pecas"].items():
                    lines.append(f"      {_nome}: {_n} un")
                _nl = _d.get("nao_listadas") or {}
                if _nl.get("tipos"):
                    lines.append(f"      (e mais {_nl['pecas']} peça(s) em {_nl['tipos']} tipo(s) "
                                 f"não listados — a lista acima são os maiores)")
            lines.append("")

        # 🩸 30/09/2026 (job 9a2c5d87) — a peça desenhada UMA A UMA, sem bloco:
        # os 776 blocos de alvenaria e os 787 furos de graute eram retângulos, e
        # a IA só via o comprimento do layer (a soma das bordas).
        _obj_sb = (self.metadata or {}).get("objetos_sem_bloco") or {}
        if _obj_sb:
            lines.append("OBJETOS DESENHADOS PEÇA POR PEÇA (sem bloco — contagem DETERMINÍSTICA "
                         "feita no arquivo: retângulo ou círculo do MESMO tamanho, repetido):")
            for _ly_sb, _pecas in sorted(_obj_sb.items(), key=lambda kv: -max(p["n"] for p in kv[1])):
                _desc = []
                for _p in _pecas[:6]:
                    if _p.get("forma") == "círculo":
                        _d1 = "%d círculos de raio %s cm" % (_p["n"], ("%g" % _p["r_cm"]).replace(".", ","))
                    else:
                        _d1 = "%d retângulos de %s × %s cm" % (
                            _p["n"], ("%g" % _p["a_cm"]).replace(".", ","), ("%g" % _p["b_cm"]).replace(".", ","))
                    if _p.get("concentrada"):
                        _d1 += " (todas num canto do desenho: provável LEGENDA ou DETALHE, não obra)"
                    _desc.append(_d1)
                lines.append(f"  {_ly_sb}: " + " · ".join(_desc))
            lines.append("  (O que cada peça é — bloco de alvenaria, placa, furo, luminária — sai da "
                         "legenda e das notas: diga isso na observação. A CONTAGEM é a quantidade da "
                         "peça; marque 'estimado'. O comprimento destas camadas é a soma das bordas "
                         "das peças, não um elemento linear.)")
            if (self.metadata or {}).get("planta_repetida"):
                lines.append("  ⚠ A PLANTA APARECE REPETIDA neste desenho: estas contagens podem somar "
                             "as cópias. Use o número como está, marque 'estimado' e escreva isso na "
                             "observação — NÃO divida e NÃO estime 'por planta'.")
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
            _cinza = (self.metadata or {}).get("parede_zona_cinza") or {}
            # 🩸 30/09 (job 9a2c5d87): o layer que É cota explodida (pela prova do
            # desenho, não pelo nome) e o que é só a borda das peças repetidas
            _cota_ly = (self.metadata or {}).get("layers_de_cota") or {}
            _borda_ly = (self.metadata or {}).get("layers_de_borda") or {}
            _tubo_fd = (self.metadata or {}).get("tubos_em_face_dupla") or {}
            _ctp = (self.metadata or {}).get("layers_contorno_de_peca") or {}
            _mol = (self.metadata or {}).get("layers_moldura_ou_limite") or {}
            _est = (self.metadata or {}).get("layers_esteira_por_travessa") or {}
            _tab = (self.metadata or {}).get("layers_grade_de_tabela") or {}
            _fx = (self.metadata or {}).get("layers_em_faixa") or {}
            _esp = (self.metadata or {}).get("parede_espessa_pelas_faces") or {}
            for layer, length in sorted(walls_by_layer.items()):
                if layer in _est and not _anot(layer):
                    # 🩸 02/10 (H88) — sem "layer <palavra>" no texto (ver abaixo)
                    lines.append(f"  {layer}: {length:.2f} m"
                                 f"   ⚠ ROLETES/TRAVESSAS — {int(100 * float(_est[layer].get('fracao') or 0))}% "
                                 f"deste comprimento são peças curtas (~{_est[layer].get('peca_m')} m: "
                                 f"roletes, travessas, caixas) SOLTAS ou LADO A LADO em escada, "
                                 f"não o comprimento da esteira: não use como medido")
                elif layer in _mol and not _anot(layer):
                    # 🩸 01/10 (H79) — sem "layer <palavra>" no texto (ver abaixo)
                    lines.append(f"  {layer}: {length:.2f} m"
                                 f"   ⚠ MOLDURA OU LIMITE — {int(100 * float(_mol[layer].get('fracao') or 0))}% "
                                 f"deste comprimento são LADOS DE RETÂNGULOS grandes (moldura "
                                 f"da folha, limite de obra ou de lote), não rede nem elemento "
                                 f"de obra: não use como medido")
                elif layer in _tab and not _anot(layer):
                    # 🩸 04/10 (E14) — sem "layer <palavra>" no texto (ver abaixo)
                    lines.append(f"  {layer}: {length:.2f} m"
                                 f"   ⚠ GRADE DE TABELA — {int(100 * float(_tab[layer].get('fracao') or 0))}% "
                                 f"deste comprimento são as LINHAS DE UMA TABELA desenhada "
                                 f"(legenda, simbologia ou quadro: '{_tab[layer].get('cabecalho')}'), "
                                 f"não rede nem elemento de obra: não use como medido")
                elif layer in _fx and not _anot(layer):
                    # 🩸 05/10 (E07) — sem "layer <palavra>" no texto (ver abaixo)
                    lines.append(f"  {layer}: {length:.2f} m"
                                 f"   ⚠ FAIXA DE ~{_fx[layer].get('linhas')} LINHAS PARALELAS a "
                                 f"{_fx[layer].get('passo_mm')} mm (preenchimento) — "
                                 f"{int(100 * float(_fx[layer].get('fracao') or 0))}% deste comprimento: "
                                 f"a soma conta cada linha da faixa (~{_fx[layer].get('linhas')}× o "
                                 f"trecho), não é medida: trate como ESTIMADO")
                elif layer in _ctp and not _anot(layer):
                    # 🩸 01/10 (H76) — sem "layer <palavra>" no texto (ver abaixo)
                    lines.append(f"  {layer}: {length:.2f} m"
                                 f"   ⚠ CONTORNO DE PEÇA — é a soma do desenho de "
                                 f"{_ctp[layer].get('insercoes')} peças em bloco "
                                 f"(~{_ctp[layer].get('m_por_insercao')} m cada: conexões, "
                                 f"conduletes, caixas), NÃO comprimento de rede: não use "
                                 f"como metro, use a CONTAGEM das peças")
                elif layer in _cota_ly and not _anot(layer):
                    _n_anot += 1
                    lines.append(f"  {layer}: {length:.2f} m"
                                 f"   ⚠ ANOTAÇÃO DO DESENHO — são LINHAS DE COTA "
                                 f"({_cota_ly[layer].get('cotas')} com o valor escrito ao lado): "
                                 f"NÃO é elemento de obra, não use como quantidade")
                elif layer in _tubo_fd and not _anot(layer):
                    _dfd = ", ".join("ø%d" % d for d in (_tubo_fd[layer].get("diametros_mm") or [])[:5])
                    # 01/10 (H75): o eletroduto não tem ø escrito — a distância é a MEDIDA
                    _el = bool(_tubo_fd[layer].get("eletroduto"))
                    lines.append(f"  {layer}: {length:.2f} m"
                                 f"   ⚠ {'ELETRODUTO' if _el else 'TUBO'} EM FACE DUPLA — são as "
                                 f"DUAS paredes de cada {'eletroduto' if _el else 'tubo'} "
                                 f"({int(100 * float(_tubo_fd[layer].get('fracao') or 0))}% em par; "
                                 f"{'distância medida entre as paredes' if _el else 'diâmetros em par'}: "
                                 f"{_dfd}): o comprimento do {'eletroduto' if _el else 'tubo'} "
                                 f"(eixo) é cerca da METADE deste número — não use como medido")
                elif layer in _borda_ly and not _anot(layer):
                    lines.append(f"  {layer}: {length:.2f} m"
                                 f"   ⚠ BORDAS das peças repetidas listadas em OBJETOS "
                                 f"DESENHADOS PEÇA POR PEÇA — é perímetro de peça, não "
                                 f"elemento linear: use a CONTAGEM")
                elif _anot(layer):
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
                elif layer in _cinza:
                    lines.append(f"  {layer}: {length:.2f} m   ⚠ PAREDE EM PARTE EM DUAS "
                                 f"LINHAS ({_cinza[layer]:.0%} do traçado em pares de face): "
                                 f"esta soma pode contar as duas faces — trate como "
                                 f"ESTIMADO, confira o comprimento no projeto")
                elif layer in _esp:
                    # 🩸 04/10 (E12) — sem "layer <palavra>" no texto (ver acima);
                    # sem número de "comprimento certo": a IA o copiaria com ✓
                    lines.append(f"  {layer}: {length:.2f} m   ⚠ PAREDE ESPESSA PELAS DUAS FACES — "
                                 f"há paredes de MAIS de 40 cm (perímetro, muro, contenção) "
                                 f"desenhadas pelas duas faces, e esta soma conta as DUAS "
                                 f"(pelo menos {int(100 * float(_esp[layer].get('fracao') or 0))}% "
                                 f"desta soma é a face a mais): o comprimento das paredes é "
                                 f"MENOR — trate como ESTIMADO, não use como medido")
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
            _secoes = self.get_layers_secao_de_parede()
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
                if layer in _secoes:
                    lines.append(f"  {layer}: {area:.2f} m²   ⚠ SEÇÃO DE PAREDE CORTADA — "
                                 f"é a ESPESSURA da parede preenchida na planta, NÃO é "
                                 f"superfície: não use como m² de parede, drywall ou "
                                 f"revestimento (o comprimento da parede está em "
                                 f"COMPRIMENTOS POR LAYER)")
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
# igualmente grave (regra nº1). Parede também é desenhada com duas linhas; até
# 26/09 ficou de fora de propósito ("mudaria todo projeto de arquitetura que
# hoje funciona"). Medido naquele dia: não funcionava — a parede saía 1,5–2×.
# Agora ela usa esta máquina em `_corrigir_parede_linha_dupla`.
# 25/09: leito de cabos, eletrocalha e bandeja são desenhados do mesmo jeito
# (as duas bordas). "eletroduto" continua de fora: é linha ÚNICA.
# 🩸 30/09 (H34 do estudo do acervo): o Revit exporta o duto como
# "M-HVAC-DUCT", em INGLÊS, com as duas faces — "ducto" (espanhol) não casava
# e o layer somava as duas bordas (acervo: 1.423 m de face → 903 m de eixo).
# A trava de letra antes do nome segura "conduct"/"product".
_RE_DUTO_DUPLO = re.compile(
    r"(?<![a-z])(?:duto|ducto|duct|leito|eletrocalha|bandeja)", re.IGNORECASE)

_DUTO_ANG_TOL = 3.0      # graus: paralelas de verdade
_DUTO_SEP_MIN = 0.05     # m: abaixo disso é a mesma linha repetida, não um par
_DUTO_SEP_MAX = 1.50     # m: acima disso não é seção de duto, são redes distintas
_DUTO_MIN_SEG = 0.25     # m: trecho menor é legenda/símbolo, não rede
_DUTO_MAX_SEG_LAYER = 3000   # teto anti-O(n²) por layer


_RE_LEGENDA_LINHA_DUPLA = re.compile(
    r"\b(?:leitos?|eletrocalhas?|bandejas?|calhas?|dutos?|ductos?)\b")
#: 🩸 29/09/2026 (job 35146640): a amostra de "ELETROCALHA LISA COM TAMPA" da
#: legenda estava no layer "0" — o padrão do AutoCAD, onde cai de tudo (base,
#: moldura, diagrama). O motor disse à IA "layer 0 = eletrocalha" e a planilha
#: saiu com 3.678 m de eletrocalha: o layer 0 inteiro. Layer genérico não diz
#: o que a peça é — e medir o layer inteiro pelo eixo cortaria a parede também.
_LAYERS_GENERICOS = frozenset({"0", "DEFPOINTS"})


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
                if str(lay).strip().upper() in _LAYERS_GENERICOS:
                    continue                    # layer 0: cai de tudo (ver acima)
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


def _menos_intervalos(livre, tira):
    """Os intervalos de `livre` sem os de `tira` (listas de (início, fim))."""
    for x0, x1 in tira:
        novo = []
        for a, b in livre:
            if x1 <= a or x0 >= b:
                novo.append((a, b))
                continue
            if a < x0:
                novo.append((a, x0))
            if x1 < b:
                novo.append((x1, b))
        livre = novo
        if not livre:
            break
    return livre


def _funde_intervalos(iv):
    """Ordena e junta os intervalos que se tocam ou se sobrepõem."""
    out = []
    for a, b in sorted(iv):
        if out and a <= out[-1][1]:
            if b > out[-1][1]:
                out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    return out


def _recorta_intervalos(iv, inicios, lo, hi):
    """Os intervalos de `iv` (ordenados e fundidos; `inicios` = os começos) que
    tocam (lo, hi), recortados a ele — por busca binária, sem varrer a lista."""
    import bisect
    j = max(0, bisect.bisect_right(inicios, lo) - 1)
    out = []
    while j < len(iv) and iv[j][0] < hi:
        a, b = iv[j]
        if b > lo:
            out.append((max(a, lo), min(b, hi)))
        j += 1
    return out


def _intersecao_intervalos(a_, b_):
    """Os trechos comuns a duas listas de intervalos ORDENADAS e sem
    sobreposição — dois ponteiros, O(n + m)."""
    out, i, j = [], 0, 0
    while i < len(a_) and j < len(b_):
        lo, hi = max(a_[i][0], b_[j][0]), min(a_[i][1], b_[j][1])
        if hi > lo:
            out.append((lo, hi))
        if a_[i][1] < b_[j][1]:
            i += 1
        else:
            j += 1
    return out


class _EspessaGrandeDemais(Exception):
    """O layer passou do teto de comparações da régua da parede grossa."""


def _sobra_das_faces_espessas(grupos_geo, em_par, sep_max, esp_max, min_sobrep, max_comparacoes=None):
    """{trecho: comprimento CRU que sobra na soma} — as duas faces de uma parede
    mais grossa que a seção da régua (ver `_PAREDE_ESPESSA_MAX_M`).

    Par = duas paralelas do mesmo grupo de direção a `sep_max`–`esp_max` uma da
    outra e sobrepostas em pelo menos `min_sobrep` (pilarete e ponta não
    entram). `em_par`: {trecho: [(início, fim, lado)]} de onde o eixo pareou a
    linha — lado +1, o par dela está ACIMA (d maior); −1, ABAIXO. Do par (a
    embaixo, b em cima) conta o trecho sobreposto em que:
    - nenhuma das duas está pareada com linha de FORA da faixa (a pra baixo, b
      pra cima): aí ela é face de outra parede;
    - as duas não estão pareadas pra DENTRO ao mesmo tempo: são duas paredes
      finas com um vão entre elas (o shaft).
    🩸 04/10 (revisão da Projetos): a linha paralela DENTRO da faixa —
    revestimento, isolamento — não desarma mais. Antes ela pareava com a face
    (a 5–25 cm) ou cortava o par "no meio", e o perímetro de 50 cm escapava.
    Cada face entra em um par só, o mais estreito primeiro. A sobra de um par é
    o trecho sobreposto (as duas faces somam 2×, o eixo seria 1×), metade em
    cada linha. 🪤 A linha de dentro também fica na soma e não entra aqui: a
    sobra sai por BAIXO do que a soma tem a mais.
    Levanta `_EspessaGrandeDemais` acima de `max_comparacoes` — quem chama
    segura (a marca não é medida; o eixo segue).
    🐢 04/10 (2ª revisão da Projetos): o eixo grava UM intervalo por fatia entre
    cortes (os cortes são as pontas de TODAS as paralelas do grupo), e a 1ª
    versão cruzava as listas cruas em produto cartesiano: num layer de 5.840
    trechos com corredores de 100 m, 54,7 s contra 0,2 s antes. Agora os
    intervalos de cada lado são fundidos uma vez, recortados ao trecho do
    candidato por busca binária, cruzados por dois ponteiros — e tudo entra no
    contador do teto.
    """
    from collections import defaultdict as _dd
    sobra = _dd(float)
    teto = max_comparacoes or _PAREDE_ESPESSA_MAX_COMPARACOES
    n = 0
    # por linha: (abaixo, começos, acima, começos), fundidos — só das linhas
    # que entram em algum par candidato, na primeira vez que entram
    lados = {}

    def _lados(k):
        if k not in lados:
            ivs = em_par.get(k, ())
            _ab = _funde_intervalos([(x, y) for x, y, lado in ivs if lado < 0])
            _ac = _funde_intervalos([(x, y) for x, y, lado in ivs if lado > 0])
            lados[k] = (_ab, [p[0] for p in _ab], _ac, [p[0] for p in _ac])
        return lados[k]
    for por_d, d, t0, t1 in grupos_geo:
        cands = []
        for a_pos, a in enumerate(por_d):
            for b_pos in range(a_pos + 1, len(por_d)):
                n += 1
                if n > teto:
                    raise _EspessaGrandeDemais("mais de %d comparações" % teto)
                b = por_d[b_pos]
                sep = d[b] - d[a]
                if sep > esp_max:
                    break
                if sep < sep_max:
                    continue
                lo, hi = max(t0[a], t0[b]), min(t1[a], t1[b])
                if hi - lo >= min_sobrep:
                    cands.append((sep, a_pos, b_pos, lo, hi))
        usado = _dd(list)
        for _sep, a_pos, b_pos, lo, hi in sorted(cands):
            a, b = por_d[a_pos], por_d[b_pos]
            ab_a, ia_a, ac_a, ic_a = _lados(a)
            ab_b, ib_b, ac_b, ic_b = _lados(b)
            livre = [(lo, hi)]
            # a pareada pra BAIXO e b pareada pra CIMA: face de outra parede
            fora = _recorta_intervalos(ab_a, ia_a, lo, hi) + _recorta_intervalos(ac_b, ic_b, lo, hi)
            n += len(fora)
            livre = _menos_intervalos(livre, _funde_intervalos(fora))
            if livre:
                # as duas pareadas pra DENTRO: duas paredes finas com um vão (shaft)
                dentro_a = _recorta_intervalos(ac_a, ic_a, lo, hi)
                dentro_b = _recorta_intervalos(ab_b, ib_b, lo, hi)
                n += len(dentro_a) + len(dentro_b)
                livre = _menos_intervalos(livre, _intersecao_intervalos(dentro_a, dentro_b))
            for k in (a, b):
                if livre:
                    _u = [iv for iv in usado[k] if iv[1] > lo and iv[0] < hi]
                    n += len(usado[k])
                    livre = _menos_intervalos(livre, _u)
            if n > teto:
                raise _EspessaGrandeDemais("mais de %d comparações" % teto)
            tot = sum(y - x for x, y in livre)
            if tot <= 0:
                continue
            for k in (a, b):
                usado[k] = _funde_intervalos(usado[k] + livre)
                sobra[k] += tot / 2.0
    return sobra


def _corrigir_duto_linha_dupla(walls, unit_factor: float = 1.0, layers_extra=None,
                               escolhe=None, sep_max_m=None, min_seg_m=None,
                               min_fracao_par=None, zona_cinza=None,
                               junta_face_fina=False, max_seg=None, faces_espessas=None):
    """Troca a soma das duas faces pelo comprimento do EIXO, em layer de duto.

    `layers_extra`: layers que a LEGENDA da prancha diz serem leito/duto
    desenhado em duas linhas (ver `_legenda_de_linha_dupla`) — o nome do layer
    não precisa dizer.
    `junta_face_fina`: linhas a até `_DUTO_SEP_MIN` uma da outra, no mesmo
    trecho, são UMA face (o reboco da parede composta) — ver
    `_corrigir_parede_linha_dupla`.
    `escolhe` (layer → bool), `sep_max_m` e `min_seg_m` trocam QUEM entra, a
    seção máxima e o menor lado que ainda entra no pareamento/tampa — é como a
    PAREDE usa esta mesma máquina (ver `_corrigir_parede_linha_dupla`).
    `min_fracao_par`: o layer só é corrigido se pelo menos essa fração do
    comprimento dele estiver em par (a convenção DO LAYER é linha dupla).
    `faces_espessas` (dict, saída): {índice em `walls`: metros da sobra} das
    faces sem par a `sep_max`–`_PAREDE_ESPESSA_MAX_M` — só registro, nenhuma
    soma muda (ver `_sobra_das_faces_espessas`).

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
            if (escolhe(lay) if escolhe else (lay in extra or _RE_DUTO_DUPLO.search(lay))):
                por_layer[w.layer].append(i)
        if not por_layer:
            return walls, "", ""

        sep_min = _DUTO_SEP_MIN / uf                                  # em bruto
        sep_max = (sep_max_m if sep_max_m else _DUTO_SEP_MAX) / uf
        min_seg = min_seg_m if min_seg_m else _DUTO_MIN_SEG           # em metro
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
                if getattr(w, "curvo", False) or getattr(w, "length", 0) < min_seg:
                    continue
                pts = getattr(w, "pontos", ()) or ()
                if len(pts) >= 2:
                    for p, q in zip(pts, pts[1:]):
                        if len(p) > 2 and p[2]:
                            continue            # lado em arco: fora (ressalva)
                        if (p[0], p[1]) != (q[0], q[1]) and math.hypot(q[0] - p[0], q[1] - p[1]) * uf >= min_seg:
                            sub.append((i, (p[0], p[1]), (q[0], q[1])))
                elif tuple(w.start) != tuple(w.end):
                    sub.append((i, tuple(w.start), tuple(w.end)))
            if len(sub) < 2 or len(sub) > (max_seg or _DUTO_MAX_SEG_LAYER):
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
            perda = _dd(float)          # índice -> comprimento BRUTO que sai da soma
            # E12: onde cada linha ficou em par (pra achar a parede grossa sem par)
            em_par = _dd(list) if faces_espessas is not None else None
            grupos_geo = []
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
                if em_par is not None:
                    grupos_geo.append((por_d, d, t0, t1))
                viz = _dd(set)
                fino = _dd(set)         # a ≤ sep_min e se olhando: mesma face
                for a_pos, a in enumerate(por_d):
                    for b in por_d[a_pos + 1:]:
                        sep = d[b] - d[a]
                        if sep >= sep_max:
                            break
                        sobrep = min(t1[a], t1[b]) - max(t0[a], t0[b])
                        olha = sobrep > 0 and sobrep >= 0.5 * min(t1[a] - t0[a], t1[b] - t0[b])
                        if sep <= sep_min:
                            if junta_face_fina and olha:
                                fino[a].add(b)
                                fino[b].add(a)
                            continue
                        if olha:
                            viz[a].add(b)
                            viz[b].add(a)
                if not viz:
                    continue
                cand = set(viz) | set(fino)
                cortes = sorted({t for i in cand for t in (t0[i], t1[i])})
                for ta, tb in zip(cortes, cortes[1:]):
                    if tb - ta <= 0:
                        continue
                    tm = (ta + tb) / 2.0
                    ativos = sorted((i for i in cand if t0[i] <= tm <= t1[i]), key=lambda i: d[i])
                    # 🩸 01/10/2026 (H73 do estudo do acervo): a parede COMPOSTA
                    # do Revit vem em 4 linhas — face, reboco (2–5 cm), bloco,
                    # reboco, face. O reboco fica abaixo de `sep_min`, então
                    # só as duas do meio pareavam e as faces somavam inteiras:
                    # "Alvenaria 1.419,73 ml ✓" numa escola de ~363 m (3,9×).
                    # A linha a ≤ sep_min da vizinha é a MESMA face; a face
                    # pareada conta meio metro por metro, dividido entre as
                    # linhas dela. Sem `junta_face_fina` cada face é 1 linha:
                    # o pareamento de antes, igual.
                    faces = []
                    for i in ativos:
                        if faces and any(j in fino[i] for j in faces[-1]):
                            faces[-1].append(i)
                        else:
                            faces.append([i])
                    k = 0
                    while k + 1 < len(faces):
                        fa, fb = faces[k], faces[k + 1]
                        if any(b in viz[a] for a in fa for b in fb):
                            for f_ in (fa, fb):
                                for x in f_:
                                    pareado[x] += tb - ta
                                    perda[x] += (1.0 - 0.5 / len(f_)) * (tb - ta)
                                    if em_par is not None:
                                        # lado do par: +1 acima (x é da face de baixo)
                                        em_par[x].append((ta, tb, 1 if f_ is fa else -1))
                            pares.add((min(fa[0], fb[0]), max(fa[0], fb[0])))
                            k += 2
                        else:
                            k += 1
            if em_par is not None:
                # 🩸 E12 — antes do `if not pares`: o muro SÓ de parede grossa não
                # tem par nenhum e é justamente o que não pode passar calado.
                # 🔒 04/10 (revisão da Projetos): try PRÓPRIO. Uma falha aqui
                # (memória, o teto de comparações) caía no `except` geral desta
                # função, que devolve os walls SEM o eixo de NENHUM layer — as
                # somas voltavam pelas duas faces. Agora só a marca deste layer
                # fica sem medir; o eixo segue.
                try:
                    _sob = _sobra_das_faces_espessas(
                        grupos_geo, em_par, sep_max, _PAREDE_ESPESSA_MAX_M / uf,
                        _PAREDE_ESPESSA_SOBREP_MIN_M / uf)
                    for k, s in _sob.items():
                        faces_espessas[sub[k][0]] = faces_espessas.get(sub[k][0], 0.0) + s * uf
                except Exception as _e12:
                    logger.warning("[parede-espessa] %s: sem a marca (%s)", layer, _e12)
            if not pares:
                continue
            if min_fracao_par:
                _em_par = sum(min(p, math.hypot(seg_b[k][0] - seg_a[k][0], seg_b[k][1] - seg_a[k][1]))
                              for k, p in pareado.items()) * uf
                if bruto <= 0 or _em_par / bruto < min_fracao_par:
                    # 🩸 27/09 (estudo, item 2): entre 15% e o piso, o layer
                    # TEM parede em duas linhas, só não o bastante pro eixo —
                    # a soma pode contar as duas faces (131 m ✓ × 74 pelo
                    # eixo). Fica anotado: sem selo de comprimento.
                    if zona_cinza is not None and bruto > 0 and _em_par / bruto >= 0.15:
                        zona_cinza[layer] = round(float(_em_par / bruto), 2)
                    continue                    # layer de linha ÚNICA: par é coincidência
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
            for k, p in perda.items():
                (ax, ay), (bx, by) = seg_a[k], seg_b[k]
                L = math.hypot(bx - ax, by - ay)
                tira[sub[k][0]] += min(p, L) * uf
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


#: Parede: a seção vai de 5 cm (drywall fino) a 40 cm (alvenaria externa com
#: revestimento). Acima disso não se pareia — são paredes diferentes.
_PAREDE_SEP_MAX = 0.40
#: 🪤 O lado mínimo do duto (25 cm) deixava a PONTA da parede (7–25 cm) e o
#: batente do vão sempre somados: nunca viravam tampa. Na parede, 3 cm.
_PAREDE_MIN_SEG = 0.03
#: A convenção do LAYER decide: com menos da metade do comprimento em par, o
#: layer é de linha ÚNICA e o par que aparece é coincidência (duas paredes
#: vizinhas). Medido no acervo (26/09): os layers de linha dupla têm 52–96% em
#: par; o drywall de um gabarito de cliente — que aprovou a pintura pela soma
#: das linhas — tinha 34%, e ficaria 17% menor.
_PAREDE_MIN_FRACAO_PAR = 0.50
#: 🩸 01/10/2026 — H73b do estudo do acervo. Acima do teto do duto (3.000
#: trechos) o layer é PULADO inteiro: uma escola tinha 3.070 trechos de parede
#: composta no térreo e saía 2.746 m (pelo eixo, 816; o feixe dá 776). Medido:
#: 2 layers de parede em 152 passam de 3.000, e o pareamento de 3.735 trechos
#: leva ~5 s. O de 11 mil trechos levaria 65 s e fica de fora.
_PAREDE_MAX_SEG_LAYER = 6000
#: 🩸 04/10/2026 — E12 da conferência dos danos. A parede de MAIS de 40 cm
#: (perímetro, muro, contenção) não pareia e soma as duas faces inteiras. Num
#: estacionamento, a parede de 50 cm do perímetro pôs ~100 m a mais no layer
#: (347,9 m contra ~218): "Parede de alvenaria 647,88 ml ✓" saiu antes do eixo
#: e o eixo do H73 tirou o layer da zona cinza — a soma voltou a valer ✓ pela
#: chave do selo. As faces sem par a 40 cm–1 m, sobrepostas em ≥ 1 m, viram
#: ressalva do layer (`parede_espessa_na_soma`). SÓ REBAIXA: não dá pra saber,
#: trecho a trecho, se são as faces de uma parede grossa ou duas paredes de
#: linha única com um shaft no meio — marcar a mais custa um ✓; a menos, um ✓
#: errado.
_PAREDE_ESPESSA_MAX_M = 1.00
_PAREDE_ESPESSA_SOBREP_MIN_M = 1.0
#: a ressalva vale com sobra ≥ 5 m E ≥ 5 % da soma do layer (ponta e chanfro
#: de parede composta ficam abaixo)
_PAREDE_ESPESSA_SOBRA_MIN_M = 5.0
_PAREDE_ESPESSA_FRACAO_MIN = 0.05
#: teto de comparações por layer (o pareamento já pula layer acima de 6.000
#: trechos; isto segura o pior caso de muitas paralelas na mesma faixa de 1 m).
#: Acima dele a marca do layer não é medida e o log diz — o eixo segue.
_PAREDE_ESPESSA_MAX_COMPARACOES = 3_000_000


# ---------------------------------------------------------------------------
# TUBO desenhado em FACE DUPLA — as duas paredes do tubo, sem eixo
# ---------------------------------------------------------------------------
# 🩸 30/09/2026 — H34 do estudo do acervo. O Revit exporta o tubo ("P-PIPE")
# pelas DUAS paredes: duas linhas paralelas à distância do diâmetro externo,
# sem linha de eixo. A soma do layer é o dobro do tubo. Um projeto de cliente
# saiu com "tubulação hidrossanitária 1.056 ml CONFIRMADO" (≈ 530 m de tubo),
# e o cliente aprovou. Medido em dois setores do mesmo prédio: 97 e 100% do
# P-PIPE com parceira paralela; 87 e 93% dela a um diâmetro ROTULADO no próprio
# desenho (ø150, ø100, ø75, ø50…).
# 🔑 NÃO divide nem pareia trecho a trecho: num feixe de tubos lado a lado o
# vão até o vizinho (0,133) é MENOR que o diâmetro (0,150) — "a parceira mais
# perto" seria o tubo errado, e 44% do comprimento é ambíguo. v1: DETECTA o
# layer em face dupla, AVISA no prompt e TIRA o selo da linha que usa o
# comprimento dele (regra nº3: razão só alerta).
_RE_LAYER_DE_TUBO = re.compile(r"(?<![a-z])(?:pipe|tubo|tubula)", re.IGNORECASE)
# ø150, Ø 100, %%c75 (o código do AutoCAD pro ø), "PVC-ø75", "ø35-CPVC" — em mm
# 🩸 02/10/2026 (H34b): o Revit em português rotula "75mmø", "110mmø" — o ø
# DEPOIS. Sem ler esse formato, `_diametros_rotulados` dava [] e o H34 não
# decidia: uma piscina saiu "tubulação 1.157 + 1.544 ml ✓" com o P-PIPE em
# face dupla (91 e 98 % em par). Só com o ø: "150mm" sozinho é nota/cota.
_RE_DIAMETRO_ROTULADO = re.compile(
    r"(?:%%[cC]|[øØ⌀])\s*(\d{2,3})(?!\d)"
    r"|(?<![\d.,])(\d{2,3})\s*mm\s*(?:%%[cC]|[øØ⌀])", re.IGNORECASE)
_TUBO_DIAM_MM = (15, 400)       # faixa de diâmetro que vale como rótulo de tubo
_TUBO_DIST_TOL = 0.12           # distância do par = diâmetro ± 12%
_TUBO_ANG_TOL = 1.0             # graus
_TUBO_COBERTURA = 0.5           # o trecho tem parceira em ≥ metade do comprimento
_TUBO_FRACAO_LAYER = 0.8        # ≥ 80% do layer em par → face dupla
# 🩸 30/09 (calibração do estudo): um P-PIPE de 862,8 m com 99% em par, mas só
# 69% a Ø ROTULADO — o resto era tubo de 35 mm SEM rótulo (dreno do ar). A
# 2ª porta: ≥ 90% com QUALQUER parceira (10–300 mm) E ≥ 50% a Ø rotulado.
# Rede de linha única não chega a 90% de parceira; e um par de tubos lado a
# lado a 60 mm (hidráulica comum, rótulos ø25/32) tem 95% de parceira mas 0%
# a Ø rotulado — nenhuma das duas marca.
_TUBO_PAR_QUALQUER = (10, 300)  # mm: faixa da "qualquer parceira"
_TUBO_FRACAO_QUALQUER = 0.9
_TUBO_FRACAO_ROTULO_MIN = 0.5
_TUBO_MIN_M = 5.0               # layer menor que isso não conta
# 🩸 30/09 (medição do estudo nos 3 de produção): os maiores danos têm 23, 37 e
# 41 MIL trechos no P-PIPE — um teto que PULA o layer pulava justo eles. Acima
# do teto, entram os trechos MAIS LONGOS (o tubo; os curtos são conexão).
_TUBO_MAX_SEG = 60000           # teto de trechos por layer (amostra os longos)


def _diametros_rotulados(texts) -> list:
    """Os diâmetros (mm) escritos no desenho: 'ø150', '%%c100', 'PVC-ø75',
    e o do Revit em português, com o ø depois: '75mmø', '110 mm ø'."""
    ds = set()
    for t in texts or ():
        for m in _RE_DIAMETRO_ROTULADO.finditer(str(getattr(t, "text", "") or "")):
            v = int(m.group(1) or m.group(2))
            if _TUBO_DIAM_MM[0] <= v <= _TUBO_DIAM_MM[1]:
                ds.add(v)
    return sorted(ds)


def tubos_em_face_dupla(walls, texts, unit_factor: float = 1.0) -> dict:
    """{layer: {'m', 'fracao', 'diametros_mm'}} dos layers de TUBO desenhados
    pelas duas paredes: ≥ 80% do comprimento com uma parceira paralela a um
    diâmetro ROTULADO no desenho (± 12%), sobrepondo ≥ metade do trecho.

    Sem rótulo de diâmetro no desenho, não decide (devolve {}): paralelas a
    uma distância qualquer podem ser AF e AQ lado a lado."""
    diam = _diametros_rotulados(texts)
    if not diam or not walls:
        return {}
    uf = float(unit_factor) if unit_factor else 1.0
    d_bruto = [d / 1000.0 / uf for d in diam]        # na unidade do desenho
    d_min = min(d_bruto) * (1 - _TUBO_DIST_TOL)
    d_max = max(d_bruto) * (1 + _TUBO_DIST_TOL)
    q_min = _TUBO_PAR_QUALQUER[0] / 1000.0 / uf
    q_max = _TUBO_PAR_QUALQUER[1] / 1000.0 / uf
    j_min, j_max = min(d_min, q_min), max(d_max, q_max)
    por_layer: dict = {}
    total_m: dict = {}
    for w in walls:
        lay = str(getattr(w, "layer", "") or "")
        if not _RE_LAYER_DE_TUBO.search(lay):
            continue
        total_m[lay] = total_m.get(lay, 0.0) + float(getattr(w, "length", 0.0) or 0.0)
        if getattr(w, "curvo", False):
            continue
        pts = getattr(w, "pontos", ()) or ()
        lados = []
        if len(pts) >= 2:
            for p, q in zip(pts, pts[1:]):
                if len(p) > 2 and p[2]:
                    continue                           # lado em arco
                lados.append(((p[0], p[1]), (q[0], q[1])))
        elif tuple(getattr(w, "start", (0, 0))) != tuple(getattr(w, "end", (0, 0))):
            lados.append((tuple(w.start)[:2], tuple(w.end)[:2]))
        for a, b in lados:
            if a != b:
                por_layer.setdefault(lay, []).append((a, b))
    out = {}
    for lay, segs in por_layer.items():
        if total_m.get(lay, 0.0) < _TUBO_MIN_M:
            continue
        _base_m = total_m[lay]
        if len(segs) > _TUBO_MAX_SEG:
            segs = sorted(segs, key=lambda ab: -math.hypot(ab[1][0] - ab[0][0],
                                                            ab[1][1] - ab[0][1]))[:_TUBO_MAX_SEG]
            # 🪤 com amostra, a fração é sobre o AMOSTRADO — sobre o layer
            # inteiro ela cairia só por ter deixado trecho de fora
            _base_m = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in segs) * uf
        itens = []
        for (ax, ay), (bx, by) in segs:
            ang = math.degrees(math.atan2(by - ay, bx - ax)) % 180.0
            itens.append((ang, (ax, ay), (bx, by)))
        itens.sort(key=lambda it: it[0])
        grupos, atual = [], [itens[0]]
        for it in itens[1:]:
            if it[0] - atual[-1][0] <= _TUBO_ANG_TOL:
                atual.append(it)
            else:
                grupos.append(atual)
                atual = [it]
        grupos.append(atual)
        if len(grupos) > 1 and grupos[0][0][0] + 180.0 - grupos[-1][-1][0] <= _TUBO_ANG_TOL:
            grupos[0] = grupos.pop() + grupos[0]
        em_par_m = 0.0
        em_par_qualquer_m = 0.0
        # 30/09 (antes/depois do estudo): o aviso listava os 5 MENORES rotulados
        # (ø25…ø75) e o ø150 que dominava o layer não aparecia — agora são os que
        # PAREARAM, pelos metros
        par_por_d: dict = {}
        for g in grupos:
            th = math.radians(g[0][0])
            ux, uy = math.cos(th), math.sin(th)
            nx, ny = -uy, ux
            sg = []
            for _ang, (ax, ay), (bx, by) in g:
                t0, t1 = sorted((ax * ux + ay * uy, bx * ux + by * uy))
                rho = ((ax + bx) / 2.0) * nx + ((ay + by) / 2.0) * ny
                sg.append((rho, t0, t1))
            sg.sort()
            rhos = [x[0] for x in sg]
            cob = [0.0] * len(sg)          # parceira a Ø ROTULADO
            cob_q = [0.0] * len(sg)        # parceira a QUALQUER distância da faixa
            for i in range(len(sg)):
                ri, a0, a1 = sg[i]
                # busca binária: só o que está na faixa do lado — os pedaços da
                # MESMA linha (dist ≈ 0) nem entram na conta
                j0 = bisect.bisect_left(rhos, ri + j_min, i + 1)
                j1 = bisect.bisect_right(rhos, ri + j_max, j0)
                for j in range(j0, j1):
                    rj, b0, b1 = sg[j]
                    dist = rj - ri
                    ov = min(a1, b1) - max(a0, b0)
                    if ov <= 0:
                        continue
                    if q_min <= dist <= q_max:
                        cob_q[i] += ov
                        cob_q[j] += ov
                    _k = next((k for k, d in enumerate(d_bruto)
                               if abs(dist - d) <= _TUBO_DIST_TOL * d), None)
                    if _k is None:
                        continue
                    cob[i] += ov
                    cob[j] += ov
                    par_por_d[diam[_k]] = par_por_d.get(diam[_k], 0.0) + ov * uf
            for (rho, t0, t1), c, cq in zip(sg, cob, cob_q):
                comp = t1 - t0
                if comp > 0 and min(c, comp) >= _TUBO_COBERTURA * comp:
                    em_par_m += comp * uf
                if comp > 0 and min(cq, comp) >= _TUBO_COBERTURA * comp:
                    em_par_qualquer_m += comp * uf
        fr = em_par_m / _base_m if _base_m > 0 else 0.0
        fr_q = em_par_qualquer_m / _base_m if _base_m > 0 else 0.0
        _porta_a = fr >= _TUBO_FRACAO_LAYER
        _porta_b = fr_q >= _TUBO_FRACAO_QUALQUER and fr >= _TUBO_FRACAO_ROTULO_MIN
        if _porta_a or _porta_b:
            out[lay] = {"m": round(total_m[lay], 2),
                        # o que o aviso diz: a fração EM PAR (a da porta que abriu)
                        "fracao": round(min(fr if _porta_a else fr_q, 1.0), 2),
                        "fracao_diametro": round(min(fr, 1.0), 2),
                        "diametros_mm": [d for d, _m in sorted(par_por_d.items(),
                                                               key=lambda kv: -kv[1])][:8]}
    return out


#: 🩸 01/10/2026 — H75 do estudo do acervo. O Revit exporta o ELETRODUTO como o
#: tubo: as duas paredes (às vezes 2 a 4 linhas, com a espessura da parede), sem
#: rótulo de ø — então a régua do tubo (que exige ø escrito) não marca. Um job de
#: cliente (iluminação, 05/09) entregou "1.798,8 ml ✓": 80 % do layer com UMA
#: parceira a 25 mm (o 3/4"), pelo eixo ~1.070 m. Os layers de eletroduto de
#: linha ÚNICA do acervo têm 0 % em par a essa distância.
_RE_LAYER_DE_ELETRODUTO = re.compile(r"(?<![a-z])(?:eletrodut|conduit|condu[ií]te)", re.IGNORECASE)
#: a PEÇA (condulete, conexão, luva…) mora em layer com nome de eletroduto e o
#: comprimento dela é contorno de bloco — outra régua (H76), não esta
_RE_LAYER_DE_CONEXAO = re.compile(r"conex|condulet|caixa|luva|curva|bucha|acess", re.IGNORECASE)
_ELETRODUTO_PAR_MM = (15, 60)     # diâmetro externo de 1/2" a 2"
_ELETRODUTO_FRACAO = 0.6          # ≥ 60 % do layer com parceira → face dupla


def eletrodutos_em_face_dupla(walls, unit_factor: float = 1.0) -> dict:
    """{layer: {'m', 'fracao', 'diametros_mm'}} dos layers de ELETRODUTO
    desenhados pelas duas paredes: ≥ `_ELETRODUTO_FRACAO` do comprimento com
    uma parceira paralela a 15–60 mm, sobrepondo ≥ metade do trecho.

    Mesmo destino do tubo (`tubos_em_face_dupla`): entra em
    `metadata["tubos_em_face_dupla"]`, a IA é avisada e a linha que usa o
    comprimento não sai medida. SÓ marca — não divide (feixe de eletrodutos
    lado a lado não diz, trecho a trecho, qual linha é de qual tubo).
    `diametros_mm` aqui é a distância MEDIDA do par (não há rótulo).
    """
    if not walls:
        return {}
    uf = float(unit_factor) if unit_factor else 1.0
    q_min = _ELETRODUTO_PAR_MM[0] / 1000.0 / uf
    q_max = _ELETRODUTO_PAR_MM[1] / 1000.0 / uf
    por_layer: dict = {}
    total_m: dict = {}
    for w in walls:
        lay = str(getattr(w, "layer", "") or "")
        if not _RE_LAYER_DE_ELETRODUTO.search(lay) or _RE_LAYER_DE_CONEXAO.search(lay):
            continue
        total_m[lay] = total_m.get(lay, 0.0) + float(getattr(w, "length", 0.0) or 0.0)
        if getattr(w, "curvo", False):
            continue
        pts = getattr(w, "pontos", ()) or ()
        if len(pts) >= 2:
            for p, q in zip(pts, pts[1:]):
                if len(p) > 2 and p[2]:
                    continue
                if (p[0], p[1]) != (q[0], q[1]):
                    por_layer.setdefault(lay, []).append(((p[0], p[1]), (q[0], q[1])))
        elif tuple(getattr(w, "start", (0, 0))) != tuple(getattr(w, "end", (0, 0))):
            por_layer.setdefault(lay, []).append((tuple(w.start)[:2], tuple(w.end)[:2]))
    out = {}
    for lay, segs in por_layer.items():
        if total_m.get(lay, 0.0) < _TUBO_MIN_M:
            continue
        base_m = total_m[lay]
        if len(segs) > _TUBO_MAX_SEG:
            segs = sorted(segs, key=lambda ab: -math.hypot(ab[1][0] - ab[0][0],
                                                            ab[1][1] - ab[0][1]))[:_TUBO_MAX_SEG]
            base_m = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in segs) * uf
        itens = sorted((math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180.0, a, b)
                       for a, b in segs)
        grupos, atual = [], [itens[0]]
        for it in itens[1:]:
            if it[0] - atual[-1][0] <= _TUBO_ANG_TOL:
                atual.append(it)
            else:
                grupos.append(atual)
                atual = [it]
        grupos.append(atual)
        if len(grupos) > 1 and grupos[0][0][0] + 180.0 - grupos[-1][-1][0] <= _TUBO_ANG_TOL:
            grupos[0] = grupos.pop() + grupos[0]
        em_par_m = 0.0
        por_mm: dict = {}
        for g in grupos:
            th = math.radians(g[0][0])
            ux, uy = math.cos(th), math.sin(th)
            nx, ny = -uy, ux
            sg = sorted((((ax + bx) / 2.0) * nx + ((ay + by) / 2.0) * ny,
                         *sorted((ax * ux + ay * uy, bx * ux + by * uy)))
                        for _ang, (ax, ay), (bx, by) in g)
            rhos = [x[0] for x in sg]
            cob = [0.0] * len(sg)
            for i in range(len(sg)):
                ri, a0, a1 = sg[i]
                j0 = bisect.bisect_left(rhos, ri + q_min, i + 1)
                j1 = bisect.bisect_right(rhos, ri + q_max, j0)
                for j in range(j0, j1):
                    rj, b0, b1 = sg[j]
                    ov = min(a1, b1) - max(a0, b0)
                    if ov <= 0:
                        continue
                    cob[i] += ov
                    cob[j] += ov
                    _mm = int(round((rj - ri) * uf * 1000.0))
                    por_mm[_mm] = por_mm.get(_mm, 0.0) + ov
            for (_r, t0, t1), c in zip(sg, cob):
                comp = t1 - t0
                if comp > 0 and min(c, comp) >= _TUBO_COBERTURA * comp:
                    em_par_m += comp * uf
        fr = em_par_m / base_m if base_m > 0 else 0.0
        if fr >= _ELETRODUTO_FRACAO:
            out[lay] = {"m": round(total_m[lay], 2), "fracao": round(min(fr, 1.0), 2),
                        "diametros_mm": [d for d, _o in sorted(por_mm.items(),
                                                               key=lambda kv: -kv[1])][:3],
                        "eletroduto": True}
    return out


#: 🩸 01/10/2026 — H76 do estudo do acervo. O motor mede a linha de DENTRO dos
#: blocos nos layers de infra linear — e a PEÇA (condulete, conexão, luva, caixa)
#: mora em layer com nome de eletroduto. O metro desses layers é o CONTORNO das
#: peças somado: um job de iluminação entregou "conexões para eletroduto
#: 376,8 ml ✓" (988 conduletes de 0,38 m de contorno) e "conexões de eletrocalha
#: 132,1 ml ✓", com as mesmas peças também contadas em un.
_CONTORNO_FRACAO_BLOCO = 0.9      # ≥ 90 % do metro do layer veio de dentro de bloco
_CONTORNO_MIN_INSERCOES = 20      # peça repetida, não um trecho desenhado em bloco
_CONTORNO_MAX_M_POR_INSERCAO = 5.0


def layers_de_contorno_de_peca(walls, metro_de_bloco) -> dict:
    """{layer: {'m', 'insercoes', 'm_por_insercao'}} — layer de CONEXÃO (pelo
    nome: `_RE_LAYER_DE_CONEXAO`) cujo metro é quase todo o contorno de peças
    repetidas desenhadas em bloco. Não é quantidade linear: a peça se conta em un.
    🔑 Só o nome de conexão + as três provas do desenho. Layer de ELETRODUTO cujo
    trecho mora em bloco (o Revit faz isso) não entra: o nome não é de peça."""
    out = {}
    tot: dict = {}
    for w in walls or ():
        lay = str(getattr(w, "layer", "") or "")
        tot[lay] = tot.get(lay, 0.0) + float(getattr(w, "length", 0.0) or 0.0)
    for lay, (m_blk, ins) in (metro_de_bloco or {}).items():
        n = len(ins)
        if not _RE_LAYER_DE_CONEXAO.search(lay) or n < _CONTORNO_MIN_INSERCOES:
            continue
        t = tot.get(lay, 0.0)
        if t <= 0 or m_blk < _CONTORNO_FRACAO_BLOCO * t:
            continue
        if m_blk / n > _CONTORNO_MAX_M_POR_INSERCAO:
            continue
        out[lay] = {"m": round(t, 2), "insercoes": n, "m_por_insercao": round(m_blk / n, 2)}
    return out


#: 🩸 01/10/2026 — H79 do estudo do acervo. Um projeto de incêndio entregou
#: "ramais secundários 12.642 ml ✓": 72 % do layer eram os LADOS de retângulos de
#: ~494 × 461 m (o limite da obra, repetido) — não rede. Medido no acervo: o
#: retângulo de lados contínuos separa (alvos 72–98 %, controles 0 % — meio-fio,
#: eletroduto, eletrocalha e 10 layers de parede, que porta e encontro
#: interrompem). Linha "longa" sozinha NÃO separa (o meio-fio dá 31 %).
_MOLDURA_FRACAO = 0.5        # ≥ 50 % do metro do layer em lado de retângulo
_MOLDURA_LADO_MIN = 0.10     # lado ≥ 10 % do lado do desenho (p2–p98)
_MOLDURA_TOL = 0.002         # 0,2 % do lado do desenho
#: limite de lote em layer de MURO é quantidade (ml de muro de divisa)
_RE_LAYER_LIMITE_QUE_E_OBRA = re.compile(r"muro|divisa|cerca|gradil|alambrado", re.IGNORECASE)


def layers_de_moldura_ou_limite(msp, walls, unit_factor: float = 1.0) -> dict:
    """{layer: {'m', 'fracao'}} — layer cujo metro é, na maior parte, os LADOS
    de retângulos grandes de lados contínuos (moldura de folha, limite de
    obra/lote): ≥ `_MOLDURA_FRACAO`. Lados horizontais/verticais de LINE e de
    LWPOLYLINE, emendados quando colineares. Parede e muro/divisa/cerca ficam
    de fora. SÓ MARCA (aviso + selo), não tira o número."""
    from engine_rules import layer_e_parede
    uf = float(unit_factor) if unit_factor else 1.0
    tot: dict = {}
    for w in walls or ():
        ly = str(getattr(w, "layer", "") or "")
        tot[ly] = tot.get(ly, 0.0) + float(getattr(w, "length", 0.0) or 0.0)
    segs: dict = {}
    for e in msp.query("LINE LWPOLYLINE"):
        try:
            ly = str(e.dxf.layer)
            if e.dxftype() == "LINE":
                pts = [(e.dxf.start[0], e.dxf.start[1]), (e.dxf.end[0], e.dxf.end[1])]
            else:
                pts = [(p[0], p[1]) for p in e.get_points("xy")]
                if e.closed and pts:
                    pts.append(pts[0])
        except Exception:
            continue
        for a, b in zip(pts, pts[1:]):
            segs.setdefault(ly, []).append((a, b))
    # 🪤 o lado do desenho sai de uma AMOSTRA COM PASSO sobre todos os trechos —
    # os primeiros N na ordem do arquivo podem ser só um canto do desenho, e aí
    # o retângulo de uma sala passaria do piso de 10 % (achado do estudo, 01/10)
    _total = sum(len(ss) for ss in segs.values())
    _passo = max(1, _total // 20000)
    xs, ys = [], []
    _k = 0
    for ss in segs.values():
        for a, b in ss:
            if _k % _passo == 0:
                xs.extend((a[0], b[0]))
                ys.extend((a[1], b[1]))
            _k += 1
    if len(xs) < 8:
        return {}
    xs.sort()
    ys.sort()

    def _p(v, q):
        return v[min(len(v) - 1, int(len(v) * q))]
    lado = max(_p(xs, 0.98) - _p(xs, 0.02), _p(ys, 0.98) - _p(ys, 0.02))
    if lado <= 0:
        return {}
    tol, lmin = _MOLDURA_TOL * lado, _MOLDURA_LADO_MIN * lado

    def _corridas(itens):
        """[(coord, ini, fim)] emendando os colineares (mesma coord, vão ≤ tol)."""
        por = {}
        for c, a, b in itens:
            por.setdefault(round(c / tol), []).append((min(a, b), max(a, b), c))
        out = []
        for lst in por.values():
            lst.sort()
            ini, fim, c = lst[0]
            for a, b, _c in lst[1:]:
                if a <= fim + tol:
                    fim = max(fim, b)
                else:
                    out.append((c, ini, fim))
                    ini, fim = a, b
            out.append((c, ini, fim))
        return out

    out = {}
    for ly, ss in segs.items():
        if layer_e_parede(ly) or _RE_LAYER_LIMITE_QUE_E_OBRA.search(ly):
            continue
        t = tot.get(ly, 0.0)
        if t <= 0:
            continue
        hs = _corridas([(a[1], a[0], b[0]) for a, b in ss if abs(b[1] - a[1]) <= tol])
        vs = _corridas([(a[0], a[1], b[1]) for a, b in ss if abs(b[0] - a[0]) <= tol])
        hs = [h for h in hs if h[2] - h[1] >= lmin]
        vs = [v for v in vs if v[2] - v[1] >= lmin]
        if len(hs) < 2 or len(vs) < 2:
            continue

        def _vert(x, y0, y1):
            return any(abs(v[0] - x) <= tol and v[1] <= y0 + tol and v[2] >= y1 - tol for v in vs)
        rect_bruto = 0.0
        usados = set()
        hs.sort()
        for i, h1 in enumerate(hs):
            for h2 in hs[i + 1:]:
                if (h2[0] - h1[0] < lmin or abs(h1[1] - h2[1]) > tol or abs(h1[2] - h2[2]) > tol):
                    continue
                if not (_vert(h1[1], h1[0], h2[0]) and _vert(h1[2], h1[0], h2[0])):
                    continue
                chave = (round(h1[0] / tol), round(h2[0] / tol), round(h1[1] / tol), round(h1[2] / tol))
                if chave in usados:
                    continue
                usados.add(chave)
                rect_bruto += 2 * ((h1[2] - h1[1]) + (h2[0] - h1[0]))
        f = rect_bruto * uf / t
        if f >= _MOLDURA_FRACAO:
            out[ly] = {"m": round(t, 2), "fracao": round(min(f, 1.0), 2)}
    return out


#: 🩸 02/10/2026 — H88 do estudo do acervo. Um layout de fábrica entregou
#: "esteira 999,31 ml ✓" e "543,19 ml ✓": os layers de esteira traziam ROLETES,
#: TRAVESSAS (em 2 linhas, de comprimentos diferentes) e CAIXAS com X, e o
#: comprimento da esteira era ~60 m. O ✓ veio da IA citando o comprimento do
#: layer. Medido no acervo (346 DXF): só esse arquivo tem layer de esteira com
#: geometria; os controles são sintéticos.
#: 🔑 Duas anatomias, medidas no arquivo, cada peça contada uma vez:
#:   • peça SOLTA — trecho curto que não continua em linha (travessa, caixa,
#:     rolete isolado): a esteira proposta, 64 %;
#:   • ESCADA — gêmeos paralelos ao lado a ≤ 0,25 L, em ≥ 4 posições: a
#:     existente, 81 %, onde os roletes das faixas empilhadas caem na mesma
#:     reta e "emendam" (solta dava 1 %).
#: Borda e eixo — inteiros, em módulos, com folga, em curva, em perfil duplo —
#: emendam e não fazem escada (as bordas ficam a ≥ 0,5 L uma da outra).
#: 🪤 1ª régua (só a fileira, gêmeos a ≤ 3 L) perdia a proposta; 2ª (só a
#: solta) perdia a existente. Sem cláusula de borda: a existente tinha as
#: bordas desenhadas e o total ainda era 9× o eixo.
#: 🪤 O NOME segura: sem ele, 17 % dos layers de uma amostra marcariam (brise,
#: pérgola, esquadria, mobiliário são escadas perfeitas).
#: 🪤 Fronteira só à ESQUERDA: "Conveyor_Proposed" tem "_" depois (letra para o
#: \b), e "testeira" tem "esteira" dentro.
#: 🪤 TEMPO: a 1ª versão varria células de 1,5 m para toda peça — 42 s só nela
#: num layer de 8,7 mil trechos, quase todos em 10 × 15 m (hoje ~1–2 s). A
#: busca agora é numa grade do
#: tamanho do RAIO da própria peça (a ponta comum: 0,5 % de L; a reta: 0,5 L,
#: só entre paralelas), e layer acima de `_ESTEIRA_MAX_TRECHOS` não roda.
#: 🪤 Limites aceitos (só tiram o ✓): transportador curto (≤ 3 m) desenhado só
#: pelo eixo e solto conta como peça; faixas estreitas paralelas a < 0,25 L
#: desenhadas pelas bordas em módulos soltos fazem escada.
_RE_LAYER_DE_ESTEIRA = re.compile(
    r"(?<![a-zà-ú])(conveyor|esteira|transportador|rolete|correia)", re.IGNORECASE)
_SOLTA_MAX_M = 3.0          # peça curta: até a largura máxima de esteira
_SOLTA_PONTA_TOL = 0.005    # ponta comum / mesma reta: ≤ 0,5 % de L (o tubo em 2 linhas: 1,5–2 %)
_SOLTA_GIRO_MAX = 20.0      # graus: ponta comum que SEGUE (curva de polilinha), não canto
_SOLTA_ALINH_TOL = 2.0      # graus: colinear / paralelo
_SOLTA_FOLGA = 0.5          # colinear com folga de até 0,5 L entre as pontas
_FILEIRA_PECA_MIN_M = 0.2   # custo: o picado de < 20 cm (texto, hachura) fica fora da escada
_FILEIRA_DESVIO = 0.10      # gêmeo ao LADO: desvio ao longo ≤ 10 % de L
_FILEIRA_PASSO_MAX = 0.25   # ...a ≤ 0,25 L (rolete da existente: 0,09 L)
_FILEIRA_MIN_POSICOES = 4   # escada: ≥ 4 posições de lado (bordas + eixo: 3)
_FILEIRA_POSICAO_TOL = 0.02 # posições a ≤ 2 % de L são a mesma (a cópia quase em pilha)
_ESTEIRA_FRACAO = 0.5       # ≥ 50 % do metro do layer em peça solta ou em escada
_ESTEIRA_MAX_TRECHOS = 60000  # teto por layer (acima: não roda, só loga)
_ESTEIRA_NIVEIS = 8         # grade do raio: célula = base / 2^k, k ≤ 8


def layers_esteira_por_travessa(msp, walls, unit_factor: float = 1.0) -> dict:
    """{layer: {'m', 'fracao', 'peca_m', 'pecas'}} — layer de ESTEIRA (pelo
    nome: `_RE_LAYER_DE_ESTEIRA`, fora anotação) cujo metro é, na maior parte,
    peças curtas (≤ 3 m) que NÃO são percurso: SOLTAS (não continuam em linha
    por nenhuma das pontas — nem ponta comum com giro ≤ 20°, nem colinear com
    folga ≤ 0,5 L) ou em ESCADA (gêmeos paralelos ao lado, a ≤ 0,25 L, em ≥ 4
    posições). `peca_m` é a mediana pelo METRO. SÓ MARCA (aviso + selo)."""
    from engine_rules import layer_is_anotacao
    uf = float(unit_factor) if unit_factor else 1.0
    tot: dict = {}
    for w in walls or ():
        ly = str(getattr(w, "layer", "") or "")
        if _RE_LAYER_DE_ESTEIRA.search(ly) and not layer_is_anotacao(ly):
            tot[ly] = tot.get(ly, 0.0) + float(getattr(w, "length", 0.0) or 0.0)
    if not tot:
        return {}
    hi, lo = _SOLTA_MAX_M / uf, _FILEIRA_PECA_MIN_M / uf
    # 🪤 a cópia exata em pilha conta UMA vez — o denominador (`walls`) já vem
    # assim (H84); sem isto, o rolete colado 2× dobrava o numerador
    _tq = 0.001 / uf
    vistos: set = set()
    segs: dict = {}
    for e in msp.query("LINE LWPOLYLINE"):
        try:
            ly = str(e.dxf.layer)
            if ly not in tot:
                continue
            if e.dxftype() == "LINE":
                pts = [(e.dxf.start[0], e.dxf.start[1]), (e.dxf.end[0], e.dxf.end[1])]
            else:
                pts = [(p[0], p[1]) for p in e.get_points("xy")]
                if e.closed and pts:
                    pts.append(pts[0])
        except Exception:
            continue
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            L = math.hypot(bx - ax, by - ay)
            if L <= 0:
                continue
            _ch = (ly,) + tuple(sorted(((round(ax / _tq), round(ay / _tq)),
                                        (round(bx / _tq), round(by / _tq)))))
            if _ch in vistos:
                continue
            vistos.add(_ch)
            segs.setdefault(ly, []).append((ax, ay, bx, by, L))
    cos_giro = math.cos(math.radians(_SOLTA_GIRO_MAX))
    cos_alinh = math.cos(math.radians(_SOLTA_ALINH_TOL))
    nb = int(180.0 // _SOLTA_ALINH_TOL)
    bases = {"ponta": _SOLTA_PONTA_TOL * hi, "reta": _SOLTA_FOLGA * hi,
             "meio": (_FILEIRA_PASSO_MAX + _FILEIRA_DESVIO) * hi}
    out = {}
    for ly, ss in segs.items():
        t = tot.get(ly, 0.0)
        if t <= 0:
            continue
        if len(ss) > _ESTEIRA_MAX_TRECHOS:
            logger.warning("[esteira-por-travessa] '%s' com %d trechos — acima do teto, "
                           "não medido", ly, len(ss))
            continue
        bal = [int((math.degrees(math.atan2(by - ay, bx - ax)) % 180.0) // _SOLTA_ALINH_TOL) % nb
               for ax, ay, bx, by, _L in ss]
        grades: dict = {}

        def _grade(tipo, k):
            """Pontas (ou meios) em células de base/2^k — o raio de busca da
            peça cabe em 1 célula, então bastam as 9 em volta."""
            g = grades.get((tipo, k))
            if g is None:
                s = bases[tipo] / (2 ** k)
                cel: dict = {}
                for j, (ax, ay, bx, by, Lj) in enumerate(ss):
                    if tipo == "meio":
                        if not lo <= Lj <= hi:
                            continue
                        pts_j = (((ax + bx) / 2.0, (ay + by) / 2.0),)
                    else:
                        pts_j = ((ax, ay), (bx, by))
                    for px, py in pts_j:
                        ch = ((int(px // s), int(py // s)) if tipo == "ponta"
                              else (bal[j], int(px // s), int(py // s)))
                        cel.setdefault(ch, []).append((j, px, py))
                g = grades[(tipo, k)] = (cel, s)
            return g

        def _vizinhos(tipo, k, px, py, b0):
            cel, s = _grade(tipo, k)
            cx, cy = int(px // s), int(py // s)
            if tipo == "ponta":
                chaves = ((cx + b, cy + c) for b in (-1, 0, 1) for c in (-1, 0, 1))
            else:
                chaves = ((p, cx + b, cy + c) for p in ((b0 - 1) % nb, b0, (b0 + 1) % nb)
                          for b in (-1, 0, 1) for c in (-1, 0, 1))
            for ch in chaves:
                yield from cel.get(ch, ())

        def _nivel(L):
            return min(_ESTEIRA_NIVEIS, max(0, int(math.log2(hi / L))))
        conta: set = set()
        # ── peça SOLTA ──
        for i, (ax, ay, bx, by, L) in enumerate(ss):
            if L > hi:
                continue
            ux, uy = (bx - ax) / L, (by - ay) / L
            k = _nivel(L)
            emenda = False
            for px, py in ((ax, ay), (bx, by)):
                # ponta comum que segue (giro ≤ 20°)
                for j, qx, qy in _vizinhos("ponta", k, px, py, 0):
                    if j != i and math.hypot(qx - px, qy - py) <= _SOLTA_PONTA_TOL * L:
                        jax, jay, jbx, jby, Lj = ss[j]
                        if abs(ux * (jbx - jax) + uy * (jby - jay)) / Lj >= cos_giro:
                            emenda = True
                            break
                if emenda:
                    break
                # a mesma reta, com folga (só entre paralelas)
                for j, qx, qy in _vizinhos("reta", k, px, py, bal[i]):
                    if j == i:
                        continue
                    d = math.hypot(qx - px, qy - py)
                    if _SOLTA_PONTA_TOL * L < d <= _SOLTA_FOLGA * L:
                        jax, jay, jbx, jby, Lj = ss[j]
                        if (abs(ux * (jbx - jax) + uy * (jby - jay)) / Lj >= cos_alinh
                                and abs(-(qx - ax) * uy + (qy - ay) * ux) <= _SOLTA_PONTA_TOL * L):
                            emenda = True
                            break
                if emenda:
                    break
            if not emenda:
                conta.add(i)
        # ── ESCADA ── gêmeo paralelo AO LADO e perto
        cand = [i for i, s_ in enumerate(ss) if lo <= s_[4] <= hi]
        pai = {i: i for i in cand}

        def _raiz(a):
            while pai[a] != a:
                pai[a] = pai[pai[a]]
                a = pai[a]
            return a
        for i in cand:
            ax, ay, bx, by, L = ss[i]
            ux, uy = (bx - ax) / L, (by - ay) / L
            mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
            for j, qx, qy in _vizinhos("meio", _nivel(L), mx, my, bal[i]):
                if j == i:
                    continue
                jax, jay, jbx, jby, Lj = ss[j]
                if abs(ux * (jbx - jax) + uy * (jby - jay)) / Lj < cos_alinh:
                    continue
                dx_, dy_ = qx - mx, qy - my
                if (abs(dx_ * ux + dy_ * uy) <= _FILEIRA_DESVIO * L
                        and abs(-dx_ * uy + dy_ * ux) <= _FILEIRA_PASSO_MAX * L):
                    ri, rj = _raiz(i), _raiz(j)
                    if ri != rj:
                        pai[ri] = rj
        grupos: dict = {}
        for i in cand:
            grupos.setdefault(_raiz(i), []).append(i)
        for g in grupos.values():
            if len(g) < _FILEIRA_MIN_POSICOES:
                continue
            ax, ay, bx, by, _L = ss[g[0]]
            Lg = math.hypot(bx - ax, by - ay)
            nx, ny = -(by - ay) / Lg, (bx - ax) / Lg
            comps = sorted(ss[i][4] for i in g)
            tol = _FILEIRA_POSICAO_TOL * comps[len(comps) // 2]
            pos = sorted((ss[i][0] + ss[i][2]) / 2.0 * nx + (ss[i][1] + ss[i][3]) / 2.0 * ny
                         for i in g)
            if 1 + sum(1 for p, q in zip(pos, pos[1:]) if q - p > tol) >= _FILEIRA_MIN_POSICOES:
                conta.update(g)
        compr = sorted(ss[i][4] for i in conta)
        f = sum(compr) * uf / t
        if f >= _ESTEIRA_FRACAO:
            # a peça típica pelo METRO: o picado de poucos cm não manda na mediana
            meio, acum, peca = sum(compr) / 2.0, 0.0, 0.0
            for c in compr:
                acum += c
                if acum >= meio:
                    peca = c
                    break
            out[ly] = {"m": round(t, 2), "fracao": round(min(f, 1.0), 2),
                       "peca_m": round(peca * uf, 2), "pecas": len(compr)}
    return out


#: 🩸 04/10/2026 — E14 da conferência da lista de dano. Um projeto de incêndio
#: entregou "tubulação 1.285,22 ml ✓" (e o mesmo número em outro job do mesmo
#: projeto): o layer da rede era, em 94–99 % do metro, a GRADE da tabela de
#: SIMBOLOGIA — rede de verdade, 0. O H79 não pega (tabela não é moldura).
#: Medido no acervo: 49 layers em 21 jobs; os elegíveis à chave, olhados no
#: desenho, são todos tabela (simbologia, quadro de áreas, legenda de pisos,
#: de portas); 0 ✓ certo perdido.
#: 🔑 TABELA = ≥ 5 horizontais de mesmo vão, espaçadas ≥ 2 % do vão, com as
#: bordas verticais das DUAS pontas fechando cada faixa, texto por linha
#: (≥ (linhas − 1)/2, de qualquer layer) e um CABEÇALHO (legenda, simbologia,
#: quadro, …). 🪤 Sem o cabeçalho há falso positivo medido: cobertura em
#: contornos empilhados, escada com cota por degrau, elevação de rack.
#: 🪤 DUAS leituras, a caixa vale se aparecer em qualquer uma: trecho a trecho
#: (a tabela de horizontais sobrepostas só aparece assim) e em CORRIDAS de
#: colineares emendados (a de linha quebrada por célula e a de retângulo por
#: célula só aparecem assim). Cada uma sozinha perdia 4 / 35 de 59 tabelas.
#: 🪤 A caixa PARTE onde as bordas das pontas param: tabelas empilhadas do mesmo
#: vão são caixas separadas (numa caixa só, a borda não cobria a altura e a
#: régua via 31 % de um layer que é 85 % tabela).
#: 🪤 Diferente do H79, NÃO pula layer de parede: o QUADRO DE ÁREAS desenhado no
#: layer de parede era 74 % do metro dele (medido). A trava é só de METRO — a
#: área da hachura do layer não é tocada.
#: 🪤 A fração é PISO: célula de linha dupla e retângulo solto com folga não são
#: lidos (um layer que é todo tabela, de células assim, mede 26 %).
#: 🩸 05/10 (revisão da Projetos): a REDE EM ESCADA tem a forma da tabela —
#: ramais paralelos de mesmo vão fechados pelos sub-gerais, um rótulo por ramal
#: — e a palavra do cabeçalho aparecia em QUALQUER lugar da caixa ("SALA DE
#: QUADROS", "VER NOTA 3", "QUADRO DE ALARME" logo acima): marcava 84 % de uma
#: grade de sprinkler. Medido nas 510 caixas dos 103 layers marcados:
#:   • a LETRA da tabela ocupa a linha: altura mediana dos textos ÷ passo
#:     mediano das linhas ≥ 0,138 nas 13 tabelas elegíveis; o rótulo de rede é
#:     0,1–0,3 m pra 1,5–3 m de ramal (0,07–0,17);
#:   • o CABEÇALHO fica na faixa de cima (da penúltima linha até a folga acima
#:     do topo) — menos na tabela COMPOSTA (seções empilhadas, cabeçalho de
#:     seção no meio), que tem ≥ 5 textos por faixa (8,9; as outras que só
#:     passam por aqui, 5,8–22) contra ~1 rótulo por ramal na rede.
#:     🪤 Com 3 passavam eletrodutos com 3 marcas por trecho (circuito,
#:     fiação, bitola) e vagas com 3 textos por vaga, com a palavra no meio
#:     (3,1–3,2 por faixa); os únicos layers medidos entre 3 e 5 eram de
#:     anotação (3,9 e 4,2), que já levam o rótulo de anotação.
#: Com as duas: 85 dos 103 seguem marcados, os 13 elegíveis todos. Saem 7
#: tabelas de aço de poucas linhas desenhadas (letra 0,04–0,10 do passo; todas
#: já fora da chave por ressalva de unidade ou layer sem nome), molduras de
#: folha com notas, um layer de quadros elétricos, 2 layers de anotação e um
#: "0" com ressalva de unidade que ficava em 21 % e cai abaixo do piso.
#: 🪤 Limite que fica: eletrocalhas paralelas a ≤ 2,5 m, fechadas nas pontas,
#: cada uma com um rótulo diferente e a palavra logo acima (teste CUSTO).
#: "Textos distintos" pegaria a de rótulo repetido, mas derruba quadro de
#: cargas e tabela de especificação reais (números repetidos) — medido, fora.
_TABELA_LETRA_MIN = 0.10      # altura da letra ÷ passo das linhas
_TABELA_TEXTO_DENSO = 5.0     # textos por faixa da tabela composta (cabeçalho no meio)
_TABELA_MIN_LINHAS = 5        # horizontais de mesmo vão
_TABELA_ESPACO_MIN = 0.02     # menor espaçamento ≥ 2 % do vão (o par de faces da parede não)
_TABELA_PONTA_TOL = 0.01      # mesmo vão / borda na ponta: a ≤ 1 % do vão
_TABELA_BORDA_COBRE = 0.8     # as bordas das 2 pontas cobrem ≥ 80 % de cada faixa
_TABELA_RETA_TOL = 0.002      # horizontal / vertical: desvio ≤ 0,2 % do trecho
_TABELA_FRACAO = 0.20         # ≥ 20 % do metro do layer dentro das caixas
_TABELA_MIN_M = 20.0          # ...e ≥ 20 m
_RE_CABECALHO_DE_TABELA = re.compile(
    r"legenda|simbologia|quadro|tabela|notas?\b|descri[cç][aã]o|\bitem\b|quant|especifica")


def layers_grade_de_tabela(msp, walls, texts, unit_factor: float = 1.0) -> dict:
    """{layer: {'m', 'fracao', 'cabecalho', 'caixas'}} — layer cujo metro é, em
    ≥ `_TABELA_FRACAO` (e ≥ `_TABELA_MIN_M`), as LINHAS DE TABELAS desenhadas
    (legenda, simbologia, quadro): caixas de ≥ 5 horizontais de mesmo vão
    fechadas pelas bordas das duas pontas, com texto por linha e cabeçalho.
    Lê LINE e os lados de LWPOLYLINE e de POLYLINE (2D/3D), a cópia exata 1×;
    o metro da grade = os trechos horizontais e verticais DENTRO das caixas.
    Sem filtro de nome nem de parede (ver acima). SÓ MARCA (aviso + selo)."""
    uf = float(unit_factor) if unit_factor else 1.0
    tot: dict = {}
    for w in walls or ():
        ly = str(getattr(w, "layer", "") or "")
        tot[ly] = tot.get(ly, 0.0) + float(getattr(w, "length", 0.0) or 0.0)
    if not tot:
        return {}
    segs: dict = {}
    for e in msp.query("LINE LWPOLYLINE POLYLINE"):
        try:
            ly = str(e.dxf.layer)
            if ly not in tot:
                continue
            tipo = e.dxftype()
            if tipo == "LINE":
                pts = [(e.dxf.start[0], e.dxf.start[1], 0.0), (e.dxf.end[0], e.dxf.end[1], 0.0)]
            elif tipo == "LWPOLYLINE":
                pts = [(p[0], p[1], p[2]) for p in e.get_points("xyb")]
                if e.closed and pts:
                    pts.append(pts[0])
            else:
                if not (e.is_2d_polyline or e.is_3d_polyline):
                    continue            # malha e polyface não são traço
                _2d = e.is_2d_polyline
                pts = [(v.dxf.location[0], v.dxf.location[1],
                        float(v.dxf.get("bulge", 0) or 0) if _2d else 0.0) for v in e.vertices]
                if e.is_closed and pts:
                    pts.append(pts[0])
        except Exception:
            continue
        ss = segs.setdefault(ly, [])
        for (ax, ay, blg), (bx, by, _b) in zip(pts, pts[1:]):
            if not blg and (ax != bx or ay != by):     # o lado em arco não é linha de tabela
                ss.append((ax, ay, bx, by))
    # o lado do desenho, por AMOSTRA COM PASSO (a lição do H79)
    _total = sum(len(ss) for ss in segs.values())
    _passo = max(1, _total // 20000)
    xs, ys = [], []
    _k = 0
    for ss in segs.values():
        for ax, ay, bx, by in ss:
            if _k % _passo == 0:
                xs.extend((ax, bx))
                ys.extend((ay, by))
            _k += 1
    if len(xs) < 8:
        return {}
    xs.sort()
    ys.sort()

    def _p(v, q):
        return v[min(len(v) - 1, int(len(v) * q))]
    lado = max(_p(xs, 0.98) - _p(xs, 0.02), _p(ys, 0.98) - _p(ys, 0.02))
    if lado <= 0:
        return {}
    tol_c, tol_gap = 1e-5 * lado, 1e-3 * lado
    txt = []
    for t in texts or ():
        try:
            txt.append((float(t.position[0]), float(t.position[1]), str(getattr(t, "text", "") or ""),
                        float(getattr(t, "height", 0) or 0)))
        except Exception:
            continue
    txt.sort()
    txs = [t[0] for t in txt]

    def _corridas(itens):
        """[(coord, ini, fim)] emendando os colineares (mesma coord ± tol_c, vão ≤ tol_gap)."""
        por: dict = {}
        for c, a, b in itens:
            por.setdefault(round(c / tol_c), []).append((a, b, c))
        out_ = []
        for lst in por.values():
            lst.sort()
            ini, fim, c = lst[0]
            for a, b, _c in lst[1:]:
                if a <= fim + tol_gap:
                    fim = max(fim, b)
                else:
                    out_.append((c, ini, fim))
                    ini, fim = a, b
            out_.append((c, ini, fim))
        return out_

    _tq = 0.001 / uf     # a cópia exata em pilha conta UMA vez (o walls já vem assim, H84)
    out = {}
    for ly, ss in segs.items():
        t = tot.get(ly, 0.0)
        if t < _TABELA_MIN_M:
            continue
        if len(ss) > _TUBO_MAX_SEG:
            logger.warning("[grade-de-tabela] '%s' com %d trechos — acima do teto, não medido",
                           ly, len(ss))
            continue
        vistos: set = set()
        hs, vs = [], []
        for ax, ay, bx, by in ss:
            _ch = tuple(sorted(((round(ax / _tq), round(ay / _tq)), (round(bx / _tq), round(by / _tq)))))
            if _ch in vistos:
                continue
            vistos.add(_ch)
            dx_, dy_ = abs(bx - ax), abs(by - ay)
            L = math.hypot(dx_, dy_)
            if dy_ <= _TABELA_RETA_TOL * L:
                hs.append(((ay + by) / 2.0, min(ax, bx), max(ax, bx)))
            elif dx_ <= _TABELA_RETA_TOL * L:
                vs.append(((ax + bx) / 2.0, min(ay, by), max(ay, by)))
        if len(hs) < _TABELA_MIN_LINHAS or len(vs) < 2:
            continue
        # a borda = a UNIÃO dos trechos verticais na ponta (a quebrada por célula
        # também cobre). 🪤 NÃO pela corrida emendada: ela emenda vão de até
        # 1/1000 do desenho, e numa prancha grande fechava a faixa vazia entre o
        # título e a tabela — a caixa não partia e o espaçamento de 0,17 do
        # título derrubava a tabela de 29 linhas inteira (medido no acervo).
        vr = sorted(vs)
        vx = [v[0] for v in vr]

        def _caixa(x0, x1, yy):
            """A caixa (x0, x1, y0, y1, cabeçalho) das linhas `yy`, ou None."""
            n, L = len(yy), x1 - x0
            if n < _TABELA_MIN_LINHAS or min(b - a for a, b in zip(yy, yy[1:])) < _TABELA_ESPACO_MIN * L:
                return None
            y0, y1 = yy[0], yy[-1]
            folga = max((y1 - y0) / (n - 1), 0.3 * (y1 - y0))
            dentro = [txt[i] for i in range(bisect_left(txs, x0), bisect_right(txs, x1))
                      if y0 <= txt[i][1] <= y1 + folga]
            if len(dentro) < max(2, (n - 1) / 2.0):
                return None
            # a letra ocupa a linha (o rótulo de rede é pequeno pro passo dos ramais)
            alturas = [h for _x, _y, _s, h in dentro if h > 0]
            passo = statistics.median(b - a for a, b in zip(yy, yy[1:]))
            if not alturas or statistics.median(alturas) < _TABELA_LETRA_MIN * passo:
                return None
            cab, em_cima = set(), False
            for _x, y, s, _h in dentro:
                ws = _RE_CABECALHO_DE_TABELA.findall(s.lower())
                cab.update(ws)
                em_cima = em_cima or (bool(ws) and y >= yy[-2])
            # o cabeçalho na faixa de cima — ou a tabela composta, densa de texto
            if not cab or not (em_cima or len(dentro) >= _TABELA_TEXTO_DENSO * (n - 1)):
                return None
            return (x0, x1, y0, y1, sorted(cab))

        def _caixas(hh):
            grupos: dict = {}
            for y, a, b in hh:
                q = _TABELA_PONTA_TOL * (b - a)
                if q > 0:
                    grupos.setdefault((round(a / q), round(b / q)), []).append((y, a, b))
            res = []
            for g in grupos.values():
                if len(g) < _TABELA_MIN_LINHAS:
                    continue
                x0 = sum(a for _, a, _ in g) / len(g)
                x1 = sum(b for _, _, b in g) / len(g)
                tb = _TABELA_PONTA_TOL * (x1 - x0)
                yy = []
                for y in sorted(y for y, _, _ in g):
                    if not yy or y - yy[-1] > tol_c:
                        yy.append(y)
                if len(yy) < _TABELA_MIN_LINHAS:
                    continue
                bordas = []
                for xb in (x0, x1):
                    bd = _funde_intervalos([(vr[i][1], vr[i][2])
                                            for i in range(bisect_left(vx, xb - tb), bisect_right(vx, xb + tb))])
                    bordas.append((bd, [a for a, _ in bd]))
                ini = 0
                for i in range(len(yy)):
                    fecha = i + 1 < len(yy) and all(
                        sum(b - a for a, b in _recorta_intervalos(bd, ib, yy[i], yy[i + 1]))
                        >= _TABELA_BORDA_COBRE * (yy[i + 1] - yy[i]) for bd, ib in bordas)
                    if not fecha:
                        cx = _caixa(x0, x1, yy[ini:i + 1])
                        if cx:
                            res.append(cx)
                        ini = i + 1
            return res
        caixas = _caixas(hs) + _caixas(_corridas(hs))
        if not caixas:
            continue
        # a mesma tabela achada pelas duas leituras (ou um pedaço dela) conta 1×
        caixas.sort(key=lambda c: -(c[1] - c[0]) * (c[3] - c[2]))
        kept = []
        for c in caixas:
            area = (c[1] - c[0]) * (c[3] - c[2])
            if not any(max(0.0, min(c[1], k[1]) - max(c[0], k[0])) * max(0.0, min(c[3], k[3]) - max(c[2], k[2]))
                       >= 0.5 * area for k in kept):
                kept.append(c)
        # o metro da grade: os trechos horizontais e verticais dentro das caixas, cada um 1×
        hs.sort()
        vs.sort()
        hy, vxx = [h[0] for h in hs], [v[0] for v in vs]
        ped_h: dict = {}
        ped_v: dict = {}
        for x0, x1, y0, y1, _cab in kept:
            tb = _TABELA_PONTA_TOL * (x1 - x0)
            for i in range(bisect_left(hy, y0 - tb), bisect_right(hy, y1 + tb)):
                a, b = max(hs[i][1], x0 - tb), min(hs[i][2], x1 + tb)
                if b > a:
                    ped_h.setdefault(i, []).append((a, b))
            for i in range(bisect_left(vxx, x0 - tb), bisect_right(vxx, x1 + tb)):
                a, b = max(vs[i][1], y0 - tb), min(vs[i][2], y1 + tb)
                if b > a:
                    ped_v.setdefault(i, []).append((a, b))
        # float(): o ponto da LWPOLYLINE vem em numpy, e isto vai pro metadata
        m = float(sum(b - a for ped in (ped_h, ped_v) for iv in ped.values()
                      for a, b in _funde_intervalos(iv))) * uf
        f = m / t
        if m >= _TABELA_MIN_M and f >= _TABELA_FRACAO:
            cab = sorted({w for c in kept for w in c[4]})
            out[ly] = {"m": round(float(t), 2), "fracao": round(min(f, 1.0), 2),
                       "cabecalho": ", ".join(cab[:3]), "caixas": len(kept)}
    return out


#: 🩸 05/10/2026 — E07 da conferência da lista de dano. Uma eletrocalha
#: desenhada como FAIXA de 9 e 17 linhas paralelas a 25 mm (o preenchimento da
#: rota) somava 1.058,79 m contra ~111 m de eixo (9,5×); outra, de 13 linhas,
#: 13×. Com a unidade provada, a chave do selo promovia as duas a ✓ (medido no
#: main de 04/10) — e o relato do eixo dizia "JÁ pelo EIXO" sem ter reduzido nada.
#: 🔑 FAIXA = linhas paralelas (≤ 0,3°), de comprimento parecido (≥ 0,7),
#: sobrepostas (≥ 80 % da menor), ao lado umas das outras a passo CONSTANTE
#: (± 5 % do 1º), encadeadas uma a uma pela distância lateral (a próxima ainda
#: livre). Conta a faixa com ≥ 5 linhas, passo ≤ 3 % do comprimento e largura
#: (n − 1)·passo ≤ 1,0 m; marca o layer com ≥ 60 % do comprimento em faixas.
#: 🪤 Numerador e denominador da MESMA população: os trechos do msp (LINE e
#: lados retos de LWPOLYLINE, a cópia exata 1×). Contra o walls (com o peso da
#: folha, e sem os lados de LWPOLYLINE fora de duto/parede/tubo), um layer de
#: detalhe dava 355 % (medido na verificação).
#: 🪤 N = 5 é o menor que deixa de fora o feixe de 3 eletrodutos no mesmo
#: traçado (ali a soma É a medida) e ainda pega a eletrocalha de 5 linhas. A
#: corrente fica com ≥ 3 linhas (como foi medida) e só a de ≥ 5 conta.
#: Medido no acervo: 7 layers / 6 jobs (com o teto de passo, abaixo); os 3 elegíveis à chave são
#: preenchimento (símbolo em gota, retalho de hachura) — ✓ ali seria errado.
#: 🪤 Escada e corrimão NÃO são isto: degrau tem passo de 24–34 cm (≫ 3 % do
#: lance). Sem filtro de nome; anotação fica de fora.
#: 🩸 05/10 (revisão da Projetos): o FEIXE REAL em linha simples — 6
#: eletrodutos a 15 cm, 8 a 10 cm, 5 tubos a 20 cm — passava em tudo (passo
#: pequeno pro comprimento, largura < 1 m) e marcava; ali a soma É a medida, e
#: o aviso ainda mostrava o "eixo" de 30 m no lugar dos 180. O preenchimento
#: medido no acervo tem passo de 2–4 mm (hachura, símbolo) e 25 mm (as
#: eletrocalhas): teto de 50 mm. Sai junto a malha de perfil de terreno a 100
#: mm (já fora da chave por ressalva de unidade; inócua). Limite que fica
#: (teste CUSTO): feixe de eletrodutos encostados, passo ≤ 25 mm, não se separa
#: do preenchimento.
_FAIXA_ANG_TOL = 0.3          # graus
_FAIXA_GAP_MAX = 0.25         # a vizinha lateral a ≤ 0,25 L
_FAIXA_DUP = 1e-4             # mais perto que 1e-4 L é colinear, não vizinha
_FAIXA_SOBREPOE = 0.8         # sobreposição ≥ 80 % da menor
_FAIXA_RAZAO_L = 0.7          # comprimentos parecidos: menor/maior ≥ 0,7
_FAIXA_PASSO_TOL = 0.05       # passo constante: ± 5 % do 1º passo da corrente
_FAIXA_OLHA = 400             # candidatas olhadas a cada passo da corrente
_FAIXA_CORRENTE_MIN = 3       # a corrente fica (as linhas não voltam pra outra)
_FAIXA_MIN_LINHAS = 5         # ...mas só a faixa de ≥ 5 linhas conta
_FAIXA_PASSO_MAX = 0.03       # passo ≤ 3 % do comprimento da faixa
_FAIXA_LARGURA_MAX = 1.0      # (n − 1)·passo ≤ 1,0 m
_FAIXA_PASSO_MAX_MM = 50.0    # passo ≤ 50 mm: acima disso é feixe de rede, não preenchimento
_FAIXA_FRACAO = 0.6           # ≥ 60 % do metro do layer em faixas


def layers_em_faixa_de_paralelas(msp, walls, unit_factor: float = 1.0) -> dict:
    """{layer: {'m', 'fracao', 'faixas', 'linhas', 'passo_mm', 'eixo_m'}} —
    layer cujo metro é, em ≥ `_FAIXA_FRACAO`, FAIXAS de ≥ 5 linhas paralelas a
    passo constante e curto (preenchimento: a soma conta cada linha da faixa).
    `linhas` e `passo_mm` são as medianas pelo metro; `eixo_m`, a soma do
    comprimento das faixas (uma vez cada). Fora anotação. SÓ MARCA (aviso + selo)."""
    from engine_rules import layer_is_anotacao
    uf = float(unit_factor) if unit_factor else 1.0
    tot: dict = {}
    for w in walls or ():
        ly = str(getattr(w, "layer", "") or "")
        tot[ly] = tot.get(ly, 0.0) + float(getattr(w, "length", 0.0) or 0.0)
    camadas = {ly for ly, t in tot.items() if t > 0 and not layer_is_anotacao(ly)}
    if not camadas:
        return {}
    segs: dict = {}
    for e in msp.query("LINE LWPOLYLINE"):
        try:
            ly = str(e.dxf.layer)
            if ly not in camadas:
                continue
            if e.dxftype() == "LINE":
                pts = [(e.dxf.start[0], e.dxf.start[1], 0.0), (e.dxf.end[0], e.dxf.end[1], 0.0)]
            else:
                pts = [(p[0], p[1], p[2]) for p in e.get_points("xyb")]
                if e.closed and pts:
                    pts.append(pts[0])
        except Exception:
            continue
        ss = segs.setdefault(ly, [])
        for (ax, ay, blg), (bx, by, _b) in zip(pts, pts[1:]):
            if not blg and (ax != bx or ay != by):     # o lado em arco não é linha reta
                ss.append((float(ax), float(ay), float(bx), float(by)))
    _tq = 0.001 / uf     # a cópia exata em pilha conta UMA vez (H84)
    out = {}
    for ly, ss in segs.items():
        if len(ss) > _TUBO_MAX_SEG:
            logger.warning("[faixa-de-paralelas] '%s' com %d trechos — acima do teto, não medido",
                           ly, len(ss))
            continue
        vistos: set = set()
        itens = []
        tot_du = 0.0
        for ax, ay, bx, by in ss:
            ch = tuple(sorted(((round(ax / _tq), round(ay / _tq)), (round(bx / _tq), round(by / _tq)))))
            if ch in vistos:
                continue
            vistos.add(ch)
            tot_du += math.hypot(bx - ax, by - ay)
            itens.append((math.degrees(math.atan2(by - ay, bx - ax)) % 180.0, ax, ay, bx, by))
        if len(itens) < _FAIXA_MIN_LINHAS or tot_du <= 0:
            continue
        # direções: grupos de ângulo a ≤ 0,3° (o 179,9° encosta no 0°)
        itens.sort()
        grupos, atual = [], [itens[0]]
        for it in itens[1:]:
            if it[0] - atual[-1][0] <= _FAIXA_ANG_TOL:
                atual.append(it)
            else:
                grupos.append(atual)
                atual = [it]
        grupos.append(atual)
        if len(grupos) > 1 and grupos[0][0][0] + 180.0 - grupos[-1][-1][0] <= _FAIXA_ANG_TOL:
            grupos[0] = grupos.pop() + grupos[0]
        faixas = []      # (linhas, passo, comprimento médio, soma) — unidade do desenho
        for g in grupos:
            if len(g) < _FAIXA_MIN_LINHAS:
                continue
            th = math.radians(g[0][0])
            ux, uy = math.cos(th), math.sin(th)
            nx, ny = -uy, ux
            rec = sorted((((ax + bx) / 2.0) * nx + ((ay + by) / 2.0) * ny,
                          *sorted((ax * ux + ay * uy, bx * ux + by * uy)))
                         for _a, ax, ay, bx, by in g)
            n = len(rec)
            usado = [False] * n
            for i in range(n):
                if usado[i]:
                    continue
                cad, usado[i], g0 = [i], True, None
                while True:
                    r0 = rec[cad[-1]]
                    L0 = r0[2] - r0[1]
                    achou, k = None, 0
                    for j in range(cad[-1] + 1, n):
                        r = rec[j]
                        d = r[0] - r0[0]
                        if d > _FAIXA_GAP_MAX * L0:
                            break
                        k += 1
                        if k > _FAIXA_OLHA:
                            break
                        if usado[j] or d <= _FAIXA_DUP * L0:
                            continue
                        L1 = r[2] - r[1]
                        if min(L0, L1) < _FAIXA_RAZAO_L * max(L0, L1):
                            continue
                        if min(r[2], r0[2]) - max(r[1], r0[1]) < _FAIXA_SOBREPOE * min(L0, L1):
                            continue
                        achou = (d, j)
                        break
                    if achou is None:
                        break
                    if g0 is None:
                        g0 = achou[0]
                    elif abs(achou[0] - g0) > _FAIXA_PASSO_TOL * g0:
                        break
                    cad.append(achou[1])
                    usado[achou[1]] = True
                if len(cad) >= _FAIXA_CORRENTE_MIN:
                    Ls = [rec[x][2] - rec[x][1] for x in cad]
                    faixas.append((len(cad), (rec[cad[-1]][0] - rec[cad[0]][0]) / (len(cad) - 1),
                                   sum(Ls) / len(cad), sum(Ls)))
                else:
                    for x in cad[1:]:          # a corrente curta devolve as linhas
                        usado[x] = False
        boas = [f for f in faixas if f[0] >= _FAIXA_MIN_LINHAS and f[1] <= _FAIXA_PASSO_MAX * f[2]
                and (f[0] - 1) * f[1] * uf <= _FAIXA_LARGURA_MAX and f[1] * uf * 1000.0 <= _FAIXA_PASSO_MAX_MM]
        f = sum(b[3] for b in boas) / tot_du
        if f < _FAIXA_FRACAO:
            continue

        def _mediana(chave):
            """A mediana pelo METRO das faixas boas."""
            pares = sorted((chave(b), b[3]) for b in boas)
            meio, acum = sum(p for _, p in pares) / 2.0, 0.0
            for v, p in pares:
                acum += p
                if acum >= meio:
                    return v
            return pares[-1][0]
        out[ly] = {"m": round(float(tot.get(ly, 0.0)), 2), "fracao": round(min(f, 1.0), 2), "faixas": len(boas),
                   "linhas": int(_mediana(lambda b: b[0])),
                   "passo_mm": round(float(_mediana(lambda b: b[1])) * uf * 1000.0, 1),
                   "eixo_m": round(float(sum(b[2] for b in boas)) * uf, 2)}
    return out


def _corrigir_parede_linha_dupla(walls, unit_factor: float = 1.0, zona_cinza=None,
                                 faces_espessas=None):
    """Parede desenhada pelas DUAS FACES mede pelo EIXO. Devolve (walls, relato).

    `faces_espessas` (lista, saída): (segmento já corrigido, metros da sobra) das
    faces da parede de mais de 40 cm, que o eixo não junta (E12, 04/10) — vai
    para `parede_espessa_na_soma` depois da leitura por folha.

    🩸 26/09/2026 — job befab5aa (interiores): a planilha trouxe "pintura
    1.977 m²" = "659 m × 3 m de pé-direito, por face". Os 659 m eram a SOMA
    DAS LINHAS do layer PAREDE — e 79% delas vinham em pares de face (5–30 cm):
    pelo eixo, a mesma versão do apartamento tem ~383 m. A soma das faces ×
    pé-direito é ≈ as DUAS faces, não uma; e toda linha "parede (ml) ✓" de DWG
    com parede em duas faces saía 1,5–2× maior. No acervo local, os layers de
    parede tinham 55–73% do comprimento em pares (3 de 4 arquivos).

    Mesma máquina do leito/duto (pares por TRECHO, tampa nas pontas, polilinha
    pelos lados), só em layer de parede (`engine_rules.layer_e_parede`) e com
    seção até 40 cm. Parede de linha ÚNICA não tem par e fica como está. A
    ressalva de hachura do duto NÃO vale aqui: ela rebaixa o desenho inteiro e
    parede com padrão gráfico no layer é caso de outra régua.
    """
    from engine_rules import layer_e_parede
    _esp = {} if faces_espessas is not None else None
    novos, relato, _ressalva = _corrigir_duto_linha_dupla(
        walls, unit_factor, escolhe=layer_e_parede, sep_max_m=_PAREDE_SEP_MAX,
        min_seg_m=_PAREDE_MIN_SEG, min_fracao_par=_PAREDE_MIN_FRACAO_PAR,
        zona_cinza=zona_cinza, junta_face_fina=True, max_seg=_PAREDE_MAX_SEG_LAYER,
        faces_espessas=_esp)
    if _esp:
        # a saída tem a mesma ordem da entrada: o índice aponta o segmento novo
        faces_espessas.extend((novos[i], s) for i, s in sorted(_esp.items()))
    return novos, relato


def parede_espessa_na_soma(walls, faces_espessas) -> dict:
    """{layer: {"sobra_m", "fracao"}} — o layer de parede em que as faces da
    parede de mais de 40 cm põem na SOMA pelo menos 5 m e 5 % a mais (E12).

    Conta o que ficou depois da leitura por folha: a face que saiu (corte,
    detalhe) não conta, e a da planta de N andares conta N vezes, como a soma.
    🔒 Só registro e ressalva: nenhuma soma muda."""
    try:
        vivos = {id(w): w for w in walls}
        sobra, soma = {}, {}
        for w, s in faces_espessas or ():
            if vivos.get(id(w)) is w:
                sobra[w.layer] = sobra.get(w.layer, 0.0) + s * getattr(w, "peso", 1.0)
        if not sobra:
            return {}
        for w in walls:
            if w.layer in sobra:
                soma[w.layer] = soma.get(w.layer, 0.0) + w.length * getattr(w, "peso", 1.0)
        out = {}
        for ly, s in sobra.items():
            tot = soma.get(ly, 0.0)
            if tot > 0 and s >= _PAREDE_ESPESSA_SOBRA_MIN_M and s >= _PAREDE_ESPESSA_FRACAO_MIN * tot:
                out[ly] = {"sobra_m": round(float(s), 1), "fracao": round(float(s / tot), 2)}
        return out
    except Exception as e:                       # nunca derruba a extração
        logger.warning("parede_espessa_na_soma: %s", e)
        return {}


_RE_RELATO_EIXO = re.compile(r"^(.*): [\d.]+m de face -> [\d.]+m de eixo \(\d+ par\(es\)\)$")


def _relato_do_eixo_na_soma(relato: str, walls, espessas=None, corte_fora=True, faixas=None,
                            so_faixas=False) -> str:
    """Reescreve o relato do eixo com o que FICOU na soma (depois da folha).

    Sem número de antes: número que não está na soma vira quantidade na mão
    da IA. Trecho que não casa o formato fica como veio.

    🩸 04/10/2026 (E12): o texto dizia sempre "JÁ pelo EIXO (… corte e detalhe
    já fora)" e a IA copiava com ✓ — numa prancha em que a parede de 50 cm
    somava as duas faces e o corte não tinha sido reconhecido. Agora:
    `espessas` (layers de `parede_espessa_na_soma`) diz que parte da soma NÃO é
    eixo; "corte e detalhe já fora" só com `corte_fora` (a leitura por folha
    rodou e reconheceu corte ou detalhe).
    🩸 05/10 (E07): o layer em `faixas` (`layers_em_faixa_de_paralelas`) é
    preenchimento — nem "JÁ pelo EIXO" nem "de eixo". `so_faixas` reescreve SÓ
    esses (quando a folha não rodou, os outros ficam como vieram)."""
    try:
        novos = []
        for trecho in (relato or "").split(" | "):
            m = _RE_RELATO_EIXO.match(trecho.strip())
            if not m or (so_faixas and m.group(1) not in (faixas or ())):
                novos.append(trecho)
                continue
            lay = m.group(1)
            atual = sum(w.length * getattr(w, "peso", 1.0) for w in walls if w.layer == lay)
            if atual < 0.05:
                novos.append(f"{lay}: desenhado em 2 linhas, mas todo o traçado desta prancha "
                             f"está em corte/detalhe/planta-chave — NADA deste layer entra "
                             f"na soma desta prancha")
            elif lay in (faixas or ()):
                novos.append(f"{lay}: {atual:.1f}m na soma — desenhado como FAIXA de linhas "
                             f"paralelas (preenchimento), cada linha somada: este número NÃO é "
                             f"o comprimento — trate como ESTIMADO")
            elif lay in (espessas or ()):
                novos.append(f"{lay}: {atual:.1f}m na soma — as paredes de até 40 cm pelo "
                             f"EIXO, mas parte da soma são paredes de MAIS de 40 cm contadas "
                             f"pelas DUAS faces: este número NÃO é o comprimento das paredes")
            else:
                novos.append(f"{lay}: {atual:.1f}m na soma, JÁ pelo EIXO (as 2 bordas contadas "
                             f"uma vez{'; corte e detalhe já fora' if corte_fora else ''})")
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

    # 🩸 30/09: antes do mm às cegas, a nota do desenho ("MEDIDAS EM
    # CENTÍMETROS") — só com a cota explodida confirmando. Job 9a2c5d87.
    pela_nota, _det_nota = _unidade_pela_nota_e_cota_explodida(doc)
    if pela_nota is not None:
        return pela_nota

    # Default for Brazilian architecture: millimeters
    # 🔑 30/09: marca que o fator é o PALPITE — sem cota que o prove, o que
    # depende de escala não sai medido (`ressalva_da_unidade_cega`).
    try:
        setattr(doc, "_aiarq_unidade_palpite", True)
    except Exception:
        pass
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
        plausiveis = [f for f in (0.01, 1.0) if lo <= largura * f <= hi]   # cm, metros
        if not plausiveis:
            return None
        fator = plausiveis[0]
        if len(plausiveis) > 1:
            # 🩸 29/09/2026 — cm E metro plausíveis: a largura não decide. O
            # "menor fator" errou os DOIS desenhos que caíram aqui em 90 dias
            # (as cotas de um corrigiram pra metro; o outro, 8 pranchas lado a
            # lado no modelo, ficou 100× pequeno). Os OBJETOS do desenho
            # desempatam — ver `_fator_pelos_objetos`. Sem voto claro, fica o
            # menor, como antes.
            voto, _det = _fator_pelos_objetos(doc, plausiveis)
            if voto is not None:
                fator = voto
        logger.warning(
            "[unit-inferida] $INSUNITS=0 e mm daria %.2f m de largura "
            "(absurdo) — adotando fator %s (%.0f m de largura)",
            largura * 0.001, fator, largura * fator)
        return fator
    except Exception:
        return None


#: Tamanho de objeto físico, em metros: do símbolo de tomada à vaga e ao carro.
_OBJETO_FISICO_M = (0.05, 8.0)
#: Menos tipos de bloco que isto não é evidência (legenda, carimbo, 2 símbolos).
_OBJETOS_MIN_TIPOS = 8
#: O fator vencedor precisa pôr esta fração dos tipos no tamanho de objeto…
_OBJETOS_PISO = 0.6
#: …e pelo menos este múltiplo da fração do outro.
_OBJETOS_RAZAO = 2.0


def _fator_pelos_objetos(doc, candidatos):
    """Qual dos fatores `candidatos` faz os BLOCOS do desenho terem tamanho de
    objeto físico? Devolve (fator ou None, detalhe).

    Cada TIPO de bloco inserido no modelo vota uma vez, com a mediana do seu
    tamanho real (definição × escala de inserção): 70 luminárias iguais são um
    voto, não 70. Ganha o fator que põe ≥ 60% dos tipos entre 5 cm e 8 m e pelo
    menos o dobro da fração do outro; senão None.

    🩸 29/09/2026 (job 6437838e). Mesa "CONJ MESA 1.40M" = 1,400 unidades, vaga
    5,0 × 3,7, bacia 0,62: o desenho estava em METROS e a largura escolheu cm
    (8 pranchas lado a lado no modelo = 1.584 unidades). Em cm, os 75 tipos
    dariam 13% de objetos; em metro, 96%.
    📏 Acervo local (90 DXF): onde a votação decidiu entre cm e m, acertou TODOS
    os que declaravam cm ou m (~45) e os 2 que declaravam mm mas eram metro (a
    produção corrigiu os dois depois, por cotas e por plausibilidade).
    🔑 Só escolhe entre cm e m (100× de distância). Entre mm e cm (10×) a
    faixa de objeto não separa — por isso esta função só desempata.
    """
    chave = tuple(candidatos)
    guardado = getattr(doc, "_aiarq_voto_objetos", None)
    if guardado and guardado[0] == chave:
        return guardado[1]            # a decisão e o log do cabeçalho perguntam o mesmo
    res = _votar_pelos_objetos(doc, candidatos)
    try:
        setattr(doc, "_aiarq_voto_objetos", (chave, res))
    except Exception:
        pass
    return res


def _votar_pelos_objetos(doc, candidatos):
    detalhe = {"tipos": 0}
    try:
        from ezdxf import bbox as _bb
        from statistics import median as _med
        caixa, por_tipo = {}, {}
        for ins in doc.modelspace().query("INSERT"):
            nome = ins.dxf.name
            if not nome or nome.startswith("*"):
                continue                               # anônimo: hachura, cota, grupo
            if nome not in caixa:
                caixa[nome] = None
                blk = doc.blocks.get(nome)
                try:
                    if blk is not None and not blk.block.is_xref:
                        ext = _bb.extents(blk, fast=True)
                        if ext.has_data:
                            caixa[nome] = (ext.size.x, ext.size.y)
                except Exception:
                    caixa[nome] = None
            wh = caixa[nome]
            if not wh:
                continue
            s = max(wh[0] * abs(ins.dxf.xscale or 1.0), wh[1] * abs(ins.dxf.yscale or 1.0))
            if s > 0:
                por_tipo.setdefault(nome, []).append(s)
        tams = [_med(v) for v in por_tipo.values()]
        detalhe["tipos"] = len(tams)
        if len(tams) < _OBJETOS_MIN_TIPOS:
            return None, detalhe
        lo, hi = _OBJETO_FISICO_M
        frac = {f: sum(1 for s in tams if lo <= s * f <= hi) / len(tams) for f in candidatos}
        detalhe["fracoes"] = {str(f): round(v, 2) for f, v in frac.items()}
        melhor = max(frac, key=frac.get)
        outros = [v for f, v in frac.items() if f != melhor]
        if frac[melhor] >= _OBJETOS_PISO and all(
                frac[melhor] >= _OBJETOS_RAZAO * max(v, 0.01) for v in outros):
            detalhe["escolha"] = melhor
            return melhor, detalhe
        return None, detalhe
    except Exception:
        return None, detalhe


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
        # 29/09: na faixa em que cm E metro são plausíveis, o voto dos objetos
        # vai pro log (é ele que decide ali — ver `_fator_pelos_objetos`)
        try:
            if int(d.get("insunits", 0) or 0) == 0 and d.get("ext"):
                _larg = max(d["ext"])
                _lo, _hi = _EXTENSAO_PLAUSIVEL_M
                _pl = [f for f in (0.01, 1.0) if _lo <= _larg * f <= _hi]
                if len(_pl) > 1 and _larg * 0.001 < _MM_ACEITAVEL_ATE_M:
                    d["objetos"] = _fator_pelos_objetos(doc, _pl)[1]
        except Exception:
            pass
        # 30/09: quando o fator caiu no mm por falta de evidência, a nota do
        # desenho + a cota explodida vão pro log (é ela que decide ali)
        try:
            _nc = getattr(doc, "_aiarq_nota_cota", None)
            if _nc:
                d["nota_cota"] = _nc[1]
        except Exception:
            pass
    except Exception:
        pass
    return d


#: "MEDIDAS EM CENTÍMETROS", "COTAS EM MM", "DIMENSÕES EM METROS"… — a NOTA
#: geral que diz em que unidade estão as cotas. Texto já sem acento e em
#: maiúsculas. 🪤 "COTAS DE NÍVEIS EM METROS" (nível, não comprimento) não casa:
#: o verbo vem colado em MEDIDAS/COTAS/DIMENSÕES.
_RE_NOTA_UNIDADE = re.compile(
    r"\b(?:MEDIDAS|COTAS|DIMENSOES)\s+(?:(?:ESTAO|SAO|DADAS|EXPRESSAS|INDICADAS)\s+)?EM\s+"
    r"(CENTIMETROS?|CM|MILIMETROS?|MM|METROS?|M)\b")
_NOTA_UNIDADE_FATOR = {"CENTIMETRO": 0.01, "CENTIMETROS": 0.01, "CM": 0.01,
                       "MILIMETRO": 0.001, "MILIMETROS": 0.001, "MM": 0.001,
                       "METRO": 1.0, "METROS": 1.0, "M": 1.0}
_RE_TEXTO_DE_COTA = re.compile(r"^\s*(\d{1,5}(?:[.,]\d{1,3})?)\s*$")
#: valor do texto ÷ comprimento da linha: a cota escreve na unidade da nota,
#: a linha mede na unidade do modelo — a razão é uma potência de 10.
_RAZOES_DE_COTA = (1.0, 10.0, 100.0, 1000.0, 0.1, 0.01, 0.001)
#: Menos cota explodida que isto não é evidência.
_COTAS_EXPLODIDAS_MIN = 8
#: A razão vencedora precisa desta fração das cotas que casaram.
_COTAS_EXPLODIDAS_ACORDO = 0.8
#: Teto de textos numéricos examinados (desenho enorme não trava a leitura).
_COTAS_EXPLODIDAS_MAX_TEXTOS = 4000


def _texto_normalizado(ent) -> str:
    try:
        s = ent.dxf.text if ent.dxftype() == "TEXT" else ent.plain_text()
    except Exception:
        return ""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).upper()
    return re.sub(r"\s+", " ", s)


def _notas_de_unidade(msp) -> dict:
    """{fator: vezes} das notas "MEDIDAS/COTAS/DIMENSÕES EM <unidade>" do modelo."""
    achadas: dict = {}
    for t in msp.query("TEXT MTEXT"):
        for m in _RE_NOTA_UNIDADE.finditer(_texto_normalizado(t)):
            f = _NOTA_UNIDADE_FATOR[m.group(1)]
            achadas[f] = achadas.get(f, 0) + 1
    return achadas


def _cotas_explodidas_casadas(msp) -> list:
    """[(layer da linha, comprimento, razão)] — uma entrada por LINHA de cota
    explodida: o texto numérico colado a uma linha paralela, e a razão é o
    valor escrito ÷ o comprimento da linha no modelo (uma potência de 10).

    Linha mais próxima do centro do texto, paralela (±5°), a até 3 alturas de
    texto e dentro do trecho. O texto da cota é arredondado: tolerância de
    meia unidade da última casa (ou 0,6%). É a MESMA régua para a unidade
    (`_cotas_explodidas`) e para o layer de cota (`layers_de_cota_explodida`).
    """
    linhas = []
    for e in msp.query("LINE"):
        a, b = e.dxf.start, e.dxf.end
        L = math.hypot(b.x - a.x, b.y - a.y)
        if L > 0:
            linhas.append((a.x, a.y, b.x, b.y, L, e.dxf.layer))
    if not linhas:
        return []
    textos = []
    for t in msp.query("TEXT"):
        try:
            m = _RE_TEXTO_DE_COTA.match(t.dxf.text or "")
        except Exception:
            m = None
        if m and float(m.group(1).replace(",", ".")) > 0:
            textos.append((t, m))
            if len(textos) >= _COTAS_EXPLODIDAS_MAX_TEXTOS:
                break
    if not textos:
        return []
    comps = sorted(l[4] for l in linhas)
    alts = sorted(float(t.dxf.get("height", 0) or 0) or 1.0 for t, _m in textos)
    # 🪤 a célula acompanha a linha E a letra: linha curta com letra grande
    # faria cada texto varrer milhares de células
    cel = max(comps[len(comps) // 2] * 2, alts[len(alts) // 2] * 3, 1e-9)
    grade: dict = {}
    for i, (x1, y1, x2, y2, _L, _ly) in enumerate(linhas):
        grade.setdefault((int(((x1 + x2) / 2) // cel), int(((y1 + y2) / 2) // cel)), []).append(i)
    casadas: dict = {}
    for t, m in textos:
        s = m.group(1).replace(",", ".")
        v = float(s)
        h = float(t.dxf.get("height", 0) or 0) or 1.0
        rot = math.radians(float(t.dxf.get("rotation", 0) or 0))
        ux, uy = math.cos(rot), math.sin(rot)
        nch = len(m.group(1))
        px = t.dxf.insert.x + ux * 0.45 * h * nch - uy * 0.5 * h
        py = t.dxf.insert.y + uy * 0.45 * h * nch + ux * 0.5 * h
        melhor = None
        gx, gy = int(px // cel), int(py // cel)
        alc = min(int(max(1, math.ceil(3 * h / cel))) + 1, 6)
        for ix in range(gx - alc, gx + alc + 1):
            for iy in range(gy - alc, gy + alc + 1):
                for i in grade.get((ix, iy), ()):
                    x1, y1, x2, y2, L, _ly = linhas[i]
                    dxl, dyl = (x2 - x1) / L, (y2 - y1) / L
                    if abs(dxl * uy - dyl * ux) > 0.09:          # não paralela (> ~5°)
                        continue
                    rx, ry = px - x1, py - y1
                    ao_longo = rx * dxl + ry * dyl
                    perp = abs(rx * dyl - ry * dxl)
                    if perp > 3 * h or ao_longo < -h or ao_longo > L + h:
                        continue
                    if melhor is None or perp < melhor[0]:
                        melhor = (perp, i)
        if melhor is None or melhor[1] in casadas:
            continue
        L = linhas[melhor[1]][4]
        casas = len(s.split(".")[1]) if "." in s else 0
        tol = max(0.006 * v, 0.5 * 10 ** (-casas))
        for k in _RAZOES_DE_COTA:
            if abs(v - L * k) <= tol:
                casadas[melhor[1]] = k
                break
    return [(linhas[i][5], linhas[i][4], k) for i, k in casadas.items()]


def _cotas_explodidas(msp) -> dict:
    """{razão: cotas} das cotas explodidas do modelo (`_cotas_explodidas_casadas`)."""
    votos: dict = {}
    for _ly, _L, k in _cotas_explodidas_casadas(msp):
        votos[k] = votos.get(k, 0) + 1
    return votos


#: Layer em que as linhas de cota são esta fração do comprimento é layer de
#: COTA: o resto são as linhas de chamada e os traços das pontas.
_LAYER_DE_COTA_FRACAO = 0.5


def layers_de_cota_explodida(msp) -> dict:
    """{layer: {"cotas": n, "fracao": f}} — layer cujas linhas são, na maioria,
    COTA EXPLODIDA (o texto com o valor ao lado de cada uma).

    🩸 30/09/2026 (job 9a2c5d87). O layer "250" era só cota: 276 linhas com o
    valor escrito ao lado, 73% do comprimento (o resto, linha de chamada). Nome
    de layer não diz nada ("250"), e a régua de anotação lê só o NOME — a soma
    das cotas (787 m) virou "comprimento de linhas de modulação" ✓ MEDIDO.
    Aqui a prova é o desenho: ≥ 8 cotas e ≥ 50% do comprimento do layer.
    """
    try:
        cas = _cotas_explodidas_casadas(msp)
        if not cas:
            return {}
        tot: dict = {}
        for e in msp.query("LINE"):
            a, b = e.dxf.start, e.dxf.end
            tot[e.dxf.layer] = tot.get(e.dxf.layer, 0.0) + math.hypot(b.x - a.x, b.y - a.y)
        cot: dict = {}
        n: dict = {}
        for ly, L, _k in cas:
            cot[ly] = cot.get(ly, 0.0) + L
            n[ly] = n.get(ly, 0) + 1
        out = {}
        for ly, c in cot.items():
            f = c / tot[ly] if tot.get(ly) else 0.0
            if n[ly] >= _COTAS_EXPLODIDAS_MIN and f >= _LAYER_DE_COTA_FRACAO:
                out[ly] = {"cotas": n[ly], "fracao": round(f, 2)}
        return out
    except Exception:
        return {}


#: Quantas peças iguais no mesmo layer fazem um "objeto repetido".
_OBJETOS_SEM_BLOCO_MIN = 10
#: Faixa de tamanho de peça, em metros (lado do retângulo / raio do círculo).
_OBJETO_SEM_BLOCO_M = (0.02, 20.0)
_CIRCULO_SEM_BLOCO_M = (0.002, 2.0)
#: Layer cujo comprimento é, nesta fração, a BORDA dessas peças.
_LAYER_DE_BORDA_FRACAO = 0.8
#: Círculo com TEXTO dentro é balão (vista, eixo, chamada), não peça — nesta
#: fração do grupo, o grupo inteiro sai.
_CIRCULO_BALAO_FRACAO = 0.5
#: Grupo PEQUENO (diagonal da caixa < esta fração da diagonal do desenho) e
#: com um texto de legenda por perto: provável legenda ou detalhe (a IA é
#: avisada; nada é apagado). 🪤 Só tamanho não basta: as luminárias de uma sala
#: pequena num desenho grande também cabem num canto.
_PECAS_LEGENDA_DIAGONAL = 0.1
_RE_TITULO_DE_LEGENDA = re.compile(
    r"\b(LEGENDA|FAMILIA|DETALHE|PERSPECTIVA|ESQUEMA|SEPTO|CONVENC|SIMBOLOGIA)")


def _diagonal_do_desenho(msp) -> float:
    """Diagonal (unidades do modelo) da extensão do cabeçalho; 0 se não houver ou
    se for a extensão vazia de desenho novo (EXTMIN > EXTMAX, ±1e20)."""
    try:
        h = msp.doc.header
        a, b = h.get("$EXTMIN"), h.get("$EXTMAX")
        if a and b and b[0] > a[0] and b[1] > a[1] and max(map(abs, (a[0], a[1], b[0], b[1]))) < 1e15:
            return float(math.hypot(b[0] - a[0], b[1] - a[1]))
    except Exception:
        pass
    return 0.0


def _pontos_de_legenda(msp) -> list:
    """Onde estão os títulos de legenda/detalhe ("LEGENDA", "FAMÍLIA DE BLOCOS"…)."""
    pts = []
    for t in msp.query("TEXT MTEXT"):
        try:
            if _RE_TITULO_DE_LEGENDA.search(_texto_normalizado(t)):
                pts.append((t.dxf.insert.x, t.dxf.insert.y))
        except Exception:
            continue
    return pts


def _na_legenda(centros, pts_legenda, diag_des) -> bool:
    """Grupo pequeno E com título de legenda dentro da caixa alargada? Provável legenda."""
    if not centros or not pts_legenda or diag_des <= 0:
        return False
    xs = [c[0] for c in centros]
    ys = [c[1] for c in centros]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    d = math.hypot(w, h)
    if d >= _PECAS_LEGENDA_DIAGONAL * diag_des:
        return False
    folga = max(d, 0.02 * diag_des)
    return bool(any(min(xs) - folga <= x <= max(xs) + folga and min(ys) - folga <= y <= max(ys) + folga
                    for x, y in pts_legenda))


def _pontos_de_texto(msp) -> list:
    """Pontos de inserção (e de alinhamento) dos TEXT/MTEXT do modelo."""
    pts = []
    for t in msp.query("TEXT MTEXT"):
        try:
            pts.append((t.dxf.insert.x, t.dxf.insert.y))
            if t.dxftype() == "TEXT" and t.dxf.hasattr("align_point"):
                pts.append((t.dxf.align_point.x, t.dxf.align_point.y))
        except Exception:
            continue
    return pts


def _fracao_com_texto_dentro(circulos, pontos) -> float:
    """Fração dos círculos (x, y, raio) que têm algum ponto de texto dentro."""
    if not circulos:
        return 0.0
    r0 = max(c[2] for c in circulos) * 1.05 or 1.0
    grade: dict = {}
    for x, y in pontos:
        grade.setdefault((int(x // r0), int(y // r0)), []).append((x, y))
    com = 0
    for x, y, r in circulos:
        gx, gy = int(x // r0), int(y // r0)
        achou = False
        for ix in (gx - 1, gx, gx + 1):
            for iy in (gy - 1, gy, gy + 1):
                for px, py in grade.get((ix, iy), ()):
                    if math.hypot(px - x, py - y) <= r * 1.05:
                        achou = True
                        break
                if achou:
                    break
            if achou:
                break
        com += achou
    return com / len(circulos)


def objetos_repetidos_sem_bloco(msp, unit_factor) -> dict:
    """{layer: [peça, ...]} — o objeto desenhado PEÇA POR PEÇA, sem bloco:
    retângulo (polilinha fechada de 4 lados) ou círculo do MESMO tamanho,
    repetido ≥ 10 vezes no mesmo layer. Cada peça: {"forma", "a_cm", "b_cm"
    (retângulo) ou "r_cm" (círculo), "n", "borda_m"}.

    🩸 30/09/2026 (job 9a2c5d87, planta de modulação da 1ª fiada). Os 776
    blocos de 19 × 39 e os 787 furos de graute de 14 × 14 estavam desenhados um
    a um, como retângulo — e a IA só via o COMPRIMENTO do layer (939 m, 441 m:
    a soma das bordas), que virou "linhas de modulação" ✓ MEDIDO. A contagem,
    que é o que se orça, não chegava.
    """
    out: dict = {}
    try:
        from engine_rules import layer_is_anotacao, layer_is_carimbo
        uf = float(unit_factor or 0)
        if uf <= 0:
            return {}
        # 🪤 layer de anotação/carimbo não é peça: no acervo, 84 quadrados de
        # "CHAMADA" (balão de chamada) e as amostras da legenda de piso
        _fora: dict = {}

        def _e_peca(ly):
            if ly not in _fora:
                _fora[ly] = bool(layer_is_anotacao(ly) or layer_is_carimbo(ly))
            return not _fora[ly]
        ret: dict = {}
        for e in msp.query("LWPOLYLINE"):
            try:
                crus = [(p[0], p[1]) for p in e.get_points("xy")]
            except Exception:
                continue
            if len(crus) == 5 and math.hypot(crus[0][0] - crus[-1][0], crus[0][1] - crus[-1][1]) < 1e-9:
                pts = crus[:4]                            # fechada repetindo o 1º ponto
            elif len(crus) == 4 and e.closed:
                pts = crus
            else:
                continue
            lados = [math.hypot(pts[(i + 1) % 4][0] - pts[i][0], pts[(i + 1) % 4][1] - pts[i][1])
                     for i in range(4)]
            d1 = math.hypot(pts[2][0] - pts[0][0], pts[2][1] - pts[0][1])
            d2 = math.hypot(pts[3][0] - pts[1][0], pts[3][1] - pts[1][1])
            if min(lados) <= 0 or abs(d1 - d2) > 0.01 * max(d1, d2):
                continue                                  # não é retângulo
            if abs(lados[0] - lados[2]) > 0.01 * lados[0] or abs(lados[1] - lados[3]) > 0.01 * lados[1]:
                continue
            a, b = sorted((lados[0] * uf, lados[1] * uf))
            if a < _OBJETO_SEM_BLOCO_M[0] or b > _OBJETO_SEM_BLOCO_M[1]:
                continue
            if not _e_peca(e.dxf.layer):
                continue
            k = (e.dxf.layer, round(a * 1000), round(b * 1000))       # mm
            ret.setdefault(k, []).append((sum(p[0] for p in pts) / 4, sum(p[1] for p in pts) / 4))
        diag_des = _diagonal_do_desenho(msp)
        pts_leg = _pontos_de_legenda(msp) if diag_des > 0 else []
        for (ly, a, b), cs in ret.items():
            n = len(cs)
            if n >= _OBJETOS_SEM_BLOCO_MIN:
                out.setdefault(ly, []).append({"forma": "retângulo", "a_cm": a / 10, "b_cm": b / 10,
                                               "n": n, "borda_m": round(n * 2 * (a + b) / 1000, 2),
                                               "concentrada": _na_legenda(cs, pts_leg, diag_des)})
        cir: dict = {}
        for e in msp.query("CIRCLE"):
            r = float(e.dxf.radius) * uf
            if not (_CIRCULO_SEM_BLOCO_M[0] <= r <= _CIRCULO_SEM_BLOCO_M[1]):
                continue
            if not _e_peca(e.dxf.layer):
                continue
            k = (e.dxf.layer, round(r * 1000))
            cir.setdefault(k, []).append((e.dxf.center.x, e.dxf.center.y, float(e.dxf.radius)))
        _txt = None
        for (ly, r), cs in cir.items():
            n = len(cs)
            if n < _OBJETOS_SEM_BLOCO_MIN:
                continue
            # 🩸 30/09 (filhote evefe9af): 26 balões de "VISTA" e 10 bolinhas de
            # eixo viraram "pilar circular Ø50,6 / Ø60 — ✓". Todos com texto
            # dentro; as 1.634 barras de aço do mesmo desenho, nenhum.
            if _txt is None:
                _txt = _pontos_de_texto(msp)
            if _fracao_com_texto_dentro(cs, _txt) >= _CIRCULO_BALAO_FRACAO:
                continue
            out.setdefault(ly, []).append({"forma": "círculo", "r_cm": r / 10, "n": n,
                                           "borda_m": round(n * 2 * math.pi * r / 1000, 2),
                                           "concentrada": _na_legenda([(c[0], c[1]) for c in cs],
                                                                      pts_leg, diag_des)})
        for ly in out:
            out[ly].sort(key=lambda p: -p["n"])
    except Exception:
        return {}
    return out


def layers_de_borda_de_objeto(objetos, walls_by_layer) -> dict:
    """{layer: fração} — layer cujo comprimento é, quase todo, a BORDA das
    peças repetidas (`objetos_repetidos_sem_bloco`): o número é perímetro de
    peça, não elemento linear de obra."""
    out = {}
    try:
        for ly, pecas in (objetos or {}).items():
            tot = float((walls_by_layer or {}).get(ly) or 0)
            if tot <= 0:
                continue
            borda = sum(p.get("borda_m", 0) for p in pecas if p.get("forma") == "retângulo")
            f = borda / tot
            if f >= _LAYER_DE_BORDA_FRACAO:
                out[ly] = round(min(f, 1.0), 2)
    except Exception:
        return {}
    return out


def _unidade_pela_nota_e_cota_explodida(doc):
    """(fator ou None, detalhe) — a unidade pela NOTA do desenho, SÓ se as
    cotas desenhadas à mão (explodidas) confirmarem.

    🩸 30/09/2026 (job 9a2c5d87, alvenaria de embasamento). DWG sem $INSUNITS,
    sem uma cota de verdade (DIMENSION) e 4.205 unidades de largura: o mm dava
    4,2 m, passava no freio de 2 m, e ficou mm. Era CENTÍMETRO — a nota do
    próprio desenho dizia "1 - MEDIDAS EM CENTÍMETROS", e 278 de 279 cotas
    explodidas (a linha de 101 com o texto "101" ao lado) davam razão 1. As
    3 linhas com "✓ MEDIDO" saíram 10× pequenas.
    🔑 A nota SOZINHA não basta: "medidas em cm" com o modelo em metro e a cota
    em cm (DIMLFAC 100) é comum. É a cota explodida que liga a nota ao modelo:
    fator = razão × unidade da nota. Duas notas de unidades diferentes, poucas
    cotas ou cotas sem acordo → None.
    Só é chamada quando o fator ia cair no mm por falta de evidência
    (`_detect_unit_factor`).
    """
    guardado = getattr(doc, "_aiarq_nota_cota", None)
    if guardado is not None:
        return guardado
    det: dict = {}
    res = (None, det)
    try:
        msp = doc.modelspace()
        notas = _notas_de_unidade(msp)
        det["notas"] = {str(k): v for k, v in notas.items()}
        if len(notas) == 1:
            f_nota = next(iter(notas))
            votos = _cotas_explodidas(msp)
            det["cotas"] = {str(k): v for k, v in votos.items()}
            tot = sum(votos.values())
            if tot >= _COTAS_EXPLODIDAS_MIN:
                k, qn = max(votos.items(), key=lambda kv: kv[1])
                f = round(k * f_nota, 6)
                if qn >= _COTAS_EXPLODIDAS_ACORDO * tot and f in (0.001, 0.01, 1.0):
                    det["escolha"] = f
                    res = (f, det)
    except Exception:
        res = (None, det)
    try:
        setattr(doc, "_aiarq_nota_cota", res)
    except Exception:
        pass
    return res


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


def ressalva_da_escala_ambigua(dim_check) -> str:
    """Texto da ressalva quando a régua das cotas terminou "ambigua" ('' se não).

    🩸 27/09/2026 — "ambigua" = MAIS DE UM fator bateu com as cotas e nenhuma
    régua desempatou: o fator ficou o do cabeçalho, sem prova. Isso É ressalva
    de escala (m/m²/m³ não sai medido — nem pela IA nem pela chave do selo).
    📏 No acervo: 4 arquivos em 3 jobs, 17 selos em m/m²/m³ que ninguém avisou
    (ex.: elétrica industrial, prancha de corte com 352 m de leito ✓).
    "nao-decidiu" NÃO entra: ali o cabeçalho é a única régua e costuma estar
    certo (80 arquivos, 28 jobs).
    """
    if not dim_check or dim_check.get("status") != "ambigua":
        return ""
    return str(dim_check.get("motivo")
               or "mais de um fator de unidade bate com as cotas")[:200]


def ressalva_da_unidade_por_desempate(voto_guardado, status_da_regua) -> str:
    """Texto da ressalva quando o fator veio do DESEMPATE cm × metro ('' se não).

    `voto_guardado` = o que `_fator_pelos_objetos` deixou no documento:
    (candidatos, (fator ou None, detalhe)) — só existe quando a largura não
    decidiu. As cotas que VALIDARAM ou CORRIGIRAM o fator provam a escala: aí
    não há ressalva.
    """
    if not voto_guardado or status_da_regua in ("validada", "corrigida"):
        return ""
    try:
        fator, det = voto_guardado[1]
        fr = (det or {}).get("fracoes") or {}
    except Exception:
        return ""
    if fator is None:
        return ("o arquivo não diz a unidade e a largura cabe em centímetro e em "
                "metro; sem objetos que decidissem, lemos em centímetro")
    nome = "metro" if fator == 1.0 else "centímetro"
    return ("o arquivo não diz a unidade e a largura cabe em centímetro e em metro; "
            "pelo tamanho dos objetos desenhados (móveis, louças, vagas) lemos em %s "
            "(%d%% dos tipos com tamanho real) — nenhuma cota confirmou"
            % (nome, round(100 * float(fr.get(str(fator), 0) or 0))))


def ressalva_da_unidade_cega(palpite, status_da_regua) -> str:
    """Texto da ressalva quando o fator é o PALPITE de milímetro ('' se não).

    🩸 30/09/2026 (job 9a2c5d87). Sem $INSUNITS, sem cota, sem nota: o motor
    lê em mm porque é o mais comum — e o selo carimbava "✓ MEDIDO" em cima
    disso, com o aviso "escala não conferida" no resumo da mesma planilha. O
    desenho era em cm: as 3 medidas saíram 10× pequenas. `palpite` é a marca
    que `_detect_unit_factor` deixa no documento; cota que VALIDOU ou CORRIGIU
    prova a escala e aí não há ressalva.
    """
    if not palpite or status_da_regua in ("validada", "corrigida", "corrigida_lfac",
                                          "provada_por_rotulo", "corrigida_plausibilidade"):
        return ""
    return ("o arquivo não diz a unidade e nenhuma cota ou nota do desenho a "
            "confirmou; lemos em milímetro, o mais comum — confira uma medida "
            "conhecida antes de usar comprimentos e áreas")


# ---------------------------------------------------------------------------
# UNIDADE CONTRADITA PELA ESPESSURA DA PAREDE
# ---------------------------------------------------------------------------
# 🩸 30/09/2026 — H51 do estudo do acervo. Desenho em CENTÍMETRO com o
# cabeçalho dizendo MILÍMETRO ($INSUNITS = 4): tudo sai 10× menor, e com selo.
# 3 jobs de cliente (2 clientes), todos com a régua de cotas "não-decidiu":
# "parede de alvenaria 49,51 ml ✓" (real ≈ 495 m) — aprovada pelo cliente —,
# laje ×100; numa casa de 46,79 m², "tubulação 1,42 m ✓".
# A PAREDE entrega a unidade: as duas faces ficam a 5–35 cm uma da outra. Lido
# em mm, o par desses desenhos dava 1,0–2,0 cm; nos 17 desenhos certos da
# varredura do estudo, 16–20 cm.
# v1: DETECTA e vira ressalva de ESCALA (m/m²/m³ sem selo + aviso). NÃO troca o
# fator: um dos arquivos mistura cm (a planta) e mm (um detalhe distante) — não
# há um fator que sirva pro desenho inteiro.
# 🪤 Só age com a unidade NÃO provada: linha de reboco a 3–4 cm da face deu
# moda "fina" num desenho certo (1 falso alarme na varredura) — lá as cotas
# provaram o metro.
# 🪤 Só no sentido "fina demais" (×10, ×100). O "grossa demais" pegou layer de
# VISTA (63/50 cm), e parede de linha única não tem par pra medir.
_RE_LAYER_DE_VISTA = re.compile(
    r"(?<![a-z])(?:vistas?|cortes?|fachadas?|eleva[cç](?:[aã]o|[oõ]es)|elev|"
    r"se[cç](?:[aã]o|[oõ]es)|sections?|elevations?|detalhes?)(?![a-z])", re.IGNORECASE)
_ESP_PAREDE_M = (0.05, 0.35)       # espessura plausível de parede
_ESP_BUSCA_M = 0.60                # parceira até 60 cm NA UNIDADE LIDA
_ESP_MIN_M = 0.0004                # mais perto que isto é a mesma linha em pedaços
_ESP_ANG_TOL = 1.0                 # graus
_ESP_SOBREPOE = 0.5                # a parceira cobre ≥ metade do trecho
_ESP_FRACAO_PAR = 0.5              # ≥ metade do comprimento com parceira
# 📏 30/09 (distribuição do estudo, 38 desenhos com parede, medida antes do eixo):
# os 4 H51 dão 0,61–0,91; o maior desenho certo que passa nas outras travas dá
# 0,50 (um CYPE; e o do reboco, 0,50, se a cota não o provasse). 55% fica no
# meio — 0,05 de folga dos dois lados. Com 60% o H51 de 0,61 passava raspando,
# e deixar passar é o erro caro (selo em número 10× errado).
_ESP_FRACAO_FINA = 0.55            # ≥ 55% do que pareou na faixa "fina"
_ESP_FRACAO_PLAUSIVEL_MAX = 0.2    # e < 20% já na faixa plausível
_ESP_MIN_PARES = 20
_ESP_MAX_SEG = 60000               # teto (amostra os trechos mais longos)
_ESP_MAX_VIZINHOS = 400            # teto da busca por trecho, em cada lado
_REGUA_QUE_PROVA = ("validada", "corrigida", "corrigida_lfac", "provada_por_rotulo")
_NOME_DA_UNIDADE = {0.001: "milímetro", 0.01: "centímetro", 0.1: "decímetro", 1.0: "metro"}
# VETO pelo texto (estudo, 90 leituras do acervo): com a unidade errada, a letra
# do modelo dá 5–16 mm (1:1 na unidade lida); com a certa, 10–25 cm. Com
# ≥ `_PLAUS_TEXTO_MIN` textos e a mediana ≥ 5 cm, a unidade lida é plausível e
# o par "fino" é outra coisa (linha de reboco, esquadria) — não age.
_ESP_VETO_TEXTO_M = 0.05


def _texto_mediano_do_modelo(doc):
    """(quantos, altura mediana CRUA) dos TEXT/MTEXT do modelo."""
    hs = []
    try:
        for e in doc.modelspace().query("TEXT MTEXT"):
            try:
                h = float(e.dxf.get("height", 0) if e.dxftype() == "TEXT"
                          else e.dxf.get("char_height", 0))
            except (TypeError, ValueError):
                continue
            if h > 0:
                hs.append(h)
    except Exception:
        return 0, 0.0
    hs.sort()
    return len(hs), (hs[len(hs) // 2] if hs else 0.0)


def _nome_da_unidade(fator) -> str:
    for f, nome in _NOME_DA_UNIDADE.items():
        if abs(float(fator) - f) <= 1e-9 * max(1.0, f):
            return nome
    return ""


def unidade_contradita_pela_parede(walls, unit_factor, status_da_regua=None, texto=None) -> dict:
    """{'k', 'espessura_cm', 'fracao_fina', 'em_par', 'n'} quando a espessura das
    paredes só é plausível com o desenho k× MAIOR (k = 10 ou 100); {} se não.

    A medida é a de `espessura_dos_pares`. Dispara com ≥ `_ESP_MIN_PARES` pares,
    metade do comprimento em par, ≥ 55% do que pareou na faixa 5–35 cm ÷ k e
    < 20% já em 5–35 cm. Unidade provada (cota, DIMLFAC, rótulo) → {}. `texto`
    = (quantos, altura mediana crua) do modelo: letra plausível na unidade lida
    veta."""
    if status_da_regua in _REGUA_QUE_PROVA:
        return {}
    uf = float(unit_factor or 0.0)
    if uf <= 0 or not walls:
        return {}
    if texto and texto[0] >= _PLAUS_TEXTO_MIN and texto[1] * uf >= _ESP_VETO_TEXTO_M:
        return {}
    e = espessura_dos_pares(walls, uf)
    if not e or e["n"] < _ESP_MIN_PARES or e["em_par"] < _ESP_FRACAO_PAR:
        return {}
    if e["plausivel"] >= _ESP_FRACAO_PLAUSIVEL_MAX:
        return {}
    for k in (10, 100):
        if e["fina"][k] >= _ESP_FRACAO_FINA:
            return {"k": k, "espessura_cm": e["espessura_cm"][k],
                    "fracao_fina": round(e["fina"][k], 2),
                    "em_par": round(min(e["em_par"], 1.0), 2), "n": e["n"]}
    return {}


def espessura_dos_pares(walls, unit_factor) -> dict:
    """A MEDIDA da régua da espessura, sem a decisão ({} sem trecho que baste).

    Pra cada trecho reto de layer de parede — ou do layer genérico de
    ARQUITETURA (H95, `engine_rules.layer_de_arquitetura`) — fora de
    vista/corte/fachada, a
    parceira paralela mais perto (≤ 1°) que cobre ≥ metade dele, até 60 cm na
    unidade lida — a mesma medida da varredura do estudo. Devolve, em float:
    'n' (pares), 'tot_m', 'par_m', 'em_par' (par_m / tot_m), 'plausivel' (fração
    do que pareou em 5–35 cm) e, por k (10, 100), 'fina' (fração em 5–35 cm ÷ k)
    e 'espessura_cm' (mediana ponderada na faixa, em cm na unidade lida).
    Existe separada pra medir a MARGEM no acervo sem reimplementar a régua."""
    uf = float(unit_factor or 0.0)
    if uf <= 0 or not walls:
        return {}
    from engine_rules import layer_de_arquitetura, layer_e_parede
    segs = []
    for w in walls:
        lay = str(getattr(w, "layer", "") or "")
        if getattr(w, "curvo", False) or _RE_LAYER_DE_VISTA.search(lay) or not (
                layer_e_parede(lay) or layer_de_arquitetura(lay)):
            continue
        pts = getattr(w, "pontos", ()) or ()
        if len(pts) >= 2:
            for p, q in zip(pts, pts[1:]):
                if len(p) > 2 and p[2]:
                    continue                           # lado em arco
                if (p[0], p[1]) != (q[0], q[1]):
                    segs.append(((p[0], p[1]), (q[0], q[1])))
        else:
            a = tuple(getattr(w, "start", (0, 0)))[:2]
            b = tuple(getattr(w, "end", (0, 0)))[:2]
            if a != b:
                segs.append((a, b))
    if len(segs) < _ESP_MIN_PARES:
        return {}
    if len(segs) > _ESP_MAX_SEG:
        segs = sorted(segs, key=lambda ab: -math.hypot(ab[1][0] - ab[0][0],
                                                        ab[1][1] - ab[0][1]))[:_ESP_MAX_SEG]
    itens = sorted((math.degrees(math.atan2(by - ay, bx - ax)) % 180.0, (ax, ay), (bx, by))
                   for (ax, ay), (bx, by) in segs)
    grupos, atual = [], [itens[0]]
    for it in itens[1:]:
        if it[0] - atual[-1][0] <= _ESP_ANG_TOL:
            atual.append(it)
        else:
            grupos.append(atual)
            atual = [it]
    grupos.append(atual)
    if len(grupos) > 1 and grupos[0][0][0] + 180.0 - grupos[-1][-1][0] <= _ESP_ANG_TOL:
        grupos[0] = grupos.pop() + grupos[0]
    busca, minimo = _ESP_BUSCA_M / uf, _ESP_MIN_M / uf
    tot_m = 0.0
    pares = []                                         # (espessura em m, trecho em m)
    for g in grupos:
        th = math.radians(g[0][0])
        ux, uy = math.cos(th), math.sin(th)
        nx, ny = -uy, ux
        sg = []
        for _ang, (ax, ay), (bx, by) in g:
            t0, t1 = sorted((ax * ux + ay * uy, bx * ux + by * uy))
            sg.append((((ax + bx) / 2.0) * nx + ((ay + by) / 2.0) * ny, t0, t1))
        sg.sort()
        rhos = [x[0] for x in sg]
        for ri, a0, a1 in sg:
            L = a1 - a0
            if L <= 0:
                continue
            tot_m += L * uf
            melhor = None
            j, vistos = bisect_left(rhos, ri + minimo), 0
            while j < len(sg) and rhos[j] - ri <= busca and vistos < _ESP_MAX_VIZINHOS:
                if min(a1, sg[j][2]) - max(a0, sg[j][1]) >= _ESP_SOBREPOE * L:
                    melhor = rhos[j] - ri
                    break
                j, vistos = j + 1, vistos + 1
            j, vistos = bisect_right(rhos, ri - minimo) - 1, 0
            while j >= 0 and ri - rhos[j] <= busca and vistos < _ESP_MAX_VIZINHOS:
                if melhor is not None and ri - rhos[j] >= melhor:
                    break
                if min(a1, sg[j][2]) - max(a0, sg[j][1]) >= _ESP_SOBREPOE * L:
                    melhor = ri - rhos[j]
                    break
                j, vistos = j - 1, vistos + 1
            if melhor is not None:
                # 🪤 float(): coordenada de polilinha vem do numpy, e round()
                # de numpy devolve numpy — o log saía "np.float64(1.499)"
                pares.append((float(melhor * uf), float(L * uf)))
    tot_m = float(tot_m)
    par_m = sum(L for _d, L in pares)
    if tot_m <= 0 or par_m <= 0:
        return {"n": len(pares), "tot_m": tot_m, "par_m": par_m, "em_par": 0.0,
                "plausivel": 0.0, "fina": {10: 0.0, 100: 0.0},
                "espessura_cm": {10: 0.0, 100: 0.0}}

    def _massa(lo, hi):
        return sum(L for d, L in pares if lo <= d <= hi)

    fina, esp_cm = {}, {}
    for k in (10, 100):
        lo, hi = _ESP_PAREDE_M[0] / k, _ESP_PAREDE_M[1] / k
        m = _massa(lo, hi)
        fina[k] = m / par_m
        # a espessura típica: mediana ponderada pelo comprimento, na faixa
        acum, esp = 0.0, 0.0
        for d, L in sorted(p for p in pares if lo <= p[0] <= hi):
            acum += L
            esp = d
            if acum >= m / 2.0:
                break
        esp_cm[k] = round(esp * 100, 3)
    return {"n": len(pares), "tot_m": tot_m, "par_m": par_m, "em_par": par_m / tot_m,
            "plausivel": _massa(*_ESP_PAREDE_M) / par_m, "fina": fina, "espessura_cm": esp_cm}


def ressalva_da_parede_fina(r, unit_factor) -> str:
    """Texto da ressalva de `unidade_contradita_pela_parede` ('' sem achado)."""
    if not r or not r.get("k"):
        return ""
    k, moda = int(r["k"]), float(r["espessura_cm"])
    lida = _nome_da_unidade(unit_factor)
    outra = _nome_da_unidade(float(unit_factor) * k)
    return ("as paredes medem %s cm de espessura na unidade lida%s, em %d%% das faces "
            "que formam par — parede não tem essa espessura; com o desenho %d× maior%s, "
            "dariam %s cm. A escala não foi provada: confira uma medida conhecida "
            "antes de usar comprimentos e áreas"
            % (_num_br(moda), ", %s" % lida if lida else "", round(100 * r.get("fracao_fina", 0)),
               k, ", em %s" % outra if outra else "", _num_br(moda * k)))


def _num_br(v) -> str:
    """1.6 → '1,6'; 16.0 → '16'; 0.15 → '0,15'."""
    v = float(v)
    s = (("%.1f" if abs(v) >= 1 else "%.2f") % v).rstrip("0").rstrip(".")
    return s.replace(".", ",")


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
        # 28/09: quantas das que apoiam cada fator têm número DIGITADO — o aviso
        # ao cliente dizia "934 cotas batem" e 931 eram texto automático
        apoio_digitado: dict[float, int] = {f: 0 for f in _CANONICAL_METRIC_FACTORS}
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
                if not auto_text:
                    apoio_digitado[f] += 1

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
                "n_cotas_digitadas": apoio_digitado[novo],
                "unidade_nome": _UNIT_FACTOR_NAMES[novo],
                "mensagem": (
                    f"unidade corrigida pelas cotas da prancha: fator {unit_factor:g} → {novo:g} "
                    f"({_UNIT_FACTOR_NAMES[novo]}) — provado por {n} cotas "
                    f"(texto exibido × medida geométrica, ±2%), {apoio_digitado[novo]} "
                    f"delas com número digitado"
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
        # H74 (01/10): o que qualificou, pra plausibilidade do imperial ler
        out["qualificados"] = [{"fator": f, "n": len(support[f]),
                                "mediana_m": round(_median_of(support[f]), 3),
                                "digitadas": apoio_digitado[f]} for f in proven]
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
# 🩸 29/09/2026 (caso 18c57c3c, 2º dia): o mesmo cliente mandou mais 3 pranchas
# do mesmo projeto com 60,2 MB — recusadas antes de converter por 0,2 MB (a 1ª,
# de 59,7 MB, passou e entregou). Medido aqui no mesmo dia, LibreDWG na de
# 59,7 MB: pico de 2.000 MB = 33,5× (o pior fator medido até hoje; o 35×
# pessimista dos testes segue valendo). 62 MB é a mínima que passa as três e
# cabe no mesmo orçamento de 2.200 MB (62 × 35 = 2.170).
_MAX_DWG_BYTES = 62 * 1024 * 1024  # 62 MB de DWG ≈ 2,1 GB na conversão (33,5× medido)


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


# ---------------------------------------------------------------------------
# VÍNCULO DO REVIT DA MESMA DISCIPLINA — o conteúdo, não o contexto (H13)
# ---------------------------------------------------------------------------
# O Revit exporta o modelo vinculado como UM BLOCO POR INSTÂNCIA × VISTA:
# "<base>_rvt-<N>-<vista>", e insere todos. Medido no acervo (19 desenhos):
# a mesma base tem conteúdo DIFERENTE em cada vista (planta 1.503 peças × corte
# 15 × isométrico 37), e muitos blocos vêm VAZIOS (60 de 72 num pavimento: a
# instância que não aparece naquela vista). Por isso: só vista de PLANTA, UMA
# vista por base (a de mais peças), e cada bloco não vazio dela uma vez.
_RE_VINCULO_INSTANCIA = re.compile(r"^(?P<base>.+?)_(?:rvt|ifc)-(?P<n>\d+)-(?P<vista>.*)$",
                                   re.IGNORECASE)
# 🩸 30/09 (lista inteira medida pelo estudo): junto o nome, o caso do toldo dá
# 100 linhas — e com 40 o "TOLDO - DEMOLIR 3" caía fora (empate no fim). A peça
# pequena com FASE é a que decide o serviço de demolição.
_VINCULO_MAX_PECAS = 100
# 🪤 corte, elevação, 3D, isométrico, perspectiva e detalhe já saem pelo
# `tipo_do_desenho` da vista ('vista'/'fora'); "1º Pav_" (sem tipo) entra.
# 🩸 30/09 (antes/depois do estudo): o Revit põe no nome da peça o ID do
# elemento e a VISTA — "…montante 50x75mm-9884787-PREDIO - TÉRREO…" — e a mesma
# família saía partida em dezenas de linhas (246 montantes em 5+). O corte das
# 40 maiores, antes de juntar, deixou de fora os 3 chuveiros a DEMOLIR. Tira o
# id (5+ dígitos) e o que vem depois, e a variante "-V14"; junta; só então corta.
_RE_ID_DO_REVIT = re.compile(r"-\d{5,}(?:-.*)?$")
_RE_VARIANTE_DO_REVIT = re.compile(r"-V\d+$", re.IGNORECASE)


def _nome_da_peca_no_vinculo(nome, vista="") -> str:
    """Nome da família/tipo sem o que o Revit cola: a VISTA da instância
    ("…-V14-PREDIO - TÉRREO…", conhecida pelo nome do bloco pai — 🩸 30/09: sem
    tirá-la, a variante não ficava no fim e 26 + 7 + 3 portas não juntavam), o
    id do elemento e a variante."""
    n = str(nome or "")
    v = str(vista or "").strip()
    if v and n.lower().endswith("-" + v.lower()):
        n = n[:-(len(v) + 1)]
    n = _RE_ID_DO_REVIT.sub("", n).strip()
    n = _RE_VARIANTE_DO_REVIT.sub("", n).strip()
    return n or str(nome or "")


def pecas_no_vinculo(doc, nomes_inseridos, nome_do_arquivo, e_anotacao=None) -> dict:
    """{base: {disciplina, instancias, vista, outras_vistas, pecas: {nome: n}}}
    dos vínculos da MESMA disciplina do arquivo; {} se o arquivo não diz a
    disciplina."""
    from engine_rules import disciplina_do_nome, tipo_do_desenho
    disc = disciplina_do_nome(os.path.splitext(os.path.basename(str(nome_do_arquivo or "")))[0])
    if not disc:
        return {}
    escolhido: dict = {}                       # (base, vista) → [Counter de cada instância]
    for nome in nomes_inseridos or ():
        m = _RE_VINCULO_INSTANCIA.match(str(nome or ""))
        if not m:
            continue
        base, vista = m.group("base").strip(), m.group("vista").strip()
        if disciplina_do_nome(base) != disc:
            continue
        if tipo_do_desenho(vista) in ("vista", "fora"):
            continue
        try:
            bdef = doc.blocks.get(nome)
        except Exception:
            bdef = None
        if bdef is None:
            continue
        cont: Counter = Counter()
        for e in bdef:
            if e.dxftype() != "INSERT":
                continue
            fn = str(e.dxf.name or "")
            if (not fn or fn.startswith("*") or _RE_VINCULO_INSTANCIA.match(fn)
                    or (e_anotacao is not None and e_anotacao(fn))):
                continue
            cont[_nome_da_peca_no_vinculo(fn, vista)] += 1
        if not cont:
            continue                           # bloco vazio: a instância não aparece nesta vista
        escolhido.setdefault((base, vista), []).append(cont)
    # 🩸 30/09 (antes/depois do estudo, alojamento de 7 pavimentos): a vista
    # "<PAV> - TIPOLOGIAS" repete os MESMOS 6 quartos, no mesmo lugar, com OUTRO
    # N — "cada (base, N) uma vez" deu 12. UMA vista por base: a de mais peças.
    # 🪤 Se um arquivo mostrar ANDARES diferentes do mesmo vínculo em vistas
    # diferentes, só um conta (a menos — e a contagem já sai sem selo).
    vista_da_base: dict = {}
    for (base, vista), conts in escolhido.items():
        total = sum(sum(c.values()) for c in conts)
        if base not in vista_da_base or total > vista_da_base[base][0]:
            vista_da_base[base] = (total, vista, conts)
    out = {}
    for base, (_t, vista, conts) in vista_da_base.items():
        pecas: Counter = Counter()
        for c in conts:
            pecas.update(c)
        outras = sorted({v for (b, v) in escolhido if b == base and v != vista})
        out[base] = {"disciplina": disc, "instancias": len(conts), "vista": vista,
                     "outras_vistas": outras[:4],
                     "pecas": dict(pecas.most_common(_VINCULO_MAX_PECAS))}
        _resto = pecas.most_common()[_VINCULO_MAX_PECAS:]
        if _resto:
            # a IA precisa saber que há mais (no caso do toldo, 20 linhas a DEMOLIR)
            out[base]["nao_listadas"] = {"tipos": len(_resto), "pecas": sum(n for _p, n in _resto)}
    return out


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


# teto de SPLINE medidas por prancha (texto explodido em curva vira milhares)
_MAX_SPLINES = 20000
# 30/09 (H10, antes/depois do estudo em 16 DXF): curva de SÍMBOLO — carro,
# móvel, vegetação, figura humana — somava metro em layer que não é obra
# (CARROS +351 m, CARROS-LF +192, LAY-OUT-LF +23, LAYOUT +12; nenhum layer de
# eletroduto casa aqui). "veicul" ficou de fora de propósito: "CARREGADOR
# VEICULAR" é elétrica. Esses layers seguem com as LINHAS deles, como antes;
# só a curva não entra. E curva em layer de anotação também não.
_RE_LAYER_SIMBOLO_EM_CURVA = re.compile(
    r"carr[oa]|[aá]rvore|veget|paisag|mob[ií]l|lay-?out|pessoa|human|figur",
    re.IGNORECASE)


def _spline_pontos(entity) -> list:
    """A SPLINE achatada: [(x, y), ...] em unidade do desenho ([] se não deu).

    Erro de corda de 1/1000 do tamanho da curva. Sem pontos de controle,
    usa os pontos de ajuste ligados por reta."""
    pts = []
    try:
        ct = entity.construction_tool()
        cps = list(ct.control_points)
        if cps:
            xs = [p[0] for p in cps]
            ys = [p[1] for p in cps]
            diag = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
            tol = diag / 1000.0 if diag > 0 else 1e-9
            pts = [(p.x, p.y) for p in ct.flattening(tol, segments=8)]
    except Exception:
        pts = []
    if len(pts) < 2:
        try:
            pts = [(p[0], p[1]) for p in entity.fit_points]
        except Exception:
            pts = []
    return pts if len(pts) >= 2 else []


def _spline_length(entity) -> float:
    """Comprimento de uma SPLINE (unidade do desenho), pela curva ACHATADA.

    🩸 30/09/2026 (H10 do estudo do acervo, job 73c6f0ed): eletroduto de piso,
    de gesso e o circuito de telefone desenhados em SPLINE — 108, 55 e 65 m,
    ≥ 99% dos layers. O motor somava só LINE/POLYLINE/ARC/CIRCLE, e o único
    traço reto de cada layer era a AMOSTRA DA LEGENDA: saíram "✓ MEDIDO
    0,6 m". A curva é achatada com erro de corda de 1/1000 do tamanho dela
    (quarto de círculo de raio 10: 15,705 contra 15,708).
    Sem pontos de controle, liga os pontos de ajuste. Falhou → 0 (não mede).
    """
    pts = _spline_pontos(entity)
    return sum(_line_length(pts[i], pts[i + 1]) for i in range(len(pts) - 1)) if pts else 0.0


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


def _hachura_e_secao_de_parede(entity, unit_factor) -> bool:
    """A hachura é a SEÇÃO de uma parede cortada (faixa fina), não superfície?

    🩸 27/09/2026 (estudo de leitura, item 1): em layer de parede, a hachura
    que preenche a espessura da parede na planta virava "m² de drywall" com
    ✓ MEDIDO — shaft 0,18 m² ✓ (real ~2,5), drywall 1,44 m² ✓ (~23 m de
    parede). Faixa fina = SOME numa erosão de 12 cm (largura ≤ ~0,25 m) e tem
    ≥ 0,6 m de comprimento. 🪤 A régua 2·A/P ≤ 0,45 pegava o vão do shaft
    (selo corta-fogo) e pilares; a erosão não (o vão resiste a 6 cm).
    Na dúvida (geometria que não lê) → False: fica como era.
    """
    try:
        if not unit_factor or unit_factor <= 0:
            return False
        from ezdxf import path as ezdxf_path
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
        pr = ezdxf_path.make_path(entity)
        subs = list(pr.sub_paths()) if getattr(pr, "has_sub_paths", False) else [pr]
        polys = []
        for p in subs:
            pts = [(v.x, v.y) for v in p.flattening(0.5)]
            if len(pts) >= 3:
                g = Polygon(pts)
                if not g.is_valid:
                    g = g.buffer(0)
                if not g.is_empty:
                    polys.append(g)
        if not polys:
            return False
        u = unary_union(polys)
        x0, y0, x1, y1 = u.bounds
        if max(x1 - x0, y1 - y0) * unit_factor < 0.6:
            return False                      # pedaço curto: não é faixa de parede
        return u.buffer(-0.12 / unit_factor).is_empty
    except Exception:
        return False


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


#: Amostra de BLOCO na legenda (ver `amostras_de_legenda`). 📏 As mínimas que
#: resolvem nos 17 DXF medidos em 26/09: 6 alturas perdia a BUCHA de um
#: elétrico (símbolo a 8,8h do rótulo); sem a coluna entravam 6 falsos.
_LEG_JANELA_H = 10       # o rótulo começa até 10 alturas à direita do símbolo
_LEG_LARGURA_H = 12      # símbolo mais largo que 12 alturas não é amostra
_LEG_COLUNA_MIN = 2      # outros rótulos na mesma coluna (x ±0,5h, altura ±10%)
_LEG_COLUNA_H = 15       # ... a até 15 alturas na vertical
_LEG_PALAVRAS_FORA = frozenset({"de", "da", "do", "das", "dos", "com", "para", "em",
                                "na", "no", "ind", "blk", "bloco", "the"})
#: A COLUNA de símbolos da legenda (ver `amostras_de_legenda`, 29/09): ≥3
#: amostras já provadas pelo nome na mesma faixa x; a inserção vizinha na
#: coluna (até 1,5 passo de um membro) também é amostra.
_LEG_COLUNA_BLOCOS_MIN = 3
_LEG_COLUNA_PASSOS = 1.5


def _nota_da_legenda(n):
    """A nota da MESMA linha do bloco no prompt. 🔑 "ao menos": a regra não
    acha todo símbolo de legenda (rótulo que não repete o nome escapa) — o N é
    piso, não conta fechada."""
    return f"  [ao menos {n} delas = símbolo desenhado na LEGENDA, não peça]" if n else ""


def _palavras_do_rotulo(s):
    """Palavras de ≥3 caracteres, sem acento e minúsculas; fora número e ligação."""
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return {t for t in re.split(r"[^a-z0-9]+", s)
            if len(t) >= 3 and t not in _LEG_PALAVRAS_FORA and not t.isdigit()}


def amostras_de_legenda(insercoes, textos):
    """Quais inserções de bloco são o SÍMBOLO desenhado na LEGENDA da prancha.

    `insercoes` = [(nome, (x0, y0, x1, y1) da inserção, pos)];
    `textos` = [(texto, x, y, altura)]. Devolve {nome: [pos das amostras]},
    só dos blocos que têm amostra.

    🩸 26/09/2026, job 32a27efc (muro de arrimo, Eberick): "Pilar nasce = 1 un
    ✓ MEDIDO" em 3 pranchas. O único INSERT 'IND PILAR NASCE' de cada folha era
    o símbolo da coluna "LEGENDA PILARES:", com "PILAR NASCE" 1,2 mm abaixo e
    "PILAR MORRE"/"PILAR CONTINUA" alinhados; na planta não havia nenhum. O
    motor conta todo INSERT, e nada olhava onde ele estava.
    📏 17 DXF de 6 clientes: 43 blocos com amostra contada como peça (34 só
    amostra, 9 com a contagem inflada em +1/+2); 0 falso positivo em 1.440
    inserções. No banco, piso de 21 linhas "confirmado" em 6 jobs.

    🔑 A inserção é amostra quando um texto de altura h
      (g) começa entre x0 − h e x1 + 10h, com folga vertical ≤ h, e o
          símbolo tem ≤ 12h de largura;
      (p) repete o nome do bloco: ≥2 palavras em comum, ou todas as do nome,
          ou 1 com ≥5 letras; palavra do nome que é começo de palavra do texto
          conta ('condu' → 'condulete');
      (c) está numa COLUNA de rótulos: ≥2 outros textos com o mesmo x (±0,5h),
          a mesma altura (±10%), a até 15h.
    🪤 Sem (c), a etiqueta ao lado da peça na planta ("ARANDELA h=1,40m",
    "Drenagem Superficial" junto do tê) virava amostra: 6 falsos medidos.
    Limite: rótulo que não repete o nome (SOLDA × "CONEXÃO APARAFUSADA") ou
    nome do conversor ('BLOCO1') não é pego.

    🩸 29/09/2026 (caso 18c57c3c, elétrico): a legenda de segurança tinha 8
    símbolos pegos pelo nome e 5 não — 'SP' ao lado de "SENSOR DE PRESENÇA",
    'SI' de "SIRENE", 'CÂMERAS 360°' de "CÂMERA DOME", 'LUM SOM' sem rótulo, 1
    CONDULETE —, e nas duas cópias da legenda de tomadas o sensor (rótulo 14 cm
    fora do alinhamento) e a emergência ("ILE") também escaparam. A planilha
    saiu com câmera, luminária com som, 2 sensores e 2 emergências que só
    existem na legenda (na planta: nenhum).
    🔑 (d) a COLUNA de símbolos: ≥3 amostras provadas acima cujos desenhos
      se encostam na horizontal formam a coluna (a faixa x que ocupam); a
      inserção que cai nessa faixa a até 1,5 passo (a mediana do espaçamento
      da coluna) de um membro também é amostra, e a coluna cresce por ela.
      Símbolo mais largo que 12h fica fora. Chave: LEGENDA_POR_COLUNA=0
      desliga sem deploy.
    """
    tx = []           # (x, y, h, palavras) — texto sem palavra conta na COLUNA
    for t in textos or []:
        try:
            s, x, y, h = t[0], float(t[1]), float(t[2]), float(t[3])
        except (TypeError, ValueError, IndexError):
            continue
        if h > 0 and str(s or "").strip():
            tx.append((x, y, h, _palavras_do_rotulo(s)))
    if not tx:
        return {}
    por_palavra = defaultdict(list)
    for i, (_x, _y, _h, ps) in enumerate(tx):
        for p in ps:
            por_palavra[p].append(i)
    palavras = sorted(por_palavra)
    ordem_x = sorted(range(len(tx)), key=lambda i: tx[i][0])
    xs = [tx[i][0] for i in ordem_x]
    coluna, rotulos = {}, {}

    def _em_coluna(i):
        if i not in coluna:
            x, y, h, _p = tx[i]
            n = 0
            for k in ordem_x[bisect_left(xs, x - 0.5 * h):bisect_right(xs, x + 0.5 * h)]:
                if k != i and abs(tx[k][2] - h) <= 0.1 * h \
                        and abs(tx[k][1] - y) <= _LEG_COLUNA_H * h:
                    n += 1
            coluna[i] = n >= _LEG_COLUNA_MIN
        return coluna[i]

    def _rotulos_do(nome):
        """Textos que repetem o nome (p) — uma vez por nome, em ordem de x,
        separados por FAIXA de altura (potência de 2).
        🪤 Com uma janela só, a do rótulo mais alto, um título "PLANTA DE
        TOMADAS" (h enorme) alargava a janela de toda inserção: 10 mil × 10
        mil levava 21 s. Por faixa, cada janela usa a altura da sua faixa."""
        if nome not in rotulos:
            tb = _palavras_do_rotulo(nome)
            cands = set()
            for a in tb:
                j = bisect_left(palavras, a)
                while j < len(palavras) and palavras[j].startswith(a):
                    cands.update(por_palavra[palavras[j]])
                    j += 1
            ok = []
            for i in cands:
                tt = tx[i][3]
                comum = (tb & tt) | {a for a in tb for b in tt if b.startswith(a) and a != b}
                if comum and (len(comum) >= 2 or tb <= tt or max(len(c) for c in comum) >= 5):
                    ok.append(i)
            faixas = defaultdict(list)
            for i in ok:
                faixas[math.frexp(tx[i][2])[1]].append(i)
            rotulos[nome] = []
            for f in faixas.values():
                f.sort(key=lambda i: tx[i][0])
                rotulos[nome].append(([tx[i][0] for i in f], f, max(tx[i][2] for i in f)))
        return rotulos[nome]

    def _tem_rotulo(nome, x0, y0, x1, y1):
        for rx, ri, hmax in _rotulos_do(nome):
            # só os rótulos cujo x pode cair na janela (a de cada um usa o seu h)
            for i in ri[bisect_left(rx, x0 - hmax):bisect_right(rx, x1 + _LEG_JANELA_H * hmax)]:
                x, y, h, _p = tx[i]
                if not (x0 - h <= x <= x1 + _LEG_JANELA_H * h):
                    continue
                if max(0.0, y0 - (y + h), y - y1) > h or (x1 - x0) > _LEG_LARGURA_H * h:
                    continue
                if not _em_coluna(i):
                    continue
                return h          # a altura do rótulo: a régua da coluna (d)
        return 0.0

    out = {}
    provadas, resto = [], []
    for ins in insercoes or []:
        try:
            nome, caixa, pos = ins
            x0, y0, x1, y1 = (float(v) for v in caixa)
            py = float(pos[1])
        except (TypeError, ValueError, IndexError):
            continue
        h = _tem_rotulo(nome, x0, y0, x1, y1)
        if h:
            out.setdefault(nome, []).append(pos)
            provadas.append((x0, x1, py, h))
        else:
            resto.append((nome, pos, x0, x1, py))
    if os.environ.get("LEGENDA_POR_COLUNA", "1") != "0":
        for nome, pos in _vizinhas_da_coluna(provadas, resto):
            out.setdefault(nome, []).append(pos)
    return out


def _vizinhas_da_coluna(provadas, resto):
    """(d) de `amostras_de_legenda`: as inserções de `resto` que continuam
    uma coluna de amostras provadas. `provadas` = [(x0, x1, y, h do rótulo)];
    `resto` = [(nome, pos, x0, x1, y)]. Devolve [(nome, pos)].

    A coluna é a FAIXA x que os desenhos dos símbolos provados ocupam (um
    encosta no outro). 🪤 Pelo ponto de inserção (±0,5h) a 2ª cópia da legenda
    de tomadas escapava: lá os símbolos foram empurrados até 20 cm pro lado."""
    colunas = []
    for x0, x1, y, h in sorted(provadas):
        if colunas and x0 <= colunas[-1][1]:
            colunas[-1][1] = max(colunas[-1][1], x1)
            colunas[-1][2].append((y, h))
        else:
            colunas.append([x0, x1, [(y, h)]])
    achadas, usadas = [], set()
    for cx0, cx1, membros in colunas:
        if len(membros) < _LEG_COLUNA_BLOCOS_MIN:
            continue
        ys = sorted(y for y, _h in membros)
        passos = [b - a for a, b in zip(ys, ys[1:]) if b - a > 0]
        if not passos:
            continue
        h = statistics.median(hh for _y, hh in membros)
        alcance = _LEG_COLUNA_PASSOS * statistics.median(passos)
        cand = [k for k, r in enumerate(resto)
                if k not in usadas and r[2] <= cx1 and r[3] >= cx0
                and r[3] - r[2] <= _LEG_LARGURA_H * h]
        cresceu = True
        while cresceu:
            cresceu = False
            for k in cand:
                if k not in usadas and any(abs(resto[k][4] - y) <= alcance for y in ys):
                    usadas.add(k)
                    ys.append(resto[k][4])
                    achadas.append((resto[k][0], resto[k][1]))
                    cresceu = True
    return achadas


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
# 🩸 30/09/2026 (H54, medido pelo estudo): o bloco de título de vista do Revit
# põe no papel o NÚMERO da vista ("6") com letra MAIOR que o nome ("CORTE AA").
# Pela altura, o título saía "6" — não diz o que o desenho é, e a janela ficava
# sem tipo (e não votava na convenção da folha).
_RE_SO_NUMERO_DA_VISTA = re.compile(r"^\s*\d{1,3}\s*$")


def _titulo_no_papel(papel, textos, lado="abaixo") -> str:
    """O título da vista escrito no PAPEL, logo abaixo da janela ('' se não há).

    🩸 25/09/2026 — job `42f99f4f` (esgoto e pluvial exportados do REVIT): 16
    janelas por folha e NENHUM título achado, porque o Revit escreve o título
    de cada vista no espaço do papel (layer `G-ANNO-TTLB`): o nome junto do
    canto de baixo-esquerdo da janela e a escala ("1 : 20") numa linha logo
    abaixo. Entre as vistas havia três "3D - Térreo - …": o isométrico da
    tubulação, somado como planta — 83% do tubo "medido" da folha 1.

    Pega o texto MAIOR na faixa logo abaixo da janela (até 15% da altura dela),
    começando perto da borda esquerda; a linha só de escala não vale.
    `lado="acima"`: a mesma faixa, espelhada no topo (folha que escreve o
    título em cima do desenho — ver `_convencao_da_folha`).
    """
    if not papel or not textos:
        return ""
    x0, y0, x1, y1 = papel
    w, h = (x1 - x0), (y1 - y0)
    if w <= 0 or h <= 0:
        return ""
    if lado == "acima":
        faixa, borda = (y1 - 0.02 * h, y1 + 0.15 * h), y1
    else:
        faixa, borda = (y0 - 0.15 * h, y0 + 0.02 * h), y0
    cand = [t for t in textos
            if faixa[0] <= t[2] <= faixa[1]
            and x0 - 0.05 * w <= t[1] <= x0 + 0.6 * w
            and not _RE_SO_ESCALA.match(t[0]) and not _RE_SO_NUMERO_DA_VISTA.match(t[0])
            and len(t[0]) <= 90]
    if not cand:
        return ""
    cand.sort(key=lambda t: (-t[3], abs(t[2] - borda) + abs(t[1] - x0)))
    return cand[0][0]


#: 🩸 30/09/2026 — H54, o erro INVERSO: o CORTE somado como PLANTA. No corte do
#: Revit, os níveis escritos no desenho ("TÉRREO", "COBERTURA", "TELHADO") são a
#: maior letra da região e viravam o título → 'planta'; o título de verdade
#: ("CORTE AA", "CORTE 1") estava no PAPEL, logo abaixo da janela. Tabela do
#: estudo (12 janelas com título no modelo E no papel): o papel do lado da
#: convenção da folha acerta 8, erra 0. O papel do lado CONTRÁRIO errou 1 (um
#: esquema de rede com "Planta Baixa" escrito em cima) — por isso só vale o lado
#: da convenção. E a convenção tem de ser CLARA: ≥ 3 janelas e 1,5× o outro
#: lado (a folha de escadas com 8 abaixo × 6 acima não decide; a casa do Revit
#: com 5 × 3 decide).
_CONVENCAO_MIN_JANELAS = 3
_CONVENCAO_RAZAO = 1.5


def _convencao_da_folha(janelas_da_folha, textos, parece, tipo) -> str:
    """'abaixo', 'acima' ou '' — de que lado da janela a folha escreve o título."""
    n = {"abaixo": 0, "acima": 0}
    for j in janelas_da_folha:
        for lado in n:
            t = _titulo_no_papel(j.get("papel"), textos, lado)
            if t and parece(t) and tipo(t):
                n[lado] += 1
    for lado, outro in (("abaixo", "acima"), ("acima", "abaixo")):
        if n[lado] >= _CONVENCAO_MIN_JANELAS and n[lado] >= _CONVENCAO_RAZAO * n[outro]:
            return lado
    return ""


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
        # 🩸 27/09/2026 — folha de DETALHE do banheiro (cliente que voltou): a
        # letra maior da folha é do carimbo (60) e os títulos dos desenhos têm
        # 7 — 12% dela. Nenhum passava, e a planta, a paginação e o forro do
        # MESMO banheiro somaram (janela 4× no lugar de 1, ralo 4× no lugar
        # de 2). Título de desenho tem a ESCALA logo embaixo ("escala 1:25");
        # o título da folha no carimbo e o rótulo solto ("DET.03") não têm.
        escalas = [(x, y) for t, x, y, h in textos if _RE_SO_ESCALA.match(t)]

        def _escala_embaixo(t, x, y, h):
            fim = x + 0.75 * h * len(t)
            return any(y - 4 * h <= ey < y and x - 6 * h <= ex <= fim + 6 * h
                       for ex, ey in escalas)

        titulos = []
        for t, x, y, h in textos:
            if len(t) > 90:
                continue
            if h < 0.8 * hmax and not _escala_embaixo(t, x, y, h):
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
        # 🩸 27/09/2026 — planta-tipo de 955 m² (cliente que voltou): ~120
        # inserções SOLTAS a dezenas de metros da folha (registros, cubas,
        # tomadas 20A, IC/CG — 3% dos pontos) esticavam a caixa da folha pra 80
        # mil unidades; a célula da malha virava 6 m e a folha inteira — planta
        # e detalhes — virava UM bloco. A folha é onde está a MASSA do desenho:
        # ponto a mais de 25% além do miolo de 90% (5% de cada ponta) é rascunho
        # perdido. 🔑 Seguro por construção: tirar ponto DAQUI só pode fazer um
        # desenho distante deixar de ser achado — nunca tira nada da soma.
        # 🪤 Medido no acervo: cortar SEMPRE mexia nas folhas A1 desenhadas no
        # modelo (elétrica industrial de 25/09): o campo de notas e o carimbo
        # ficam nas pontas, a malha encolhia, as caixas dos cortes saíam menores
        # e 100 m de corte voltavam pra soma. Só corta quando há ponto LONGE de
        # verdade: a caixa inteira ≥ 4× a caixa do miolo (na planta do caso, 11×).
        xs = sorted(c for s in segs for c in (s[0][0], s[1][0]))
        ys = sorted(c for s in segs for c in (s[0][1], s[1][1]))
        k = len(xs) // 20
        rx0, rx1, ry0, ry1 = xs[k], xs[-1 - k], ys[k], ys[-1 - k]
        mx, my = 0.25 * (rx1 - rx0), 0.25 * (ry1 - ry0)
        caixa_miolo = (rx1 - rx0 + 2 * mx) * (ry1 - ry0 + 2 * my)
        caixa_toda = (xs[-1] - xs[0]) * (ys[-1] - ys[0])
        if caixa_miolo > 0 and caixa_toda >= 4 * caixa_miolo:
            def _na_folha(p):
                return rx0 - mx <= p[0] <= rx1 + mx and ry0 - my <= p[1] <= ry1 + my
            segs = [s for s in segs if _na_folha(s[0]) and _na_folha(s[1])]
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
                        # 🩸 27/09/2026 (estudo, item 7): o SUBLINHADO do título
                        # é o 1º traço acima do meio da letra — e virava "o
                        # desenho" (no banho, 4 elevações e 1 corte eram só o
                        # sublinhado: 181 m seguiam na soma). Componente que
                        # não passa da LINHA DE CÉLULAS do título não é o
                        # desenho. Em células, não em altura de letra: a caixa
                        # do componente é arredondada pra célula, e com célula
                        # grande o traço "subia" além de qualquer folga em h.
                        if v in comp_de and comps[comp_de[v]][3] > y0 + (iy + 1.5) * cel:
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
        # 🩸 30/09/2026 — H57 do estudo do acervo: 7 folhas A1 EMPILHADAS no
        # modelo, as molduras se tocando — a geometria virou UM bloco (a coluna
        # inteira, 42% da área, abaixo do teto de 60%) e 11 títulos (detalhes,
        # cortes, elevações) pegaram a MESMA caixa. Cada um tirava a coluna toda
        # da soma: 2.705 m → 0,19 m, com as plantas dentro. Um bloco que DOIS ou
        # mais títulos reclamam não é "um desenho": nenhum deles vale (fica como
        # antes da leitura por folha).
        _por_caixa: dict = {}
        for f in out:
            _por_caixa[f["caixa"]] = _por_caixa.get(f["caixa"], 0) + 1
        _repartidas = sum(1 for f in out if _por_caixa[f["caixa"]] > 1)
        if _repartidas:
            logger.info("_desenhos_no_modelo: %d título(s) pegaram a mesma caixa — fora", _repartidas)
            out = [f for f in out if _por_caixa[f["caixa"]] == 1]
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


# 🩸 30/09/2026 — H54 do estudo do acervo: a PLANTA virava vista pelo texto do
# modelo. Na planta do Revit as marcas "CORTE 1" / "CORTE 2" (e, noutra casa,
# "ELEVAÇÃO") são a MAIOR letra da região — e viravam o título dela: 84,86 m²
# do piso da casa saíram como "superfície vista de lado, NÃO é piso".
# 🔑 Marca é curta e genérica ("CORTE 1", "CORTE A-A", "ELEVAÇÃO"); título de
# corte de verdade que vem do MODELO costuma ser descritivo. Só marca + 3 ou
# mais nomes de AMBIENTE na região = é a planta com as marcas desenhadas nela.
# 🪤 Nome de ambiente SOZINHO não separa (o esquema de prumada tem 30; o corte
# do Revit etiqueta os ambientes): por isso só vale junto da marca genérica, e
# só no título que veio do texto do modelo.
_RE_MARCA_DE_VISTA = re.compile(
    r"^\s*(?:corte|vista|eleva[cç][aã]o|fachada)\s*[\w\-]{0,4}\s*$", re.IGNORECASE)
_RE_NOME_DE_AMBIENTE = re.compile(
    r"^\s*(?:(?:sala|sal[aã]o|quarto|qto|su[ií]te|dormit[oó]rio|banheiro|bwc|wc|lavabo|"
    r"cozinha|copa|varanda|sacada|terra[cç]o|closet|escrit[oó]rio|circula[cç][aã]o|"
    r"corredor|hall|dep[oó]sito|lavanderia|garagem|estar|jantar|despensa|gourmet)"
    r"(?![a-zà-ú])|[aá]rea\s+(?:de\s+)?serv|a\.\s*serv|i\.\s*s\.)", re.IGNORECASE)
_AMBIENTES_QUE_FAZEM_PLANTA = 3


def _so_vistas_no_modelo(msp) -> list:
    """Arquivo SEM janela útil, lido pelo modelo — só quando é folha de VISTAS.

    🩸 30/09/2026 — H61 do estudo do acervo. Sem janela, o arquivo nunca era
    lido por desenho: uma folha só de fachadas entregou "guarda-corpo de
    fachada 1.247,45 ml ✓" — o layer inteiro na elevação (horizontais,
    verticais e as diagonais), em fachadas que somam 178,5 m de largura.
    🪤 Ligar geral NÃO: no acervo, sem janela, a caixa "logo acima do título"
    falhava mais (planta com caixa 0 × 0, detalhe de 120 m engolindo os
    vizinhos — a família do H57). Por isso só age quando é inequívoco: 2+
    desenhos, TODOS vista (elevação/corte — nenhum detalhe, esquema ou planta),
    e nenhuma região com 3+ nomes de ambiente (cara de planta). Senão, [].
    """
    regs = _desenhos_no_modelo(msp)
    if len(regs) < 2 or any(r.get("tipo") != "vista" for r in regs):
        return []
    amb = []
    for e in msp.query("TEXT MTEXT"):
        try:
            t = _texto_do_text(e) if e.dxftype() == "TEXT" else e.plain_text()
            if t and _RE_NOME_DE_AMBIENTE.match(" ".join(t.split())):
                amb.append((e.dxf.insert[0], e.dxf.insert[1]))
        except Exception:
            continue
    if any(sum(1 for a in amb if _dentro(a, r["caixa"])) >= _AMBIENTES_QUE_FAZEM_PLANTA
           for r in regs):
        return []
    for r in regs:
        r["como"] = "modelo sem janela"
    return regs


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
            # 🩸 30/09 (H61): sem janela nenhuma, a folha só de elevações
            # nunca era lida por desenho (ver `_so_vistas_no_modelo`)
            _mv = _so_vistas_no_modelo(doc.modelspace())
            if _mv:
                out["folhas"] = _mv
                out["origem"] = "modelo sem janela"
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
        ambientes = []                   # (x, y) dos nomes de ambiente (H54)
        for e in msp.query("TEXT MTEXT"):
            try:
                p = e.dxf.insert
                alt = float((e.dxf.get("height", 0) if e.dxftype() == "TEXT"
                             else e.dxf.get("char_height", 0)) or 0)
                alturas.append((p[0], p[1], alt))
                t = _texto_do_text(e) if e.dxftype() == "TEXT" else e.plain_text()
                t = " ".join((t or "").split())
                if t and _RE_NOME_DE_AMBIENTE.match(t):
                    ambientes.append((p[0], p[1]))
                if t and len(t) <= 90 and parece_titulo_de_desenho(t) and tipo_do_desenho(t):
                    textos.append((t, p[0], p[1], alt))
            except Exception:
                continue
        # de que lado cada folha escreve o título no papel (H54, ver a constante)
        conv = {f: _convencao_da_folha([j for j in uteis if j["folha"] == f],
                                       textos_papel.get(f, []), parece_titulo_de_desenho,
                                       tipo_do_desenho)
                for f in {j["folha"] for j in uteis}}
        out["convencao"] = {f: c for f, c in conv.items() if c}   # pro log e pra medir
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
                # 🩸 H54: a marca de corte desenhada NA planta não é o título dela
                if tits and all(_RE_MARCA_DE_VISTA.match(t) for t in tits):
                    _n_amb = sum(1 for a in ambientes if _dentro(a, j["caixa"]))
                    if _n_amb >= _AMBIENTES_QUE_FAZEM_PLANTA:
                        j["marca_na_planta"] = "%s (%d ambientes)" % (" | ".join(tits)[:60], _n_amb)
                        tits = []
                        # e o papel também não: é a planta, não se sabe qual
                        j["sem_titulo_de_proposito"] = True
            _lado = conv.get(j["folha"]) or ""
            if tits and _lado and not j.get("sem_titulo_de_proposito"):
                # 🩸 H54, o erro inverso: o papel do lado da convenção da folha
                # vence o texto do modelo quando os dois discordam no tipo
                _tp = _titulo_no_papel(j.get("papel"), textos_papel.get(j["folha"], []), _lado)
                _tt = tipo_do_desenho(_tp) if _tp else ""
                if _tt and _tt not in {tipo_do_desenho(t) for t in tits}:
                    j["papel_venceu_modelo"] = " | ".join(tits)[:80]
                    tits = [_tp]
                    j["titulo_no_papel"] = True
            if not tits and not j.get("sem_titulo_de_proposito"):
                # 25/09: o Revit escreve o título da vista no PAPEL, logo
                # abaixo da janela — não no modelo, onde se procurava até aqui.
                # 30/09: na folha que escreve o título EM CIMA, procura em cima.
                _tp = _titulo_no_papel(j.get("papel"), textos_papel.get(j["folha"], []),
                                       _lado or "abaixo")
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
        if not uteis:                            # só a janela geral (H61)
            _mv = _so_vistas_no_modelo(msp)
            if _mv:
                uteis = _mv
                out["origem"] = "modelo sem janela"
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

    🩸 26/09/2026, job befab5aa (interiores): na PLANTA luminotécnica, um "C01"
    — número de circuito, 39 vezes na planta — tinha à direita, na mesma linha,
    o rótulo "PERFIL DE LED DE EMBUTIR - 2,00m" de UMA luminária. Virou
    "C01 = PERFIL DE LED…" nesta seção, a IA obedeceu ("use ESTE nome") e a
    planilha trouxe 39 × 2 m = 78 ml de perfil (os rótulos somam ~20 m).
    🔑 Legenda é TABELA: o par sigla → nome da mesma linha só vale se a sigla
    estiver numa coluna de pelo menos 3 siglas distintas (uma embaixo da
    outra). Par solto no meio da planta é anotação, não definição. O "=" ("L =
    LEITO") diz sozinho que é definição e continua valendo sozinho. Medido no
    acervo (37 DXF): some o C01, um "IP55", um "PM02 = W.C. SUÍTE 04" e o
    "SGL" do carimbo do Revit; TH/CH/CZ/JA/CVE/CVI e o R6 do forro ficam; perde
    o MB-01 de uma legenda de 2 linhas (fica sem nome — a IA lê o texto).
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
        pares = []
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
                pares.append((txt, melhor[1], x, y, h))
        siglas = [(t, x, y) for t, x, y, h in itens if _e_sigla(t)]
        for txt, nome, x, y, h in pares:
            # a coluna da tabela: 3+ siglas DISTINTAS no prumo desta (±3 letras
            # — 🪤 na tabela do Felipe a "JA", curta, sai 1,9 letra fora) a até
            # 20 linhas. Conta sigla com ou sem nome na linha: no forro do
            # acervo só o R6 tem o nome na mesma linha, as outras não.
            coluna = {t for t, x2, y2 in siglas if abs(x2 - x) <= 3 * h and abs(y2 - y) <= 20 * h}
            if len(coluna) >= 3:
                out.setdefault(txt, nome)
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


def _o_conteudo_e_das_vistas(folhas) -> bool:
    """Os cortes/elevações têm pelo menos tanto conteúdo quanto os desenhos SEM
    tipo (em comprimento E em blocos). Sem a medida por folha, True (como era).

    🩸 28/09/2026 (job dd52081b): 1 corte reconhecido e 15 desenhos sem tipo —
    as 4 plantas baixas do prédio, com 22.450 m e 560 blocos contra 73 m e 4
    blocos do corte. "Nenhuma planta TIPADA" virava "NENHUMA planta" no texto
    da IA, que repetiu isso ao cliente e deixou a parede em branco. O mesmo na
    planta de forro da HWB 700 (573 m × 294 m). A folha de cortes de verdade
    (p0003/p0004, 25/09) tem 0 fora das vistas."""
    med = (folhas or {}).get("medida") or {}
    vis, neu = med.get("vista"), med.get("neutro")
    if not vis or not neu:
        return True
    return (float(neu.get("m") or 0) <= float(vis.get("m") or 0)
            and float(neu.get("blocos") or 0) <= float(vis.get("blocos") or 0))


def prancha_so_de_vista(extraction) -> bool:
    """A prancha tem corte/elevação e NENHUMA planta — a "prancha de cortes" do
    conjunto, cuja planta está em outro arquivo."""
    try:
        fl = getattr(extraction, "folhas", None) or {}
        if not fl.get("aplicada"):
            return False
        ds = fl.get("desenhos_lista") or []
        return (any(d.get("tipo") == "vista" for d in ds)
                and not any(d.get("tipo") == "planta" for d in ds)
                and _o_conteudo_e_das_vistas(fl))
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


# ── VISTAS DA MESMA BASE (28/09/2026) ──────────────────────────────────────────
# 🩸 Caso 18c57c3c (elétrico de um centro de distribuição): a folha tem QUATRO
# vistas do MESMO pavimento — alimentadores, iluminação, sistemas, tomadas —, cada
# uma com a base de arquitetura inserida de novo (translação pura). Tomada só na
# vista de tomadas, interruptor só na de iluminação: contados 1× cada. Mas o
# QDF-ADM1 e o QDF-MANUT aparecem nas TRÊS vistas, no mesmo ponto da planta: a
# planilha disse 11 quadros "✓ medido" e são 7. Os títulos das vistas ("TOMADAS",
# "ILUMINAÇÃO") não viraram desenho na leitura por folha, e o registro em sombra
# das cópias (D1) procura a planta INTEIRA copiada — não viu nenhum dos dois.
# 🔑 O deslocamento entre as inserções da base é EXATO: símbolo que cai no mesmo
# ponto da planta em duas vistas (tolerância de 0,01% do deslocamento) é a mesma
# peça. Medido no acervo antes de escrever: a regra ingênua ("bloco grande inserido
# 2×") apagava 84 mesas de escritório em grade e as cópias do elétrico ×3. As
# quatro travas abaixo separam os casos — só age com as quatro:
_VISTAS_BASE_MIN = 0.20          # a base é PLANTA: ≥ 20% da largura ou da altura do desenho
_VISTAS_SEPARACAO_MIN = 0.75     # vistas SEPARADAS: deslocamento ≥ 75% da base (não é grade)
_VISTAS_PARCELA_MAX = 0.10       # POUCOS símbolos repetem (planta inteira copiada é o D1)
_VISTAS_EXCLUSIVIDADE_MIN = 0.80  # cada tipo mora na SUA vista (andares repetem tudo)
_VISTAS_TOL = 1e-4               # coincidência: fração do deslocamento


def vistas_da_mesma_base(doc, blocks) -> dict:
    """A mesma peça desenhada em várias vistas temáticas do MESMO pavimento conta 1×.

    Vistas = inserções da mesma base (≥ 2, mesma escala, sem rotação) que é planta
    (extensão ≥ `_VISTAS_BASE_MIN` do desenho) e que estão separadas (cada
    deslocamento ≥ `_VISTAS_SEPARACAO_MIN` da base). Repetido = mesmo tipo de
    bloco no ponto p e em p + deslocamento. Só age se os repetidos são poucos
    (≤ `_VISTAS_PARCELA_MAX` dos símbolos) E cada tipo mora na sua vista
    (≥ `_VISTAS_EXCLUSIVIDADE_MIN`) — num prédio de vários andares a mesma base
    se repete por andar e a tomada aparece em TODOS: aí nada sai.
    Muta `blocks` só quando age; devolve o que viu ({} quando não há vista).
    """
    from ezdxf import bbox as _ezbbox
    msp = doc.modelspace()
    por_nome = {}
    for ins in msp.query("INSERT"):
        por_nome.setdefault(ins.dxf.name, []).append(ins)
    todos = [(i.dxf.insert.x, i.dxf.insert.y) for lst in por_nome.values() for i in lst]
    if len(todos) < 10:
        return {}
    candidatas = []
    for nome, lst in por_nome.items():
        if len(lst) < 2:
            continue
        formas = {(round(i.dxf.xscale, 4), round(i.dxf.yscale, 4),
                   round((i.dxf.rotation or 0.0) % 360.0, 3)) for i in lst}
        if len(formas) != 1:
            continue
        sx, sy, rot = formas.pop()
        if rot not in (0.0, 360.0):
            continue
        blk = doc.blocks.get(nome)
        if blk is None:
            continue
        geo = [e for e in blk if e.dxftype() != "INSERT"]
        caixa = None
        try:
            if geo:
                ext = _ezbbox.extents(geo, fast=True)
                if ext.has_data:
                    caixa = (ext.extmin.x, ext.extmin.y, ext.extmax.x, ext.extmax.y)
        except Exception:
            caixa = None
        if caixa is None:
            pts = [e.dxf.insert for e in blk if e.dxftype() == "INSERT"]
            if len(pts) < 2:
                continue
            caixa = (min(p.x for p in pts), min(p.y for p in pts),
                     max(p.x for p in pts), max(p.y for p in pts))
        w, h = (caixa[2] - caixa[0]) * abs(sx), (caixa[3] - caixa[1]) * abs(sy)
        if w <= 0 and h <= 0:
            continue
        caixas = []
        for i in lst:
            px, py = i.dxf.insert.x, i.dxf.insert.y
            x0, x1 = sorted((px + caixa[0] * sx, px + caixa[2] * sx))
            y0, y1 = sorted((py + caixa[1] * sy, py + caixa[3] * sy))
            caixas.append((x0, y0, x1, y1))
        candidatas.append((nome, lst, w, h, caixas))
    if not candidatas:
        return {}
    xs = [p[0] for p in todos] + [c[k] for b in candidatas for c in b[4] for k in (0, 2)]
    ys = [p[1] for p in todos] + [c[k] for b in candidatas for c in b[4] for k in (1, 3)]
    larg, alt = max(xs) - min(xs), max(ys) - min(ys)
    desloc = set()
    base = None
    nomes_base = set()
    for nome, lst, w, h, caixas in candidatas:
        if not ((larg > 0 and w >= _VISTAS_BASE_MIN * larg) or (alt > 0 and h >= _VISTAS_BASE_MIN * alt)):
            continue
        pts = [(i.dxf.insert.x, i.dxf.insert.y) for i in lst]
        ds = [(b[0] - a[0], b[1] - a[1]) for a in pts for b in pts if a != b]
        if not ds or any(abs(dx) < _VISTAS_SEPARACAO_MIN * w and abs(dy) < _VISTAS_SEPARACAO_MIN * h
                         for dx, dy in ds):
            continue
        desloc.update((round(dx, 6), round(dy, 6)) for dx, dy in ds)
        nomes_base.add(nome)                   # a base é a vista, não peça: não se deduplica
        if base is None or len(caixas) > len(base[1]):
            base = (nome, caixas)
    if not desloc:
        return {}

    def _dona(p):
        ks = [k for k, c in enumerate(base[1]) if c[0] <= p[0] <= c[2] and c[1] <= p[1] <= c[3]]
        return ks[0] if len(ks) == 1 else None

    grupos_por_tipo = {}
    total = repetidos = 0
    for b in blocks:
        pos = list(getattr(b, "positions", None) or [])
        if b.name in nomes_base or len(pos) != b.count or len(pos) < 2:
            continue
        pai = list(range(len(pos)))

        def _raiz(i):
            while pai[i] != i:
                pai[i] = pai[pai[i]]
                i = pai[i]
            return i
        for dx, dy in desloc:
            tol = _VISTAS_TOL * math.hypot(dx, dy)
            if tol <= 0:
                continue
            grade = {}
            for k, p in enumerate(pos):
                grade.setdefault((math.floor(p[0] / tol), math.floor(p[1] / tol)), []).append(k)
            for k, p in enumerate(pos):
                qx, qy = p[0] + dx, p[1] + dy
                cx, cy = math.floor(qx / tol), math.floor(qy / tol)
                for gx in (cx - 1, cx, cx + 1):
                    for gy in (cy - 1, cy, cy + 1):
                        for j in grade.get((gx, gy), ()):
                            if j != k and abs(pos[j][0] - qx) <= tol and abs(pos[j][1] - qy) <= tol:
                                pai[_raiz(k)] = _raiz(j)
        grupos = {}
        for k in range(len(pos)):
            grupos.setdefault(_raiz(k), []).append(k)
        total += len(pos)
        repetidos += len(pos) - len(grupos)
        grupos_por_tipo[b.name] = (b, pos, list(grupos.values()))
    if not repetidos:
        return {}
    # exclusividade: quanto de cada tipo mora na vista dele (um de cada grupo)
    na_vista = dominante = 0
    for b, pos, grupos in grupos_por_tipo.values():
        cont = Counter(_dona(pos[g[0]]) for g in grupos)
        cont.pop(None, None)
        if sum(cont.values()) >= 3:
            na_vista += sum(cont.values())
            dominante += max(cont.values())
    parcela = repetidos / float(total or 1)
    exclusiva = dominante / float(na_vista) if na_vista >= 10 else 0.0
    rep = {n: len(pos) - len(g) for n, (b, pos, g) in grupos_por_tipo.items() if len(pos) > len(g)}
    out = {"base": base[0], "vistas": len(base[1]), "parcela": round(parcela, 3),
           "exclusividade": round(exclusiva, 2), "repetidos": rep, "aplicada": False}
    if parcela > _VISTAS_PARCELA_MAX:
        out["motivo"] = "muitos símbolos repetidos — planta copiada, não vistas temáticas"
        return out
    if exclusiva < _VISTAS_EXCLUSIVIDADE_MIN:
        out["motivo"] = "os tipos se repetem entre as vistas — podem ser andares"
        return out
    novos = []
    for b in blocks:
        g = grupos_por_tipo.get(b.name)
        if g and len(g[2]) < len(g[1]):
            b_, pos, grupos = g
            # fica, de cada grupo, a posição na vista onde o tipo mais aparece
            cont = Counter(_dona(pos[x[0]]) for x in grupos)
            cont.pop(None, None)
            vista_do_tipo = cont.most_common(1)[0][0] if cont else None
            fica = [pos[next((k for k in x if _dona(pos[k]) == vista_do_tipo), x[0])] for x in grupos]
            b.positions, b.count = fica, len(fica)
        if b.count > 0:
            novos.append(b)
    blocks[:] = novos
    out["aplicada"] = True
    return out


def tipos_nas_copias(blocks, vetores_m, unit_factor, tol_m: float = 0.05) -> dict:
    """Depois que `copias_em_sombra` PROVOU os vetores da planta repetida: quais
    tipos de bloco têm peça no ponto p + v? Devolve {nome: peças em cópia}.

    🩸 29/09/2026 (job 6437838e). O detector achou os vetores certos (128,65 m
    e 82,9 m entre as 5 cópias da planta-base), mas as travas POR NOME — feitas
    pra não inventar vetor — deixaram de fora vagas, mastro, pórtico,
    carregadores e totem (1 ou 2 por cópia). Aqui nenhum vetor nasce: só se
    pergunta, com a tolerância do detector, quem mora nos vetores provados, na
    soma e na diferença dos dois e no dobro de cada (a 3ª cópia de uma fila).
    """
    try:
        uf = float(unit_factor or 0)
        if uf <= 0 or not vetores_m:
            return {}
        tol = tol_m / uf
        vs = [(float(v[0]) / uf, float(v[1]) / uf) for v in vetores_m]
        desl = set()
        for a in vs:
            desl.add(a)
            desl.add((2 * a[0], 2 * a[1]))
            for b in vs:
                if a != b:
                    desl.add((a[0] + b[0], a[1] + b[1]))
                    desl.add((a[0] - b[0], a[1] - b[1]))
        out = {}
        for b in blocks or []:
            pos = [tuple(map(float, q)) for q in (getattr(b, "positions", None) or [])]
            if len(pos) < 2:
                continue
            grade = {}
            for j, q in enumerate(pos):
                grade.setdefault((round(q[0] / tol), round(q[1] / tol)), []).append(j)
            em_copia = set()
            for i, p in enumerate(pos):
                for dx_, dy_ in desl:
                    ax, ay = p[0] + dx_, p[1] + dy_
                    ci, cj = round(ax / tol), round(ay / tol)
                    for gx in (ci - 1, ci, ci + 1):
                        for gy in (cj - 1, cj, cj + 1):
                            for j in grade.get((gx, gy), ()):
                                if j != i and math.hypot(pos[j][0] - ax, pos[j][1] - ay) <= tol:
                                    em_copia.add(j)
            if em_copia:
                out[b.name] = len(em_copia)
        return out
    except Exception:
        return {}


# 🩸 30/09/2026 (estudo do acervo, casa de 1 banheiro exportada do ArchiCAD) —
# a MESMA peça da biblioteca sai com um nome por vista: "Lavatório" na planta
# baixa e "Lavatório[16]_3" no layout (o [N] é o número da peça na biblioteca,
# o _N a vista). Vaso, lavatório, ducha, bancada e tanque saíram 2× com selo,
# deslocados EXATAMENTE (447,3; 0) m, e a sombra não via: ela casa por nome
# igual. Junta pela família SÓ o sufixo [N] da biblioteca — um "_N" solto fica:
# fora do ArchiCAD "PORTA_1" e "PORTA_2" são peças diferentes.
# 📏 Nos 93 DXF do acervo local muda só esse arquivo (0 → 6 peças); nos 6 que
# já tinham cópia o resultado fica idêntico.
_RE_SUFIXO_BIBLIOTECA_ARCHICAD = re.compile(r"\[\d+\](?:_\d+)?$")


def familia_do_bloco(nome: str) -> str:
    """'Lavatório[16]_3' → 'Lavatório'; 'PORTA_1' fica 'PORTA_1'."""
    return _RE_SUFIXO_BIBLIOTECA_ARCHICAD.sub("", nome or "").strip() or (nome or "")


def copias_em_sombra(blocks, unit_factor) -> dict:
    """A mesma planta desenhada 2 ou 3 vezes no modelo — SÓ MEDE, nada muda.

    📏 28/09/2026 (estudo de leitura, D1, 1º passo: sombra por 2 semanas). No
    elétrico do 73c6f0ed a prancha aparece em 3 faixas do modelo: o fundo de
    arquitetura ×3 e os pontos elétricos ×2 (hh 70 ≈ 36 + 34, TOMBIMEDIA110
    13 + 13) — e saem com selo. O título não resolve (letra de 12–18% da maior
    da folha). Antes de tirar selo ou peça, o log conta onde isso acontece.

    Travas do verificador (sem elas, 16 de 44 arquivos "tinham cópia"):
    - o vetor é votado por ≥5 NOMES de bloco (legenda empilhada e eixo de
      pilar dão 1–4); no vetor, o nome vota com 2+ pares ou metade das peças
      livres, e no fim só conta se os vetores, JUNTOS, casam ao menos metade
      das peças dele (hh casa 64 de 70, em dois vetores — um por andar);
    - o vetor tem ≥2 m em METROS (em cm/mm um piso no desenho não protege);
    - casamento 1 a 1, e por vetor cada peça é original OU cópia, nunca as
      duas: a grade de cadeiras encadeava 63 → 1; assim, coluna 1→2, 3→4…
      põe originais e cópias na mesma caixa, e o vetor cai no teste abaixo;
    - a caixa dos originais e a das cópias NÃO se cruzam (desenhos
      separados — duas bacias a 0,85 m não são duas plantas), o vão entre
      elas é a maior faixa na direção do vetor (1,5× o maior vão de dentro)
      e o corredor que o original varre até a cópia está vazio (≤10% dos
      pares): as metades de uma grade regular passavam no teste da caixa;
    - um vetor de cada vez: os dois andares da prancha usam vetores
      diferentes, e o ×3 é A→B (v) e depois A→C (2v).

    Devolve {} quando não achou; senão {'pecas': cópias casadas, 'vetores':
    [[dx_m, dy_m, pares, nomes, [até 3 nomes]]], 'nomes': {nome: cópias}}.
    Nome com mais de 150 posições fica de fora (custo n²).
    """
    try:
        uf = float(unit_factor or 0)
    except (TypeError, ValueError):
        return {}
    if uf <= 0:
        return {}
    tol = 0.05 / uf                      # 5 cm, no desenho
    minimo = 2.0 / uf                    # vetor ≥ 2 m
    pos = {}
    for b in blocks:
        p = [tuple(map(float, q)) for q in (getattr(b, "positions", None) or [])]
        if p and len(p) == b.count:
            pos.setdefault(familia_do_bloco(b.name), []).extend(p)
    pos = {n: p for n, p in pos.items() if 2 <= len(p) <= 150}
    if len(pos) < 5:
        return {}
    copia = {n: set() for n in pos}      # índices já casados como CÓPIA
    aceitos, vetores, por_nome = [], [], {}

    def _casar(v):
        """{nome: [(i, j)]} com j ≈ i + v; por vetor, cada índice num papel só."""
        pares = {}
        vx, vy = v
        for n, p in pos.items():
            celula = {}
            for j, q in enumerate(p):
                if j not in copia[n]:
                    celula.setdefault((round(q[0] / tol), round(q[1] / tol)), []).append(j)
            orig, cop, achados = set(), set(), []
            for i in sorted(range(len(p)), key=lambda k: p[k][0] * vx + p[k][1] * vy):
                if i in copia[n] or i in cop:
                    continue
                ax, ay = p[i][0] + vx, p[i][1] + vy
                ci, cj = round(ax / tol), round(ay / tol)
                melhor = None
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        for j in celula.get((ci + dx, cj + dy), ()):
                            if j == i or j in orig or j in cop:
                                continue
                            d = math.hypot(p[j][0] - ax, p[j][1] - ay)
                            if d <= 1.5 * tol and (melhor is None or d < melhor[0]):
                                melhor = (d, j)
                if melhor is not None:
                    orig.add(i)
                    cop.add(melhor[1])
                    achados.append((i, melhor[1]))
            if achados:
                pares[n] = achados
        return pares

    def _caixa(pts):
        xs, ys = [q[0] for q in pts], [q[1] for q in pts]
        return min(xs), min(ys), max(xs), max(ys)

    for _rodada in range(6):
        votos: dict = {}
        for n, p in pos.items():
            livres = [i for i in range(len(p)) if i not in copia[n]]
            vistos = set()
            for i in livres:
                for j in livres:
                    dx, dy = p[j][0] - p[i][0], p[j][1] - p[i][1]
                    k = (round(dx / tol), round(dy / tol))
                    if k <= (0, 0) or math.hypot(dx, dy) < minimo:
                        continue            # um sentido só; curto não é cópia de planta
                    vistos.add(k)
            for k in vistos:
                votos.setdefault(k, set()).add(n)
        # o arredondamento pode partir um vetor em dois baldes vizinhos
        cand = []
        for k, ns in votos.items():
            if len(ns) < 3:
                continue
            junto = set()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    junto |= votos.get((k[0] + dx, k[1] + dy), set())
            if len(junto) >= 5:
                cand.append((len(junto), len(ns), k))
        aceito = None
        for _nv, _nb, k in sorted(cand, reverse=True)[:10]:
            v = (k[0] * tol, k[1] * tol)
            # no vetor, o nome vota com 2+ pares ou metade das peças livres:
            # 1 par solto de um nome de 8 é coincidência (a 1ª e a última
            # mesa da fileira); o de 2 peças com 1 par é a peça copiada
            pares = {n: ps for n, ps in _casar(v).items()
                     if len(ps) >= 2 or 2 * len(ps) >= 0.5 * (len(pos[n]) - len(copia[n]))}
            if len(pares) < 5:
                continue
            origs = [pos[n][i] for n, ps in pares.items() for i, _ in ps]
            cops = [pos[n][j] for n, ps in pares.items() for _, j in ps]
            a, b = _caixa(origs), _caixa(cops)
            if a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]:
                continue                    # originais e cópias no mesmo lugar
            # Uma fileira de 8 mesas também é "duas metades de 4", e as caixas
            # das metades não se cruzam. Entre duas cópias de planta, o vão na
            # direção do vetor é a MAIOR faixa vazia; entre as metades de uma
            # grade, é igual ao passo dela.
            ux, uy = v[0] / math.hypot(*v), v[1] / math.hypot(*v)
            po = sorted(q[0] * ux + q[1] * uy for q in origs)
            pc = sorted(q[0] * ux + q[1] * uy for q in cops)
            internos = [y - x for x, y in zip(po, po[1:])] + [y - x for x, y in zip(pc, pc[1:])]
            if pc[0] - po[-1] <= 1.5 * max(internos + [0.0]):
                continue
            # ...e VAZIA: nenhuma peça desses nomes no corredor que o original
            # varre até a cópia — entre os dois na direção do vetor, e na
            # largura deles MAIS o espaçamento típico entre as peças do
            # original na outra direção. Sem a largura, a planta do andar AO
            # LADO vetava a cópia de verdade; sem a folga, a coincidência numa
            # constelação fina escapava pela vizinha de fileira.
            viz = []
            for q in origs[:300]:
                d = min((math.hypot(q[0] - r[0], q[1] - r[1]) for r in origs if r is not q), default=0.0)
                viz.append(d)
            folga = max(sorted(viz)[len(viz) // 2] if viz else 0.0, tol)
            tr = [-q[0] * uy + q[1] * ux for q in origs + cops]
            t0, t1 = min(tr) - folga, max(tr) + folga
            no_corredor = sum(1 for n in pares for i, q in enumerate(pos[n]) if i not in copia[n]
                              and po[-1] < q[0] * ux + q[1] * uy < pc[0]
                              and t0 <= -q[0] * uy + q[1] * ux <= t1)
            if no_corredor > 0.1 * len(origs):
                continue                    # uma peça perdida no meio não veta 16 pares
            aceito = (v, pares)
            break
        if aceito is None:
            break
        v, pares = aceito
        for n, ps in pares.items():
            copia[n].update(j for _, j in ps)
        aceitos.append(aceito)
    # O nome só conta se os vetores, JUNTOS, casam ao menos metade das peças
    # dele (pares de coincidência — o núcleo do prédio em andares diferentes
    # desenhados lado a lado — não passam). Junto e não por vetor: no
    # elétrico, hh tem 22 pares no térreo e 10 no superior; por vetor, o
    # superior casava 10 de 48 e o hh caía de lá.
    envolvidas: dict = {}
    for _v, pares in aceitos:
        for n, ps in pares.items():
            envolvidas.setdefault(n, set()).update(i for par in ps for i in par)
    fica = {n for n, s in envolvidas.items() if len(s) >= 0.5 * len(pos[n])}
    for v, pares in aceitos:
        pares = {n: ps for n, ps in pares.items() if n in fica}
        if len(pares) < 5:
            continue                        # sem os caronas, o vetor não se sustenta
        for n, ps in pares.items():
            por_nome[n] = por_nome.get(n, 0) + len(ps)
        top = sorted(pares, key=lambda n: -len(pares[n]))[:3]
        vetores.append([round(v[0] * uf, 2), round(v[1] * uf, 2),
                        sum(len(ps) for ps in pares.values()), len(pares), top])
    if not vetores:
        return {}
    pecas = sum(por_nome.values())
    # 🩸 01/10/2026 — H78 do estudo do acervo. Família do Revit, legenda e
    # pilha de fixação davam "planta repetida" FALSA, e a IA escrevia "o valor
    # real pode ser ~metade" em arruela/porca/parafuso que são peças iguais
    # lado a lado. Medido: a cópia VERDADEIRA põe ≥ 4,6 % das inserções do
    # arquivo em cópia; as falsas que derrubavam contagem, ≤ 2,0 %.
    # 🪤 Cobertura na caixa (< 30 %) derrubava cópia verdadeira de planta-base
    # (só a base se repete), "caixa < 2 m" depende da unidade estar certa, e
    # "menos de 10 peças" derrubava a casa do ArchiCAD de 1 banheiro (6 peças,
    # verdadeira) — fica só a fração.
    _n_ins = sum(int(getattr(b, "count", 0) or 0) for b in blocks)
    if _n_ins > 0 and pecas < _COPIA_MIN_FRACAO * _n_ins:
        logger.info("[copias] descartada: %d peça(s) em cópia de %d inserção(ões)", pecas, _n_ins)
        return {}
    return {"pecas": pecas, "vetores": vetores,
            "nomes": dict(sorted(por_nome.items(), key=lambda kv: -kv[1])[:8])}


_COPIA_MIN_FRACAO = 0.03     # H78: ≥ 3 % das inserções do arquivo em cópia


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


# ══════════════════════════════════════════════════════════════════════
#  FOLHA DE PAPEL DESENHADA NO MODELO — cada vista numa escala
# ══════════════════════════════════════════════════════════════════════
# 🩸 26/09/2026 — job 32a27efc (7 DXF de estrutura de muro de arrimo). Cada
# prancha é a FOLHA A1 inteira desenhada no MODELO, em milímetros de PAPEL
# ($INSUNITS=4, extensão 841×594, nenhuma janela de layout), e cada vista numa
# escala: fôrma em 1:125, seções em 1:25, cortes em 1:100. Quem conta a escala
# de cada vista é a cota: o DIMLFAC dela é a escala em cm por mm de papel
# (12,5 → 1:125; 2,5 → 1:25). O motor usa UM fator por arquivo: na 0001 ficou
# o milímetro do cabeçalho (tudo 125× menor, e SEM ressalva); nas outras seis a
# plausibilidade escolheu decímetro — certo numa vista, errado nas outras.
# 🔑 Não existe fator único que meça esta folha. Então não se tenta medir: a
# prancha é marcada (`escala_por_vista`) e isso vira ressalva de ESCALA —
# m/m²/m³ dela não saem medidos; contagem e kg de quadro de aço continuam.
# 📏 Alcance medido: 7 de 7 pranchas do caso; 0 dos DXF locais de controle
# (acervo antigo + casos de 25–26/09 + gabarito).
_FOLHAS_ISO_MM = ((1189.0, 841.0), (841.0, 594.0), (594.0, 420.0),
                  (420.0, 297.0), (297.0, 210.0))      # A0 … A4
_FOLHA_TOL = 0.03
_FOLHA_MIN_COTAS = 3
_FOLHA_FRACAO_FORA_DE_1 = 0.80


def _e_folha_iso(w, h) -> str:
    """Nome da folha ISO (A0–A4, ±3%, qualquer orientação) ou ''."""
    maior, menor = max(w, h), min(w, h)
    for i, (a, b) in enumerate(_FOLHAS_ISO_MM):
        if abs(maior / a - 1) <= _FOLHA_TOL and abs(menor / b - 1) <= _FOLHA_TOL:
            return "A%d" % i
    return ""


def _extensao_do_cabecalho(doc):
    """(largura, altura) de $EXTMIN/$EXTMAX, ou None se vazio ou inválido.

    🪤 O ezdxf e vários conversores gravam o "nunca calculado" como ±1e20.
    """
    try:
        emin, emax = doc.header.get("$EXTMIN"), doc.header.get("$EXTMAX")
        v = [float(emin[0]), float(emin[1]), float(emax[0]), float(emax[1])]
    except Exception:
        return None
    if any(x != x or abs(x) >= 1e19 for x in v):
        return None
    w, h = v[2] - v[0], v[3] - v[1]
    return (w, h) if w > 0 and h > 0 else None


def histograma_dimlfac(doc) -> dict:
    """{DIMLFAC efetivo: nº de cotas} do modelo. Nunca levanta.

    Mesma régua de `_unidade_por_dimlfac` (override → estilo → 1), com o mesmo
    teto de varredura das cotas.
    """
    c: Counter = Counter()
    try:
        for i, dim in enumerate(doc.modelspace().query("DIMENSION")):
            if i >= _DIM_MAX_SCAN:
                break
            try:
                med = dim.get_measurement()
            except Exception:
                continue
            if not isinstance(med, (int, float)) or abs(med) <= 1e-9:
                continue
            c[round(_dim_effective_dimlfac(doc, dim), 4)] += 1
    except Exception:
        pass
    return dict(c)


def lfac_para_log(hist) -> str:
    """'{12.5:54,2.5:48}' — o histograma numa linha, do mais comum pro menos."""
    itens = sorted((hist or {}).items(), key=lambda kv: -kv[1])
    return "{" + ",".join("%g:%d" % (k, n) for k, n in itens[:8]) + "}"


def folha_de_papel_no_modelo(doc):
    """A prancha é a FOLHA DE PAPEL desenhada no modelo, com vistas em escala?

    Devolve None, ou {"folha", "cotas", "fora_de_1", "escalas", "texto"} —
    `escalas` = [(denominador, nº de cotas)], `texto` = "1:125 (54 cotas), …".
    Pura: só lê o doc. Nunca levanta.

    Critério (TODOS):
      · $INSUNITS 0 ou 4 — o milímetro do papel;
      · nenhuma janela de viewport — quem monta a folha no layout não desenha
        a folha no modelo;
      · extensão de folha ISO A0–A4 (±3%) — do cabeçalho; das entidades
        quando o cabeçalho está vazio ou inválido (1e20);
      · ≥3 cotas lineares e ≥80% delas com razão efetiva ≠ 1: a cota exibe
        OUTRO número que a medida do desenho, ou seja, a vista está em escala.
    Razão efetiva = número exibido / medida: na cota automática é o DIMLFAC,
    na digitada é o número escrito — `_dim_displayed_number` dá as duas.

    🪤 O denominador (DIMLFAC × 10) supõe a cota em CENTÍMETRO, como na
    estrutura e na arquitetura brasileiras. Serve pra DIZER a escala ao
    cliente; a decisão de marcar não depende dele.
    """
    try:
        if int(doc.header.get("$INSUNITS", 0) or 0) not in (0, 4):
            return None
        for lay in doc.layouts:
            for vp in lay.query("VIEWPORT"):
                if _janela_da_viewport(vp) is not None:
                    return None
        msp = doc.modelspace()
        n = fora = 0
        for i, dim in enumerate(msp.query("DIMENSION")):
            if i >= _DIM_MAX_SCAN:
                break
            try:
                if dim.dimtype not in (0, 1):
                    continue            # só cota linear/alinhada é régua
                med = float(dim.get_measurement())
            except Exception:
                continue
            if med <= 1e-9:
                continue
            mostrado = _dim_displayed_number(doc, dim, med)
            if mostrado is None or mostrado[0] <= 0:
                continue
            n += 1
            if abs(mostrado[0] / med - 1.0) > _DIM_RATIO_TOL:
                fora += 1
        if n < _FOLHA_MIN_COTAS or fora < _FOLHA_FRACAO_FORA_DE_1 * n:
            return None
        ext = _extensao_do_cabecalho(doc) or _compute_block_bbox(msp)
        folha = _e_folha_iso(*ext) if ext else ""
        if not folha:
            return None
        hist = histograma_dimlfac(doc)
        escalas = [(round(lf * 10, 1), c) for lf, c in
                   sorted(hist.items(), key=lambda kv: -kv[1])
                   if c >= _FOLHA_MIN_COTAS and abs(lf - 1.0) > _DIM_RATIO_TOL]
        texto = ", ".join("1:%s (%d cotas)" % (("%g" % d).replace(".", ","), c)
                          for d, c in escalas)
        return {"folha": folha, "cotas": n, "fora_de_1": fora, "escalas": escalas,
                "texto": texto or ("%d de %d cotas exibem outro número que a "
                                   "medida do desenho" % (fora, n))}
    except Exception as exc:
        logger.warning("[folha-no-modelo] falhou (ignorado): %s", exc)
        return None


def _classe_do_anonimo(nome: str) -> str:
    """Classe do bloco que o filtro de nome joga fora — SÓ pro log.

    📏 27/09/2026 (estudo de leitura, item 5): `anonimo=N` juntava lixo do
    AutoCAD (*X de hachura), bloco dinâmico (*U, que pode ser porta), desenho
    colado (A$C) e peça de xref ligado ($0$). O conserto de cada um depende de
    quanto pesa; sem a classe, a decisão seria no escuro."""
    n = (nome or "").upper()
    if n.startswith("*U"):
        return "*U"
    if n.startswith("*X"):
        return "*X"
    if n.startswith("*"):
        return "*outro"
    for marca in ("$0$", "A$C", "G$C"):
        if marca in n:
            return marca
    if n.startswith("ZW$"):
        return "zw$"
    return "$outro"


def _nome_do_bloco_dinamico(doc, nome: str):
    """Nome do bloco dinâmico por trás de um '*U' (XDATA AcDbBlockRepBTag do
    registro do bloco), ou None quando o conversor não guardou o vínculo."""
    try:
        for t in doc.block_records.get(nome).get_xdata("AcDbBlockRepBTag"):
            if t.code == 1005:
                e = doc.entitydb.get(t.value)
                return e.dxf.name if e is not None else None
    except Exception:
        return None
    return None


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
    _regua_1a = dim_check      # 📏 27/09 (item 5): o log guarda o que as cotas disseram
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
            _plaus = _unidade_por_plausibilidade(doc, unit_factor, cotas=_regua_1a)
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
    # 🩸 26/09/2026 — job 32a27efc: a FOLHA inteira desenhada no modelo, cada
    # vista numa escala (ver `folha_de_papel_no_modelo`). Roda DEPOIS da
    # cascata e fora dela: não escolhe fator — não existe um que sirva — só
    # marca a prancha. 🪤 Não entra em `unit_warnings`/`alerta_unidade`: a 5ª
    # régua apaga essa chave quando dois rótulos de área batem, e bater numa
    # vista não prova as outras.
    _folha_papel = folha_de_papel_no_modelo(doc)
    # 📏 O histograma vai pro log `motor:unidade` de TODA prancha com cota —
    # sem ele não dá pra medir no acervo quantas são folha de papel.
    _lfac_hist = histograma_dimlfac(doc)
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
        # 🩸 27/09: régua "ambigua" É ressalva de escala — ver a função. Se o
        # consenso do projeto trocou o fator (escala provada por cota em outra
        # prancha), a ambiguidade desta foi resolvida: não é ressalva.
        _amb = "" if _unit_consenso else ressalva_da_escala_ambigua(dim_check)
        if _amb:
            metadata["escala_ambigua"] = _amb
        # 🩸 29/09: sem unidade no cabeçalho, cm E metro cabiam na largura e o
        # fator saiu de um DESEMPATE (`_fator_pelos_objetos`). Se as cotas não
        # provaram, é ressalva de escala — m/m²/m³ não saem medidos. Antes, o
        # que segurava isto no job 6437838e era a ressalva do DUTO, por acaso.
        _desemp = "" if _unit_consenso else ressalva_da_unidade_por_desempate(
            getattr(doc, "_aiarq_voto_objetos", None), _dim_status)
        if _desemp:
            metadata["unidade_por_desempate"] = _desemp
        # 🩸 30/09: o fator é o palpite de mm (nem cabeçalho, nem largura, nem
        # nota) e as cotas não provaram — m/m²/m³ não saem medidos. Job 9a2c5d87.
        _cega = "" if _unit_consenso else ressalva_da_unidade_cega(
            bool(getattr(doc, "_aiarq_unidade_palpite", None))
            and abs(float(unit_factor) - 0.001) < 1e-12, _dim_status)
        if _cega:
            metadata["unidade_cega"] = _cega
        if dim_check.get("motivo"):
            metadata["regua_cotas_motivo"] = str(dim_check["motivo"])[:200]
        # 📏 27/09 (estudo, item 5): quando o DIMLFAC ou a plausibilidade
        # decidem, `dim_check` vira o deles e o que as COTAS disseram sumia
        # do log (30 de 30 pranchas com `porque=-`).
        if _regua_1a is not dim_check:
            metadata["regua_cotas_antes"] = "%s|%s|%s" % (
                _regua_1a.get("status") or "-", _regua_1a.get("cotas_utilizaveis", "-"),
                str(_regua_1a.get("motivo") or "-")[:200])
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
    # 🔑 Ressalva de ESCALA com chave própria (engine_rules
    # `_RESSALVAS_SO_DE_ESCALA`): m/m²/m³ desta prancha não saem medidos.
    if _folha_papel:
        metadata["escala_por_vista"] = _folha_papel["texto"]
    if _lfac_hist:
        metadata["lfac_por_cota"] = lfac_para_log(_lfac_hist)

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
    # 🩸 30/09/2026 (H16 do estudo): os símbolos do TQS contados como PEÇA — 14
    # plantas de fôrma de um cliente, 10+ linhas com selo ("indicação de desnível
    # 85 un", "AVCR 19 un"). O que cada um desenha (sem texto nenhum):
    # `_DESNIV` = círculo + 2 linhas (desnível); `_CORTEA`… = a marca do corte;
    # `AVCR` = círculo com cruz colado aos "a", "b", "a×b" de um detalhe que se
    # repete em todo andar; `SN` = círculo + 3 linhas ao lado de cotas (nível).
    # 🪤 NÃO é o prefixo "_": `_VAONER065250652500550005500` é o VÃO da laje
    # nervurada — a cubeta, peça de verdade, 2.719 num pavimento só.
    # 🪤 "SN" é curto demais pra valer em qualquer desenho: só é símbolo quando o
    # arquivo tem outra marca do TQS. No acervo (111 desenhos), esses nomes só
    # aparecem nos 14 do TQS.
    _TQS_SIMBOLOS = {"_DESNIV", "AVCR"}
    _TQS_CORTE_RE = re.compile(r"^_CORTE[A-Z]?$", re.IGNORECASE)
    try:
        _nomes_def = {str(b.name).upper() for b in doc.blocks}
    except Exception:
        _nomes_def = set()
    _arquivo_tqs = bool(_nomes_def & _TQS_SIMBOLOS) or any(
        _TQS_CORTE_RE.match(n) or n.startswith("_VAONER") for n in _nomes_def)

    def _is_annotation_block(name: str) -> bool:
        if not name:
            return False
        if _ANNOTATION_NAME_RE.match(name):
            return True
        if _XREF_NAME_RE.search(name):
            return True
        if name.upper() in _ANNOTATION_EXACT_NAMES:
            return True
        if name.upper() in _TQS_SIMBOLOS or _TQS_CORTE_RE.match(name):
            return True
        if _arquivo_tqs and name.upper() == "SN":
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
    _desc = {"anonimo": 0, "utilitario": 0, "anotacao": 0, "ilegivel": 0, "duplicado": 0}
    # 🩸 27/09/2026 — a janela JA7 da folha de detalhe do banheiro estava
    # inserida DUAS vezes no MESMO ponto (cópia em cima da cópia, invisível no
    # CAD) e saía "4 ✓" com a planta repetida; no desenho é 1. Duas inserções
    # do mesmo bloco no mesmo ponto, mesma rotação, mesma escala e mesmos
    # atributos são a mesma peça: conta uma.
    _ja_inserido = set()
    _amostra_anonimo = []
    # 📏 27/09 (estudo, item 5): SÓ registro — nada aqui muda contagem.
    _anon_classe: dict = {}               # classe → inserções descartadas
    _dinamico_de: dict = {}               # '*U12' → nome do dinâmico (cache)
    _dinamicos: dict = {}                 # nome do dinâmico → inserções
    _espelhados: dict = {}                # nome → inserções com extrusão z<0
    _def_vazia: dict = {}                 # nome → inserções de bloco sem desenho
    _vazia_cache: dict = {}
    _blocos_desligados = 0
    _layers_desligados = set()
    try:
        for _lt in doc.layers:
            if _lt.is_frozen() or _lt.is_off():
                _layers_desligados.add(_lt.dxf.name.upper())
    except Exception:
        pass

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

    # 🩸 26/09/2026, job 32a27efc: a CAIXA de cada inserção contada, pra achar
    # o símbolo desenhado na legenda (ver `amostras_de_legenda`). A caixa da
    # DEFINIÇÃO sai uma vez por nome (mesmo cache de cima) e vai pro lugar
    # pelos 4 cantos. ATTDEF é molde de atributo, não desenho: fica de fora.
    _caixa_def: dict = {}
    _insercoes_caixa: list = []           # [(nome, caixa, pos)]

    def _caixa_da_insercao(ins):
        n = ins.dxf.name
        if n not in _caixa_def:
            c = None
            try:
                b = doc.blocks.get(n)
                if b is not None:
                    eb = _ezbbox.extents((e for e in b if e.dxftype() != "ATTDEF"),
                                         cache=_bbox_cache)
                    if eb.has_data:
                        c = (eb.extmin.x, eb.extmin.y, eb.extmax.x, eb.extmax.y)
            except Exception:
                c = None
            _caixa_def[n] = c
        c = _caixa_def[n]
        if c is None:
            return None
        try:
            m = ins.matrix44()
            ps = [m.transform((px, py, 0)) for px in (c[0], c[2]) for py in (c[1], c[3])]
            return (min(p[0] for p in ps), min(p[1] for p in ps),
                    max(p[0] for p in ps), max(p[1] for p in ps))
        except Exception:
            return None

    for insert in msp.query("INSERT"):
        try:
            bname = insert.dxf.name
            layer = insert.dxf.layer
            # 🩸 27/09/2026 (estudo, item 8): o ponto de inserção está no OCS
            # da peça. Com a extrusão virada (0,0,-1 — bloco espelhado no
            # eixo Z) o x sai com o SINAL TROCADO: no R17, IC e CG caíam em
            # −76 m em vez de +76 m, fora de qualquer folha. A posição vai
            # pro WCS; a contagem não muda.
            _p = insert.ocs().to_wcs(insert.dxf.insert)
            x, y = float(_p[0]), float(_p[1])
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
            _cl = _classe_do_anonimo(bname)
            _anon_classe[_cl] = _anon_classe.get(_cl, 0) + 1
            if _cl == "*U":
                if bname not in _dinamico_de:
                    _dinamico_de[bname] = _nome_do_bloco_dinamico(doc, bname)
                if _dinamico_de[bname]:
                    _dinamicos[_dinamico_de[bname]] = _dinamicos.get(_dinamico_de[bname], 0) + 1
            continue
        # Skip utility / system layers that don't represent real items
        if layer and layer.upper() in _UTILITY_LAYERS_UPPER:
            _desc["utilitario"] += 1
            continue
        # Skip annotation / callout blocks (legendas, TAGs, cortes, elevações)
        if _is_annotation_block(bname):
            _desc["anotacao"] += 1
            continue
        try:
            _d = insert.dxf
            _chave_ins = (bname, round(x, 4), round(y, 4), round(float(_d.get("rotation", 0) or 0), 3),
                          round(float(_d.get("xscale", 1) or 1), 4),
                          round(float(_d.get("yscale", 1) or 1), 4),
                          tuple(round(float(c), 3) for c in _d.get("extrusion", (0, 0, 1))),
                          tuple(sorted((a.dxf.tag, a.dxf.text) for a in insert.attribs)))
        except Exception:
            _chave_ins = None
        if _chave_ins is not None:
            if _chave_ins in _ja_inserido:
                _desc["duplicado"] += 1
                continue
            _ja_inserido.add(_chave_ins)

        if bname not in block_counter:
            block_counter[bname] = {
                "count": 0, "layer": layer, "positions": [],
                "widths": [], "heights": [], "camadas": {},
            }
        block_counter[bname]["count"] += 1
        _cam = block_counter[bname]["camadas"]
        _cam[layer] = _cam.get(layer, 0) + 1
        try:
            if float(insert.dxf.get("extrusion", (0, 0, 1))[2]) < 0:
                _espelhados[bname] = _espelhados.get(bname, 0) + 1
            if bname not in _vazia_cache:
                _b = doc.blocks.get(bname)
                _vazia_cache[bname] = _b is not None and not any(
                    e.dxftype() != "ATTDEF" for e in _b)
            if _vazia_cache[bname]:
                _def_vazia[bname] = _def_vazia.get(bname, 0) + 1
            if layer and layer.upper() in _layers_desligados:
                _blocos_desligados += 1
        except Exception:
            pass
        _onde = _centro_do_desenho(insert)
        if _onde is not None:
            x, y = _onde
            metadata["blocos_pelo_desenho"] = metadata.get("blocos_pelo_desenho", 0) + 1
        block_counter[bname]["positions"].append((round(x, 2), round(y, 2)))
        _cx = _caixa_da_insercao(insert)
        if _cx is not None:
            _insercoes_caixa.append((bname, _cx, (round(x, 2), round(y, 2))))

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
            camadas=dict(info.get("camadas") or {}),
        )
        for name, info in block_counter.items()
    ]

    if not blocks:
        logger.warning(
            "Nenhum bloco (INSERT) usado no DXF: %s — descartados: %s%s",
            filepath, _desc,
            (" amostra=" + ", ".join(_amostra_anonimo)) if _amostra_anonimo else "")

    # 📏 27/09 (estudo, item 5): procedência dos blocos, só pro log do motor
    def _mais(d, n=5):
        return dict(sorted(d.items(), key=lambda kv: -kv[1])[:n])
    _proc_blocos = {}
    if _anon_classe:
        _proc_blocos["anonimos"] = _anon_classe
    if _dinamicos:
        _proc_blocos["dinamicos"] = _mais(_dinamicos)
    if _espelhados:
        _proc_blocos["espelhados"] = _mais(_espelhados)
    if _def_vazia:
        _proc_blocos["def_vazia"] = _mais(_def_vazia)
    # 📏 28/09 (estudo, item 5 — ANINHADOS): peça dentro de bloco com nome não
    # entra na contagem — o bloco "banheiro tipo 1" conta 3 e os 12 vasos de
    # dentro dele somem (job dd52081b). Pro log: os 5 pais com mais peças
    # dentro, os 3 filhos principais (× inserções do pai); filho em layer
    # desligado e pai que é vínculo de modelo vêm marcados. Não conta nada.
    try:
        from engine_rules import e_vinculo_de_modelo as _e_vinc
        _filhos_por_pai = {}
        for _pai, _info in block_counter.items():
            _bdef = doc.blocks.get(_pai)
            if _bdef is None:
                continue
            _cont = {}
            for _e in _bdef:
                if _e.dxftype() != "INSERT":
                    continue
                _fn = str(_e.dxf.name or "")
                if _fn.startswith("*") or _is_annotation_block(_fn):
                    continue
                _rot = _fn[:30] + (" (desl)" if str(_e.dxf.get("layer", "") or "").upper()
                                   in _layers_desligados else "")
                _cont[_rot] = _cont.get(_rot, 0) + 1
            if _cont:
                _n_pai = int(_info.get("count") or 1)
                _top = sorted(_cont.items(), key=lambda kv: -kv[1])[:3]
                _chave = _pai[:30] + (" (vínculo)" if _e_vinc(_pai) else "")
                _filhos_por_pai[_chave] = (sum(_cont.values()) * _n_pai,
                                           {k: v * _n_pai for k, v in _top})
        if _filhos_por_pai:
            _proc_blocos["aninhados"] = {
                p: f for p, (_t, f) in sorted(_filhos_por_pai.items(), key=lambda kv: -kv[1][0])[:5]}
    except Exception as _ean:
        logger.warning("[aninhados] falhou (não-fatal): %s", _ean)
    # 🩸 30/09 (H13): o vínculo do Revit da MESMA disciplina é o conteúdo
    try:
        _pv = pecas_no_vinculo(doc, list(block_counter.keys()), filepath, _is_annotation_block)
        if _pv:
            metadata["pecas_no_vinculo"] = _pv
    except Exception as _epv:
        logger.warning("[vinculo-conteudo] falhou (não-fatal): %s", _epv)
    if _proc_blocos:
        metadata["procedencia_blocos"] = _proc_blocos

    # ---- Lines / polylines (wall segments) --------------------------------
    walls: list[WallSegment] = []
    # 25/09: o que a LEGENDA da prancha diz ser leito/duto desenhado em duas
    # linhas (o nome do layer pode ser só um código, "K-04")
    _legenda_dupla = _legenda_de_linha_dupla(msp)
    _layers_linha_dupla = set(_legenda_dupla)

    # 🩸 01/10/2026 — H84 do estudo do acervo: CÓPIA EXATA em pilha. A mesma
    # treliça colada 16× no mesmo lugar (68,7 m → 1.099 m), difusores colados
    # uns sobre os outros (611 trechos, 247 repetidos 4×+), a rampa com as 40
    # linhas 2×. Copiar-colar em pilha não é obra: conta UMA vez, só quando a
    # cópia é do MESMO tipo — LINE com as mesmas pontas (±1 mm), ou polilinha
    # ABERTA com os mesmos vértices. 🪤 Polilinha FECHADA e aresta de figura
    # sobre linha ficam: o lado comum de duas figuras vizinhas é legítimo
    # (rodapé e pintura dos dois lados).
    _tol_copia = 0.001 / unit_factor if unit_factor else 0.001
    _vistas_copia: set = set()
    _copias_exatas: dict = {}

    def _ja_visto(chave, layer, metros) -> bool:
        if chave in _vistas_copia:
            _c = _copias_exatas.setdefault(str(layer), {"m": 0.0, "n": 0})
            _c["m"] += metros
            _c["n"] += 1
            return True
        _vistas_copia.add(chave)
        return False

    def _q(p):
        return (round(p[0] / _tol_copia), round(p[1] / _tol_copia))

    for line in msp.query("LINE"):
        try:
            start = (line.dxf.start.x, line.dxf.start.y)
            end = (line.dxf.end.x, line.dxf.end.y)
            length = _line_length(start, end) * unit_factor
            if length > 0 and _ja_visto(("L", str(line.dxf.layer)) + tuple(sorted((_q(start), _q(end)))),
                                        line.dxf.layer, length):
                continue
            if length > 0:
                walls.append(WallSegment(
                    layer=line.dxf.layer,
                    length=length,
                    start=start,
                    end=end,
                ))
        except Exception:
            continue

    from engine_rules import layer_e_parede as _layer_e_parede
    for lwpoly in msp.query("LWPOLYLINE"):
        try:
            length = _lwpolyline_length(lwpoly) * unit_factor
            if length > 0 and not lwpoly.closed:
                # H84: polilinha ABERTA idêntica (mesmos vértices, qualquer sentido)
                _vq = [(_q(p) + (round(float(p[2]), 3),)) for p in lwpoly.get_points(format="xyb")]
                _vq_r = [(_q(p) + (round(-float(p[2]), 3),)) for p in reversed(list(lwpoly.get_points(format="xyb")))]
                if _ja_visto(("P", str(lwpoly.dxf.layer)) + tuple(min(_vq, _vq_r)), lwpoly.dxf.layer, length):
                    continue
            if length > 0:
                pts = list(lwpoly.get_points(format="xy"))
                start = pts[0] if pts else (0, 0)
                end = pts[-1] if pts else (0, 0)
                _pontos = ()
                # os lados da polilinha, pra o pareamento das faces (duto, leito
                # e — 26/09 — parede: sem eles a parede em polilinha entrava
                # como UMA reta do 1º ao último vértice e não pareava)
                if (lwpoly.dxf.layer in _layers_linha_dupla or _RE_DUTO_DUPLO.search(str(lwpoly.dxf.layer))
                        or _layer_e_parede(lwpoly.dxf.layer)
                        or _RE_LAYER_DE_TUBO.search(str(lwpoly.dxf.layer))):
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

    if _copias_exatas:
        # H84: o que a cópia em pilha somaria (rastro pro log; a soma já é 1×)
        metadata["copias_exatas"] = {ly: {"m": round(v["m"], 2), "n": v["n"]}
                                     for ly, v in _copias_exatas.items()}
        logger.info("[copia-exata] %d trecho(s) repetido(s) contado(s) 1×: %s",
                    sum(v["n"] for v in _copias_exatas.values()),
                    ", ".join("%s %.1f m" % (k, v["m"]) for k, v in list(_copias_exatas.items())[:5]))

    for poly in msp.query("POLYLINE"):
        try:
            length = _polyline_length(poly) * unit_factor
            if length > 0:
                verts = [(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
                start = verts[0] if verts else (0, 0)
                end = verts[-1] if verts else (0, 0)
                # 🩸 30/09/2026 (H52 do estudo do acervo): a POLILINHA "pesada"
                # (2D/3D, com VERTEX) ia sem os lados, como a LWPOLYLINE antes de
                # 25/09. Uma parede desenhada pelo contorno — vai 71 m e volta a
                # 15 cm — virava uma reta de 15 cm do 1º ao último vértice, e o
                # eixo nunca a via: 239 dos 457 m de alvenaria de um projeto de
                # cliente eram as duas faces somadas. Mesma regra da LWPOLYLINE
                # (só layer candidato a linha dupla); malha e polyface não são
                # caminho. A 3D vai no plano (o z era lixo) e sem arco.
                _pontos = ()
                _lay_p = str(poly.dxf.layer)
                if (verts and (poly.is_2d_polyline or poly.is_3d_polyline)
                        and (poly.dxf.layer in _layers_linha_dupla or _RE_DUTO_DUPLO.search(_lay_p)
                             or _layer_e_parede(poly.dxf.layer) or _RE_LAYER_DE_TUBO.search(_lay_p))):
                    _blg = [float(v.dxf.get("bulge", 0) or 0) if poly.is_2d_polyline else 0.0
                            for v in poly.vertices]
                    _xyb = [(x, y, b) for (x, y), b in zip(verts, _blg)]
                    if poly.is_closed:
                        _xyb.append(_xyb[0])
                    _pontos = tuple(_xyb)
                walls.append(WallSegment(
                    layer=poly.dxf.layer,
                    length=length,
                    start=start,
                    end=end,
                    pontos=_pontos,
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

    # SPLINEs (30/09, H10): eletroduto e circuito desenhados em curva. Sem
    # isto, o layer só tinha a amostra reta da legenda e saía "✓ MEDIDO 0,6 m".
    # Teto de quantidade: texto explodido em curva pode trazer dezenas de
    # milhares — passando dele, pára e registra (nunca derruba a prancha).
    _spl_n = 0
    _spl_por_layer: dict = {}
    _spl_simbolo = 0
    from engine_rules import layer_is_anotacao as _anot_spl
    for spl in msp.query("SPLINE"):
        if _spl_n >= _MAX_SPLINES:
            break
        try:
            if (_RE_LAYER_SIMBOLO_EM_CURVA.search(str(spl.dxf.layer))
                    or _anot_spl(spl.dxf.layer)):
                _spl_simbolo += 1
                continue                 # antes de achatar: não custa tempo
            _pts_s = _spline_pontos(spl)
            length = sum(_line_length(_pts_s[i], _pts_s[i + 1])
                         for i in range(len(_pts_s) - 1)) * unit_factor if _pts_s else 0.0
            if length > 0:
                _spl_n += 1
                _lay_s = spl.dxf.layer
                _spl_por_layer[_lay_s] = _spl_por_layer.get(_lay_s, 0.0) + length
                # como no ARC: `length` é a curva; start/end, as pontas
                walls.append(WallSegment(layer=_lay_s, length=length,
                                         start=_pts_s[0], end=_pts_s[-1], curvo=True))
        except Exception:
            continue
    if _spl_n:
        _top_s = sorted(_spl_por_layer.items(), key=lambda kv: -kv[1])[:5]
        metadata["splines_medidas"] = "%d SPLINE, %.2f m | %s" % (
            _spl_n, sum(_spl_por_layer.values()),
            " · ".join("%s %.2f m" % (l, m) for l, m in _top_s))
    if _spl_simbolo:
        metadata["splines_medidas"] = (metadata.get("splines_medidas", "0 SPLINE")
                                       + " | fora (símbolo/anotação): %d" % _spl_simbolo)

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
    _metro_de_bloco: dict = {}       # H76: {layer: [metro de dentro de bloco, {inserções}]}
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
                        if _et not in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC", "SPLINE"):
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
                            elif _et == "SPLINE":
                                _L = _spline_length(_e)
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
                            # H76: quanto do layer veio de dentro de bloco, e de quantas inserções
                            _st = _metro_de_bloco.setdefault(str(_lay), [0.0, set()])
                            _st[0] += _L
                            _st[1].add(id(insert))
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
    # 🔑 H94 (02/10/2026): contorno fechado SÓ COMO REGIÃO DE PROVA da 5ª régua
    # (rótulo de área × região). A allowlist acima continua valendo pra MEDIR:
    # nada daqui entra em `polygon_areas`, `walls` ou nas somas. Medido no
    # acervo: o cômodo de um sobrado estava no layer "INVISIVEIS" (34 rótulos
    # "QUARTO 1 Ar = 12.34 m²" batendo) e a peneira de nome jogava fora.
    # Aninhado entra (o cômodo dentro do piso é a região do rótulo); layer da
    # denylist (cota, legenda, quadro…) continua fora.
    _contornos_de_prova: list = []
    _MAX_CONTORNOS_DE_PROVA = 20000

    def _guardar_contorno_de_prova(layer_name, pts, a):
        if a < 0.5 or len(_contornos_de_prova) >= _MAX_CONTORNOS_DE_PROVA:
            return
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        _w, _h = max(xs) - min(xs), max(ys) - min(ys)
        if _w <= 0 or _h <= 0 or not area_factor:
            return
        _contornos_de_prova.append(HatchArea(
            layer=layer_name, area=a, pattern="contorno de prova",
            bbox=(min(xs), min(ys), max(xs), max(ys)),
            preenchimento=round(min(1.0, (a / area_factor) / (_w * _h)), 4)))

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
                # H94: só região de prova — não vira medição
                _guardar_contorno_de_prova(layer_name, pts, abs(_shoelace_area(pts)) * area_factor)
                return  # allowlist: só superfície física reconhecível
            a = abs(_shoelace_area(pts)) * area_factor
            if a < 0.5:
                _poly_recusa["area_minima"] += 1
                return
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            _poly_cands.append((a, (min(xs), min(ys), max(xs), max(ys)), layer_name))
            _guardar_contorno_de_prova(layer_name, pts, a)
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
                from engine_rules import layer_de_hachura_de_parede as _lhp
                hatches.append(HatchArea(
                    layer=hatch.dxf.layer,
                    area=area,
                    pattern=pattern,
                    bbox=_bb,
                    preenchimento=round(_fill, 4),
                    secao_de_parede=bool(_lhp(hatch.dxf.layer)
                                         and _hachura_e_secao_de_parede(hatch, unit_factor)),
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

    # 🩸 26/09/2026, job 32a27efc: o símbolo desenhado na LEGENDA (ver
    # `amostras_de_legenda`). Calcula aqui, com as posições de ANTES da leitura
    # por folha; o número vai pro bloco depois dela, pelas posições que ficaram.
    try:
        _amostra_pos = amostras_de_legenda(
            _insercoes_caixa,
            [(t.text, t.position[0], t.position[1], t.height) for t in texts])
    except Exception as _eam:
        logger.warning("[amostra-legenda] falhou (não-fatal): %s", _eam)
        _amostra_pos = {}

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
    # 🩸 30/09 (H51): a espessura da parede desmente a unidade lida — ANTES do
    # eixo, que junta as faces que esta régua mede. Fator do consenso do
    # projeto veio de cota de outra prancha, ou a nota do desenho com as cotas
    # explodidas decidiu: provado, não entra.
    try:
        if not _unit_consenso and not (getattr(doc, "_aiarq_nota_cota", None) or (None,))[0]:
            _pf = unidade_contradita_pela_parede(walls, unit_factor, dim_check.get("status"),
                                                 _texto_mediano_do_modelo(doc))
            if _pf:
                metadata["unidade_contradita_pela_parede"] = ressalva_da_parede_fina(_pf, unit_factor)
                logger.warning("[unit-parede] %s: %s", os.path.basename(filepath), _pf)
    except Exception as _epf:
        logger.warning("[unit-parede] falhou (não-fatal): %s", _epf)
    # 26/09: parede em duas faces também mede pelo EIXO (ver a função)
    _zona_cinza_parede: dict = {}
    _faces_espessas: list = []          # E12: a parede de mais de 40 cm (ver a função)
    walls, _rel_parede = _corrigir_parede_linha_dupla(walls, unit_factor, _zona_cinza_parede,
                                                      _faces_espessas)
    if _rel_parede:
        metadata["parede_linha_dupla"] = _rel_parede
    if _zona_cinza_parede:
        # layer de parede com 15–50% em duas linhas: o eixo não rodou e a
        # soma pode contar as duas faces (a chave do selo não usa)
        metadata["parede_zona_cinza"] = _zona_cinza_parede
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
    # 🩸 28/09/2026 (job dd52081b): quantas unidades o quadro declara — é contra
    # isso que o main confere as cozinhas contadas (`cozinhas_acima_das_unidades`)
    try:
        from engine_rules import unidades_do_quadro as _unid_quadro
        _uq = _unid_quadro([(getattr(t, "text", ""), float(t.position[0]), float(t.position[1]),
                             float(getattr(t, "height", 0) or 0)) for t in texts])
        if _uq:
            metadata["unidades_do_quadro"] = _uq
    except Exception as _euq:
        logger.warning("[unidades-quadro] falhou (não-fatal): %s", _euq)

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
                                  unidade_provada_por_rotulo as _prova5,
                                  pares_de_prova_por_rotulo as _pares94,
                                  rotulo_area_de_comodo as _rot94)
        _p5 = _casar5(texts, list(polygon_areas) + list(hatches))
        _v5 = _prova5(_p5)
        # 🔑 H94 (02/10/2026) — quando a régua de hoje não prova, a mesma régua
        # com três aberturas, medidas no acervo (de 3 para 21 provas em 94
        # desenhos com rótulo "m²"; ×100 e ÷100 não provam em nenhum):
        #   (1) o rótulo com o número no FIM ("SALA ÁREA=9,99m²", "Ar = 12.34 m²");
        #   (2) contorno fechado de QUALQUER layer como região (`_contornos_de_prova`,
        #       nunca medição);
        #   (3) só os rótulos de área disputam a região (o nome não a ocupa antes).
        # Rótulo e contorno de LOTE/TERRENO/DIVISA/IMPLANTAÇÃO não provam: no
        # evaa4391 a implantação estava em cm e o prédio em mm.
        # 🪤 E ≥ 10 % dos rótulos batendo: com o contorno de QUALQUER layer há
        # muito mais região pra um par casar por acaso. Nos 6 desenhos que
        # destravam no acervo a razão é 34–79 %; os de 3–4 % (5 de 196, 4 de
        # 118) não tinham trava e ficam sem esta prova nova.
        _PROVA_COMODO_FRACAO_MIN = 0.10
        _prova_h94 = None
        if not _v5.get("provada"):
            _v94 = _prova5(_pares94(texts, list(_contornos_de_prova) + list(hatches)),
                           leitor=_rot94)
            if _v94.get("provada") and (int(_v94.get("n_batem") or 0)
                                        >= _PROVA_COMODO_FRACAO_MIN
                                        * max(1, int(_v94.get("n_rotulos_area") or 0))):
                _prova_h94 = _v94
        _vp = _prova_h94 or _v5
        if _vp.get("provada"):
            _ex = "; ".join(f'"{e["texto"]}"={e["medida"]}' for e in _vp["exemplos"][:3])
            metadata["unidade_provada_por_rotulo"] = (
                f"{_vp['n_batem']} rótulo(s) de área da própria prancha conferem "
                f"com a geometria medida ({_ex}) — escala provada pelo desenho.")
            if _prova_h94:
                # registro do log (fora do prompt): qual caminho provou
                metadata["prova_por_rotulo_de_comodo"] = {
                    "rotulos": int(_prova_h94.get("n_rotulos_area") or 0),
                    "batem": int(_prova_h94.get("n_batem") or 0),
                    "contornos": len(_contornos_de_prova)}
            # a prova supera a ressalva de ESCALA (não as outras)
            # 🩸 27/09: a régua ambígua também — o rótulo desempata o que as
            # cotas não desempataram. A folha de papel (escala_por_vista) NÃO:
            # um rótulo prova UMA vista, não a folha inteira.
            for _k in ("unidade_suspeita", "alerta_unidade", "escala_ambigua",
                       "unidade_por_desempate", "unidade_cega",
                       "unidade_contradita_pela_parede"):
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

    # 📏 27/09 (estudo, item 5): o que está em layer CONGELADO ou DESLIGADO e
    # mesmo assim entra na medição (no R17, ~270 peças em bases congeladas).
    # Só registro: se vale tirar, decide-se com este número na mão.
    if _layers_desligados:
        try:
            _em_desl = {
                "m": round(float(sum(w.length for w in walls
                                     if (w.layer or "").upper() in _layers_desligados)), 1),
                "m2": round(float(sum(h.area for h in list(hatches) + list(polygon_areas)
                                      if (h.layer or "").upper() in _layers_desligados)), 1),
                "blocos": _blocos_desligados,
            }
            if any(_em_desl.values()):
                metadata["em_layer_desligado"] = _em_desl
        except Exception:
            pass

    # 📄 LEITURA POR FOLHA (24/09/2026, Pedro: "vamos ensinar ele a fazer
    # isso"). O esquema/detalhe sai da medição; a planta-tipo vale por N
    # andares. Ver `mapa_de_folhas`. Chave: LEITURA_POR_FOLHA=0 desliga sem
    # deploy. Qualquer falha aqui deixa a medição como estava.
    # 🩸 05/10 (E07): layer cujo metro é FAIXA de linhas paralelas (preenchimento).
    # Antes da folha: o relato do eixo, reescrito lá, não chama a faixa de eixo.
    _faixas = {}
    try:
        _faixas = layers_em_faixa_de_paralelas(msp, walls, unit_factor)
        if _faixas:
            metadata["layers_em_faixa"] = _faixas
    except Exception as _efx:
        logger.warning("[faixa-de-paralelas] falhou (não-fatal): %s", _efx)
    _folhas = {}
    _parede_espessa = None
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
            # 🩸 04/10 (E12): "corte e detalhe já fora" só se a folha rodou e
            # reconheceu corte ou detalhe; o layer com parede grossa pelas duas
            # faces não é "JÁ pelo EIXO".
            _parede_espessa = parede_espessa_na_soma(walls, _faces_espessas)
            _corte_fora = bool(_folhas.get("aplicada")) and any(
                f.get("tipo") in ("vista", "fora") for f in _mapa.get("folhas", []))
            for _chave_eixo in ("duto_linha_dupla", "parede_linha_dupla"):
                if metadata.get(_chave_eixo):
                    metadata[_chave_eixo] = _relato_do_eixo_na_soma(
                        metadata[_chave_eixo], walls, espessas=_parede_espessa,
                        corte_fora=_corte_fora, faixas=_faixas)
        except Exception as _efl:
            logger.warning("[leitura-por-folha] falhou (não-fatal): %s", _efl)
            _folhas = {"aplicada": False, "motivo": "erro: %s" % str(_efl)[:120]}
    # (E07) sem a folha, o relato fica cru ("de face -> de eixo"): o da faixa sai
    # aqui; o trecho já reescrito não casa o formato cru e fica como está
    if _faixas:
        for _chave_eixo in ("duto_linha_dupla", "parede_linha_dupla"):
            if metadata.get(_chave_eixo):
                metadata[_chave_eixo] = _relato_do_eixo_na_soma(
                    metadata[_chave_eixo], walls, faixas=_faixas, so_faixas=True)
    # 🩸 04/10 (E12): a parede de mais de 40 cm somada pelas duas faces — ressalva
    # do layer (fora da chave do selo e do resgate; ⚠ no prompt)
    if _parede_espessa is None:
        _parede_espessa = parede_espessa_na_soma(walls, _faces_espessas)
    if _parede_espessa:
        metadata["parede_espessa_pelas_faces"] = _parede_espessa
        logger.warning("[parede-espessa] %s: %s", os.path.basename(filepath), _parede_espessa)

    # 🩸 28/09 (caso 18c57c3c): vistas temáticas do MESMO pavimento, cada uma com
    # a base inserida de novo — a peça que aparece em várias vistas conta 1× (ver
    # `vistas_da_mesma_base`). Chave: VISTAS_DA_MESMA_BASE=0 desliga sem deploy.
    if os.environ.get("VISTAS_DA_MESMA_BASE", "1") != "0":
        try:
            _vis = vistas_da_mesma_base(doc, blocks)
            if _vis:
                metadata["vistas_da_mesma_base"] = _vis
        except Exception as _evb:
            logger.warning("[vistas-da-mesma-base] falhou (não-fatal): %s", _evb)

    # 📏 28/09 (estudo, D1): a planta repetida no modelo — SÓ registro, sobre
    # o que a leitura por folha deixou (é o que vai pro cliente)
    try:
        _cop = copias_em_sombra(blocks, unit_factor)
        if _cop:
            # 🩸 29/09: os tipos que moram nos vetores PROVADOS (a 2ª passada —
            # ver `tipos_nas_copias`); é esta lista que o rebaixamento usa
            _tc = dict(_cop.get("nomes") or {})
            for _n, _k in tipos_nas_copias(blocks, _cop.get("vetores"), unit_factor).items():
                _tc[_n] = max(_tc.get(_n, 0), _k)
            _cop["tipos_copiados"] = _tc
            metadata["copias_sombra"] = _cop
            # 🩸 29/09 (Pedro): da sombra para o REBAIXAMENTO — só selo, nenhum
            # número muda. m/m²/m³ por esta ressalva; contagem, por tipo, em
            # `engine_rules.selo_apos_planta_repetida`. 🪤 Fica FORA da lista que
            # a prova por rótulo apaga: o rótulo prova a escala, não que a
            # planta é uma só.
            from engine_rules import ressalva_da_planta_repetida as _ress_rep
            _rep = _ress_rep(_cop)
            if _rep:
                metadata["planta_repetida"] = _rep
    except Exception as _ecs:
        logger.warning("[copias-sombra] falhou (não-fatal): %s", _ecs)

    # 26/09: quantas das posições que FICARAM são o símbolo da legenda
    if _amostra_pos:
        for b in blocks:
            _livres = Counter(_amostra_pos.get(b.name, ()))
            for p in b.positions:
                if _livres[p] > 0:
                    _livres[p] -= 1
                    b.amostras_legenda += 1
        _am_bl = {b.name: b.amostras_legenda for b in blocks if b.amostras_legenda}
        if _am_bl:
            # nome ≠ 'amostras_legenda' (as HACHURAS da legenda, 24/09)
            metadata["blocos_da_legenda"] = _am_bl

    # 🩸 30/09 (job 9a2c5d87): o layer que é só COTA explodida e a peça
    # desenhada uma a uma, sem bloco — a IA vê a contagem, e o comprimento
    # desses layers não prova quantidade (a chave do selo não usa).
    try:
        _msp_ob = doc.modelspace()
        _lc = layers_de_cota_explodida(_msp_ob)
        if _lc:
            metadata["layers_de_cota"] = _lc
        _obj = objetos_repetidos_sem_bloco(_msp_ob, unit_factor)
        if _obj:
            metadata["objetos_sem_bloco"] = _obj
            _wbl: dict = {}
            for _w in walls:
                _wbl[_w.layer] = _wbl.get(_w.layer, 0.0) + _w.length * getattr(_w, "peso", 1.0)
            _lb = layers_de_borda_de_objeto(_obj, _wbl)
            if _lb:
                metadata["layers_de_borda"] = _lb
    except Exception as _eob:
        logger.warning("[objetos-sem-bloco] falhou (não-fatal): %s", _eob)
    # 🩸 30/09 (H34): tubo desenhado pelas duas paredes (Revit P-PIPE)
    try:
        _tfd = tubos_em_face_dupla(walls, texts, unit_factor)
        if _tfd:
            metadata["tubos_em_face_dupla"] = _tfd
    except Exception as _etfd:
        logger.warning("[tubo-face-dupla] falhou (não-fatal): %s", _etfd)
    # 🩸 01/10 (H79): metro de layer que é lado de moldura / limite de obra
    try:
        _mol = layers_de_moldura_ou_limite(msp, walls, unit_factor)
        if _mol:
            metadata["layers_moldura_ou_limite"] = _mol
    except Exception as _emol:
        logger.warning("[moldura-ou-limite] falhou (não-fatal): %s", _emol)
    # 🩸 02/10 (H88): metro de layer de esteira que é rolete/travessa lado a lado
    try:
        _est = layers_esteira_por_travessa(msp, walls, unit_factor)
        if _est:
            metadata["layers_esteira_por_travessa"] = _est
    except Exception as _eest:
        logger.warning("[esteira-por-travessa] falhou (não-fatal): %s", _eest)
    # 🩸 04/10 (E14): metro de layer que é a grade de uma tabela desenhada
    try:
        _tab = layers_grade_de_tabela(msp, walls, texts, unit_factor)
        if _tab:
            metadata["layers_grade_de_tabela"] = _tab
    except Exception as _etab:
        logger.warning("[grade-de-tabela] falhou (não-fatal): %s", _etab)
    # 🩸 01/10 (H76): metro de layer de CONEXÃO que é o contorno das peças
    try:
        _ctp = layers_de_contorno_de_peca(walls, _metro_de_bloco)
        if _ctp:
            metadata["layers_contorno_de_peca"] = _ctp
    except Exception as _ectp:
        logger.warning("[contorno-de-peca] falhou (não-fatal): %s", _ectp)
    # 🩸 01/10 (H75): o eletroduto do Revit também vem pelas duas paredes, sem ø
    try:
        _efd = eletrodutos_em_face_dupla(walls, unit_factor)
        if _efd:
            # o que a régua do TUBO (com ø rotulado) já decidiu vence
            metadata["tubos_em_face_dupla"] = {**_efd,
                                               **(metadata.get("tubos_em_face_dupla") or {})}
    except Exception as _eefd:
        logger.warning("[eletroduto-face-dupla] falhou (não-fatal): %s", _eefd)

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

def escala_provada_pela_prancha(metadata) -> Optional[float]:
    """O fator (p/ metros) que ESTA prancha provou por cota, ou None.

    É a mesma régua do `probe_unit` (cota validou ou corrigiu), lida do que a
    extração já gravou — serve de consenso TARDIO pras pranchas seguintes.
    🩸 01/10/2026 — job e3b8ddce: o pré-passe pula prancha > 60 MB, e a única
    que provava a escala era a de arquitetura (163 MB, emagrecida pra 21 MB e
    validada por 1.062 cotas DENTRO do laço). O elétrico, lido logo depois,
    não soube e saiu 10× menor (decímetro por plausibilidade).
    """
    try:
        md = metadata or {}
        if md.get("regua_cotas_status") not in ("validada", "corrigida"):
            return None
        f = float(md.get("fator_para_metros") or 0)
        return f if f > 0 else None
    except (TypeError, ValueError, AttributeError):
        return None


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


_PLAUS_TEXTO_MIN = 30              # textos no modelo pra julgar pela altura
_PLAUS_TEXTO_IMPOSSIVEL_M = 0.001  # texto mediano < 1 mm de verdade = impossível
_PLAUS_TEXTO_OK = (0.05, 1.0)      # texto do modelo em 1:25–1:200: 5 cm a 1 m
_FATORES_IMPERIAIS = {0.0254: "polegadas", 0.3048: "pés"}


def _unidade_pela_altura_do_texto(doc, unit_factor: float) -> dict:
    """Reforço da plausibilidade: a altura MEDIANA do texto do modelo é possível?

    🩸 29/09/2026 (caso 18c57c3c): prancha elétrica de um centro de distribuição
    desenhada em METRO declarando milímetro, sem cota. O núcleo em mm dava
    0,99 × 0,11 m — a régua do núcleo exige os DOIS lados < 0,5 m e deixou
    passar; e em metro o núcleo (4 vistas lado a lado) tem 991 m, acima dos
    200 m da faixa. Todo comprimento saiu 1000× menor ("eletroduto 15 m").
    O texto não mente: 0,135 unidade — em mm, letra de 0,14 mm.
    📏 Acervo local (57 DXF): só 3 disparam, os três declarando mm com texto de
    0,1–0,25 — este, o dd52081b (934 cotas PROVARAM metro) e o elétrico do
    73c6f0ed (a plausibilidade do núcleo corrigiu pra metro). Os murais do
    32a2 (mm com texto de 2 mm, escala de papel) não disparam.
    🔑 Corrige só com as três: ≥ `_PLAUS_TEXTO_MIN` textos, texto mediano abaixo
    de 1 mm na unidade declarada E exatamente UMA unidade que põe o texto entre
    5 cm e 1 m. Como a do núcleo, NÃO é prova: entra como ressalva.
    """
    hs = []
    for e in doc.modelspace().query("TEXT MTEXT"):
        try:
            h = float(e.dxf.get("height", 0) if e.dxftype() == "TEXT"
                      else e.dxf.get("char_height", 0))
        except (TypeError, ValueError):
            continue
        if h > 0:
            hs.append(h)
    if len(hs) < _PLAUS_TEXTO_MIN:
        return {"status": None, "motivo": f"só {len(hs)} textos no modelo"}
    hs.sort()
    med = hs[len(hs) // 2]
    # 🩸 01/10/2026 — H56 do estudo do acervo (liberado pelo Pedro): POLEGADA sem
    # cota que prove. Em 120 dias, 5 pranchas declararam polegada — erradas nas
    # DUAS direções: um ar-condicionado desenhado em mm saiu 25× MAIOR (duto de
    # 22.332 m, real ~879 m — a avaliação NOTA 1 de 01/09), uma estrutura em
    # metro saiu 39× MENOR. A letra entrega: 4 m em polegada (16 cm em mm); 2,5 mm
    # em polegada (10 cm em metro). Só pra unidade IMPERIAL declarada: em metro,
    # uma implantação 1:2000 tem letra de ~5 m de verdade e não pode "virar" cm.
    # Mesmas travas da régua de baixo: ≥ 30 textos e EXATAMENTE uma unidade
    # métrica que põe a letra entre 5 cm e 1 m; NÃO é prova, entra como ressalva.
    lo, hi = _PLAUS_TEXTO_OK
    _imp = next((n for f, n in _FATORES_IMPERIAIS.items() if abs(unit_factor - f) < 1e-9), "")
    if _imp:
        if lo <= med * unit_factor <= hi:
            return {"status": None, "motivo": f"texto mediano {med * unit_factor * 100:.1f} cm em {_imp} é possível"}
        cands = [f for f in _CANONICAL_METRIC_FACTORS if lo <= med * f <= hi]
        if len(cands) != 1:
            return {"status": None, "motivo": f"texto mediano {med:g} un em {_imp}: sem unidade métrica única ({len(cands)})"}
        fator = cands[0]
        return {
            "status": "corrigida_plausibilidade",
            "fator_corrigido": fator,
            "mensagem": (
                f"unidade corrigida por PLAUSIBILIDADE (altura do texto): o arquivo "
                f"declara {_imp} e nenhuma cota confirma; em {_imp} o texto do desenho "
                f"teria {med * unit_factor * 100:.2f} cm (impossível); em "
                f"{_UNIT_FACTOR_NAMES.get(fator, fator)}, {med * fator * 100:.1f} cm. "
                f"NÃO é prova — quantidades entram como estimado, confira a escala do "
                f"seu arquivo."),
        }
    if med * unit_factor >= _PLAUS_TEXTO_IMPOSSIVEL_M:
        return {"status": None, "motivo": f"texto mediano {med * unit_factor * 1000:.1f} mm é possível"}
    cands = [f for f in _CANONICAL_METRIC_FACTORS if f > unit_factor and lo <= med * f <= hi]
    if len(cands) != 1:
        return {"status": None, "motivo": f"texto mediano {med:g} un sem unidade única ({len(cands)})"}
    fator = cands[0]
    return {
        "status": "corrigida_plausibilidade",
        "fator_corrigido": fator,
        "mensagem": (
            f"unidade corrigida por PLAUSIBILIDADE (altura do texto): com "
            f"{_UNIT_FACTOR_NAMES.get(unit_factor, unit_factor)} o texto do desenho "
            f"teria {med * unit_factor * 1000:.2f} mm (impossível); em "
            f"{_UNIT_FACTOR_NAMES.get(fator, fator)}, {med * fator * 100:.1f} cm. "
            f"NÃO é prova — quantidades entram como estimado, confira a escala do "
            f"seu arquivo."),
    }


def _unidade_por_plausibilidade(doc, unit_factor: float, cotas=None) -> dict:
    """Última régua: o desenho, na unidade declarada, é fisicamente possível?

    Devolve {'status': 'corrigida_plausibilidade', 'fator_corrigido', 'mensagem'}
    ou {'status': None, 'motivo'}. Nunca lança.
    🩸 29/09: quando o NÚCLEO não decide, a altura do texto decide (ver
    `_unidade_pela_altura_do_texto`).
    `cotas`: o que a régua das cotas devolveu (`_validate_unit_by_dimensions`),
    pra régua das cotas automáticas no imperial (H74).
    """
    r = _unidade_pelo_nucleo(doc, unit_factor)
    if r.get("status"):
        return r
    try:
        u = _unidade_pela_coordenada_utm(doc, unit_factor)
    except Exception as e:
        u = {"status": None, "motivo": f"utm falhou: {type(e).__name__}"}
    if u.get("status"):
        return u
    try:
        c = _unidade_pelas_cotas_automaticas(cotas, unit_factor)
    except Exception as e:
        c = {"status": None, "motivo": f"cotas automáticas falharam: {type(e).__name__}"}
    if c.get("status"):
        return c
    try:
        t = _unidade_pela_altura_do_texto(doc, unit_factor)
    except Exception as e:
        t = {"status": None, "motivo": f"texto falhou: {type(e).__name__}"}
    if t.get("status"):
        return t
    return {"status": None,
            "motivo": f"{r.get('motivo', '')} | {u.get('motivo', '')} | "
                      f"{c.get('motivo', '')} | {t.get('motivo', '')}"}


_COTAS_AUTO_MIN = 30                  # cotas que qualificaram o fator
_COTAS_AUTO_MEDIANA_M = (0.5, 15.0)   # vão, porta, pé-direito — não furação de 40 cm


def _unidade_pelas_cotas_automaticas(cotas, unit_factor: float) -> dict:
    """Unidade IMPERIAL que as cotas automáticas desmentem: o único fator métrico
    que elas qualificam vira plausibilidade (estimado).

    🩸 01/10/2026 — H74 do estudo do acervo. Um refeitório declara POLEGADA, sem
    cota digitada, com 109 cotas automáticas medindo 0,8 / 0,9 / 1,8 / 2,0 —
    vãos e portas em METRO; lido em polegada, sairia 39× menor. A correção por
    cota exige número digitado (cota "<>" é circular: prova qualquer fator) —
    mas no imperial, que no Brasil já é suspeito, a MAGNITUDE das automáticas é
    plausibilidade, como o núcleo e a letra.
    🪤 Medido: fora do imperial o mesmo sinal ERRA 3 de 7 — folha de detalhe
    (furação, pontos) com mediana crua de 20–50 em cm qualifica METRO. Daí as
    travas: só imperial, ≥ `_COTAS_AUTO_MIN` cotas e mediana sob o fator em
    0,5–15 m (as erradas davam 25–48 m; as certas 1,0 e 2,5).
    """
    imp = next((n for f, n in _FATORES_IMPERIAIS.items() if abs(unit_factor - f) < 1e-9), "")
    if not imp:
        return {"status": None, "motivo": "cotas automáticas: unidade declarada não é imperial"}
    quals = list((cotas or {}).get("qualificados") or [])
    if len(quals) != 1:
        return {"status": None,
                "motivo": f"cotas automáticas: {len(quals)} fator(es) qualificaram, não decide"}
    q = quals[0]
    fator, n, med = float(q.get("fator") or 0), int(q.get("n") or 0), float(q.get("mediana_m") or 0)
    lo, hi = _COTAS_AUTO_MEDIANA_M
    if fator <= 0 or n < _COTAS_AUTO_MIN or not (lo <= med <= hi):
        return {"status": None,
                "motivo": f"cotas automáticas: {n} cotas, mediana {med:g} m — não decide"}
    return {
        "status": "corrigida_plausibilidade",
        "fator_corrigido": fator,
        "mensagem": (
            f"unidade corrigida por PLAUSIBILIDADE (cotas automáticas): o arquivo declara "
            f"{imp}, mas {n} cotas automáticas medem, em "
            f"{_UNIT_FACTOR_NAMES.get(fator, fator)}, mediana de {med:.2f} m (vãos e "
            f"portas). NÃO é prova — quantidades entram como estimado, confira a escala "
            f"do seu arquivo."),
    }


#: Faixa UTM do Brasil no hemisfério SUL (fusos 18–25, SIRGAS 2000): o leste
#: vai de ~166 a ~834 km e o norte de ~6.200 km (sul do RS) a 10.000 km (o
#: equador). O hemisfério norte (Roraima, Amapá) tem norte de 0 a ~600 km —
#: confunde com coordenada comum e fica de fora.
_UTM_BR_LESTE = (160_000.0, 840_000.0)
_UTM_BR_NORTE = (6_200_000.0, 10_000_000.0)


def _unidade_pela_coordenada_utm(doc, unit_factor: float) -> dict:
    """Unidade IMPERIAL num desenho georreferenciado em UTM: é metro.

    🩸 01/10/2026 — H63 do estudo do acervo, job b445916a (loteamento e
    pavimentação, 15/09): o cabeçalho declara PÉS, sem cota, e a letra cabe nas
    duas unidades (o H56 não decide, e certo). Mas o desenho está em
    coordenada UTM (leste ~245 mil, norte ~8,98 milhões) — e UTM é metro por
    definição: em pés, 8,98 milhões seriam 2.738 km. A entrega saiu 3,3×
    menor no comprimento e 10,8× na área ("terraplenagem 9.453 m²").
    🔑 Só com as três: unidade declarada imperial, ≥ `_PLAUS_MIN_PONTOS`
    pontos e o NÚCLEO (percentis 25–75, os dois eixos) inteiro dentro da
    faixa UTM do Brasil. Como as outras plausibilidades, NÃO é prova: entra
    como ressalva e nada sai 'confirmado'.
    """
    imp = next((n for f, n in _FATORES_IMPERIAIS.items() if abs(unit_factor - f) < 1e-9), "")
    if not imp:
        return {"status": None, "motivo": "utm: unidade declarada não é imperial"}
    xs: list = []
    ys: list = []
    for ent in doc.modelspace():
        if len(xs) >= 20000:
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
    if len(xs) < _PLAUS_MIN_PONTOS:
        return {"status": None, "motivo": f"utm: {len(xs)} pontos, pouco pra julgar"}
    xs.sort(); ys.sort()

    def _p(v, q):
        return v[min(len(v) - 1, int(len(v) * q))]
    x0, x1, y0, y1 = _p(xs, 0.25), _p(xs, 0.75), _p(ys, 0.25), _p(ys, 0.75)
    (le0, le1), (no0, no1) = _UTM_BR_LESTE, _UTM_BR_NORTE
    if not (le0 <= x0 and x1 <= le1 and no0 <= y0 and y1 <= no1):
        return {"status": None, "motivo": "utm: o núcleo não está na faixa UTM do Brasil"}
    xm = f"{_p(xs, 0.5):,.0f}".replace(",", ".")
    ym = f"{_p(ys, 0.5):,.0f}".replace(",", ".")
    return {
        "status": "corrigida_plausibilidade",
        "fator_corrigido": 1.0,
        "mensagem": (
            f"unidade corrigida por PLAUSIBILIDADE (coordenada UTM): o arquivo declara "
            f"{imp}, mas o desenho está em coordenada UTM (leste ~{xm}, norte ~{ym}), "
            f"que é sempre em metros. NÃO é prova — quantidades entram como estimado, "
            f"confira a escala do seu arquivo."),
    }


def _unidade_pelo_nucleo(doc, unit_factor: float) -> dict:
    """A régua do NÚCLEO denso (17/08/2026, caso cliente-81) — ver `_unidade_por_plausibilidade`."""
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
