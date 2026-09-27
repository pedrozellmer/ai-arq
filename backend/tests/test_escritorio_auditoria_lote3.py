# -*- coding: utf-8 -*-
"""Lote 3 da auditoria completa do Escritório (26/09/2026) — os achados baixos.

Servidor: SRV-6 (leitura que falha virava memorial/cronograma automático), SRV-7 (2ª leitura do dono virava 403),
SRV-8 (reenvio matava o link), CONV-4 (reenvio desfazia um aceite no mesmo instante), DRV-3 (Emitidos de outro dono),
DRV-5 (lista cortada calada), DRV-6 ("acesso limitado" aberto pra equipe), DRV-9 (retorno do Google sem login ligava o
Drive de OUTRA pessoa), LGPD-1/DRV-8 (apagar a conta não desfazia o Drive), LGPD-7 (e-mail em claro no log e na
resposta do tick). Tela: TELA-5/6/8/9/10/11/12, LGPD-3 (dados de quem saiu), LGPD-9 (nomes no navegador após Sair),
CONV-6 (link trocado com a pessoa logada).
"""
import os
import sys
import types
import urllib.parse

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
_RAIZ = os.path.dirname(_BACKEND)
sys.path.insert(0, _BACKEND)

import escritorio as esc  # noqa: E402
import escritorio_drive as ed  # noqa: E402
from fastapi import HTTPException  # noqa: E402

PROJ = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
DONA = {"id": "11111111-1111-4111-8111-111111111111", "email": "dona@exemplo.com"}
OUTRA = {"id": "22222222-2222-4222-8222-222222222222", "email": "outra@exemplo.com"}
REQ = types.SimpleNamespace(headers={"Authorization": "Bearer x"}, state=types.SimpleNamespace())


def _ler(nome):
    return open(os.path.join(_RAIZ, nome), encoding="utf-8").read()


def _corpo(fonte, cabeca, fim="\n}\n"):
    i = fonte.index(cabeca)
    return fonte[i:fonte.index(fim, i)]


@pytest.fixture(autouse=True)
def _pecas(monkeypatch):
    antes = (esc._SERVICO, esc._COMO_USUARIO, esc._USUARIO, esc._REGISTRAR, ed._HTTP, ed.CLIENT_ID)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "segredo-de-teste-do-servidor")
    monkeypatch.setenv("GOOGLE_DRIVE_CLIENT_SECRET", "segredo-do-cliente")
    ed.CLIENT_ID = "cliente-de-teste.apps.googleusercontent.com"
    ed._CACHE_ACESSO.clear()
    ed._PENDENTES.clear()
    yield
    (esc._SERVICO, esc._COMO_USUARIO, esc._USUARIO, esc._REGISTRAR, ed._HTTP, ed.CLIENT_ID) = antes
    ed._CACHE_ACESSO.clear()
    ed._PENDENTES.clear()


class Banco:
    def __init__(self, usuario=DONA, papel="dono"):
        self.usuario, self.papel = usuario, papel
        self.conexoes = {DONA["id"]: {"user_id": DONA["id"], "google_email": "dona@exemplo.com",
                                      "token_cifrado": ed.cifrar("refresh-da-dona")}}
        self.membros, self.feitos, self.projetos, self.escritas = [], [], [], []
        esc._SERVICO = self
        esc._USUARIO = lambda r: self.usuario
        esc._COMO_USUARIO = lambda req, m, path, body=None, **k: (200, self.papel)
        esc._REGISTRAR = None

    def __call__(self, method, path, body=None, params=None, prefer=None, **_k):
        params = params or {}
        if method != "GET":
            self.escritas.append((method, path, dict(params), body))
        if path == "escritorio_drive_conexoes":
            if method == "GET":
                uid = params["user_id"].split(".", 1)[1]
                return 200, ([self.conexoes[uid]] if uid in self.conexoes else [])
            if method == "POST":
                self.conexoes[body["user_id"]] = dict(body)
            if method == "DELETE":
                self.conexoes.pop(params["user_id"].split(".", 1)[1], None)
            return 204, None
        if path == "escritorio_membros":
            return 200, self.membros
        if path == "escritorio_projetos":
            if "dono" in params:
                return 200, self.projetos
            return 200, [{"id": PROJ, "dono": DONA["id"], "nome": "Casa Exemplo", "pasta_id": "PASTA_PROJ", "pasta_caminho": "Casa"}]
        if path == "escritorio_drive_permissoes":
            if method == "DELETE":
                i = params["id"].split(".", 1)[1]
                self.feitos = [f for f in self.feitos if str(f["id"]) != i]
            return 200, self.feitos if method == "GET" else None
        return 200, []


