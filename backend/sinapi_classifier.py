# -*- coding: utf-8 -*-
"""Classificador BATCH de SINAPI → catalog_familia.

Roda 1x (ou ocasionalmente, quando catálogo muda). Pega composições
sem familia_id, classifica em lotes de N via Claude Haiku 4.5 e
atualiza in-place. Depois disso, busca de SINAPI por família vira
trivial (lookup por familia_id no banco).

Uso:
    python sinapi_classifier.py [batch_size=20] [limit=None]
"""
import json
import os
import re
import sys
import time
import urllib.request
from typing import Optional


SUPABASE_URL = "https://kqjabzwgbfuivzlcfvvu.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtxamFiendnYmZ1aXZ6bGNmdnZ1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzYwMDg5NzcsImV4cCI6MjA5MTU4NDk3N30.48xSenZlDV0LfD94ZxwGvX41Kf9Je2n-ouZpJrrCSKI"


def _supabase_get(query: str, paginate: bool = False, page_size: int = 1000) -> list[dict]:
    """GET ao Supabase REST. Se paginate=True, faz loop com Range header
    pra contornar o limite default de 1000 rows."""
    if not paginate:
        url = f"{SUPABASE_URL}/rest/v1/{query}"
        req = urllib.request.Request(url, method="GET")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        req.add_header("Accept", "application/json")
        resp = urllib.request.urlopen(req, timeout=20)
        return json.loads(resp.read().decode("utf-8"))

    out = []
    offset = 0
    while True:
        url = f"{SUPABASE_URL}/rest/v1/{query}"
        req = urllib.request.Request(url, method="GET")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        req.add_header("Accept", "application/json")
        req.add_header("Range-Unit", "items")
        req.add_header("Range", f"{offset}-{offset+page_size-1}")
        resp = urllib.request.urlopen(req, timeout=30)
        page = json.loads(resp.read().decode("utf-8"))
        if not page:
            break
        out.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    return out


def _supabase_patch(query: str, data: dict) -> bool:
    try:
        url = f"{SUPABASE_URL}/rest/v1/{query}"
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="PATCH")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        req.add_header("Content-Type", "application/json")
        req.add_header("Prefer", "return=minimal")
        urllib.request.urlopen(req, timeout=15)
        return True
    except Exception as e:
        print(f"  PATCH error {query}: {e}")
        return False


def _load_families():
    fams = _supabase_get(
        "catalog_familia?select=id,code,name,typical_unit,keywords,"
        "grupo:grupo_id(code,name,capitulo:capitulo_id(code,name))"
    )
    out = []
    for f in fams:
        grupo = f.get("grupo") or {}
        capitulo = (grupo.get("capitulo") or {}) if isinstance(grupo, dict) else {}
        out.append({
            "id": f["id"],
            "code": f["code"],
            "name": f["name"],
            "typical_unit": f.get("typical_unit"),
            "keywords": f.get("keywords") or [],
            "grupo_code": grupo.get("code") if isinstance(grupo, dict) else None,
            "capitulo_code": capitulo.get("code"),
        })
    return out


def _build_catalog_text(families):
    by_cap = {}
    for f in families:
        by_cap.setdefault(f.get("capitulo_code") or "—", {}).setdefault(
            f.get("grupo_code") or "—", []).append(f)
    lines = []
    for cap_code, grupos in sorted(by_cap.items()):
        lines.append(f"### {cap_code}")
        for grp_code, fams in sorted(grupos.items()):
            lines.append(f"  [{grp_code}]")
            for f in fams:
                kw = ", ".join(f["keywords"][:5]) if f["keywords"] else ""
                unit = f.get("typical_unit") or "?"
                lines.append(f"    - {f['code']} ({unit}): {f['name']}"
                             + (f" | kw: {kw}" if kw else ""))
    return "\n".join(lines)


