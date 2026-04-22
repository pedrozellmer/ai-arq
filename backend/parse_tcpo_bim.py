# -*- coding: utf-8 -*-
"""Parser do PDF TCPO BIM 15ª Edição Completo (1028 páginas, 8.500+ composições).

CRÍTICO: o PDF tem LAYOUT DE 2 COLUNAS (composições lado a lado).
`pdfplumber.extract_text()` mistura as duas colunas. Este parser usa
bounding boxes (`extract_words`) pra separar esquerda/direita antes de
processar.

Estrutura de cada composição:
    [Título do serviço] - [unidade]
    Consumos
    Código           Descrição            Unid.   Consumo (ou múltiplas variantes)
    2N 3616 25...    Eletricista          h       0,14
    2C 1413 09...    Curva 90º ø 1/2"     un      1,00
    Conteúdo do serviço: texto...
    Critério de medição: texto...
    Normas técnicas: NBR XXXX...
    Observações: [opcional]

Uso:
    python parse_tcpo_bim.py <pdf> [--dry-run] [--start-page N] [--end-page N]
        [--sample-output FILE] [--batch N]
"""
import os
import re
import sys
import json
import argparse
import urllib.request
from typing import List, Dict, Tuple, Optional
from collections import defaultdict

import pdfplumber


SUPABASE_URL = os.getenv("SUPABASE_URL", "https://kqjabzwgbfuivzlcfvvu.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY") or (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtxamFiendnYmZ1aXZ6bGNmdnZ1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzYwMDg5NzcsImV4cCI6MjA5MTU4NDk3N30.48xSenZlDV0LfD94ZxwGvX41Kf9Je2n-ouZpJrrCSKI"
)


# ═══════════════════════════════════════════════════════════════
#  Regex e padrões
# ═══════════════════════════════════════════════════════════════

# Código TCPO BIM: "3R 2312 00 00 00 00 01 07" ou "2N 3616 25 12 21"
RE_CODIGO_BIM = re.compile(r'\b(\d[A-Z])\s?(\d{2,4}(?:\s\d{2}){0,7})\b')

# Título com unidade ao final: "Curva 90º ... - un" ou "Alvenaria ... - m²"
# Também aceita "•" / "·" como separador (TCPO usa às vezes).
RE_TITULO_UNIDADE = re.compile(
    r'^(.+?)\s*[-–•·.]\s*(un|m|m2|m²|m3|m³|ml|h|h prod|h imp|kg|t|cj|vb|%|mês|mes|dia|l)\s*$',
    re.IGNORECASE
)

# Número com vírgula ou ponto
RE_NUMERO = re.compile(r'(\d+[.,]\d+)')

# Unidades válidas (pra detectar fim de descrição)
UNIDADES_VALIDAS = {'h', 'hprod', 'himp', 'h prod', 'h imp',
                    'kg', 'kW', 'kw', 'm', 'm2', 'm²', 'm3', 'm³',
                    'ml', 'un', 't', 'l', 'cj', 'vb', '%', 'mês', 'mes',
                    'prod', 'imp', 'dia'}

SISTEMAS = {
    'sistemas elétricos': 'Sistemas Elétricos',
    'sistemas hidráulicos': 'Sistemas Hidráulicos',
    'pisos': 'Pisos',
    'cobertura': 'Cobertura',
    'superestrutura': 'Superestrutura',
    'impermeabilização': 'Impermeabilização',
    'urbanização': 'Urbanização',
    'equipamentos': 'Equipamentos',
    'serviços iniciais': 'Serviços Iniciais',
    'infraestrutura': 'Infraestrutura',
    'revestimentos': 'Revestimentos',
    'pinturas': 'Pinturas',
    'esquadrias': 'Esquadrias',
    'divisórias': 'Divisórias',
    'forros': 'Forros',
    'isolamento': 'Isolamento',
    'ar-condicionado': 'Ar-Condicionado',
    'prevenção contra incêndio': 'PPCI',
    'obras complementares': 'Complementares',
    'serviços complementares': 'Complementares',
    'vedações': 'Vedações',
    'comunicação visual': 'Comunicação Visual',
}


def normalize_codigo(codigo_bim: str) -> str:
    return re.sub(r'\s+', '', codigo_bim or '')


