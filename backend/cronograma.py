# -*- coding: utf-8 -*-
"""Gerador de cronograma físico-financeiro a partir do quantitativo do projeto.

Recebe lista de disciplinas (extraída do project_items) + data início + duração.
Devolve JSON com fases + Gantt + curva S, pronto pra renderizar no frontend.

Sequenciamento alinhado com convenção de mercado BR (16 etapas construtivas):
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


def gerar_cronograma_de_fases_custom(fases_custom: List[Dict], data_inicio: str,
                                       duracao_meses: int) -> Dict:
    """Gera cronograma JSON a partir de lista de fases EDITADAS pelo cliente.

    Cada fase em fases_custom: {label, inicio, fim, dur_dias?, cor?, ambiente?, ordem?}
    inicio e fim em ISO YYYY-MM-DD.

    Pula a etapa de mapear disciplina→sequenciamento (já vem mastigado).
    """
    import math
    dt_inicio = _parse_date(data_inicio)

    fases = []
    for f in fases_custom:
        try:
            ini = _parse_date(f['inicio'])
            fim = _parse_date(f['fim'])
        except (KeyError, ValueError):
            continue
        dur_dias = (fim - ini).days
        if dur_dias <= 0:
            dur_dias = 7
            fim = ini + timedelta(days=7)
        label = f.get('label', 'Sem nome')
        cat = f.get('categoria') or categoria_da_disciplina(label)
        pct_exec = float(f.get('pct_executado', 0) or 0)
        pct_exec = max(0.0, min(100.0, pct_exec))
        fases.append({
            'label': label,
            'inicio': ini.isoformat(),
            'fim': fim.isoformat(),
            'dur_dias': dur_dias,
            'offset_pct': 0,
            'dur_pct': 0,
            'cor': f.get('cor') or _cor_da_disciplina(label),
            'ambiente': f.get('ambiente'),
            'ordem': f.get('ordem'),
            'manual': bool(f.get('manual', False)),
            'categoria': cat,
            'pct_executado': pct_exec,
        })

    fases.sort(key=lambda x: (x.get('ordem') or 0, x['inicio']))
    data_fim = max((_parse_date(f['fim']) for f in fases), default=dt_inicio)
    duracao_dias_real = max(1, (data_fim - dt_inicio).days)

    # Meses calendário
    meses = []
    cursor = date(dt_inicio.year, dt_inicio.month, 1)
    n_meses_grid = max(duracao_meses + 2, math.ceil(duracao_dias_real / 30) + 1)
    for mes_idx in range(n_meses_grid):
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

    # Matriz % por disciplina × mês
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

    # Curva S sigmoidal
    K_SIGMOID = 10
    curva_s = []
    for m in meses:
        m_fim = _parse_date(m['fim'])
        t = max(0, (m_fim - dt_inicio).days)
        t_norm = min(1.0, t / duracao_dias_real)
        try:
            pct = 100.0 / (1.0 + math.exp(-K_SIGMOID * (t_norm - 0.5)))
        except OverflowError:
            pct = 100.0 if t_norm > 0.5 else 0.0
        if t_norm >= 0.99:
            pct = 100.0
        curva_s.append({
            'mes_idx': m['mes_idx'],
            'mes_label': m['label'],
            'pct_acumulado': round(pct, 1),
            'data_fim_mes': m['fim'],
        })

    caminho_critico = sorted(fases, key=lambda f: f['dur_dias'], reverse=True)[:5]
    caminho_critico = [{'label': f['label'], 'dur_dias': f['dur_dias']} for f in caminho_critico]

    # NOVO: PPC + distribuição categoria + curva realizada
    ppc = calcular_ppc(fases)
    distrib_cat = distribuicao_por_categoria(fases)
    curva_real = curva_s_realizada(fases, meses, dt_inicio.isoformat())

    return {
        'fases': fases,
        'meses': meses,
        'matriz_pct': matriz,
        'curva_s': curva_s,
        'curva_s_realizada': curva_real,
        'curva_s_modelo': {
            'tipo': 'sigmoidal',
            'k': K_SIGMOID,
            'formula': 'P(t) = 100 / (1 + e^(-k(t/T - 0.5)))',
        },
        'distribuicao_categoria': distrib_cat,
        'ppc': ppc,
        'resumo': {
            'data_inicio': dt_inicio.isoformat(),
            'data_fim': data_fim.isoformat(),
            'duracao_meses': duracao_meses,
            'duracao_dias_reais': duracao_dias_real,
            'n_fases': len(fases),
            'n_disciplinas_quantitativo': len(fases),
            'caminho_critico': caminho_critico,
            'ppc_alvo': 0.75,
            'lps_compativel': True,
            'editado_manualmente': True,
            'avanco_real_pct': ppc['avanco_real_pct'],
        },
        'marcos_legais': [
            'Lei 14.133/2021 Art 117 — medição mensal obrigatória',
            'Lei 14.133/2021 Art 121 — fiscalização + diário de obra',
            'Acórdão TCU 2622/2013 — cronograma físico-financeiro evidenciado',
            'PMI PMBOK 7th ed. — Performance Domain Planning',
            'NBR 16636-1/2:2017 — gerenciamento de serviços técnicos',
            'Last Planner System (Ballard 2000) — 4 níveis + PPC',
        ],
        'ressalva': (
            'Cronograma editado manualmente pelo usuário. '
            'Validar com engenheiro responsável (CREA/CAU) antes de comprometer '
            'prazo com cliente.'
        ),
    }


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

    # Curva S — modelo SIGMOIDAL (logístico), não linear
    # P(t) = 100 / (1 + e^(-k(t/T - 0.5)))
    # k=10 default (curvatura média). Maior k = curva mais brusca início/fim.
    import math
    K_SIGMOID = 10
    duracao_dias_real = (max(_parse_date(f['fim']) for f in fases) - dt_inicio).days if fases else duracao_dias
    curva_s = []
    for m in meses:
        m_fim = _parse_date(m['fim'])
        # Tempo decorrido em dias até o fim do mês
        t = max(0, (m_fim - dt_inicio).days)
        # Normalizado 0..1 (clamp em 1.0)
        t_norm = min(1.0, t / max(1, duracao_dias_real))
        # Função logística sigmoidal
        try:
            pct = 100.0 / (1.0 + math.exp(-K_SIGMOID * (t_norm - 0.5)))
        except OverflowError:
            pct = 100.0 if t_norm > 0.5 else 0.0
        # Marca 100 no último mês útil
        if t_norm >= 0.99:
            pct = 100.0
        curva_s.append({
            'mes_idx': m['mes_idx'],
            'mes_label': m['label'],
            'pct_acumulado': round(pct, 1),
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
        'curva_s_modelo': {
            'tipo': 'sigmoidal',
            'k': K_SIGMOID,
            'formula': 'P(t) = 100 / (1 + e^(-k(t/T - 0.5)))',
            'nota': 'Curva S realista (não linear). Refletido em obra padrão BR.',
        },
        'resumo': {
            'data_inicio': dt_inicio.isoformat(),
            'data_fim': data_fim.isoformat(),
            'duracao_meses': duracao_meses,
            'duracao_dias_reais': (data_fim - dt_inicio).days,
            'n_fases': len(fases),
            'n_disciplinas_quantitativo': len(disciplinas_ativas),
            'caminho_critico': caminho_critico,
            'ppc_alvo': 0.75,           # padrão Last Planner médio porte BR
            'lps_compativel': True,
        },
        'marcos_legais': [
            'Lei 14.133/2021 Art 117 — medição mensal obrigatória',
            'Lei 14.133/2021 Art 121 — fiscalização + diário de obra',
            'Acórdão TCU 2622/2013 — cronograma físico-financeiro evidenciado',
            'PMI PMBOK 7th ed. — Performance Domain Planning',
            'NBR 16636-1/2:2017 — gerenciamento de serviços técnicos',
            'Last Planner System (Ballard 2000) — 4 níveis + PPC',
        ],
        'ressalva': (
            'Cronograma referência baseado em produtividade típica de mercado '
            '(construtora médio porte) + sequenciamento construtivo padrão BR '
            '(16 etapas construtivas, alinhado NBR 16636) + curva S sigmoidal. '
            'Validar com engenheiro responsável (CREA/CAU) antes de comprometer '
            'prazo com cliente. Variáveis específicas (sondagem, fornecedor de '
            'pré-fabricado, restrição climática, condicionantes do canteiro, '
            'férias coletivas) podem alterar significativamente.'
        ),
    }


def sugerir_duracao(typology: Optional[str], area_m2: Optional[float],
                    files_count: int = 0, n_disciplinas: int = 0) -> Dict:
    """Sugere duração de obra em meses baseado em tipologia + área + complexidade.

    Heurística calibrada com produtividade típica de mercado BR — construtora
    médio porte, sem condicionantes especiais.

    Retorna {duracao_meses, faixa_min, faixa_max, raciocinio, detalhes}.
    """
    typology = (typology or '').lower().strip()
    area = float(area_m2 or 0)

    # Categorias por tipologia (faixas em meses)
    # Format: (cond, base_min, base_max, m2_por_mes_extra, label)
    if typology in ('residential', 'residencial'):
        if area <= 200:
            base_min, base_max, default = 6, 9, 7
            label = 'Residencial 1 pav até 200 m²'
        elif area <= 400:
            base_min, base_max, default = 10, 14, 12
            label = 'Residencial 2-3 pav (200-400 m²)'
        elif area <= 1000:
            base_min, base_max, default = 14, 20, 17
            label = 'Residencial alto padrão (400-1000 m²)'
        else:
            base_min, base_max, default = 18, 28, 22
            label = 'Residencial multifamiliar grande (1000+ m²)'

    elif typology in ('retail', 'comercial', 'varejo'):
        if area <= 200:
            base_min, base_max, default = 3, 5, 4
            label = 'Comercial pequeno até 200 m²'
        elif area <= 500:
            base_min, base_max, default = 4, 7, 5
            label = 'Comercial médio (200-500 m²)'
        elif area <= 1000:
            base_min, base_max, default = 6, 10, 8
            label = 'Comercial grande (500-1000 m²)'
        else:
            base_min, base_max, default = 10, 16, 13
            label = 'Comercial 1000+ m²'

    elif typology in ('office', 'escritorio', 'corporativo'):
        if area <= 300:
            base_min, base_max, default = 3, 6, 4
            label = 'Escritório pequeno até 300 m²'
        elif area <= 800:
            base_min, base_max, default = 5, 8, 6
            label = 'Andar corporativo médio (300-800 m²)'
        else:
            base_min, base_max, default = 8, 14, 11
            label = 'Andar corporativo grande (800+ m²)'

    elif typology in ('hospital', 'clinica', 'clínica', 'saude', 'saúde'):
        if area <= 300:
            base_min, base_max, default = 5, 8, 6
            label = 'Clínica/consultório pequeno (RDC ANVISA 50)'
        elif area <= 1000:
            base_min, base_max, default = 8, 14, 11
            label = 'Clínica média (300-1000 m²)'
        else:
            base_min, base_max, default = 18, 30, 22
            label = 'Hospital / clínica grande (1000+ m²)'

    elif typology in ('educational', 'educacional', 'escola'):
        if area <= 500:
            base_min, base_max, default = 6, 10, 8
            label = 'Educacional pequeno até 500 m²'
        else:
            base_min, base_max, default = 12, 18, 14
            label = 'Educacional médio/grande'

    else:
        # Sem tipologia identificada — chuta pela área
        if area <= 100:
            base_min, base_max, default = 3, 5, 4
            label = 'Obra pequena (~até 100 m²)'
        elif area <= 500:
            base_min, base_max, default = 5, 9, 6
            label = 'Obra média (até 500 m²)'
        elif area <= 1500:
            base_min, base_max, default = 8, 14, 11
            label = 'Obra grande (500-1500 m²)'
        else:
            base_min, base_max, default = 12, 22, 16
            label = 'Obra muito grande (1500+ m²)'

    # Ajuste por complexidade — mais disciplinas = mais coordenação
    if n_disciplinas >= 12:
        default = min(base_max, default + 2)
        complexidade = 'alta (12+ disciplinas)'
    elif n_disciplinas >= 8:
        default = min(base_max, default + 1)
        complexidade = 'média (8-11 disciplinas)'
    else:
        complexidade = f'baixa ({n_disciplinas} disciplinas)' if n_disciplinas else 'não estimada'

    # Raciocínio textual
    raciocinio_partes = [label]
    if area > 0:
        raciocinio_partes.append(f'~{int(area)} m²')
    if n_disciplinas:
        raciocinio_partes.append(f'{n_disciplinas} disciplina(s)')
    raciocinio = ' · '.join(raciocinio_partes)

    return {
        'duracao_meses': default,
        'faixa_min': base_min,
        'faixa_max': base_max,
        'raciocinio': raciocinio,
        'complexidade': complexidade,
        'detalhes': {
            'typology': typology or 'não informada',
            'area_m2': area,
            'files_count': files_count,
            'n_disciplinas': n_disciplinas,
            'label_categoria': label,
        },
    }


def categoria_da_disciplina(label: str) -> str:
    """Agrupa disciplina em macro-categoria. Útil pra pie chart e stacked bar."""
    l = label.lower()
    if any(t in l for t in ['preliminar', 'mobiliza', 'canteiro', 'demoli',
                              'movimento', 'terra']):
        return 'preliminares'
    if any(t in l for t in ['fundação', 'fundacao', 'estrutura', 'concreto',
                              'pilar', 'viga', 'laje']):
        return 'estrutura'
    if any(t in l for t in ['fechamento', 'alvenaria', 'parede', 'vedação',
                              'vedacao', 'cobertura', 'impermeabil',
                              'esquadria']):
        return 'vedacoes'
    if any(t in l for t in ['elétric', 'eletric', 'hidráulic', 'hidraulic',
                              'gás', 'gas', 'incêndio', 'incendio',
                              'condicionado', 'spda', 'cabeamento',
                              'dados', 'instal']):
        return 'instalacoes'
    if any(t in l for t in ['revestimento', 'piso', 'forro', 'pintura',
                              'marcenaria', 'louças', 'loucas', 'lou',
                              'metais', 'mobili']):
        return 'acabamentos'
    if any(t in l for t in ['limpeza', 'entulho', 'entrega']):
        return 'entrega'
    return 'complementares'


# Paleta sóbria — alinhada com identidade AI.arq (indigo + slate + cyan).
# Atualizada 2026-05-25 — antes havia 20 cores saturadas tipo carnaval.
# Agora: 7 tons dessaturados que mantêm diferenciação por categoria sem
# parecer dashboard de criança. Verde só pra "Entrega" (marco de sucesso).
CATEGORIA_COR = {
    'preliminares':   '#94A3B8',  # slate-400 — neutro, fase inicial
    'estrutura':      '#334155',  # slate-700 — pesado, escuro
    'vedacoes':       '#475569',  # slate-600 — fechamentos
    'instalacoes':    '#4F46E5',  # indigo-600 — accent principal da marca
    'acabamentos':    '#0E7490',  # cyan-700 — accent secundário da marca
    'entrega':        '#059669',  # emerald-600 — único toque de sucesso
    'complementares': '#64748B',  # slate-500 — neutro
}

CATEGORIA_LABEL = {
    'preliminares':   'Preliminares',
    'estrutura':      'Estrutura',
    'vedacoes':       'Vedações + Cobertura',
    'instalacoes':    'Instalações',
    'acabamentos':    'Acabamentos',
    'entrega':        'Entrega',
    'complementares': 'Complementares',
}


def calcular_ppc(fases: List[Dict]) -> Dict:
    """PPC (Percent Plan Complete) — Last Planner.

    PPC global = (soma pct_executado de cada fase ponderado pela duração) / 100

    Devolve {ppc_pct, n_executadas, n_em_andamento, n_nao_iniciadas}.
    """
    if not fases:
        return {'ppc_pct': 0, 'n_executadas': 0, 'n_em_andamento': 0,
                'n_nao_iniciadas': 0, 'avanco_real_pct': 0}

    soma_pct = 0
    soma_dur = 0
    n_exec = 0
    n_and = 0
    n_nao = 0
    for f in fases:
        pct = float(f.get('pct_executado', 0) or 0)
        pct = max(0, min(100, pct))
        dur = float(f.get('dur_dias', 1) or 1)
        soma_pct += pct * dur
        soma_dur += dur
        if pct >= 100:
            n_exec += 1
        elif pct > 0:
            n_and += 1
        else:
            n_nao += 1
    avanco_real = round(soma_pct / max(1, soma_dur), 1)
    return {
        'ppc_pct': avanco_real,
        'n_executadas': n_exec,
        'n_em_andamento': n_and,
        'n_nao_iniciadas': n_nao,
        'avanco_real_pct': avanco_real,
    }


def distribuicao_por_categoria(fases: List[Dict]) -> List[Dict]:
    """Pra pie chart: % de esforço (dias totais) por macro-categoria."""
    if not fases:
        return []
    total = sum(f.get('dur_dias', 0) for f in fases) or 1
    por_cat = {}
    for f in fases:
        cat = f.get('categoria') or categoria_da_disciplina(f.get('label', ''))
        por_cat[cat] = por_cat.get(cat, 0) + f.get('dur_dias', 0)
    out = []
    for cat, dias in sorted(por_cat.items(), key=lambda x: -x[1]):
        out.append({
            'categoria': cat,
            'label': CATEGORIA_LABEL.get(cat, cat.title()),
            'cor': CATEGORIA_COR.get(cat, '#64748B'),
            'dias': dias,
            'pct': round(100 * dias / total, 1),
        })
    return out


def curva_s_realizada(fases: List[Dict], meses: List[Dict],
                       data_inicio_iso: str) -> List[Dict]:
    """Curva S REALIZADA baseada em pct_executado de cada fase.

    Pra cada mês: soma (overlap_dias / total_dias_fase) * pct_executado_fase
    ponderado pela duração da fase no projeto.

    Devolve lista por mês com pct_acumulado_realizado.
    """
    if not fases:
        return []
    dt_inicio = _parse_date(data_inicio_iso)
    total_dur = sum(f.get('dur_dias', 1) for f in fases) or 1

    out = []
    for m in meses:
        m_ini = _parse_date(m['inicio'])
        m_fim = _parse_date(m['fim'])
        acumulado = 0.0
        for f in fases:
            f_ini = _parse_date(f['inicio'])
            f_fim = _parse_date(f['fim'])
            # Considera só dias da fase até FIM do mês atual (acumulado)
            if f_ini > m_fim:
                continue  # fase nem começou nesse mês
            # pct executado proporcional ao tempo decorrido na fase
            # Simplificação: aplica pct uniforme da fase
            pct_fase = float(f.get('pct_executado', 0) or 0)
            # Quanto da fase aconteceu até m_fim?
            if f_fim <= m_fim:
                # Fase inteira já no passado/presente — usa pct_executado direto
                contrib_dur = f.get('dur_dias', 1)
            else:
                # Fase ainda rolando — só a parte já decorrida
                contrib_dur = max(0, (m_fim - f_ini).days + 1)
            contrib_dias_real = contrib_dur * (pct_fase / 100.0)
            acumulado += contrib_dias_real
        acumulado_pct = round(100 * acumulado / total_dur, 1)
        out.append({
            'mes_idx': m['mes_idx'],
            'mes_label': m['label'],
            'pct_realizado': min(100.0, acumulado_pct),
            'data_fim_mes': m['fim'],
        })
    return out


def _mes_label_pt(d: date) -> str:
    """jun/26, jul/26, ago/26 — abreviação PT-BR."""
    meses_br = ['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez']
    return f'{meses_br[d.month - 1]}/{str(d.year)[-2:]}'


def _cor_da_disciplina(label: str) -> str:
    """Cor hex pra cada disciplina.

    Atualizada 2026-05-25: removido o mapping de 20 cores saturadas
    (rosa, laranja, marrom, vermelho fogo) que faziam o cronograma parecer
    dashboard infantil. Agora cada disciplina ganha a cor da CATEGORIA
    a que pertence — 7 tons sóbrios alinhados com indigo + slate + cyan
    da identidade da marca. Pedro é daltônico (regra dura): cores não
    podem ser único diferenciador — o cronograma já leva texto/ícone
    junto, então cor é só apoio visual.
    """
    l = label.lower()
    # Preliminares e canteiro
    if any(k in l for k in ['preliminar', 'canteiro', 'demoli']):
        return CATEGORIA_COR['preliminares']
    # Estrutura (fundação + lajes + pilares)
    if any(k in l for k in ['estrutura', 'fundac', 'fundaç', 'sapata', 'pilar', 'viga', 'laje']):
        return CATEGORIA_COR['estrutura']
    # Vedações e cobertura
    if any(k in l for k in ['fechamento', 'alvenaria', 'vedaç', 'vedac', 'cobertura', 'telhado', 'esquadria', 'impermeabil']):
        return CATEGORIA_COR['vedacoes']
    # Instalações (elétrica, hidráulica, gás, ar, incêndio)
    if any(k in l for k in ['elétric', 'eletric', 'hidráulic', 'hidraulic', 'incêndio', 'incendio',
                            'condicionado', 'climati', 'gás', ' gas', 'instalaç', 'instalac', 'lógic', 'logic']):
        return CATEGORIA_COR['instalacoes']
    # Acabamentos (piso, revestimento, forro, pintura, marcenaria, louça, mobiliário)
    if any(k in l for k in ['piso', 'revestimento', 'forro', 'pintura', 'marcenaria',
                            'mobili', 'lou', 'acabamento']):
        return CATEGORIA_COR['acabamentos']
    # Entrega e limpeza final
    if any(k in l for k in ['entrega', 'limpeza', 'entulho', 'vistoria', 'habite']):
        return CATEGORIA_COR['entrega']
    # Complementares / demais
    if any(k in l for k in ['complementar', 'paisag', 'sinalizaç', 'sinalizac']):
        return CATEGORIA_COR['complementares']
    # Default — slate neutro
    return CATEGORIA_COR['complementares']
