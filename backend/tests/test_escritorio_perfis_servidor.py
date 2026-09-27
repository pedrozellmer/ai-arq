# -*- coding: utf-8 -*-
"""Perfis do Escritório no SERVIDOR (26/09/2026 — maquete aprovada pelo Pedro; banco na seção 26).

O banco já separa o que cada perfil vê. Aqui, o que o servidor faz com a chave da dona (que enxerga tudo):
  • convite com perfil: cliente/fornecedor gravados certos; reenviar SEM perfil mantém o que era;
  • a subpasta do fornecedor tem que estar DENTRO do projeto e não ser a pasta inteira;
  • Arquivos: cliente não navega; fornecedor só na subpasta dele;
  • o quantitativo/memorial/pranchas (projeto medido) é só da EQUIPE — cliente é membro ativo e não vê;
  • Drive: equipe EDITA a pasta do projeto, fornecedor LÊ a subpasta, cliente não ganha pasta;
  • "mandar pra": acesso de leitura ao ARQUIVO emitido (nunca à pasta Emitidos), só pra cliente/fornecedor
    ativo deste projeto; quem sai perde; o histórico de pra quem foi fica;
  • a resposta do cliente vai COM O LOGIN DELE (quem decide é o banco) e avisa a admin sem enxurrada;
  • cliente e fornecedor não entram na esteira de cliente novo, e o "sua área também" é só da equipe.
🧪 O banco falso daqui FILTRA como o PostgREST (eq, neq, in, is, not.is, gte): o dos testes antigos devolvia
tudo, e um filtro esquecido (papel=eq.freela) passaria verde.
"""
import os
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import escritorio as esc  # noqa: E402
import escritorio_drive as ed  # noqa: E402
from fastapi import HTTPException  # noqa: E402

PROJ = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OUTRO_PROJ = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
M_DONO = "00000000-0000-4000-8000-000000000001"
M_EQ = "00000000-0000-4000-8000-000000000002"
M_FORN = "00000000-0000-4000-8000-000000000003"
M_CLI = "00000000-0000-4000-8000-000000000004"
M_CLI_OUTRO = "00000000-0000-4000-8000-000000000005"
E1 = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee1"
DONA = {"id": "uid-dona", "email": "dona@exemplo.com", "email_confirmado": True}
EQUIPE = {"id": "uid-equipe", "email": "equipe@exemplo.com", "email_confirmado": True}
FORN = {"id": "uid-forn", "email": "fornecedor@exemplo.com", "email_confirmado": True}
CLI = {"id": "uid-cli", "email": "cliente@exemplo.com", "email_confirmado": True}
REQ = types.SimpleNamespace(headers={"Authorization": "Bearer x"}, state=types.SimpleNamespace())
FUTURO = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()


