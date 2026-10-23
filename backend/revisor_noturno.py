# -*- coding: utf-8 -*-
"""O REVISOR NOTURNO — toda noite, a ficha de cada projeto de cliente dos últimos dias.

🎯 Pedro, 19/10/2026: *"um robô, automático, no próprio site, como um revisor de TODOS os projetos,
pra ir melhorando cada vez mais o nosso motor"* — e *"sempre à noite"*.

É a regra da casa de 23/09 (revisar = olhar os 6 sinais) rodando sozinha, porque até hoje ela eram
6 consultas que alguém tinha de lembrar de fazer:

    1. o arquivo e o motor ........ `projects` (linhas medidas) + `error_log` (etapas)
    2. o Q&A do projeto ........... `agent_conversations`
    3. revisão linha a linha ...... `item_reviews`
    4. revisão em lote ............ `revision_feedback`
    5. os outros entregáveis ...... memorial · cronograma · financeiro · comparativo
    6. NPS e e-mails .............. `nps_responses` · `email_sent_log`

🔑 O QUE ELE FAZ: monta a ficha de cada projeto, dá uma NOTA DE SUSPEITA pela soma dos motivos e
diz quais etapas do motor aparecem junto com reação do cliente (os "padrões da noite"). É uma fila
pra uma pessoa olhar — o painel mostra os MOTIVOS, não só o número.

🚫 O QUE ELE NÃO FAZ, de propósito:
- não conserta o motor, não liga chave, não reprocessa nada;
- não manda e-mail a cliente (é do Pedro);
- não chama IA nenhuma — é contagem no banco, custo de API zero;
- não guarda texto do cliente: a ficha leva CONTAGENS (o recado continua em "Voz do cliente").

🚨 REGRA DURA nº2: isto é DIAGNÓSTICO. O que um cliente corrigiu NUNCA vira valor em outro projeto —
aprende-se ONDE o motor erra, nunca QUANTO vale.

🪤 Por que reler a janela inteira toda noite e não só "o de ontem": o cliente reage dias depois
(revisa, pergunta, dá nota). Medido em 19/10: 121 projetos de cliente em 30 dias, só 26 com
revisão linha a linha. A ficha de um projeto de 10 dias atrás muda quando ele volta — e `novidade`
marca exatamente isso: sinal do cliente que chegou depois da rodada anterior.

🪤 `severity` do `error_log` NÃO entra na nota. Medido em 19/10: 71 de 121 projetos tinham linha
"error", e entre elas estavam `nps:promoter-alerta` (cliente que deu 9 ou 10) e `motor:spline`
(diagnóstico). A etapa vai pra ficha como CONTEXTO, e os padrões cruzam etapa × reação do cliente.
"""
from __future__ import annotations

from datetime import datetime, timezone

# ── Os motivos e seus pesos ───────────────────────────────────────────────────────────────────
# O peso maior é do que o CLIENTE fez ou disse: o motor mostra o que a máquina viu; o cliente mostra
# o que ele precisava. Ver [[feedback_revisar_projeto_e_olhar_TODOS_os_sinais]].
PESOS = {
    "medido_mexido": 3,   # editou ou apagou item com selo ✓ MEDIDO — a regra nº1 em jogo
    "recado": 3,          # escreveu com as próprias mãos na revisão
    "faltou": 3,          # disse que faltou item
    "lote_cortou": 3,     # na planilha revisada, cortou ou alterou metade ou mais
    "nps_baixo": 3,       # nota de 0 a 6
    "recusou": 2,         # apagou muita linha
    "editou": 2,          # corrigiu várias quantidades
    "falhou": 2,          # o projeto terminou em erro
    "perguntou": 1,       # perguntou no chat do projeto (dúvida, não defeito)
    "reprocessou": 1,     # foi processado de novo (pelo cliente OU pelo admin)
    "cad_sem_medida": 1,  # veio CAD e nada saiu medido
}

#: a partir daqui a ficha entra na fila de "suspeitos"
NOTA_SUSPEITO = 3

