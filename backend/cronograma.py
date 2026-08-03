# -*- coding: utf-8 -*-
"""Gerador de cronograma FÍSICO a partir do quantitativo do projeto.

🪤 Físico, não físico-financeiro: a curva S daqui é % de AVANÇO acumulado, não
desembolso. Não existe um único campo em R$ neste módulo, e não deve existir
enquanto valer a regra dura nº5 (o AI.arq não precifica).

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
    # 01/08/2026 — 4 disciplinas REAIS do banco caíam no vácuo (nenhuma keyword
    # batia) e SUMIAM do cronograma em silêncio. Era a raiz dos cronogramas de
    # 1-2 fases que minavam a confiança.
    ('PORTA',                     'Esquadrias',                 0.45, 0.20),
    ('ILUMIN',                    'Iluminação',                 0.60, 0.25),
    ('DIVIS',                     'Divisórias e vidros',        0.50, 0.20),
    ('VIDRO',                     'Divisórias e vidros',        0.50, 0.20),
    ('PERSIANA',                  'Persianas e cortinas',       0.88, 0.08),
    ('CORTINA',                   'Persianas e cortinas',       0.88, 0.08),
]


def _mapear_fase(disc_upper: str):
    """Disciplina (UPPER) → (label, offset%, dur%) do SEQUENCIAMENTO, ou None.
    Compartilhado entre a criação de fases e o cálculo de produtividade
    (cronograma_produtividade) pra nunca divergirem."""
    for kw, label, off, dur in SEQUENCIAMENTO:
        if kw in disc_upper:
            return (label, off, dur)
    return None


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


def _valor_limpo(v) -> float:
    """Valor em R$ vindo do navegador → float não-negativo. 0 = não informado.

    Aceita "1.234,56" (pt-BR), "1234.56" e número. Lixo vira 0 em vez de
    explodir: o financeiro é opcional, e um campo mal digitado não pode
    derrubar o cronograma inteiro — que é a parte que sempre funciona."""
    if v is None or v is True or v is False:
        return 0.0
    if isinstance(v, (int, float)):
        return max(0.0, round(float(v), 2))
    s = str(v).strip()
    if not s:
        return 0.0
    s = s.replace('R$', '').replace(' ', '').replace('\xa0', '')
    if ',' in s:
        # Tem vírgula: pt-BR sem ambiguidade — ponto é milhar, vírgula decimal.
        s = s.replace('.', '').replace(',', '.')
    elif '.' in s:
        # 🚨 Só ponto é AMBÍGUO e errar aqui erra o dinheiro por 1000×:
        # "1.234" é mil duzentos e trinta e quatro em pt-BR e um-vírgula-dois
        # em en. Desempate pela forma do grupo, que é como o brasileiro digita:
        #   "1.234" / "1.234.567"  -> milhar (3 dígitos no último grupo)
        #   "1.23"  / "1.2"        -> decimal
        # Mesma família do erro de escala 100× do motor: número plausível e
        # calado é pior que número que quebra.
        grupos = s.split('.')
        if len(grupos) > 2 or (len(grupos) == 2 and len(grupos[1]) == 3
                               and grupos[0].isdigit()):
            s = s.replace('.', '')
    try:
        return max(0.0, round(float(s), 2))
    except ValueError:
        return 0.0


def calcular_financeiro(fases: List[Dict], matriz: List[Dict],
                        meses: List[Dict]) -> Optional[Dict]:
    """Distribui o valor QUE O CLIENTE INFORMOU por mês, usando o mesmo rateio
    do cronograma físico (`matriz_pct`).

    🔒 Regra dura nº5 — não precificamos: aqui não existe tabela de preço,
    sugestão de valor, BDI nem SINAPI de custo. A conta é uma só:
        desembolso(mês) = Σ_fase  valor_informado(fase) × %(fase, mês)
    Se o cliente não informou nada, devolve None e o cronograma segue sendo
    puramente físico — que é o comportamento de sempre.

    🪤 O rateio é o MESMO da parte física de propósito: se o cliente mover uma
    fase no Gantt, o desembolso anda junto. Dois rateios independentes
    divergiriam em silêncio, que é o problema que a regra nº7 existe pra evitar.
    """
    total = round(sum(f.get('valor_previsto') or 0 for f in fases), 2)
    if total <= 0:
        return None

    n_meses = len(meses)
    por_mes = [0.0] * n_meses
    # matriz[i] corresponde a fases[i] (mesma ordem, montada no mesmo laço).
    for fase, linha in zip(fases, matriz):
        valor = fase.get('valor_previsto') or 0
        if valor <= 0:
            continue
        pcts = linha.get('percentuais_por_mes') or []
        soma_pct = sum(pcts)
        if soma_pct <= 0:
            continue
        # Normaliza pela soma real, não por 100: os percentuais são
        # arredondados por mês e quase nunca fecham exatamente em 100. Dividir
        # por 100 faria sumir (ou sobrar) dinheiro do total informado.
        for i, p in enumerate(pcts):
            if p:
                por_mes[i] += valor * p / soma_pct

    por_mes = [round(v, 2) for v in por_mes]
    # Sobra de centavos do arredondamento vai pro último mês com desembolso —
    # a soma dos meses TEM que bater com o total informado, senão o cliente vê
    # dois números diferentes pra mesma coisa e não confia em nenhum.
    dif = round(total - sum(por_mes), 2)
    if dif:
        ultimo = max((i for i, v in enumerate(por_mes) if v > 0), default=0)
        por_mes[ultimo] = round(por_mes[ultimo] + dif, 2)

    acumulado, corrente = [], 0.0
    for v in por_mes:
        corrente = round(corrente + v, 2)
        acumulado.append(corrente)

    return {
        'total_informado': total,
        'por_mes': por_mes,
        'acumulado': acumulado,
        # Curva S financeira: mesma leitura da física, com peso em dinheiro.
        'curva_s': [
            {'mes_idx': m['mes_idx'], 'data': m['inicio'], 'label': m['label'],
             'pct_acumulado': round(100 * acumulado[i] / total, 1)}
            for i, m in enumerate(meses)
        ],
        'n_fases_com_valor': sum(1 for f in fases if (f.get('valor_previsto') or 0) > 0),
        'n_fases': len(fases),
        # Carimbo de origem: este número é DELE. O front e o PDF usam isto pra
        # rotular, do mesmo jeito que a área total informada é rotulada.
        'origem': 'informado_pelo_cliente',
    }


def gerar_cronograma_de_fases_custom(fases_custom: List[Dict], data_inicio: str,
                                       duracao_meses: int) -> Dict:
    """Gera cronograma JSON a partir de lista de fases EDITADAS pelo cliente.

    Cada fase em fases_custom: {label, inicio, fim, dur_dias?, cor?, ambiente?, ordem?,
                                 depends_on?, is_milestone?, parent_ordem?}
    inicio e fim em ISO YYYY-MM-DD.

    Onda 3 (2026-05-25):
    - depends_on: lista de ordens das fases predecessoras (FS — Finish-Start).
      Se preenchido, o início da fase é forçado pro dia seguinte ao fim da
      última predecessora terminar. Cascade automático.
    - is_milestone: marco pontual (dur_dias = 0, renderizado como diamante).
    - parent_ordem: ordem da fase-grupo pai (se a fase é filha de um grupo).

    Pula a etapa de mapear disciplina→sequenciamento (já vem mastigado).
    """
    import math
    dt_inicio = _parse_date(data_inicio)

    fases = []
    for orig_idx, f in enumerate(fases_custom):
        try:
            ini = _parse_date(f['inicio'])
            fim = _parse_date(f['fim'])
        except (KeyError, ValueError):
            continue
        is_milestone = bool(f.get('is_milestone', False))
        dur_dias = (fim - ini).days
        if is_milestone:
            # Marcos têm duração 0 — fim = início
            fim = ini
            dur_dias = 0
        elif dur_dias <= 0:
            dur_dias = 7
            fim = ini + timedelta(days=7)
        label = f.get('label', 'Sem nome')
        cat = f.get('categoria') or categoria_da_disciplina(label)
        pct_exec = float(f.get('pct_executado', 0) or 0)
        pct_exec = max(0.0, min(100.0, pct_exec))
        # Normaliza depends_on: aceita None, lista vazia, lista de int
        deps_raw = f.get('depends_on') or []
        if isinstance(deps_raw, list):
            depends_on = [int(d) for d in deps_raw if d is not None]
        else:
            depends_on = []
        parent_ordem = f.get('parent_ordem')
        if parent_ordem is not None:
            try:
                parent_ordem = int(parent_ordem)
            except (TypeError, ValueError):
                parent_ordem = None
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
            'depends_on': depends_on,
            'is_milestone': is_milestone,
            'parent_ordem': parent_ordem,
            # Origem da duração (01/08): 'calculada' (das quantidades),
            # 'padrão' (% de mercado) ou 'editada' (mexeu na mão). Preserva o
            # esforço pro peso da curva S continuar fiel após edições.
            'origem': ('editada' if f.get('manual') else (f.get('origem') or 'editada')),
            'esforco_hh': f.get('esforco_hh'),
            'origem_detalhe': f.get('origem_detalhe'),
            # 💰 Valor da fase — SEMPRE informado pelo cliente, nunca calculado
            # por nós (regra dura nº5: não precificamos). Mesmo tratamento da
            # área total informada: entra como dado dele, rotulado como dele.
            'valor_previsto': _valor_limpo(f.get('valor_previsto')),
            # Índice posicional ORIGINAL (na lista fases_custom enviada pelo
            # frontend). depends_on/parent_ordem foram gravados pelo front
            # como índices nessa lista, então guardamos a referência estável
            # pra remapear após o sort abaixo. Bug P0 2026-06-09: o sort
            # reordenava as fases mas deixava os índices apontando pra fase
            # errada.
            '_orig_idx': orig_idx,
        })

    fases.sort(key=lambda x: (x.get('ordem') or 0, x['inicio']))

    # Remapeia depends_on/parent_ordem (índices da ordem ORIGINAL do frontend)
    # pra nova posição após o sort. Sem isso, o sort faz os índices apontarem
    # pra fase errada (P0-2 da auditoria 2026-06-09). Índices que apontam pra
    # uma fase que foi descartada (data inválida) ou inexistente viram None/
    # removidos — não viram dependência fantasma.
    remap = {f['_orig_idx']: novo_idx for novo_idx, f in enumerate(fases)}
    for f in fases:
        f['depends_on'] = [remap[d] for d in f['depends_on'] if d in remap]
        p = f.get('parent_ordem')
        f['parent_ordem'] = remap.get(p) if p is not None else None

    # Aplica cascade FS — fases com depends_on começam após predecessoras terminarem
    fases, warnings_ciclo = _aplicar_dependencias_fs(fases)
    # Re-agrega datas dos grupos pai = min(filhos.inicio) e max(filhos.fim)
    fases = _agregar_grupos(fases)

    # _orig_idx era só auxiliar do remap — não vaza pro JSON de saída.
    for f in fases:
        f.pop('_orig_idx', None)
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

    # Curva S por ESFORÇO (01/08): mover/editar fase MOVE a curva —
    # a sigmoide antiga era função só do tempo, cega ao Gantt editado.
    curva_s = _curva_s_por_esforco(fases, meses, dt_inicio)

    caminho_critico = sorted(fases, key=lambda f: f['dur_dias'], reverse=True)[:5]
    caminho_critico = [{'label': f['label'], 'dur_dias': f['dur_dias'],
                        'categoria': f.get('categoria'), 'cor': f.get('cor')}
                       for f in caminho_critico]

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
        # None enquanto o cliente não informar valor nenhum — aí o cronograma
        # é puramente FÍSICO, como sempre foi. Só vira físico-financeiro
        # quando o número dele existe.
        'financeiro': calcular_financeiro(fases, matriz, meses),
        'curva_s_modelo': {
            'tipo': 'esforco_por_fase',
            'formula': 'P(mês) = Σ esforço concluído até o fim do mês ÷ esforço total',
        },
        'distribuicao_categoria': distrib_cat,
        'ppc': ppc,
        # Avisos não-fatais pro frontend exibir (ex.: dependência circular
        # ignorada). Lista de strings já formatadas em PT-BR. Vazia quando
        # nada foi descartado.
        'warnings': warnings_ciclo,
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
            # 🪤 Saiu o Acórdão TCU 2622/2013 ("cronograma físico-FINANCEIRO
            # evidenciado"): este gerador entrega só a parte FÍSICA (curva S em
            # % de avanço, zero valor em R$). Citar o acórdão sugeria uma
            # conformidade que não temos — e roça a regra dura nº5 (não
            # precificar). Volta a entrar se/quando existir a parte financeira.
            'PMI PMBOK 7th ed. — Performance Domain Planning',
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

    # Esforço CALCULADO das quantidades medidas (01/08 — proposta A do
    # diagnóstico): Σ(qtd × Hh SINAPI) ÷ equipe. Fase com cálculo usa a duração
    # calculada; sem cálculo, cai no % padrão de mercado — sempre ROTULADO.
    try:
        from cronograma_produtividade import esforco_por_fase
        esforcos = esforco_por_fase(items, lambda d: (_mapear_fase(d) or [None])[0])
    except Exception:
        esforcos = {}

    # Mapeia cada disciplina ativa pra uma entry do SEQUENCIAMENTO via keyword.
    # Disciplina SEM keyword vira fase própria (0.30→0.70) — nunca some em
    # silêncio (bug dos cronogramas de 1-2 fases, corrigido 01/08).
    fases = []
    warnings_geracao = []
    ja_adicionados = set()
    avisos_cap = []
    for disc in sorted(disciplinas_ativas):
        m = _mapear_fase(disc)
        if m:
            label, off, dur = m
        else:
            label, off, dur = disc.title(), 0.30, 0.40
            warnings_geracao.append(
                f'Disciplina "{disc.title()}" sem etapa padrão mapeada — entrou como fase própria; ajuste as datas se precisar.')
        if label in ja_adicionados:
            continue
        dt_fase_inicio = dt_inicio + timedelta(days=int(off * duracao_dias))
        calc = esforcos.get(label)
        if calc:
            dur_dias = max(3, min(calc['dias_corridos'], int(duracao_dias * 0.95)))
            if calc['dias_corridos'] > duracao_dias:
                avisos_cap.append(
                    f'{label}: as quantidades pedem ~{calc["dias_corridos"]} dias — mais que a obra inteira ({duracao_dias}); durações limitadas, considere aumentar a duração total.')
            origem = 'calculada'
        else:
            dur_dias = max(7, int(dur * duracao_dias))
            origem = 'padrão'
        # Fase não pode terminar depois do fim da janela: recua o início se preciso
        ini_dias = int(off * duracao_dias)
        if ini_dias + dur_dias > duracao_dias:
            ini_dias = max(0, duracao_dias - dur_dias)
            dt_fase_inicio = dt_inicio + timedelta(days=ini_dias)
        dt_fase_fim = dt_fase_inicio + timedelta(days=dur_dias)
        fase = {
            'label': label,
            'inicio': dt_fase_inicio.isoformat(),
            'fim': dt_fase_fim.isoformat(),
            'dur_dias': dur_dias,
            'offset_pct': off,
            'dur_pct': dur,
            'cor': _cor_da_disciplina(label),
            'origem': origem,
        }
        if calc:
            fase['esforco_hh'] = calc['esforco_hh']
            fase['origem_detalhe'] = calc['detalhe']
            fase['equipe_premissa'] = calc['equipe_premissa']
        fases.append(fase)
        ja_adicionados.add(label)
    warnings_geracao.extend(avisos_cap)

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

    # Curva S por ESFORÇO (01/08): derivada do próprio Gantt — peso de cada
    # fase (Hh calculado, ou dur_dias como proxy) distribuído nos dias dela.
    # Editar fase agora MOVE a curva. Substitui a sigmoide decorativa.
    curva_s = _curva_s_por_esforco(fases, meses, dt_inicio)

    # Top-5 fases mais longas (NÃO é caminho crítico — nome mantido na chave
    # por compat com o frontend; rótulo correto aplicado na tela em 01/08)
    caminho_critico = sorted(fases, key=lambda f: f['dur_dias'], reverse=True)[:5]
    caminho_critico = [{'label': f['label'], 'dur_dias': f['dur_dias'],
                        'categoria': f.get('categoria'), 'cor': f.get('cor')}
                       for f in caminho_critico]

    data_fim = max(_parse_date(f['fim']) for f in fases) if fases else dt_inicio
    n_calculadas = sum(1 for f in fases if f.get('origem') == 'calculada')

    return {
        'fases': fases,
        'meses': meses,
        'matriz_pct': matriz,
        'curva_s': curva_s,
        'curva_s_modelo': {
            'tipo': 'esforco_por_fase',
            'formula': 'P(mês) = Σ esforço concluído até o fim do mês ÷ esforço total',
            'nota': ('Curva derivada do próprio Gantt: peso de cada fase = homem-hora '
                     'calculado das quantidades (quando disponível) ou duração da fase.'),
        },
        'warnings': warnings_geracao,
        'resumo': {
            'data_inicio': dt_inicio.isoformat(),
            'data_fim': data_fim.isoformat(),
            'duracao_meses': duracao_meses,
            'duracao_dias_reais': (data_fim - dt_inicio).days,
            'n_fases': len(fases),
            'n_fases_calculadas': n_calculadas,
            'n_disciplinas_quantitativo': len(disciplinas_ativas),
            'caminho_critico': caminho_critico,
            'ppc_alvo': 0.75,           # padrão Last Planner médio porte BR
            'lps_compativel': True,
        },
        'marcos_legais': [
            'Lei 14.133/2021 Art 117 — medição mensal obrigatória',
            'Lei 14.133/2021 Art 121 — fiscalização + diário de obra',
            # 🪤 Saiu o Acórdão TCU 2622/2013 ("cronograma físico-FINANCEIRO
            # evidenciado"): este gerador entrega só a parte FÍSICA (curva S em
            # % de avanço, zero valor em R$). Citar o acórdão sugeria uma
            # conformidade que não temos — e roça a regra dura nº5 (não
            # precificar). Volta a entrar se/quando existir a parte financeira.
            'PMI PMBOK 7th ed. — Performance Domain Planning',
            'Last Planner System (Ballard 2000) — 4 níveis + PPC',
        ],
        'ressalva': (
            'Fases marcadas como "calculada" têm duração derivada das QUANTIDADES do seu '
            'quantitativo × coeficientes de mão de obra de composições SINAPI (código citado '
            'em cada fase), com premissa de equipe declarada — ajuste se a sua equipe for '
            'outra. Demais fases seguem sequenciamento usual de obra brasileira (% da duração '
            'total). Quantidades estimadas (laranja no quantitativo) entram no cálculo — '
            'revise-as pra um cronograma mais fiel. Validar com engenheiro responsável '
            '(CREA/CAU) antes de comprometer prazo com cliente; sondagem, clima, fornecedores '
            'e canteiro podem alterar significativamente.'
        ),
    }


def _curva_s_por_esforco(fases: List[Dict], meses: List[Dict], dt_inicio: date) -> List[Dict]:
    """Curva S derivada do PRÓPRIO Gantt (01/08/2026, proposta B do diagnóstico).

    Peso da fase = esforco_hh (calculado das quantidades) quando existe, senão
    dur_dias como proxy. O esforço de cada fase é distribuído uniformemente nos
    dias dela; %% acumulado do mês = esforço concluído até o fim do mês ÷ total.
    Editar/mover fase muda a curva — a sigmoide antiga era decorativa (função
    do tempo, cega ao Gantt)."""
    pesos = []
    total = 0.0
    for f in fases:
        try:
            p = float(f.get('esforco_hh') or 0) or float(f.get('dur_dias') or 1)
        except (TypeError, ValueError):
            p = 1.0
        pesos.append(max(0.001, p))
        total += pesos[-1]
    curva = []
    for m in meses:
        m_fim = _parse_date(m['fim'])
        feito = 0.0
        for f, peso in zip(fases, pesos):
            f_ini = _parse_date(f['inicio'])
            f_fim = _parse_date(f['fim'])
            dur = max(1, (f_fim - f_ini).days + 1)
            if m_fim >= f_fim:
                frac = 1.0
            elif m_fim < f_ini:
                frac = 0.0
            else:
                frac = ((m_fim - f_ini).days + 1) / dur
            feito += peso * frac
        pct = 100.0 * feito / total if total else 0.0
        curva.append({
            'mes_idx': m['mes_idx'],
            'mes_label': m['label'],
            'pct_acumulado': round(min(100.0, pct), 1),
            'data_fim_mes': m['fim'],
        })
    return curva


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


# Paleta "materiais de obra" — atualizada 2026-07-18 a pedido do Pedro
# ("to achando feio" a escala 100% cinza de 2026-05-25; ele liberou a regra
# do daltonismo pros materiais de cliente e pediu elegância). Tons TERROSOS
# e dessaturados — cada categoria evoca o material da etapa, sem virar
# dashboard infantil. Mesma cor alimenta Gantt, matriz, PDF e PPT.
CATEGORIA_COR = {
    'preliminares':   '#C9B896',  # areia — canteiro/mobilização, leve
    'estrutura':      '#3E5C76',  # azul-aço — peso do concreto/aço
    'vedacoes':       '#C06B4E',  # terracota — alvenaria/tijolo
    'instalacoes':    '#2F8F83',  # verde-petróleo — dutos e tubulações
    'acabamentos':    '#98A15F',  # oliva — pintura/revestimentos
    'entrega':        '#703D57',  # vinho — marco final, celebração sóbria
    'complementares': '#8E8CA8',  # lilás-cinza — apoio, discreto
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


# ─── Onda 3 (2026-05-25): dependências FS + grupos ─────────────────────

def _aplicar_dependencias_fs(fases: List[Dict]):
    """Aplica cascade Finish-Start respeitando ordenação topológica.

    Pra cada fase com depends_on, força inicio = max(predecessoras.fim) + 1 dia,
    e ajusta fim mantendo a duração original (dur_dias).

    P0-1 da auditoria 2026-06-09: antes o cascade percorria as fases na ordem
    da lista. Se uma sucessora aparecia ANTES da predecessora, ela lia a data
    velha da predecessora (que ainda não tinha sido recalculada). Agora a
    ordem de processamento é definida por um topological sort (Kahn): toda
    predecessora é recalculada antes da sucessora, então o cascade propaga
    em uma passada só.

    Ciclos: dependências que fazem parte de um ciclo são descartadas (a aresta
    "de volta" é removida) e um aviso em PT-BR é acumulado pra devolver ao
    frontend. Não trava o cronograma — só ignora a dependência circular.

    Grupos (fases que SÃO pai — têm filhos) não têm cascade aplicado direto;
    suas datas são agregadas em _agregar_grupos depois.

    Retorna (fases, warnings): mesma lista (mutada) + lista de strings de aviso.
    """
    warnings: List[str] = []
    if not fases:
        return fases, warnings

    n = len(fases)

    # Detecta grupos (que TÊM filhos) — não cascateamos eles, deixamos
    # pro agregar_grupos. Filhos sim, cascateamos.
    grupos = {f.get('parent_ordem') for f in fases if f.get('parent_ordem') is not None}

    # 1) Saneia depends_on: descarta índice fora de faixa e auto-referência.
    #    deps_por_fase[i] = lista de predecessoras válidas (estruturalmente).
    deps_por_fase: List[List[int]] = []
    for i, f in enumerate(fases):
        validos = []
        for d in (f.get('depends_on') or []):
            if not isinstance(d, int):
                continue
            if d < 0 or d >= n or d == i:
                continue
            if d not in validos:
                validos.append(d)
        deps_por_fase.append(validos)

    def _label(idx: int) -> str:
        return fases[idx].get('label', f'fase {idx + 1}')

    # 2) Quebra ciclos: faz um DFS marcando cor (0=branco,1=cinza,2=preto).
    #    Aresta i→d que aponta pra um nó "cinza" (no stack atual) é uma aresta
    #    de retorno → remove e gera aviso. Resultado: grafo acíclico (DAG).
    BRANCO, CINZA, PRETO = 0, 1, 2
    cor = [BRANCO] * n

    def _dfs(i: int):
        cor[i] = CINZA
        sobreviventes = []
        for d in deps_por_fase[i]:
            if cor[d] == CINZA:
                # aresta de retorno → ciclo entre i e d
                warnings.append(
                    f'Dependência circular ignorada entre "{_label(i)}" e '
                    f'"{_label(d)}".'
                )
                continue  # descarta esta aresta
            if cor[d] == BRANCO:
                _dfs(d)
            sobreviventes.append(d)
        deps_por_fase[i] = sobreviventes
        cor[i] = PRETO

    for i in range(n):
        if cor[i] == BRANCO:
            _dfs(i)

    # 3) Kahn: ordena topologicamente o DAG (predecessoras antes de sucessoras).
    #    grau de entrada = nº de predecessoras de cada fase.
    indeg = [0] * n
    sucessores: List[List[int]] = [[] for _ in range(n)]
    for i in range(n):
        for d in deps_por_fase[i]:
            indeg[i] += 1
            sucessores[d].append(i)

    from collections import deque
    fila = deque(i for i in range(n) if indeg[i] == 0)
    ordem_topo: List[int] = []
    while fila:
        i = fila.popleft()
        ordem_topo.append(i)
        for s in sucessores[i]:
            indeg[s] -= 1
            if indeg[s] == 0:
                fila.append(s)
    # Salvaguarda: se sobrou algo (não deveria, já é DAG), anexa na ordem atual.
    if len(ordem_topo) < n:
        restantes = [i for i in range(n) if i not in set(ordem_topo)]
        ordem_topo.extend(restantes)

    # 4) Aplica cascade na ordem topológica.
    for i in ordem_topo:
        if i in grupos:
            continue  # grupo pai, datas vêm dos filhos
        f = fases[i]
        deps_validos = deps_por_fase[i]
        # Propaga a lista saneada pra saída (frontend desenha as setas daqui).
        f['depends_on'] = deps_validos
        if not deps_validos:
            continue
        try:
            max_fim = max(_parse_date(fases[d]['fim']) for d in deps_validos)
        except (KeyError, ValueError):
            continue
        novo_inicio = max_fim + timedelta(days=1)
        dur = f.get('dur_dias', 7)
        if f.get('is_milestone'):
            f['inicio'] = novo_inicio.isoformat()
            f['fim'] = novo_inicio.isoformat()
            f['dur_dias'] = 0
        else:
            f['inicio'] = novo_inicio.isoformat()
            f['fim'] = (novo_inicio + timedelta(days=dur)).isoformat()
            # Recalcula dur (caso novo_inicio == ini original, dur intacto)
            f['dur_dias'] = (_parse_date(f['fim']) - _parse_date(f['inicio'])).days

    return fases, warnings


def _agregar_grupos(fases: List[Dict]) -> List[Dict]:
    """Pra cada fase-pai (que tem filhos com parent_ordem apontando pra ela),
    força inicio = min(filhos.inicio) e fim = max(filhos.fim).

    Permite que o usuário defina grupos como "Estrutura" cujas datas
    espelham automaticamente as fases filhas.
    """
    if not fases:
        return fases
    # Mapeia ordem → idx (a partir de "ordem" se setado, senão idx posicional)
    n = len(fases)

    # Pais identificados por parent_ordem apontando pra esse idx
    # parent_ordem é INDEX posicional na lista (0-based)
    filhos_por_pai = {}
    for i, f in enumerate(fases):
        p = f.get('parent_ordem')
        if p is None:
            continue
        if not isinstance(p, int) or p < 0 or p >= n or p == i:
            continue
        filhos_por_pai.setdefault(p, []).append(i)

    for pai_idx, filhos_idx in filhos_por_pai.items():
        pai = fases[pai_idx]
        try:
            inicios = [_parse_date(fases[ci]['inicio']) for ci in filhos_idx]
            fins = [_parse_date(fases[ci]['fim']) for ci in filhos_idx]
        except (KeyError, ValueError):
            continue
        pai['inicio'] = min(inicios).isoformat()
        pai['fim'] = max(fins).isoformat()
        pai['dur_dias'] = (max(fins) - min(inicios)).days
        pai['is_group'] = True  # flag pro frontend renderizar diferente

    return fases