class BancoFiel:
    """Tabelas em memória que filtram como o PostgREST."""
    def __init__(self):
        self.t = {k: [] for k in (
            "escritorio_projetos", "escritorio_membros", "escritorio_drive_permissoes", "escritorio_drive_conexoes",
            "escritorio_emissoes", "escritorio_emissao_destinos", "escritorio_emissao_eventos", "escritorio_piloto",
            "escritorio_convites_enviados", "profiles")}
        self.falhar = set()          # (método, tabela) que devolvem 500
        self.rls_recusa = False      # a gravação COMO USUÁRIO bate na RLS
        self._n = 0

    @staticmethod
    def casa(linha, params):
        for k, v in (params or {}).items():
            if k in ("select", "order", "limit", "on_conflict"):
                continue
            atual, v = linha.get(k), str(v)
            if v.startswith("eq."):
                ok = str(atual) == v[3:]
            elif v.startswith("neq."):
                ok = str(atual) != v[4:]
            elif v.startswith("in.("):
                ok = str(atual) in v[4:-1].split(",")
            elif v == "is.true":
                ok = atual is True
            elif v == "is.null":
                ok = atual is None
            elif v == "not.is.null":
                ok = atual is not None
            elif v.startswith("gte."):
                ok = str(atual or "") >= v[4:]
            else:
                raise AssertionError("filtro não previsto: %s=%s" % (k, v))
            if not ok:
                return False
        return True

    def __call__(self, method, path, body=None, params=None, prefer=None, **_k):
        path = path.lstrip("/")
        if path not in self.t:
            raise AssertionError("tabela inesperada: " + path)
        if (method, path) in self.falhar:
            return 500, None
        linhas = self.t[path]
        if method == "GET":
            return 200, [dict(x) for x in linhas if self.casa(x, params)]
        if method == "POST":
            self._n += 1
            nova = {"id": "id-%d" % self._n, **(body or {})}
            linhas.append(nova)
            return 201, [dict(nova)]
        if method == "PATCH":
            alvo = [x for x in linhas if self.casa(x, params)]
            for x in alvo:
                x.update(body or {})
            return 200, [dict(x) for x in alvo]
        if method == "DELETE":
            self.t[path] = [x for x in linhas if not self.casa(x, params)]
            return 204, None
        raise AssertionError(method)

    def como_usuario(self, method, path, body):
        """A resposta do cliente gravada COM O LOGIN DELE (aqui: o que o banco faria)."""
        assert (method, path) == ("POST", "escritorio_emissao_eventos"), (method, path)
        if self.rls_recusa:
            return 403, {"code": "42501", "message": "new row violates row-level security policy"}
        self._n += 1
        nova = {"id": "ev-%d" % self._n, **body, "pelo_cliente": True,
                "criado_em": datetime.now(timezone.utc).isoformat()}
        self.t[path].append(nova)
        return 201, [dict(nova)]


class GoogleFiel:
    def __init__(self, pastas=None, pais=None):
        self.pastas, self.pais, self.chamadas = (pastas or {}), (pais or {}), []
        self.falha_permissao = False
        ed._HTTP = self

    def __call__(self, method, url, token=None, form=None, corpo=None, timeout=20):
        self.chamadas.append((method, url, corpo))
        if "oauth2.googleapis.com/token" in url:
            return 200, {"access_token": "acesso", "expires_in": 3600}
        if method == "DELETE":
            return 204, {}
        if "/permissions" in url:
            if method == "POST":
                return (500, None) if self.falha_permissao else (200, {"id": "perm-%d" % len(self.chamadas)})
            return 200, {"permissions": []}
        if "/files/" in url:
            fid = url.split("/files/", 1)[1].split("?", 1)[0]
            if "fields=parents" in url:
                return (200, {"parents": [self.pais[fid]]}) if fid in self.pais else (200, {})
            if fid in self.pastas:
                return 200, {"id": fid, **self.pastas[fid]}
            return 404, {}
        if "/files?" in url:
            return 200, {"files": [{"id": "ARQ1", "name": "detalhe.dwg", "mimeType": "x"}]}
        return 200, {}

    def permissoes_dadas(self):
        return [(url.split("/files/", 1)[1].split("/", 1)[0], c["role"], c["emailAddress"])
                for m, url, c in self.chamadas if m == "POST" and "/permissions" in url]

    def permissoes_tiradas(self):
        return [url.split("/files/", 1)[1].split("?", 1)[0] for m, url, _ in self.chamadas if m == "DELETE"]


@pytest.fixture(autouse=True)
def _pecas(monkeypatch):
    nomes = ("_SERVICO", "_COMO_USUARIO", "_USUARIO", "_REGISTRAR", "_ENVIAR", "_MOLDURA",
             "_DEPOIS_DO_ACEITE", "_PASTA_DO_FORNECEDOR")
    antes = {n: getattr(esc, n) for n in nomes}
    antes_http = ed._HTTP
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "segredo-de-teste-do-servidor")
    monkeypatch.setenv("GOOGLE_DRIVE_CLIENT_SECRET", "segredo-do-cliente")
    ed._CACHE_ACESSO.clear()
    yield
    for n, v in antes.items():
        setattr(esc, n, v)
    ed._HTTP = antes_http
    ed._CACHE_ACESSO.clear()