# Limiares. Pequenos de propósito: o beta tem poucos projetos e o painel mostra o motivo, então o
# custo de um falso suspeito é uma olhada; o de um defeito escondido é o cliente que não volta.
RECUSOU_MIN = 5          # linhas apagadas
RECUSOU_FRACAO = 0.30    # ... e pelo menos 30% das linhas que ele tocou
EDITOU_MIN = 3           # quantidades corrigidas
LOTE_MIN_ORIGINAIS = 5   # planilha revisada com menos que isso não diz nada
LOTE_FRACAO = 0.50       # (alterados + removidos) / originais
NPS_BAIXO_MAX = 6

#: o selo branco é gravado como 'confirmado' (`_antes.confidence` do item_reviews)
_CONF_MEDIDO = {"confirmado", "medido"}

#: só estas etapas do `error_log` são do MOTOR (leitura do arquivo). Medido em 19/10 nos 121 projetos
#: de cliente de 30 dias: motor (77 etapas), pdfvec, dxfrooms, libredwg, dwg, dxf, process_job. O resto
#: — nps, cobranca, entrega, email, admin, cliente, revisao, upload… — é o site falando, e cruzar
#: `nps:detractor-alerta` com "nota baixa" só acharia a si mesmo.
#: 🪤 Prefixo novo do motor fica de fora até entrar aqui (lista que libera, não que bloqueia).
PREFIXOS_DO_MOTOR = ("motor:", "pdfvec:", "dxfrooms:", "libredwg:", "dwg:", "dxf:", "process_job")

#: 🩸 20/10/2026, na 1ª rodada no ar: `motor:refaz-planilha-admin` (botão do admin) saiu nos padrões
#: como se fosse etapa do motor. Pior que ruído são as que gravam PORQUE uma pessoa agiu — elas andam
#: junto com a reação do cliente por construção, não por defeito, e subiriam sempre pro topo:
#: - o cliente revisou/informou: revisao-concluida (finalize_review), revisao-aprendizado (a esteira
#:   que roda depois da revisão), planilha-refeita (funde as revisões dele), informou-depois
#:   (inform_project_area), prazo-informado, respostas-processamento (o que ele respondeu no envio);
#: - alguém reprocessou: reprocess-troca-tipo (reprocess_project), versao-anterior
#:   (_arquivar_versao_anterior), avisos-velhos (a passada nova tirou os avisos da velha);
#: - o admin agiu: refaz-planilha-admin (admin_refazer_planilha);
#: - a trava do envio: envio-em-dobro.
#: Conferido no main.py em 20/10, uma por uma, onde cada uma é gravada. `motor:pai-e-filho` FICA: é o
#: motor achando linha de total junto das partes.
ETAPAS_QUE_NAO_SAO_LEITURA = frozenset({
    "motor:revisao-concluida", "motor:revisao-aprendizado", "motor:planilha-refeita",
    "motor:informou-depois", "motor:prazo-informado", "motor:respostas-processamento",
    "motor:reprocess-troca-tipo", "motor:versao-anterior", "motor:avisos-velhos",
    "motor:avisos-velhos-sem-lista", "motor:refaz-planilha-admin", "motor:envio-em-dobro",
})


def etapa_do_motor(stage) -> bool:
    s = str(stage or "")
    if s in ETAPAS_QUE_NAO_SAO_LEITURA:
        return False
    return any(s == p or s.startswith(p) for p in PREFIXOS_DO_MOTOR)


def _ts(v):
    """ISO do Supabase → datetime com fuso; None se não der.

    🪤 Carimbo sem fuso vira UTC (o padrão do Postgres): misturar com e sem fuso no `max` levanta
    TypeError e derrubaria a ficha inteira por uma coluna `date`."""
    if not v:
        return None
    try:
        t = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _max_ts(*valores):
    ts = [t for t in (_ts(v) for v in valores) if t is not None]
    return max(ts) if ts else None


