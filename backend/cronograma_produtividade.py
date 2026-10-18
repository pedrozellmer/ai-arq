# -*- coding: utf-8 -*-
"""Duração de fase CALCULADA das quantidades medidas (proposta A do
diagnóstico de 01/08/2026 — docs/DIAGNOSTICO_CRONOGRAMA_2026-08-01.md).

Antes, cada fase era um % fixo da duração total — as quantidades que o motor
MEDE não influenciavam nada. Agora: fases com referência de produtividade têm
duração = Σ(quantidade × Hh/unid) ÷ (equipe × 8 h/dia), com origem rotulada.

FONTE dos coeficientes: composições da NOSSA base SINAPI analítica
(sinapi_composicao + sinapi_insumos, soma dos itens com unidade 'H').
Valores conferidos por SQL em 01/08/2026 (sync da base local). Pra atualizar:
  select composicao_codigo, sum(coeficiente) from sinapi_insumos
  where upper(unidade)='H' and composicao_codigo in (...) group by 1;

EQUIPE é PREMISSA declarada (não medida): profissional+ajudante típicos por
serviço. Aparece no detalhe de cada fase e na ressalva — o cliente ajusta a
duração na tela se a equipe dele for outra.

⚠️ Regra "nunca escolher código SINAPI na mão" vale pro MATCH de item do
cliente (entregável). Aqui é tabela interna de referência de produtividade,
com o código citado abertamente no detalhe da fase — outro uso.
"""

import math
import re
import unicodedata

HORAS_DIA = 8
DIAS_UTEIS_POR_CORRIDOS = 5 / 7  # dias corridos = úteis ÷ (5/7)

# Ar-condicionado: (tipo, BTU/h) → (código SINAPI, Hh). Hh somado da NOSSA base
# analítica (unidade H), conferido por SQL 18/10/2026. Inverter e on/off, frio
# e quente/frio do mesmo tipo e porte têm o mesmo Hh na base.
_AR_TIPOS = {
    'hi-wall': (r'hi\W?wall', {9000: ('103244', 4.667), 12000: ('103247', 4.667),
                               18000: ('103250', 5.046), 24000: ('103253', 5.267)}),
    'cassete': (r'cassete', {18000: ('103268', 7.942), 24000: ('103270', 8.257),
                             36000: ('103272', 9.505), 48000: ('103274', 10.018),
                             60000: ('103276', 10.018)}),
    'piso-teto': (r'piso\W?teto', {18000: ('103256', 7.740), 24000: ('103258', 7.946),
                                   36000: ('103261', 8.724), 48000: ('103263', 9.150),
                                   60000: ('103266', 9.150)}),
    'duto': (r'dutos?|dutad[ao]', {18000: ('103279', 5.644), 24000: ('103280', 6.549),
                                   36000: ('103281', 7.130)}),
    'janela': (r'de janela|tipo janela', {7500: ('103282', 0.388), 10000: ('103283', 0.403),
                                          12000: ('103284', 0.414)}),
}


def _refs_ar_condicionado():
    """Uma referência por (tipo, porte): a descrição tem de dizer os dois.
    O porte casa "36.000 BTU", "36000 BTUs", "36,000 btu/h" — e não 136.000."""
    refs = []
    for tipo, (pad_tipo, portes) in _AR_TIPOS.items():
        for btu, (codigo, hh) in portes.items():
            mil, resto = divmod(btu, 1000)
            pad_btu = rf'(?<![\d.,]){mil}[.,]?{resto:03d}\s*btu'
            refs.append((codigo, hh,
                         f"split {tipo} {mil}.{resto:03d} BTU — instalação" if tipo != 'janela'
                         else f"ar de janela {mil}.{resto:03d} BTU — instalação",
                         re.compile(rf'^(?=.*\b(?:{pad_tipo})\b)(?=.*{pad_btu})')))
    return refs


