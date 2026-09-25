# -*- coding: utf-8 -*-
"""Escritório × Google Drive (24/09/2026) — o que não pode dar errado.

  • a chave de acesso ao Drive de alguém NUNCA fica legível no banco (cifrada; chave errada = recusa);
  • o retorno do Google só vale com o `state` que NÓS assinamos e dentro do prazo;
  • só quem está no piloto conecta; só a DONA do projeto escolhe a pasta; quem é da equipe lista;
  • a lista usa a conta da DONA, e subpasta FORA da pasta do projeto é barrada (senão, pelo id,
    alguém da equipe listaria o Drive inteiro da admin);
  • o compartilhamento dá acesso a quem entrou, tira de quem saiu e da pasta antiga — e só mexe
    no que nós criamos;
  • a tela não carrega script nem janela do Google (a CSP do site barra, de propósito).
🧪 Controles: a assinatura certa passa; a subpasta DENTRO da pasta passa; membro que já tem acesso não
ganha outro.
"""
import os
import sys
import time
import types
import urllib.parse

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import escritorio as esc  # noqa: E402
import escritorio_drive as ed  # noqa: E402
from fastapi import HTTPException  # noqa: E402

PROJ = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
DONA = {"id": "uid-dona", "email": "dona@exemplo.com"}
EQUIPE = {"id": "uid-equipe", "email": "equipe@exemplo.com"}
REQ = types.SimpleNamespace(headers={"Authorization": "Bearer x"}, state=types.SimpleNamespace())


@pytest.fixture(autouse=True)
def _pecas(monkeypatch):
    antes = (esc._SERVICO, esc._COMO_USUARIO, esc._USUARIO, esc._REGISTRAR, ed._HTTP, ed.CLIENT_ID)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "segredo-de-teste-do-servidor")
    monkeypatch.setenv("GOOGLE_DRIVE_CLIENT_SECRET", "segredo-do-cliente")
    ed.CLIENT_ID = "cliente-de-teste.apps.googleusercontent.com"
    ed._CACHE_ACESSO.clear()
    yield
    (esc._SERVICO, esc._COMO_USUARIO, esc._USUARIO, esc._REGISTRAR, ed._HTTP, ed.CLIENT_ID) = antes
    ed._CACHE_ACESSO.clear()


class Banco:
    def __init__(self, papel="dono", usuario=DONA, piloto=True, pasta="PASTA_PROJ", conectada=True):
        self.papel, self.usuario, self.piloto = papel, usuario, piloto
        self.projeto = {"id": PROJ, "dono": DONA["id"], "nome": "Casa Exemplo", "pasta_id": pasta, "pasta_caminho": "Casa"}
        self.conexoes = {DONA["id"]: {"user_id": DONA["id"], "google_email": "dona@exemplo.com",
                                      "token_cifrado": ed.cifrar("refresh-da-dona")}} if conectada else {}
        self.membros = []           # {"id","user_id"}
        self.feitos = []            # linhas de escritorio_drive_permissoes
        self.escritas = []
        esc._SERVICO = self
        esc._USUARIO = lambda r: self.usuario
        esc._COMO_USUARIO = lambda req, m, path, body=None, **k: (200, self.papel)
        esc._REGISTRAR = None

    def __call__(self, method, path, body=None, params=None, prefer=None, **_k):
        params = params or {}
        if method != "GET":
            self.escritas.append({"m": method, "path": path, "body": body, "params": params})
        if path == "escritorio_piloto":
            return 200, ([{"user_id": "x"}] if self.piloto else [])
        if path == "escritorio_drive_conexoes":
            if method == "GET":
                uid = params["user_id"].split(".", 1)[1]
                return 200, ([self.conexoes[uid]] if uid in self.conexoes else [])
            if method == "POST":
                self.conexoes[body["user_id"]] = dict(body)
            return 201, None
        if path == "escritorio_projetos":
            if method == "PATCH":
                self.projeto.update(body)
            return 200, [self.projeto]
        if path == "escritorio_membros":
            return 200, self.membros
        if path == "escritorio_drive_permissoes":
            if method == "GET":
                return 200, self.feitos
            if method == "DELETE":
                i = params["id"].split(".", 1)[1]
                self.feitos = [f for f in self.feitos if str(f["id"]) != i]
            if method == "POST":
                self.feitos.append({"id": len(self.feitos) + 100, **body})
            return 201, None
        if path == "profiles":
            return 200, [{"user_id": m["user_id"], "email": m["user_id"] + "@exemplo.com"} for m in self.membros]
        raise AssertionError("tabela inesperada: " + path)


