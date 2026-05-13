# -*- coding: utf-8 -*-
"""Gerador de cronograma físico-financeiro a partir do quantitativo do projeto.

Recebe lista de disciplinas (extraída do project_items) + data início + duração.
Devolve JSON com fases + Gantt + curva S, pronto pra renderizar no frontend.

Sequenciamento alinhado com padrão Sienge (16 etapas oficiais BR):
SERVIÇOS INICIAIS → MOVIMENTAÇÃO DE TERRA → FUNDAÇÃO → ESTRUTURA → PAREDE →
ESQUADRIAS → COBERTURA → IMPERMEABILIZAÇÃO → REVESTIMENTOS → PREVENTIVO →
ELÉTRICO → HIDROSSANITÁRIO → LOUÇAS E METAIS → SERVIÇOS COMPLEMENTARES →
PINTURAS → RETIRADA DE ENTULHO
"""
from datetime import date, timedelta
from typing import List, Dict, Optional
from collections import defaultdict


# Sequenciamento padrão BR — cada disciplina mapeada por keyword
# (keyword, label, offset_inicio_%, duracao_%)
SEQUENCIAMENTO = [
    ('PRELIMINAR',                'Serviços preliminares',     0.00, 0.95),
    ('DEMOLI',                    'Demolição',                  0.00, 0.15),
    ('TERRA',                     'Movimento de terra',         0.03, 0.10),
    ('FUNDA',                     'Fundação',                   0.05, 0.18),
    ('ESTRUTUR',                  'Estrutura',                  0.10, 0.30),
    ('FECHAMENTO',                'Fechamentos / alvenaria',    0.20, 0.30),
    ('ALVENARIA',                 'Alvenaria',                  0.20, 0.30),
    ('COBERTURA',                 'Cobertura',                  0.35, 0.15),
    ('IMPERMEABIL',               'Impermeabilização',          0.32, 0.18),
    ('ESQUADRIA',                 'Esquadrias',                 0.45, 0.20),
    ('REVESTIMENTO',              'Revestimentos',              0.50, 0.30),
    ('PISO',                      'Pisos',                      0.60, 0.20),
    ('FORRO',                     'Forros',                     0.55, 0.15),
    ('PINTURA',                   'Pintura',                    0.78, 0.18),
    ('ELÉTRIC',                   'Instalações elétricas',      0.25, 0.55),
    ('ELETRIC',                   'Instalações elétricas',      0.25, 0.55),
    ('HIDR',                      'Instalações hidráulicas',    0.25, 0.55),
    ('LOU',                       'Louças e metais',            0.70, 0.20),
    ('INCÊNDIO',                  'Preventivo contra incêndio', 0.35, 0.30),
    ('INCENDIO',                  'Preventivo contra incêndio', 0.35, 0.30),
    ('AR-CONDICIONADO',           'Ar-condicionado',            0.45, 0.30),
    ('GÁS',                       'Gás',                        0.35, 0.20),
    ('MARCENARIA',                'Marcenaria',                 0.62, 0.25),
    ('MOBILI',                    'Mobiliário',                 0.85, 0.10),
    ('COMPLEMENTAR',              'Complementares',             0.05, 0.85),
    ('LIMPEZA',                   'Limpeza e entrega',          0.93, 0.07),
    ('ENTULHO',                   'Retirada de entulho',        0.95, 0.05),
]


def _parse_date(s: str) -> date:
    """Converte ISO string (YYYY-MM-DD) pra date."""
    return date.fromisoformat(s)


def _add_months_calendar(d: date, m: int) -> date:
    """Soma m meses à data d (calendário civil, não +30d)."""
    y, mo = d.year, d.month + m
    while mo > 12:
        y += 1; mo -= 12
    while mo < 1:
        y -= 1; mo += 12
    # Mantém dia, mas clampa pro último dia do mês se exceder
    import calendar
    last = calendar.monthrange(y, mo)[1]
    return date(y, mo, min(d.day, last))


def _extract_disciplinas(items: List[Dict]) -> set:
    """A partir de lista de project_items, retorna set de disciplinas ativas
    (normalizado upper-case sem caracteres especiais)."""
    out = set()
    for it in items:
        disc = (it.get('discipline') or '').strip().upper()
        if disc and disc not in ('PREMISSAS', 'PREMISSA', ''):
            out.add(disc)
    return out


