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
# Usa a service_role quando disponível (backend) — ela NÃO tem statement_timeout,
# então a busca SINAPI não é cancelada aos 3s do anon sob carga. Fix 2026-07-22:
# o matcher dispara ~8 RPCs concorrentes por projeto; sob saturação de CPU da
# instância Supabase, chamadas passavam de 3s → 500 → item ficava sem código SINAPI
# (confirmado nos logs: "canceling statement due to statement timeout"). Cai pro
# anon localmente. As RPCs (sinapi_candidates/search_sinapi) são SECURITY DEFINER
# read-only do catálogo público — service_role aqui não expõe nada.
SUPABASE_KEY = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
                or os.getenv("SUPABASE_ANON_KEY") or (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtxamFiendnYmZ1aXZ6bGNmdnZ1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzYwMDg5NzcsImV4cCI6MjA5MTU4NDk3N30.48xSenZlDV0LfD94ZxwGvX41Kf9Je2n-ouZpJrrCSKI"
))

# Similaridade mínima — mais baixa que TCPO porque SINAPI é mais descritivo
# (códigos longos com modelo/fabricante embutido, similaridade textual cai)
MIN_SIMILARITY = 0.15

# Confiança atribuída ao código que a IA conferiu. O texto puro não separa
# "spot de embutir redondo" (luminária) de "cuba de embutir redonda" (louça):
# o errado pontua 0.61 e o certo 0.57. Quem desempata é semântica, não trigrama —
# então quando a IA confere, a nota dela é que vale.
LLM_PICK_CONFIDENCE = 0.95


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
    ranked = sorted(results, key=lambda x: x.get('similarity', 0), reverse=True)
    # Capa o score exibido em 100%. O boost por spec (0.5 * matches) serve só
    # pra RANKEAR, não pra inflar a confiança — score de 133%/122% na planilha
    # detonava a credibilidade (matemática impossível pra similaridade).
    for _r in ranked:
        _r['similarity'] = max(0.0, min(1.0, _r.get('similarity', 0)))
    return ranked


def _rescore_honest(description: str, results: List[Dict]) -> List[Dict]:
    """Recalcula a confiança contra a descrição ORIGINAL do item.

    O search_sinapi pontua contra a query que ELE recebeu. Nos níveis de fallback
    essa query é uma palavra só, então "Piso porcelanato retificado 60x60" caía em
    "Piso" e casava com PISO DE BORRACHA CANELADO com nota 1.0 — 100% de confiança
    num código errado, que é justamente o que induz o orçamentista a copiar.
    Aqui a nota é sempre "quanto da descrição completa do item aparece nesta
    composição", sem os bônus de ranqueamento (eles passavam de 1.0 e viravam
    "100%" no corte).

    A ORDEM é preservada de propósito: quem ranqueia é o _rerank_by_specs (que
    entende amperagem/bitola). Esta função mexe só no número exibido.
    """
    if not results:
        return results
    cods = [r.get('codigo') for r in results if r.get('codigo')]
    if not cods:
        return results
    scored = _supabase_rpc("sinapi_rescore", {"p_query": description[:200], "p_codigos": cods})
    by_cod = {s.get('codigo'): (s.get('similarity') or 0) for s in (scored or []) if s.get('codigo')}
    if not by_cod:
        # RPC fora do ar: mantém o que veio em vez de inventar nota. Marca pra
        # quem consome saber que a confiança não passou pela conferência.
        print("[sinapi] rescore indisponível — confiança segue a do ranqueamento")
        for r in results:
            r['_rescore_failed'] = True
        return results
    for r in results:
        cod = r.get('codigo')
        if cod in by_cod:
            r['_similarity_rank'] = r.get('similarity')  # score de ranqueamento (com bônus)
            r['similarity'] = max(0.0, min(1.0, by_cod[cod]))
    return results


def _select(results: List[Dict], description: str, limit: int) -> List[Dict]:
    """Ranqueia (spec-aware) → repontua honesto → corta pelo mínimo."""
    results = _rerank_by_specs(results, description)
    results = _rescore_honest(description, results)
    return [r for r in results if r.get("similarity", 0) >= MIN_SIMILARITY][:limit]


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
    valid = _select(results, desc, limit)
    if valid:
        return valid

    # 2) Top 3 palavras-chave (com pré-tradução de termos coloquiais)
    q3 = _extract_keywords(desc, n=3)
    q3_translated = _apply_pre_translation(q3)
    if q3 and q3 != desc:
        results = _supabase_rpc("search_sinapi", {"p_query": q3_translated, "p_limit": limit * 8})
        valid = _select(results, desc, limit)
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
        valid = _select(results, desc, limit)
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
            valid = _select(results, desc, limit)
            if valid:
                for r in valid:
                    r["_match_level"] = "synonym"
                    r["_match_query"] = syn
                    r["_match_original_query"] = q1
                return valid

    return []


