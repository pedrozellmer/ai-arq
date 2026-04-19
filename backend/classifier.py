# -*- coding: utf-8 -*-
"""Classificador LLM — mapeia descrição livre de item de orçamento pra
uma família do catálogo hierárquico (`catalog_familia`), extraindo os
atributos folha (cor, PD, marca, dimensão, etc.) num passo único.

Regra do produto:
- Nunca perde informação: atributos folha ficam preservados em
  `density_ingest_raw.attributes` (jsonb) pra caderno de compra.
- Calibração estatística agrega no nível FAMÍLIA (pintura acrílica
  agrupa todas as cores; forro gesso agrupa todos os PDs).
- Alertas cascateiam folha → família → grupo → capítulo.
"""
import json
import os
import re
import time
import urllib.request
from typing import Optional


SUPABASE_URL = "https://kqjabzwgbfuivzlcfvvu.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtxamFiendnYmZ1aXZ6bGNmdnZ1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzYwMDg5NzcsImV4cCI6MjA5MTU4NDk3N30.48xSenZlDV0LfD94ZxwGvX41Kf9Je2n-ouZpJrrCSKI"

_families_cache = {"data": None, "timestamp": 0}
_CACHE_TTL = 600  # 10 min


def _supabase_select(table: str, query: str) -> list[dict]:
    try:
        url = f"{SUPABASE_URL}/rest/v1/{table}?{query}"
        req = urllib.request.Request(url, method="GET")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        req.add_header("Accept", "application/json")
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[classifier] Supabase select error: {e}")
        return []


def load_families() -> list[dict]:
    """Carrega catálogo de famílias com contexto hierárquico (grupo + capítulo).
    Cached 10 min."""
    now = time.time()
    if _families_cache["data"] is not None and (now - _families_cache["timestamp"]) < _CACHE_TTL:
        return _families_cache["data"]

    # Pega tudo de uma vez com joins via select
    rows = _supabase_select(
        "catalog_familia",
        "select=id,code,name,typical_unit,keywords,grupo:grupo_id(id,code,name,capitulo:capitulo_id(id,code,name))",
    )
    # Denormaliza pra facilitar o prompt
    out = []
    for r in rows:
        grupo = r.get("grupo") or {}
        capitulo = (grupo.get("capitulo") or {}) if isinstance(grupo, dict) else {}
        out.append({
            "id": r.get("id"),
            "code": r.get("code"),
            "name": r.get("name"),
            "typical_unit": r.get("typical_unit"),
            "keywords": r.get("keywords") or [],
            "grupo_id": grupo.get("id") if isinstance(grupo, dict) else None,
            "grupo_code": grupo.get("code") if isinstance(grupo, dict) else None,
            "grupo_name": grupo.get("name") if isinstance(grupo, dict) else None,
            "capitulo_id": capitulo.get("id"),
            "capitulo_code": capitulo.get("code"),
            "capitulo_name": capitulo.get("name"),
        })
    _families_cache["data"] = out
    _families_cache["timestamp"] = now
    return out


def invalidate_cache() -> None:
    _families_cache["data"] = None
    _families_cache["timestamp"] = 0


def _build_catalog_text(families: list[dict]) -> str:
    """Serializa o catálogo em formato compacto pro prompt."""
    # Agrupa por capítulo → grupo → família pra o LLM "ver" a árvore
    by_cap: dict = {}
    for f in families:
        cap = f.get("capitulo_code") or "—"
        grp = f.get("grupo_code") or "—"
        by_cap.setdefault(cap, {}).setdefault(grp, []).append(f)
    lines = []
    for cap_code, grupos in sorted(by_cap.items()):
        cap_name = next((f["capitulo_name"] for grp in grupos.values() for f in grp), cap_code)
        lines.append(f"### {cap_code} — {cap_name}")
        for grp_code, fams in sorted(grupos.items()):
            grp_name = fams[0].get("grupo_name") or grp_code
            lines.append(f"  [{grp_code}] {grp_name}")
            for f in fams:
                kw = ", ".join(f["keywords"][:6]) if f["keywords"] else ""
                unit = f.get("typical_unit") or "?"
                lines.append(f"    - {f['code']} ({unit}): {f['name']}"
                             + (f" | kw: {kw}" if kw else ""))
    return "\n".join(lines)


_CLASSIFY_PROMPT_TEMPLATE = """Você é um assistente de orçamento de obra especializado em projetos de escritório corporativo.

Tarefa: classificar UMA descrição de item de orçamento na família mais adequada do catálogo hierárquico abaixo, extraindo também os atributos folha (cor, PD, dimensão, marca etc.) que são críticos pra compra.

CATÁLOGO:
{catalog}

ITEM A CLASSIFICAR:
- descrição: "{description}"
- unidade: {unit}

INSTRUÇÕES:
1. Escolha UMA família do catálogo acima cuja keywords/nome melhor descrevem a ação sobre o substrato do item.
2. Se a unidade do item NÃO bater com typical_unit da família, baixe a confidence.
3. Se a descrição for muito genérica ou não encaixar em nenhuma família, retorne `familia_code: null` com confidence baixa.
4. Extraia TODOS os atributos relevantes: cor, acabamento, marca/fornecedor, dimensão, PD (pé-direito), material, código do projeto (P1, R4, A1, MB-01…). Preserve em `attributes`.

Retorne APENAS o JSON (sem texto antes ou depois):
{{
  "familia_code": "fam_xxx" ou null,
  "confidence": 0.0-1.0,
  "attributes": {{}},
  "reasoning": "frase curta"
}}"""


