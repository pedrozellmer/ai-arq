# -*- coding: utf-8 -*-
"""Matcher de itens quantitativos com composições TCPO BIM.

Para cada BudgetItem, consulta a RPC `search_tcpo` no Supabase e retorna
os top matches (por similaridade). Também busca insumos da composição
pra preencher a aba de Memória Técnica.

Uso:
    from tcpo_matcher import match_item, get_insumos
    matches = match_item("Luminária LED 60x60")
    # [{'id': 'uuid', 'codigo_bim': '3R 27 52', 'descricao': '...',
    #   'unidade': 'un', 'sistema': 'Sistemas Elétricos',
    #   'similarity': 0.77}, ...]
"""
import json
import os
import urllib.request
from typing import List, Dict, Optional


SUPABASE_URL = os.getenv("SUPABASE_URL", "https://kqjabzwgbfuivzlcfvvu.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY") or (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtxamFiendnYmZ1aXZ6bGNmdnZ1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzYwMDg5NzcsImV4cCI6MjA5MTU4NDk3N30.48xSenZlDV0LfD94ZxwGvX41Kf9Je2n-ouZpJrrCSKI"
)

# Similaridade mínima pra considerar match válido (0.0-1.0)
MIN_SIMILARITY = 0.2


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
        print(f"  [tcpo_matcher] RPC {fname} erro: {e}")
        return []


def match_item(description: str, limit: int = 3) -> List[Dict]:
    """Busca composições TCPO que matcham a descrição do item.

    Retorna lista ordenada por similaridade desc, filtrada por MIN_SIMILARITY.
    """
    if not description or len(description.strip()) < 3:
        return []

    results = _supabase_rpc("search_tcpo", {
        "p_query": description.strip()[:200],
        "p_limit": limit,
    })

    # Filtra abaixo do threshold
    return [r for r in results if r.get("similarity", 0) >= MIN_SIMILARITY]


def get_insumos(composicao_id: str) -> List[Dict]:
    """Retorna a lista de insumos (materiais, mão de obra, equipamentos) de
    uma composição TCPO.
    """
    if not composicao_id:
        return []
    url = (
        f"{SUPABASE_URL}/rest/v1/tcpo_insumos"
        f"?composicao_id=eq.{composicao_id}"
        "&select=codigo_insumo,descricao,unidade,consumo,tipo"
        "&order=tipo.asc,descricao.asc"
    )
    req = urllib.request.Request(url, method="GET")
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    req.add_header("Accept", "application/json")
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  [tcpo_matcher] get_insumos erro: {e}")
        return []


def match_items_batch(items: List) -> Dict[str, List[Dict]]:
    """Faz matching de múltiplos items (em paralelo no futuro).

    Args:
        items: lista de objetos com atributo .description (BudgetItem) ou
               dicts com chave 'description'.

    Returns:
        dict {item_id: [matches]} onde item_id é item_num ou index.
    """
    out = {}
    for i, item in enumerate(items):
        desc = getattr(item, "description", None) or item.get("description", "")
        key = getattr(item, "item_num", None) or item.get("item_num", str(i))
        matches = match_item(desc, limit=3)
        # Enriquece o 1º match com insumos (só o melhor pra não lotar)
        if matches:
            matches[0]["insumos"] = get_insumos(matches[0]["id"])
        out[key] = matches
    return out


if __name__ == "__main__":
    # Teste rápido
    queries = [
        "Luminária LED 60x60",
        "Piso vinílico",
        "Porta de madeira 80x210",
        "Pintura látex PVA",
        "Forro de gesso acartonado",
    ]
    for q in queries:
        print(f"\n=== {q} ===")
        for r in match_item(q, limit=3):
            print(f"  [{r['similarity']:.2f}] {r['codigo_bim']} | "
                  f"{r['unidade']} | {r['descricao'][:70]}")
