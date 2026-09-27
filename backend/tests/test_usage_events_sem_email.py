# -*- coding: utf-8 -*-
"""`usage_events` sem e-mail: a telemetria grava só o `user_id`, e quem lê cruza pela CONTA.

🔒 27/09/2026 — auditoria de SI/LGPD (minimização). Todo evento de conta logada gravava o e-mail junto com o
`user_id`. Medido em 27/09: 5.427 eventos; 4.879 com e-mail, TODOS com `user_id`; 0 com conta apagada; 0 com
e-mail diferente do da conta atual. O e-mail era cópia — e dado pessoal a mais.

🪤 Não dava pra só parar de gravar. O painel de Atividade tirava as contas da casa e agrupava as pessoas PELO
e-mail do evento; a ficha do usuário achava os eventos PELO e-mail; 4 RPCs do admin idem. Parar de gravar sem
trocar a leitura faria o Pedro voltar a contar no próprio painel e a ficha dizer "nenhum evento" — calado.

O que se cobra aqui — cada painel mostra O MESMO NÚMERO com o e-mail no evento (hoje) e com ele zerado (depois):
  · POST /api/track EXECUTADO: a linha gravada não leva e-mail, com e sem login — e o id continua chegando;
  · /api/admin/activity EXECUTADO sobre o mesmo cenário nos dois estados → a MESMA resposta, e os números são os
    que o código de ad74225 (antes do conserto) dava no estado de hoje — conferido rodando o código velho;
  · a lista de contas falhando NÃO infla calada: `eventos_sem_conta_achada` sobe e a tela diz (dukpy);
  · a ficha do usuário acha os mesmos eventos nos dois estados; busca por e-mail sem perfil acha o id no auth;
  · as RPCs do admin (SQL — a bancada não roda): o arquivo da migração não lê `user_email` de `usage_events`,
    não tem e-mail escrito, mantém SECURITY DEFINER + search_path, e o script de zerar trava no md5 exato dela.
🚫 Não cobre: o banco de verdade (bloqueado na bancada). O ensaio das RPCs foi um DO-block desfeito em 27/09 —
antes = depois = depois com e-mail zerado nas 12 leituras; o resultado está no cabeçalho da migração.
"""
import asyncio
import hashlib
import io
import json
import os
import re
import sys
import urllib.parse as _up
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402
from _jsbancada import funcao_js, motor, _do_marcador_ate_fechar  # noqa: E402

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ADMIN = os.path.join(_RAIZ, "admin.html")
_UTILS = os.path.join(_RAIZ, "aiarq-utils.js")
_PEND = os.path.join(_RAIZ, "backend", "migrations_pendentes")
_MIGRACAO = os.path.join(_PEND, "usage_events_le_pelo_user_id.sql")
_ZERA = os.path.join(_PEND, "usage_events_zera_email_antigo.sql")


# ── a gravação: POST /api/track ─────────────────────────────────────────────

def _gravar(monkeypatch, conta):
    """Chama a rota de verdade; o banco vira uma lista local e a sessão é dublada."""
    gravados = []
    monkeypatch.setattr(main, "_supabase_insert",
                        lambda tabela, linha: gravados.append((tabela, linha)))
    monkeypatch.setattr(main, "_get_user_from_request", lambda *a, **k: conta)
    p = main.TrackPayload(event="view_dashboard", user_id="qualquer",
                          user_email="cliente-a@exemplo.com", meta={"cid": "c1"})
    assert asyncio.run(main.track_event(p, None)) == {"status": "ok"}
    assert len(gravados) == 1 and gravados[0][0] == "usage_events", gravados
    return gravados[0][1]


def test_evento_de_conta_logada_grava_o_id_e_NAO_o_email(monkeypatch):
    linha = _gravar(monkeypatch, {"id": "u-a", "email": "cliente-a@exemplo.com"})
    # 🧪 controle: a identidade continua chegando — sem isto o teste passaria com a rota gravando nada.
    assert linha["user_id"] == "u-a", linha
    assert not linha.get("user_email"), linha
    assert "cliente-a@exemplo.com" not in json.dumps(linha), linha


