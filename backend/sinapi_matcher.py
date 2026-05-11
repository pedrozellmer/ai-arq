# -*- coding: utf-8 -*-
"""Matcher de itens quantitativos com composições SINAPI (Caixa).

Análogo ao tcpo_matcher mas consulta a base SINAPI (10K composições).
Pra cada BudgetItem, retorna os top matches da RPC `search_sinapi`.

Uso:
    from sinapi_matcher import match_item as match_sinapi
    matches = match_sinapi("Lavatório com ponto hidráulico")
    # [{'codigo': '86879', 'descricao': '...', 'unidade': 'UN',
    #   'familia_id': 77, 'similarity': 0.75}, ...]
"""
import json
import os
import urllib.request
from typing import List, Dict, Optional


SUPABASE_URL = os.getenv("SUPABASE_URL", "https://kqjabzwgbfuivzlcfvvu.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY") or (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtxamFiendnYmZ1aXZ6bGNmdnZ1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzYwMDg5NzcsImV4cCI6MjA5MTU4NDk3N30.48xSenZlDV0LfD94ZxwGvX41Kf9Je2n-ouZpJrrCSKI"
)

# Similaridade mínima — mais baixa que TCPO porque SINAPI é mais descritivo
# (códigos longos com modelo/fabricante embutido, similaridade textual cai)
MIN_SIMILARITY = 0.15


def _supabase_rpc(fname: str, params: dict) -> list:
    """Chama uma RPC do Supabase (POST em /rest/v1/rpc/<fname>)."""
    url = f"{SUPABASE_URL}/rest/v1/rpc/{fname}"
    body = json.dumps(params).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    req.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  [sinapi_matcher] RPC {fname} erro: {e}")
        return []


# Termos genéricos que NÃO devem ser usados como query principal sozinhos
# (resultam em matches imprecisos — "Ponto" → "Tratamento de ralo" SINAPI 106110)
_GENERIC_TERMS = {
    'ponto', 'sistema', 'instalação', 'instalacao', 'fornecimento',
    'aplicação', 'aplicacao', 'execução', 'execucao', 'serviço', 'servico',
    'conjunto', 'kit', 'unidade', 'peça', 'peca', 'item', 'material',
}


def _extract_bitola(description: str) -> str:
    """Detecta bitola/dimensão de TUBO/CABO/ELETRODUTO/DISJUNTOR na descrição.

    Bitola SÓ faz sentido pra tubulação, cabo elétrico, eletroduto, disjuntor.
    Pra outros itens (escada com 30cm de pisante, p. ex.), "30cm" NÃO é bitola
    e anexar isso na query polui o match SINAPI.

    Retorna string normalizada (32MM, 2.5MM2, 10A) só se a descrição contém
    palavra de contexto adequado.
    """
    import re
    desc_low = description.lower()

    # ── Disjuntor → amperagem (10A, 16A, 20A, 25A, 32A...) ──
    # SINAPI tem códigos diferentes por amperagem; é a "bitola" do disjuntor.
    disjuntor_context = any(t in desc_low for t in [
        'disjuntor', 'dr', 'dps', 'idr', 'minidisjuntor'
    ])
    if disjuntor_context:
        m = re.search(r'\b(\d+)\s*a\b', description, re.I)
        if m:
            return f'{m.group(1)}A'

    # Só extrai bitola dimensional se há contexto de tubo/cabo/eletroduto
    bitola_context = any(t in desc_low for t in [
        'tubulação', 'tubulacao', 'tubo', 'cabo', 'fio',
        'eletroduto', 'ramal', 'cabeamento'
    ])
    if not bitola_context:
        return ''

    # Bitola elétrica primeiro (mais específica): "2,5mm²", "4mm²", "6mm²"
    m = re.search(r'(\d+(?:,\d+)?)\s*mm[²2]', description)
    if m:
        return f'{m.group(1).replace(",", ".")}MM2'
    # Bitola hidráulica: 25mm, 32mm, 50mm, 100mm
    m = re.search(r'\b(\d+)\s*mm\b', description, re.I)
    if m:
        return f'{m.group(1)}MM'
    # Polegadas: 1/2", 3/4"
    m = re.search(r'(\d+/\d+)\s*["\']', description)
    if m:
        return f'{m.group(1)}"'
    return ''


