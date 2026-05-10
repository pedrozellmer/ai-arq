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


def _extract_keywords(description: str, n: int = 3) -> str:
    """Extrai N palavras-chave essenciais (filtra conectores e códigos).

    Ex: 'Lavatório LV com ponto hidráulico e ramal de água fria 25mm'
        → n=1: 'Lavatório'
        → n=3: 'Lavatório ponto hidráulico'
    """
    import re
    text = description.strip()
    # Limpa parênteses e códigos curtos (LV, AF1, AQ, ES, VS, etc)
    text = re.sub(r'\([^)]*\)', '', text)
    text = re.sub(r'\b(LV|AF\d?|AQ\d?|ES\d?|AP|VS|CH|TQ|LM\d+|QD|PVC|CPVC)\b', '', text, flags=re.I)
    # Remove conectores
    text = re.sub(r'\b(com|para|de|em|e|ou|por|do|da|no|na|um|uma|sobre|entre|sem|tipo|conforme)\b', ' ', text, flags=re.I)
    text = ' '.join(text.split())
    # Pega N primeiras palavras com 3+ chars
    words = [w for w in text.split() if len(w) >= 3 and not w.replace(',','').replace('.','').isdigit()]
    return ' '.join(words[:n]).strip()


def match_item(description: str, limit: int = 3) -> List[Dict]:
    """Busca composições SINAPI que matcham a descrição do item.

    Estratégia progressiva de fallback:
    1) Query completa (descrição original)
    2) Top 3 palavras-chave (sem conectores/códigos)
    3) Top 1 palavra-chave (substantivo principal)

    Cada nível mais ampla. Marca matches via fallback com flag.
    """
    if not description or len(description.strip()) < 3:
        return []

    desc = description.strip()

    # 1) Query completa
    results = _supabase_rpc("search_sinapi", {"p_query": desc[:200], "p_limit": limit})
    valid = [r for r in results if r.get("similarity", 0) >= MIN_SIMILARITY]
    if valid:
        return valid

    # 2) Top 3 palavras-chave
    q3 = _extract_keywords(desc, n=3)
    if q3 and q3 != desc:
        results = _supabase_rpc("search_sinapi", {"p_query": q3, "p_limit": limit})
        valid = [r for r in results if r.get("similarity", 0) >= MIN_SIMILARITY]
        if valid:
            for r in valid:
                r["_match_level"] = "simplified_3"
                r["_match_query"] = q3
            return valid

    # 3) Top 1 palavra-chave (substantivo principal)
    q1 = _extract_keywords(desc, n=1)
    if q1 and q1 != desc and q1 != q3:
        results = _supabase_rpc("search_sinapi", {"p_query": q1, "p_limit": limit})
        valid = [r for r in results if r.get("similarity", 0) >= MIN_SIMILARITY]
        if valid:
            for r in valid:
                r["_match_level"] = "simplified_1"
                r["_match_query"] = q1
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
