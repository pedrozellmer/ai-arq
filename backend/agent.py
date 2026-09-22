# -*- coding: utf-8 -*-
"""Agente "tira-dúvidas" da planilha — Claude + ferramentas pra investigar
um projeto específico (job_id) e responder perguntas do cliente.

Loop padrão de agente:
  user → Claude → (opcional) chamada de tool → resultado da tool → Claude → resposta final

Tools disponíveis (todas operam no escopo de UM job_id):
  - list_items: lista resumida de itens da planilha
  - get_item_details: dados completos + observação de UM item específico
  - search_items: busca por palavra-chave na descrição
  - read_dxf_summary: estatísticas de um DXF (layers, blocos, walls)
  - check_density: roda check_density_anomaly num item específico
"""
import json
import os
import re
import urllib.request
from typing import Any, Optional

from openpyxl import load_workbook

from models import SELO_MEDIDO


SUPABASE_URL = os.getenv("SUPABASE_URL", "https://kqjabzwgbfuivzlcfvvu.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_ANON_KEY") or "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtxamFiendnYmZ1aXZ6bGNmdnZ1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzYwMDg5NzcsImV4cCI6MjA5MTU4NDk3N30.48xSenZlDV0LfD94ZxwGvX41Kf9Je2n-ouZpJrrCSKI"
# `apikey` continua sendo a anon (PostgREST exige). O `Authorization: Bearer`
# usa a service_role pra ler project_items/agent_conversations etc. depois que a
# RLS fechar pra anon. service_role roda só server-side, nunca exposta ao frontend.
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or SUPABASE_KEY

WORK_DIR = os.path.join(os.environ.get("TMPDIR", "/tmp"), "aiarq_jobs")


# ════════════════════════════════════════════════════════════════
#  Tools — funções Python que o agente pode chamar
# ════════════════════════════════════════════════════════════════

def _nome_da_prancha_para_o_cliente(valor) -> str:
    """O nome da prancha como o cliente a enviou — regra única de engine_rules.

    18/09/2026: a planilha antiga guardava "planta_libredwg.dxf" (o DXF que o
    conversor gerou) e o chat repetia isso pro cliente. Limpa aqui também, pra
    planilha antiga no Storage não fazer o chat divergir da tela.
    """
    from engine_rules import nome_que_o_cliente_enviou
    return nome_que_o_cliente_enviou(str(valor or "").strip())


def _planilha_path(job_id: str) -> Optional[str]:
    """Path local da planilha. Se sumiu (Render restart), tenta baixar
    do Supabase Storage via helper do main.py."""
    local = os.path.join(WORK_DIR, job_id, f"orcamento_{job_id}.xlsx")
    if os.path.exists(local):
        return local
    try:
        from main import get_planilha_path as _get
        return _get(job_id)
    except Exception:
        return None


def _open_planilha(job_id: str):
    path = _planilha_path(job_id)
    if not path or not os.path.exists(path):
        return None
    return load_workbook(path, read_only=True, data_only=True)


def _selo_da_linha(item_num: str, observations: str) -> str:
    """medido / estimado / metadado — o que a PLANILHA disse desta linha.

    🩸 15/09/2026 (job ba869938): o resumo por disciplina pôs "✓ medidos do
    CAD" em ~20 linhas ESTIMADAS — alvenaria, 7.314 m² de piso, 144 vagas — com
    o cliente, orçamentista, lendo. O prompt manda dizer medido × estimado, e
    `list_items` entregava só número, descrição, unidade e quantidade: o modelo
    chutou ✓ em tudo que tinha número. Precisou de e-mail de correção.
    🔑 O selo é lido do COMEÇO da observação, onde `generate_spreadsheet` o
    escreve — nunca de um "MEDIDO" no meio do texto, que o motor pode ter
    escrito falando de outra linha. Linha 0.x é a capa (área, "também gera"):
    não é serviço, então não é medida nem estimativa.
    FAIL-SAFE: o que não começa com o selo de medido é estimado."""
    if str(item_num or "").strip().startswith("0."):
        return "metadado"
    if str(observations or "").lstrip().startswith(SELO_MEDIDO):
        return "medido"
    return "estimado"


def _iter_orcamento_rows(wb):
    """Itera linhas da aba Orçamento, devolvendo dicts."""
    if not wb or "Orçamento" not in wb.sheetnames:
        return
    ws = wb["Orçamento"]
    # 🩸 18/09/2026 — lia até a 9ª coluna e chamava a 9ª de `ref_sheet`. A 9ª
    # é ORIGEM DA MEDIÇÃO (desde 24/08); a referência da prancha é a 11ª,
    # REF. O chat vinha entregando a origem da medição como se fosse o nome
    # da prancha. Achado da revisão adversarial deste commit.
    for row in ws.iter_rows(min_row=1, max_col=11, values_only=True):
        if not row or len(row) < 4:
            continue
        item_num = row[0]
        if not isinstance(item_num, str):
            continue
        if not re.match(r"^\d+\.\d+", item_num.strip()):
            continue
        _obs = str(row[7] or "").strip() if len(row) > 7 else ""
        yield {
            "item_num": item_num.strip(),
            "description": str(row[1] or "").strip(),
            "unit": str(row[2] or "").strip(),
            "quantity": row[3],
            "selo": _selo_da_linha(item_num, _obs),
            "observations": _obs,
            # 18/09: o chat lê a planilha; o nome da prancha sai como o cliente
            # enviou ("planta.dwg"), nunca como o DXF do conversor. Regra única.
            "ref_sheet": _nome_da_prancha_para_o_cliente(row[10] if len(row) > 10 else ""),
        }


def tool_list_items(job_id: str, max_items: int = 200) -> dict:
    """Lista itens da planilha — número, descrição (80 chars), unit, qty e o
    SELO (medido/estimado/metadado). Sem o selo o resumo chutava ✓ (15/09)."""
    wb = _open_planilha(job_id)
    if wb is None:
        return {"error": f"planilha do job {job_id} não encontrada"}
    items = []
    for r in _iter_orcamento_rows(wb):
        items.append({
            "item_num": r["item_num"],
            "description": r["description"][:80],
            "unit": r["unit"],
            "quantity": r["quantity"],
            "selo": r["selo"],
        })
        if len(items) >= max_items:
            break
    wb.close()
    return {"count": len(items), "items": items}


def tool_get_item_details(job_id: str, item_num: str) -> dict:
    """Dados completos de UM item + classificação automática (família,
    grupo, capítulo) e atributos folha extraídos (cor, PD, marca, etc.)."""
    wb = _open_planilha(job_id)
    if wb is None:
        return {"error": f"planilha do job {job_id} não encontrada"}
    found = None
    for r in _iter_orcamento_rows(wb):
        if r["item_num"] == item_num.strip():
            found = r
            break
    wb.close()
    if not found:
        return {"error": f"item {item_num} não encontrado"}

    # Enriquece com classificação (LLM Haiku, ~3s)
    try:
        from classifier import classify_item
        cls = classify_item(found["description"], found["unit"])
        found["categoria"] = {
            "capitulo": cls.get("capitulo_code"),
            "grupo": cls.get("grupo_code"),
            "familia": cls.get("familia_code"),
            # 15/09: é a confiança do CLASSIFICADOR (0 a 1), não da medição —
            # com o nome "confidence" ao lado do `selo` o modelo lia "alta
            # confiança" num item estimado.
            "confianca_da_classificacao": round(cls.get("confidence", 0), 2),
        }
        found["atributos_folha"] = cls.get("attributes") or {}
    except Exception as e:
        found["categoria"] = {"error": str(e)[:100]}
    return found


