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
import io
import json
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
            "escritorio_convites_enviados", "profiles", "escritorio_fotos")}
        self.falhar = set()          # (método, tabela) que devolvem 500
        self.rls_recusa = False      # a gravação COMO USUÁRIO bate na RLS
        self.papel = None            # quem está logado (pra leitura COMO USUÁRIO seguir a RLS)
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
            fora = [dict(x) for x in linhas if self.casa(x, params)]
            self.t[path] = [x for x in linhas if not self.casa(x, params)]
            return (200, fora) if "return=representation" in (prefer or "") else (204, None)
        raise AssertionError(method)

    def como_usuario(self, method, path, body, params=None):
        """O que o banco faria COM O LOGIN da pessoa (a RLS da seção 26, no que estes testes usam)."""
        if (method, path) == ("GET", "escritorio_fotos"):
            if self.papel not in ("dono", "freela", "fornecedor", "cliente"):
                return 200, []
            linhas = [x for x in self.t[path] if self.casa(x, params)]
            return 200, [dict(x) for x in linhas if self.papel != "cliente" or x.get("pro_cliente") is True]
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
        self.tirar = {}                  # id do arquivo/pasta → status que o Google devolve ao TIRAR um acesso
        ed._HTTP = self

    def __call__(self, method, url, token=None, form=None, corpo=None, timeout=20):
        self.chamadas.append((method, url, corpo))
        if "oauth2.googleapis.com/token" in url:
            return 200, {"access_token": "acesso", "expires_in": 3600}
        if method == "DELETE":
            return self.tirar.get(url.split("/files/", 1)[1].split("/", 1)[0], 204), {}
        if method == "PATCH" and "/files/" in url:
            return 200, {}                                           # ex.: foto pra lixeira
        if method == "POST" and "/files?" in url:
            return 200, {"id": "PASTA_%s" % str((corpo or {}).get("name", "NOVA")).upper()}   # cria a subpasta
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
    antes_http, antes_bruto = ed._HTTP, ed._BRUTO
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "segredo-de-teste-do-servidor")
    monkeypatch.setenv("GOOGLE_DRIVE_CLIENT_SECRET", "segredo-do-cliente")
    ed._CACHE_ACESSO.clear()
    yield
    for n, v in antes.items():
        setattr(esc, n, v)
    ed._HTTP, ed._BRUTO = antes_http, antes_bruto
    ed._CACHE_ACESSO.clear()


def montar(usuario, papel):
    b, enviados, depois = BancoFiel(), [], []
    b.papel = papel
    esc._SERVICO = b
    esc._USUARIO = lambda r: usuario
    esc._COMO_USUARIO = lambda req, m, path, body=None, params=None, **k: (
        (200, papel) if path == "rpc/escritorio_papel" else b.como_usuario(m, path, body, params))
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


# ── fotos (26/09: "pasta Fotos no Drive"; sobem equipe e fornecedor; o cliente vê as "pro cliente") ──
JPG = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"foto-de-teste"
PNG = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]) + b"png-de-teste"
F1 = "f0000000-0000-4000-8000-000000000001"
F2 = "f0000000-0000-4000-8000-000000000002"


class BrutoFiel:
    """Upload e download de imagem (o que não é JSON)."""
    def __init__(self):
        self.chamadas, self.falha_upload = [], False
        ed._BRUTO = self

    def __call__(self, method, url, token=None, corpo=None, tipo=None, timeout=60):
        self.chamadas.append({"m": method, "url": url, "corpo": corpo, "tipo": tipo})
        if "/upload/drive/v3/files" in url:
            if self.falha_upload:
                return 500, b"", ""
            n = len([c for c in self.chamadas if "/upload/" in c["url"]])
            return 200, json.dumps({"id": "FOTO_DRIVE_%02d" % n, "name": "x"}).encode("utf-8"), "application/json"
        if "googleusercontent" in url:
            return 200, b"miniatura-" + url.rsplit("=", 1)[1].encode("ascii"), "image/jpeg"
        if "alt=media" in url:
            return 200, JPG, "image/jpeg"
        return 404, b"", ""

    def uploads(self):
        return [c for c in self.chamadas if "/upload/" in c["url"]]