def formato(file_types) -> str:
    """'CAD', 'PDF', 'CAD+PDF' ou '' — pelo `projects.file_types` ({"dwg": n, "dxf": n, "pdf": n})."""
    ft = file_types if isinstance(file_types, dict) else {}
    def _n(k):
        try:
            return int(ft.get(k) or 0)
        except Exception:
            return 0
    cad = _n("dwg") + _n("dxf") > 0
    pdf = _n("pdf") > 0
    return "CAD+PDF" if cad and pdf else "CAD" if cad else "PDF" if pdf else ""


def resumir_revisoes(linhas, recado_digitado) -> dict:
    """Conta o que o cliente fez na tela de revisão.

    🪤 `reject` apaga o item, e o `item_id` fica nulo (medido em 19/10: os 542 reject têm item_id
    nulo) — por isso reject e faltou contam LINHA. Já approve/edit podem ter várias linhas do mesmo
    item (o cliente volta e muda): vale a ÚLTIMA de cada item, senão quem mudou de ideia 3 vezes
    vira 3 correções.
    🪤 Recado não se conta por `comment != ''`: a nossa própria tela escreve frase ali. Quem decide
    o que é texto de gente é `recado_digitado` (main.py), a mesma régua da "Voz do cliente".
    """
    ultima_por_item, soltas = {}, []
    for r in linhas or []:
        iid = r.get("item_id")
        if iid and r.get("action") in ("approve", "edit"):
            atual = ultima_por_item.get(iid)
            if atual is None or str(r.get("reviewed_at") or "") >= str(atual.get("reviewed_at") or ""):
                ultima_por_item[iid] = r
        else:
            soltas.append(r)
    efetivas = list(ultima_por_item.values()) + soltas
    out = {"aprovou": 0, "editou": 0, "recusou": 0, "faltou": 0, "recados": 0, "medido_mexido": 0}
    for r in efetivas:
        a = r.get("action")
        if a == "approve":
            out["aprovou"] += 1
        elif a == "edit":
            out["editou"] += 1
        elif a == "reject":
            out["recusou"] += 1
        elif a == "faltou":
            out["faltou"] += 1
        if a in ("edit", "reject"):
            antes = (r.get("edits") or {}).get("_antes") if isinstance(r.get("edits"), dict) else None
            if isinstance(antes, dict) and str(antes.get("confidence") or "").lower() in _CONF_MEDIDO:
                out["medido_mexido"] += 1
    # recado: em TODAS as linhas, não só na última de cada item — um recado antigo não some porque
    # o cliente aprovou o item depois
    out["recados"] = sum(1 for r in linhas or [] if recado_digitado(r.get("comment")))
    return out


def motivos_da_ficha(s: dict) -> list:
    """Os motivos que pesam, a partir dos sinais já contados. Cada um: {codigo, peso, texto}."""
    m = []

    def _add(codigo, texto):
        m.append({"codigo": codigo, "peso": PESOS[codigo], "texto": texto})

    rev = s.get("revisao") or {}
    tocou = (rev.get("aprovou", 0) + rev.get("editou", 0) + rev.get("recusou", 0))
    if rev.get("medido_mexido", 0) > 0:
        _add("medido_mexido", "mexeu em %d item(ns) com selo de MEDIDO" % rev["medido_mexido"])
    if rev.get("recados", 0) > 0:
        _add("recado", "escreveu %d recado(s) na revisão" % rev["recados"])
    if rev.get("faltou", 0) > 0:
        _add("faltou", "marcou %d item(ns) como faltando" % rev["faltou"])
    if (rev.get("recusou", 0) >= RECUSOU_MIN and tocou
            and rev["recusou"] / tocou >= RECUSOU_FRACAO):
        _add("recusou", "apagou %d de %d linhas que revisou" % (rev["recusou"], tocou))
    if rev.get("editou", 0) >= EDITOU_MIN:
        _add("editou", "corrigiu %d quantidade(s)" % rev["editou"])

    lote = s.get("lote")
    if lote and (lote.get("originais") or 0) >= LOTE_MIN_ORIGINAIS:
        mexeu = (lote.get("alterados") or 0) + (lote.get("removidos") or 0)
        if mexeu / lote["originais"] >= LOTE_FRACAO:
            _add("lote_cortou", "na planilha revisada, mudou ou tirou %d de %d linhas"
                 % (mexeu, lote["originais"]))

    nps = s.get("nps")
    if nps is not None and nps <= NPS_BAIXO_MAX:
        _add("nps_baixo", "deu nota %d no NPS" % nps)

    if s.get("status") == "error":
        _add("falhou", "o projeto terminou em erro")
    if (s.get("chat") or {}).get("perguntas", 0) > 0:
        _add("perguntou", "perguntou %d vez(es) no chat do projeto" % s["chat"]["perguntas"])
    if (s.get("reprocessos") or 0) > 0:
        _add("reprocessou", "foi reprocessado %d vez(es)" % s["reprocessos"])

    motor = s.get("motor") or {}
    # 🪤 Só CAD: PDF sai estimado por desenho do produto (regra nº1), então "nada medido" num PDF é
    # o esperado, não suspeita.
    if (s.get("formato") == "CAD" and s.get("status") == "done"
            and (motor.get("total") or 0) > 0 and (motor.get("medidas") or 0) == 0):
        _add("cad_sem_medida", "veio CAD e nenhuma das %d linhas saiu medida" % motor["total"])
    return m


