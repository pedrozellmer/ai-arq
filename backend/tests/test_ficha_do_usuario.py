# -*- coding: utf-8 -*-
"""A ficha do usuario mostra tudo — e nao mente quando nao consegue ler.

Pedro, 31/08/2026: *"A gente consegue fazer uma pagina de usuarios, com todas
as funcoes, tudo que o cara respondeu, tudo que ele fez"* e *"Tudo de produto,
deixar isso claro na aba usuario pra poder ver tudo que foi feito"*.

O RISCO CENTRAL desta rota, e o motivo de existir teste: `_supa_rows` devolve
`[]` em QUALQUER falha. Uma secao que quebrou fica identica a uma secao sem
dado — e a tela concluiria "esse cliente nunca usou o chat" quando na verdade
a consulta caiu. E o mesmo erro do /api/track (29h de 500 calados) e do cron
que dizia `succeeded` com o erro no corpo: HTTP 200 nao prova nada.

Por isso a rota carrega `_falhas` e estes testes cobram esse contrato.
"""
import json
import os
import sys
import urllib.parse as _up

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


class _Req:
    headers = {}
    client = None


PERFIL = {"user_id": "u-9", "full_name": "cliente-13",
          "email": "marcelo@exemplo.com", "company": "MA Arq", "role": "arquiteto"}
PROJETO = {"job_id": "j1", "project_name": "Casa", "status": "done",
           "items_count": 40, "is_eval": False}


def _colunas_pedidas(consulta, kw):
    """As colunas do `select=` — vazio quando e `*` ou quando nao ha select."""
    q = dict(_up.parse_qsl(consulta or "", keep_blank_values=True))
    sel = (kw.get("params") or {}).get("select") or q.get("select") or ""
    if not sel or sel.strip() == "*":
        return set()
    return {c.strip() for c in sel.split(",") if c.strip()}


def _falso_banco(mapa, quebra=()):
    """Dubla o Supabase: devolve o que o mapa disser, por prefixo de tabela.

    🔑 06/09 — e HONRA o `select=`, como o PostgREST de verdade. Sem isso o
    dublê devolvia a linha INTEIRA e a ficha "vazava" ou "nao vazava" por
    conta do dublê, nunca por conta da rota: qualquer coluna nova no `select`
    ficava invisivel pro guarda de privacidade.

    `quebra` = tabelas que devem ESTOURAR, pra simular indisponibilidade real."""
    def _f(method, path, *a, **kw):
        tabela, _sep, consulta = path.partition("?")
        if tabela in quebra:
            raise OSError("connection reset")
        linhas = [dict(r) for r in mapa.get(tabela, [])]
        colunas = _colunas_pedidas(consulta, kw)
        if colunas:
            linhas = [{k: v for k, v in r.items() if k in colunas} for r in linhas]
        return 200, linhas
    return _f


def _chamar(monkeypatch, mapa, quebra=(), chave="marcelo@exemplo.com"):
    monkeypatch.setattr(main, "_require_admin", lambda *a, **k: {"email": "admin@x"})
    monkeypatch.setattr(main, "_supa_rest_service", _falso_banco(mapa, quebra))
    return main.admin_ficha_usuario(chave, _Req())


def test_ficha_junta_tudo_num_lugar_so(monkeypatch):
    """O pedido do Pedro: respondeu + fez, na mesma tela."""
    d = _chamar(monkeypatch, {
        "profiles": [PERFIL],
        "projects": [PROJETO],
        "nps_responses": [{"score": 9, "comment": "Gostei muito do resultado",
                           "context": "after_download"}],
        "item_reviews": [{"action": "edit"}, {"action": "reject"}, {"action": "approve"}],
        "agent_conversations": [{"question": "quanto de piso?"}],
        "project_memorial": [{"job_id": "j1"}],
        "cronogramas": [{"job_id": "j1"}],
        "usage_events": [{"event": "download_xlsx"}],
    })
    r = d["resumo"]
    assert r["projetos"] == 1 and r["projetos_concluidos"] == 1
    assert r["respondeu_nps"] == 1 and r["melhor_nps"] == 9
    assert r["usou_chat"] is True, "o Pedro pediu explicitamente 'se usou o chat'"
    assert r["gerou_memorial"] is True, "o Pedro pediu explicitamente 'se fez memorial'"
    assert r["gerou_cronograma"] is True
    assert r["revisoes_por_acao"] == {"edit": 1, "reject": 1, "approve": 1}
    assert d["nps"][0]["comment"] == "Gostei muito do resultado"
    assert not d["_falhas"], d["_falhas"]