def _arq(dados, nome="foto.jpg"):
    return types.SimpleNamespace(file=io.BytesIO(dados), filename=nome)


def test_fornecedor_sobe_fotos_na_pasta_fotos_e_elas_nao_vao_sozinhas_pro_cliente():
    b, _, _ = montar(FORN, "fornecedor")
    membro(b, M_FORN, "fornecedor", FORN)
    g, br = _pastas(), BrutoFiel()
    r = ed.projeto_fotos_subir(PROJ, REQ, fotos=[_arq(JPG), _arq(PNG, "b.png")], legenda="Vão da cozinha",
                               etapa="Obra", pro_cliente="1")
    assert len(r["fotos"]) == 2 and r["falhas"] == 0
    assert all(f["pro_cliente"] is False and f["enviada_por"] == FORN["id"] and f["etapa"] == "Obra"
               for f in b.t["escritorio_fotos"])
    criou = [c for m, u, c in g.chamadas if m == "POST" and "/files?" in u]
    assert [c["name"] for c in criou] == ["Fotos"] and criou[0]["parents"] == ["PASTA_PROJ"]
    up = br.uploads()
    assert len(up) == 2 and all(b"PASTA_FOTOS" in c["corpo"] for c in up)
    assert b"da cozinha 01.jpg" in up[0]["corpo"] and b"da cozinha 02.png" in up[1]["corpo"]
    assert up[0]["tipo"].startswith("multipart/related; boundary=") and JPG in up[0]["corpo"]


def test_controle_a_equipe_marca_pro_cliente_na_subida():
    b, _, _ = montar(EQUIPE, "freela")
    membro(b, M_EQ, "freela", EQUIPE)
    _pastas()
    BrutoFiel()
    ed.projeto_fotos_subir(PROJ, REQ, fotos=[_arq(JPG)], legenda="Fachada", pro_cliente="1")
    assert b.t["escritorio_fotos"][0]["pro_cliente"] is True


def test_cliente_nao_sobe_foto():
    montar(CLI, "cliente")
    br = BrutoFiel()
    with pytest.raises(HTTPException) as e:
        ed.projeto_fotos_subir(PROJ, REQ, fotos=[_arq(JPG)])
    assert e.value.status_code == 403 and not br.chamadas


def test_o_que_nao_e_imagem_e_recusado_pelos_bytes_mesmo_com_nome_de_jpg():
    b, _, _ = montar(EQUIPE, "freela")
    _pastas()
    br = BrutoFiel()
    with pytest.raises(HTTPException) as e:
        ed.projeto_fotos_subir(PROJ, REQ, fotos=[_arq(b"%PDF-1.7 planta", "planta.jpg")])
    assert e.value.status_code == 415 and not br.chamadas and not b.t["escritorio_fotos"]


def test_foto_acima_do_teto_e_recusada_antes_de_subir(monkeypatch):
    montar(EQUIPE, "freela")
    _pastas()
    br = BrutoFiel()
    monkeypatch.setattr(ed, "_FOTO_TETO", 10)
    with pytest.raises(HTTPException) as e:
        ed.projeto_fotos_subir(PROJ, REQ, fotos=[_arq(JPG)])
    assert e.value.status_code == 413 and not br.chamadas


def test_sem_o_registro_a_foto_nao_fica_orfa_no_drive():
    b, _, _ = montar(EQUIPE, "freela")
    g = _pastas()
    BrutoFiel()
    b.falhar.add(("POST", "escritorio_fotos"))
    with pytest.raises(HTTPException) as e:
        ed.projeto_fotos_subir(PROJ, REQ, fotos=[_arq(JPG)])
    assert e.value.status_code == 502
    assert any(m == "DELETE" and "/files/FOTO_DRIVE_01" in u for m, u, _ in g.chamadas)