def normalize_unit(u: str) -> str:
    u = u.strip().lower().replace('  ', ' ')
    mapa = {'m2': 'm²', 'm3': 'm³', 'mes': 'mês'}
    return mapa.get(u, u)


def detect_sistema(text: str) -> str:
    """Detecta sistema pelo cabeçalho da página (primeiras 200 chars)."""
    lower = text.lower()[:300]
    for key, label in SISTEMAS.items():
        if key in lower:
            return label
    return ""


def is_page_to_skip(text: str) -> bool:
    if not text or len(text) < 300:
        return True
    lower = text.lower()
    if any(m in lower[:600] for m in ('sumário', 'apresentação do tcpo',
                                        'bdi - benefícios', 'índice remissivo',
                                        'palavra do presidente')):
        return True
    if not RE_CODIGO_BIM.search(text):
        return True
    return False


# ═══════════════════════════════════════════════════════════════
#  Extração por COLUNA (bounding box)
# ═══════════════════════════════════════════════════════════════

def split_page_into_columns(page) -> Tuple[str, str]:
    """Divide uma página em 2 colunas baseado nas coordenadas X das palavras.

    Retorna (texto_esquerda, texto_direita). Agrupa palavras por linha
    (mesma Y) e ordena por X. Separa em 2 colunas usando o meio da página
    como divisor.

    IMPORTANTE: descarta footer (número de página) e header (nome do
    capítulo) pra não poluir o conteúdo das composições.
    """
    width = page.width or 595  # default A4
    height = page.height or 842
    x_divider = width / 2

    # Zona de header (topo) e footer (fundo) a descartar — 4% acima/abaixo
    y_header = height * 0.04
    y_footer = height * 0.96

    words = page.extract_words(
        x_tolerance=2, y_tolerance=3, keep_blank_chars=False,
        use_text_flow=False, extra_attrs=[]
    ) or []

    # Separa palavras em esquerda/direita pela coordenada X do centro da palavra
    left_words = []
    right_words = []
    for w in words:
        # Descarta header e footer pra não poluir
        y_center = (w['top'] + w['bottom']) / 2
        if y_center < y_header or y_center > y_footer:
            continue
        x_center = (w['x0'] + w['x1']) / 2
        if x_center < x_divider:
            left_words.append(w)
        else:
            right_words.append(w)

    def words_to_lines(wlist, line_tolerance=3):
        """Agrupa palavras em linhas pelo top (Y) e concatena ordenado por X."""
        if not wlist:
            return ""
        # Agrupa por Y
        lines_map = defaultdict(list)
        for w in wlist:
            # Arredonda Y pra próximos N pixels (linha aproximada)
            y_bucket = round(w['top'] / line_tolerance) * line_tolerance
            lines_map[y_bucket].append(w)
        # Ordena linhas por Y asc, palavras por X asc
        lines_sorted = sorted(lines_map.items(), key=lambda x: x[0])
        out = []
        for y, ws in lines_sorted:
            ws_sorted = sorted(ws, key=lambda w: w['x0'])
            line_text = ' '.join(w['text'] for w in ws_sorted)
            out.append(line_text)
        return '\n'.join(out)

    return words_to_lines(left_words), words_to_lines(right_words)


# ═══════════════════════════════════════════════════════════════
#  Parser por coluna de texto
# ═══════════════════════════════════════════════════════════════

