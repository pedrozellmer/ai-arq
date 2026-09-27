# -*- coding: utf-8 -*-
"""Resumo diário das @menções do Escritório (27/09/2026 — Pedro escolheu "Resumo diário").

Quem foi mencionado com @ num comentário recebe UM e-mail por dia, a partir das 18 h de Brasília, com as menções de
ontem 18 h até hoje 18 h — só as que a pessoa enxerga no quadro (a mesma regra do banco, seção 26):
  • equipe (a admin e quem ela chamou como equipe): todas;
  • fornecedor: só nas tarefas em que ele está;
  • cliente: nunca (o cliente não vê comentários).
🔒 A menção é uma lista de ids que a TELA grava — o banco não confere. Aqui o servidor confere que a pessoa é do
MESMO projeto do comentário e está ativa: senão um id de outro projeto levaria o texto do comentário pra fora.
🔑 Uma marca por pessoa e por dia, gravada ANTES do envio (quem chama passa `marcar`): mandar duas vezes é pior do
que faltar um dia. A marca não conta no teto semanal dos e-mails de marketing da pessoa.
"""
from datetime import datetime, timedelta, timezone

import escritorio as esc

HORA = 18                  # a partir das 18 h de Brasília (o tick é de hora em hora, das 8 h às 20 h)
TETO_ITENS = 30            # menções num e-mail; o resto vira "e mais N no quadro"
TETO_TEXTO = 280           # caracteres de cada comentário no e-mail
KIND = "escritorio_mencoes"
BRASILIA = timezone(timedelta(hours=-3))    # sem horário de verão desde 2019
PAPEIS_QUE_VEEM = ("dono", "freela", "fornecedor")


def janela(agora_utc: datetime):
    """(dia, início, fim) da rodada de hoje — ontem 18 h até hoje 18 h, em UTC —, ou None antes das 18 h."""
    agora_br = agora_utc.astimezone(BRASILIA)
    if agora_br.hour < HORA:
        return None
    fim = agora_br.replace(hour=HORA, minute=0, second=0, microsecond=0)
    return fim.date().isoformat(), (fim - timedelta(days=1)).astimezone(timezone.utc), fim.astimezone(timezone.utc)


def _quando(s):
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _em(ids) -> str:
    return "in.(" + ",".join(sorted({str(x) for x in ids})) + ")"


def _ler(tabela: str, params: dict) -> list:
    """🪤 vazio ≠ falhou: (200, []) é "não tem"; qualquer outra coisa levanta e a rodada não manda nada."""
    st, linhas = esc._SERVICO("GET", tabela, params=params)
    if st >= 300 or st == 0 or linhas is None:
        raise RuntimeError(f"{tabela} HTTP {st}")
    return linhas


def _curto(texto: str) -> str:
    t = " ".join(str(texto or "").split())
    return t if len(t) <= TETO_TEXTO else t[:TETO_TEXTO - 1].rstrip() + "…"


def quem_leva(inicio: datetime, fim: datetime) -> dict:
    """{user_id: {"email", "nome", "itens": [...]}} com as menções da janela que cada pessoa pode ver."""
    coms = _ler("escritorio_comentarios", {
        "criado_em": "gte." + inicio.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "select": "id,tarefa_id,projeto_id,autor,texto,mencoes,criado_em", "order": "criado_em.asc"})
    coms = [c for c in coms if c.get("mencoes") and (_quando(c.get("criado_em")) or fim) < fim]
    if not coms:
        return {}
    pids = {str(c["projeto_id"]) for c in coms}
    tids = {str(c["tarefa_id"]) for c in coms}
    mids = {str(m) for c in coms for m in c["mencoes"]}
    membro = {str(m["id"]): m for m in _ler("escritorio_membros", {
        "id": _em(mids), "select": "id,projeto_id,papel,status,user_id,email,email_conta,nome"})}
    tarefa = {str(t["id"]): t for t in _ler("escritorio_tarefas", {"id": _em(tids), "select": "id,projeto_id,titulo"})}
    projeto = {str(p["id"]): p for p in _ler("escritorio_projetos", {"id": _em(pids), "select": "id,nome"})}
    autores = {str(c["autor"]) for c in coms if c.get("autor")}
    nome_do_autor = {}
    if autores:
        for m in _ler("escritorio_membros", {"projeto_id": _em(pids), "user_id": _em(autores),
                                             "select": "projeto_id,user_id,nome,email"}):
            nome_do_autor[(str(m["projeto_id"]), str(m["user_id"]))] = (m.get("nome") or
                                                                        str(m.get("email") or "").split("@")[0])
    forn = {mid for mid in mids if (membro.get(mid) or {}).get("papel") == "fornecedor"}
    designado = set()
    if forn:
        designado = {(str(x["tarefa_id"]), str(x["membro_id"])) for x in _ler("escritorio_tarefa_pessoas", {
            "tarefa_id": _em(tids), "membro_id": _em(forn), "select": "tarefa_id,membro_id"})}

    pessoas = {}
    for c in coms:
        pid, tid = str(c["projeto_id"]), str(c["tarefa_id"])
        t = tarefa.get(tid)
        if not t or str(t.get("projeto_id")) != pid:
            continue
        for mid in dict.fromkeys(str(x) for x in c["mencoes"]):
            m = membro.get(mid)
            if (not m or m.get("status") != "ativo" or str(m.get("projeto_id")) != pid or not m.get("user_id")
                    or m.get("papel") not in PAPEIS_QUE_VEEM):
                continue
            if str(m["user_id"]) == str(c.get("autor") or ""):
                continue                                   # quem se menciona não precisa de aviso
            if m["papel"] == "fornecedor" and (tid, mid) not in designado:
                continue                                   # o banco não mostra esse comentário pra ele
            email = str(m.get("email_conta") or m.get("email") or "").strip().lower()
            if not email:
                continue
            p = pessoas.setdefault(str(m["user_id"]), {"email": email, "nome": m.get("nome") or "", "itens": []})
            p["itens"].append({
                "projeto_id": pid, "projeto": (projeto.get(pid) or {}).get("nome") or "Projeto",
                "tarefa": t.get("titulo") or "Tarefa",
                "autor": nome_do_autor.get((pid, str(c.get("autor") or ""))) or "Alguém da equipe",
                "texto": _curto(c.get("texto"))})
    return pessoas


