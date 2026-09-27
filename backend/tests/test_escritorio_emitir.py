# -*- coding: utf-8 -*-
"""Emitir R00, R01… (26/09/2026) — a CÓPIA com a revisão no nome, na pasta "Emitidos".

Decisões do Pedro (23/09): "renomear com R00/R01 ao emitir"; é uma CÓPIA — o original segue sendo o arquivo
de trabalho; só a admin emite. O que estes guardas cobram:
  • a revisão é POR ARQUIVO e vem do BANCO (R00 na 1ª, R01 na 2ª…), reservada ANTES da cópia: dois cliques
    juntos não viram duas R03 e não sobra cópia órfã no Drive;
  • a cópia vai pra "Emitidos" (criada na 1ª vez, reaproveitada depois), com o nome certo, e fica travada;
  • o ORIGINAL não é tocado (nenhuma escrita no id dele);
  • só a admin; só arquivo DENTRO da pasta do projeto; pasta, cópia já emitida e id estranho são recusados;
  • a cópia falhou → a reserva sai do banco (nada emitido pela metade).
🧪 Controles: a 2ª emissão do MESMO arquivo é R01; outro arquivo começa em R00; trava que falha não derruba.
"""
import os
import sys
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
REQ = types.SimpleNamespace(headers={"Authorization": "Bearer x"}, state=types.SimpleNamespace())
RAIZ, SUB, FORA, EMIT = "PASTA_PROJ_0001", "SUBPASTA_0001", "OUTRA_PASTA_01", "EMITIDOS_0001"
ARQ, ARQ2 = "ARQUIVO_PLANTA_01", "ARQUIVO_CORTE_001"


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
    def __init__(self, papel="dono", conflito=False):
        self.papel, self.conflito = papel, conflito
        self.projeto = {"id": PROJ, "dono": DONA["id"], "nome": "Casa Exemplo", "pasta_id": RAIZ, "pasta_caminho": "Casa"}
        self.emissoes, self.escritas, self.avisos = [], [], []
        esc._SERVICO = self
        esc._USUARIO = lambda r: DONA
        esc._COMO_USUARIO = lambda req, m, path, body=None, **k: (200, self.papel)
        esc._REGISTRAR = lambda stage, msg, **k: self.avisos.append((stage, msg))

    def __call__(self, method, path, body=None, params=None, prefer=None, **_k):
        params = params or {}
        if method != "GET":
            self.escritas.append({"m": method, "path": path, "body": body, "params": params})
        if path == "escritorio_projetos":
            return 200, [self.projeto]
        if path == "escritorio_drive_conexoes":
            return 200, [{"user_id": DONA["id"], "google_email": "dona@exemplo.com",
                          "token_cifrado": ed.cifrar("refresh-da-dona")}]
        if path == "escritorio_emissoes":
            if method == "GET":
                arq = params["arquivo_id"].split(".", 1)[1]
                linhas = sorted((e for e in self.emissoes if e["arquivo_id"] == arq), key=lambda e: -e["revisao"])
                return 200, [{"revisao": e["revisao"]} for e in linhas[:1]]
            if method == "POST":
                if self.conflito:
                    return 409, {"code": "23505"}
                linha = {"id": f"em-{len(self.emissoes) + 1}", **body}
                self.emissoes.append(linha)
                return 201, [linha]
            i = params["id"].split(".", 1)[1]
            if method == "PATCH":
                for e in self.emissoes:
                    if e["id"] == i:
                        e.update(body)
                return 200, None
            if method == "DELETE":
                self.emissoes = [e for e in self.emissoes if e["id"] != i]
                return 204, None
        raise AssertionError("tabela inesperada: " + path)