def parse_column_text(col_text: str, page_num: int, sistema: str) -> List[Dict]:
    """Parseia o texto de UMA coluna (já separada).

    Blocos típicos:
        [Título - unidade]
        Consumos
        [tabela header]
        [rows de insumos]
        [linhas de metadados: Conteúdo/Critério/Normas/Observações]
        [próxima composição...]
    """
    if not col_text.strip():
        return []

    lines = [l.strip() for l in col_text.split('\n') if l.strip()]
    composicoes = []

    # Estado da máquina: procurando título → capturando tabela → capturando metadados
    i = 0
    while i < len(lines):
        line = lines[i]

        # Procura linha "Consumos" (marcador de início). Tolera variações de
        # OCR tipo "Constmos", "Consurnos", "Consumo" etc.
        is_consumos_marker = (
            line == 'Consumos' or
            (line.startswith('Consumos') and len(line) < 20) or
            (len(line) < 15 and line[:4].lower() in ('cons', 'cost') and
             line.lower().endswith(('mos', 'nos', 'rnos')))
        )
        if is_consumos_marker:
            # Captura título olhando pra trás. Título em TCPO BIM tem
            # 1-4 linhas. Regra: andar de trás pra frente a partir de i-1,
            # agregando linhas enquanto parecerem título, parar quando
            # encontrar algo que NÃO é título (ponto final, começo de
            # parágrafo, metadado, código BIM, etc).
            title_lines_rev = []
            def _looks_like_title_line(s: str) -> bool:
                if not s:
                    return False
                # Metadado — definitivamente não
                if any(s.startswith(p) for p in ('Conteúdo', 'Critério',
                                                   'Normas', 'Observaç',
                                                   'Metodologia')):
                    return False
                # Linha de insumo — começa com código BIM
                if RE_CODIGO_BIM.match(s):
                    return False
                # Cabeçalho de seção (tudo maiúsculo e longo)
                if s.isupper() and len(s) > 10:
                    return False
                # Subheader de seção/subseção começando com "■" + texto curto
                # (ex: "■ Caixas de passagem em aço", "■ Sistemas Elétricos")
                if s.startswith('■') or s.startswith('●'):
                    return False
                return True

            # Linha imediatamente acima de Consumos é o fim do título (em geral
            # termina em "- unidade"). Captura dela pra trás.
            found_unit_marker = False
            for j in range(i - 1, max(-1, i - 6), -1):
                s = lines[j]
                if not _looks_like_title_line(s):
                    break
                # Se a linha termina com ponto final (fim de frase), é
                # observação/conteúdo da composição anterior, não título.
                # Porém a linha "cauda" do título pode ter unidade após hífen,
                # ex: "... -m²" ou "... - un" — não é fim de frase.
                if title_lines_rev and s.rstrip().endswith('.'):
                    break
                # Se o título já foi concluído (achamos "- unidade"), só pegamos
                # mais linhas se elas são curtas (< 80) e não parecem parágrafo.
                if found_unit_marker and (len(s) > 80 or s[0:1].islower()):
                    break
                # Marca se essa linha tem o padrão "título - unidade"
                if RE_TITULO_UNIDADE.match(s):
                    found_unit_marker = True
                title_lines_rev.append(s)
                # Limite de 4 linhas
                if len(title_lines_rev) >= 4:
                    break

            title_candidates = list(reversed(title_lines_rev))

            # Captura tabela de insumos (linhas que começam com código BIM)
            rows = []
            header_codigos = []  # códigos BIM encontrados no header da tabela
            j = i + 1
            # Pula header da tabela — "Código Descrição Unid. 3R 27 21 3R 27 21"
            # O header contém o código BIM da composição (repetido 1-3x, um por
            # variante). Capturamos ele pra usar como codigo_bim da composição.
            while j < len(lines):
                nxt = lines[j]
                # Header da tabela
                if 'Código' in nxt and 'Descrição' in nxt:
                    # Extrai códigos BIM do header (geralmente 1-3 repetições)
                    for m_h in RE_CODIGO_BIM.finditer(nxt):
                        header_codigos.append(m_h.group(0).strip())
                    j += 1
                    # Linha de sufixos "00 00 00 00" e "32 20 32 24" (variantes
                    # do código BIM) — pula 1-3 linhas de sufixos numéricos puros
                    while j < len(lines):
                        suffix_line = lines[j]
                        # Linha só de dígitos/espaços = continuação de sufixo de código
                        if re.fullmatch(r'[\d\s]+', suffix_line):
                            j += 1
                            continue
                        break
                    continue
                # Label "Com tampa Sem tampa" ou similar (título das colunas de variante)
                if not rows and not RE_CODIGO_BIM.match(nxt) and len(nxt) < 60:
                    # Pula se parece rótulo de variante (tudo letras + poucas palavras)
                    if re.fullmatch(r'[A-ZÀ-Úa-zà-ú\s/\-]+', nxt) and len(nxt.split()) <= 6:
                        j += 1
                        continue
                # Linha começa com código BIM? é row de insumo
                if RE_CODIGO_BIM.match(nxt):
                    rows.append(nxt)
                    j += 1
                    continue
                # Linha de metadado? termina a tabela
                if any(nxt.startswith(p) for p in ('Conteúdo do', 'Critério de',
                                                     'Normas', 'Observaç', 'Metodologia')):
                    break
                # Pode ser continuação de row anterior (quebra de linha)
                if rows and not RE_TITULO_UNIDADE.match(nxt) and 'Consumos' not in nxt:
                    rows[-1] += ' ' + nxt
                    j += 1
                    continue
                # Nova composição começando?
                if RE_TITULO_UNIDADE.match(nxt):
                    break
                j += 1

            # Captura metadados
            meta_raw = []
            while j < len(lines):
                nxt = lines[j]
                if any(nxt.startswith(p) for p in ('Conteúdo do', 'Critério de',
                                                     'Normas', 'Observaç', 'Metodologia')):
                    meta_raw.append(nxt)
                    j += 1
                    continue
                # Continuação de metadado anterior
                if meta_raw and not RE_TITULO_UNIDADE.match(nxt) and 'Consumos' not in nxt:
                    if not RE_CODIGO_BIM.match(nxt):
                        meta_raw[-1] += ' ' + nxt
                        j += 1
                        continue
                # Próxima composição ou outra coisa
                break

            # Monta composição
            if title_candidates or rows:
                comp = _finalize(title_candidates, rows, meta_raw, sistema,
                                 page_num, header_codigos)
                if comp:
                    composicoes.append(comp)

            i = j
            continue

        i += 1

    return composicoes