def test_evento_anonimo_tambem_nao_leva_email(monkeypatch):
    linha = _gravar(monkeypatch, None)
    assert linha["user_id"] == "" and not linha.get("user_email"), linha
    assert "@" not in json.dumps(linha), linha


# ── o painel de Atividade: o mesmo número, com e sem o e-mail no evento ─────

_AGORA = datetime.now(timezone.utc)
_ANTIGO = "2020-01-01T00:00:00Z"   # conta criada fora da janela: não vira `signup_created`


def _quando(dias, horas=0):
    return (_AGORA - timedelta(days=dias, hours=horas)).isoformat().replace("+00:00", "Z")


def _apelido_do_dono():
    local, dom = main.ADMIN_EMAIL.split("@", 1)
    return local + "+smoke@" + dom


def _contas():
    return [{"id": "u-a", "email": "cliente-a@exemplo.com", "created_at": _ANTIGO},
            {"id": "u-b", "email": "cliente-b@exemplo.com", "created_at": _ANTIGO},
            {"id": "u-dono", "email": main.ADMIN_EMAIL, "created_at": _ANTIGO},
            {"id": "u-smoke", "email": _apelido_do_dono(), "created_at": _ANTIGO}]


def _eventos_de_hoje():
    """Como estão HOJE no banco: conta logada com id E e-mail; anônimo sem os dois.

    O dono e o apelido dele (+smoke) estão aqui de propósito: é o filtro deles que dependia do e-mail."""
    email = {c["id"]: c["email"] for c in _contas()}
    base = [("view_dashboard", "u-a", 1), ("open_project", "u-a", 12),
            ("view_dashboard", "u-b", 20),
            ("view_dashboard", "u-dono", 0), ("open_project", "u-dono", 2), ("view_dashboard", "u-dono", 25),
            ("view_dashboard", "u-smoke", 3),
            ("view_landing", "", 1), ("view_landing", "", 4)]
    return [{"id": "e%d" % i, "event": ev, "user_id": uid, "user_email": email.get(uid, ""),
             "job_id": "", "path": "/", "meta": {"cid": "c%d" % i}, "created_at": _quando(dias, i)}
            for i, (ev, uid, dias) in enumerate(base)]


def _zerado(eventos):
    """Como vão ficar depois do `usage_events_zera_email_antigo.sql`."""
    return [dict(e, user_email="") for e in eventos]


def _banco(eventos):
    """Dubla o PostgREST HONRANDO o `select=`: coluna que a rota não pede não chega.

    🔑 É o que torna o "hoje" honesto: o banco ainda TEM o e-mail, mas a rota nova não o pede — e o código velho
    pedia (é assim que ele reproduz os números de antes)."""
    def _tudo(path, params=None, **k):
        if path != "usage_events":
            return 200, []
        cols = [c.strip() for c in ((params or {}).get("select") or "").split(",") if c.strip()]
        linhas = [dict(r) for r in eventos]
        if cols and cols != ["*"]:
            linhas = [{c: r[c] for c in cols if c in r} for r in linhas]
        return 200, linhas
    return _tudo