def _fotos(b, g):
    b.t["escritorio_fotos"] += [
        {"id": F1, "projeto_id": PROJ, "drive_file_id": "FOTO_DRIVE_01", "pro_cliente": True, "enviada_por": DONA["id"]},
        {"id": F2, "projeto_id": PROJ, "drive_file_id": "FOTO_DRIVE_02", "pro_cliente": False, "enviada_por": FORN["id"]}]
    for fid in ("FOTO_DRIVE_01", "FOTO_DRIVE_02"):
        g.pastas[fid] = {"thumbnailLink": "https://lh3.googleusercontent.com/" + fid + "=s220"}


def test_o_cliente_so_ve_a_imagem_das_fotos_pro_cliente_e_no_tamanho_pedido():
    b, _, _ = montar(CLI, "cliente")
    g = _pastas()
    _fotos(b, g)
    BrutoFiel()
    r = ed.projeto_foto_imagem(PROJ, F1, REQ, tam="grande")
    assert r.body == b"miniatura-s1600" and r.media_type == "image/jpeg"
    assert "private" in r.headers["cache-control"]
    with pytest.raises(HTTPException) as e:
        ed.projeto_foto_imagem(PROJ, F2, REQ)
    assert e.value.status_code == 404


def test_miniatura_que_nao_e_do_google_nao_e_seguida():
    b, _, _ = montar(EQUIPE, "freela")
    g = _pastas()
    _fotos(b, g)
    g.pastas["FOTO_DRIVE_01"] = {"thumbnailLink": "https://outro.exemplo.com/x=s220"}
    br = BrutoFiel()
    r = ed.projeto_foto_imagem(PROJ, F1, REQ)
    assert r.body == JPG and not [c for c in br.chamadas if "exemplo.com" in c["url"]]


def test_apagar_foto_so_quem_subiu_ou_a_admin_e_vai_pra_lixeira():
    b, _, _ = montar(FORN, "fornecedor")
    g = _pastas()
    _fotos(b, g)
    with pytest.raises(HTTPException) as e:
        ed.projeto_foto_apagar(PROJ, F1, REQ)                    # a da admin
    assert e.value.status_code == 403
    assert ed.projeto_foto_apagar(PROJ, F2, REQ)["ok"]            # a dele
    lixo = [(u, c) for m, u, c in g.chamadas if m == "PATCH"]
    assert len(lixo) == 1 and "/files/FOTO_DRIVE_02" in lixo[0][0] and lixo[0][1] == {"trashed": True}
    assert [f["id"] for f in b.t["escritorio_fotos"]] == [F1]
    b2, _, _ = montar(DONA, "dono")
    g2 = _pastas()
    _fotos(b2, g2)
    assert ed.projeto_foto_apagar(PROJ, F2, REQ)["ok"]            # a admin apaga a de qualquer um


# ── cronograma só leitura pro cliente (27/09 — Pedro: "faz o cronograma só leitura pro cliente") ──
CRON = {"fases": [{"label": "Fundação", "inicio": "2026-10-01", "fim": "2026-10-20", "dur_dias": 19, "pct_executado": 40,
                   "cor": "#EA580C", "valor_previsto": 12345.0, "esforco_hh": 80, "obs": "margem interna"}],
        "resumo": {"data_inicio": "2026-10-01", "data_fim": "2027-03-01", "duracao_meses": 5, "valor_total": 98765.0},
        "curva_s": [{"mes": 1, "valor": 1}], "financeiro": {"total": 98765.0}}


def _crono(monkeypatch, usuario, papel, job="job-exemplo", salvo=(200, {"job_id": "job-exemplo"}), cron=CRON):
    import main
    b, _, _ = montar(usuario, papel)
    b.t["escritorio_projetos"][0]["job_id"] = job
    leu = []
    monkeypatch.setattr(main, "_get_user_from_request", lambda r: usuario)
    monkeypatch.setattr(main, "_supa_rest_service", b)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(main, "_fin_cronograma_salvo", lambda req, j: leu.append((req, j)) or salvo)

    def _monta(j, s):
        if isinstance(cron, Exception):
            raise cron
        return cron
    monkeypatch.setattr(main, "_cronograma_do_salvo", _monta)
    return main, leu