# ── Busca por palavras ──────────────────────────────────────────────────────
# 🩸 22/09/2026 (job 844603fb): a cliente colou 3 linhas da legenda e o chat
# respondeu "nenhum dos três itens foi encontrado". UM estava na planilha — o
# conjunto tomada + interruptor paralelo (8 un). Os outros dois (tomada em
# caixa 4x4 embutida no forro, para luminária de emergência, e tomada 4x4 de
# piso) são linhas da legenda que a leitura da IA não listou. A busca exigia a
# FRASE inteira como pedaço da descrição: "tomada caixa 4x2" dava 0 com 8
# linhas "Tomada ... em caixa 4x2\"". Em 60 dias as 10 buscas de mais de uma
# palavra voltaram 0 (10 de 10). Agora é por palavra, em qualquer ordem, sem
# acento nem caixa, e quando nenhuma linha tem TODAS as palavras a resposta
# traz as mais parecidas dizendo o que bate, o que falta e o que DIVERGE.
# 🩸 A 1ª versão deste conserto (revisão de 22/09) errou pro outro lado:
#   • a tomada 4x4 do FORRO saía como "a sua tomada, em caixa 4x2" — era a
#     tomada 4x2 de OUTRA linha da legenda. Candidato com outra medida, outro
#     lugar ou outro formato agora vem com `outro_item` e o `diverge`;
#   • `items` trazia linha SEM a palavra: portão por porta, quadra por quadro,
#     tampa por tampo (a variante de prefixo e de gênero contava como a mesma
#     palavra), e "tipo" era palavra vazia, então "pavimento tipo" devolvia o
#     "último pavimento". Variante agora só entra em `candidatos`.
_PALAVRAS_VAZIAS = frozenset(
    "a o as os e de da do das dos em no na nos nas ao aos para pra por com "
    "um uma ou que se conforme uso legenda m h".split())
_SINONIMOS_DA_BUSCA = {"cx": "caixa"}
# Adjetivo de obra no feminino = o mesmo no masculino ("parede interna" acha o
# "reboco interno ... paredes"). Lista FECHADA de propósito: a regra geral a/o
# junta substantivos que não são a mesma coisa (quadro/quadra, tampo/tampa).
_NO_MASCULINO = {p: p[:-1] + "o" for p in (
    "interna externa embutida sobreposta rigida quadrada redonda dupla tripla "
    "eletrica hidraulica metalica ceramica").split()}
_TOKEN_DA_BUSCA = re.compile(
    r"\d+x\d+|\d+p\+t|\d+(?:,\d+)*[a-z]*|[a-z][a-z0-9]*")


