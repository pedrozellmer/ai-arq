# -*- coding: utf-8 -*-
"""Lookup de heurísticas de mercado (tabela market_heuristics do Supabase).

Regra dura: NUNCA retornar valor absoluto de projeto. Só métricas adimensionais
(coeficientes de variação, shares, patterns). Usado pra gerar ALERTAS nas
planilhas — nunca pra copiar valor de um projeto pro outro.

Uso:
    from market_heuristics import check_item_anomaly, get_dispersion_for_category
    alertas = check_item_anomaly(item)
    # alertas: lista de strings curtas pra anexar em observations
"""
import json
import os
import re
import unicodedata
import urllib.request
from typing import List, Dict, Optional


SUPABASE_URL = os.getenv("SUPABASE_URL", "https://kqjabzwgbfuivzlcfvvu.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY") or (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtxamFiendnYmZ1aXZ6bGNmdnZ1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzYwMDg5NzcsImV4cCI6MjA5MTU4NDk3N30."
    "48xSenZlDV0LfD94ZxwGvX41Kf9Je2n-ouZpJrrCSKI"
)


# Mesmo mapeamento de categorias do script extrator (manter coerente).
CATEGORIAS_KEYWORDS = {
    "demolicao": ["demolicao", "remocao", "retirada", "demolir"],
    "drywall": ["drywall", "gesso", "septo", "sept"],
    "eletrica": ["eletr", "tomada", "interruptor", "cabeamento", "luminaria",
                  "iluminac"],
    "hidraulica": ["hidr", "tubulacao", "bacia", "torneira", "registro"],
    "piso": ["piso", "carpete", "laminado", "vinil", "contrapiso"],
    "pintura": ["pintura", "tinta", "selador", "verniz", "esmalte"],
    "forro": ["forro"],
    "esquadria": ["porta", "janela", "esquadria"],
    "ar_condicionado": ["ar condicionado", "hvac", "condicionado", "climatiz"],
    "mobiliario": ["mobiliar", "armario", "marcenar", "bancada"],
    "preliminares": ["mobilizacao", "canteiro", "tapume", "protecao",
                      "sinalizacao", "art"],
}


def _normalize(s: str) -> str:
    """Tira acento, lowercase, espaços únicos. Mesma função do extrator."""
    if not s:
        return ""
    s = str(s).strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def categorize_item(description: str) -> str:
    """Classifica descrição em categoria canônica (mesma lógica do extrator)."""
    desc_norm = _normalize(description)
    for cat, keys in CATEGORIAS_KEYWORDS.items():
        for k in keys:
            if k in desc_norm:
                return cat
    return "outros"


# Cache em memória — heurísticas mudam raramente (só quando ingerimos novo projeto)
_CACHE: Dict[str, List[Dict]] = {}


def _fetch(heuristic_type: str, typology: str = "office") -> List[Dict]:
    """Busca heurísticas do Supabase. Cachea por (type, typology)."""
    cache_key = f"{heuristic_type}:{typology}"
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    url = (
        f"{SUPABASE_URL}/rest/v1/market_heuristics"
        f"?heuristic_type=eq.{heuristic_type}"
        f"&typology=eq.{typology}"
        f"&select=*"
    )
    req = urllib.request.Request(url, method="GET")
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    try:
        resp = urllib.request.urlopen(req, timeout=8)
        data = json.loads(resp.read().decode("utf-8"))
        _CACHE[cache_key] = data
        return data
    except Exception as e:
        print(f"  [market_heuristics] erro buscando {heuristic_type}: {e}")
        return []