def _painel(monkeypatch, eventos, contas):
    monkeypatch.setattr(main, "_require_admin", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supa_rest_tudo", _banco(eventos))
    monkeypatch.setattr(main, "_auth_admin_list_users", lambda *a, **k: [dict(c) for c in contas])
    monkeypatch.setattr(main, "_usage_events_por_nome", lambda dias=365: [])
    return main.admin_activity(object(), days=30, limit=50)


def _numeros(d):
    return {"total_events": d["total_events"], "active_7d": d["active_7d"],
            "active_window": d["active_window"], "by_event": d["by_event"], "funnel": d["funnel"],
            "users": [(u["email"], u["events"]) for u in d["users"]]}


#: O que o código de ANTES (ad74225, lendo o e-mail do evento) mostrava para `_eventos_de_hoje()` — conferido em
#: 27/09 rodando aquele main.py com este mesmo cenário. Dono e +smoke fora; anônimo agrupado como "anonymous".
_NUMEROS_DE_ANTES = {
    "total_events": 5, "active_7d": 1, "active_window": 2,
    "by_event": {"view_dashboard": 2, "open_project": 1, "view_landing": 2},
    "funnel": {"view_landing": 2, "view_cadastro": 0, "signup_done": 0},
    "users": [("cliente-a@exemplo.com", 2), ("anonymous", 2), ("cliente-b@exemplo.com", 1)],
}


def test_o_painel_de_atividade_da_o_MESMO_numero_com_e_sem_o_email_no_evento(monkeypatch):
    hoje = _painel(monkeypatch, _eventos_de_hoje(), _contas())
    depois = _painel(monkeypatch, _zerado(_eventos_de_hoje()), _contas())
    assert _numeros(hoje) == _NUMEROS_DE_ANTES, _numeros(hoje)
    assert _numeros(depois) == _NUMEROS_DE_ANTES, _numeros(depois)
    # a resposta INTEIRA, não só os cartões: lista recente e "quem" também
    assert hoje == depois
    assert depois["eventos_sem_conta_achada"] == 0


def test_o_evento_recente_mostra_o_email_da_CONTA(monkeypatch):
    d = _painel(monkeypatch, _zerado(_eventos_de_hoje()), _contas())
    quem = {r["user_id"]: r["user_email"] for r in d["recent"] if r.get("user_id")}
    assert quem == {"u-a": "cliente-a@exemplo.com", "u-b": "cliente-b@exemplo.com"}, quem


def test_se_a_lista_de_contas_falhar_o_painel_DIZ_em_vez_de_inflar_calado(monkeypatch):
    """`_auth_admin_list_users` engole erro e devolve vazio. Sem a conta, o evento fica sem e-mail e o filtro da
    casa não o pega: o dono volta a contar (5 → 9). A tela não pode mostrar 9 como se fosse verdade."""
    d = _painel(monkeypatch, _zerado(_eventos_de_hoje()), [])
    assert d["eventos_sem_conta_achada"] == 7, d["eventos_sem_conta_achada"]
    assert d["total_events"] == 9, "o cenário perdeu os eventos do dono — o teste deixou de medir o risco"


def test_CONTROLE_conta_que_nao_veio_na_lista_conta_so_ela(monkeypatch):
    sem_b = [c for c in _contas() if c["id"] != "u-b"]
    d = _painel(monkeypatch, _zerado(_eventos_de_hoje()), sem_b)
    assert d["eventos_sem_conta_achada"] == 1, d["eventos_sem_conta_achada"]


# ── a tela do painel (o JavaScript real, no dukpy) ──────────────────────────

def _escape_html_real():
    src = io.open(_UTILS, encoding="utf-8").read()
    marca = "window.escapeHtml = function"
    return _do_marcador_ate_fechar(src, src.index(marca), "escapeHtml")


def _js():
    js = motor("var window = {}; true;")
    js.evaljs(_escape_html_real() + "; var escapeHtml = window.escapeHtml; true;")
    js.evaljs(funcao_js("htmlAvisoSemConta", _ADMIN))
    return js


def test_a_tela_avisa_quando_ha_evento_sem_conta_e_cala_quando_nao_ha():
    js = _js()
    assert js.evaljs("htmlAvisoSemConta(0)") == ""
    assert js.evaljs("htmlAvisoSemConta(undefined)") == ""
    um = js.evaljs("htmlAvisoSemConta(1)")
    assert "1 evento de conta logada" in um, um
    sete = js.evaljs("htmlAvisoSemConta(7)")
    assert "7 eventos de conta logada" in sete and "inflados" in sete, sete


def test_o_painel_poe_o_aviso_com_o_campo_que_a_rota_entrega(monkeypatch):
    corpo = funcao_js("loadActivity", _ADMIN)
    assert "htmlAvisoSemConta(d.eventos_sem_conta_achada)" in corpo
    # e o campo existe na resposta da rota (nome casado com o de cima)
    assert "eventos_sem_conta_achada" in _painel(monkeypatch, _eventos_de_hoje(), _contas())


# ── a ficha do usuário ──────────────────────────────────────────────────────

class _Req:
    headers = {}
    client = None


_PERFIL = {"user_id": "u-9", "full_name": "cliente-13", "email": "cliente-91@exemplo.com"}


def _eventos_da_ficha():
    return [{"event": "view_dashboard", "user_id": "u-9", "user_email": "cliente-91@exemplo.com",
             "path": "/", "job_id": "", "meta": {}, "created_at": "2026-09-21T10:00:00Z"},
            {"event": "open_project", "user_id": "u-9", "user_email": "cliente-91@exemplo.com",
             "path": "/", "job_id": "", "meta": {}, "created_at": "2026-09-20T10:00:00Z"},
            {"event": "view_dashboard", "user_id": "u-outro", "user_email": "cliente-92@exemplo.com",
             "path": "/", "job_id": "", "meta": {}, "created_at": "2026-09-19T10:00:00Z"}]


def _banco_da_ficha(mapa):
    """Dubla o PostgREST HONRANDO `coluna=eq.valor` e `select=` — o filtro é justamente o que muda aqui.
    (`in.(...)`, `order` e `limit` ficam de fora: não mudam nada nesta conta.)"""
    def _f(method, path, *a, **kw):
        tabela, _sep, consulta = path.partition("?")
        pares = _up.parse_qsl(consulta, keep_blank_values=True)
        linhas = [dict(r) for r in mapa.get(tabela, [])]
        for k, v in pares:
            if v.startswith("eq."):
                linhas = [r for r in linhas if str(r.get(k, "")) == v[3:]]
        sel = dict(pares).get("select", "")
        if sel and sel != "*":
            cols = [c.strip() for c in sel.split(",")]
            linhas = [{c: r[c] for c in cols if c in r} for r in linhas]
        return 200, linhas
    return _f


def _ficha(monkeypatch, chave, perfis, eventos, contas=()):
    monkeypatch.setattr(main, "_require_admin", lambda *a, **k: {"email": "admin@x"})
    monkeypatch.setattr(main, "_supa_rest_service",
                        _banco_da_ficha({"profiles": perfis, "usage_events": eventos}))
    monkeypatch.setattr(main, "_auth_admin_list_users", lambda *a, **k: [dict(c) for c in contas])
    return main.admin_ficha_usuario(chave, _Req())


def test_a_ficha_acha_os_MESMOS_eventos_com_e_sem_o_email_no_evento(monkeypatch):
    for chave in ("cliente-91@exemplo.com", "u-9"):
        hoje = _ficha(monkeypatch, chave, [_PERFIL], _eventos_da_ficha())
        depois = _ficha(monkeypatch, chave, [_PERFIL], _zerado(_eventos_da_ficha()))
        assert len(hoje["eventos"]) == 2, (chave, hoje["eventos"])
        assert hoje["eventos"] == depois["eventos"], chave
        assert [e["event"] for e in depois["eventos"]] == ["view_dashboard", "open_project"]
        assert depois["_falhas"] == [], depois["_falhas"]


def test_busca_por_email_de_conta_SEM_perfil_acha_o_id_na_lista_de_contas(monkeypatch):
    """Cadastro incompleto (25 contas em 27/09). Antes a seção achava os eventos pelo e-mail; sem o desvio pelo
    auth ela passaria a vir vazia com cara de "não fez nada"."""
    d = _ficha(monkeypatch, "cliente-91@exemplo.com", [], _zerado(_eventos_da_ficha()),
               contas=[{"id": "u-9", "email": "Cliente-91@Exemplo.com"}])
    assert len(d["eventos"]) == 2, d["eventos"]
    assert not any("eventos de uso" in f for f in d["_falhas"]), d["_falhas"]


def test_CONTROLE_sem_perfil_e_sem_conta_a_ficha_DIZ_que_nao_leu(monkeypatch):
    d = _ficha(monkeypatch, "cliente-91@exemplo.com", [], _zerado(_eventos_da_ficha()), contas=[])
    assert d["eventos"] == []
    assert any("eventos de uso" in f for f in d["_falhas"]), d["_falhas"]


def test_busca_por_id_sem_perfil_le_os_eventos_pelo_id(monkeypatch):
    d = _ficha(monkeypatch, "u-9", [], _zerado(_eventos_da_ficha()))
    assert len(d["eventos"]) == 2, d["eventos"]


# ── as RPCs do admin: o arquivo da migração (a bancada não roda SQL) ────────

_FUNCOES = {"admin_email_retorno", "admin_filhotes", "admin_funil_do_site", "admin_origem_visitas"}


def _texto(caminho):
    return io.open(caminho, encoding="utf-8").read().replace("\r\n", "\n")


def _funcoes(caminho):
    """{nome: (cabeçalho, corpo)} — o corpo é o texto entre os `$function$`, exatamente o `prosrc` do banco."""
    rx = re.compile(r"CREATE OR REPLACE FUNCTION public\.(\w+)\((.*?)AS \$function\$(.*?)\$function\$;", re.S)
    return {m.group(1): (m.group(2), m.group(3)) for m in rx.finditer(_texto(caminho))}


def _sem_comentario(sql):
    return re.sub(r"--[^\n]*", "", sql)


_NAO_E_APELIDO = {"where", "join", "left", "right", "inner", "full", "on", "group", "order", "limit", "cross"}


def _le_email_do_evento(corpo):
    """Os trechos em que o corpo lê `user_email` de `usage_events`: pelo apelido dela, ou sem apelido nenhum.

    Todo `user_email` tem que vir com o apelido de OUTRA tabela (projects, por ex.); sem apelido é ambíguo e
    reprova — a régua não depende de a tabela se chamar `u`."""
    sql = _sem_comentario(corpo)
    apelidos = set()
    for m in re.finditer(r"\b(?:from|join)\s+(?:public\.)?usage_events\b(?:\s+(?:as\s+)?(\w+))?", sql, re.I):
        a = (m.group(1) or "").lower()
        apelidos.add("usage_events" if (not a or a in _NAO_E_APELIDO) else a)
    if not apelidos:
        return []
    achados = []
    for m in re.finditer(r"(?:(\w+)\s*\.\s*)?\buser_email\b", sql, re.I):
        dono = (m.group(1) or "").lower()
        if not dono or dono in apelidos:
            achados.append(m.group(0))
    return achados


def test_CONTROLE_a_regua_do_sql_REPROVA_os_jeitos_de_ler_o_email_do_evento():
    """🧪 Todo guarda prova que reprova: os três jeitos das funções de antes, e um que não é leitura dela."""
    assert _le_email_do_evento("select 1 from usage_events u where lower(u.user_email) = p.email")
    assert _le_email_do_evento("from usage_events where coalesce(user_email,'') not ilike 'x'")
    assert _le_email_do_evento("from public.usage_events as ev where ev.user_email <> ''")
    assert _le_email_do_evento("from usage_events u join projects x on x.job_id = u.job_id "
                               "where x.user_email <> '' and u.user_email <> ''")
    assert not _le_email_do_evento("from usage_events u join projects x on x.job_id = u.job_id "
                                   "where x.user_email <> ''")
    assert not _le_email_do_evento("from projects p where p.user_email <> ''")
    assert not _le_email_do_evento("from usage_events u -- u.user_email não\n where u.user_id <> ''")


def test_nenhuma_rpc_da_migracao_le_o_email_do_evento():
    fs = _funcoes(_MIGRACAO)
    assert set(fs) == _FUNCOES, sorted(fs)
    for nome, (_cab, corpo) in fs.items():
        assert "usage_events" in corpo, nome
        assert _le_email_do_evento(corpo) == [], (nome, _le_email_do_evento(corpo))


def test_as_rpcs_seguem_com_a_permissao_do_dono_e_search_path_fixo():
    """CREATE OR REPLACE mantém dono e GRANT, mas NÃO SECURITY DEFINER nem o search_path: esquecer um deles
    muda quem lê auth.users (ou abre a função pra outro schema)."""
    for nome, (cab, _corpo) in _funcoes(_MIGRACAO).items():
        assert "SECURITY DEFINER" in cab and "SET search_path TO 'public'" in cab, nome


def test_a_migracao_e_o_script_de_zerar_nao_tem_email_escrito_nem_DROP():
    """Repo PÚBLICO: o dono sai de emails_da_casa(), nunca de um e-mail (ou pedaço dele) digitado aqui."""
    for caminho in (_MIGRACAO, _ZERA):
        txt = _texto(caminho)
        assert not re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", txt), caminho
        assert not re.search(r"\bdrop\b", _sem_comentario(txt), re.I), caminho
    for nome, (_cab, corpo) in _funcoes(_MIGRACAO).items():
        # coluna de e-mail comparada com padrão LITERAL ('%nome%'). `message ilike '%enviado%'` é texto de log, passa.
        achado = re.search(r"email\b[^\n]*?\bilike\s+'%[^%'\n]+%'", _sem_comentario(corpo), re.I)
        assert not achado, (nome, "e-mail comparado com nome digitado", achado and achado.group(0))
    for nome in ("admin_filhotes", "admin_funil_do_site", "admin_origem_visitas"):
        assert "split_part((public.emails_da_casa())[1], '@', 1)" in _funcoes(_MIGRACAO)[nome][1], nome


def test_CONTROLE_a_regua_do_nome_digitado_REPROVA_o_jeito_de_antes():
    rx = r"email\b[^\n]*?\bilike\s+'%[^%'\n]+%'"
    assert re.search(rx, "and coalesce(u.user_email,'') not ilike '%fulano%'", re.I)
    assert re.search(rx, "where a.email ilike '%fulano%'", re.I)
    assert not re.search(rx, "where a.email ilike '%' || split_part((public.emails_da_casa())[1], '@', 1) || '%'", re.I)
    assert not re.search(rx, "and message ilike '%enviado%' and message not ilike '%falhou%'", re.I)


def test_o_script_de_zerar_trava_no_md5_EXATO_da_migracao():
    """Se alguém mexer numa RPC da migração e esquecer o script, a trava 1 dele deixaria zerar com a versão
    errada no ar (ou barraria a certa). O md5 é do `prosrc` — o texto entre os `$function$`."""
    m = re.search(r"esperado jsonb := '(\{.*?\})';", _texto(_ZERA), re.S)
    assert m, "não achei o `esperado` no script de zerar"
    esperado = json.loads(m.group(1))
    calculado = {nome: hashlib.md5(corpo.encode("utf-8")).hexdigest()
                 for nome, (_cab, corpo) in _funcoes(_MIGRACAO).items()}
    assert esperado == calculado, (esperado, calculado)


def test_o_script_de_zerar_so_zera_depois_das_tres_travas():
    txt = _sem_comentario(_texto(_ZERA))
    i_update = txt.index("update public.usage_events set user_email = ''")
    for trava in ("PARE (trava 1)", "PARE (trava 2)", "PARE (trava 3)"):
        assert txt.index(trava) < i_update, trava
