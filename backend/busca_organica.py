# -*- coding: utf-8 -*-
"""Busca orgânica no tick diário: Google Search Console e Bing Webmaster (04/10/2026).

🔎 Pedro (decisões da auditoria de telemetria, 28/09: "os dois"; 04/10: "segue com o Search Console e Bing no
tick"). Até aqui a leitura era manual e n=1. O Cloudflare diz de ONDE chegou a visita (Google 85 · Bing 52 na semana
de 27/09); o Search Console e o Bing dizem POR QUAL BUSCA e em qual posição — a pergunta "que consulta traz gente?".

Credenciais (criadas pelo Pedro, coladas por ele no Render — nunca no código nem no chat):
  · GSC_SERVICE_ACCOUNT_JSON — o JSON da conta de serviço do Google, adicionada como usuário no Search Console.
  · BING_WEBMASTER_API_KEY   — a chave da API do Bing Webmaster (Configurações → Acesso à API).
  · GSC_SITE (opcional)      — a propriedade, se a descoberta automática não achar ("sc-domain:ai.arq.br").
Sem elas o tick diz "sem credencial" e não grava nada — nunca zero no lugar de "não medi".

🪤 A chave do Bing vai na URL (é assim a API). Nenhuma mensagem de erro daqui leva a URL.
🪤 O Search Console fecha o dia com ~2–3 dias de atraso: o tick lê D-3, D-4 e D-5 (o que ainda mexer, regrava).
🪤 Do Bing: o total vem POR DIA; consultas e páginas vêm POR SEMANA (a API diz "updated every week").
"""
import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

ESCOPO = "https://www.googleapis.com/auth/webmasters.readonly"
TOKEN_URL = "https://oauth2.googleapis.com/token"
GSC_API = "https://searchconsole.googleapis.com/webmasters/v3"
BING_API = "https://ssl.bing.com/webmaster/api.svc/json"
SITE_BING = "https://ai.arq.br/"
# a ordem é a preferência quando a conta enxerga mais de uma propriedade
SITES_GOOGLE = ("sc-domain:ai.arq.br", "https://ai.arq.br/", "https://www.ai.arq.br/", "http://ai.arq.br/")
DIAS_GOOGLE = (3, 4, 5)       # dias atrás que o tick lê no Search Console
LINHAS = 200                  # consultas/páginas por dia (Google) — o resto é cauda
_CHAVE_MAX = 300


# ─── credenciais ────────────────────────────────────────────────────────────────────────────
def credencial_google():
    """O JSON da conta de serviço, ou None se não foi configurada. Levanta se veio QUEBRADO (a mensagem
    não carrega o conteúdo: é segredo)."""
    bruto = (os.getenv("GSC_SERVICE_ACCOUNT_JSON") or "").strip()
    if not bruto:
        return None
    try:
        c = json.loads(bruto)
    except ValueError:
        raise ValueError("GSC_SERVICE_ACCOUNT_JSON não é um JSON válido (cole o arquivo inteiro)")
    if not isinstance(c, dict) or not c.get("client_email") or not c.get("private_key"):
        raise ValueError("GSC_SERVICE_ACCOUNT_JSON sem client_email/private_key — é o arquivo da CHAVE da conta de serviço?")
    return c


def chave_bing():
    return (os.getenv("BING_WEBMASTER_API_KEY") or "").strip() or None