def candidates_for(description: str, limit: int = 20) -> List[Dict]:
    """Junta candidatos de VÁRIAS buscas — pra IA escolher depois.

    Motivo: nenhuma busca sozinha traz o certo. Medido em 17/07, posição do
    código certo entre as 10k composições:
      - por FRASE INTEIRA: porcelanato 2º e spot 2º (o plano B só trazia lixo),
        mas porta 52º e "pintura em forro de gesso" 338º — a base fala "TETO",
        não "forro", e trigrama não sabe que é a mesma coisa.
      - por PALAVRA-CHAVE: traz a família certa (todas as pinturas, todas as
        portas), mas escolhe mal dentro dela.
    Uma pega o que a outra perde, então usamos as duas e deixamos a escolha pra
    quem entende de semântica (pick_best_batch).

    Devolve até `limit` candidatos, sem repetir código, já com a nota honesta
    (contra a descrição completa) e ordenados por ela.
    """
    if not description or len(description.strip()) < 3:
        return []
    desc = description.strip()
    por_fonte: List[List[Dict]] = []

    def _fonte(rows: list, nivel: str):
        lote = []
        for r in (rows or []):
            if r.get("codigo"):
                r["_match_level"] = nivel
                lote.append(r)
        if lote:
            por_fonte.append(lote)

    # a) frase inteira (sem threshold — varre as 10k)
    _fonte(_supabase_rpc("sinapi_candidates", {"p_query": desc[:200], "p_limit": limit}), "full")
    # b) busca atual com a descrição completa (tem os bônus de ranqueamento)
    _fonte(_supabase_rpc("search_sinapi", {"p_query": desc[:200], "p_limit": limit}), "full")
    # c) palavras-chave — traz a família certa quando a frase inteira não acha
    q3 = _apply_pre_translation(_extract_keywords(desc, n=3))
    if q3:
        _fonte(_supabase_rpc("search_sinapi", {"p_query": q3, "p_limit": limit}), "simplified_3")
    q1 = _apply_pre_translation(_extract_keywords(desc, n=1))
    if q1 and q1 != q3:
        _fonte(_supabase_rpc("search_sinapi", {"p_query": q1, "p_limit": limit}), "simplified_1")
    if not por_fonte:
        return []

    # INTERCALA (1 de cada fonte por vez) em vez de juntar tudo e cortar pela nota.
    # Cortar pela nota parecia natural e destruía o recall: a nota honesta é
    # justamente o que NÃO sabe separar o certo ("spot" × cuba 0.61 > luminária
    # 0.57), então o corte descartava o bom candidato que uma das buscas achou.
    # Intercalando, toda busca coloca os melhores dela na mesa e a IA decide.
    escolhidos: Dict[str, Dict] = {}
    for pos in range(max(len(f) for f in por_fonte)):
        for fonte in por_fonte:
            if pos < len(fonte) and len(escolhidos) < limit:
                c = fonte[pos]
                escolhidos.setdefault(c["codigo"], c)
        if len(escolhidos) >= limit:
            break

    todos = _rerank_by_specs(list(escolhidos.values()), desc)
    return _rescore_honest(desc, todos)


_PICK_PROMPT = """Você é orçamentista sênior e conhece a base SINAPI (Caixa).

Pra CADA item de um quantitativo de obra, escolha entre os candidatos SINAPI qual
descreve O MESMO serviço/material. Os candidatos vieram de uma busca por TEXTO —
ela erra feio, porque casa palavra sem entender o que a coisa é. Exemplos reais:
"Spot LED de embutir redondo" casou com "CUBA DE EMBUTIR REDONDA EM LOUÇA" (é
luminária, não louça); "Piso porcelanato" casou com "PISO DE BORRACHA CANELADO".

REGRA DURA: na dúvida, responda null. Um código errado é MUITO pior que nenhum —
o orçamentista copia o código achando que é referência oficial e orça a coisa
errada. Só escolha quando for a MESMA coisa.

Pode escolher mesmo com diferença de acabamento/padrão (ex.: "porta de madeira
80x210 com batente" ≈ "KIT DE PORTA DE MADEIRA ... 80X210CM ... BATENTE,
FECHADURA"). NÃO escolha quando muda a natureza do serviço:
- material diferente (porcelanato × granito × borracha)
- serviço inverso (instalar × REMOVER/DEMOLIR)
- objeto diferente (luminária × cuba; porta × carga e descarga de porta)
- se o item é serviço de obra que o SINAPI não tem como composição, responda null

ITENS:
{items}

Responda SÓ um array JSON, um objeto por item, sem texto em volta:
[{{"i": 0, "codigo": "87263"}}, {{"i": 1, "codigo": null}}]"""