def _normalizar_para_busca(texto) -> str:
    """Minúsculo, sem acento, e as medidas no formato único (4x2, 2p+t, 10a)."""
    import unicodedata
    t = unicodedata.normalize("NFKD", str(texto or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = t.replace("×", "x").replace("°", "o")  # aspas (4x2" / 4x2'') já separam token
    t = re.sub(r"(\d)\s*x\s*(\d)", r"\1x\2", t)                # 4 x 4 -> 4x4
    t = re.sub(r"(\d)\s*p\s*\+\s*t(?![a-z0-9])", r"\1p+t", t)  # 2P + T -> 2p+t
    t = re.sub(r"(\d)\.(\d)", r"\1,\2", t)                      # 1.20 -> 1,20
    t = re.sub(r"(\d)\s+a(?![a-z0-9])", r"\1a", t)             # 10 A -> 10a
    return t


def _radical(p: str) -> str:
    """Plural -> singular, só o bastante pra "tomadas" achar "tomada"."""
    if len(p) <= 3 or not p.isalpha():
        return p
    if p.endswith("oes"):
        return p[:-3] + "ao"
    if len(p) >= 5 and p.endswith(("res", "zes")):
        return p[:-2]
    if len(p) > 4 and p.endswith("is"):
        return p[:-2] + "l"
    if p.endswith("s") and not p.endswith("ss"):
        return p[:-1]
    return p


def _termos_da_busca(texto) -> list:
    termos = []
    for tok in _TOKEN_DA_BUSCA.findall(_normalizar_para_busca(texto)):
        m = re.fullmatch(r"(\d+),(\d+)(m?)", tok)
        if m:  # 1,20m -> 1,2 (a altura escrita de 3 jeitos é a mesma)
            dec = m.group(2).rstrip("0")
            tok = m.group(1) + ("," + dec if dec else "")
        elif re.fullmatch(r"\d+m", tok):
            tok = tok[:-1]
        tok = _SINONIMOS_DA_BUSCA.get(tok, tok)
        if tok in _PALAVRAS_VAZIAS:
            continue
        tok = _radical(tok)
        tok = _NO_MASCULINO.get(tok, tok)
        if tok not in termos:
            termos.append(tok)
    return termos


def _termo_casa(q: str, termos_da_linha: list) -> tuple:
    """(nota, a palavra da linha que casou).

    1.0 = a MESMA palavra (depois de tirar acento, caixa, plural e o feminino
    dos adjetivos de `_NO_MASCULINO`).
    0.8 = VARIANTE: a mesma raiz com outra ponta (lumin/luminaria). A mesma
    regra junta palavras que NÃO são a mesma coisa (porta/portao, quadro/quadra,
    tampo/tampa), então variante só serve pra candidato — nunca pra `items`.
    Número e medida só casam iguais: 4x2 não é 4x4."""
    if q in termos_da_linha:
        return 1.0, q
    if not q.isalpha() or len(q) < 4:
        return 0.0, ""
    for d in termos_da_linha:
        if len(d) < 4 or not d.isalpha():
            continue
        if d.startswith(q) or q.startswith(d):
            return 0.8, d
        if (len(q) >= 5 and len(d) == len(q) and q[:-1] == d[:-1]
                and q[-1] in "ao" and d[-1] in "ao"):
            return 0.8, d
    return 0.0, ""


# Palavra (já no masculino) -> (classe, valor). Na MESMA classe, valor
# diferente é OUTRO item: tomada de piso não é tomada de forro, caixa
# octogonal não é caixa quadrada, parede externa não é parede interna.
_CLASSE_DA_PALAVRA = {
    "piso": ("lugar", "piso"), "contrapiso": ("lugar", "piso"),
    "parede": ("lugar", "parede"),
    "forro": ("lugar", "teto"), "teto": ("lugar", "teto"), "laje": ("lugar", "teto"),
    "interno": ("lado", "interno"), "externo": ("lado", "externo"),
    "quadrado": ("formato", "quadrado"), "retangular": ("formato", "retangular"),
    "octogonal": ("formato", "octogonal"), "redondo": ("formato", "redondo"),
    "circular": ("formato", "redondo"),
}


def _classe_do_termo(t: str):
    """Medida: a FORMA com os números trocados — 4x4 e 4x2 são "9x9", 10a e 20a
    são "9a", as alturas 1,2 e 0,4 são "9,9". Palavra: a da tabela acima."""
    if any(c.isdigit() for c in t):
        return ("medida " + re.sub(r"\d+", "9", t), t)
    return _CLASSE_DA_PALAVRA.get(t)


def _divergencias(falta: list, termos_da_linha: list) -> dict:
    """{termo pedido: [o que a linha diz no lugar dele]}.

    Só conta quando a linha traz um valor DIFERENTE da mesma classe (4x2 onde
    se pediu 4x4). Linha que apenas não menciona o termo não diverge: o
    conjunto tomada + interruptor paralelo da planilha do caso não traz a
    altura H=1,20m da legenda e É o item — descrição curta não é outro item."""
    out = {}
    for q in falta:
        cq = _classe_do_termo(q)
        if not cq:
            continue
        outros = [d for d in termos_da_linha
                  if (cd := _classe_do_termo(d)) and cd[0] == cq[0] and cd[1] != cq[1]]
        if outros:
            out[q] = outros
    return out


def buscar_linhas(linhas: list, query: str, max_hits: int = 20,
                  max_candidatos: int = 8) -> dict:
    """Busca por palavras nas descrições. `linhas` = dicts de _iter_orcamento_rows.

    `items`, na ordem da planilha: as linhas que a busca ANTIGA achava (a frase
    como pedaço da descrição, sem ligar pra maiúscula — nada que ela achava se
    perde) e as que têm TODAS as palavras IGUAIS, em qualquer ordem. Variante
    não entra: a ferramenta promete ao modelo que `items` tem as palavras.
    `candidatos`: quando sobram menos de 3 em `items`, as linhas que têm ao
    menos METADE das palavras (iguais ou variantes), das mais parecidas pras
    menos, cada uma com `bate`, `falta`, `variante` (a palavra parecida que a
    linha tem no lugar), `diverge` e `outro_item`. `outro_item` = a linha diz
    OUTRA medida, lugar ou formato do mesmo tipo: é outro item, nunca "o seu
    item com outra medida". Palavra rara pesa mais que palavra que está em todo
    lugar ("4x4" em 3 linhas decide mais que "caixa" em 16).
    `termos_sem_correspondencia`: palavras que não aparecem, nem parecidas, em
    linha NENHUMA — é o que deixa o modelo dizer "não há caixa QUADRADA".
    """
    import math
    termos = _termos_da_busca(query)
    frase = str(query or "").lower().strip()  # o contrato da busca antiga, letra por letra
    base = []
    for r in linhas:
        desc = str(r.get("description") or "")
        base.append((r, desc.lower(), _termos_da_busca(desc)))
    notas = [{q: _termo_casa(q, tl) for q in termos} for _, _, tl in base]
    n = len(base)
    peso = {q: 1.0 + math.log((n + 1.0) / (sum(1 for nt in notas if nt[q][0]) + 1.0))
            for q in termos}

    def _linha(r, com_obs=True):
        out = {"item_num": r["item_num"], "description": r["description"][:120],
               "unit": r["unit"], "quantity": r["quantity"], "selo": r["selo"]}
        if com_obs:
            out["observation_preview"] = (r.get("observations") or "")[:120]
        return out

    hits, parciais = [], []
    for i, ((r, desc_l, tl), nt) in enumerate(zip(base, notas)):
        iguais = [q for q in termos if nt[q][0] == 1.0]
        if (frase and frase in desc_l) or (termos and len(iguais) == len(termos)):
            if len(hits) < max_hits:
                hits.append(_linha(r))
            continue
        casadas = [q for q in termos if nt[q][0]]
        if casadas and 2 * len(casadas) >= len(termos):
            parciais.append((-sum(peso[q] * nt[q][0] for q in termos), -len(casadas), i,
                             r, tl, nt, casadas))
    out = {"query": query, "count": len(hits), "items": hits,
           "busca_por_palavras": termos}
    faltam_em_tudo = [q for q in termos if not any(nt[q][0] for nt in notas)]
    if faltam_em_tudo:
        out["termos_sem_correspondencia"] = faltam_em_tudo
    if len(hits) < 3 and parciais:
        parciais.sort(key=lambda x: x[:3])
        cands = []
        for *_, r, tl, nt, casadas in parciais[:max_candidatos]:
            falta = [q for q in termos if q not in casadas]
            diverge = _divergencias(falta, tl)
            c = dict(_linha(r, com_obs=False), bate=casadas, falta=falta,
                     outro_item=bool(diverge))
            variante = {q: nt[q][1] for q in casadas if nt[q][0] < 1.0}
            if variante:
                c["variante"] = variante
            if diverge:
                c["diverge"] = diverge
            cands.append(c)
        out["candidatos"] = cands
    if not hits:
        out["aviso"] = (
            "Nenhuma linha tem TODAS as palavras da busca. Isso NÃO prova que o item "
            "não existe, nem que um candidato É o item. Candidato com `outro_item: true` "
            "traz OUTRA medida, lugar ou formato (`diverge`): é outro item — diga ao "
            "cliente que a planilha não lista o que ele pediu e que a leitura do PDF "
            "pode tê-lo deixado passar. Nos outros, diga o que a linha traz e o que ela "
            "não diz (`falta`); `variante` é palavra parecida, não a mesma. Se não "
            "houver candidato, tente uma palavra só ou list_items antes de responder.")
    return out


def tool_search_items(job_id: str, query: str, max_hits: int = 20) -> dict:
    """Busca itens por palavras na descrição (qualquer ordem, sem acento).
    Ver `buscar_linhas` — é ela que decide; aqui só se abre a planilha."""
    wb = _open_planilha(job_id)
    if wb is None:
        return {"error": f"planilha do job {job_id} não encontrada"}
    try:
        linhas = list(_iter_orcamento_rows(wb))
    finally:
        wb.close()
    return buscar_linhas(linhas, query, max_hits=max_hits)


def tool_read_dxf_summary(job_id: str, dxf_filename: str = "") -> dict:
    """Estatísticas dos DXFs de um job — layers, blocos, walls.
    Se dxf_filename vazio, lista os arquivos disponíveis."""
    work = os.path.join(WORK_DIR, job_id)
    if not os.path.isdir(work):
        return {"error": f"work dir do job {job_id} não encontrado"}
    dxfs = [f for f in os.listdir(work) if f.lower().endswith(".dxf")]
    if not dxf_filename:
        return {"available_dxfs": dxfs}
    target = next((f for f in dxfs if dxf_filename.lower() in f.lower()), None)
    if not target:
        return {"error": f"dxf '{dxf_filename}' não encontrado entre {dxfs}"}
    try:
        from dwg_extractor import extract_from_file
        result = extract_from_file(os.path.join(work, target))
        # Resumo compacto pra não estourar contexto
        return {
            "filename": target,
            "blocks_count": len(result.get("blocks", [])),
            "walls_count": len(result.get("walls", [])),
            "layers": result.get("layers", [])[:50],
            "areas_m2": result.get("areas_m2", []),
        }
    except Exception as e:
        return {"error": f"erro ao ler DXF: {type(e).__name__}: {e}"}


def tool_get_sinapi_codes(familia_code: str, query: str = "",
                           top_k: int = 5) -> dict:
    """Lista códigos SINAPI mapeados pra uma família. Se `query` informada,
    filtra por similaridade simples na descrição (palavras-chave)."""
    if not familia_code:
        return {"error": "familia_code obrigatório"}
    try:
        # Pega o id da família
        url = (f"{SUPABASE_URL}/rest/v1/catalog_familia"
               f"?select=id,name&code=eq.{familia_code}")
        req = urllib.request.Request(url, method="GET")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_SERVICE_ROLE_KEY}")
        req.add_header("Accept", "application/json")
        resp = urllib.request.urlopen(req, timeout=10)
        fams = json.loads(resp.read().decode("utf-8"))
        if not fams:
            return {"error": f"família '{familia_code}' não encontrada"}
        familia_id = fams[0]["id"]
        familia_nome = fams[0]["name"]

        # Pega SINAPIs da família
        url = (f"{SUPABASE_URL}/rest/v1/sinapi_composicao"
               f"?select=codigo,descricao,unidade&familia_id=eq.{familia_id}"
               f"&limit=50")
        req = urllib.request.Request(url, method="GET")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_SERVICE_ROLE_KEY}")
        req.add_header("Accept", "application/json")
        resp = urllib.request.urlopen(req, timeout=10)
        rows = json.loads(resp.read().decode("utf-8"))

        # Se query informada, ranqueia por keyword overlap
        if query and rows:
            q_tokens = set(re.findall(r"\w{4,}", query.lower()))
            for r in rows:
                d_tokens = set(re.findall(r"\w{4,}", (r.get("descricao") or "").lower()))
                r["_score"] = len(q_tokens & d_tokens)
            rows.sort(key=lambda r: -r.get("_score", 0))
            for r in rows:
                r.pop("_score", None)

        return {
            "familia_code": familia_code,
            "familia_nome": familia_nome,
            "total_sinapis_mapeados": len(rows),
            "top": rows[:top_k],
        }
    except Exception as e:
        return {"error": f"erro: {type(e).__name__}: {e}"}


