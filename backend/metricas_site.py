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
from datetime import date, timedelta

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

# 🚨 20/09/2026 — O TETO QUE FAZIA O PAINEL MENTIR. A consulta pede ao
# Cloudflare os grupos com MAIS requisições (`orderBy: count_DESC`) e só depois
# separa robô de gente, aqui no Python. Quando uma onda de robôs chega, eles
# ocupam os primeiros lugares e as PESSOAS caem fora da janela — o painel então
# mostra o resto como se fosse o público do dia.
#
# 📏 Medido: até 16/09 o robô era 7–43% do tráfego e a coleta via 40–74
# endereços de gente. De 17/09 a 19/09 o robô foi a 88%, 93% e 85% (de ~80 para
# 14.000 requisições/dia) e os endereços caíram para 38, 19 e 19 — enquanto as
# REQUISIÇÕES de gente subiam (738 → 1.147). Não foi o público que sumiu.
#
# 🪤 O número aqui não conserta nada sozinho: o que consertava era o painel
# saber que a conta veio no teto. Por isso quem coleta devolve
# `grupos_recebidos` e `coleta_truncada`, e o veredito se recusa a comparar um
# dia truncado com os outros.
TETO_DE_GRUPOS = 400


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


# 🚨 02/09/2026 — O "DIA" DESTA SÉRIE ERA O DE GREENWICH. As consultas ao
# Cloudflare filtravam `T00:00:00Z`..`T23:59:59Z`, e em Brasília isso vai das
# 21h de ONTEM às 21h de HOJE. O mesmo painel contava "projetos hoje" em
# Brasília (conserto de 24/08) e a série de 7 dias em Greenwich — dois relógios
# na mesma tela. Medido em usage_events: 14% dos eventos caem entre 21h e 24h,
# e em 5 de 12 dias a contagem UTC×BRT diverge mais de 15%.
#
# 🔑 Meia-noite de Brasília é 03:00Z (UTC-3, sem horário de verão desde 2019).
# A regra de fuso da casa mora em main._agora_br_fn; este módulo não pode
# importar main (main importa ele), então a borda fica explícita aqui.
_INICIO_DIA_BR = "T03:00:00Z"
_FIM_DIA_BR = "T02:59:59Z"


def bordas_do_dia_br(dia: date) -> tuple:
    """(início, fim) em UTC do dia `dia` contado no relógio de Brasília."""
    return (dia.isoformat() + _INICIO_DIA_BR,
            (dia + timedelta(days=1)).isoformat() + _FIM_DIA_BR)


def erros_5xx_do_dia(ini: str, fim: str):
    """Quantos 5xx o site devolveu na janela. `None` = NAO CONSEGUI MEDIR.

    🚨 02/09/2026 — O FAROL "SITE NO AR" NUNCA MEDIU NADA. A coluna `site_ok`
    era LIDA pelo painel e NUNCA escrita: 11 de 11 dias NULL, e o teste na tela
    era `=== false`, entao NULL nao era false e o farol dizia "sim" em verde,
    todo dia. Afirmacao verde com zero medicao atras e pior que farol nenhum.

    🩸 17/09/2026 — E A MESMA DOENCA AINDA ESTAVA AQUI, POR OUTRA PORTA. So
    EXCECAO virava `None`. O GraphQL reporta falha com **HTTP 200 e um campo
    `errors`** — isso caia no `.get("data") or {}`, virava lista vazia, somava
    zero e acendia o farol VERDE sem ter medido nada. Agora resposta sem `data`
    utilizavel e "nao sei", que e uma resposta; "esta tudo bem" nao e.

    🔑 E devolve o NUMERO, nao um sim/nao. O painel dizia "6 dias com erro" e
    nao dava pra saber se eram seis solucos de um segundo ou seis quedas de uma
    hora — um unico 5xx em 800 requisicoes pintava o dia igual. O dado pra
    decidir existia e era jogado fora na hora de gravar.
    🪤 `0` e resposta ("medi e nao houve"); `None` e ausencia de resposta. Os
    dois nunca podem virar a mesma coisa — foi confundi-los que criou o farol
    mentiroso de 02/09.
    """
    try:
        q = ("""query { viewer { zones(filter: {zoneTag: "%s"}) {
          httpRequestsAdaptiveGroups(limit: 1,
            filter: {datetime_geq: "%s", datetime_leq: "%s",
                     clientRequestHTTPHost: "ai.arq.br", edgeResponseStatus_geq: 500}) {
            count } } } }""" % (_ZONA, ini, fim))
        r = _graphql(q)
    except Exception as e:
        print("[metricas] 5xx do dia: %s" % e)
        return None
    if not isinstance(r, dict) or r.get("errors"):
        return None
    zonas = (((r.get("data") or {}).get("viewer") or {}).get("zones"))
    if not zonas:
        return None
    grupos = (zonas[0] or {}).get("httpRequestsAdaptiveGroups")
    if grupos is None:
        return None
    try:
        return sum(int(x.get("count") or 0) for x in grupos)
    except (TypeError, ValueError, AttributeError):
        return None