class Google:
    """O Google falso: registra as chamadas e responde por padrão de URL."""
    def __init__(self, pais=None, respostas=None):
        self.chamadas, self.pais, self.respostas = [], (pais or {}), (respostas or {})
        ed._HTTP = self

    def __call__(self, method, url, token=None, form=None, corpo=None, timeout=20):
        self.chamadas.append({"m": method, "url": url, "token": token, "form": form, "corpo": corpo})
        for chave, resp in self.respostas.items():
            if chave in url and (chave != "/permissions" or method == "POST"):
                return resp
        if "oauth2.googleapis.com/token" in url:
            return 200, {"access_token": "acesso-da-" + (form or {}).get("refresh_token", "x"), "expires_in": 3600}
        if "/files/" in url and "fields=parents" in url:
            fid = url.split("/files/", 1)[1].split("?", 1)[0]
            return 200, {"parents": [self.pais[fid]]} if fid in self.pais else {}
        if method == "DELETE":
            return 204, {}
        if url.endswith("/permissions") or "/permissions?" in url:
            return 200, {"id": "perm-" + str(len(self.chamadas))}
        if "/files?" in url:
            return 200, {"files": [{"id": "A1", "name": "planta.dwg", "mimeType": "x", "webViewLink": "https://drive.google.com/file/d/A1/view"}]}
        return 200, {}


# ── cifra e assinatura ──
def test_a_chave_do_drive_fica_cifrada_e_chave_errada_recusa(monkeypatch):
    c = ed.cifrar("refresh-secreto")
    assert "refresh-secreto" not in c and ed.decifrar(c) == "refresh-secreto"
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "outro-segredo")
    with pytest.raises(HTTPException) as e:
        ed.decifrar(c)
    assert e.value.status_code == 409


def test_o_retorno_do_google_so_vale_assinado_e_no_prazo():
    ok = ed.assinar_estado({"u": "uid", "p": "", "exp": time.time() + 60})
    assert ed.ler_estado(ok)["u"] == "uid"                             # controle
    corpo, sig = ok.rsplit(".", 1)
    for ruim in (corpo + ".00", "lixo", ed.assinar_estado({"u": "uid", "exp": time.time() - 1})):
        with pytest.raises(HTTPException):
            ed.ler_estado(ruim)


@pytest.mark.parametrize("entrada,esperado", [
    ("https://drive.google.com/drive/folders/1AbC_def-GHIjkl", "1AbC_def-GHIjkl"),
    ("https://drive.google.com/drive/u/2/folders/1AbC_def-GHIjkl?usp=sharing", "1AbC_def-GHIjkl"),
    ("https://drive.google.com/open?id=1AbC_def-GHIjkl", "1AbC_def-GHIjkl"),
    ("1AbC_def-GHIjkl", "1AbC_def-GHIjkl")])
def test_link_ou_id_da_pasta(entrada, esperado):
    assert ed.id_da_pasta(entrada) == esperado


def test_link_estranho_e_recusado():
    for ruim in ("", "https://exemplo.com/x", "a' or '1'='1"):
        with pytest.raises(HTTPException):
            ed.id_da_pasta(ruim)


# ── conectar ──
def test_so_quem_esta_no_piloto_conecta():
    Banco(piloto=False)
    with pytest.raises(HTTPException) as e:
        ed.drive_iniciar(REQ, {"projeto_id": PROJ})
    assert e.value.status_code == 403


def test_a_url_do_google_pede_so_o_drive_com_acesso_duradouro():
    Banco()
    q = urllib.parse.parse_qs(urllib.parse.urlparse(ed.drive_iniciar(REQ, {"projeto_id": PROJ})["url"]).query)
    assert q["scope"] == [ed.ESCOPO] and q["access_type"] == ["offline"] and q["prompt"] == ["consent"]
    assert q["redirect_uri"] == [ed.REDIRECT_URI] and q["client_id"] == [ed.CLIENT_ID]
    assert ed.ler_estado(q["state"][0])["u"] == DONA["id"]