def test_o_cliente_ve_o_cronograma_so_com_datas_e_andamento_sem_dinheiro(monkeypatch):
    main, leu = _crono(monkeypatch, CLI, "cliente")
    r = main.escritorio_cronograma_pro_cliente(PROJ, REQ)
    assert r["status"] == "ok"
    assert r["cronograma"]["fases"] == [{"label": "Fundação", "inicio": "2026-10-01", "fim": "2026-10-20",
                                          "dur_dias": 19, "pct_executado": 40, "cor": "#EA580C"}]
    assert r["cronograma"]["resumo"] == {"data_inicio": "2026-10-01", "data_fim": "2027-03-01", "duracao_meses": 5}
    tudo = json.dumps(r, ensure_ascii=False)
    assert "12345" not in tudo and "98765" not in tudo and "margem" not in tudo and "curva" not in tudo
    # o cliente não tem acesso ao projeto medido: quem lê é o SERVIDOR (sem o login dele, a RLS esconderia o salvo)
    assert leu == [(None, "job-exemplo")]


def test_controle_a_equipe_tambem_ve_o_cronograma_do_cliente(monkeypatch):
    main, _ = _crono(monkeypatch, EQUIPE, "freela")
    assert main.escritorio_cronograma_pro_cliente(PROJ, REQ)["status"] == "ok"


@pytest.mark.parametrize("quem, papel", [(FORN, "fornecedor"), ({"id": "uid-x", "email": "x@exemplo.com"}, None)])
def test_fornecedor_e_quem_nao_e_do_projeto_nao_veem_o_cronograma(monkeypatch, quem, papel):
    main, leu = _crono(monkeypatch, quem, papel)
    with pytest.raises(HTTPException) as e:
        main.escritorio_cronograma_pro_cliente(PROJ, REQ)
    assert e.value.status_code == 403 and leu == []


def test_sem_projeto_medido_sem_cronograma_salvo_ou_sem_itens_o_cliente_ve_o_aviso(monkeypatch):
    main, leu = _crono(monkeypatch, CLI, "cliente", job=None)
    assert main.escritorio_cronograma_pro_cliente(PROJ, REQ) == {"status": "sem_cronograma"} and leu == []
    main, _ = _crono(monkeypatch, CLI, "cliente", salvo=(200, None))
    assert main.escritorio_cronograma_pro_cliente(PROJ, REQ) == {"status": "sem_cronograma"}
    main, _ = _crono(monkeypatch, CLI, "cliente", cron=HTTPException(404, "Projeto sem itens"))
    assert main.escritorio_cronograma_pro_cliente(PROJ, REQ) == {"status": "sem_cronograma"}


def test_leitura_que_falha_e_502_e_nao_vira_sem_cronograma(monkeypatch):
    main, _ = _crono(monkeypatch, CLI, "cliente", salvo=(500, None))
    with pytest.raises(HTTPException) as e:
        main.escritorio_cronograma_pro_cliente(PROJ, REQ)
    assert e.value.status_code == 502
    main, _ = _crono(monkeypatch, CLI, "cliente")
    main._supa_rest_service.falhar.add(("GET", "escritorio_projetos"))
    with pytest.raises(HTTPException) as e:
        main.escritorio_cronograma_pro_cliente(PROJ, REQ)
    assert e.value.status_code == 502


