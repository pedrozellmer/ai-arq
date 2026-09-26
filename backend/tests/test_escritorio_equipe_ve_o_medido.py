# -*- coding: utf-8 -*-
"""A equipe do Escritório VÊ o projeto medido ligado (Parte 2, 24/09/2026).

Decisões do Pedro (24/09): a equipe convidada pra um projeto do Escritório ligado a um projeto medido
vê o quantitativo, as pranchas, o cronograma e o memorial — SÓ PRA VER. Baixar arquivo só com
autorização da admin, POR PESSOA (`escritorio_membros.pode_baixar`).

O que estes guardas provam, com a checagem de verdade (`_require_project_viewer`) e o banco falso:
  • dono e admin passam como sempre (é `_require_project_owner` por dentro), sem marca de "só leitura";
  • membro ATIVO do projeto ligado passa pra VER e ganha `so_leitura`; pra BAIXAR, só com `pode_baixar`;
  • quem não é da equipe, quem é de OUTRO projeto, e projeto sem ligação: 403 (a consulta filtra
    status=ativo — removido não volta);
  • projeto sem dono (beta antigo) continua só do admin, mesmo pra quem "é da equipe";
  • 🪤 banco fora é 503, nunca "não é da equipe";
  • a lista EXATA das rotas que aceitam "pode ver"/"pode baixar": se alguém puser a checagem nova numa
    rota que escreve, ou tirar de uma de leitura, reprova.
🧪 Controle positivo: o dono do projeto passa sem nenhuma consulta ao Escritório.
"""
import os
import re
import sys
import types

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import main  # noqa: E402
from fastapi import HTTPException  # noqa: E402

DONO = {"id": "uid-dono", "email": "dona@exemplo.com"}
EQUIPE = {"id": "uid-equipe", "email": "equipe@exemplo.com"}
OUTRO = {"id": "uid-outro", "email": "outro@exemplo.com"}


def _req():
    return types.SimpleNamespace(headers={"Authorization": "Bearer x"}, state=types.SimpleNamespace())


@pytest.fixture
def banco(monkeypatch):
    """Projeto medido J1 da DONO, ligado ao projeto do Escritório E1, com EQUIPE ativa (pode_baixar configurável)."""
    estado = {"usuario": None, "dono": "uid-dono", "ligado": True, "membros": {"uid-equipe": False},
              "falha": False, "consultas": []}

    def servico(method, path, body=None, params=None, **_k):
        estado["consultas"].append((path, dict(params or {})))
        if estado["falha"]:
            return 500, None
        params = params or {}
        if path == "/escritorio_projetos":
            assert params["job_id"] == "eq.J1"
            return 200, ([{"id": "E1"}] if estado["ligado"] else [])
        if path == "/escritorio_membros":
            assert params["projeto_id"] == "eq.E1" and params["status"] == "eq.ativo"
            uid = params["user_id"].split(".", 1)[1]
            return 200, ([{"id": "m-" + uid, "pode_baixar": estado["membros"][uid]}] if uid in estado["membros"] else [])
        raise AssertionError("tabela inesperada: " + path)

    monkeypatch.setattr(main, "_supa_rest_service", servico)
    monkeypatch.setattr(main, "_get_project_owner", lambda job_id: estado["dono"])
    monkeypatch.setattr(main, "_get_user_from_request", lambda request: estado["usuario"])
    return estado


def test_controle_o_dono_passa_sem_consultar_o_escritorio(banco):
    banco["usuario"] = DONO
    r = _req()
    assert main._require_project_viewer(r, "J1", baixar=True) == "uid-dono"
    assert not main._so_leitura(r) and banco["consultas"] == []


def test_admin_passa_como_sempre(banco):
    banco["usuario"] = {"id": "uid-admin", "email": main.ADMIN_EMAIL}
    r = _req()
    assert main._require_project_viewer(r, "J1", baixar=True) == "uid-dono" and not main._so_leitura(r)


def test_equipe_ve_e_fica_marcada_so_leitura(banco):
    banco["usuario"] = EQUIPE
    r = _req()
    assert main._require_project_viewer(r, "J1") == "uid-dono"
    assert main._so_leitura(r) and r.state.escritorio_id == "E1"
    assert main._req_de_leitura(r) is None           # lê com a chave do servidor (a RLS só conhece o dono)


def test_equipe_so_baixa_com_a_autorizacao_da_admin(banco):
    banco["usuario"] = EQUIPE
    with pytest.raises(HTTPException) as e:
        main._require_project_viewer(_req(), "J1", baixar=True)
    assert e.value.status_code == 403 and "liberou o download" in e.value.detail
    banco["membros"]["uid-equipe"] = True              # a admin ligou o "pode baixar"
    assert main._require_project_viewer(_req(), "J1", baixar=True) == "uid-dono"