# ─── rede ───────────────────────────────────────────────────────────────────────────────────
def _http(metodo, url, corpo=None, cabecalhos=None, form=None, timeout=30):
    """JSON de resposta. Em erro levanta RuntimeError com o status e o começo da resposta — SEM a URL
    (a do Bing leva a chave)."""
    dados = None
    cab = dict(cabecalhos or {})
    if form is not None:
        dados = urllib.parse.urlencode(form).encode("utf-8")
        cab["Content-Type"] = "application/x-www-form-urlencoded"
    elif corpo is not None:
        dados = json.dumps(corpo).encode("utf-8")
        cab["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=dados, method=metodo, headers=cab)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        try:
            resp = e.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            resp = ""
        raise RuntimeError("HTTP %s: %s" % (e.code, resp))
    except urllib.error.URLError as e:
        raise RuntimeError("rede: %s" % (getattr(e, "reason", "") or type(e).__name__))
    return json.loads(txt) if txt.strip() else {}


# ─── Google ─────────────────────────────────────────────────────────────────────────────────
def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def jwt_da_conta(cred, agora=None):
    """O JWT RS256 que a conta de serviço troca por token (sem biblioteca do Google: o `cryptography` já está)."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    t = int(time.time() if agora is None else agora)
    cab = {"alg": "RS256", "typ": "JWT"}
    corpo = {"iss": cred["client_email"], "scope": ESCOPO, "aud": TOKEN_URL, "iat": t, "exp": t + 3600}
    a_assinar = (_b64(json.dumps(cab, separators=(",", ":")).encode()) + "." +
                 _b64(json.dumps(corpo, separators=(",", ":")).encode()))
    chave = serialization.load_pem_private_key(cred["private_key"].encode("utf-8"), password=None)
    return a_assinar + "." + _b64(chave.sign(a_assinar.encode("ascii"), padding.PKCS1v15(), hashes.SHA256()))


def token_google(cred):
    r = _http("POST", TOKEN_URL, form={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                       "assertion": jwt_da_conta(cred)})
    tok = r.get("access_token")
    if not tok:
        raise RuntimeError("o Google não devolveu token")
    return tok


def site_google(tok):
    """A propriedade do ai.arq.br que a conta de serviço enxerga (GSC_SITE manda, se existir)."""
    fixo = (os.getenv("GSC_SITE") or "").strip()
    if fixo:
        return fixo
    r = _http("GET", GSC_API + "/sites", cabecalhos={"Authorization": "Bearer " + tok})
    vistos = [s.get("siteUrl", "") for s in (r.get("siteEntry") or [])]
    for s in SITES_GOOGLE:
        if s in vistos:
            return s
    raise RuntimeError("a conta de serviço não enxerga o ai.arq.br no Search Console (vê %d propriedade(s): %s) "
                       "— falta adicioná-la como usuário em Configurações → Usuários e permissões"
                       % (len(vistos), ", ".join(vistos[:3]) or "nenhuma"))


def caminho(url_ou_caminho):
    """Página como caminho ("/faq.html"): o Google manda URL inteira, o Bing também; http/https/www viram um só."""
    s = str(url_ou_caminho or "").strip()
    if "://" in s:
        s = urllib.parse.urlsplit(s).path or "/"
    return (s or "/")[:_CHAVE_MAX]


def _linha(fonte, dia, periodo, tipo, chave, cliques, impressoes, posicao):
    pos = None
    try:
        pos = round(float(posicao), 2) if posicao not in (None, "") else None
    except (TypeError, ValueError):
        pos = None
    return {"fonte": fonte, "dia": dia.isoformat(), "periodo": periodo, "tipo": tipo,
            "chave": (caminho(chave) if tipo == "pagina" else str(chave or "").strip()[:_CHAVE_MAX]),
            "cliques": int(cliques or 0), "impressoes": int(impressoes or 0), "posicao": pos}


def linhas_google(tok, site, dia):
    """O dia inteiro do Search Console: total, consultas e páginas. Dia sem linha nenhuma no total = o Google
    ainda não fechou o dia (ou não houve impressão) — NÃO grava zero."""
    url = GSC_API + "/sites/" + urllib.parse.quote(site, safe="") + "/searchAnalytics/query"
    cab = {"Authorization": "Bearer " + tok}
    out = []
    for tipo, dims in (("total", []), ("consulta", ["query"]), ("pagina", ["page"])):
        corpo = {"startDate": dia.isoformat(), "endDate": dia.isoformat(), "rowLimit": LINHAS}
        if dims:
            corpo["dimensions"] = dims
        r = _http("POST", url, corpo=corpo, cabecalhos=cab)
        linhas = r.get("rows") or []
        if tipo == "total" and not linhas:
            return []
        for row in linhas:
            chave = (row.get("keys") or [""])[0] if dims else ""
            out.append(_linha("google", dia, "dia", tipo, chave, row.get("clicks"), row.get("impressions"),
                              row.get("position")))
    return out


# ─── Bing ───────────────────────────────────────────────────────────────────────────────────
_DATA_BING = re.compile(r"/Date\((-?\d+)([+-]\d{4})?\)/")


def data_do_bing(valor):
    """"/Date(1316156400000-0700)/" → date(2011, 9, 16): o dia no fuso que o próprio Bing mandou."""
    m = _DATA_BING.search(str(valor or ""))
    if not m:
        return None
    t = datetime.fromtimestamp(int(m.group(1)) / 1000.0, tz=timezone.utc)
    if m.group(2):
        sinal = -1 if m.group(2)[0] == "-" else 1
        t = t + sinal * timedelta(hours=int(m.group(2)[1:3]), minutes=int(m.group(2)[3:5]))
    return t.date()


def linhas_bing(chave, site=SITE_BING):
    out = []
    for metodo, tipo, periodo in (("GetRankAndTrafficStats", "total", "dia"),
                                  ("GetQueryStats", "consulta", "semana"),
                                  ("GetPageStats", "pagina", "semana")):
        url = BING_API + "/" + metodo + "?" + urllib.parse.urlencode({"siteUrl": site, "apikey": chave})
        try:
            r = _http("GET", url)
        except RuntimeError as e:
            raise RuntimeError("%s: %s" % (metodo, str(e).replace(chave, "<chave>")))
        for it in (r.get("d") or []):
            dia = data_do_bing(it.get("Date"))
            if not dia:
                continue
            out.append(_linha("bing", dia, periodo, tipo, "" if tipo == "total" else it.get("Query"),
                              it.get("Clicks"), it.get("Impressions"),
                              None if tipo == "total" else it.get("AvgImpressionPosition")))
    return out


# ─── gravação e leitura ─────────────────────────────────────────────────────────────────────
def juntar(linhas):
    """Uma linha por (fonte, dia, tipo, chave): http/https/www da mesma página viram uma só (soma; posição
    média ponderada pelas impressões). Sem isso o upsert recusaria o lote inteiro por chave repetida."""
    acc = {}
    for l in linhas:
        k = (l["fonte"], l["dia"], l["tipo"], l["chave"])
        a = acc.get(k)
        if a is None:
            acc[k] = dict(l, _peso=(l["posicao"] or 0) * l["impressoes"])
            continue
        a["cliques"] += l["cliques"]
        a["impressoes"] += l["impressoes"]
        a["_peso"] += (l["posicao"] or 0) * l["impressoes"]
    out = []
    for a in acc.values():
        peso = a.pop("_peso")
        if a["posicao"] is not None and a["impressoes"]:
            a["posicao"] = round(peso / a["impressoes"], 2)
        out.append(a)
    return out


def resumo(linhas, desde):
    """O que o painel mostra, por fonte: totais (dias medidos), top consultas e top páginas desde `desde`.
    Posição = média ponderada pelas impressões (posição de quem quase não aparece não pesa igual)."""
    out = {}
    for fonte in ("google", "bing"):
        ls = [l for l in linhas if l.get("fonte") == fonte and str(l.get("dia", "")) >= desde.isoformat()]
        tot = [l for l in ls if l.get("tipo") == "total"]

        def _agrupa(tipo):
            g = {}
            for l in ls:
                if l.get("tipo") != tipo:
                    continue
                a = g.setdefault(l.get("chave") or "", {"chave": l.get("chave") or "", "cliques": 0,
                                                          "impressoes": 0, "_peso": 0.0})
                a["cliques"] += int(l.get("cliques") or 0)
                a["impressoes"] += int(l.get("impressoes") or 0)
                if l.get("posicao") is not None:
                    a["_peso"] += float(l["posicao"]) * int(l.get("impressoes") or 0)
            lista = []
            for a in g.values():
                peso = a.pop("_peso")
                a["posicao"] = round(peso / a["impressoes"], 1) if a["impressoes"] and peso else None
                lista.append(a)
            lista.sort(key=lambda a: (-a["cliques"], -a["impressoes"], a["chave"]))
            return lista[:10]

        imp = sum(int(l.get("impressoes") or 0) for l in tot)
        peso = sum(float(l["posicao"]) * int(l.get("impressoes") or 0) for l in tot if l.get("posicao") is not None)
        out[fonte] = {
            "dias_medidos": len({l.get("dia") for l in tot}),
            "ultimo_dia": max([str(l.get("dia")) for l in ls] or [None]) if ls else None,
            "cliques": sum(int(l.get("cliques") or 0) for l in tot),
            "impressoes": imp,
            "posicao": round(peso / imp, 1) if imp and peso else None,
            "consultas": _agrupa("consulta"),
            "paginas": _agrupa("pagina"),
        }
    return out