def site_ok_da_contagem(erros):
    """O farol DERIVADO da contagem — nunca medido em paralelo.

    🔑 Dois campos independentes sobre o mesmo fato divergem; foi assim que o
    motor retentava de um jeito e contava a falha de outro (caso de 16/09, as
    duas reguas do retry). Aqui `site_ok` e so uma leitura de `erros_5xx`.
    """
    if erros is None:
        return None
    return int(erros) == 0


def coletar(dia: date, ips_da_casa=None) -> dict:
    """Números de UM dia (de Brasília), já separados. Levanta se não der — quem chama decide.

    🪤 O `httpRequestsAdaptiveGroups` (o que traz IP e navegador) só aceita
    janela de 1 dia por consulta, e o Cloudflare só guarda ~7 dias dele. Por
    isso a coleta é diária e não "pega o mês quando precisar".
    """
    d = dia.isoformat()
    ini, fim = bordas_do_dia_br(dia)
    q = ("""query { viewer { zones(filter: {zoneTag: "%s"}) {
      httpRequestsAdaptiveGroups(limit: %d,
        filter: {datetime_geq: "%s", datetime_leq: "%s",
                 clientRequestHTTPHost: "ai.arq.br"}, orderBy: [count_DESC]) {
        count dimensions { clientIP userAgentBrowser clientRequestPath
                           edgeResponseStatus edgeResponseContentTypeName }
      } } } }""" % (_ZONA, TETO_DE_GRUPOS, ini, fim))
    dados = _graphql(q)
    if dados.get("errors"):
        raise RuntimeError("Cloudflare recusou: %s" % dados["errors"][:1])
    grupos = (((dados.get("data") or {}).get("viewer") or {})
              .get("zones") or [{}])[0].get("httpRequestsAdaptiveGroups") or []

    # 🔒 A lista do banco MANDA; a de emergência só entra se ela vier vazia.
    nossos = set(ips_da_casa or ()) | _IPS_DE_EMERGENCIA
    ips_gente, gente, robo, nosso = set(), 0, 0, 0
    # 🔑 Quais páginas trouxeram gente. Medido em 29/08: a FAQ é a SEGUNDA
    # página mais vista do site (76 endereços em 5 dias, contra 38 do melhor
    # post do blog) — e ninguém sabia, porque esse número nunca era calculado.
    por_pagina = {}
    for g in grupos:
        dim = g.get("dimensions") or {}
        ip = dim.get("clientIP") or ""
        nav = dim.get("userAgentBrowser") or ""
        n = int(g.get("count") or 0)
        if ip in nossos:
            nosso += n
            continue
        if _e_robo(nav):
            robo += n
            continue
        gente += n
        ips_gente.add(ip)
        # 🪤 Só página HTML com resposta 200: asset (css/js/imagem) inflaria e
        # esconderia a página; 404 de scanner viraria "página popular".
        if dim.get("edgeResponseContentTypeName") == "html"                 and str(dim.get("edgeResponseStatus")) == "200":
            cam = dim.get("clientRequestPath") or "/"
            por_pagina.setdefault(cam, set()).add(ip)

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

    # 🚨 02/09/2026 — O FAROL "SITE NO AR" NUNCA MEDIU NADA. A coluna `site_ok`
    # era LIDA pelo painel (admin.html) e NUNCA escrita por ninguém: 11 de 11
    # dias com NULL. E o teste na tela era `=== false`, então NULL não era false
    # e o farol dizia "sim" em verde, todo dia, desde que nasceu. Afirmação
    # verde com zero medição atrás é pior que farol nenhum — é a primeira coisa
    # que o Pedro olha.
    #
    # 🔑 Agora mede: erro 5xx do dia, perguntado ao Cloudflare numa consulta
    # própria (a de cima tem `limit: 400` por contagem, então um 5xx raro
    # ficaria de fora do topo e passaria por "site ok" — teto não serve de
    # prova de ausência).
    #
    # 🪤 Se a consulta falhar, fica None de propósito: "não consegui medir" é
    # uma resposta, "está tudo bem" não é.
    erros_5xx = erros_5xx_do_dia(ini, fim)
    site_ok = site_ok_da_contagem(erros_5xx)

    topo = sorted(({"pagina": k, "enderecos": len(v)} for k, v in por_pagina.items()),
                  key=lambda x: -x["enderecos"])[:12]
    # 🔑 A linha DIZ em que relógio foi contada. As 11 linhas antigas ficam com
    # o default 'UTC' da coluna e a tela as marca; misturar sem marcar seria
    # comparar dia de 21h-21h com dia de 0h-24h e chamar de "mesma série".
    return {"dia": d, "fuso": "America/Sao_Paulo",
            "req_total": gente + robo + nosso, "req_robo": robo,
            "req_nosso": nosso, "req_gente": gente, "ips_gente": len(ips_gente),
            "unicos_cloudflare": unicos, "paginas": paginas, "site_ok": site_ok,
            "erros_5xx": erros_5xx,
            # 🔑 Quantos grupos vieram e se bateu o teto. Sem isto, "não
            # consegui contar direito" é indistinguível de "caiu o movimento" —
            # foi assim que três dias de robô viraram "vale olhar".
            "grupos_recebidos": len(grupos),
            "coleta_truncada": len(grupos) >= TETO_DE_GRUPOS,
            "top_paginas": topo, "fonte": "tick"}