#: motivos que vêm do CLIENTE (não da máquina) — é o que conta como "reação" nos padrões.
#: 🪤 `reprocessou` fica de fora: o `reprocess_count` também sobe quando o ADMIN reprocessa o
#: projeto do cliente (main.py, rota de reprocesso, rastro `admin:reprocessou-projeto-de-cliente`).
#: 🪤 `perguntou` também: pergunta é dúvida, não correção — conta como RETORNO, não como reação.
MOTIVOS_DO_CLIENTE = {"medido_mexido", "recado", "faltou", "lote_cortou", "nps_baixo",
                      "recusou", "editou"}


def _teve_retorno(f) -> bool:
    """O cliente fez QUALQUER coisa neste projeto (base dos padrões)."""
    s = f.get("sinais") or {}
    rev = s.get("revisao") or {}
    return bool(rev.get("aprovou") or rev.get("editou") or rev.get("recusou") or rev.get("faltou")
                or rev.get("recados") or s.get("lote") or (s.get("chat") or {}).get("perguntas")
                or s.get("nps") is not None)


def montar_fichas(projetos, extra, revisoes, lotes, conversas, nps, erros, entregaveis, emails,
                  recado_digitado, ultima_rodada=None) -> list:
    """Uma ficha por projeto. Tudo já lido do banco; aqui só se conta.

    - `projetos`: linhas de `projetos_de_cliente` (job_id, created_at, status, file_types,
      reprocess_count, revisao_aberturas)
    - `extra`: {job_id: {linhas_medidas, linhas_total}} (de `projects`, que a view não traz)
    - `revisoes`, `lotes`, `conversas`, `nps`, `erros`, `emails`: linhas cruas com `job_id`
    - `entregaveis`: {"memorial": [...], "cronograma": [...], "financeiro": [...],
      "comparativo": [...]} — linhas com job_id e um carimbo de data
    - `ultima_rodada`: quando a rodada anterior gravou (ISO); None na primeira
    """
    def _por_job(linhas):
        d = {}
        for r in linhas or []:
            d.setdefault(r.get("job_id"), []).append(r)
        return d

    rev_j, lote_j, conv_j = _por_job(revisoes), _por_job(lotes), _por_job(conversas)
    nps_j, err_j, mail_j = _por_job(nps), _por_job(erros), _por_job(emails)
    ent_j = {k: _por_job(v) for k, v in (entregaveis or {}).items()}
    corte = _ts(ultima_rodada)

    fichas = []
    for p in projetos or []:
        jid = p.get("job_id")
        if not jid:
            continue
        ex = (extra or {}).get(jid) or {}
        rv = rev_j.get(jid, [])
        lt = sorted(lote_j.get(jid, []), key=lambda r: str(r.get("created_at") or ""))
        cv = conv_j.get(jid, [])
        np_ = sorted(nps_j.get(jid, []), key=lambda r: str(r.get("created_at") or ""))
        er = err_j.get(jid, [])

        ultimo_lote = lt[-1] if lt else None
        sinais = {
            "formato": formato(p.get("file_types")),
            "status": p.get("status"),
            "reprocessos": int(p.get("reprocess_count") or 0),
            "motor": {
                "medidas": ex.get("linhas_medidas"),
                "total": ex.get("linhas_total"),
                # contexto, não nota: as etapas que o motor registrou neste projeto
                "etapas": sorted({str(r["stage"]) for r in er if etapa_do_motor(r.get("stage"))}),
            },
            "revisao": dict(resumir_revisoes(rv, recado_digitado),
                            aberturas=int(p.get("revisao_aberturas") or 0)),
            "lote": ({"originais": ultimo_lote.get("n_originais") or 0,
                      "mantidos": ultimo_lote.get("n_mantidos") or 0,
                      "alterados": ultimo_lote.get("n_alterados") or 0,
                      "removidos": ultimo_lote.get("n_removidos") or 0,
                      "adicionados": ultimo_lote.get("n_adicionados") or 0,
                      "planilhas": len(lt)} if ultimo_lote else None),
            "chat": {"perguntas": len(cv)},
            # a nota MAIS RECENTE: quem deu 5 e depois 9 mudou de ideia
            "nps": (int(np_[-1]["score"]) if np_ and np_[-1].get("score") is not None else None),
            "entregaveis": {k: bool(ent_j.get(k, {}).get(jid)) for k in
                            ("memorial", "cronograma", "financeiro", "comparativo")},
            "emails": len(mail_j.get(jid, [])),
        }
        motivos = motivos_da_ficha(sinais)

        datas_ent = []
        for k, por_job in ent_j.items():
            for r in por_job.get(jid, []):
                datas_ent.append(r.get("quando"))
        ultimo = _max_ts(*[r.get("reviewed_at") for r in rv],
                         *[r.get("created_at") for r in lt],
                         *[r.get("created_at") for r in cv],
                         *[r.get("created_at") for r in np_],
                         *datas_ent)
        if corte is None:
            novidade = ultimo is not None
        else:
            novidade = ultimo is not None and ultimo > corte

        fichas.append({
            "job_id": jid,
            "criado_em": p.get("created_at"),
            "nota": sum(x["peso"] for x in motivos),
            "motivos": motivos,
            "sinais": sinais,
            "ultimo_sinal_do_cliente": ultimo.isoformat() if ultimo else None,
            "novidade": bool(novidade),
        })
    fichas.sort(key=lambda f: (-f["nota"], not f["novidade"], str(f["criado_em"] or "")))
    return fichas