class Google:
    """Drive falso: arquivos por id, pais, a pasta Emitidos (existe ou não) e o que cada chamada fez."""
    def __init__(self, emitidos_existe=False, copia_falha=False, trava_falha=False):
        self.chamadas = []
        self.arquivos = {
            ARQ: {"id": ARQ, "name": "Planta baixa.dwg", "mimeType": "image/vnd.dwg", "parents": [SUB]},
            ARQ2: {"id": ARQ2, "name": "Corte AA_R04.pdf", "mimeType": "application/pdf", "parents": [RAIZ]},
            "ARQUIVO_FORA_0001": {"id": "ARQUIVO_FORA_0001", "name": "x.pdf", "mimeType": "application/pdf", "parents": [FORA]},
            "PASTA_QUALQUER_01": {"id": "PASTA_QUALQUER_01", "name": "Fotos", "mimeType": ed.PASTA, "parents": [RAIZ]},
            "COPIA_EMITIDA_01": {"id": "COPIA_EMITIDA_01", "name": "Planta_R00.dwg", "mimeType": "image/vnd.dwg", "parents": [EMIT]},
            "DOC_DO_GOOGLE_01": {"id": "DOC_DO_GOOGLE_01", "name": "Memorial", "mimeType": "application/vnd.google-apps.document", "parents": [RAIZ]},
            "ATALHO_000000001": {"id": "ATALHO_000000001", "name": "Planta (atalho)", "mimeType": "application/vnd.google-apps.shortcut", "parents": [RAIZ]},
            "COPIA_NA_SUB_001": {"id": "COPIA_NA_SUB_001", "name": "Planta_R01.dwg", "mimeType": "image/vnd.dwg", "parents": ["SUB_DE_EMITIDOS"]},
        }
        self.pais = {SUB: RAIZ, EMIT: RAIZ, FORA: "raiz-do-drive", "SUB_DE_EMITIDOS": EMIT}
        self.emitidos_existe, self.copia_falha, self.trava_falha = emitidos_existe, copia_falha, trava_falha
        self.copia_sem_resposta, self.copia_feita_mesmo_assim, self.recusa = False, False, None
        ed._HTTP = self

    def __call__(self, method, url, token=None, form=None, corpo=None, timeout=20):
        self.chamadas.append({"m": method, "url": url, "corpo": corpo})
        if "oauth2.googleapis.com/token" in url:
            return 200, {"access_token": "acesso", "expires_in": 3600}
        u = urllib.parse.urlparse(url)
        q = dict(urllib.parse.parse_qsl(u.query))
        caminho = u.path.split("/drive/v3/", 1)[1]
        if caminho == "files" and method == "GET" and "name='Emitidos'" in q["q"]:   # procura a pasta Emitidos
            assert f"'{RAIZ}' in parents" in q["q"]
            return 200, {"files": [{"id": EMIT, "ownedByMe": True}] if self.emitidos_existe else []}   # a da dona (lote 3, DRV-3)
        if caminho == "files" and method == "GET":        # procura a cópia pelo nome (a cópia ficou sem resposta)
            assert f"'{EMIT}' in parents" in q["q"]
            achou = [{"id": "COPIA_ACHADA_001", "name": "Planta baixa_R00.dwg", "webViewLink": "https://drive.google.com/file/d/COPIA_ACHADA_001/view"}]
            return 200, {"files": achou if self.copia_feita_mesmo_assim and "name='Planta baixa_R00.dwg'" in q["q"] else []}
        if caminho == "files" and method == "POST":       # cria a pasta Emitidos
            self.emitidos_existe = True
            return 200, {"id": EMIT}
        if caminho.endswith("/copy"):
            if self.copia_sem_resposta:
                return 0, None
            if self.recusa:
                return 403, {"error": {"errors": [{"reason": self.recusa}]}}
            if self.copia_falha:
                return 500, None
            return 200, {"id": "COPIA_NOVA_0001", "name": corpo["name"], "webViewLink": "https://drive.google.com/file/d/COPIA_NOVA_0001/view"}
        fid = caminho.split("/", 1)[1]
        if method == "PATCH":   # o Drive devolve o que gravou (fields=contentRestrictions)
            return (500, None) if self.trava_falha else (200, {"contentRestrictions": (corpo or {}).get("contentRestrictions")})
        if q.get("fields") == "parents":
            return 200, ({"parents": [self.pais[fid]]} if fid in self.pais else {})
        if fid in self.arquivos:
            return 200, self.arquivos[fid]
        return 404, {}

    def feitas(self, metodo, trecho):
        return [c for c in self.chamadas if c["m"] == metodo and trecho in c["url"]]


def _emitir(arquivo=ARQ, nota=""):
    return ed.projeto_emitir(PROJ, REQ, {"arquivo_id": arquivo, "nota": nota})