def test_sem_segredo_no_servidor_nem_manda_pro_google(monkeypatch):
    Banco()
    monkeypatch.delenv("GOOGLE_DRIVE_CLIENT_SECRET")
    with pytest.raises(HTTPException) as e:
        ed.drive_iniciar(REQ, {"projeto_id": PROJ})
    assert e.value.status_code == 503


def test_volta_do_google_guarda_cifrado_e_volta_pra_aba_do_projeto():
    b = Banco(conectada=False)
    Google(respostas={"oauth2.googleapis.com/token": (200, {"access_token": "a", "refresh_token": "r-novo", "scope": ed.ESCOPO}),
                      "/about": (200, {"user": {"emailAddress": "dona@exemplo.com"}})})
    estado = ed.assinar_estado({"u": DONA["id"], "p": PROJ, "exp": time.time() + 60})
    r = ed.drive_callback(state=estado, code="codigo")
    assert r.headers["location"].endswith(f"escritorio.html?drive=ok#/p/{PROJ}/arquivos")
    guardado = b.conexoes[DONA["id"]]
    assert "r-novo" not in guardado["token_cifrado"] and ed.decifrar(guardado["token_cifrado"]) == "r-novo"


@pytest.mark.parametrize("caso,esperado", [("estado-falso", "erro"), ("negou", "negado"), ("desmarcou-o-drive", "sem-permissao")])
def test_volta_do_google_com_problema_nao_guarda_nada(caso, esperado):
    b = Banco(conectada=False)
    Google(respostas={"oauth2.googleapis.com/token": (200, {"access_token": "a", "refresh_token": "r", "scope": "openid"})})
    estado = ed.assinar_estado({"u": DONA["id"], "p": PROJ, "exp": time.time() + 60})
    kw = {"estado-falso": {"state": "lixo.00", "code": "c"}, "negou": {"state": estado, "error": "access_denied"},
          "desmarcou-o-drive": {"state": estado, "code": "c"}}[caso]
    r = ed.drive_callback(**kw)
    assert f"drive={esperado}" in r.headers["location"] and b.conexoes == {}


# ── pasta e lista ──
def test_so_a_dona_escolhe_a_pasta():
    Banco(papel="freela", usuario=EQUIPE)
    Google()
    with pytest.raises(HTTPException) as e:
        ed.projeto_pasta(PROJ, REQ, {"pasta": "PASTA_NOVA_123"})
    assert e.value.status_code == 403


def test_escolher_algo_que_nao_e_pasta_e_recusado():
    Banco()
    Google(respostas={"/files/NAO_E_PASTA1": (200, {"id": "NAO_E_PASTA1", "name": "x.pdf", "mimeType": "application/pdf"})})
    with pytest.raises(HTTPException) as e:
        ed.projeto_pasta(PROJ, REQ, {"pasta": "NAO_E_PASTA1"})
    assert e.value.status_code == 400


def test_pasta_escolhida_e_gravada_e_ja_compartilhada():
    b = Banco(pasta=None)
    b.membros = [{"id": "m1", "user_id": "u1"}]
    g = Google(respostas={"/files/PASTA_NOVA_123?": (200, {"id": "PASTA_NOVA_123", "name": "Casa 2026", "mimeType": ed.PASTA})})
    r = ed.projeto_pasta(PROJ, REQ, {"pasta": "https://drive.google.com/drive/folders/PASTA_NOVA_123"})
    assert b.projeto["pasta_id"] == "PASTA_NOVA_123" and r["compartilhados"] == 1
    perm = [c for c in g.chamadas if c["m"] == "POST" and "/permissions" in c["url"]][0]
    assert perm["corpo"] == {"role": "writer", "type": "user", "emailAddress": "u1@exemplo.com"}


def test_quem_nao_e_do_projeto_nao_lista():
    Banco(papel=None, usuario=EQUIPE)
    Google()
    with pytest.raises(HTTPException) as e:
        ed.projeto_arquivos(PROJ, REQ)
    assert e.value.status_code == 403


def test_equipe_lista_com_a_conta_da_dona():
    Banco(papel="freela", usuario=EQUIPE)
    g = Google()
    r = ed.projeto_arquivos(PROJ, REQ)
    assert r["arquivos"][0]["nome"] == "planta.dwg"
    listagem = [c for c in g.chamadas if "/files?" in c["url"]][0]
    assert listagem["token"] == "acesso-da-refresh-da-dona"
    assert urllib.parse.quote_plus("'PASTA_PROJ' in parents") in listagem["url"]