# Tradução PRÉ-busca: termo coloquial → termo SINAPI oficial
# Aplicado na keyword query antes da RPC (não como fallback)
_PRE_TRANSLATE = {
    'tubulação':   'tubo pvc soldável',
    'tubulacao':   'tubo pvc soldável',
    'cabo':        'cabo de cobre flexível isolado',
    'cabeamento':  'cabo de cobre flexível isolado',
    'eletroduto':  'eletroduto flexível corrugado',
    'luz':         'luminária led',
    'iluminação':  'luminária led',
    'iluminacao':  'luminária led',
}


def _apply_pre_translation(query: str) -> str:
    """Substitui termos coloquiais por equivalentes SINAPI oficiais.

    Ex: 'Tubulação 32MM' → 'tubo pvc soldável 32MM'
    """
    import re
    q = query
    for coloquial, sinapi in _PRE_TRANSLATE.items():
        # Substitui só word boundary (não pega "tubulação" dentro de outras palavras)
        pattern = r'\b' + re.escape(coloquial) + r'\b'
        q = re.sub(pattern, sinapi, q, flags=re.I)
    return q.strip()


def _extract_keywords(description: str, n: int = 3) -> str:
    """Extrai N palavras-chave essenciais (filtra conectores e códigos).

    - Ignora termos genéricos ("Ponto", "Sistema") como primeira palavra
    - Inclui bitola/dimensão (32mm, 1/2") se detectada — melhora match preciso

    Ex: 'Tubulação água fria 32mm' → n=1: 'Tubulação 32MM'
        'Lavatório LV com ponto hidráulico' → n=1: 'Lavatório'
        'Ponto de tomada 2P+T 10A' → n=1: 'tomada' (pula "Ponto")
    """
    import re
    text = description.strip()
    text = re.sub(r'\([^)]*\)', '', text)
    # Códigos elétricos/hidráulicos a remover
    text = re.sub(r'\b(LV|AF\d?|AQ\d?|ES\d?|AP|VS|CH|TQ|LM\d+|QD|PVC|CPVC|2P\+T)\b', '', text, flags=re.I)
    # Conectores
    text = re.sub(r'\b(com|para|de|em|e|ou|por|do|da|no|na|um|uma|sobre|entre|sem|tipo|conforme|qual)\b', ' ', text, flags=re.I)
    text = ' '.join(text.split())

    # Filtra palavras: 3+ chars, não-numérica
    words = []
    for w in text.split():
        wl = w.lower().strip('.,;:!?')
        if len(wl) >= 3 and not wl.replace(',', '').replace('.', '').isdigit():
            words.append(w)

    # PULA termos genéricos no início — usa a próxima palavra significativa
    # Ex: "Ponto de luz" → keywords vira ["Ponto", "luz"]; pula "Ponto", retorna "luz"
    while words and words[0].lower().strip('.,;:!?') in _GENERIC_TERMS:
        words.pop(0)

    result = ' '.join(words[:n]).strip()

    # Se tem bitola na descrição, anexa pra busca SINAPI mais precisa
    bitola = _extract_bitola(description)
    if bitola and bitola not in result.upper():
        result = f'{result} {bitola}'.strip()

    return result