# ── e-mail do AI.arq quando a emissão chega pro cliente (27/09 — Pedro: "e-mail do AI.arq também") ──
def test_o_cliente_que_recebe_a_emissao_leva_o_email_do_aiarq_e_o_fornecedor_nao():
    b, enviados, _ = montar(DONA, "dono")
    esc._MOLDURA = lambda titulo, corpo, **k: "<h1>%s</h1>%s<a href='%s'>" % (titulo, corpo, k.get("cta_url"))
    membro(b, M_FORN, "fornecedor", FORN)
    membro(b, M_CLI, "cliente", CLI)
    _emissao(b)
    b.t["escritorio_emissoes"][0]["nota"] = "Cozinha <b>ampliada</b>"
    _pastas()
    r = ed.projeto_mandar_emissao(PROJ, E1, REQ, {"para": [M_CLI, M_FORN]})
    assert r["mandados"] == 2 and r["avisados"] == 1
    assert [e["para"] for e in enviados] == [CLI["email"]]
    e = enviados[0]
    assert e["kind"] == "escritorio_emissao_cliente" and e["assunto"] == "Pra você aprovar: Planta_R02.pdf"
    assert "Admin Exemplo" in e["html"] and "Casa Exemplo" in e["html"]
    assert "https://ai.arq.br/escritorio.html#/p/%s/emissoes" % PROJ in e["html"]
    assert "<b>ampliada</b>" not in e["html"] and "&lt;b&gt;ampliada" in e["html"]
    # mandar de novo pra quem já tem: nem acesso novo, nem e-mail novo
    assert ed.projeto_mandar_emissao(PROJ, E1, REQ, {"para": [M_CLI]})["avisados"] == 0 and len(enviados) == 1


def test_o_aviso_que_falha_nao_desfaz_o_envio():
    b, _, _ = montar(DONA, "dono")
    membro(b, M_CLI, "cliente", CLI)
    _emissao(b)
    g = _pastas()

    def _cai(*a, **k):
        raise RuntimeError("smtp fora")
    esc._ENVIAR = _cai
    r = ed.projeto_mandar_emissao(PROJ, E1, REQ, {"para": [M_CLI]})
    assert r["mandados"] == 1 and r["avisados"] == 0
    assert b.t["escritorio_emissao_destinos"][0]["permission_id"] and not g.permissoes_tiradas()


def test_assunto_do_aviso_ao_cliente_cabe_no_teto_e_nao_quebra_linha():
    nome = "Planta" + chr(13) + chr(10) + "Bcc: x@exemplo.com " + "longo " * 20 + ".pdf"
    assunto, _, _ = esc.email_da_emissao("Admin", nome, "Casa", None, "https://ai.arq.br/escritorio.html",
                                         moldura=lambda t, c, **k: c)
    assert len(assunto) <= esc.TETO_ASSUNTO and chr(10) not in assunto and chr(13) not in assunto


# ── apagar o projeto (27/09 — auditoria DRV-8: tirar no Drive ANTES de apagar o registro) ──
def _acessos_dados(b):
    b.t["escritorio_drive_permissoes"] += [
        {"id": "dp-1", "projeto_id": PROJ, "membro_id": M_EQ, "email": EQUIPE["email"], "pasta_id": "PASTA_PROJ",
         "permission_id": "perm-eq", "ja_existia": False},
        {"id": "dp-2", "projeto_id": PROJ, "membro_id": M_EQ, "email": "antigo@exemplo.com", "pasta_id": "PASTA_PROJ",
         "permission_id": "perm-antiga", "ja_existia": True},              # já tinha à mão: não fomos nós que demos
        {"id": "dp-3", "projeto_id": PROJ, "membro_id": M_FORN, "email": FORN["email"], "pasta_id": "PASTA_MARC",
         "permission_id": "perm-forn", "ja_existia": False},
        {"id": "dp-4", "projeto_id": OUTRO_PROJ, "membro_id": None, "email": FORN["email"], "pasta_id": "PASTA_MARC",
         "permission_id": "perm-forn", "ja_existia": False}]                 # segue noutro projeto com a MESMA pasta
    _emissao(b)
    b.t["escritorio_emissao_destinos"].append({"emissao_id": E1, "projeto_id": PROJ, "membro_id": M_CLI,
                                               "permission_id": "perm-cli"})


def test_apagar_o_projeto_tira_antes_os_acessos_que_demos_e_so_depois_apaga():
    b, _, _ = montar(DONA, "dono")
    _acessos_dados(b)
    g = _pastas()
    na_hora = []

    def espiao(method, path, *a, **k):
        if method == "DELETE" and path.lstrip("/") == "escritorio_projetos":
            na_hora.append(sorted(g.permissoes_tiradas()))
        return b(method, path, *a, **k)
    esc._SERVICO = espiao
    assert ed.projeto_apagar(PROJ, REQ) == {"ok": True, "apagado": True}
    tirados = ["COPIA1/permissions/perm-cli", "PASTA_PROJ/permissions/perm-eq"]
    assert sorted(g.permissoes_tiradas()) == tirados and na_hora == [tirados]
    assert [p["id"] for p in b.t["escritorio_projetos"]] == []