def email_do_resumo(nome: str, itens: list, moldura=None):
    """(assunto, html, texto) do resumo. Tudo que veio de fora vai escapado."""
    n = len(itens)
    mostrar = itens[:TETO_ITENS]
    por_projeto = {}
    for it in mostrar:
        por_projeto.setdefault(it["projeto_id"], []).append(it)
    corpo, texto = "", []
    for pid, its in por_projeto.items():
        link = f"{esc.SITE}/escritorio.html#/p/{pid}/tarefas"
        corpo += f'<p style="margin:18px 0 8px;font-weight:700;">{esc._escapar(its[0]["projeto"])}</p>'
        texto.append(its[0]["projeto"])
        for it in its:
            corpo += ('<p style="margin:0 0 10px;padding:10px 12px;background:#f8fafc;border-radius:8px;">'
                      f'<b>{esc._escapar(it["autor"])}</b> em <b>{esc._escapar(it["tarefa"])}</b>:<br>'
                      f'“{esc._escapar(it["texto"])}”</p>')
            texto.append(f'- {it["autor"]} em {it["tarefa"]}: “{it["texto"]}”')
        corpo += f'<p style="margin:0 0 6px;"><a href="{link}" style="color:#4F46E5;">Abrir o quadro</a></p>'
        texto.append(link)
    if n > len(mostrar):
        resto = n - len(mostrar)
        corpo += f'<p style="margin:12px 0 0;">E mais {resto} {"menção" if resto == 1 else "menções"} no quadro.</p>'
        texto.append(f"E mais {resto} no quadro.")
    ola = f"Oi, {esc._escapar(nome.split()[0])}!" if str(nome or "").split() else "Oi!"
    abre = f'<p style="margin:0 0 4px;">{ola} Mencionaram você com @ no Escritório desde ontem:</p>'
    unico = list(por_projeto)
    cta = f"{esc.SITE}/escritorio.html" + (f"#/p/{unico[0]}/tarefas" if len(unico) == 1 else "")
    html = (moldura or esc._MOLDURA)(
        "Menções pra você", abre + corpo, cta_text="Abrir o Escritório", cta_url=cta,
        reason="Você recebeu este e-mail porque mencionaram você com @ num comentário do Escritório do AI.arq. "
               "Sai no máximo um resumo por dia, e só quando há menção.",
        preheader=f"{n} {'menção' if n == 1 else 'menções'} desde ontem.")
    assunto = f"{n} {'menção' if n == 1 else 'menções'} pra você no Escritório do AI.arq"
    return assunto, html, "Mencionaram você com @ no Escritório desde ontem:" + esc._DUAS_LINHAS + chr(10).join(texto)


def rodada(agora_utc: datetime, marcar, dry: bool = False) -> dict:
    """Uma rodada do tick. `marcar(ref)` grava a marca do dia: True = é a primeira (manda), False = já tinha
    (não manda), None = não gravou (não manda: na dúvida, não duplica). Nunca levanta."""
    j = janela(agora_utc)
    if not j:
        return {"status": "fora_da_hora"}
    dia, inicio, fim = j
    try:
        pessoas = quem_leva(inicio, fim)
    except Exception as e:
        esc._registrar("escritorio:mencoes", f"não li as menções — nenhum resumo sai agora: {type(e).__name__}: "
                                             f"{str(e)[:160]}")
        return {"status": "erro"}
    if dry:
        return {"status": "dry", "pessoas": len(pessoas)}
    feito = {"status": "ok", "enviados": 0, "ja_tinham": 0, "falhas": 0}
    for uid, p in pessoas.items():
        try:
            vez = marcar(f"{dia}:{uid}")
        except Exception:
            vez = None
        if vez is not True:
            feito["ja_tinham" if vez is False else "falhas"] += 1
            continue
        assunto, html, texto = email_do_resumo(p["nome"], p["itens"])
        try:
            ok = bool(esc._ENVIAR(p["email"], assunto, html, texto, log_kind=KIND))
        except Exception:
            ok = False
        if ok:
            feito["enviados"] += 1
        else:
            feito["falhas"] += 1
            esc._registrar("escritorio:mencoes", f"o resumo de {dia} não saiu (conta {uid}); não sai de novo hoje")
    return feito