# ── o nome ──
@pytest.mark.parametrize("nome,rev,nativo,esperado", [
    ("Planta baixa.dwg", 0, False, "Planta baixa_R00.dwg"),
    ("Planta_R02.dwg", 3, False, "Planta_R03.dwg"),            # a revisão velha do nome sai
    ("Planta - R05.dwg", 6, False, "Planta_R06.dwg"),
    ("Casa SR01.pdf", 0, False, "Casa SR01_R00.pdf"),          # "SR01" não é revisão (sem separador)
    ("v1.0 final.pdf", 0, False, "v1.0 final_R00.pdf"),
    ("Memorial", 1, True, "Memorial_R01"),                     # documento do Google: sem extensão
    ("Memorial.v2", 1, True, "Memorial.v2_R01"),
    ("", 0, False, "arquivo_R00")])
def test_o_nome_da_copia(nome, rev, nativo, esperado):
    assert ed.nome_da_emissao(nome, rev, nativo) == esperado


# ── a emissão ──
def test_primeira_emissao_e_R00_copia_em_Emitidos_e_trava():
    b, g = Banco(), Google()
    r = _emitir(nota="Pra aprovação do cliente")
    assert r["ok"] and r["revisao"] == 0 and r["nome"] == "Planta baixa_R00.dwg" and r["travada"] is True
    assert len(g.feitas("POST", "/drive/v3/files?")) == 1, "a pasta Emitidos nasce na 1ª emissão"
    copia = g.feitas("POST", f"/files/{ARQ}/copy")
    assert len(copia) == 1 and copia[0]["corpo"] == {"name": "Planta baixa_R00.dwg", "parents": [EMIT]}
    trava = g.feitas("PATCH", "/files/COPIA_NOVA_0001")
    assert trava and trava[0]["corpo"]["contentRestrictions"][0]["readOnly"] is True
    # 🔒 26/09 (auditoria SEG-1): sem ownerRestricted qualquer editora da pasta (a equipe) tirava a trava
    assert trava[0]["corpo"]["contentRestrictions"][0]["ownerRestricted"] is True
    assert not [c for c in g.chamadas if c["m"] != "GET" and f"/files/{ARQ}" in c["url"] and "/copy" not in c["url"]], \
        "o ORIGINAL não é tocado"
    e = b.emissoes[0]
    assert (e["revisao"], e["arquivo_id"], e["copia_id"], e["emitido_por"], e["nota"]) == \
        (0, ARQ, "COPIA_NOVA_0001", DONA["id"], "Pra aprovação do cliente")


def test_segunda_emissao_do_mesmo_arquivo_e_R01_e_reaproveita_Emitidos():
    b, g = Banco(), Google()
    _emitir()
    g.chamadas.clear()
    r = _emitir()
    assert r["revisao"] == 1 and r["nome"] == "Planta baixa_R01.dwg"
    assert not g.feitas("POST", "/drive/v3/files?"), "Emitidos já existe: não cria outra"
    assert [e["revisao"] for e in b.emissoes] == [0, 1]


def test_controle_outro_arquivo_comeca_em_R00_e_troca_a_revisao_do_nome():
    b = Banco()
    Google(emitidos_existe=True)
    b.emissoes.append({"id": "em-velha", "arquivo_id": ARQ, "revisao": 7})
    r = _emitir(ARQ2)
    assert r["revisao"] == 0 and r["nome"] == "Corte AA_R00.pdf"


def test_documento_do_google_sai_sem_extensao():
    Banco(), Google(emitidos_existe=True)
    assert _emitir("DOC_DO_GOOGLE_01")["nome"] == "Memorial_R00"


def test_so_a_admin_emite():
    b, g = Banco(papel="freela"), Google()
    with pytest.raises(HTTPException) as e:
        _emitir()
    assert e.value.status_code == 403 and not b.escritas and not g.chamadas


@pytest.mark.parametrize("arquivo,codigo", [
    ("ARQUIVO_FORA_0001", 403),        # fora da pasta do projeto
    ("PASTA_QUALQUER_01", 400),        # pasta
    ("COPIA_EMITIDA_01", 400),         # já é uma cópia emitida
    ("COPIA_NA_SUB_001", 400),         # 26/09 (LOG-C3): cópia movida pra subpasta de Emitidos também é cópia
    ("ATALHO_000000001", 400),         # 26/09 (DRV-2): atalho copiaria só o atalho
    ("NAO_EXISTE_00001", 404),
    ("x'/../", 400), ("", 400)])       # id estranho nem chega ao Google