def tool_check_density_for_item(job_id: str, item_num: str,
                                 typology: str = "office") -> dict:
    """Roda check_density_anomaly num item específico da planilha."""
    details = tool_get_item_details(job_id, item_num)
    if "error" in details:
        return details
    # Busca area do projeto no Supabase
    project = _supabase_select_project(job_id)
    ref_area = (project.get("layout_area") or project.get("total_area") or 0) if project else 0
    typ = (project.get("typology") if project else None) or typology

    # cria objeto-like pra check
    class _Item:
        pass
    it = _Item()
    it.description = details["description"]
    it.unit = details["unit"]
    try:
        it.quantity = float(details["quantity"])
    except Exception:
        it.quantity = 0

    try:
        from density_calibration import check_density_anomaly
        is_anom, msg = check_density_anomaly(it, float(ref_area or 0), typology=typ)
    except Exception as e:
        return {"error": f"check error: {e}"}
    return {
        "item_num": item_num,
        "description": details["description"],
        "qty": details["quantity"],
        "unit": details["unit"],
        "ref_area_m2": ref_area,
        "typology": typ,
        "is_anomaly": is_anom,
        "alert": msg or "sem alerta — densidade dentro do padrão (ou sem benchmark)",
    }


def tool_list_supplier_quotes(job_id: str) -> dict:
    """Lista cotações de fornecedores submetidas neste projeto.
    Retorna: [{supplier_name, n_items_quoted, total_bruto, total_material,
    total_mao_obra}].
    """
    try:
        url = (f"{SUPABASE_URL}/rest/v1/project_supplier_quotes"
               f"?job_id=eq.{job_id}"
               f"&select=id,supplier_name,n_items_quoted,total_bruto,"
               f"total_material,total_mao_obra,status"
               f"&order=uploaded_at.asc")
        req = urllib.request.Request(url, method="GET")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_SERVICE_ROLE_KEY}")
        resp = urllib.request.urlopen(req, timeout=8)
        quotes = json.loads(resp.read().decode("utf-8"))
        return {
            "job_id": job_id,
            "n_quotes": len(quotes),
            "quotes": quotes,
        }
    except Exception as e:
        return {"error": str(e)}


def tool_compare_supplier_quotes(job_id: str) -> dict:
    """Compara as cotações de fornecedores deste projeto entre si e contra
    o quantitativo original do AI.arq.

    Retorna análise completa: ranking por total pareado, cobertura de cada
    fornecedor, maiores discrepâncias item-a-item, e (se aplicável) itens
    do quantitativo que fornecedores esqueceram.
    """
    try:
        from supplier_quote_compare import compare_quotes
    except ImportError:
        return {"error": "supplier_quote_compare indisponível"}

    # Busca quotes
    try:
        url = (f"{SUPABASE_URL}/rest/v1/project_supplier_quotes"
               f"?job_id=eq.{job_id}&select=*&order=uploaded_at.asc")
        req = urllib.request.Request(url, method="GET")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_SERVICE_ROLE_KEY}")
        resp = urllib.request.urlopen(req, timeout=8)
        quotes_raw = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}

    if len(quotes_raw) < 2:
        return {"error": "precisa de pelo menos 2 cotações"}

    quotes = [{
        "supplier_name": q["supplier_name"],
        "n_items_quoted": q.get("n_items_quoted", 0),
        "total_bruto": float(q.get("total_bruto") or 0),
        "total_material": float(q.get("total_material") or 0),
        "total_mao_obra": float(q.get("total_mao_obra") or 0),
        "items": q.get("items") or [],
    } for q in quotes_raw]

    # Busca reference items
    reference_items = None
    try:
        ref_url = (f"{SUPABASE_URL}/rest/v1/project_items"
                   f"?job_id=eq.{job_id}&select=description,unit,quantity")
        ref_req = urllib.request.Request(ref_url, method="GET")
        ref_req.add_header("apikey", SUPABASE_KEY)
        ref_req.add_header("Authorization", f"Bearer {SUPABASE_SERVICE_ROLE_KEY}")
        ref_resp = urllib.request.urlopen(ref_req, timeout=8)
        reference_items = json.loads(ref_resp.read().decode("utf-8"))
    except Exception:
        pass

    analysis = compare_quotes(quotes, reference_items=reference_items)

    # Retorna versão compacta (o agente não precisa de tudo)
    return {
        "suppliers": analysis["suppliers"],
        "n_items_comparados": analysis["paired_count"],
        "ranking": [{"fornecedor": s, "total_pareado": t}
                    for s, t in analysis["ranking"]],
        "cobertura_por_fornecedor": {
            sup: f"{cov['pct']:.0f}% ({cov['n_priced']}/{cov['n_total_unique']})"
            for sup, cov in analysis["coverage"].items()
        },
        "top_10_discrepancias": [
            {
                "descricao": d["desc"],
                "diferenca_pct": f"{d['pct_diff']:.0f}%",
                "mais_barato": d["cheapest"],
                "mais_caro": d["most_expensive"],
                "valores": {k: f"R$ {v:,.2f}" for k, v in d["totals"].items()},
            }
            for d in analysis["biggest_discrepancies"][:10]
        ],
        "vs_quantitativo_aiarq": analysis.get("reference_check", {}).get("summary")
            if analysis.get("reference_check") else None,
    }


def tool_check_market_heuristics(description: str, typology: str = "office") -> dict:
    """Checa um item contra as heurísticas de mercado (dispersão, cobertura,
    share MAT/MO) extraídas de orçamentos reais anonimizados.

    Retorna alertas curtos + métricas agregadas. NUNCA valor absoluto.
    """
    try:
        from market_heuristics import (
            categorize_item, check_item_anomaly, metricas_para_mostrar,
        )
    except ImportError:
        return {"error": "market_heuristics indisponível"}

    if not description or len(description.strip()) < 3:
        return {"error": "descrição muito curta"}

    cat = categorize_item(description)
    alertas = check_item_anomaly({"description": description, "unit": ""},
                                   typology=typology)

    # 🩸 18/09/2026 — este dicionário dizia "agregado de orçamentos reais" no
    # plural e entregava "±X%" ao modelo com a base de UM comparativo. Agora os
    # números só vêm com lastro (regra única em `metricas_para_mostrar`), e a
    # base vem SEMPRE, pra o modelo dizer ao cliente o tamanho dela.
    m = metricas_para_mostrar(cat, typology)
    _n = max((b.get("n_fontes", 0) for b in m["base"].values()), default=0)
    _lastro = any(b.get("lastro") for b in m["base"].values())
    return {
        "categoria": cat,
        "tipologia": typology,
        "alertas": alertas,
        "base": m["base"],
        "dispersao_mercado": m["dispersao"],
        "share_mat_mo_tipico": m["share_mat_mo"],
        "cobertura_tipica": m["cobertura"],
        "obs": (f"Base: {_n} projeto(s)-fonte. Números só aparecem com pelo menos "
                f"{m['base']['dispersao']['minimo']} — SEM lastro, diga ao cliente "
                f"que ainda não há base pra estimar variação, e NÃO invente intervalo."
                if not _lastro else
                f"Base: {_n} projeto(s)-fonte, anônima. Use pra orientar sobre "
                f"variação esperada, NÃO como valor de referência deste projeto — "
                f"e cite o tamanho da base."),
    }


def _supabase_select_project(job_id: str) -> Optional[dict]:
    try:
        url = f"{SUPABASE_URL}/rest/v1/projects?job_id=eq.{job_id}&select=*"
        req = urllib.request.Request(url, method="GET")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_SERVICE_ROLE_KEY}")
        req.add_header("Accept", "application/json")
        resp = urllib.request.urlopen(req, timeout=8)
        rows = json.loads(resp.read().decode("utf-8"))
        return rows[0] if rows else None
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════
#  Schema das tools (formato Anthropic Tool Use)
# ════════════════════════════════════════════════════════════════