def montar(usuario, papel):
    b, enviados, depois = BancoFiel(), [], []
    esc._SERVICO = b
    esc._USUARIO = lambda r: usuario
    esc._COMO_USUARIO = lambda req, m, path, body=None, **k: (
        (200, papel) if path == "rpc/escritorio_papel" else b.como_usuario(m, path, body))
    esc._REGISTRAR = None
    esc._MOLDURA = lambda titulo, corpo, **k: "<h1>%s</h1>%s" % (titulo, corpo)
    esc._ENVIAR = lambda para, assunto, html, texto="", **k: enviados.append(
        {"para": para, "assunto": assunto, "html": html, "kind": k.get("log_kind")}) or True
    esc._DEPOIS_DO_ACEITE = lambda pid: depois.append(pid)
    esc._PASTA_DO_FORNECEDOR = ed.pasta_do_fornecedor
    b.t["escritorio_projetos"].append({"id": PROJ, "nome": "Casa Exemplo", "dono": DONA["id"],
                                       "pasta_id": "PASTA_PROJ", "pasta_caminho": "Casa"})
    b.t["escritorio_membros"].append({"id": M_DONO, "projeto_id": PROJ, "papel": "dono", "status": "ativo",
                                      "user_id": DONA["id"], "nome": "Admin Exemplo", "email": DONA["email"]})
    b.t["escritorio_piloto"].append({"user_id": DONA["id"]})
    b.t["escritorio_drive_conexoes"].append({"user_id": DONA["id"], "google_email": DONA["email"],
                                             "token_cifrado": ed.cifrar("refresh-da-dona")})
    return b, enviados, depois


def membro(b, mid, papel, user, status="ativo", **extra):
    linha = {"id": mid, "projeto_id": PROJ, "papel": papel, "status": status, "user_id": user["id"],
             "email": user["email"], "email_conta": user["email"], "nome": papel.title() + " Exemplo",
             "drive_pasta_id": None, "drive_pasta_nome": None, **extra}
    b.t["escritorio_membros"].append(linha)
    return linha


def _pastas():
    return GoogleFiel(pastas={"PASTA_PROJ": {"name": "Casa", "mimeType": ed.PASTA},
                              "PASTA_MARC": {"name": "Marcenaria", "mimeType": ed.PASTA},
                              "PASTA_FORA": {"name": "Outra obra", "mimeType": ed.PASTA},
                              "ARQUIVO_SOLTO": {"name": "planta.pdf", "mimeType": "application/pdf"}},
                      pais={"PASTA_MARC": "PASTA_PROJ", "ARQUIVO_SOLTO": "PASTA_PROJ", "PASTA_FORA": "root"})


# ── convite com perfil ──
def test_convite_de_cliente_grava_o_papel_sem_pasta_sem_baixar_e_com_o_texto_dele():
    b, enviados, _ = montar(DONA, "dono")
    r = esc.convidar(PROJ, REQ, {"email": "cliente@exemplo.com", "perfil": "cliente"})
    novo = [m for m in b.t["escritorio_membros"] if m.get("email") == "cliente@exemplo.com"][0]
    assert r["perfil"] == "cliente" and novo["papel"] == "cliente" and novo["status"] == "convidado"
    assert novo["pode_baixar"] is False and novo.get("drive_pasta_id") is None
    assert "acompanhar o projeto" in enviados[0]["html"] and "trabalhar" not in enviados[0]["html"]


def test_controle_convite_sem_perfil_continua_sendo_da_equipe():
    b, enviados, _ = montar(DONA, "dono")
    r = esc.convidar(PROJ, REQ, {"email": "equipe@exemplo.com"})
    novo = [m for m in b.t["escritorio_membros"] if m.get("email") == "equipe@exemplo.com"][0]
    assert r["perfil"] == "equipe" and novo["papel"] == "freela" and "trabalhar" in enviados[0]["html"]


def test_convite_de_fornecedor_guarda_a_subpasta_conferida_no_drive():
    b, enviados, _ = montar(DONA, "dono")
    _pastas()
    esc.convidar(PROJ, REQ, {"email": "fornecedor@exemplo.com", "perfil": "fornecedor", "pasta": "PASTA_MARC"})
    novo = [m for m in b.t["escritorio_membros"] if m.get("email") == "fornecedor@exemplo.com"][0]
    assert (novo["papel"], novo["drive_pasta_id"], novo["drive_pasta_nome"]) == ("fornecedor", "PASTA_MARC", "Marcenaria")
    assert "a sua parte do projeto" in enviados[0]["html"]