def _client():
    """Client Anthropic, ou None se não houver chave (matcher segue sem a IA)."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic
        return anthropic.Anthropic(api_key=api_key, timeout=120.0)
    except Exception:
        return None


def pick_best_batch(items: List[Dict], batch_size: int = 12,
                    job_id: Optional[str] = None) -> Dict[int, Optional[str]]:
    """A IA escolhe, entre os candidatos de cada item, o código SINAPI certo.

    O trigrama é bom pra JUNTAR candidatos e péssimo pra ESCOLHER — ele não sabe
    que spot é luz e cuba é pia. Aqui a busca continua fazendo a peneira grossa
    (recall) e a Haiku faz a escolha (precisão), que é o que separa "referência
    oficial" de chute com cara de oficial.

    items: [{'description': str, 'unit': str, 'candidates': [match, ...]}, ...]
    Retorna {índice_do_item: codigo_escolhido_ou_None}.
    Item sem candidato nem entra no prompt. Falha da IA → {} (o chamador cai
    no corte por nota honesta, nunca inventa).
    """
    client = _client()
    if not client:
        return {}
    alvos = [(i, it) for i, it in enumerate(items) if (it.get('candidates') or [])]
    if not alvos:
        return {}

    escolhas: Dict[int, Optional[str]] = {}
    for ini in range(0, len(alvos), batch_size):
        lote = alvos[ini:ini + batch_size]
        linhas = []
        for i, it in lote:
            cands = "\n".join(
                f'     - {c.get("codigo")}: {(c.get("descricao") or "")[:110]} [un: {c.get("unidade") or "?"}]'
                for c in it['candidates']
            )
            linhas.append(
                f'  i={i} | ITEM: {(it.get("description") or "")[:110]} '
                f'[un: {it.get("unit") or "?"}]\n     CANDIDATOS:\n{cands}')
        try:
            from llm_retry import call_with_retry
            resp = call_with_retry(
                client, tag="sinapi_pick", job_id=job_id, max_retries=3,
                model="claude-haiku-4-5-20251001", max_tokens=1500,
                messages=[{"role": "user",
                           "content": _PICK_PROMPT.format(items="\n".join(linhas))}],
            )
            txt = resp.content[0].text.strip() if resp.content else ""
            import re as _re
            m = _re.search(r"\[[\s\S]*\]", txt)
            if not m:
                print(f"[sinapi-pick] sem JSON na resposta: {txt[:120]}")
                continue
            for e in json.loads(m.group(0)):
                idx = e.get("i")
                cod = e.get("codigo")
                if not isinstance(idx, int):
                    continue
                cod = str(cod).strip() if cod else None
                # Só aceita código que estava entre os candidatos DAQUELE item —
                # blinda contra a IA inventar código que não existe na base.
                validos = {c.get("codigo") for c in (items[idx].get('candidates') or [])}
                escolhas[idx] = cod if cod in validos else None
        except Exception as ex:
            print(f"[sinapi-pick] lote falhou (segue sem IA): {ex}")
    return escolhas


def apply_llm_pick(items: List[Dict], job_id: Optional[str] = None) -> int:
    """Aplica a escolha da IA in-place: põe o código escolhido em 1º e marca
    `_llm_picked`. Devolve quantos itens a IA confirmou."""
    escolhas = pick_best_batch(items, job_id=job_id)
    n = 0
    for idx, cod in escolhas.items():
        cands = items[idx].get('candidates') or []
        if not cod:
            for c in cands:
                c['_llm_rejected'] = True
            continue
        for c in cands:
            if c.get('codigo') == cod:
                c['_llm_picked'] = True
                c['_similarity_texto'] = c.get('similarity')
                c['similarity'] = LLM_PICK_CONFIDENCE
                cands.remove(c)
                cands.insert(0, c)
                n += 1
                break
    return n


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