#: quantos projetos-fonte DISTINTOS a base precisa ter pra uma heurística
#: virar FRASE na planilha do cliente.
#:
#: 🩸 18/09/2026. A base inteira era UM comparativo (3 fornecedores de um
#: escritório corporativo, ingerido em 23/04). O "±X%" de cada categoria era a
#: média do coeficiente de variação de 1 a 5 itens com 2-3 cotações cada —
#: "piso" era 1 item com 2 cotações — e saía como fato de mercado em **3.873
#: linhas (36,7%) de 66 jobs, 50 contas**, inclusive projetos de ESTRUTURA
#: categorizados por palavra de fit-out. E só disparava em `office`, que é a
#: PRIMEIRA opção do select, ou seja, o default de quem não escolhe.
#:
#: 🔑 Dois é o mínimo pra "mais de um projeto" — não é garantia estatística, e a
#: frase carrega o nº de fontes exatamente por isso: com N pequeno, o cliente
#: lê o N. Decisão do Pedro (18/09): desligar até ter base, código fica.
#: 🚫 NÃO baixe este piso pra fazer a frase voltar: a frase volta sozinha
#: quando o SEGUNDO comparativo for ingerido.
_MINIMO_DE_FONTES = 2
#: a categoria pega-tudo do `categorize_item`: "itens dessa categoria" não
#: quer dizer nada quando a categoria é "o que não casou palavra nenhuma".
_CATEGORIA_SEM_IDENTIDADE = "outros"


def base_da_tipologia(typology: str = "office",
                      heuristic_type: str = "dispersion") -> Dict:
    """Quantos projetos-fonte DISTINTOS sustentam este tipo de heurística.

    Conta `source_anonimo` distinto — linhas da MESMA fonte contam uma vez.
    Devolve {n_fontes, lastro, minimo}. `lastro` é o que libera a frase.
    """
    rows = _fetch(heuristic_type, typology) or []
    fontes = {str(r.get("source_anonimo") or "").strip() for r in rows}
    fontes.discard("")
    return {"n_fontes": len(fontes),
            "lastro": len(fontes) >= _MINIMO_DE_FONTES,
            "minimo": _MINIMO_DE_FONTES}


def metricas_para_mostrar(category: str, typology: str = "office") -> Dict:
    """O que o chat e a API podem MOSTRAR de uma categoria: a base sempre; os
    números só com lastro, e nunca pra categoria sem identidade.

    Uma regra pros dois chamadores (agent.py e /api/heuristics/check) — antes
    cada um montava a resposta por conta própria e os dois exibiam "±X%" de
    uma base de um projeto só.
    """
    saida = {"categoria": category, "tipologia": typology, "base": {}}
    _sem_identidade = (category == _CATEGORIA_SEM_IDENTIDADE)
    for tipo, fn, chave in (("dispersion", get_dispersion_for_category, "dispersao"),
                            ("coverage_pattern", get_coverage_pattern_for_category, "cobertura"),
                            ("mat_mo_share", get_mat_mo_share_for_category, "share_mat_mo")):
        b = base_da_tipologia(typology, tipo)
        saida["base"][chave] = b
        saida[chave] = fn(category, typology) if (b["lastro"] and not _sem_identidade) else None
    return saida


def get_dispersion_for_category(category: str,
                                  typology: str = "office") -> Optional[Dict]:
    """Retorna estatísticas de dispersão de preço pra uma categoria.

    Exemplo: {'cv_medio': 0.85, 'n_items': 4} = variação média de 85%.
    """
    rows = _fetch("dispersion", typology)
    matches = [r for r in rows if r["category"] == category]
    if not matches:
        return None

    valores = [r["metric_value"] for r in matches if r.get("metric_value")]
    if not valores:
        return None

    return {
        "cv_medio": sum(valores) / len(valores),
        "cv_max": max(valores),
        "n_items": len(matches),
    }


def get_mat_mo_share_for_category(category: str,
                                   typology: str = "office") -> Optional[Dict]:
    """Retorna share típico MAT vs MO pra categoria.

    Exemplo: {'share_mat': 0.25, 'share_mo': 0.75, 'stddev': 0.23, 'n': 50}.
    """
    rows = _fetch("mat_mo_share", typology)
    mat = next((r for r in rows
                if r["category"] == category and r["metric_name"] == "share_mat"),
               None)
    mo = next((r for r in rows
               if r["category"] == category and r["metric_name"] == "share_mo"),
              None)
    if not mat:
        return None

    return {
        "share_mat": mat["metric_value"],
        "share_mo": mo["metric_value"] if mo else 1 - mat["metric_value"],
        "stddev_mat": mat.get("stddev", 0),
        "n_observations": mat.get("n_observations", 0),
    }


