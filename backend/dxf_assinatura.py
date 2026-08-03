# -*- coding: utf-8 -*-
"""Assinatura de conteúdo de um DXF — pra saber se dois envios são o MESMO desenho.

Pedido do Pedro (03/08/2026): *"dá pra ler o projeto dentro rapidamente tb antes
de fazer né? aí já avisa o cliente pra subir dentro do mesmo ou não"*.

A sugestão por NOME de arquivo já está no ar e resolve o caso comum
(`BOMBEIRO 01 Rev B.dwg` × `.dxf`). Ela não resolve o caso em que o cliente
RENOMEIA — que é justamente quando ele mais precisa da ajuda, porque aí nem ele
lembra que já mandou.

🔒 Lê só o COMEÇO do arquivo. As duas coisas que interessam moram lá:
  - `$FINGERPRINTGUID`, na seção HEADER — id que o AutoCAD carrega junto com o
    desenho e sobrevive a "Salvar como", inclusive na exportação pra DXF. É a
    prova forte: igual = mesmo desenho, sem depender de heurística.
  - a tabela LAYER, na seção TABLES — logo depois. É a prova fraca, pra quando o
    fingerprint não existe (DXF gerado por outro programa, versão antiga).
Um DXF de 112 MB é lido em alguns MB. Não vale a pena varrer o arquivo inteiro:
depois das TABLES vem a geometria, que é 99% do peso e não diz identidade.

🪤 NÃO serve pra DWG: é binário e o formato é fechado. Lá continua valendo o
nome do arquivo.
"""
import re

# Quanto do arquivo ler. HEADER + TABLES de um DXF de projeto real cabem MUITO
# abaixo disso; 8 MB é folga pra desenho com centenas de layers e estilos.
LIMITE_LEITURA = 8 * 1024 * 1024

_RE_FINGERPRINT = re.compile(
    r"\$FINGERPRINTGUID\s*\r?\n\s*430\s*\r?\n\s*\{?([0-9A-Fa-f\-]{36})\}?")
# Na tabela LAYER cada entrada é "  0 / LAYER / <handle, classe...> /  2 / <nome>".
# 🪤 Entre "LAYER" e o grupo 2 vêm VÁRIAS linhas (5/handle, 330/dono, 100/classe).
# A 1ª versão usava `(?:.*?\r?\n)??`, que pula no máximo UMA linha — não casava
# nada num DXF real e a assinatura saía sempre vazia (silenciosamente: zero layer
# lido é indistinguível de "arquivo sem layer"). Agora pula até 12 linhas.
_RE_LAYER = re.compile(
    r"\r?\n\s*0\s*\r?\nLAYER\r?\n(?:[^\r\n]*\r?\n){0,12}?[ \t]*2[ \t]*\r?\n([^\r\n]+)")


def _normaliza_layer(nome: str) -> str:
    """Layer comparável entre exportações. Xref vem como 'ARQUIVO|LAYER' — fica
    só o layer, senão o mesmo desenho referenciado de pastas diferentes não bate."""
    n = (nome or "").strip()
    if "|" in n:
        n = n.split("|", 1)[1]
    return n.upper()


def assinatura_de_dxf(caminho: str, limite: int = LIMITE_LEITURA) -> dict:
    """{'fingerprint': str|None, 'layers': [str], 'n_layers': int}.

    Nunca levanta: assinatura é acessório do fluxo de sugestão. Arquivo ilegível
    devolve assinatura vazia, e quem chama simplesmente não sugere nada."""
    try:
        with open(caminho, "rb") as fh:
            bruto = fh.read(limite)
    except Exception:
        return {"fingerprint": None, "layers": [], "n_layers": 0}
    return assinatura_de_texto(bruto.decode("latin-1", errors="ignore"))


def assinatura_de_texto(texto: str) -> dict:
    fp = None
    m = _RE_FINGERPRINT.search(texto)
    if m:
        fp = m.group(1).lower()
    layers = []
    vistos = set()
    for lm in _RE_LAYER.finditer(texto):
        nome = _normaliza_layer(lm.group(1))
        # "0" e "DEFPOINTS" existem em TODO desenho — não distinguem nada e só
        # inflariam a semelhança entre projetos que não têm relação nenhuma.
        if not nome or nome in ("0", "DEFPOINTS") or nome in vistos:
            continue
        vistos.add(nome)
        layers.append(nome)
    return {"fingerprint": fp, "layers": sorted(layers), "n_layers": len(layers)}


def semelhanca(a: dict, b: dict) -> dict:
    """Compara duas assinaturas → {'mesmo_desenho': bool, 'motivo': str, 'jaccard': float}.

    🪤 O corte é ALTO (0,80) de propósito. Um escritório usa o MESMO padrão de
    layers em todos os projetos — 'ARQ-PAREDE', 'ARQ-PISO' aparecem em tudo. Com
    corte baixo, dois projetos diferentes do mesmo escritório passariam por
    "mesmo desenho" e a gente sugeriria juntar coisa que não tem nada a ver.
    Sugestão errada é pior que sugestão nenhuma: ensina o cliente a ignorar.
    """
    fa, fb = (a or {}).get("fingerprint"), (b or {}).get("fingerprint")
    if fa and fb and fa == fb:
        return {"mesmo_desenho": True, "jaccard": 1.0,
                "motivo": "mesmo identificador interno do desenho (AutoCAD)"}
    if fa and fb and fa != fb:
        # Fingerprint é prova forte nos DOIS sentidos: se os dois têm e diferem,
        # são desenhos distintos, por mais parecidos que os layers sejam.
        return {"mesmo_desenho": False, "jaccard": 0.0,
                "motivo": "identificadores internos diferentes"}
    la, lb = set((a or {}).get("layers") or []), set((b or {}).get("layers") or [])
    if len(la) < 5 or len(lb) < 5:
        # Poucos layers: qualquer coincidência é ruído.
        return {"mesmo_desenho": False, "jaccard": 0.0, "motivo": "layers de menos pra comparar"}
    inter, uniao = len(la & lb), len(la | lb)
    j = inter / uniao if uniao else 0.0
    return {"mesmo_desenho": j >= 0.80, "jaccard": round(j, 3),
            "motivo": f"{inter} de {uniao} layers em comum"}