# Referências por LABEL de fase (pós-mapeamento do SEQUENCIAMENTO).
# Cada fase tem referência por classe de unidade (m2 / m / un): uma tupla, ou
# uma LISTA delas quando a classe junta serviços de taxas diferentes.
# (codigo SINAPI, Hh por unidade, descricao curta[, filtro da descrição])
# Com filtro, só o item cuja descrição casa entra; numa lista vale a 1ª que
# casar. Item que não casa com nenhuma fica fora da conta.
REFS_POR_FASE = {
    'Alvenaria': {
        'equipe': 3,
        'm2': ('103368', 1.290, 'alvenaria de vedação bloco cerâmico 14 cm'),
    },
    'Fechamentos / alvenaria': {
        'equipe': 3,
        'm2': ('103368', 1.290, 'alvenaria de vedação bloco cerâmico 14 cm'),
    },
    # 18/10/2026 — REVESTIMENTOS E PISOS: UMA COMPOSIÇÃO POR TIPO DE ITEM.
    # 🩸 Era um coeficiente só por unidade, sem filtro: no /exemplo a pintura
    # (parede 214 m² + forro 101,7 m²) entrava na taxa de EMBOÇO (0,818 Hh/m²,
    # quase 4× a da pintura), e contrapiso e piso vinílico na de PORCELANATO.
    # No acervo (16 cronogramas com estas fases) nenhum m² de Revestimentos com
    # quantidade era emboço: era pintura, emassamento, impermeabilização, deck.
    # Agora o item escolhe a PRIMEIRA composição cuja descrição casa; o que não
    # casa com nenhuma sai da conta — não ganha a de um serviço parecido.
    # Hh somado da NOSSA base analítica (unidade H), conferido por SQL 18/10:
    #  - pintura látex, manual, 2 demãos: teto 0,303 (88488) e parede 0,218
    #    (88489) — econômica, standard e premium têm o MESMO Hh na base. Item
    #    que fala de parede E teto não tem uma taxa só: fica fora.
    #  - piso vinílico: manta 0,627 (101728), placas 0,190 (101727), réguas
    #    0,421 (106790) — 3,3× entre eles, então vinílico sem o formato fica fora.
    #  🪤 Pintura e emboço valem só quando são o serviço que a descrição NOMEIA
    #    (começa por ele): "Reboco liso para pintura — paredes" não é pintura, e
    #    "Pintura em fachada, 2 demãos sobre emboço" não é emboço.
    #  - piso cerâmico 45×45 em área > 10 m², 0,385 (87251): os tamanhos da
    #    base (35×35 a 80×80, mesma faixa de área, assentamento reto) vão de
    #    0,370 a 0,441.
    #  - CONTRAPISO FICA FORA: a base vai de 0,08 (autonivelante 2 cm) a 0,92
    #    Hh/m² (área molhada sobre impermeabilização) — a descrição do item quase
    #    nunca diz qual. Intertravado, carpete, pedra e "piso a definir" também
    #    ficam fora: sem composição escolhida para eles aqui.
    #  🪤 O material tem de estar no NOME do item (antes do "—" ou do
    #    parêntese): "Piso em Prainha — a definir (pedra, deck, porcelanato
    #    externo)" é uma lista de opções, não porcelanato.
    'Revestimentos': {
        'equipe': 3,
        'm2': [
            ('88488', 0.303, 'pintura látex em teto/forro, 2 demãos',
             re.compile(r'^(?!.*\b(paredes?|epox\w*|esmalte|textur\w*|grafiat\w*|verniz|demarca\w*)\b)'
                        r'\W*pintura\b.*\b(tetos?|forros?)\b')),
            ('88489', 0.218, 'pintura látex em parede, 2 demãos',
             re.compile(r'^(?!.*\b(tetos?|forros?|epox\w*|esmalte|textur\w*|grafiat\w*|verniz|demarca\w*)\b)'
                        r'\W*pintura\b.*\bparedes?\b')),
            ('87794', 0.818, 'emboço/massa única em argamassa',
             re.compile(r'^\W*(chapisco\W+(e\W+)?)?(emboco|reboco|massa unica)\b')),
        ],
    },
    'Pisos': {
        'equipe': 2,
        'm2': [
            ('87263', 0.688, 'porcelanato 60×60 assentado',
             re.compile(r'^(?!.*\b(contrapiso|rodapes?|soleiras?)\b)[^—(]*\bporcelanato\b')),
            ('87251', 0.385, 'piso cerâmico 45×45 assentado',
             re.compile(r'^(?!.*\b(contrapiso|rodapes?|soleiras?|paredes?)\b)[^—(]*\bceramic[ao]s?\b')),
            ('101728', 0.627, 'piso vinílico em manta',
             re.compile(r'^(?=[^—(]*\bvinilico\b)[^—(]*\bmanta\b')),
            ('101727', 0.190, 'piso vinílico em placas',
             re.compile(r'^(?=[^—(]*\bvinilico\b)[^—(]*\bplacas?\b')),
            ('106790', 0.421, 'piso vinílico em réguas',
             re.compile(r'^(?=[^—(]*\bvinilico\b)[^—(]*\breguas?\b')),
        ],
    },
    'Forros': {
        'equipe': 2,
        'm2': ('96109', 1.437, 'forro de placas de gesso'),
    },
    'Pintura': {
        'equipe': 2,
        'm2': ('88489', 0.218, 'pintura látex 2 demãos em paredes'),
    },
    'Esquadrias': {
        'equipe': 2,
        'un': ('90822', 2.876, 'porta de madeira 80×210 completa'),
    },
    'Instalações elétricas': {
        'equipe': 2,
        'un': ('91998', 0.484, 'ponto de tomada 2P+T'),
        'm': ('91845', 0.142, 'eletroduto corrugado 25 mm'),
    },
    'Iluminação': {
        'equipe': 2,
        'un': ('97599', 0.232, 'luminária — instalação'),
    },
    # 18/10/2026 — HIDRÁULICA, DIVISÓRIAS E DEMOLIÇÃO GANHARAM A UNIDADE QUE
    # O QUANTITATIVO TRAZ — mas SÓ pro tipo de item que o coeficiente
    # representa (4º elemento: a descrição tem de casar). Sem coeficiente a
    # fase caía no % do prazo e crescia com o PRAZO, não com a quantidade:
    # 3 bacias + 1 cuba viravam 82 dias numa obra de 5 meses.
    # 🩸 A 1ª versão era por unidade, sem filtro, e o acervo derrubou: nos 23
    # cronogramas da base o "un" de hidráulica ia de LUVA e JOELHO (320 numa
    # obra só) a ESTACA RAIZ classificada na disciplina errada; o "un" de
    # divisórias era quase todo JANELA; e "demolição m²" era TERRAPLENAGEM e
    # LIMPEZA DE TERRENO (9.453 m² → 311 dias). Item que não casa fica fora da
    # conta, como antes — a fase segue 'padrão' se nada casar.
    # Hh somado da NOSSA base analítica (unidade H), conferido por SQL 18/10:
    #  - 86888 bacia c/ caixa acoplada, 1,443 Hh — vale pra louça/aparelho e
    #    pro "ponto de <aparelho>" (cuba 1,24; lavatório 1,19–2,44; chuveiro
    #    1,64). Torneira (0,13–0,68), registro, ralo e conexão NÃO entram:
    #    a 1,443 cada, 320 conexões viravam 2 meses de obra.
    #  - 90822 porta 80×210, a mesma de Esquadrias. Janela não tem composição
    #    por unidade na base (é por m²) — fica fora.
    #  - 97638 remoção de drywall, 0,375 Hh/m². Alvenaria de 15 cm pela 97622
    #    (2,55 Hh/m³ × 0,15) dá 0,38 — as duas demolições de reforma caem no
    #    mesmo número. Forro, piso e terreno ficam fora (taxas outras).
    'Instalações hidráulicas': {
        'equipe': 2,
        'm': ('89356', 0.760, 'tubo PVC soldável 25 mm em ramal'),
        'un': ('86888', 1.443, 'louça/aparelho sanitário (bacia c/ caixa acoplada)',
               re.compile(r'\b(bacia|vaso|cuba|lavatorio|pia|mictorio|chuveiro|ducha'
                          r'|tanque(?! sept)|loucas?)\b')),
    },
    'Divisórias e vidros': {
        'equipe': 2,
        'm2': ('96370', 0.456, 'parede drywall face simples'),
        # 🩸 18/10 — a porta de VIDRO entrava na taxa da de madeira. Na base a
        # porta de vidro temperado vai de 1,82 (de correr, 90×210) a 5,93 Hh
        # (de abrir com mola, 90×210) — sem o tipo de abertura não há uma
        # taxa só, então porta que nomeia outro material fica fora.
        'un': ('90822', 2.876, 'porta de madeira 80×210 completa',
               re.compile(r'^(?!.*\b(vidros?|temperado|blindex|box|aluminio|metalic[ao]s?|ferro|aco'
                          r'|pvc)\b).*\bportas?\b')),
    },
    'Demolição': {
        'equipe': 2,
        'm2': ('97638', 0.375, 'remoção de drywall / alvenaria de vedação',
               re.compile(r'drywall|divisori|alvenaria|parede')),
    },
    # 20/08/2026 — Hh derivado da NOSSA base analítica no banco: soma dos
    # insumos de mão de obra (unidade H). A composição é "fornecimento e
    # instalação", mas o Hh somado é SÓ trabalho — serve pro esforço.
    # 🩸 18/10/2026 — era UM coeficiente (split hi-wall 12.000 BTU, 103247)
    # pra qualquer "un" da disciplina: o cassete 36.000 BTU do /exemplo saía
    # com metade do trabalho (4,667 Hh em vez de 9,505), e no acervo entravam na mesma
    # taxa ponto elétrico, termostato, difusor e condensadora. Agora a
    # composição sai do TIPO e do PORTE escritos na descrição (tabela abaixo);
    # sem os dois, o item fica fora da conta.
    # ⚰️ Incêndio ficou FORA de propósito: a base não tem composição limpa de
    # extintor com mão de obra (só abrigo de hidrante, 4,2 Hh — representaria
    # mal um extintor de parede). Sem representante honesto, sem coeficiente.
    'Ar-condicionado': {
        'equipe': 2,
        'un': _refs_ar_condicionado(),
    },
}