TOOLS = [
    {
        "name": "list_items",
        "description": "Lista itens da planilha de quantitativos (número, descrição, unidade, quantidade e selo). O campo `selo` é o que a PLANILHA marcou em cada linha: 'medido' (branco, medido do CAD), 'estimado' (laranja, pra revisar) ou 'metadado' (linhas 0.x da capa, não é serviço). Use pra ter visão geral do que existe.",
        "input_schema": {
            "type": "object",
            "properties": {
                "max_items": {"type": "integer", "description": "Limite de itens (default 200)"},
            },
        },
    },
    {
        "name": "get_item_details",
        "description": "Retorna dados completos de UM item, incluindo observação inteira (cita fonte/layer CAD/consolidador) E classificação automática (capítulo > grupo > família) e atributos folha extraídos (cor, PD, marca, dimensão, código produto). Use SEMPRE que o usuário perguntar 'por que tem X' ou pedir detalhes de um item específico — a categoria + atributos enriquecem a explicação.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item_num": {"type": "string", "description": "Número do item, ex: '6.3' ou '8.1'"},
            },
            "required": ["item_num"],
        },
    },
    {
        "name": "search_items",
        "description": "Busca itens da planilha por PALAVRAS na descrição — em qualquer ordem, sem acento nem maiúscula (4x2\", 2P+T e 10A são normalizados) —, com o mesmo campo `selo` de list_items ('medido', 'estimado' ou 'metadado'). Use quando o usuário menciona um termo (LED, alvenaria, forro etc). `items` traz as linhas com TODAS as palavras iguais; se vier vazio ou curto, `candidatos` traz as mais parecidas com o que `bate`, o que `falta`, a `variante` (palavra parecida, não a mesma: portão não é porta) e `outro_item: true` quando a linha diz OUTRA medida, lugar ou formato (`diverge`: 4x2 onde se pediu 4x4) — aí é outro item, não o pedido. `termos_sem_correspondencia` diz as palavras que não estão em linha nenhuma. Busque UM item por vez (se o cliente colar várias linhas de legenda, uma busca por linha).",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Palavras do item (ex.: 'tomada caixa 4x2', 'luminária emergência')"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_dxf_summary",
        "description": "Estatísticas de um DXF (layers, qtd de blocos, walls). Sem dxf_filename, lista os DXFs do projeto.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dxf_filename": {"type": "string", "description": "Nome (ou parte) do DXF. Vazio pra listar."},
            },
        },
    },
    {
        "name": "check_density_for_item",
        "description": "Compara a densidade (qty/área) de um item contra o padrão histórico da mesma tipologia. Usa pra justificar quantidades.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item_num": {"type": "string", "description": "Número do item"},
            },
            "required": ["item_num"],
        },
    },
    {
        "name": "get_sinapi_codes",
        "description": "Lista códigos SINAPI mapeados pra uma família do catálogo. Use quando o cliente perguntar 'qual código SINAPI desse item?' ou pedir referência oficial pra compra. Fornece familia_code (você obtém de get_item_details.categoria.familia) e opcionalmente query (descrição original do item) pra ranqueamento por similaridade.",
        "input_schema": {
            "type": "object",
            "properties": {
                "familia_code": {"type": "string", "description": "Código da família, ex: 'fam_pint_acrilica' (vem de get_item_details.categoria.familia)"},
                "query": {"type": "string", "description": "Descrição do item original pra ranquear melhores matches (opcional)"},
                "top_k": {"type": "integer", "description": "Quantos códigos retornar (default 5)"},
            },
            "required": ["familia_code"],
        },
    },
    {
        "name": "list_supplier_quotes",
        "description": "Lista as cotações de fornecedores que o cliente enviou pra este projeto (planilhas de orçamento recebidas dos fornecedores). Use quando o cliente perguntar 'quais fornecedores já mandaram proposta?', 'quantas cotações eu tenho?', 'qual fornecedor é mais barato?' (pra este último, use depois compare_supplier_quotes).",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "compare_supplier_quotes",
        "description": "Compara todas as cotações de fornecedores submetidas no projeto. Retorna ranking por total pareado (só itens que todos orçaram), cobertura de cada fornecedor, top 10 maiores discrepâncias item-a-item, e verificação contra o quantitativo original (itens esquecidos, divergências de quantidade). Use quando o cliente perguntar 'compara os orçamentos', 'qual o mais caro em elétrica?', 'quem esqueceu ar-condicionado?'.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "check_market_heuristics",
        "description": "Checa heurísticas agregadas de mercado (dispersão de preço entre fornecedores, share típico de material vs mão de obra, padrão de cobertura) pra uma categoria de item. Use quando o cliente perguntar 'quanto varia o preço disso?', 'é normal esse item ser 80% material?', 'esse serviço costuma ser esquecido?'. Responde SEM valores absolutos — só ratios e percentuais, e SÓ quando a base tem lastro: a resposta traz `base` (nº de projetos-fonte por métrica). Sem lastro os números vêm nulos — diga ao cliente que ainda não há base pra estimar variação e não invente intervalo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "Descrição do item (ex: 'demolição de drywall', 'luminária LED 60x60')"},
                "typology": {"type": "string", "description": "office|residential|retail|hospital|educational (default office)"},
            },
            "required": ["description"],
        },
    },
]


def _dispatch_tool(name: str, job_id: str, tool_input: dict) -> Any:
    if name == "list_items":
        return tool_list_items(job_id, tool_input.get("max_items", 200))
    if name == "get_item_details":
        return tool_get_item_details(job_id, tool_input["item_num"])
    if name == "search_items":
        return tool_search_items(job_id, tool_input["query"])
    if name == "read_dxf_summary":
        return tool_read_dxf_summary(job_id, tool_input.get("dxf_filename", ""))
    if name == "check_density_for_item":
        return tool_check_density_for_item(job_id, tool_input["item_num"])
    if name == "get_sinapi_codes":
        return tool_get_sinapi_codes(
            tool_input["familia_code"],
            tool_input.get("query", ""),
            tool_input.get("top_k", 5),
        )
    if name == "list_supplier_quotes":
        return tool_list_supplier_quotes(job_id)
    if name == "compare_supplier_quotes":
        return tool_compare_supplier_quotes(job_id)
    if name == "check_market_heuristics":
        return tool_check_market_heuristics(
            tool_input["description"],
            tool_input.get("typology", "office"),
        )
    return {"error": f"tool '{name}' desconhecida"}


# ════════════════════════════════════════════════════════════════
#  Loop do agente
# ════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """Você é o assistente do AI.arq — atende clientes que usam o site pra gerar orçamento de obra a partir de plantas (DWG/PDF).

CONTEXTO DESTA CONVERSA:
- O cliente está perguntando sobre UM projeto específico (job_id={job_id}).
- Você tem ferramentas pra ler a planilha gerada, buscar itens, ler DXFs e checar calibração.