# ── Os casos (parte 3, peças A e B — 23/10/2026) ──────────────────────────────────────────────
# 🪤 Sem isto, projeto consertado ficava 30 dias na fila: em 23/10 eram 17 "continuam na fila, sem
# novidade", e o relatório da manhã repetiria os mesmos nomes todo dia até a janela os soltar.
#: o caso FECHOU — o projeto sai da contagem de suspeitos (até o cliente voltar)
ESTADOS_FECHADOS = {"consertado", "nao_e_defeito"}
ESTADOS = {"olhando", "confirmado"} | ESTADOS_FECHADOS


def aplicar_casos(fichas, casos) -> list:
    """Põe em cada ficha o caso dela (`revisor_casos`) e reordena a fila.

    - caso FECHADO (`consertado`/`nao_e_defeito`): `tratado` = True — sai da contagem de suspeitos.
    - mas se o cliente fez algo DEPOIS de `fechado_em`: `voltou` = True e ele NÃO é tratado — volta
      pra fila. É o alarme que importa: o conserto não bastou, ou o cliente achou outra coisa.
    - caso aberto (`olhando`/`confirmado`): só anota; o projeto continua contando.
    - estado desconhecido (digitado errado) não esconde nada: conta como aberto.

    🔒 A nota NÃO muda: o que o cliente fez continua sendo o que ele fez. O caso só diz se alguém
    já olhou.
    """
    por_job = {c.get("job_id"): c for c in casos or [] if c.get("job_id")}
    for f in fichas or []:
        c = por_job.get(f.get("job_id"))
        if not c:
            f["caso"] = None
            continue
        estado = str(c.get("estado") or "")
        fechado = estado in ESTADOS_FECHADOS
        fechado_em = _ts(c.get("fechado_em"))
        ultimo = _ts(f.get("ultimo_sinal_do_cliente"))
        # 🪤 fechado sem data não tem como saber se voltou — o banco proíbe (constraint), e aqui o
        # caso fica ABERTO em vez de sumir com o projeto calado
        volta = bool(fechado and fechado_em and ultimo and ultimo > fechado_em)
        f["caso"] = {
            "estado": estado,
            "forma": c.get("forma") or "",
            "origem": c.get("origem") or "",
            "conserto_commit": c.get("conserto_commit"),
            "chave": c.get("chave"),
            "teste": c.get("teste"),
            "fechado_em": fechado_em.isoformat() if fechado_em else None,
            "tratado": bool(fechado and fechado_em and not volta),
            "voltou": volta,
        }
    fichas.sort(key=lambda f: (tratado(f), -f["nota"], not voltou(f), not f["novidade"],
                               str(f["criado_em"] or "")))
    return fichas