def _classe_unidade(unit):
    u = (unit or '').strip().lower()
    u = unicodedata.normalize('NFKD', u)
    u = ''.join(c for c in u if not unicodedata.combining(c))
    u = u.replace('²', '2')
    if u in ('m2', 'm.2', 'm^2'):
        return 'm2'
    if u in ('m', 'ml', 'mts'):
        return 'm'
    if u in ('un', 'und', 'unid', 'pc', 'pc.', 'peca', 'pca', 'cj', 'pt', 'ponto'):
        return 'un'
    return None


def _sem_acento(txt):
    """Minúsculo e sem acento — o filtro de descrição casa 'Lavatório' e 'lavatorio'."""
    t = unicodedata.normalize('NFKD', str(txt or '').lower())
    return ''.join(c for c in t if not unicodedata.combining(c))


def _ref_do_item(cfg_cls, descricao):
    """A composição que representa ESTE item, ou None (fica fora da conta)."""
    refs = cfg_cls if isinstance(cfg_cls, list) else [cfg_cls]
    desc = _sem_acento(descricao)
    for ref in refs:
        if len(ref) <= 3 or ref[3].search(desc):
            return ref
    return None


def _fmt_qty(q):
    txt = f"{q:,.1f}".replace(",", "§").replace(".", ",").replace("§", ".")
    return txt.rstrip("0").rstrip(",") or "0"