# Dicionário de sinônimos PT-BR pra termos de construção civil
# Mapeamento: termo coloquial → termo usado no SINAPI/Caixa
# Quando query falha com palavra original, tenta com cada sinônimo até achar.
_SYNONYMS_BR = {
    # ─── Hidráulica / Esgoto ──────────────────────
    'cisterna':       ['reservatório', 'reservatório de água'],
    'tubulação':      ['tubo pvc soldável', 'tubo'],
    'tubulacao':      ['tubo pvc soldável', 'tubo'],
    'lavanderia':     ['tanque', 'área de serviço'],
    'lavatório':      ['lavatório de louça', 'pia de banheiro'],
    'lavabo':         ['lavatório', 'pia'],
    'banheira':       ['banheira de hidromassagem', 'cuba'],
    'ducha':          ['chuveiro'],
    'esgoto':         ['tubo pvc esgoto'],
    'pluvial':        ['águas pluviais'],
    # ─── Cozinha / Áreas molhadas ─────────────────
    'cooktop':        ['fogão'],
    'gourmet':        ['churrasqueira', 'área de serviço'],
    # ─── Marcenaria / Mobília ─────────────────────
    'closet':         ['guarda-roupa', 'armário'],
    'redário':        ['rede'],
    'redario':        ['rede'],
    'pufe':           ['banco'],
    'painel':         ['marcenaria', 'tampo'],
    # ─── Iluminação ───────────────────────────────
    'spot':           ['luminária', 'ponto de luz'],
    'plafonier':      ['luminária'],
    'plafom':         ['luminária'],
    'arandela':       ['luminária'],
    'lustre':         ['luminária'],
    'pendente':       ['luminária pendente'],
    # ─── Elétrica ─────────────────────────────────
    'cftv':           ['câmera de segurança', 'cftv'],
    'alarme':         ['sistema de alarme'],
    'antena':         ['antena televisão'],
    'tomadas':        ['tomada'],
    'cabo':           ['cabo de cobre flexível', 'cabo cobre isolado'],
    'cabos':          ['cabo de cobre flexível'],
    'cabeamento':     ['cabo de cobre flexível'],
    'eletroduto':     ['eletroduto flexível corrugado pvc', 'eletroduto pvc'],
    'eletrodutos':    ['eletroduto flexível corrugado pvc'],
    'luz':            ['luminária led', 'luminária'],
    'fio':            ['cabo de cobre flexível'],
    'disjuntor':      ['disjuntor tipo din'],
    # ─── Esquadrias / Ferragens ───────────────────
    'maçaneta':       ['ferragens'],
    'dobradiça':      ['ferragens'],
    'corrimão':       ['corrimão metálico', 'guarda-corpo'],
    # ─── Forros / Acabamentos ─────────────────────
    'sancas':         ['rebaixo', 'forro de gesso'],
    'sanca':          ['rebaixo', 'forro de gesso'],
    'amenities':      ['guarnição', 'acabamento'],
    'rasante':        ['raspagem'],
    # ─── Serviços preliminares ────────────────────
    'administração':  ['encarregado geral', 'mestre de obras'],
    'fee':            ['encarregado geral'],
    'mobilização':    ['canteiro', 'instalação de canteiro'],
    'mob':            ['canteiro'],
    'as-built':       ['as built'],
    # ─── Incêndio ─────────────────────────────────
    'sprinkler':      ['sprinkler', 'sistema sprinkler'],
    'hidrante':       ['hidrante de incêndio'],
    'extintor':       ['extintor incêndio'],
    # ─── Estrutura ────────────────────────────────
    'pilar':          ['pilar concreto'],
    'viga':           ['viga concreto'],
    'laje':           ['laje concreto'],
    # ─── Ar-condicionado ──────────────────────────
    'split':          ['ar condicionado split'],
    'vrf':            ['ar condicionado vrf'],
    'fancoil':        ['fan coil'],
}