@pytest.mark.parametrize("onde", ["COPIA1", "PASTA_PROJ"])
def test_se_o_google_nao_tira_um_acesso_o_projeto_nao_e_apagado(onde):
    b, _, _ = montar(DONA, "dono")
    _acessos_dados(b)
    g = _pastas()
    g.tirar[onde] = 500
    with pytest.raises(HTTPException) as e:
        ed.projeto_apagar(PROJ, REQ)
    assert e.value.status_code == 502 and "NÃO foi apagado" in e.value.detail
    assert [p["id"] for p in b.t["escritorio_projetos"]] == [PROJ]


@pytest.mark.parametrize("enxerga", [True, False])
def test_404_so_vale_como_ja_saiu_se_a_conta_enxerga_a_pasta(enxerga):
    b, _, _ = montar(DONA, "dono")
    b.t["escritorio_drive_permissoes"].append({"id": "dp-1", "projeto_id": PROJ, "membro_id": M_EQ,
                                               "email": EQUIPE["email"], "pasta_id": "PASTA_PROJ",
                                               "permission_id": "perm-eq", "ja_existia": False})
    g = _pastas()
    g.tirar["PASTA_PROJ"] = 404
    if not enxerga:
        del g.pastas["PASTA_PROJ"]
        with pytest.raises(HTTPException) as e:
            ed.projeto_apagar(PROJ, REQ)
        assert e.value.status_code == 502 and b.t["escritorio_projetos"]
    else:
        assert ed.projeto_apagar(PROJ, REQ)["apagado"] is True and not b.t["escritorio_projetos"]


def test_sem_conexao_com_o_drive_e_acesso_a_tirar_pede_pra_reconectar_e_nao_apaga():
    b, _, _ = montar(DONA, "dono")
    _acessos_dados(b)
    b.t["escritorio_drive_conexoes"].clear()
    g = _pastas()
    with pytest.raises(HTTPException) as e:
        ed.projeto_apagar(PROJ, REQ)
    assert e.value.status_code == 409 and b.t["escritorio_projetos"] and not g.permissoes_tiradas()
    # a admin precisa saber POR QUE não apagou (o 409 genérico do Drive diria só "não está conectado")
    assert "Pra apagar" in e.value.detail


def test_controle_projeto_que_nunca_compartilhou_nada_apaga_mesmo_sem_o_drive():
    b, _, _ = montar(DONA, "dono")
    b.t["escritorio_drive_permissoes"].append({"id": "dp-2", "projeto_id": PROJ, "email": "antigo@exemplo.com",
                                               "pasta_id": "PASTA_PROJ", "permission_id": "p", "ja_existia": True})
    b.t["escritorio_drive_conexoes"].clear()
    assert ed.projeto_apagar(PROJ, REQ)["apagado"] is True and not b.t["escritorio_projetos"]


@pytest.mark.parametrize("tabela", ["escritorio_drive_permissoes", "escritorio_emissao_destinos"])
def test_banco_que_nao_responde_nao_apaga(tabela):
    b, _, _ = montar(DONA, "dono")
    b.falhar.add(("GET", tabela))
    with pytest.raises(HTTPException) as e:
        ed.projeto_apagar(PROJ, REQ)
    assert e.value.status_code == 502 and b.t["escritorio_projetos"]


@pytest.mark.parametrize("quem, papel", [(EQUIPE, "freela"), (CLI, "cliente"), (FORN, "fornecedor")])
def test_so_a_admin_apaga_o_projeto(quem, papel):
    b, _, _ = montar(quem, papel)
    g = _pastas()
    with pytest.raises(HTTPException) as e:
        ed.projeto_apagar(PROJ, REQ)
    assert e.value.status_code == 403 and b.t["escritorio_projetos"] and not g.chamadas