REGRAS:
- Use as ferramentas pra investigar antes de responder. NUNCA invente número.
- Se uma ferramenta retornar erro (ex.: {{"error": ...}} — a planilha pode ter sumido após um reinício do servidor), NÃO chute um valor: diga que não conseguiu acessar agora e que é só recarregar/reprocessar. Nunca preencha um número que você não leu de uma ferramenta.
- MEDIDO vs ESTIMADO: ao citar uma quantidade, diga se o item está "✓ medido do CAD" ou "⚠ estimativa pra revisar" — e isso vem SÓ do campo `selo` que as ferramentas devolvem: ✓ apenas quando selo = "medido"; selo = "estimado" é ⚠; selo = "metadado" (linhas 0.x) não é quantidade de serviço. Ter número NÃO é ter medição. Num resumo, marque linha a linha pelo selo; se não tiver o selo de uma linha, não use ✓. Nunca apresente uma estimativa como certeza; deixe claro o que é chão firme e o que o usuário precisa conferir.
- 🪤 Em 15/09/2026 um resumo por disciplina pôs ✓ em ~20 linhas estimadas (alvenaria, pisos, vagas) só porque tinham número — e o cliente, orçamentista, leu isso como medido.
- As respostas ANTERIORES desta conversa (o histórico) podem ter marcado ✓ errado: antes de 15/09/2026 as ferramentas não entregavam o selo. Nunca repita um ✓ do histórico sem conferir o selo na ferramenta de novo.
- Se o resultado de uma ferramenta terminar com [RESULTADO CORTADO ...], a lista veio INCOMPLETA: diga isso ao cliente e não resuma nem conte o que não veio.
- O AI.arq NÃO precifica. Se pedirem preço, valor ou custo, explique que o quantitativo sai sem preço de propósito — quem precifica é o orçamentista, com o BDI e os fornecedores dele. Você ajuda com as quantidades, não com R$.
- E o AI.arq NÃO REVISA PROJETO. Se pedirem para validar dimensionamento, apontar erro de projeto, dizer se um rack está subdimensionado, se uma rota de cabo é inadequada, se a distância excede norma, se falta reserva técnica — NÃO dê o veredito. Você lê o desenho; você não lê a norma, não conhece a obra e não assina o projeto. Opinar sobre o dimensionamento de outra pessoa é estimativa vestida de análise técnica, e é onde errar sai mais caro pro cliente.
- O QUE FAZER NESSE CASO, em vez de recusar seco: entregue o que você TEM, que é muito. Diga o que está no desenho (quantidades, contagens, comprimentos por layer, o que o carimbo declara) e o que o desenho NÃO traz (falta cota, falta quadro, o item aparece sem especificação). Isso é insumo de verdade pro projetista decidir. Depois diga, numa frase e sem rodeio, que a validação do projeto é dele — a gente levanta, ele decide.
- 🪤 Isto vale mesmo quando o cliente descreve o pedido em detalhe e parece esperar a auditoria. Em 03/09/2026 um cliente mandou um briefing pedindo análise completa de um projeto de cabeamento (rack, rotas, interferências, norma) e a resposta saiu com "PROBLEMA → MOTIVO TÉCNICO → CORREÇÃO RECOMENDADA". Pedido detalhado não é autorização — é só um pedido detalhado.
- Quando citar um item, mencione o item_num e cite a observação que justifica a quantidade.
- BUSCA VAZIA NÃO PROVA QUE O ITEM NÃO EXISTE — e candidato parecido não prova que existe. Antes de responder, leia `candidatos` e `termos_sem_correspondencia` do search_items:
  • candidato com `outro_item: true` traz OUTRA medida, lugar ou formato (`diverge`: 4x2 onde se pediu 4x4, parede onde se pediu forro). É OUTRO item: diga que a planilha não lista o item pedido, que a leitura do PDF pode tê-lo deixado passar, e cite o candidato só como item diferente — nunca como "o seu item, com outra medida";
  • candidato sem `outro_item` com palavra em `falta`: diga o que a linha traz e o que ela não diz (ex.: "a planilha tem o conjunto tomada + interruptor paralelo em caixa 4x2, 8 un; a linha não traz a altura"). Palavra em `variante` é parecida, não a mesma (portão não é porta).
  🪤 Em 22/09/2026 o chat disse a uma cliente que o conjunto tomada + interruptor paralelo, que ESTAVA na planilha, não existia. E o primeiro conserto ia dizer a ela que a tomada 4x4 do forro, que a planilha NÃO tem, estava lá em caixa 4x2 — era a tomada de outra linha da legenda.