def _rerank_by_specs(results: List[Dict], description: str) -> List[Dict]:
    """Rerank: prioriza matches cuja descrição SINAPI contém a mesma spec
    técnica (amperagem, bitola mm/mm², polegadas) que a descrição original.

    Sem isso, "Disjuntor 10A" matcha "Disjuntor 50A" com similaridade textual
    alta — mas é o item errado pra comprar.

    target_patterns são regex que casam variações da spec (com/sem espaço,
    vírgula/ponto, MM/mm²) — porque SINAPI usa "10 A", "1,5 MM²" e nós escrevemos
    "10A", "1.5mm²".
    """
    import re
    if not results:
        return results

    desc_low = description.lower()
    # Cada pattern é uma regex que casa o número COM separador opcional na unidade
    target_patterns: List[str] = []

    # Amperagem (10A, 16A, 25A...) — só se contexto disjuntor/DR/DPS.
    # findall pra suportar queries multi-spec ("Disjuntor 10A / 16A / 20A").
    if any(t in desc_low for t in ['disjuntor', 'dr', 'dps', 'idr']):
        for n in re.findall(r'\b(\d+)\s*a\b', description, re.I):
            # Casa "10A", "10 A", "DE 10A", mas NÃO "100A" nem "210A"
            target_patterns.append(rf'(?<!\d){re.escape(n)}\s*A\b')

    # mm² (1,5mm², 2,5mm², 4mm²) — bitola de cabo elétrico.
    # findall pra suportar "Cabo 4-6mm²" → matcha 4 OU 6.
    for v in re.findall(r'(\d+(?:[,.]\d+)?)\s*mm[²2]', description):
        v_norm = v.replace('.', ',')  # SINAPI usa vírgula: "1,5 MM²"
        target_patterns.append(rf'(?<!\d){re.escape(v_norm)}\s*MM[²2]')

    # Captura também ranges como "Cabo 4-6mm²" — gera matchers pros 2 valores.
    range_match = re.search(r'(\d+(?:[,.]\d+)?)\s*-\s*(\d+(?:[,.]\d+)?)\s*mm[²2]', description)
    if range_match:
        for v in (range_match.group(1), range_match.group(2)):
            v_norm = v.replace('.', ',')
            pat = rf'(?<!\d){re.escape(v_norm)}\s*MM[²2]'
            if pat not in target_patterns:
                target_patterns.append(pat)

    # Bitola hidráulica (25mm, 32mm, 50mm) — só se contexto de tubo/cabo.
    if any(t in desc_low for t in ['tubo', 'tubulação', 'eletroduto']):
        for n in re.findall(r'\b(\d+)\s*mm\b', description, re.I):
            # Casa "32MM", "DE 32 MM", mas NÃO "320MM"
            target_patterns.append(rf'(?<!\d){re.escape(n)}\s*MM\b(?!²|2)')

    # Penaliza códigos de remoção/demolição quando query é sobre obra nova.
    # Ex.: "Forro de gesso liso" matchava 97641 "REMOÇÃO DE FORRO DE GESSO".
    is_demolition_query = any(t in desc_low for t in [
        'demolição', 'demolicao', 'remoção', 'remocao', 'retirada',
        'desmontagem', 'demolir', 'remover', 'retirar'
    ])
    _DEMOLITION_KEYWORDS = ('REMOÇÃO', 'REMOCAO', 'DEMOLIÇÃO', 'DEMOLICAO',
                            'RETIRADA', 'DESMONTAGEM', 'RASPAGEM')

    for r in results:
        desc_sinapi = (r.get('descricao') or '').upper()

        # Boost por spec
        if target_patterns:
            matches_spec = sum(
                1 for pat in target_patterns
                if re.search(pat, desc_sinapi, re.I)
            )
            if matches_spec:
                r['similarity'] = r.get('similarity', 0) + 0.5 * matches_spec
                r['_spec_boost'] = matches_spec

        # Penalidade: SINAPI é de remoção mas query NÃO é
        if not is_demolition_query and any(k in desc_sinapi for k in _DEMOLITION_KEYWORDS):
            r['similarity'] = r.get('similarity', 0) - 0.5
            r['_demolition_penalty'] = True

    # Reordena por similaridade ajustada
    return sorted(results, key=lambda x: x.get('similarity', 0), reverse=True)