def classify_item(description: str, unit: str = "") -> dict:
    """Classifica uma descrição em família do catálogo.

    Retorna dict com: familia_id, familia_code, grupo_id, capitulo_id,
    confidence, attributes, reasoning.

    Em caso de erro (API key faltando, LLM indisponível, JSON inválido),
    retorna familia_id=None com confidence=0.
    """
    if not description or len(description.strip()) < 3:
        return _empty_result("descrição muito curta")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return _empty_result("ANTHROPIC_API_KEY não configurada")

    families = load_families()
    if not families:
        return _empty_result("catálogo vazio")

    catalog_text = _build_catalog_text(families)
    prompt = _CLASSIFY_PROMPT_TEMPLATE.format(
        catalog=catalog_text,
        description=description.strip()[:200],
        unit=unit or "?",
    )

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip() if resp.content else ""
    except Exception as e:
        return _empty_result(f"erro LLM: {type(e).__name__}: {e}")

    # Extrai JSON do texto (LLM às vezes adiciona prefixo)
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return _empty_result(f"LLM não retornou JSON: {text[:100]}")

    try:
        data = json.loads(m.group(0))
    except Exception as e:
        return _empty_result(f"JSON inválido: {e} | texto: {text[:100]}")

    familia_code = data.get("familia_code") or None
    familia = next((f for f in families if f["code"] == familia_code), None) if familia_code else None

    return {
        "familia_id": familia["id"] if familia else None,
        "familia_code": familia_code,
        "grupo_id": familia["grupo_id"] if familia else None,
        "grupo_code": familia["grupo_code"] if familia else None,
        "capitulo_id": familia["capitulo_id"] if familia else None,
        "capitulo_code": familia["capitulo_code"] if familia else None,
        "confidence": max(0.0, min(1.0, float(data.get("confidence", 0) or 0))),
        "attributes": data.get("attributes", {}) or {},
        "reasoning": (data.get("reasoning") or "")[:200],
    }


def _empty_result(reason: str) -> dict:
    return {
        "familia_id": None, "familia_code": None,
        "grupo_id": None, "grupo_code": None,
        "capitulo_id": None, "capitulo_code": None,
        "confidence": 0.0, "attributes": {}, "reasoning": reason,
    }


# Cache simples pra busca de SINAPI por palavras-chave
_sinapi_cache = {}


def suggest_sinapi(description: str, unit: str = "", top_k: int = 1) -> list[dict]:
    """Sugere o(s) código(s) SINAPI mais próximo(s) da descrição.

    Estratégia simples (sem embedding por enquanto): busca via PostgREST
    full-text-ish — quebra a descrição em palavras-chave e busca em
    sinapi_composicao.descricao via ILIKE com peso pela quantidade de
    palavras que casam.

    Cacheia o resultado por (description normalizada, unit).
    """
    if not description or len(description.strip()) < 4:
        return []
    cache_key = (description.strip().lower()[:120], (unit or "").lower())
    if cache_key in _sinapi_cache:
        return _sinapi_cache[cache_key][:top_k]

    # Extrai palavras-chave significativas (>=4 chars, sem genéricas)
    import unicodedata as _u
    text = _u.normalize("NFD", description.lower()).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    stop = {"de", "do", "da", "em", "com", "para", "tipo", "modelo",
            "novo", "nova", "existente", "conforme", "execucao",
            "fornecimento", "instalacao"}
    keywords = [w for w in text.split() if len(w) >= 4 and w not in stop][:5]
    if not keywords:
        return []

    # Busca cada keyword em sinapi_composicao e pontua por overlap
    candidates: dict = {}  # codigo -> (score, row)
    try:
        for kw in keywords:
            url = (f"{SUPABASE_URL}/rest/v1/sinapi_composicao"
                   f"?select=codigo,descricao,unidade"
                   f"&descricao=ilike.*{urllib.request.quote(kw)}*&limit=20")
            req = urllib.request.Request(url, method="GET")
            req.add_header("apikey", SUPABASE_KEY)
            req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
            req.add_header("Accept", "application/json")
            resp = urllib.request.urlopen(req, timeout=10)
            rows = json.loads(resp.read().decode("utf-8"))
            for r in rows:
                cod = r["codigo"]
                desc = (r.get("descricao") or "").lower()
                if cod not in candidates:
                    candidates[cod] = {"score": 0, "row": r}
                # +1 por keyword presente
                candidates[cod]["score"] += 1
                # bônus se unit bate
                if unit and r.get("unidade") and unit.lower() in r["unidade"].lower():
                    candidates[cod]["score"] += 0.5
    except Exception as e:
        print(f"[classifier] sinapi search error: {e}")
        return []

    if not candidates:
        return []

    # Ordena por score desc; empate por descrição mais curta (mais genérica)
    ranked = sorted(
        candidates.values(),
        key=lambda x: (-x["score"], len(x["row"].get("descricao") or "")),
    )
    out = []
    for entry in ranked[:max(top_k, 5)]:
        r = entry["row"]
        out.append({
            "codigo": r["codigo"],
            "descricao": r.get("descricao", "")[:150],
            "unidade": r.get("unidade"),
            "match_score": entry["score"],
        })
    _sinapi_cache[cache_key] = out
    return out[:top_k]


def get_ancestors(familia_id: int) -> dict:
    """Busca grupo_id + capitulo_id a partir de um familia_id.
    Útil pra popular cascade em benchmarks e alertas."""
    if not familia_id:
        return {"familia_id": None, "grupo_id": None, "capitulo_id": None}
    families = load_families()
    f = next((x for x in families if x["id"] == familia_id), None)
    if not f:
        return {"familia_id": familia_id, "grupo_id": None, "capitulo_id": None}
    return {
        "familia_id": familia_id,
        "grupo_id": f.get("grupo_id"),
        "capitulo_id": f.get("capitulo_id"),
    }