def test_subpasta_fora_da_pasta_do_projeto_e_barrada():
    Banco(papel="freela", usuario=EQUIPE)
    Google(pais={"OUTRA_PASTA_DA_DONA": "root"})
    with pytest.raises(HTTPException) as e:
        ed.projeto_arquivos(PROJ, REQ, pasta="OUTRA_PASTA_DA_DONA")
    assert e.value.status_code == 403


def test_controle_subpasta_dentro_da_pasta_do_projeto_passa():
    Banco(papel="freela", usuario=EQUIPE)
    Google(pais={"SUBPASTA_NETA": "SUBPASTA_FILHA", "SUBPASTA_FILHA": "PASTA_PROJ"})
    assert "arquivos" in ed.projeto_arquivos(PROJ, REQ, pasta="SUBPASTA_NETA")


def test_sem_pasta_e_sem_conexao_dizem_o_que_falta():
    Banco(papel="freela", usuario=EQUIPE, pasta=None)
    assert ed.projeto_arquivos(PROJ, REQ) == {"sem_pasta": True}
    Banco(papel="freela", usuario=EQUIPE, conectada=False)
    assert ed.projeto_arquivos(PROJ, REQ)["sem_conexao"] is True


# ── compartilhamento ──
def test_sincronizar_da_a_quem_entrou_tira_de_quem_saiu_e_da_pasta_antiga():
    b = Banco()
    b.membros = [{"id": "m-novo", "user_id": "u-novo"}, {"id": "m-fica", "user_id": "u-fica"}]
    b.feitos = [
        {"id": 1, "membro_id": "m-fica", "pasta_id": "PASTA_PROJ", "permission_id": "p-fica", "email": "u-fica@exemplo.com"},
        {"id": 2, "membro_id": "m-saiu", "pasta_id": "PASTA_PROJ", "permission_id": "p-saiu", "email": "saiu@exemplo.com"},
        {"id": 3, "membro_id": "m-fica", "pasta_id": "PASTA_VELHA", "permission_id": "p-velha", "email": "u-fica@exemplo.com"}]
    g = Google()
    r = ed.sincronizar(PROJ)
    assert r == {"compartilhados": 1, "tirados": 2, "falhas": []}
    apagadas = sorted(c["url"].split("/permissions/")[1].split("?")[0] for c in g.chamadas if c["m"] == "DELETE")
    assert apagadas == ["p-saiu", "p-velha"]                           # nunca o "p-fica" (controle)
    criadas = [c["corpo"]["emailAddress"] for c in g.chamadas if c["m"] == "POST" and "/permissions" in c["url"]]
    assert criadas == ["u-novo@exemplo.com"]


def test_compartilhamento_que_falha_nao_derruba_e_fica_listado():
    b = Banco()
    b.membros = [{"id": "m1", "user_id": "u1"}]
    Google(respostas={"/permissions": (400, {"error": {"message": "not a Google account"}})})
    r = ed.sincronizar(PROJ)
    assert r["compartilhados"] == 0 and r["falhas"] == ["u1@exemplo.com"] and b.feitos == []


def test_o_aceite_do_convite_chama_o_drive():
    assert esc._DEPOIS_DO_ACEITE is ed.sincronizar_em_segundo_plano
    fonte = open(os.path.join(os.path.dirname(_AQUI), "escritorio.py"), encoding="utf-8").read()
    ac = fonte[fonte.index("def aceitar_convite("):]
    assert ac.index("_DEPOIS_DO_ACEITE(m[\"projeto_id\"])") < ac.index("outro_email =")


# ── a tela ──
def test_a_tela_nao_carrega_script_nem_janela_do_google():
    h = open(os.path.join(os.path.dirname(os.path.dirname(_AQUI)), "escritorio.html"), encoding="utf-8").read()
    for proibido in ("accounts.google.com/gsi", "apis.google.com/js", "google.picker", "gapi.load"):
        assert proibido not in h, proibido
    assert "location.href = r.dados.url;" in h                       # vai pro Google navegando, não em janela
    assert "const ehLinkDoGoogle = (u) => /^https:\\/\\/(docs|drive)\\.google\\.com\\//.test(String(u || ''));" in h