- Se o usuário perguntar "por que essa quantidade?", busca o item, leia a observação (que cita layer CAD ou processo de consolidação) e explique.
- LINHA DE ÁREA EM BRANCO TEM CONSERTO NA HORA — ofereça isso ANTES de qualquer outra saída. Se o cliente perguntar pela metragem que faltou num item de m² com quantidade ZERO de superfície horizontal (piso, forro, laje, contrapiso, revestimento de piso), diga que na tela de revisão, logo acima da lista de itens, existe um campo "Área total": informando a metragem ali, a planilha é refeita NA HORA, sem reprocessar e sem custo nenhum, e as linhas saem marcadas como "estimado (informado por você)". Só depois disso mencione reenviar em DXF ou preencher item por item — esses dois são caros e demorados.
- NÃO ofereça esse campo pra pintura de PAREDE, alvenaria, chapisco/reboco ou qualquer item que dependa da ALTURA: a área total não preenche esses. Ali o que falta é o pé-direito, e ele só fecha a conta se houver parede medida em metro linear. E NUNCA prometa QUANTAS linhas serão preenchidas — quem decide item a item é o motor.
- NÃO INVENTE CAMPO, BOTÃO OU TELA. Na tela de revisão existe UM campo só: "Área total". NÃO existe campo de altura nem de pé-direito ali. O pé-direito se informa na PÁGINA DO PROJETO (a caixa "informe o pé-direito", quando ela aparece) ou num novo envio. Se você não tem certeza de que um controle existe, descreva o que fazer sem citar botão nenhum.
- Respostas curtas (3-5 frases). Use linguagem comum, sem jargão técnico de IA.
- Se a pergunta sair do escopo do quantitativo, redirecione: "Não tenho acesso a isso, posso ajudar com itens da sua planilha?"
"""


_BUCKET_DAS_PRANCHAS = "aiarq-pranchas"  # o PRANCHAS_BUCKET de main.py (um guarda confere)


def _pedir_json_ao_supabase(url: str, corpo: Optional[dict] = None):
    req = urllib.request.Request(
        url, data=None if corpo is None else json.dumps(corpo).encode("utf-8"),
        method="GET" if corpo is None else "POST")
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_SERVICE_ROLE_KEY}")
    req.add_header("Accept", "application/json")
    if corpo is not None:
        req.add_header("Content-Type", "application/json")
    return json.loads(urllib.request.urlopen(req, timeout=8).read().decode("utf-8"))


def _ha_cad_guardado(job_id: str) -> Optional[bool]:
    """True se o projeto tem .dxf/.dwg no Storage OU linha medida do DXF
    (origem dxf_geom); False se as duas fontes responderam e não há; None se
    alguma não respondeu. Falta de resposta não vira "não há CAD"."""
    from urllib.parse import quote
    try:
        objs = _pedir_json_ao_supabase(
            f"{SUPABASE_URL}/storage/v1/object/list/{_BUCKET_DAS_PRANCHAS}",
            {"prefix": f"{job_id}/", "limit": 1000})
        if not isinstance(objs, list):
            return None
        if any(str(o.get("name") or "").lower().endswith((".dxf", ".dwg"))
               for o in objs if isinstance(o, dict)):
            return True
        linhas = _pedir_json_ao_supabase(
            f"{SUPABASE_URL}/rest/v1/project_items?job_id=eq.{quote(str(job_id))}"
            f"&origem=eq.dxf_geom&select=item_num&limit=1")
        if not isinstance(linhas, list):
            return None
        return bool(linhas)
    except Exception as e:
        print(f"[agent] CAD guardado de {job_id}: {e}")
        return None


def tipos_de_arquivo_do_projeto(job_id: str) -> Optional[dict]:
    """{"pdf": n, "dxf": n, "dwg": n} que o cliente enviou, ou None se não deu
    pra confirmar. Síncrona (rede) — a rota chama no threadpool, nunca no laço.

    🩸 22/09/2026 (revisão): `projects.file_types` está VELHO em projetos de
    antes do conserto do /add-file de 03/09 — diz só PDF, e o Storage tem DWG
    (num deles, 12 linhas medidas do DXF na planilha). Confiar só nele faria o
    chat esconder read_dxf_summary e jurar "aqui não existe layer" a quem
    mandou DWG. Só-PDF agora exige as duas fontes concordando; se discordam
    ou uma não responde, volta None (o ramo "não consegui confirmar")."""
    try:
        from urllib.parse import quote
        rows = _pedir_json_ao_supabase(
            f"{SUPABASE_URL}/rest/v1/projects?job_id=eq.{quote(str(job_id))}"
            f"&select=file_types")
        ft = rows[0].get("file_types") if rows else None
    except Exception as e:
        print(f"[agent] tipos de arquivo de {job_id}: {e}")
        return None
    if not isinstance(ft, dict):
        return None
    if projeto_so_pdf(ft):
        cad = _ha_cad_guardado(job_id)
        if cad is not False:
            print(f"[agent] {job_id}: file_types diz só PDF, mas "
                  f"{'há CAD guardado' if cad else 'não deu pra confirmar'} — não afirmo só-PDF")
            return None
    return ft


def _conta_do_tipo(tipos, chave) -> int:
    try:
        return max(0, int((tipos or {}).get(chave) or 0))
    except (TypeError, ValueError):
        return 0


def projeto_so_pdf(tipos) -> bool:
    """Veio PDF e nenhum CAD. Sem a informação (None), NÃO é só-PDF: falta de
    dado não pode esconder a ferramenta de DXF de quem mandou DXF."""
    if not isinstance(tipos, dict):
        return False
    return (_conta_do_tipo(tipos, "pdf") > 0 and _conta_do_tipo(tipos, "dxf") == 0
            and _conta_do_tipo(tipos, "dwg") == 0)


def contexto_dos_arquivos(tipos) -> str:
    """O que o modelo precisa saber dos arquivos ANTES de explicar uma ausência.

    🩸 22/09/2026 (job 844603fb): projeto de 1 PDF e nenhum CAD, e o chat culpou
    "os layers do DWG", "um arquivo DXF separado" e ofereceu "listar os DXFs do
    projeto". O prompt nunca dizia o que o cliente enviou, e o modelo chutou.
    """
    if not isinstance(tipos, dict):
        return ("\n\nARQUIVOS DESTE PROJETO: não consegui confirmar agora quais tipos "
                "de arquivo vieram. Não afirme que existe DWG/DXF nem fale de layer "
                "ou bloco sem antes ver o DXF pela ferramenta read_dxf_summary.")
    pdf, dxf, dwg = (_conta_do_tipo(tipos, k) for k in ("pdf", "dxf", "dwg"))
    if projeto_so_pdf(tipos):
        return ("\n\nARQUIVOS DESTE PROJETO: só PDF (%d arquivo%s), NENHUM DWG ou DXF. "
                "Aqui não existe layer, bloco nem DXF: nunca explique a falta de um "
                "item por layer, bloco ou DWG, e não ofereça listar DXF. No PDF a IA "
                "lê a imagem da prancha, então toda quantidade é estimativa (nunca "
                "medida) e um símbolo pode ter passado despercebido na leitura. Pra "
                "medir de verdade, o caminho é enviar o DXF da mesma prancha."
                % (pdf, "" if pdf == 1 else "s"))
    return ("\n\nARQUIVOS DESTE PROJETO: %d DWG, %d DXF e %d PDF. O que veio de PDF "
            "é leitura da imagem (estimativa); layer e bloco só existem nos DWG/DXF."
            % (dwg, dxf, pdf))


def _log_conversation(job_id: str, question: str, answer: str,
                      tool_calls: list, iterations: int, duration_ms: int,
                      error: str = "") -> None:
    """Persiste a conversa em agent_conversations pra auditoria/admin."""
    try:
        record = {
            "job_id": job_id,
            "question": question[:2000],
            "answer": (answer or "")[:5000],
            "tool_calls": tool_calls[:30],  # limita pra não estourar
            "iterations": iterations,
            "duration_ms": duration_ms,
            "error": (error or "")[:500] or None,
        }
        url = f"{SUPABASE_URL}/rest/v1/agent_conversations"
        body = json.dumps(record, default=str, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_SERVICE_ROLE_KEY}")
        req.add_header("Content-Type", "application/json")
        req.add_header("Prefer", "return=minimal")
        urllib.request.urlopen(req, timeout=8)
    except Exception as e:
        print(f"[agent] log error: {e}")
    # 🚨 O chat é o melhor detector de buraco do motor que a gente tem — e era
    # CEGO. Em 21/07 um cliente reclamou de eletroduto faltando e a resposta
    # explicou a causa raiz ("a planta não tem polilinha fechada"); ficou 9 dias
    # numa tabela sem ninguém ler. Das 11 conversas de sempre, 3 eram falha real
    # de medição, com job_id anexado. Agora isso vira alerta. (30/07/2026)
    try:
        _alerta_lacuna(job_id, question)
    except Exception as _e:
        print(f"[agent] alerta de lacuna falhou (nao-fatal): {_e}")


# Sinais de que o cliente está APONTANDO UMA FALHA, não tirando dúvida.
_LACUNA_RE = re.compile(
    r"(n[ãa]o\s+(tem|veio|apareceu|consta|calculou|mediu|bateu)|"
    r"falt(a|ou|aram|ando)|sem\s+(quantitativo|medi[çc][ãa]o|quantidade)|"
    # 🪤 03/09 — o plural NAO casava: "os itens ESTAO zerados na tabela" e
    # queixa de manual e passava batido, porque so havia `est[áa]` no
    # singular. Achado pelo controle positivo do guarda do alarme.
    r"(t[áãa]o?|est[áãa]o?)\s+(em\s+branco|zerad|vazi|errad)|"
    r"n[ãa]o\s+apresentou|incomplet|"
    r"(pq|por\s*que|porqu[êe])\s+(n[ãa]o|nao))",
    re.IGNORECASE,
)


# O que é NOSSO entregável. A queixa só vira alerta se estiver perto de um
# destes — senão é o cliente falando do projeto dele, não da nossa planilha.
_NOSSO_ENTREGAVEL_RE = re.compile(
    r"planilha|quantitativ|quantidade|medi[çc][ãa]o|medid|"
    r"\bitem\b|\bitens\b|\blinha|tabela|or[çc]amento|"
    r"\bm2\b|m²|metragem|\b[áa]rea\b|relat[óo]rio|xlsx|excel",
    re.IGNORECASE,
)
# 🪤 Os `\b` acima TÊM que ser barra invertida + b. Escrevendo este arquivo por
# heredoc eu transformei `\b` em caractere de BACKSPACE (0x08) e o regex passou
# a nunca casar "item" — alarme cego, sem erro nenhum. Foi o SEXTO escape errado
# do mesmo tipo em 03/09/2026. Este assert custa nada e reprova na importação,
# antes de qualquer cliente perguntar.
assert _NOSSO_ENTREGAVEL_RE.search("item") and _NOSSO_ENTREGAVEL_RE.search("área"), (
    "_NOSSO_ENTREGAVEL_RE nao casa o vocabulario basico — escape quebrado?")


def _alerta_lacuna(job_id: str, question: str) -> None:
    """Avisa o dono quando o cliente aponta falta de medição no chat.

    Best-effort e silencioso: nunca pode atrapalhar a resposta ao cliente.
    Deduplica por job (1 alerta por projeto) pra não virar spam em conversa
    longa — o objetivo é sinalizar o projeto, não cada frase.
    """
    # 🩸 03/09/2026 — ESTE ALARME LEU O CHECKLIST DO CLIENTE COMO QUEIXA.
    # O cliente-73 (job eebe543a) mandou um briefing pedindo auditoria do projeto de
    # rede DELE, com itens tipo "Falta de reserva técnica" e "Falta de espaço
    # para expansão futura". O `falt(a|ou)` casou, e o Pedro recebeu
    # "Chat: cliente diz que faltou medição" — coisa que ele não disse.
    # 🔑 A palavra sozinha não distingue "faltou medição NA PLANILHA" de "falta
    # reserva técnica NO PROJETO DELE". O que distingue é a queixa estar perto
    # de algo NOSSO. Alarme falso gasta a atenção do Pedro, que é o recurso
    # mais escasso da casa — e treina ele a ignorar os verdadeiros.
    if not question or not _LACUNA_RE.search(question):
        return
    _m = _LACUNA_RE.search(question)
    _perto = question[max(0, _m.start() - 90):_m.end() + 90]
    if not _NOSSO_ENTREGAVEL_RE.search(_perto):
        return
    try:
        from main import _notify_admin, _email_auto_registrar, _email_auto_ja_enviado, NOTIFY_EMAIL
    except Exception:
        return
    _ref = f"chat:{job_id}"
    if _email_auto_ja_enviado(NOTIFY_EMAIL, "alerta_chat_lacuna", ref=_ref):
        return
    import html as _h
    _corpo = (
        f"<b>Um cliente apontou falta de medição pelo chat.</b><br><br>"
        f"<b>Pergunta:</b> {_h.escape(question[:400])}<br>"
        f"<b>Projeto:</b> {_h.escape(job_id)}<br><br>"
        f"Isso costuma ser buraco do motor, não dúvida do cliente — vale olhar "
        f"o que a planilha deixou de medir nesse projeto.<br><br>"
        f'<a href="https://ai.arq.br/admin.html#projetos">Abrir no painel</a>'
    )
    if _notify_admin(f"Chat: cliente diz que faltou medição — {job_id}", _corpo):
        _email_auto_registrar(NOTIFY_EMAIL, "alerta_chat_lacuna", ref=_ref)


_TETO_RESULTADO_FERRAMENTA = 8000


def _conteudo_da_ferramenta(result, teto: int = _TETO_RESULTADO_FERRAMENTA) -> str:
    """JSON do resultado da ferramenta pro modelo — e, se passar do teto, AVISA.

    🩸 15/09/2026: o corte em 8.000 caracteres era calado. Numa planilha de 182
    linhas o `list_items` mostrava ~50 e o modelo resumia "por disciplina" como
    se fosse a planilha inteira. O `selo` novo ainda somou ~20 caracteres por
    linha (52 → 47 linhas vistas, medido pela revisão). Cortar continua
    necessário; esconder que cortou, não."""
    txt = json.dumps(result, default=str, ensure_ascii=False)
    if len(txt) <= teto:
        return txt
    return (txt[:teto]
            + "\n\n[RESULTADO CORTADO: passou de %d caracteres (%d no total) e o resto "
              "NÃO veio. Não resuma nem conte o que não veio: diga que a lista está "
              "incompleta e use search_items por termo pra ver o restante.]" % (teto, len(txt)))


def ask(job_id: str, question: str, max_iterations: int = 8,
        history: Optional[list] = None,
        tipos_de_arquivo: Optional[dict] = None) -> dict:
    """Roda o loop do agente até ele dar resposta final.

    Args:
        job_id: identificador do projeto (escopo das tools)
        question: pergunta atual do cliente
        history: opcional, lista de {role, content} de turnos anteriores
                 da MESMA conversa. Permite o cliente perguntar "e o item 3.4?"
                 como continuação. Se None, conversa inicia do zero.
        tipos_de_arquivo: {"pdf": n, "dxf": n, "dwg": n} do projeto (a rota lê
                 com `tipos_de_arquivo_do_projeto`). None = não se sabe, e o
                 prompt manda não afirmar CAD nenhum. Só-PDF esconde a
                 ferramenta de DXF — não há DXF pra ler.

    Retorna {answer, tool_calls: [(name, input, result)...], iterations}.
    Loga conversa em agent_conversations no Supabase.
    """
    import time as _t
    t0 = _t.time()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        result = {"answer": "API key não configurada.", "tool_calls": [], "iterations": 0}
        _log_conversation(job_id, question, result["answer"], [], 0,
                          int((_t.time()-t0)*1000), "no api key")
        return result

    try:
        import anthropic
    except ImportError:
        result = {"answer": "SDK anthropic não instalado.", "tool_calls": [], "iterations": 0}
        _log_conversation(job_id, question, result["answer"], [], 0,
                          int((_t.time()-t0)*1000), "no anthropic SDK")
        return result

    client = anthropic.Anthropic(api_key=api_key)

    # Monta histórico — turnos anteriores + pergunta atual.
    # Filtra cada entrada do history pra ficar só com {role, content} string
    # (sem tool_use blocks intermediários, que não fazem sentido fora da
    # iteração original e podem confundir o modelo se não pareados com tool_result).
    messages: list = []
    if history:
        for turn in history[-20:]:  # limita pra não estourar contexto
            role = turn.get("role")
            content = turn.get("content")
            if role in ("user", "assistant") and isinstance(content, str) and content.strip():
                messages.append({"role": role, "content": content.strip()[:4000]})
    messages.append({"role": "user", "content": question})
    tool_calls_log = []
    final_answer = ""
    # 🩸 03/09/2026 — A RESPOSTA SAÍA CORTADA NO MEIO DA PALAVRA, E CALADA.
    # Cliente `cliente-11@` (job eebe543a) pediu uma análise longa; a
    # resposta bateu no teto de 2.000 tokens e terminou em "O projeto usa dois
    # sím". O `stop_reason` da API diz `max_tokens` — e não era lido em lugar
    # NENHUM deste arquivo. A gente entregava o pedaço como se fosse a resposta.
    # 🔑 Duas defesas, porque teto maior sozinho só empurra o problema pra
    # frente:
    #   • se cortou, PEDE PRA CONTINUAR de onde parou (até 2 vezes);
    #   • se ainda assim cortar, DIZ ao cliente que cortou.
    # Resposta incompleta avisada é utilizável; resposta incompleta calada vira
    # decisão errada com a nossa assinatura embaixo.
    _MAX_CONTINUACOES = 2
    _partes_cortadas = []
    _continuacoes = 0
    _ficou_truncada = False

    # 22/09/2026 (job 844603fb): o modelo precisa saber o que o cliente ENVIOU
    # antes de explicar por que um item falta — senão culpa "layer do DWG" num
    # projeto que nunca teve DWG.
    _system = SYSTEM_PROMPT.format(job_id=job_id) + contexto_dos_arquivos(tipos_de_arquivo)
    _ferramentas = ([t for t in TOOLS if t["name"] != "read_dxf_summary"]
                    if projeto_so_pdf(tipos_de_arquivo) else TOOLS)

    from llm_retry import call_with_retry
    for it in range(max_iterations):
        try:
            resp = call_with_retry(
                client,
                tag=f"agent:job={job_id}",
                max_retries=3,
                model="claude-sonnet-4-6",
                max_tokens=4000,
                system=_system,
                tools=_ferramentas,
                messages=messages,
            )
        except Exception as e:
            err_msg = f"Erro na chamada Claude: {type(e).__name__}: {e}"
            _log_conversation(job_id, question, err_msg, tool_calls_log, it,
                              int((_t.time()-t0)*1000), str(e)[:300])
            return {"answer": err_msg, "tool_calls": tool_calls_log,
                    "iterations": it}

        # Coleta texto + tool_use blocks
        text_chunks = []
        tool_uses = []
        for block in resp.content:
            if block.type == "text":
                text_chunks.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append(block)

        # Se não houve tool_use, é a resposta final
        if not tool_uses:
            final_answer = "\n".join(text_chunks).strip()
            if getattr(resp, "stop_reason", None) == "max_tokens":
                if _continuacoes < _MAX_CONTINUACOES and it < max_iterations - 1:
                    _continuacoes += 1
                    _partes_cortadas.append(final_answer)
                    messages.append({"role": "assistant", "content": final_answer})
                    messages.append({"role": "user", "content":
                                     "Sua resposta foi cortada no limite de "
                                     "tamanho. Continue EXATAMENTE de onde parou, "
                                     "sem repetir o que já escreveu e sem "
                                     "recomeçar."})
                    final_answer = ""
                    continue
                _ficou_truncada = True
            break

        # Adiciona a resposta do assistant ao histórico
        messages.append({"role": "assistant", "content": resp.content})

        # Executa cada tool e devolve o resultado
        tool_results = []
        for tu in tool_uses:
            try:
                result = _dispatch_tool(tu.name, job_id, tu.input)
            except Exception as e:
                result = {"error": f"tool exception: {e}"}
            tool_calls_log.append({
                "name": tu.name, "input": tu.input,
                "result_preview": json.dumps(result, default=str, ensure_ascii=False)[:300],
            })
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": _conteudo_da_ferramenta(result),
            })
        messages.append({"role": "user", "content": tool_results})

    if _partes_cortadas:
        final_answer = "".join(_partes_cortadas) + final_answer
    if not final_answer:
        final_answer = "Não consegui formular uma resposta após várias iterações."
    if _ficou_truncada:
        final_answer += (
            "\n\n---\n\n⚠ **Esta resposta foi cortada no limite de tamanho** — "
            "ela está incompleta. Pergunte de novo pedindo a continuação de um "
            "tópico específico (ex.: \"continue a partir do PROBLEMA 1\") que eu "
            "retomo daí.")

    duration_ms = int((_t.time() - t0) * 1000)
    _log_conversation(job_id, question, final_answer, tool_calls_log,
                      it + 1, duration_ms)

    return {
        "answer": final_answer,
        "tool_calls": tool_calls_log,
        "iterations": it + 1,
        "duration_ms": duration_ms,
    }