def _finalize(title_candidates: List[str], rows_raw: List[str],
              meta_raw: List[str], sistema: str, pagina: int,
              header_codigos: Optional[List[str]] = None) -> Optional[Dict]:
    """Monta a composição final a partir dos blocos capturados."""
    header_codigos = header_codigos or []

    # Descobre título + unidade.
    # Estratégia: a ÚLTIMA linha dos candidatos em geral tem "- unidade" no fim.
    # Ela é a cauda do título; as linhas anteriores compõem o começo.
    # Juntamos todas (na ordem) antes de separar a unidade final.
    titulo = None
    unidade = None
    title_raw = None

    if title_candidates:
        # Junta todas as linhas em um único título multi-linha
        joined = ' '.join(title_candidates).strip()
        joined = re.sub(r'\s+', ' ', joined)
        title_raw = joined

        m = RE_TITULO_UNIDADE.match(joined)
        if m:
            titulo = m.group(1).strip()
            unidade = normalize_unit(m.group(2))
        else:
            titulo = joined
            unidade = 'un'

    if not titulo or len(titulo) < 5:
        return None

    # Código BIM da composição. Prioridade:
    #   1) header da tabela ("Código Descrição Unid. 3R 27 21 3R 27 21")
    #   2) primeira row dos rows (se for linha de código puro)
    #   3) título (raríssimo mas pode aparecer)
    codigo_bim = None

    # Prioridade 1: header_codigos
    if header_codigos:
        # Usa o primeiro código do header (se há 2-3, são variantes do mesmo)
        codigo_bim = header_codigos[0]

    # Prioridade 2: primeira row sem descrição real
    if not codigo_bim and rows_raw:
        m = RE_CODIGO_BIM.search(rows_raw[0])
        if m:
            first_row = rows_raw[0].strip()
            remainder = first_row[m.end():].strip()
            remainder_alpha = re.sub(r'[\d\s\-\.\,]', '', remainder)
            if len(remainder_alpha) < 5:
                codigo_bim = m.group(0).strip()

    # Prioridade 3: título
    if not codigo_bim:
        search_area = ' '.join(title_candidates) + ' ' + (title_raw or titulo)
        m = RE_CODIGO_BIM.search(search_area)
        if m:
            codigo_bim = m.group(0).strip()

    if not codigo_bim:
        codigo_bim = f"LOCAL-{abs(hash(titulo)) % 999999:06d}"

    # Remove códigos BIM do título final pra deixar descrição limpa
    titulo_clean = RE_CODIGO_BIM.sub('', titulo).strip()

    # Remove bullets e caracteres decorativos do começo/fim
    titulo_clean = re.sub(r'^[■•·\s]+', '', titulo_clean)
    titulo_clean = re.sub(r'[■•·\s]+$', '', titulo_clean)

    # Remove header de capítulo/sistema que vazou no começo do título
    # (quando a coluna esquerda é muito estreita e invade a direita)
    for sys_key in SISTEMAS.keys():
        pattern = r'^' + re.escape(sys_key) + r'\s+'
        titulo_clean = re.sub(pattern, '', titulo_clean, flags=re.IGNORECASE)

    # Remove "m2"/"m3"/"cm" solto colado no meio do título (vazamento)
    titulo_clean = re.sub(
        r'\s+(m2|m3|m²|m³)\s+(?=[a-zà-úA-ZÀ-Ú])',
        ' ', titulo_clean
    )
    # Remove ".m2" ou "- m2" ou "• un" no final (inclui separadores decorativos)
    titulo_clean = re.sub(
        r'[\s\.,\-•·]+(m2|m3|m²|m³|un|m|ml|h|kg|t|cj|vb|l|dia)\s*$',
        '', titulo_clean, flags=re.IGNORECASE
    )
    # Remove "• un • com mão de obra empreitada" ou similar no fim
    titulo_clean = re.sub(
        r'\s*[\-–•·]\s*com\s+mão\s+de\s+obra.*$',
        '', titulo_clean, flags=re.IGNORECASE
    )

    titulo_clean = re.sub(r'\s+', ' ', titulo_clean).strip()

    if len(titulo_clean) < 8 or not any(c.isalpha() for c in titulo_clean):
        return None

    # Metadados: limpa prefixos duplicados ("Conteúdo do Considera..." →
    # "Considera...")
    def _clean_meta(m_text: str, prefix_keys: list, leak_words: list = None) -> str:
        text = m_text
        # Remove o rótulo ("Conteúdo do serviço:" ou "Conteúdo do")
        # procurando dois pontos; se não tiver, remove só o prefixo conhecido
        if ':' in text:
            _, _, val = text.partition(':')
            text = val.strip()
        # Remove palavras do prefixo no começo
        for pk in prefix_keys:
            pattern = r'^\s*' + re.escape(pk) + r'\s+'
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        # LEAK WORDS: "serviço" / "medição" / "técnicas" vazam NO MEIO do texto
        # porque o rótulo da próxima coluna ("Conteúdo do serviço" / "Critério
        # de medição") quebra em 2 linhas e a 2ª linha ("serviço" / "medição")
        # cola no final de uma linha do conteúdo anterior.
        # Ex: "para fabricação, montagem serviço (inclusive de contraventamentos)"
        # Removemos essas palavras quando aparecem isoladas (cercadas de espaço
        # ou pontuação) no meio do texto, pois não fazem sentido semântico.
        if leak_words:
            for w in leak_words:
                # Remove ocorrência isolada (não a 1ª palavra do texto)
                # Padrão: ",? WORD" onde WORD não é início nem fim natural
                text = re.sub(
                    r'(?<=[a-zà-ú,)\]])\s+(' + re.escape(w) + r')\b(?!\s*,)',
                    '', text, flags=re.IGNORECASE
                )
                # Também remove quando vem cercada por vírgulas ("X, serviço Y")
                text = re.sub(
                    r'\s+' + re.escape(w) + r'\s+',
                    ' ', text, flags=re.IGNORECASE
                )

        # Remove "serviço" / "medição" / "técnicas" duplicados no começo ou fim
        text = re.sub(r'^(serviço|medição|técnicas)\s+', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s+(medição|serviço|técnicas)\s*$', '', text, flags=re.IGNORECASE)
        # Remove duplicações tipo "serviço serviço"
        text = re.sub(r'\b(\w+)\s+\1\b', r'\1', text, flags=re.IGNORECASE)
        # Remove número de página no fim (3 dígitos isolados)
        text = re.sub(r'\s+\d{1,4}\s*$', '', text)
        # Limpa espaços duplicados
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    conteudo, criterio, normas, observacoes = '', '', '', ''
    for m in meta_raw:
        if m.startswith('Conteúdo'):
            # "serviço" vaza dentro de Conteúdo (porque o próximo bloco é
            # "Critério de medição" — mas "serviço" é do rótulo do próprio
            # bloco atual quando quebrado em 2 linhas)
            conteudo = _clean_meta(m, ['Conteúdo do serviço', 'Conteúdo do'],
                                   leak_words=['serviço'])
        elif m.startswith('Critério'):
            criterio = _clean_meta(m, ['Critério de medição', 'Critério de'],
                                   leak_words=['medição'])
        elif m.startswith('Normas'):
            normas = _clean_meta(m, ['Normas técnicas', 'Normas'],
                                 leak_words=['técnicas'])
        elif m.startswith('Observaç'):
            observacoes = _clean_meta(m, ['Observações'])

    # Insumos
    insumos = []
    for row in rows_raw:
        ins = _parse_insumo(row)
        if ins:
            insumos.append(ins)

    # Se não conseguimos nenhum insumo útil, descarta composição
    if not insumos:
        return None

    # Gera variante única a partir do título + página pra não colidir quando
    # múltiplas composições têm mesmo codigo_bim (ex: fabricação/montagem/
    # desmontagem da mesma Fôrma, ou variantes de diâmetro).
    import hashlib
    variante_seed = (titulo_clean[:60] + str(pagina)).lower().strip()
    variante = hashlib.md5(variante_seed.encode('utf-8')).hexdigest()[:10]

    return {
        'codigo_bim': codigo_bim[:80],
        'codigo_norm': normalize_codigo(codigo_bim)[:80],
        'descricao': titulo_clean[:500],
        'unidade': unidade or 'un',
        'sistema': sistema,
        'conteudo': conteudo[:2000],
        'criterio': criterio[:500],
        'normas': normas[:1500],
        'observacoes': observacoes[:2000],
        'pagina_pdf': pagina,
        'variante': variante,
        'insumos': insumos,
    }


def _parse_insumo(row: str) -> Optional[Dict]:
    """Parseia uma row de insumo: código + descrição + unidade + consumo.

    Ex: '2N 3616 25 12 21 Eletricista h 0,1400 0,1400'
    """
    m = RE_CODIGO_BIM.match(row.strip())
    if not m:
        return None

    codigo = m.group(0).strip()
    rest = row[m.end():].strip()

    # Pega primeiro valor numérico (primeira variante de consumo)
    nums = RE_NUMERO.findall(rest)
    if nums:
        try:
            consumo = float(nums[0].replace(',', '.'))
        except ValueError:
            consumo = None
    else:
        consumo = None

    # Remove números do final pra pegar só descrição + unidade
    rest_clean = RE_NUMERO.sub('', rest).strip()

    # Detecta unidade como última palavra antes dos números
    tokens = rest_clean.split()
    unidade = 'un'
    descricao_tokens = tokens

    # Procura de trás pra frente a última unidade válida
    for idx in range(len(tokens) - 1, -1, -1):
        tok_lower = tokens[idx].lower()
        if tok_lower in UNIDADES_VALIDAS:
            unidade = normalize_unit(tokens[idx])
            descricao_tokens = tokens[:idx]
            break

    descricao = ' '.join(descricao_tokens).strip()

    # Remove outros códigos BIM que vazaram na descrição
    descricao = RE_CODIGO_BIM.sub('', descricao).strip()

    # Remove blocos numéricos soltos de 2-4 dígitos cercados por espaços
    # (são fragmentos de códigos BIM tipo "14 00 00 00", "1615", "0011",
    # "17 05" que vazam da coluna de variantes). Aplicamos em loop até
    # não haver mais, pra pegar sequências consecutivas.
    # NÃO removemos números no início/fim quando fazem parte de código
    # de insumo (já extraímos isso acima).
    prev = None
    while prev != descricao:
        prev = descricao
        # Remove sequências de 2+ tokens numéricos seguidos (ex: "14 00 00")
        descricao = re.sub(r'\s+\d{2,4}(\s+\d{2,4}){1,}\s+', ' ', descricao)
        # Remove token numérico isolado no meio (2-4 dígitos entre palavras)
        descricao = re.sub(r'(?<=[a-zà-ú])\s+\d{2,4}\s+(?=[a-zà-ú])', ' ', descricao,
                           flags=re.IGNORECASE)
        # Remove "m2"/"m3"/"kg"/"h prod" colados no meio da descrição
        # (quando a unidade da linha de cima vaza)
        descricao = re.sub(
            r'\s+(m2|m3|m²|m³|kg|h prod|h imp|hprod|himp|ml)\s+(?=[a-zà-ú])',
            ' ', descricao, flags=re.IGNORECASE
        )

    # Remove números isolados no FIM da descrição (vazamento da coluna de consumo)
    descricao = re.sub(r'\s+\d{2,4}(\s+\d{2,4})*\s*$', '', descricao).strip()
    # Remove sequência de dígitos no INÍCIO (vazamento de código de variante)
    descricao = re.sub(r'^\d{2,4}(\s+\d{2,4})*\s+', '', descricao).strip()

    descricao = re.sub(r'\s+', ' ', descricao).strip()

    if not descricao or len(descricao) < 3:
        return None

    # FILTRO 1: descarta "insumos lixo" onde descrição é só número/hífen
    # (acontece quando o header da tabela foi mal parseado; são os
    # sufixos de código BIM tipo "05 51" / "05 52" / "-").
    desc_alpha = re.sub(r'[\d\s\-\.\,]', '', descricao)
    if len(desc_alpha) < 3:
        return None

    # FILTRO 2: descarta rows "vazadas" onde duas composições se misturaram.
    # Detecta presença de múltiplas referências a códigos BIM na descrição
    # original (antes de remover).
    codigos_extras = re.findall(r'\b(?:\d[A-Z]|[A-Z]\d)\s?\d{3,4}', row[m.end():])
    if len(codigos_extras) >= 2:
        # Múltiplos códigos BIM na mesma linha = linha vazada; descarta
        # pra não inserir descrição incorreta
        return None

    # Classifica tipo
    desc_lower = descricao.lower()
    if any(t in desc_lower for t in ('pedreiro', 'servente', 'ajudante', 'encanador',
                                       'eletricista', 'pintor', 'carpinteiro',
                                       'ferreiro', 'azulejista', 'ladrilhista',
                                       'operador', 'mestre', 'engenheiro', 'técnico',
                                       'soldador')):
        tipo = 'mao_de_obra'
    elif any(t in desc_lower for t in ('taxa de', 'equipamento', 'máquina',
                                         'betoneira', 'martelete', 'caminhão',
                                         'retro', 'pá-carregadeira', 'compressor',
                                         'andaime', 'vibrador', 'guindaste',
                                         'bomba', 'compactador')):
        tipo = 'equipamento'
    else:
        tipo = 'material'

    return {
        'codigo_insumo': codigo[:80],
        'descricao': descricao[:300],
        'unidade': unidade,
        'consumo': consumo,
        'tipo': tipo,
    }


# ═══════════════════════════════════════════════════════════════
#  Entry por página (integra 2 colunas)
# ═══════════════════════════════════════════════════════════════

def parse_page(page, page_num: int, sistema_from_page: str = "") -> List[Dict]:
    # Primeiro checa se vale pular
    full_text = page.extract_text() or ''
    if is_page_to_skip(full_text):
        return []

    sistema = detect_sistema(full_text) or sistema_from_page

    # Separa em 2 colunas
    left_text, right_text = split_page_into_columns(page)

    composicoes = []
    composicoes.extend(parse_column_text(left_text, page_num, sistema))
    composicoes.extend(parse_column_text(right_text, page_num, sistema))

    return composicoes


# ═══════════════════════════════════════════════════════════════
#  Inserção em lote no Supabase
# ═══════════════════════════════════════════════════════════════

def insert_batch_composicoes(rows: List[Dict]) -> Dict[Tuple[str, str], str]:
    if not rows:
        return {}
    payload = [{
        'codigo_bim': r['codigo_bim'],
        'codigo_norm': r['codigo_norm'],
        'descricao': r['descricao'],
        'unidade': r['unidade'],
        'sistema': r['sistema'],
        'conteudo': r['conteudo'],
        'criterio': r['criterio'],
        'normas': r['normas'],
        'observacoes': r['observacoes'],
        'pagina_pdf': r['pagina_pdf'],
        'variante': r.get('variante', ''),
    } for r in rows]

    url = f"{SUPABASE_URL}/rest/v1/tcpo_composicoes"
    body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=body, method='POST')
    req.add_header('apikey', SUPABASE_KEY)
    req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Prefer', 'return=representation,resolution=ignore-duplicates')

    try:
        resp = urllib.request.urlopen(req, timeout=60)
        inserted = json.loads(resp.read().decode('utf-8'))
        return {(r['codigo_norm'], r.get('variante', '')): r['id'] for r in inserted}
    except Exception as e:
        print(f"  [erro] insert composicoes: {e}")
        return {}