class Google:
    def __init__(self, respostas=None):
        self.chamadas, self.respostas = [], respostas or {}
        ed._HTTP = self

    def __call__(self, method, url, token=None, form=None, corpo=None, timeout=20):
        self.chamadas.append({"m": method, "url": url, "form": form, "corpo": corpo})
        for chave, resp in self.respostas.items():
            if chave in url:
                return resp(method, url) if callable(resp) else resp
        if "oauth2.googleapis.com/token" in url:
            return 200, {"access_token": "acesso", "refresh_token": "refresh-novo", "scope": ed.ESCOPO, "expires_in": 3600}
        if "/about" in url:
            return 200, {"user": {"emailAddress": "google.da.pessoa@exemplo.com"}}
        return 200, {}


# ── DRV-9: o retorno do Google só vale confirmado pela conta que começou ──
def test_retorno_do_google_nao_grava_a_conexao_fica_pendente():
    b = Banco()
    b.conexoes = {}
    Google()
    estado = ed.assinar_estado({"u": DONA["id"], "p": PROJ, "exp": 9e12})
    r = ed.drive_callback(state=estado, code="codigo")
    loc = r.headers["location"]
    assert "drive=confirmar&c=" in loc and b.conexoes == {}, "nada gravado sem a confirmação da tela logada"
    c = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query)["c"][0]
    assert ed._PENDENTES[c]["u"] == DONA["id"] and "refresh-novo" not in str(ed._PENDENTES[c])


def test_outra_conta_nao_confirma_a_conexao_de_quem_comecou():
    b = Banco(usuario=OUTRA)
    b.conexoes = {}
    c = ed._guardar_pendente(DONA["id"], "refresh-da-vitima", "vitima@exemplo.com")
    with pytest.raises(HTTPException) as e:
        ed.drive_confirmar(REQ, {"c": c})
    assert e.value.status_code == 403 and b.conexoes == {} and c in ed._PENDENTES


def test_quem_comecou_confirma_e_a_conexao_e_gravada_cifrada():
    b = Banco()
    b.conexoes = {}
    c = ed._guardar_pendente(DONA["id"], "refresh-bom", "dona@exemplo.com")
    assert ed.drive_confirmar(REQ, {"c": c})["ok"] is True
    g = b.conexoes[DONA["id"]]
    assert ed.decifrar(g["token_cifrado"]) == "refresh-bom" and c not in ed._PENDENTES


def test_recusar_revoga_no_google_e_nao_grava():
    b = Banco()
    b.conexoes = {}
    g = Google()
    c = ed._guardar_pendente(DONA["id"], "refresh-recusado", "x@exemplo.com")
    assert ed.drive_confirmar(REQ, {"c": c, "recusar": True})["recusado"] is True
    assert b.conexoes == {} and any("revoke" in x["url"] for x in g.chamadas)


def test_pendente_vencido_nao_vale():
    Banco()
    c = ed._guardar_pendente(DONA["id"], "r", "x@exemplo.com")
    ed._PENDENTES[c]["exp"] = 0
    with pytest.raises(HTTPException) as e:
        ed.drive_confirmar(REQ, {"c": c})
    assert e.value.status_code == 404


# ── DRV-5: a lista segue as páginas e diz quando cortou ──
def test_lista_segue_as_paginas_e_marca_truncado(monkeypatch):
    Banco()
    paginas = {"": ({"files": [{"id": f"A{i}", "name": f"a{i}"} for i in range(3)], "nextPageToken": "p2"}),
               "p2": ({"files": [{"id": "B1", "name": "b1"}], "nextPageToken": "p3"}),
               "p3": ({"files": [{"id": "C1", "name": "c1"}]})}

    def lista(method, url):
        tok = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query)).get("pageToken", "")
        return 200, paginas[tok]
    Google(respostas={"/files?": lista})
    r = ed.projeto_arquivos(PROJ, REQ)
    assert [f["id"] for f in r["arquivos"]] == ["A0", "A1", "A2", "B1", "C1"] and r["truncado"] is False
    monkeypatch.setattr(ed, "_TETO_DA_LISTA", 3)
    r = ed.projeto_arquivos(PROJ, REQ)
    assert r["truncado"] is True, "passou do teto: a tela tem que saber que não é tudo"


# ── DRV-6: "acesso limitado" não abre pra equipe ──
def test_acesso_limitado_some_da_lista_da_equipe_e_nao_da_dona():
    itens = {"files": [{"id": "PUBLICA_001", "name": "Plantas", "mimeType": ed.PASTA},
                       {"id": "RESTRITA_01", "name": "Contrato", "mimeType": ed.PASTA, "inheritedPermissionsDisabled": True}]}
    Banco(papel="freela", usuario=OUTRA)
    Google(respostas={"/files?": (200, itens)})
    assert [f["id"] for f in ed.projeto_arquivos(PROJ, REQ)["arquivos"]] == ["PUBLICA_001"]
    Banco(papel="dono")                                          # controle: a dona vê as duas
    Google(respostas={"/files?": (200, itens)})
    assert len(ed.projeto_arquivos(PROJ, REQ)["arquivos"]) == 2