@pytest.mark.parametrize("caso", ["nao_e_da_equipe", "projeto_sem_ligacao", "projeto_sem_dono"])
def test_quem_nao_e_da_equipe_continua_barrado(banco, caso):
    banco["usuario"] = OUTRO if caso == "nao_e_da_equipe" else EQUIPE
    if caso == "projeto_sem_ligacao":
        banco["ligado"] = False
    r = _req()
    if caso == "projeto_sem_dono":
        banco["dono"] = "anonymous"
        # 🪤 hoje o `_require_project_owner` recusa projeto sem dono ANTES de guardar quem é a pessoa —
        # sem isto o teste passava por esse acaso e não pela trava do "sem dono" (a sabotagem mostrou)
        r.state.usuario_validado = EQUIPE
    with pytest.raises(HTTPException) as e:
        main._require_project_viewer(r, "J1")
    assert e.value.status_code == 403


def test_sem_login_e_401_e_banco_fora_e_503(banco):
    with pytest.raises(HTTPException) as e:
        main._require_project_viewer(_req(), "J1")
    assert e.value.status_code == 401
    banco["usuario"] = EQUIPE
    banco["falha"] = True
    with pytest.raises(HTTPException) as e:
        main._require_project_viewer(_req(), "J1")
    assert e.value.status_code == 503


def test_a_rota_de_acesso_conta_o_que_a_tela_precisa(banco, monkeypatch):
    banco["usuario"] = EQUIPE
    antigo = main._supa_rest_service

    def servico(method, path, body=None, params=None, **k):
        if path == "/projects":
            return 200, [{"project_name": "Casa Exemplo", "typology": "residencial", "items_count": 191, "linhas_medidas": 48}]
        return antigo(method, path, body=body, params=params, **k)
    monkeypatch.setattr(main, "_supa_rest_service", servico)
    assert main.projeto_acesso("J1", _req()) == {
        "so_leitura": True, "escritorio_id": "E1", "pode_baixar": False,
        "nome": "Casa Exemplo", "tipologia": "residencial", "itens": 191, "medido": 48}
    banco["usuario"] = DONO
    assert main.projeto_acesso("J1", _req()) == {"so_leitura": False, "pode_baixar": True}


# ── a lista EXATA das rotas ──
VER = {("GET", "/api/status/{job_id}"), ("GET", "/api/items/{job_id}"), ("GET", "/api/sheet/{job_id}"),
       ("POST", "/api/projeto/{job_id}/pranchas-com-imagem"), ("GET", "/api/projeto/{job_id}/coerencia"),
       ("GET", "/api/cronograma/{job_id}"), ("GET", "/api/cronograma/{job_id}/full"),
       ("GET", "/api/memorial/{job_id}/estrutura"), ("GET", "/api/projeto/{job_id}/acesso")}
BAIXAR = {("GET", "/api/download/{job_id}"), ("GET", "/api/cronograma/{job_id}/export/pdf"),
          ("GET", "/api/cronograma/{job_id}/export/xlsx"), ("GET", "/api/cronograma/{job_id}/export/pptx"),
          ("GET", "/api/memorial/{job_id}"), ("GET", "/api/memorial/{job_id}/pdf")}


def _rotas_com_a_checagem_nova():
    fonte = open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    achadas = {}
    for m in re.finditer(r'@app\.(get|post|put|patch|delete)\("([^"]+)"\)', fonte):
        d = re.search(r'\n(?:async )?def [^\n]*\n', fonte[m.start():])
        ini = m.start() + d.end()
        f = re.search(r'\n(?:@app\.|def |async def |class )', fonte[ini:])
        corpo = fonte[ini: ini + (f.start() if f else len(fonte) - ini)]
        chamada = re.search(r'_require_project_viewer\(request, job_id(, baixar=True)?\)', corpo)
        if chamada:
            achadas[(m.group(1).upper(), m.group(2))] = bool(chamada.group(1))
    return achadas


def test_so_as_rotas_de_leitura_aceitam_a_equipe():
    achadas = _rotas_com_a_checagem_nova()
    assert set(achadas) == VER | BAIXAR, sorted(set(achadas) ^ (VER | BAIXAR))
    assert {r for r, b in achadas.items() if b} == BAIXAR, "rota que entrega arquivo tem que pedir baixar=True"
    escrita = [r for r in achadas if r[0] in ("PUT", "PATCH", "DELETE")] + \
              [r for r in achadas if r[0] == "POST" and r != ("POST", "/api/projeto/{job_id}/pranchas-com-imagem")]
    assert not escrita, f"rota que escreve aceitando a equipe: {escrita}"


def test_a_equipe_le_o_cronograma_com_a_chave_do_servidor():
    # as tabelas do projeto só conhecem o DONO na RLS: com o JWT da equipe a leitura voltaria vazia
    fonte = open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    assert "_fin_cronograma_salvo(_req_de_leitura(request), job_id)" in fonte
    assert fonte.count("_build_cronograma_for_export, job_id, request=_req_de_leitura(request))") == 3
    assert "_build_cronograma_for_export(job_id, request=_req_de_leitura(request))" in fonte