def tratado(f) -> bool:
    return bool((f.get("caso") or {}).get("tratado"))


def voltou(f) -> bool:
    return bool((f.get("caso") or {}).get("voltou"))


def e_suspeito(f) -> bool:
    """Entra na contagem de suspeitos: nota 3 ou mais e o caso não foi fechado (ou voltou)."""
    return f.get("nota", 0) >= NOTA_SUSPEITO and not tratado(f)


def padroes(fichas) -> list:
    """Cada etapa do motor × quantos projetos com ela tiveram reação do cliente.

    🔑 Um caso não é padrão ([[feedback_o_numero_que_eu_medi_pode_ser_o_meu_proprio_corte]]). A
    etapa que aparece em 29 projetos e em 1 só o cliente reagiu é ruído; a que aparece em 6 e em 5
    o cliente reagiu é a próxima coisa a olhar. A fração vai junto com a BASE (`com_retorno`):
    projeto em que o cliente ainda não fez nada não diz se a etapa dói.

    🪤 Ordenar por `com_reacao` cru põe no topo a etapa que está em TODO projeto (medido em 19/10: as
    etapas `motor:` aparecem nos 121). Por isso a ordem é pelo `excesso`: reações a mais do que a
    taxa média daria naquela base — `com_reacao - com_retorno × taxa_geral`. Etapa que está em tudo
    tem excesso ~0; a que concentra reação sobe.
    """
    retornos = [f for f in fichas or [] if _teve_retorno(f)]
    reagiram = [f for f in retornos
                if {m["codigo"] for m in f.get("motivos") or []} & MOTIVOS_DO_CLIENTE]
    taxa_geral = (len(reagiram) / len(retornos)) if retornos else 0.0

    por_etapa = {}
    for f in fichas or []:
        do_cliente = {m["codigo"] for m in f.get("motivos") or []} & MOTIVOS_DO_CLIENTE
        revisou = _teve_retorno(f)
        for et in (f.get("sinais") or {}).get("motor", {}).get("etapas") or []:
            d = por_etapa.setdefault(et, {"etapa": et, "projetos": 0, "com_retorno": 0,
                                           "com_reacao": 0, "exemplos": []})
            d["projetos"] += 1
            if revisou:
                d["com_retorno"] += 1
            if do_cliente:
                d["com_reacao"] += 1
                if len(d["exemplos"]) < 5:
                    d["exemplos"].append(f["job_id"])
    out = list(por_etapa.values())
    for d in out:
        d["excesso"] = round(d["com_reacao"] - d["com_retorno"] * taxa_geral, 2)
        d["taxa_geral"] = round(taxa_geral, 3)
    out.sort(key=lambda d: (-d["excesso"], -d["com_reacao"], -d["projetos"], d["etapa"]))
    return out
