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

# Referências por LABEL de fase (pós-mapeamento do SEQUENCIAMENTO).
# Cada fase pode ter uma referência por classe de unidade (m2 / m / un).
# (codigo SINAPI, Hh por unidade, descricao curta)
REFS_POR_FASE = {
    'Alvenaria': {
        'equipe': 3,
        'm2': ('103368', 1.290, 'alvenaria de vedação bloco cerâmico 14 cm'),
    },
    'Fechamentos / alvenaria': {
        'equipe': 3,
        'm2': ('103368', 1.290, 'alvenaria de vedação bloco cerâmico 14 cm'),
    },
    'Revestimentos': {
        'equipe': 3,
        'm2': ('87794', 0.818, 'emboço/massa única em argamassa'),
    },
    'Pisos': {
        'equipe': 2,
        'm2': ('87263', 0.688, 'porcelanato 60×60 assentado'),
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
        'un': ('90822', 2.876, 'porta de madeira 80×210 completa',
               re.compile(r'\bportas?\b')),
    },
    'Demolição': {
        'equipe': 2,
        'm2': ('97638', 0.375, 'remoção de drywall / alvenaria de vedação',
               re.compile(r'drywall|divisori|alvenaria|parede')),
    },
    # 20/08/2026 — Hh derivado da NOSSA base analítica no banco:
    # soma dos insumos de mão de obra (unidade H) da composição 103247
    # (split hi-wall inverter 12.000 BTU, o porte mais comum). A composição é
    # "fornecimento e instalação", mas o Hh somado é SÓ trabalho — serve pro
    # esforço de cronograma. Representante conservador (portes maiores chegam
    # a 9,15 Hh).
    # ⚰️ Incêndio ficou FORA de propósito: a base não tem composição limpa de
    # extintor com mão de obra (só abrigo de hidrante, 4,2 Hh — representaria
    # mal um extintor de parede). Sem representante honesto, sem coeficiente.
    'Ar-condicionado': {
        'equipe': 2,
        'un': ('103247', 4.667, 'split hi-wall 12.000 BTU — instalação'),
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
    somas = {}
    medido = {}      # {label: {cls: quanto DAQUELA soma veio de item medido}}
    for it in items or []:
        label = mapear_fase((it.get('discipline') or '').strip().upper())
        if not label or label not in REFS_POR_FASE:
            continue
        cls = _classe_unidade(it.get('unit'))
        if not cls or cls not in REFS_POR_FASE[label]:
            continue
        _ref = REFS_POR_FASE[label][cls]
        if len(_ref) > 3 and not _ref[3].search(_sem_acento(it.get('description'))):
            continue
        try:
            qty = float(it.get('quantity') or 0)
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            continue
        somas.setdefault(label, {}).setdefault(cls, 0.0)
        somas[label][cls] += qty
        # 🪤 O selo pode vir como Enum (`.value`) ou string crua, dependendo de
        # quem chama — o motor passa objeto, o banco devolve texto.
        _cf = it.get('confidence')
        _cf = str(getattr(_cf, 'value', _cf) or '')
        medido.setdefault(label, {}).setdefault(cls, 0.0)
        if _cf == 'confirmado':
            medido[label][cls] += qty

    out = {}
    for label, por_cls in somas.items():
        cfg = REFS_POR_FASE[label]
        equipe = cfg.get('equipe', 2)
        hh_total = 0.0
        partes = []
        refs = []
        for cls, qty in sorted(por_cls.items()):
            codigo, hh_unid, desc = cfg[cls][:3]
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