def get_coverage_pattern_for_category(category: str,
                                        typology: str = "office") -> Optional[Dict]:
    """Retorna padrão de cobertura: quantos fornecedores tipicamente orçam essa categoria.

    Exemplo: {'cobertura_media': 1.0, 'n_fornecedores': 3} = só 1 de 3 fornecedores
    costuma orçar essa categoria (muito omitida).
    """
    rows = _fetch("coverage_pattern", typology)
    matches = [r for r in rows
               if r["category"] == category and r["metric_name"] == "cobertura_completa"]
    if not matches:
        return None

    cobertura = matches[0]["metric_value"]
    return {
        "cobertura_observada": cobertura,  # 0-3 (quantos dos 3 fornecedores orçaram)
        "n_fornecedores": matches[0].get("n_observations", 3),
        "raramente_cotada": cobertura <= 1,  # flag pra alerta forte
    }


def check_item_anomaly(item, typology: str = "office") -> List[str]:
    """Checa um BudgetItem contra as heurísticas de mercado.

    Retorna lista de strings curtas pra anexar em observations.
    Aceita tanto BudgetItem (com atributos) quanto dict.
    """
    # Extrai campos do item (funciona com BudgetItem e dict)
    if hasattr(item, "description"):
        desc = item.description
        unit = item.unit
    else:
        desc = item.get("description", "") or item.get("desc", "")
        unit = item.get("unit", "") or item.get("un", "")

    if not desc:
        return []

    category = categorize_item(desc)
    alertas = []

    # 🚫 "itens dessa categoria" pra quem caiu no pega-tudo é frase sem
    # sujeito: 2.283 das 3.873 linhas afetadas eram exatamente "outros".
    if category == _CATEGORIA_SEM_IDENTIDADE:
        return []

    # 1. DISPERSÃO — só com LASTRO (ver `_MINIMO_DE_FONTES`), e a frase diz o
    # tamanho da base, pra nunca mais soar como estatística de mercado quando
    # é a média de meia dúzia de cotações.
    _b_disp = base_da_tipologia(typology, "dispersion")
    disp = get_dispersion_for_category(category, typology) if _b_disp["lastro"] else None
    if disp and disp["cv_medio"] > 0.5:  # variação > 50%
        pct = int(disp["cv_medio"] * 100)
        alertas.append(
            f"💡 Em {_b_disp['n_fontes']} comparativos, itens de {category} "
            f"variaram ±{pct}% entre fornecedores — vale pedir 3 orçamentos."
        )

    # 2. COBERTURA — mesma régua, mesma base.
    _b_cov = base_da_tipologia(typology, "coverage_pattern")
    cov = get_coverage_pattern_for_category(category, typology) if _b_cov["lastro"] else None
    if cov and cov.get("raramente_cotada"):
        alertas.append(
            f"⚠ Em {_b_cov['n_fontes']} comparativos, '{category}' costumou ficar "
            f"de fora dos orçamentos — confirmar se está no escopo."
        )

    return alertas


def get_summary() -> Dict:
    """Retorna resumo do que tem na base (pra debug / UI)."""
    summary = {"typology": "office"}
    for htype in ("dispersion", "coverage_pattern", "mat_mo_share"):
        rows = _fetch(htype)
        summary[htype] = {
            "n_rows": len(rows),
            "categorias": sorted(set(r["category"] for r in rows)),
            # 18/09: quantos projetos-fonte sustentam isto — é o que decide se
            # alguma frase sai pro cliente.
            "base": base_da_tipologia("office", htype),
        }
    return summary


if __name__ == "__main__":
    # Teste rápido
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print("Summary:")
    s = get_summary()
    for k, v in s.items():
        if isinstance(v, dict):
            print(f"  {k}: {v['n_rows']} rows, cats={v['categorias'][:5]}...")
        else:
            print(f"  {k}: {v}")

    print()
    print("Teste de alertas em items típicos:")
    testes = [
        {"description": "Demolição de divisórias em drywall", "unit": "m²"},
        {"description": "Pintura látex PVA em parede", "unit": "m²"},
        {"description": "Instalação de ar-condicionado split", "unit": "un"},
        {"description": "Luminária LED 60x60", "unit": "un"},
    ]
    for t in testes:
        cat = categorize_item(t["description"])
        alertas = check_item_anomaly(t)
        print(f"  [{cat}] {t['description']}")
        for a in alertas:
            print(f"    → {a}")