def test_equipe_nao_entra_em_subpasta_de_acesso_limitado():
    Banco(papel="freela", usuario=OUTRA)
    Google(respostas={"/files/RESTRITA_01?": (200, {"parents": ["PASTA_PROJ"], "inheritedPermissionsDisabled": True})})
    with pytest.raises(HTTPException) as e:
        ed.projeto_arquivos(PROJ, REQ, pasta="RESTRITA_01")
    assert e.value.status_code == 403


# ── DRV-3: Emitidos de OUTRO dono não é reaproveitada ──
def test_emitidos_de_outra_pessoa_nao_e_reaproveitada():
    g = Google(respostas={"/drive/v3/files?": lambda m, u: (200, {"files": [{"id": "EMITIDOS_DO_FREELA", "ownedByMe": False}]}) if m == "GET"
                          else (200, {"id": "EMITIDOS_DA_DONA"})})
    assert ed._pasta_emitidos("tok", "PASTA_PROJ") == "EMITIDOS_DA_DONA"
    assert [x for x in g.chamadas if x["m"] == "POST"], "criou a da dona"
    Google(respostas={"/drive/v3/files?": (200, {"files": [{"id": "EMITIDOS_OK", "ownedByMe": True}]})})
    assert ed._pasta_emitidos("tok", "PASTA_PROJ") == "EMITIDOS_OK"          # controle


# ── LGPD-1 / DRV-8: limpar o Escritório antes de apagar a conta ──
def test_limpar_conta_de_quem_e_equipe_sai_e_perde_a_pasta(monkeypatch):
    b = Banco()
    b.membros = [{"id": "m1", "projeto_id": PROJ, "papel": "freela", "status": "ativo"}]
    sinc = []
    monkeypatch.setattr(ed, "sincronizar", lambda pid: sinc.append(pid) or {"compartilhados": 0, "tirados": 1, "falhas": []})
    r = ed.limpar_conta(OUTRA["id"])
    assert r["saiu_de"] == 1 and r["tirados"] == 1 and r["pendentes"] == 0 and sinc == [PROJ]
    patch = [e for e in b.escritas if e[0] == "PATCH" and e[1] == "escritorio_membros"][0]
    assert patch[3]["status"] == "removido" and patch[2]["status"] == "eq.ativo"


def test_limpar_conta_da_dona_tira_o_que_demos_preserva_o_que_ja_existia_e_revoga():
    b = Banco()
    b.projetos = [{"id": PROJ}]
    b.feitos = [{"id": 1, "pasta_id": "PASTA_PROJ", "permission_id": "p-nosso", "ja_existia": False},
                {"id": 2, "pasta_id": "PASTA_PROJ", "permission_id": "p-da-mao", "ja_existia": True}]
    g = Google()
    r = ed.limpar_conta(DONA["id"])
    apagadas = [x["url"] for x in g.chamadas if x["m"] == "DELETE"]
    assert len(apagadas) == 1 and "p-nosso" in apagadas[0], "só o que o AI.arq deu sai do Drive"
    assert r["google_revogado"] is True and DONA["id"] not in b.conexoes and b.feitos == []


def test_limpar_conta_so_a_administracao(monkeypatch):
    Banco(usuario=OUTRA)
    monkeypatch.setattr(ed, "_email_da_administracao", lambda: "admin@exemplo.com")
    with pytest.raises(HTTPException) as e:
        ed.admin_limpar_conta(REQ, {"user_id": DONA["id"]})
    assert e.value.status_code == 403


# ── SRV-8 / CONV-4: o reenvio ──
def test_reenvio_le_a_admin_antes_de_trocar_o_link_e_nao_desfaz_aceite():
    src = open(os.path.join(_BACKEND, "escritorio.py"), encoding="utf-8").read()
    cv = src[src.index("def convidar("):src.index("def _recusa_se_nao_vale(")]
    assert cv.index('"papel": "eq.dono", "select": "nome,email"') < cv.index("token = novo_token()")
    assert '"status": f"eq.{atual[\'status\']}"' in cv
    assert "if status < 300 and dados == []:" in cv


# ── SRV-6 / SRV-7 ──
def test_memorial_que_nao_leu_e_502_e_nao_o_automatico(monkeypatch):
    import main
    monkeypatch.setattr(main, "_supa_rest_service", lambda *a, **k: (500, None))
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    with pytest.raises(HTTPException) as e:
        main._memorial_carregar_salvo("job-exemplo")
    assert e.value.status_code == 502
    monkeypatch.setattr(main, "_supa_rest_service", lambda *a, **k: (200, []))
    assert main._memorial_carregar_salvo("job-exemplo") is None           # controle: não existe ≠ não leu