@pytest.mark.parametrize("pasta,motivo", [("PASTA_PROJ", "projeto inteiro"), ("PASTA_FORA", "não está dentro"),
                                          ("ARQUIVO_SOLTO", "não é uma pasta"), ("NAO_EXISTE_NO_DRIVE", "não é uma pasta")])
def test_subpasta_do_fornecedor_fora_do_projeto_ou_a_pasta_inteira_e_recusada_antes_de_gravar(pasta, motivo):
    b, enviados, _ = montar(DONA, "dono")
    _pastas()
    with pytest.raises(HTTPException) as e:
        esc.convidar(PROJ, REQ, {"email": "fornecedor@exemplo.com", "perfil": "fornecedor", "pasta": pasta})
    assert e.value.status_code == 400 and motivo in e.value.detail
    assert not [m for m in b.t["escritorio_membros"] if m.get("email") == "fornecedor@exemplo.com"] and not enviados


def test_perfil_inventado_e_recusado():
    montar(DONA, "dono")
    with pytest.raises(HTTPException) as e:
        esc.convidar(PROJ, REQ, {"email": "x@exemplo.com", "perfil": "socio"})
    assert e.value.status_code == 400


def test_reenviar_sem_perfil_mantem_o_cliente_e_trocar_o_perfil_limpa_a_pasta():
    b, _, _ = montar(DONA, "dono")
    linha = membro(b, M_CLI, "fornecedor", CLI, status="convidado", convite_expira=FUTURO,
                   drive_pasta_id="PASTA_MARC", drive_pasta_nome="Marcenaria")
    esc.convidar(PROJ, REQ, {"email": CLI["email"], "nome": "Pessoa"})          # o "reenviar" da tela
    assert linha["papel"] == "fornecedor" and linha["drive_pasta_id"] == "PASTA_MARC"
    esc.convidar(PROJ, REQ, {"email": CLI["email"], "perfil": "cliente"})
    assert linha["papel"] == "cliente" and linha["drive_pasta_id"] is None and linha["pode_baixar"] is False


def test_a_pagina_do_convite_e_a_lista_da_conta_dizem_o_perfil():
    b, _, _ = montar(CLI, None)
    token = "T" * 43
    membro(b, M_CLI, "cliente", CLI, status="convidado", convite_expira=FUTURO, convite_hash=esc.hash_do_token(token))
    assert esc.ver_convite({"token": token})["perfil"] == "cliente"
    assert esc.convites_pendentes_da_conta(REQ)["convites"][0]["perfil"] == "cliente"


@pytest.mark.parametrize("papel,sincroniza", [("cliente", False), ("fornecedor", True), ("freela", True)])
def test_aceite_so_mexe_no_drive_de_quem_ganha_pasta(papel, sincroniza):
    b, _, depois = montar(CLI, None)
    token = "T" * 43
    membro(b, M_CLI, papel, CLI, status="convidado", convite_expira=FUTURO, convite_hash=esc.hash_do_token(token),
           user_id=None)
    r = esc.aceitar_convite(REQ, {"token": token})
    assert r["perfil"] == esc.PERFIL_DO_PAPEL[papel] and (depois == [PROJ]) is sincroniza


# ── Arquivos ──
def test_cliente_nao_navega_na_pasta_do_projeto():
    b, _, _ = montar(CLI, "cliente")
    membro(b, M_CLI, "cliente", CLI)
    _pastas()
    with pytest.raises(HTTPException) as e:
        ed.projeto_arquivos(PROJ, REQ)
    assert e.value.status_code == 403 and "Emissões" in e.value.detail


def test_fornecedor_lista_so_a_subpasta_dele_e_nao_sobe_pro_projeto():
    b, _, _ = montar(FORN, "fornecedor")
    membro(b, M_FORN, "fornecedor", FORN, drive_pasta_id="PASTA_MARC", drive_pasta_nome="Marcenaria")
    _pastas()
    r = ed.projeto_arquivos(PROJ, REQ)
    assert r["pasta"]["id"] == "PASTA_MARC" and r["pasta"]["atual"] == "PASTA_MARC"
    with pytest.raises(HTTPException) as e:
        ed.projeto_arquivos(PROJ, REQ, pasta="PASTA_PROJ")        # a pasta do projeto inteiro, pelo id
    assert e.value.status_code == 403


