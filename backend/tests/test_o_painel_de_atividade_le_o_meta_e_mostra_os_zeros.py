# -*- coding: utf-8 -*-
"""O painel de Atividade lê o `meta` e mostra os zeros.

🩸 18/09/2026 — item 8 da fila. Medido antes de escrever: **2.522 de 2.522**
eventos dos últimos 30 dias carregam `meta` (type=dwg, tela=revisao,
motivo=origem, campo=nenhum, n_itens, pendentes…), em **88 nomes** distintos —
e o painel jogava tudo fora: contava por nome e listava "quem/quando". A
telemetria dos avisos de 15/09 nasceu pra ser lida ali e não dava pra ler. E um
nome que registrou no passado e ficou em silêncio na janela simplesmente não
aparecia: silêncio com cara de "nunca existiu".

O que se cobra aqui:
  · `_meta_por_evento`: detalhe por evento, `cid` nunca (é o visitante, não o
    detalhe), chave numérica vira min/mediana/max, chave de texto vira os
    valores mais frequentes com teto;
  · `_nomes_em_silencio`: nomes do período longo que não estão na janela;
  · `admin_activity` EXECUTADO com as fontes dubladas entrega os dois campos e
    NÃO cai quando a RPC dos zeros falha (best-effort, e a tela diz);
  · as funções da tela RODANDO no dukpy: `resumoDoMeta`, `htmlDetalheDoEvento`
    e `htmlSilencio` — com o `escapeHtml` REAL do admin.html, porque o `meta` é
    texto que veio do navegador do visitante.

🚫 Não cobre: o `loadActivity` inteiro (DOM), nem o número real de zeros hoje
(depende do banco).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _jsbancada import funcao_js, motor, _do_marcador_ate_fechar  # noqa: E402

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ADMIN = os.path.join(_RAIZ, "admin.html")
_UTILS = os.path.join(_RAIZ, "aiarq-utils.js")


def _escape_html_real():
    """O `escapeHtml` que o admin USA mora em aiarq-utils.js, como
    `window.escapeHtml = function (s) {…}` — não é `function escapeHtml(`,
    então `funcao_js` não o acha. Recorta o REAL do marcador até a chave que
    fecha; copiar o corpo pra cá seria testar uma cópia."""
    import io
    src = io.open(_UTILS, encoding="utf-8").read()
    marca = "window.escapeHtml = function"
    return _do_marcador_ate_fechar(src, src.index(marca), "escapeHtml")


def _linha(ev, meta, quem="c@x.com", quando="2026-09-18T10:00:00Z"):
    return {"event": ev, "user_email": quem, "user_id": "u1", "job_id": "",
            "path": "", "meta": meta, "created_at": quando}


# ── o detalhe por evento ────────────────────────────────────────────────────

def test_o_meta_vira_detalhe_por_evento_e_o_cid_fica_de_fora():
    import main
    rows = [_linha("arquivo_escolhido", {"cid": "abc", "src": "google", "type": "dwg"}),
            _linha("arquivo_escolhido", {"cid": "def", "src": "google", "type": "pdf"}),
            _linha("arquivo_escolhido", {"cid": "ghi", "src": "direto", "type": "dwg"})]
    m = main._meta_por_evento(rows)
    assert set(m) == {"arquivo_escolhido"}
    assert "cid" not in m["arquivo_escolhido"], "o identificador do visitante virou 'detalhe'"
    assert m["arquivo_escolhido"]["type"] == [["dwg", 2], ["pdf", 1]]
    assert m["arquivo_escolhido"]["src"] == [["google", 2], ["direto", 1]]


def test_chave_numerica_vira_min_mediana_max_e_nao_lista_de_ruido():
    import main
    rows = [_linha("revisao_saiu", {"n_itens": n, "pendentes": p})
            for n, p in ((38, 37), (12, 3), (7, 0))]
    m = main._meta_por_evento(rows)["revisao_saiu"]
    assert m["n_itens"] == {"min": 7, "mediana": 12, "max": 38, "n": 3}, m
    assert isinstance(m["pendentes"], dict)


def test_CONTROLE_numero_misturado_com_texto_NAO_vira_estatistica():
    import main
    rows = [_linha("x", {"campo": 3}), _linha("x", {"campo": "nenhum"})]
    m = main._meta_por_evento(rows)["x"]
    assert isinstance(m["campo"], list), "uma média de '3' com 'nenhum' não existe"


def test_o_teto_de_valores_e_de_chaves_vale():
    import main
    rows = [_linha("e", {"k%d" % k: "v%d" % v for k in range(9)}) for v in range(9)]
    m = main._meta_por_evento(rows, topo_valores=2, topo_chaves=3)["e"]
    assert len(m) == 3, m.keys()
    assert all(len(v) == 2 for v in m.values()), m


def test_evento_sem_meta_ou_meta_vazio_nao_aparece():
    import main
    rows = [_linha("start_project", {}), _linha("signup_created", None),
            _linha("view_aba", {"tela": "home"})]
    assert set(main._meta_por_evento(rows)) == {"view_aba"}


# ── os zeros ────────────────────────────────────────────────────────────────

def test_os_zeros_sao_os_nomes_do_periodo_longo_que_NAO_estao_na_janela():
    import main
    por_nome = [{"event": "nps_exibido", "n": 8, "ultimo": "2026-09-10T12:00:00Z"},
                {"event": "view_aba", "n": 160, "ultimo": "2026-09-18T12:00:00Z"},
                {"event": "aviso_tipo:exibido", "n": 3, "ultimo": "2026-08-30T12:00:00Z"}]
    z = main._nomes_em_silencio(por_nome, {"view_aba": 141})
    assert [x["event"] for x in z] == ["nps_exibido", "aviso_tipo:exibido"], z
    assert z[0]["n_periodo"] == 8 and z[0]["ultimo"].startswith("2026-09-10")


def test_CONTROLE_sem_periodo_longo_nao_ha_zeros_e_nao_ha_erro():
    import main
    assert main._nomes_em_silencio([], {"a": 1}) == []
    assert main._nomes_em_silencio(None, {}) == []


# ── a rota, EXECUTADA ───────────────────────────────────────────────────────

def _rota(monkeypatch, rpc):
    import main
    rows = [_linha("arquivo_escolhido", {"cid": "abc", "type": "dwg"}),
            _linha("view_aba", {"cid": "abc", "tela": "home"})]
    monkeypatch.setattr(main, "_require_admin", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supa_rest_tudo",
                        lambda path, params=None, **k: (200, rows if path == "usage_events" else []))
    monkeypatch.setattr(main, "_auth_admin_list_users", lambda *a, **k: [])
    monkeypatch.setattr(main, "_email_eh_interno", lambda e: False)
    monkeypatch.setattr(main, "_usage_events_por_nome", rpc)
    return main.admin_activity(object(), days=30, limit=50)


def test_a_rota_entrega_o_detalhe_e_os_zeros(monkeypatch):
    d = _rota(monkeypatch, lambda dias=365: [
        {"event": "nps_exibido", "n": 8, "ultimo": "2026-09-10T12:00:00Z"},
        {"event": "view_aba", "n": 160, "ultimo": "2026-09-18T12:00:00Z"}])
    assert d["meta_por_evento"]["arquivo_escolhido"]["type"] == [["dwg", 1]]
    assert "cid" not in d["meta_por_evento"]["arquivo_escolhido"]
    assert [z["event"] for z in d["sem_registro_na_janela"]] == ["nps_exibido"]
    assert d["silencio_base_dias"] == 365
    # o `meta` continua indo na lista recente (é dele que a tela faz o resumo)
    assert d["recent"][0]["meta"]["type"] == "dwg"


def test_CONTROLE_se_a_RPC_dos_zeros_cair_o_painel_NAO_cai(monkeypatch):
    """Best-effort de verdade: a seção fica vazia e a tela DIZ; os outros
    números continuam chegando."""
    d = _rota(monkeypatch, lambda dias=365: [])
    assert d["sem_registro_na_janela"] == []
    assert d["total_events"] == 2 and d["by_event"] == {"arquivo_escolhido": 1, "view_aba": 1}


def test_a_RPC_e_chamada_como_POST_com_o_parametro_dias(monkeypatch):
    import main
    import urllib.request
    visto = {}

    class _R:
        def read(self):
            return json.dumps([{"event": "x", "n": 1, "ultimo": "2026-09-01T00:00:00Z"}]).encode()

    def _open(req, timeout=0):
        visto["url"] = req.full_url
        visto["method"] = req.get_method()
        visto["body"] = json.loads(req.data.decode())
        return _R()
    monkeypatch.setattr(urllib.request, "urlopen", _open)
    r = main._usage_events_por_nome(180)
    assert visto["url"].endswith("/rest/v1/rpc/usage_events_por_nome"), visto
    assert visto["method"] == "POST" and visto["body"] == {"dias": 180}, visto
    assert r and r[0]["event"] == "x"


# ── a tela, RODANDO o JavaScript real ───────────────────────────────────────

def _js():
    # ACT_LABELS e fmtBR são globais do admin.html; o mínimo pra as funções rodarem.
    # `window` vem ANTES do escapeHtml real, que se pendura nele.
    js = motor("var ACT_LABELS = {nps_exibido: '⭐ NPS'}; "
               "var window = {fmtBR: function(iso){ return String(iso); }}; true;")
    js.evaljs(_escape_html_real() + "; var escapeHtml = window.escapeHtml; true;")
    for nome in ("actLabel", "actFmtTime", "resumoDoMeta",
                 "htmlDetalheDoEvento", "htmlSilencio"):
        js.evaljs(funcao_js(nome, _ADMIN))
    return js


def test_a_tela_resume_o_meta_sem_o_cid_e_ESCAPANDO_o_que_veio_do_visitante():
    js = _js()
    out = js.evaljs("resumoDoMeta(%s)" % json.dumps(
        {"cid": "abc", "type": "dwg", "rotulo": "<img src=x onerror=alert(1)>"}))
    assert "cid" not in out
    assert "type=dwg" in out
    assert "<img" not in out and "&lt;img" in out, out


def test_a_tela_mostra_o_detalhe_numerico_e_o_de_texto():
    js = _js()
    out = js.evaljs("htmlDetalheDoEvento(%s)" % json.dumps(
        {"n_itens": {"min": 7, "mediana": 12, "max": 38, "n": 3},
         "type": [["dwg", 2], ["pdf", 1]]}))
    assert "mediana 12" in out and "max 38" in out
    assert "dwg" in out and "pdf" in out
    assert js.evaljs("htmlDetalheDoEvento({})") == "" and js.evaljs("htmlDetalheDoEvento(null)") == ""


def test_a_tela_mostra_os_zeros_e_DIZ_quando_nao_ha_nenhum():
    js = _js()
    out = js.evaljs("htmlSilencio(%s, 365)" % json.dumps(
        [{"event": "nps_exibido", "n_periodo": 8, "ultimo": "2026-09-10T12:00:00Z"}]))
    assert "1 nome sem registro" in out and "NPS" in out and "365" in out, out
    vazio = js.evaljs("htmlSilencio([], 365)")
    assert "Nenhum nome ficou em silêncio" in vazio, vazio