def test_cronograma_que_nao_leu_e_502_nas_exportacoes(monkeypatch):
    import main
    monkeypatch.setattr(main, "_fin_cronograma_salvo", lambda req, job: (503, None))
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    with pytest.raises(HTTPException) as e:
        main._build_cronograma_for_export("job-exemplo")
    assert e.value.status_code == 502


def test_viewer_reusa_o_dono_ja_lido():
    src = open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    ow = src[src.index("def _require_project_owner("):src.index("def _usuario_ja_validado(")]
    assert "request.state.dono_do_projeto = owner" in ow
    vw = src[src.index("def _require_project_viewer("):src.index("def _so_leitura(")]
    assert 'getattr(getattr(request, "state", None), "dono_do_projeto", None) or _get_project_owner(job_id)' in vw


# ── LGPD-7 ──
def test_log_e_resposta_do_tick_sem_email():
    src = open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    assert 'print(f"[email] OK -> pessoa={_marca_do_email(to_email)} ({log_kind or \'email\'})"' in src
    assert 'print(f"[email] OK -> {to_email}' not in src
    t = src[src.index("def emails_auto_tick("):]
    t = t[:t.index("\n@app.")]
    assert '"detalhe": enviados' not in t and '"por_tipo": por_tipo_env' in t


# ── tela ──
def test_tela_lote3():
    h = _ler("escritorio.html")
    # TELA-8 / TELA-10 / TELA-9 / TELA-11
    assert "filter((m) => m && m.status !== 'removido');" in h
    assert "const convidados = MEMBROS.filter(conviteVivo).length;" in h
    assert "Math.round((iA / et.length) * 100)" in h and "Math.round(((iA + 1) / et.length)" not in h
    assert "if (ja) return toast('Essa etapa já está na lista.', true);" in h
    # TELA-5
    assert "const antes = viz[i - 1], depois = antes ? todos[todos.indexOf(antes) + 1] : todos[0];" in _corpo(h, "async function mover(id, st, i) {")
    assert "mud.posicao = Math.max(0, ...TAR.filter((x) => x.status === st).map((x) => x.posicao)) + 1;" in h
    assert "if (o.posicao === t.posicao) {" in _corpo(h, "async function subirDescer(id, d) {")
    # TELA-6: nome escapado no RegExp; placeholder sem prometer aviso
    assert "new RegExp('@' + escRe(curto(m))" in h and "pra chamar alguém" not in h
    # TELA-12
    for f in ("function editarComentario(", "function apagarComentario(", "function editarAta(", "function apagarAta(",
              "function gerirEtiquetas(", "async function renomearEtiqueta(", "async function apagarEtiqueta("):
        assert f in h, f
    # LGPD-3
    ad = _corpo(h, "function apagarDadosPessoa(id) {")
    assert ".from('escritorio_membros').delete({ count: 'exact' }).eq('id', id).eq('status', 'removido')" in ad
    assert "const saiu = souAdmin() ? MEMBROS.filter((m) => m.status === 'removido') : [];" in h
    # DRV-9 / DRV-5
    assert "apiEsc('drive/confirmar', 'POST'" in _corpo(h, "async function confirmarDrive(c) {")
    assert "if (volta === 'confirmar') {" in h and "d.truncado ?" in h


def test_sair_apaga_a_lembranca_do_escritorio():
    for pagina, ancora in (("menu-lateral.js", "window.aiarqConvite.limpar(); } catch (_) {}"),
                           ("dashboard.html", "window.aiarqConvite.limpar(); } catch (_) {}"),
                           ("cadastro.html", "window.aiarqConvite.limpar(); } catch (_) {}")):
        f = _ler(pagina)
        i = f.index(ancora)
        assert "localStorage.removeItem('aiarq_esc_mapa')" in f[i:i + 400], pagina


def test_link_trocado_com_a_pessoa_logada_procura_pelo_email():
    c = _ler("convite.html")
    rec = c[c.index("function recusado(r) {"):c.index("async function desligarConta()")]
    assert "if (r.status === 404 && SESSAO && !recusado.jaProcurou) {" in rec
    assert "if (opcoes.seNadaAchar) return opcoes.seNadaAchar();" in c


def test_admin_tem_o_botao_de_limpar_antes_de_excluir():
    a = _ler("admin-usuario.html")
    assert "`${API_BASE}/api/escritorio/admin/limpar-conta`" in a and "onclick=\"limparEscritorio(this)\"" in a