def test_fornecedor_sem_subpasta_nao_ve_nada_e_subpasta_movida_pra_fora_e_recusada():
    b, _, _ = montar(FORN, "fornecedor")
    linha = membro(b, M_FORN, "fornecedor", FORN)
    g = _pastas()
    assert ed.projeto_arquivos(PROJ, REQ) == {"sem_pasta": True, "fornecedor": True}
    linha.update(drive_pasta_id="PASTA_MARC", drive_pasta_nome="Marcenaria")
    g.pais["PASTA_MARC"] = "PASTA_FORA"                          # a admin tirou a pasta de dentro do projeto
    with pytest.raises(HTTPException) as e:
        ed.projeto_arquivos(PROJ, REQ)
    assert e.value.status_code == 403


def test_controle_equipe_continua_vendo_a_pasta_do_projeto():
    b, _, _ = montar(EQUIPE, "freela")
    membro(b, M_EQ, "freela", EQUIPE)
    _pastas()
    assert ed.projeto_arquivos(PROJ, REQ)["pasta"]["id"] == "PASTA_PROJ"


# ── o projeto medido é só da equipe ──
def test_o_quantitativo_nao_abre_pro_cliente_nem_pro_fornecedor(monkeypatch):
    import main
    b = BancoFiel()
    b.t["escritorio_projetos"].append({"id": PROJ, "job_id": "job-exemplo"})
    for mid, papel, u in ((M_EQ, "freela", EQUIPE), (M_FORN, "fornecedor", FORN), (M_CLI, "cliente", CLI)):
        b.t["escritorio_membros"].append({"id": mid, "projeto_id": PROJ, "papel": papel, "status": "ativo",
                                          "user_id": u["id"], "pode_baixar": True})
    monkeypatch.setattr(main, "_supa_rest_service", b)
    assert main._equipe_do_projeto_medido("job-exemplo", CLI["id"]) is None
    assert main._equipe_do_projeto_medido("job-exemplo", FORN["id"]) is None
    assert main._equipe_do_projeto_medido("job-exemplo", EQUIPE["id"]) == {"escritorio_id": PROJ, "pode_baixar": True}


# ── Drive: quem ganha o quê ──
def test_equipe_edita_o_projeto_fornecedor_le_a_subpasta_cliente_nao_ganha_pasta():
    b, _, _ = montar(DONA, "dono")
    membro(b, M_EQ, "freela", EQUIPE)
    membro(b, M_FORN, "fornecedor", FORN, drive_pasta_id="PASTA_MARC", drive_pasta_nome="Marcenaria")
    membro(b, M_CLI, "cliente", CLI)
    g = _pastas()
    r = ed.sincronizar(PROJ)
    assert sorted(g.permissoes_dadas()) == [("PASTA_MARC", "reader", FORN["email"]), ("PASTA_PROJ", "writer", EQUIPE["email"])]
    assert r["compartilhados"] == 2 and not r["falhas"]
    # o fornecedor sai: perde a subpasta; a equipe fica como estava
    b.t["escritorio_membros"][2]["status"] = "removido"
    g.chamadas.clear()
    ed.sincronizar(PROJ)
    assert [t.split("/permissions/")[0] for t in g.permissoes_tiradas()] == ["PASTA_MARC"] and not g.permissoes_dadas()


# ── mandar a emissão ──
def _emissao(b):
    b.t["escritorio_emissoes"].append({"id": E1, "projeto_id": PROJ, "copia_id": "COPIA1", "arquivo_nome": "Planta.pdf",
                                       "copia_nome": "Planta_R02.pdf", "revisao": 2})