def gerar_cronograma(items: List[Dict], data_inicio: str,
                     duracao_meses: int) -> Dict:
    """Gera cronograma JSON-serializable.

    Args:
        items: lista de project_items (cada um com 'discipline' setada)
        data_inicio: ISO string YYYY-MM-DD
        duracao_meses: int 1..36

    Returns:
        dict com:
        - fases: lista de {label, inicio, fim, dur_dias, offset_pct, dur_pct, cor}
        - meses: lista de {label, inicio, fim, mes_idx}
        - matriz_pct: [{label_disciplina, percentuais_por_mes: [int]}]
        - curva_s: [{mes_idx, pct_acumulado, data}]
        - resumo: {data_inicio, data_fim, duracao_meses, n_fases, caminho_critico}
    """
    if duracao_meses <= 0 or duracao_meses > 60:
        duracao_meses = 4
    dt_inicio = _parse_date(data_inicio)
    duracao_dias = duracao_meses * 30

    disciplinas_ativas = _extract_disciplinas(items)

    # Mapeia cada disciplina ativa pra uma entry do SEQUENCIAMENTO via keyword
    fases = []
    ja_adicionados = set()
    for disc in sorted(disciplinas_ativas):
        for kw, label, off, dur in SEQUENCIAMENTO:
            if kw in disc and label not in ja_adicionados:
                dt_fase_inicio = dt_inicio + timedelta(days=int(off * duracao_dias))
                dur_dias = max(7, int(dur * duracao_dias))
                dt_fase_fim = dt_fase_inicio + timedelta(days=dur_dias)
                fases.append({
                    'label': label,
                    'inicio': dt_fase_inicio.isoformat(),
                    'fim': dt_fase_fim.isoformat(),
                    'dur_dias': dur_dias,
                    'offset_pct': off,
                    'dur_pct': dur,
                    'cor': _cor_da_disciplina(label),
                })
                ja_adicionados.add(label)
                break

    # Ordena por data de início
    fases.sort(key=lambda f: f['inicio'])

    # Calcula meses calendário (cobertura: duracao_meses + 1 pra dar buffer)
    meses = []
    cursor = date(dt_inicio.year, dt_inicio.month, 1)
    for mes_idx in range(duracao_meses + 2):
        # Primeiro dia do mês cursor
        # Último dia = dia 1 do mês seguinte - 1
        if cursor.month == 12:
            prox = date(cursor.year + 1, 1, 1)
        else:
            prox = date(cursor.year, cursor.month + 1, 1)
        ultimo = prox - timedelta(days=1)
        meses.append({
            'mes_idx': mes_idx,
            'label': _mes_label_pt(cursor),
            'inicio': cursor.isoformat(),
            'fim': ultimo.isoformat(),
        })
        cursor = prox

    # Matriz de % por disciplina x mês (string "26%" ou "")
    matriz = []
    for fase in fases:
        f_ini = _parse_date(fase['inicio'])
        f_fim = _parse_date(fase['fim'])
        f_dur = fase['dur_dias']
        pcts = []
        for m in meses:
            m_ini = _parse_date(m['inicio'])
            m_fim = _parse_date(m['fim'])
            if f_fim < m_ini or f_ini > m_fim:
                pcts.append(0)
                continue
            overlap_ini = max(f_ini, m_ini)
            overlap_fim = min(f_fim, m_fim)
            overlap_dias = (overlap_fim - overlap_ini).days + 1
            pct = round(100 * overlap_dias / max(1, f_dur))
            pcts.append(max(0, min(100, pct)))
        matriz.append({
            'label': fase['label'],
            'cor': fase['cor'],
            'percentuais_por_mes': pcts,
        })

    # Curva S: avanço acumulado por mês (peso igual por disciplina)
    curva_s = []
    n_fases = max(1, len(fases))
    peso = 100 / n_fases
    acumulado = 0.0
    for m in meses:
        m_ini = _parse_date(m['inicio'])
        m_fim = _parse_date(m['fim'])
        contrib = 0
        for fase in fases:
            f_ini = _parse_date(fase['inicio'])
            f_fim = _parse_date(fase['fim'])
            if f_fim < m_ini or f_ini > m_fim:
                continue
            overlap_ini = max(f_ini, m_ini)
            overlap_fim = min(f_fim, m_fim)
            overlap_dias = (overlap_fim - overlap_ini).days + 1
            contrib += peso * (overlap_dias / max(1, fase['dur_dias']))
        acumulado = min(100, acumulado + contrib)
        curva_s.append({
            'mes_idx': m['mes_idx'],
            'mes_label': m['label'],
            'pct_acumulado': round(acumulado, 1),
            'data_fim_mes': m['fim'],
        })

    # Caminho crítico = top 5 disciplinas com maior duração
    caminho_critico = sorted(fases, key=lambda f: f['dur_dias'], reverse=True)[:5]
    caminho_critico = [{'label': f['label'], 'dur_dias': f['dur_dias']}
                       for f in caminho_critico]

    data_fim = max(_parse_date(f['fim']) for f in fases) if fases else dt_inicio

    return {
        'fases': fases,
        'meses': meses,
        'matriz_pct': matriz,
        'curva_s': curva_s,
        'resumo': {
            'data_inicio': dt_inicio.isoformat(),
            'data_fim': data_fim.isoformat(),
            'duracao_meses': duracao_meses,
            'duracao_dias_reais': (data_fim - dt_inicio).days,
            'n_fases': len(fases),
            'n_disciplinas_quantitativo': len(disciplinas_ativas),
            'caminho_critico': caminho_critico,
        },
    }


def _mes_label_pt(d: date) -> str:
    """jun/26, jul/26, ago/26 — abreviação PT-BR."""
    meses_br = ['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez']
    return f'{meses_br[d.month - 1]}/{str(d.year)[-2:]}'


def _cor_da_disciplina(label: str) -> str:
    """Cor hex pra cada disciplina. Mapping consistente com identidade AI.arq."""
    l = label.lower()
    if 'preliminar' in l: return '#94A3B8'
    if 'estrutura' in l: return '#1E40AF'
    if 'fechamento' in l or 'alvenaria' in l: return '#3730A3'
    if 'cobertura' in l: return '#4338CA'
    if 'esquadria' in l: return '#5B21B6'
    if 'piso' in l: return '#7C3AED'
    if 'revestimento' in l: return '#9333EA'
    if 'forro' in l: return '#A855F7'
    if 'pintura' in l: return '#C026D3'
    if 'elétric' in l or 'eletric' in l: return '#DB2777'
    if 'hidráulic' in l or 'hidraulic' in l: return '#0891B2'
    if 'incêndio' in l or 'incendio' in l: return '#DC2626'
    if 'condicionado' in l: return '#0EA5E9'
    if 'gás' in l or 'gas' in l: return '#F59E0B'
    if 'marcenaria' in l: return '#A16207'
    if 'mobili' in l: return '#78350F'
    if 'lou' in l: return '#06B6D4'
    if 'impermeabil' in l: return '#0D9488'
    if 'complementar' in l: return '#64748B'
    if 'limpeza' in l or 'entulho' in l: return '#10B981'
    return '#6366F1'