_BATCH_PROMPT = """Você classifica composições do catálogo SINAPI nas famílias do catálogo abaixo.

CATÁLOGO DE FAMÍLIAS DISPONÍVEIS:
{catalog}

LISTA DE COMPOSIÇÕES SINAPI A CLASSIFICAR:
{items}

Pra CADA composição, escolha a família mais adequada do catálogo (use o `code`, ex: "fam_pint_acrilica"). **Se nenhuma família encaixa BEM, retorne null** — não force.

REGRAS DE QUALIDADE (importantíssimas):
- Use APENAS códigos da lista de famílias acima. NÃO invente.
- Material/produto exato deve bater. Exemplos:
  * "Tinta acrílica" vai em fam_pint_acrilica; "Tinta esmalte/alquídica/poliuretânica" vai em fam_pint_esmalte (NÃO em fam_pint_epoxi)
  * "Luminária CALHA T8/fluorescente/sobrepor" vai em fam_lum_fluorescente (NÃO em fam_lum_linear que é fita LED moderna)
  * "Janela PVC/madeira/alumínio" vai em fam_janela_madeira ou fam_janela_metal (NÃO em fam_vidro_fixo)
  * "Entrada de energia da concessionária" vai em fam_entrada_energia (NÃO em fam_quadro)
- Composições genéricas/de insumo (carga/descarga, transporte, hora de equipe, argamassas avulsas como insumo, conexões pontuais) → null. Não força em família de produto-final.
- Demolição/remoção/recolocação são famílias separadas (DEMO.*); não confundir com instalação nova.
- Use unidade como dica forte (m², m, ml, un, vb, kg, h, dia).
- Em dúvida razoável, prefira null. **Mais vale ficar sem mapear do que errar.**

Retorne APENAS JSON na ordem da lista de entrada (mesma ordem):
[
  {{"codigo": "12345", "familia_code": "fam_xxx" ou null, "confidence": 0.0-1.0}},
  ...
]"""


def classify_batch(items: list[dict], catalog_text: str, families_by_code: dict,
                   client) -> list[dict]:
    """Classifica N composições em uma chamada LLM. items deve ter
    {codigo, descricao, unidade}. Retorna [{codigo, familia_id, confidence}]."""
    items_str = "\n".join(
        f'  {{"codigo": "{i["codigo"]}", "descricao": "{(i.get("descricao") or "")[:120]}", "unidade": "{i.get("unidade") or ""}"}}'
        for i in items
    )
    prompt = _BATCH_PROMPT.format(catalog=catalog_text, items=items_str)

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip() if resp.content else ""
    except Exception as e:
        print(f"  LLM err: {e}")
        return []

    # Extrai array JSON
    m = re.search(r"\[[\s\S]*\]", text)
    if not m:
        print(f"  no JSON in: {text[:200]}")
        return []
    try:
        parsed = json.loads(m.group(0))
    except Exception as e:
        print(f"  JSON err: {e} | {text[:200]}")
        return []

    out = []
    for entry in parsed:
        cod = str(entry.get("codigo", "")).strip()
        fam_code = entry.get("familia_code")
        conf = float(entry.get("confidence") or 0)
        familia = families_by_code.get(fam_code) if fam_code else None
        out.append({
            "codigo": cod,
            "familia_id": familia["id"] if familia else None,
            "familia_code": fam_code,
            "confidence": max(0.0, min(1.0, conf)),
        })
    return out


def main():
    batch_size = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY não configurada")
        sys.exit(1)

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    print("Carregando catálogo de famílias...")
    families = _load_families()
    families_by_code = {f["code"]: f for f in families}
    catalog_text = _build_catalog_text(families)
    print(f"  {len(families)} famílias")

    # Pega composições sem familia_id (paginado pra contornar limite 1000)
    print("Buscando composições SINAPI sem classificação...")
    query = "sinapi_composicao?select=codigo,descricao,unidade&familia_id=is.null&order=codigo"
    if limit:
        query += f"&limit={limit}"
        pending = _supabase_get(query)
    else:
        pending = _supabase_get(query, paginate=True)
    total = len(pending)
    print(f"  {total} pendentes")
    if total == 0:
        print("Nada a classificar.")
        return

    # Processa em batches
    classified = 0
    null_count = 0
    t0 = time.time()
    for i in range(0, total, batch_size):
        batch = pending[i:i + batch_size]
        results = classify_batch(batch, catalog_text, families_by_code, client)
        for r in results:
            if r.get("familia_id") is None:
                null_count += 1
                # mantém familia_id null pra retentativa futura, mas
                # marca confidence=0 (já passou pelo classificador)
                continue
            ok = _supabase_patch(
                f"sinapi_composicao?codigo=eq.{r['codigo']}",
                {"familia_id": r["familia_id"]},
            )
            if ok:
                classified += 1
        elapsed = time.time() - t0
        rate = (i + len(batch)) / elapsed if elapsed > 0 else 0
        eta = (total - (i + len(batch))) / rate if rate > 0 else 0
        print(f"  [{i + len(batch)}/{total}] classified={classified} null={null_count} "
              f"rate={rate:.1f}/s eta={eta/60:.1f}min")

    print(f"\nDONE em {(time.time()-t0)/60:.1f}min")
    print(f"  Classificados: {classified}")
    print(f"  Sem família (rejeitados pelo LLM): {null_count}")


if __name__ == "__main__":
    main()