def test_mandar_da_leitura_so_no_arquivo_e_so_pra_cliente_ou_fornecedor_deste_projeto():
    b, _, _ = montar(DONA, "dono")
    membro(b, M_EQ, "freela", EQUIPE)
    membro(b, M_FORN, "fornecedor", FORN)
    membro(b, M_CLI, "cliente", CLI)
    b.t["escritorio_membros"].append({"id": M_CLI_OUTRO, "projeto_id": OUTRO_PROJ, "papel": "cliente",
                                      "status": "ativo", "email_conta": "outro@exemplo.com"})
    _emissao(b)
    g = _pastas()
    r = ed.projeto_mandar_emissao(PROJ, E1, REQ, {"para": [M_CLI, M_FORN, M_EQ, M_CLI_OUTRO, "lixo"]})
    assert r["mandados"] == 2 and sorted(r["falhas"]) == sorted([M_EQ, M_CLI_OUTRO])
    assert sorted(g.permissoes_dadas()) == [("COPIA1", "reader", CLI["email"]), ("COPIA1", "reader", FORN["email"])]
    assert len(b.t["escritorio_emissao_destinos"]) == 2
    enviados = [e for e in b.t["escritorio_emissao_eventos"] if e["tipo"] == "enviado"]
    assert len(enviados) == 1                                   # foi pro cliente: "Enviada ao cliente"
    # de novo: quem já tem fica como está, e o "enviado" não duplica
    g.chamadas.clear()
    assert ed.projeto_mandar_emissao(PROJ, E1, REQ, {"para": [M_CLI]})["mandados"] == 0 and not g.permissoes_dadas()
    assert len([e for e in b.t["escritorio_emissao_eventos"] if e["tipo"] == "enviado"]) == 1


def test_controle_mandar_so_pro_fornecedor_nao_registra_enviado_ao_cliente():
    b, _, _ = montar(DONA, "dono")
    membro(b, M_FORN, "fornecedor", FORN)
    _emissao(b)
    _pastas()
    assert ed.projeto_mandar_emissao(PROJ, E1, REQ, {"para": [M_FORN]})["mandados"] == 1
    assert b.t["escritorio_emissao_eventos"] == []


def test_se_o_registro_falha_o_acesso_dado_no_drive_e_desfeito():
    b, _, _ = montar(DONA, "dono")
    membro(b, M_CLI, "cliente", CLI)
    _emissao(b)
    g = _pastas()
    b.falhar.add(("POST", "escritorio_emissao_destinos"))
    r = ed.projeto_mandar_emissao(PROJ, E1, REQ, {"para": [M_CLI]})
    assert r["mandados"] == 0 and r["falhas"] == [M_CLI]
    assert [t.split("/permissions/")[0] for t in g.permissoes_tiradas()] == ["COPIA1"]


def test_so_a_admin_manda():
    b, _, _ = montar(EQUIPE, "freela")
    _emissao(b)
    with pytest.raises(HTTPException) as e:
        ed.projeto_mandar_emissao(PROJ, E1, REQ, {"para": [M_CLI]})
    assert e.value.status_code == 403


def test_quem_sai_perde_o_arquivo_emitido_e_o_historico_fica():
    b, _, _ = montar(DONA, "dono")
    saiu = membro(b, M_CLI, "cliente", CLI, status="removido")
    membro(b, M_FORN, "fornecedor", FORN)
    _emissao(b)
    b.t["escritorio_emissao_destinos"] += [
        {"emissao_id": E1, "projeto_id": PROJ, "membro_id": M_CLI, "permission_id": "perm-cli"},
        {"emissao_id": E1, "projeto_id": PROJ, "membro_id": M_FORN, "permission_id": "perm-forn"}]
    g = _pastas()
    ed.sincronizar(PROJ)
    assert g.permissoes_tiradas() == ["COPIA1/permissions/perm-cli"]          # controle: o fornecedor ativo fica
    dest = {d["membro_id"]: d["permission_id"] for d in b.t["escritorio_emissao_destinos"]}
    assert dest == {M_CLI: None, M_FORN: "perm-forn"} and saiu["status"] == "removido"