def test_SECAO_QUE_QUEBROU_NAO_VIRA_nunca_usou(monkeypatch):
    """O teste que justifica a rota inteira.

    O chat CAIU. A ficha nao pode dizer 'usou_chat: false' e pronto — isso vira
    conclusao errada sobre o cliente. Tem que aparecer em `_falhas`."""
    d = _chamar(monkeypatch,
                {"profiles": [PERFIL], "projects": [PROJETO]},
                quebra=("agent_conversations",))
    assert d["resumo"]["usou_chat"] is False
    assert any("chat" in f for f in d["_falhas"]), (
        "a consulta do chat quebrou e a ficha nao avisou — a tela diria "
        "'nunca usou o chat' sobre alguem que talvez tenha usado")


def test_varias_falhas_sao_TODAS_listadas(monkeypatch):
    d = _chamar(monkeypatch, {"profiles": [PERFIL], "projects": [PROJETO]},
                quebra=("nps_responses", "contact_messages", "usage_events"))
    txt = " | ".join(d["_falhas"])
    assert "NPS" in txt and "contato" in txt and "eventos" in txt, txt


def test_vazio_de_verdade_NAO_vira_falha(monkeypatch):
    """CONTROLE NEGATIVO: cliente que realmente nao fez nada tem `_falhas`
    vazio. Sem isto, o alarme tocaria sempre e viraria ruido."""
    d = _chamar(monkeypatch, {"profiles": [PERFIL], "projects": []})
    assert d["resumo"]["projetos"] == 0
    assert d["resumo"]["usou_chat"] is False
    assert d["_falhas"] == [], d["_falhas"]


def test_aceita_user_id_alem_do_email(monkeypatch):
    """A tela do admin navega por ?id=<user_id>; o Pedro busca por e-mail."""
    d = _chamar(monkeypatch, {"profiles": [PERFIL], "projects": [PROJETO]},
                chave="u-9")
    assert d["user_id"] == "u-9" and d["email"] == "marcelo@exemplo.com"
    assert d["resumo"]["projetos"] == 1


def test_cadastro_incompleto_AVISA_em_vez_de_mentir(monkeypatch):
    """Conta no auth sem linha em `profiles` e caso real (12 em 26/08). Sem
    e-mail nao da pra ler as tabelas ligadas por e-mail — a tela precisa saber,
    senao mostra tudo zerado como se a pessoa nao tivesse feito nada."""
    d = _chamar(monkeypatch, {"profiles": [], "projects": [PROJETO]}, chave="u-404")
    assert d["email"] == ""
    assert any("sem perfil" in f for f in d["_falhas"]), d["_falhas"]
    assert d["resumo"]["projetos"] == 0


def test_projeto_de_avaliacao_nao_conta_como_do_cliente(monkeypatch):
    """`is_eval` e reprocesso nosso, nao uso do cliente — inflaria a contagem
    (armadilha ja registrada: metrica inflada por reprocesso)."""
    d = _chamar(monkeypatch, {
        "profiles": [PERFIL],
        "projects": [PROJETO, dict(PROJETO, job_id="j2", is_eval=True)],
    })
    assert d["resumo"]["projetos"] == 1, "projeto de avaliacao entrou na conta"


# ── Privacidade: o que a rota DEVOLVE, e pelos DOIS caminhos de busca ─────
# 🪤 06/09 — o guarda antigo procurava tres nomes de coluna e so exercitava a
# busca por E-MAIL. Dois buracos: (a) a tela do admin navega por `?id=<user_id>`
# — o caminho mais usado — e vazamento por ele passava verde; (b) a lista de
# proibidos era fechada, entao qualquer coluna nova (`endereco`, `whatsapp` do
# cliente final, documento com outro nome) saia sem ninguem ver.
# 🔑 Agora o dublê guarda um VALOR-ISCA em cada coluna que nao pode sair, e o
# guarda cobra que nenhuma isca apareca na resposta — seja qual for o nome da
# coluna.
_ISCA = "ISCA-NAO-PODE-SAIR-"
_PROIBIDAS = {
    "profiles": ("cpf_cnpj", "endereco", "documento", "senha_hash"),
    "project_clients": ("client_phone", "client_email", "client_cpf",
                        "client_address"),
    "nps_responses": ("ip",),
}