# ── a pergunta que o Pedro faz de verdade ───────────────────────────────────

def _dia_por_extenso(iso: str) -> str:
    """"01/09 (terça)" — a data que a frase está falando, sem ambiguidade.

    🪤 Nunca "hoje": o dia mais novo da série é sempre pelo menos ontem.
    """
    try:
        _dt = date.fromisoformat(str(iso))
    except Exception:
        return str(iso)
    return "%02d/%02d (%s)" % (_dt.day, _dt.month, _COMO_FALAR[_dt.weekday()][0].split("-")[0])


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
    # 🚨 02/09/2026 — A FRASE DIZIA "HOJE" E MOSTRAVA ONTEM. O tick grava sempre
    # `today - 1/2/3` (o Cloudflare fecha o dia depois), então o dia mais novo
    # da série NUNCA é o de hoje. Em 21 das 24 horas do dia a frase estava
    # falando de ontem chamando de hoje — e durante um buraco de coleta ela
    # chamaria de "hoje" um número de três dias atrás. Agora diz a DATA.
    _qual = _dia_por_extenso(str(hoje["dia"]))
    # 🚨 20/09/2026 — DIA TRUNCADO NÃO ENTRA EM COMPARAÇÃO, nem como o dia
    # julgado nem como régua. A coleta pede os N grupos MAIORES ao Cloudflare;
    # numa onda de robôs eles tomam a janela e as pessoas ficam de fora. O
    # painel então dizia "19/09 teve 19 endereços, o mais fraco que já vi teve
    # 29, vale olhar" — mandando o Pedro olhar o público quando o que quebrou
    # foi a régua. Três dias seguidos assim, e o aviso virou ruído.
    # 🪤 `is True` de propósito: NULL (dia coletado antes desta medida existir)
    # não é "não truncado", é "não se sabe" — e não-sei não pode virar acusação.
    if hoje.get("coleta_truncada") is True:
        return {"status": "coleta_truncada", "hoje": hoje.get("ips_gente"),
                "grupos": hoje.get("grupos_recebidos"),
                "frase": ("%s não dá pra comparar: a coleta bateu no teto de %s "
                          "grupos do Cloudflare e os endereços de gente ficaram "
                          "de fora da conta. O número que aparece (%s) está "
                          "incompleto — não é queda de movimento."
                          % (_qual, hoje.get("grupos_recebidos") or "?",
                             hoje.get("ips_gente")))}
    dow = date.fromisoformat(str(hoje["dia"])).weekday()
    iguais = [d for d in serie[:-1]
              if date.fromisoformat(str(d["dia"])).weekday() == dow
              and d.get("ips_gente") is not None
              and d.get("coleta_truncada") is not True]
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
                "frase": ("%s teve %d endereços, e %s que já vi teve %d. Vale olhar."
                          % (_qual, atual, fraco, piso))}
    if atual > teto:
        return {"status": "acima", "faixa": [piso, teto], "hoje": atual,
                "frase": ("%s teve %d endereços, acima %s que já vi (%d)."
                          % (_qual, atual, cheio, teto))}
    return {"status": "normal", "faixa": [piso, teto], "hoje": atual,
            "frase": ("%s: dentro do normal, %d endereços — %s ficaram entre %d e %d."
                      % (_qual, atual, outros, piso, teto))}


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