def esforco_por_fase(items, mapear_fase) -> dict:
    """Calcula esforço (Hh) e dias por fase a partir dos itens.

    mapear_fase: função (discipline:str) -> label da fase ou None — a MESMA
    usada pra criar as fases (evita mapa paralelo divergente).

    Retorna {label_fase: {esforco_hh, dias_corridos, origem:'calculada',
                          detalhe, refs:[...]}} só pras fases calculáveis.
    """
    # Σ quantidade por (fase, classe de unidade)
    # 🚨 07/09/2026 — E O SELO DE CADA PARCELA VAI JUNTO. A conta somava
    # `quantity` de qualquer item e devolvia `origem: 'calculada'`, palavra que
    # nesta casa significa SAIU DO DESENHO. Medido nos 10 cronogramas da base:
    # a mediana é 85% de quantidade LARANJA, e DOIS foram calculados com ZERO
    # item medido — carimbados "⚙ calculada das quantidades" do mesmo jeito.
    # É a regra dura nº1 no lugar mais visível do produto. Achado nº5/6.
    # Chave da soma: (classe de unidade, composição) — duas composições da
    # mesma unidade (pintura de teto e de parede) somam separadas.
    somas = {}
    medido = {}      # {label: {chave: quanto DAQUELA soma veio de item medido}}
    for it in items or []:
        label = mapear_fase((it.get('discipline') or '').strip().upper())
        if not label or label not in REFS_POR_FASE:
            continue
        cls = _classe_unidade(it.get('unit'))
        if not cls or cls not in REFS_POR_FASE[label]:
            continue
        _ref = _ref_do_item(REFS_POR_FASE[label][cls], it.get('description'))
        if _ref is None:
            continue
        try:
            qty = float(it.get('quantity') or 0)
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue
        chave = (cls, _ref[:3])
        somas.setdefault(label, {}).setdefault(chave, 0.0)
        somas[label][chave] += qty
        # 🪤 O selo pode vir como Enum (`.value`) ou string crua, dependendo de
        # quem chama — o motor passa objeto, o banco devolve texto.
        _cf = it.get('confidence')
        _cf = str(getattr(_cf, 'value', _cf) or '')
        medido.setdefault(label, {}).setdefault(chave, 0.0)
        if _cf == 'confirmado':
            medido[label][chave] += qty

    out = {}
    for label, por_cls in somas.items():
        cfg = REFS_POR_FASE[label]
        equipe = cfg.get('equipe', 2)
        hh_total = 0.0
        partes = []
        refs = []
        for (cls, (codigo, hh_unid, desc)), qty in sorted(por_cls.items()):
            hh = qty * hh_unid
            hh_total += hh
            unidade_label = {'m2': 'm²', 'm': 'm', 'un': 'un'}[cls]
            partes.append(f"{_fmt_qty(qty)} {unidade_label} × {str(hh_unid).replace('.', ',')} Hh "
                          f"(SINAPI {codigo} — {desc})")
            refs.append({'sinapi': codigo, 'hh_por_unidade': hh_unid,
                         'unidade': unidade_label, 'quantidade': round(qty, 2)})
        if hh_total <= 0:
            continue
        dias_uteis = max(1, math.ceil(hh_total / (equipe * HORAS_DIA)))
        dias_corridos = max(3, math.ceil(dias_uteis / DIAS_UTEIS_POR_CORRIDOS))
        # 🔑 O CRONOGRAMA HERDA O SELO DAS QUANTIDADES QUE USOU.
        # `calculada` continua significando o que sempre significou nesta casa:
        # saiu do desenho. Quando a conta é feita de estimativa, ela é honesta
        # sobre isso — e o número segue valendo, porque estimativa rotulada é
        # útil; estimativa com cara de medição é que não.
        _tot = sum(por_cls.values())
        _med = sum((medido.get(label) or {}).values())
        _pct_med = (100.0 * _med / _tot) if _tot else 0.0
        if _med <= 0:
            _origem = 'estimada'
        elif _pct_med >= 80.0:
            _origem = 'calculada'
        else:
            _origem = 'calculada-parcial'
        out[label] = {
            'esforco_hh': round(hh_total, 1),
            'dias_corridos': dias_corridos,
            'origem': _origem,
            'pct_medido': round(_pct_med, 1),
            'qtd_medida': round(_med, 2),
            'qtd_total': round(_tot, 2),
            'detalhe': (f"{' + '.join(partes)} = {_fmt_qty(hh_total)} Hh ÷ "
                        f"(equipe de {equipe} × {HORAS_DIA} h/dia) ≈ {dias_uteis} dias úteis "
                        f"(~{dias_corridos} corridos)"),
            'refs': refs,
            'equipe_premissa': equipe,
        }
    return out