def _mapa_com_iscas():
    """O banco de mentira com as colunas proibidas PRESENTES — se a rota
    pedir alguma, a isca aparece na resposta."""
    def _com(base, tabela):
        return dict(base, **{c: _ISCA + c for c in _PROIBIDAS.get(tabela, ())})
    return {
        "profiles": [_com(PERFIL, "profiles")],
        "projects": [PROJETO],
        "nps_responses": [_com({"score": 9, "comment": "Gostei"}, "nps_responses")],
        "project_clients": [_com({"job_id": "j1", "client_name": "ISCA-PERMITIDA-nome",
                                  "client_company": "MA Arq"}, "project_clients")],
        "agent_conversations": [{"job_id": "j1", "question": "quanto de piso?"}],
    }


@pytest.mark.parametrize("chave", ["marcelo@exemplo.com", "u-9"],
                         ids=["por_email", "por_user_id"])
def test_nao_devolve_documento_nem_telefone_de_terceiro(monkeypatch, chave):
    """Privacidade: a ficha existe pra entender USO. CPF/CNPJ nao ajuda nisso,
    e telefone/e-mail do cliente final do usuario e dado de terceiro.

    🔑 Os DOIS caminhos: a interface do admin busca por `user_id`, o Pedro
    busca por e-mail. Vazar por um so ja e vazar."""
    d = _chamar(monkeypatch, _mapa_com_iscas(), chave=chave)
    inteiro = json.dumps(d, default=str, ensure_ascii=False)
    vazou = sorted({p for tab in _PROIBIDAS.values() for p in tab
                    if (_ISCA + p) in inteiro})
    assert not vazou, (
        "a ficha (busca por %r) devolveu coluna que nao pode sair: %s"
        % (chave, vazou))

    # 🧪 CONTROLE POSITIVO no mesmo teste: se o dublê nao entregasse NADA, o
    # assert de cima passaria por vacuidade. O que e permitido tem que chegar.
    assert "ISCA-PERMITIDA-nome" in inteiro, (
        "nem o dado PERMITIDO chegou — o guarda acima estaria absolvendo por "
        "resposta vazia, nao por privacidade")
    assert d["resumo"]["cadastrou_cliente_final"] is True


def test_CONTROLE_o_duble_do_banco_ENTREGA_a_coluna_que_a_rota_pede():
    """🧪 O guarda de privacidade so vale se o dublê devolver de verdade o que
    o `select=` pede. Se ele filtrasse tudo, nenhuma isca apareceria nunca e o
    teste acima seria decoracao."""
    banco = _falso_banco({"profiles": [{"user_id": "u-9", "cpf_cnpj": "X-9"}]})
    _st, linhas = banco("GET", "profiles?user_id=eq.u-9&select=user_id,cpf_cnpj")
    assert linhas == [{"user_id": "u-9", "cpf_cnpj": "X-9"}], linhas
    _st, linhas = banco("GET", "profiles?user_id=eq.u-9&select=user_id")
    assert linhas == [{"user_id": "u-9"}], "o dublê ignorou o select="


def test_a_rota_exige_admin(monkeypatch):
    """CONTROLE: sem admin, nao passa. Este e o unico guarda entre um dossie
    completo de cliente e qualquer pessoa logada."""
    import inspect
    src = inspect.getsource(main.admin_ficha_usuario)
    assert "_require_admin(request)" in src
    # e de verdade: se o _require_admin estourar, a rota nao devolve nada
    def _nega(*a, **k):
        raise main.HTTPException(403, "nao")
    monkeypatch.setattr(main, "_require_admin", _nega)
    monkeypatch.setattr(main, "_supa_rest_service", _falso_banco({"profiles": [PERFIL]}))
    try:
        main.admin_ficha_usuario("marcelo@exemplo.com", _Req())
    except main.HTTPException as e:
        assert e.status_code == 403
    else:
        raise AssertionError("a rota respondeu sem admin")
