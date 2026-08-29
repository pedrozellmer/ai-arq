# -*- coding: utf-8 -*-
"""Foto diária do movimento do site — e a resposta pra "isso é normal?".

🎯 29/08/2026, pedido do Pedro. Ele me perguntou três vezes na mesma semana se o
site tinha caído do Google. Toda vez a resposta custou meia hora de consulta na
mão, e nas duas primeiras **eu respondi errado**:

  1ª: "a visita está normal, 211 únicos na quinta" — aquele dia era **76% ROBÔ**
      (1.129 de 1.475 requisições, de 16 endereços). O número de "únicos" do
      painel do Cloudflare conta robô.
  2ª: "21 downloads do memorial hoje, tem gente usando" — eram 5 endereços, e um
      sozinho fez 16 (faixa da Azure, com user-agent de Edge).

🔑 O problema não era falta de dado: era eu reinventando o critério a cada vez.
Este módulo põe o critério num lugar só e guarda a série — porque o Cloudflare
**só retém o detalhe (IP, navegador) por 7 DIAS**. Sem gravar, é impossível
responder "isso é normal?" olhando pra trás.

🪤 O QUE ESTE MÓDULO NÃO SABE. `req_gente` é TETO, não medida: robô disfarçado
de navegador cai nele. O nome da coluna é `req_gente` e não `pessoas` de
propósito — a honestidade do nome é o que impede a próxima leitura preguiçosa.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import date

# A zona do ai.arq.br no Cloudflare.
_ZONA = "e2375067fceb7c34bb92136d7b5d23d7"

# 🚨 PEDIDO EXPLÍCITO DO PEDRO (29/08): "tira sempre o meu acesso e o seu da
# contagem pra não estragar a estatística."
#
# 🪤 A 1ª versão era uma lista FIXA no código, com um IP só. Isso envelhece
# calado: IP residencial rotaciona, e o celular dele é outro endereço. Daqui a
# um mês a lista estaria errada e ninguém saberia — a estatística voltaria a
# contar a gente como público.
#
# 🔑 Por isso a lista de verdade mora no BANCO (`ips_da_casa`) e se enche
# sozinha: toda vez que o painel de admin carrega, ele registra o IP de quem
# está olhando. Só admin chama, então só entra quem é da casa.
#
# O que fica aqui embaixo é só a rede de segurança pra quando o banco não
# responder — e a env permite acrescentar sem deploy.
_IPS_DE_EMERGENCIA = {ip.strip() for ip in
                      (os.environ.get("METRICAS_IPS_NOSSOS") or "189.62.150.142").split(",")
                      if ip.strip()}

# 🪤 IP que não aparece há muito tempo provavelmente voltou pro pool da
# operadora e hoje é de outra pessoa. Excluir pra sempre apagaria visita de
# cliente — o erro oposto, e igualmente calado.
_DIAS_PRA_ESQUECER_IP = 90

# Navegador que o Cloudflare não reconhece, ou que se declara robô.
_MARCA_DE_ROBO = ("unknown", "bot", "crawler", "spider", "curl", "python", "wget")


def _e_robo(navegador: str) -> bool:
    n = (navegador or "").lower()
    return any(m in n for m in _MARCA_DE_ROBO)


def token() -> str:
    return (os.environ.get("CLOUDFLARE_API_TOKEN") or "").strip()


def _graphql(query: str, timeout: int = 25) -> dict:
    req = urllib.request.Request(
        "https://api.cloudflare.com/client/v4/graphql",
        data=json.dumps({"query": query}).encode("utf-8"),
        method="POST",
        headers={"Authorization": "Bearer %s" % token(),
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def coletar(dia: date, ips_da_casa=None) -> dict:
    """Números de UM dia, já separados. Levanta se não der — quem chama decide.

    🪤 O `httpRequestsAdaptiveGroups` (o que traz IP e navegador) só aceita
    janela de 1 dia por consulta, e o Cloudflare só guarda ~7 dias dele. Por
    isso a coleta é diária e não "pega o mês quando precisar".
    """
    d = dia.isoformat()
    q = ("""query { viewer { zones(filter: {zoneTag: "%s"}) {
      httpRequestsAdaptiveGroups(limit: 400,
        filter: {datetime_geq: "%sT00:00:00Z", datetime_leq: "%sT23:59:59Z",
                 clientRequestHTTPHost: "ai.arq.br"}, orderBy: [count_DESC]) {
        count dimensions { clientIP userAgentBrowser } } } } }""" % (_ZONA, d, d))
    dados = _graphql(q)
    if dados.get("errors"):
        raise RuntimeError("Cloudflare recusou: %s" % dados["errors"][:1])
    grupos = (((dados.get("data") or {}).get("viewer") or {})
              .get("zones") or [{}])[0].get("httpRequestsAdaptiveGroups") or []

    # 🔒 A lista do banco MANDA; a de emergência só entra se ela vier vazia.
    nossos = set(ips_da_casa or ()) | _IPS_DE_EMERGENCIA
    ips_gente, gente, robo, nosso = set(), 0, 0, 0
    for g in grupos:
        ip = (g.get("dimensions") or {}).get("clientIP") or ""
        nav = (g.get("dimensions") or {}).get("userAgentBrowser") or ""
        n = int(g.get("count") or 0)
        if ip in nossos:
            nosso += n
        elif _e_robo(nav):
            robo += n
        else:
            gente += n
            ips_gente.add(ip)

    # o número CRU do painel, guardado só pra lembrar o quanto ele infla
    unicos = paginas = None
    try:
        q2 = ("""query { viewer { zones(filter: {zoneTag: "%s"}) {
          httpRequests1dGroups(limit: 1, filter: {date: "%s"}) {
            sum { pageViews } uniq { uniques } } } } }""" % (_ZONA, d))
        a = ((((_graphql(q2).get("data") or {}).get("viewer") or {})
              .get("zones") or [{}])[0].get("httpRequests1dGroups") or [{}])[0]
        unicos = (a.get("uniq") or {}).get("uniques")
        paginas = (a.get("sum") or {}).get("pageViews")
    except Exception:
        pass

    return {"dia": d, "req_total": gente + robo + nosso, "req_robo": robo,
            "req_nosso": nosso, "req_gente": gente, "ips_gente": len(ips_gente),
            "unicos_cloudflare": unicos, "paginas": paginas, "fonte": "tick"}


# ── a pergunta que o Pedro faz de verdade ───────────────────────────────────

def veredito(serie: list) -> dict:
    """"Está dentro do normal?" — comparando com a faixa dos dias iguais.

    🔑 COMPARA DIA DA SEMANA COM DIA DA SEMANA. Sexta com sexta, sábado com
    sábado. Sem isso eu quase disse "caiu pela metade" olhando a sexta (50)
    contra a quinta (97) — e a sexta anterior tinha dado 51. Fim de semana cai
    sempre; comparar com a média geral inventa uma queda que não existe.

    🪤 Devolve "não sei" quando há menos de 3 dias iguais no histórico. Um
    veredito com 1 ponto de comparação é chute com cara de medida — e chute com
    cara de medida foi o que fez o Pedro perder a manhã três vezes.
    """
    if not serie:
        return {"status": "sem_dados", "frase": "ainda não há série pra comparar."}
    hoje = serie[-1]
    dow = date.fromisoformat(str(hoje["dia"])).weekday()
    iguais = [d for d in serie[:-1]
              if date.fromisoformat(str(d["dia"])).weekday() == dow
              and d.get("ips_gente") is not None]
    nome, plural, masculino = _COMO_FALAR[dow]
    # 🪤 Frase INTEIRA por gênero, com preposição e tudo. Tentei montar colando
    # letras ("d%s mai%s") e saiu "acima DA MAIS CHEIO"; tentei recortar
    # (`cheio[1:]`) e saiu "acima D MAIS CHEIO". Três tentativas no mesmo
    # detalhe — conjugar recortando string é sempre mais frágil que escrever as
    # duas versões. E este texto o Pedro lê todo dia: frase torta faz o painel
    # parecer descuidado, e painel descuidado não é lido.
    if masculino:
        fraco, cheio, outros = "o mais fraco", "do mais cheio", "os outros"
    else:
        fraco, cheio, outros = "a mais fraca", "da mais cheia", "as outras"

    if len(iguais) < 3:
        return {"status": "nao_sei", "comparaveis": len(iguais),
                "frase": ("só tenho %d %s no histórico — preciso de 3 pra dizer se "
                          "hoje é normal. Volte em algumas semanas."
                          % (len(iguais), nome if len(iguais) == 1 else plural))}
    vals = sorted(d["ips_gente"] for d in iguais)
    piso, teto = vals[0], vals[-1]
    atual = hoje.get("ips_gente") or 0
    if atual < piso:
        return {"status": "abaixo", "faixa": [piso, teto], "hoje": atual,
                "frase": ("hoje tem %d endereços, e %s que já vi teve %d. Vale olhar."
                          % (atual, fraco, piso))}
    if atual > teto:
        return {"status": "acima", "faixa": [piso, teto], "hoje": atual,
                "frase": ("hoje tem %d endereços, acima %s que já vi (%d)."
                          % (atual, cheio, teto))}
    return {"status": "normal", "faixa": [piso, teto], "hoje": atual,
            "frase": ("dentro do normal: %d endereços, e %s ficaram entre %d e %d."
                      % (atual, outros, piso, teto))}


#   (nome, plural, é_masculino)
_COMO_FALAR = {
    0: ("segunda-feira", "segundas-feiras", False),
    1: ("terça-feira", "terças-feiras", False),
    2: ("quarta-feira", "quartas-feiras", False),
    3: ("quinta-feira", "quintas-feiras", False),
    4: ("sexta-feira", "sextas-feiras", False),
    5: ("sábado", "sábados", True),
    6: ("domingo", "domingos", True),
}