def insert_batch_insumos(insumos: List[Dict]) -> int:
    if not insumos:
        return 0
    url = f"{SUPABASE_URL}/rest/v1/tcpo_insumos"
    total = 0
    for i in range(0, len(insumos), 200):
        chunk = insumos[i:i+200]
        body = json.dumps(chunk).encode('utf-8')
        req = urllib.request.Request(url, data=body, method='POST')
        req.add_header('apikey', SUPABASE_KEY)
        req.add_header('Authorization', f'Bearer {SUPABASE_KEY}')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Prefer', 'return=minimal')
        try:
            urllib.request.urlopen(req, timeout=60)
            total += len(chunk)
        except Exception as e:
            print(f"  [erro] insert insumos chunk: {e}")
    return total


# ═══════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pdf', help='Path do PDF TCPO BIM')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--start-page', type=int, default=0)
    ap.add_argument('--end-page', type=int, default=0)
    ap.add_argument('--batch', type=int, default=50)
    ap.add_argument('--sample-output', type=str, default='')
    args = ap.parse_args()

    print(f"Abrindo: {args.pdf}")
    all_comp = []

    with pdfplumber.open(args.pdf) as pdf:
        total_pages = len(pdf.pages)
        start = args.start_page or 0
        end = args.end_page or total_pages
        print(f"Processando {start+1}..{end} de {total_pages}")

        last_sistema = ""
        seen_keys = set()  # (codigo_norm, primeira_descrição) pra deduplicar
        for i, page in enumerate(pdf.pages[start:end], start=start):
            try:
                composicoes = parse_page(page, i + 1, last_sistema)
            except Exception as e:
                print(f"  [warn] erro na página {i+1}: {e}")
                continue

            for c in composicoes:
                if c.get('sistema'):
                    last_sistema = c['sistema']
                else:
                    c['sistema'] = last_sistema

                # DEDUPE: mesma composição aparecendo em 2+ páginas seguidas
                # (comum quando descrevem fabricação/montagem/desmontagem como
                # 3 composições diferentes com o mesmo codigo_bim). Chave =
                # codigo_norm + primeiras 40 chars da descrição.
                dedup_key = (c['codigo_norm'],
                             c['descricao'][:40].lower().strip())
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)

                all_comp.append(c)

            if (i + 1) % 50 == 0:
                total_ins = sum(len(c.get('insumos', [])) for c in all_comp)
                print(f"  [{i+1}/{end}] composições={len(all_comp)} insumos={total_ins}")

    total_ins = sum(len(c.get('insumos', [])) for c in all_comp)
    print(f"\nTotal: {len(all_comp)} composições, {total_ins} insumos")

    if args.sample_output:
        sample = all_comp[:15]
        with open(args.sample_output, 'w', encoding='utf-8') as f:
            json.dump(sample, f, ensure_ascii=False, indent=2)
        print(f"Amostra salva: {args.sample_output}")

    if args.dry_run:
        print("\n[DRY RUN] 3 primeiras composições:")
        for c in all_comp[:3]:
            print(json.dumps(c, ensure_ascii=False, indent=2))
            print()
        return

    print(f"\nEnviando em batches de {args.batch}...")
    inserted_comp = 0
    inserted_ins = 0
    for i in range(0, len(all_comp), args.batch):
        batch = all_comp[i:i+args.batch]
        id_map = insert_batch_composicoes(batch)
        inserted_comp += len(id_map)
        insumos_payload = []
        for comp in batch:
            key = (comp['codigo_norm'], comp.get('variante', ''))
            comp_id = id_map.get(key)
            if not comp_id:
                continue
            for ins in comp.get('insumos', []):
                insumos_payload.append({'composicao_id': comp_id, **ins})
        inserted_ins += insert_batch_insumos(insumos_payload)
        if (i + args.batch) % (args.batch * 10) == 0:
            print(f"  [{i+args.batch}/{len(all_comp)}] comp={inserted_comp} ins={inserted_ins}")

    print(f"\nOK: {inserted_comp} composições, {inserted_ins} insumos no Supabase")


if __name__ == '__main__':
    main()