def test_o_que_nao_se_emite(arquivo, codigo):
    b, g = Banco(), Google(emitidos_existe=True)
    with pytest.raises(HTTPException) as e:
        _emitir(arquivo)
    assert e.value.status_code == codigo
    assert not b.escritas and not g.feitas("POST", "/copy")


def test_dois_cliques_juntos_o_segundo_nao_copia():
    Banco(conflito=True)
    g = Google(emitidos_existe=True)
    with pytest.raises(HTTPException) as e:
        _emitir()
    assert e.value.status_code == 409 and not g.feitas("POST", "/copy"), "a reserva barrou ANTES da cópia"


def test_copia_que_falha_desfaz_a_reserva():
    b = Banco()
    Google(emitidos_existe=True, copia_falha=True)
    with pytest.raises(HTTPException) as e:
        _emitir()
    assert e.value.status_code == 502 and b.emissoes == [], "nada emitido pela metade"
    assert [x["m"] for x in b.escritas if x["path"] == "escritorio_emissoes"] == ["POST", "DELETE"]


def test_copia_sem_resposta_que_saiu_mesmo_assim_e_adotada_e_travada():
    # 🩸 26/09 (LOG-C2/DRV-3): tempo esgotado não é "nada foi emitido" — procura pelo nome antes de desfazer
    b, g = Banco(), Google(emitidos_existe=True)
    g.copia_sem_resposta, g.copia_feita_mesmo_assim = True, True
    r = _emitir()
    assert r["ok"] and b.emissoes[0]["copia_id"] == "COPIA_ACHADA_001" and r["travada"] is True
    assert g.feitas("PATCH", "/files/COPIA_ACHADA_001")


def test_copia_sem_resposta_que_nao_saiu_desfaz_a_reserva():
    b, g = Banco(), Google(emitidos_existe=True)
    g.copia_sem_resposta = True                            # controle: não achou pelo nome → nada emitido
    with pytest.raises(HTTPException) as e:
        _emitir()
    assert e.value.status_code == 502 and b.emissoes == []


@pytest.mark.parametrize("motivo,trecho", [("storageQuotaExceeded", "cheio"), ("cannotCopyFile", "não deixa copiar")])
def test_recusa_definitiva_do_google_nao_manda_tentar_de_novo(motivo, trecho):
    # 26/09 (LOG-C7): Drive cheio / cópia proibida nunca vai dar certo tentando de novo
    b, g = Banco(), Google(emitidos_existe=True)
    g.recusa = motivo
    with pytest.raises(HTTPException) as e:
        _emitir()
    assert e.value.status_code == 409 and trecho in e.value.detail and "tente de novo" not in e.value.detail
    assert b.emissoes == []


def test_trava_que_falha_nao_derruba_a_emissao():
    b = Banco()
    Google(emitidos_existe=True, trava_falha=True)
    r = _emitir()
    assert r["ok"] and r["travada"] is False and b.emissoes[0]["copia_id"] == "COPIA_NOVA_0001"


def test_sem_pasta_ligada_nao_emite():
    b, g = Banco(), Google()
    b.projeto["pasta_id"] = None
    with pytest.raises(HTTPException) as e:
        _emitir()
    assert e.value.status_code == 409 and not g.chamadas


def test_a_rota_esta_no_app_e_a_tela_chama():
    import main
    assert "/api/escritorio/projetos/{projeto_id}/emitir" in {r.path for r in main.app.routes}
    h = open(os.path.join(os.path.dirname(os.path.dirname(_AQUI)), "escritorio.html"), encoding="utf-8").read()
    assert "apiEsc(`projetos/${PROJ.id}/emitir`, 'POST'" in h


def test_na_tela_so_a_admin_emite_e_registra_e_o_botao_nao_abre_o_arquivo():
    h = open(os.path.join(os.path.dirname(os.path.dirname(_AQUI)), "escritorio.html"), encoding="utf-8").read()
    assert "const podeEmitir = souAdmin() && " in h
    assert '${souAdmin() ? `<button type="button" class="btn btn-s" onclick="registrarRetorno(' in h
    assert "if (!li || ev.target.closest('a,button')) return;" in h, "clicar em Emitir não pode abrir o arquivo no Drive"
    # o nome do arquivo é texto de gente: vai em data-*, nunca dentro de onclick
    assert 'class="btn btn-s arq-emitir" data-id="${esc(f.id)}" data-nome="${esc(f.nome)}"' in h
    assert "onclick=\"emitirArquivo(" not in h