def test_download_da_equipe_nao_conta_como_cliente_e_nao_regenera():
    fonte = open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = fonte.index('@app.get("/api/download/{job_id}")')
    corpo = fonte[i:fonte.index("\n@app.", i + 10)]
    assert '_quem = "equipe" if _so_leitura(request) else' in corpo
    assert corpo.index("if _so_leitura(request):") < corpo.index("await rebuild_planilha_from_review(job_id, request)")


# ── as telas (só esconde o que daria erro: quem barra é o servidor) ──
_RAIZ = os.path.dirname(_BACKEND)


def _ler(nome):
    return open(os.path.join(_RAIZ, nome), encoding="utf-8").read()


def test_a_pagina_pergunta_ao_servidor_e_se_marca():
    u = _ler("aiarq-utils.js")
    assert "window.API_BASE + '/api/projeto/' + encodeURIComponent(jobId) + '/acesso'" in u
    marca = u[u.index("window.aiarqMarcarSoLeitura = function (jobId) {"):]
    assert "h.classList.add('so-leitura');" in marca
    assert "if (!a.pode_baixar) h.classList.add('sem-baixar');" in marca
    for pagina in ("projeto.html", "cronograma.html", "memorial.html"):
        assert "window.aiarqMarcarSoLeitura && window.aiarqMarcarSoLeitura(jobId)" in _ler(pagina), pagina


@pytest.mark.parametrize("pagina,so_dono,baixar", [
    ("projeto.html", ["#btn-reprocess", "#cad-upload-btn", "#btn-upload-rev", "#cotacoes-section", "#chat-quant",
                      "#client-data", '[onclick^="saveProjectAndClient"]'],
     ['[onclick^="downloadProtected"]', '[onclick^="openPdfProtected"]']),
    ("cronograma.html", ["#btn-gerar", "#btn-save", "#btn-edit", "#btn-add-fase"],
     ["#btn-export-pdf", "#btn-export-pptx", "#btn-export-xlsx"]),
    ("memorial.html", ["#btn-ia", "#btn-salvar"], ["#btn-docx", "#btn-pdf"]),
])
def test_cada_tela_esconde_as_acoes_do_dono_e_os_downloads_sem_liberacao(pagina, so_dono, baixar):
    fonte = _ler(pagina)
    for sel in so_dono:
        assert ".so-leitura " + sel in fonte, (pagina, sel)
    for sel in baixar:
        assert ".sem-baixar " + sel in fonte, (pagina, sel)
        assert ".so-leitura " + sel not in fonte, (pagina, sel, "download liberado pela admin tem que continuar visível")


def test_o_menu_da_equipe_mostra_so_o_que_ela_pode():
    js = _ler("menu-lateral.js")
    sel = js[js.index("function atualizarSelo()"):]
    assert sel.index("if (nx) nx.textContent = 'Projeto não encontrado';") < sel.index("montarEquipe();")
    eq = js[js.index("function montarEquipe() {"):]
    eq = eq[:eq.index("\n  }\n")]
    # 26/09: quem não é equipe (ou saiu) não ganha nada — e, se o menu nasceu da lembrança, ela é apagada
    assert "if (!a || !a.so_leitura) { if (a && ESC_DO_MAPA && !a.escritorio_id) gravarMapa(JOB, null); return; }" in eq
    # 25/09: tirar os itens do dono virou função (a troca pro menu do Escritório refaz os grupos e
    # precisa tirar de novo); o caminho de volta deixou de ser um link solto: o menu INTEIRO vira o do
    # Escritório (aplicarEscritorio), com "Página do projeto" etc.
    assert "tirarItensDoDono();" in eq
    tira = js[js.index("function tirarItensDoDono() {"):]
    assert "['revisao', 'financeiro', 'comparativo'].forEach(" in tira[:tira.index("\n  }\n")]
    assert "if (a.escritorio_id) aplicarEscritorio(" in eq


def test_a_admin_libera_o_download_por_pessoa():
    h = _ler("escritorio.html")
    assert "const COLS_MEMBRO = 'id,projeto_id,user_id,nome,papel,funcao,status,convidado_em,aceito_em,removido_em,pode_baixar';" in h
    assert "${souAdmin() && PROJ.job_id && m.papel !== 'dono' ? `<label class=\"chip\"" in h
    mb = h[h.index("async function mudarBaixar(id, v, el) {"):]
    mb = mb[:mb.index("\n}\n")]
    assert ".update({ pode_baixar: v }).eq('id', id).eq('projeto_id', PROJ.id)" in mb
    assert "if (el) el.checked = !v;" in mb                  # deu erro: a chave volta pro que era