def test_a_faxina_pega_arquivo_emitido_que_ficou_com_quem_saiu(monkeypatch):
    b, _, _ = montar(DONA, "dono")
    membro(b, M_CLI, "cliente", CLI, status="removido")
    b.t["escritorio_emissao_destinos"].append({"emissao_id": E1, "projeto_id": PROJ, "membro_id": M_CLI,
                                               "permission_id": "perm-cli"})
    chamou = []
    monkeypatch.setattr(ed, "sincronizar", lambda pid: chamou.append(pid) or {"tirados": 1, "falhas": []})
    assert ed.faxina()["projetos"] == 1 and chamou == [PROJ]


def test_limpar_conta_tira_o_cliente_do_projeto(monkeypatch):
    b, _, _ = montar(DONA, "dono")
    linha = membro(b, M_CLI, "cliente", CLI)
    monkeypatch.setattr(ed, "sincronizar", lambda pid: {"tirados": 1, "falhas": []})
    feito = ed.limpar_conta(CLI["id"])
    assert linha["status"] == "removido" and feito["saiu_de"] == 1


# ── a resposta do cliente ──
def test_resposta_do_cliente_grava_com_o_login_dele_e_avisa_a_admin_uma_vez():
    b, enviados, _ = montar(CLI, "cliente")
    membro(b, M_CLI, "cliente", CLI, nome="Cliente Exemplo")
    _emissao(b)
    r = esc.responder_emissao(E1, REQ, {"tipo": "revisao", "nota": "a porta <script>x</script> da despensa"})
    assert r["ok"] and r["aviso_enviado"] is True
    ev = b.t["escritorio_emissao_eventos"][0]
    assert (ev["tipo"], ev["registrado_por"], ev["emissao_id"]) == ("revisao", CLI["id"], E1)
    aviso = enviados[0]
    assert aviso["para"] == DONA["email"] and aviso["kind"] == "escritorio_resposta_cliente"
    assert aviso["assunto"].startswith("Cliente pediu revisão") and len(aviso["assunto"]) <= esc.TETO_ASSUNTO
    assert "<script>" not in aviso["html"] and "&lt;script&gt;" in aviso["html"]
    # 2º clique em seguida: a resposta grava, mas a admin não leva outro e-mail
    r2 = esc.responder_emissao(E1, REQ, {"tipo": "aprovado"})
    assert r2["ok"] and r2["aviso_enviado"] is False and len(enviados) == 1


def test_quem_nao_recebeu_a_emissao_leva_403_do_banco():
    b, enviados, _ = montar(EQUIPE, "freela")
    _emissao(b)
    b.rls_recusa = True
    with pytest.raises(HTTPException) as e:
        esc.responder_emissao(E1, REQ, {"tipo": "aprovado"})
    assert e.value.status_code == 403 and not enviados


@pytest.mark.parametrize("corpo", [{"tipo": "enviado"}, {"tipo": "revisao"}, {"tipo": "revisao", "nota": "   "}])
def test_resposta_invalida_ou_revisao_sem_dizer_o_que_mudar_e_recusada(corpo):
    b, _, _ = montar(CLI, "cliente")
    _emissao(b)
    with pytest.raises(HTTPException) as e:
        esc.responder_emissao(E1, REQ, corpo)
    assert e.value.status_code == 400 and b.t["escritorio_emissao_eventos"] == []


# ── e-mails automáticos ──
def test_cliente_e_fornecedor_contam_como_convidados_e_so_a_equipe_leva_o_sua_area(monkeypatch):
    import main
    linhas = [{"user_id": "u-dono", "papel": "dono", "status": "ativo", "aceito_em": "2026-09-01", "nome": "Admin", "projeto_id": PROJ},
              {"user_id": "u-cli", "papel": "cliente", "status": "ativo", "aceito_em": "2026-09-02", "nome": None, "projeto_id": PROJ},
              {"user_id": "u-eq", "papel": "freela", "status": "ativo", "aceito_em": "2026-09-03", "nome": None, "projeto_id": PROJ}]
    monkeypatch.setattr(main, "_supa_rest_tudo", lambda path, **k: (
        (200, linhas) if path == "escritorio_membros" else (200, [{"id": PROJ, "nome": "Casa Exemplo"}])))
    conv = main._convidados_do_escritorio()
    assert set(conv) == {"u-cli", "u-eq"}
    assert conv["u-cli"]["papeis"] == {"cliente"} and conv["u-eq"]["papeis"] == {"freela"}