def match_item(description: str, limit: int = 3) -> List[Dict]:
    """Busca composições SINAPI que matcham a descrição do item.

    Estratégia progressiva de fallback (4 níveis):
    1) Query completa (descrição original)
    2) Top 3 palavras-chave (sem conectores/códigos)
    3) Top 1 palavra-chave (substantivo principal)
    4) Sinônimo do termo principal (dicionário PT-BR)

    Marca matches via fallback com flag _match_level.
    Aplica rerank por spec técnica (amperagem/bitola) em todos os níveis.
    """
    if not description or len(description.strip()) < 3:
        return []

    desc = description.strip()

    # 1) Query completa
    # Pede mais resultados (limit*3) pra ter o que rerankear, mas devolve só `limit`.
    results = _supabase_rpc("search_sinapi", {"p_query": desc[:200], "p_limit": limit * 8})
    results = _rerank_by_specs(results, desc)
    valid = [r for r in results if r.get("similarity", 0) >= MIN_SIMILARITY][:limit]
    if valid:
        return valid

    # 2) Top 3 palavras-chave (com pré-tradução de termos coloquiais)
    q3 = _extract_keywords(desc, n=3)
    q3_translated = _apply_pre_translation(q3)
    if q3 and q3 != desc:
        results = _supabase_rpc("search_sinapi", {"p_query": q3_translated, "p_limit": limit * 8})
        results = _rerank_by_specs(results, desc)
        valid = [r for r in results if r.get("similarity", 0) >= MIN_SIMILARITY][:limit]
        if valid:
            for r in valid:
                r["_match_level"] = "simplified_3"
                r["_match_query"] = q3_translated
            return valid

    # 3) Top 1 palavra-chave (com pré-tradução)
    q1 = _extract_keywords(desc, n=1)
    q1_translated = _apply_pre_translation(q1)
    if q1 and q1 != desc and q1 != q3:
        results = _supabase_rpc("search_sinapi", {"p_query": q1_translated, "p_limit": limit * 8})
        results = _rerank_by_specs(results, desc)
        valid = [r for r in results if r.get("similarity", 0) >= MIN_SIMILARITY][:limit]
        if valid:
            for r in valid:
                r["_match_level"] = "simplified_1"
                r["_match_query"] = q1_translated
            return valid

    # 4) Fallback de sinônimo (último recurso) — pra termos onde nosso vocabulário
    # difere do SINAPI (ex: "cisterna" → SINAPI usa "reservatório").
    if q1:
        synonyms = _SYNONYMS_BR.get(q1.lower(), [])
        for syn in synonyms:
            results = _supabase_rpc("search_sinapi", {"p_query": syn, "p_limit": limit * 8})
            results = _rerank_by_specs(results, desc)
            valid = [r for r in results if r.get("similarity", 0) >= MIN_SIMILARITY][:limit]
            if valid:
                for r in valid:
                    r["_match_level"] = "synonym"
                    r["_match_query"] = syn
                    r["_match_original_query"] = q1
                return valid

    return []


def get_insumos(composicao_codigo: str) -> List[Dict]:
    """Retorna insumos (analítico) de uma composição SINAPI.

    Args:
        composicao_codigo: código SINAPI (ex.: '87905')
    """
    if not composicao_codigo:
        return []
    url = (
        f"{SUPABASE_URL}/rest/v1/sinapi_insumos"
        f"?composicao_codigo=eq.{composicao_codigo}"
        "&select=codigo_item,descricao,unidade,coeficiente,tipo_item"
        "&order=tipo_item.asc,descricao.asc"
        "&limit=50"
    )
    req = urllib.request.Request(url, method="GET")
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    req.add_header("Accept", "application/json")
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  [sinapi_matcher] get_insumos erro: {e}")
        return []


if __name__ == "__main__":
    # Teste rápido
    queries = [
        "Lavatório com ponto hidráulico",
        "Tubulação água fria 32mm",
        "Cobertura telha cerâmica",
        "Quadro de distribuição elétrica",
        "Porta de madeira 80x210",
        "Pintura látex PVA",
    ]
    for q in queries:
        print(f"\n=== {q} ===")
        for r in match_item(q, limit=3):
            print(f"  [{r['similarity']:.2f}] {r['codigo']} | "
                  f"{r['unidade']} | {r['descricao'][:80]}")
