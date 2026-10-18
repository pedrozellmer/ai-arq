# -*- coding: utf-8 -*-
"""Os dois cortes do gasto do SINAPI (18/10/2026).

💸 Gasto de API, 30 dias (`llm_uso`): o `sinapi_pick` era 40 % do total.
  1. US$ 31 eram REPETIÇÃO no mesmo job — quem remonta a planilha (revisão,
     área informada) refazia a escolha inteira com os mesmos itens e os mesmos
     candidatos. → A escolha de cada item fica guardada (`llm_cache`, tag
     `sinapi_escolha`) e o mesmo item com os mesmos candidatos não volta pra IA.
  2. US$ 20,62 eram avaliações que nunca foram pro cliente. → `?sem_sinapi=1`
     na avaliação pula a etapa; a avaliação que pulou não é liberada.

🪤 A etapa do SINAPI também confere a unidade da linha (e tira o selo quando a
grandeza é suspeita): pular é opcional, e a planilha que pulou não vai pro
cliente nem à mão nem pelo vigia automático.
"""
import inspect
import json
import os
import re
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

import llm_retry  # noqa: E402
import sinapi_matcher as sm  # noqa: E402


# ── um banco e uma IA de mentira ─────────────────────────────────────────────
class _Banco:
    """A tabela `llm_cache`, só no que a escolha guardada usa."""

    def __init__(self, falha=False):
        self.linhas, self.gets, self.posts, self.falha = {}, 0, [], falha

    def __call__(self, method, path, body=None, params=None, prefer=None, timeout=15):
        assert path == "llm_cache"
        if self.falha:
            raise RuntimeError("banco fora")
        if method == "GET":
            self.gets += 1
            assert params["tag"] == "eq.sinapi_escolha"
            chaves = params["cache_key"][len("in.("):-1].split(",")
            return 200, [{"cache_key": k, "response_text": self.linhas[k]} for k in chaves if k in self.linhas]
        assert method == "POST" and prefer == "resolution=ignore-duplicates"
        self.posts.append(body)
        for linha in body:
            assert linha["tag"] == "sinapi_escolha" and linha["model"] == sm._MODELO_DA_ESCOLHA
            self.linhas.setdefault(linha["cache_key"], linha["response_text"])
        return 201, None


class _Resposta:
    def __init__(self, texto):
        self.content = [type("B", (), {"text": texto})()]
        self.stop_reason = "end_turn"


class _IA:
    """Responde, pra cada item do pedido, o código que `escolhe(descrição)` dá."""

    def __init__(self, escolhe):
        self.escolhe, self.pedidos = escolhe, []

    def __call__(self, client, **kw):
        texto = kw["messages"][0]["content"]
        self.pedidos.append(texto)
        saida = []
        for i, desc in re.findall(r"  i=(\d+) \| ITEM: (.*?) \[un:", texto):
            saida.append({"i": int(i), "codigo": self.escolhe(desc)})
        return _Resposta(json.dumps(saida))


def _itens(n=3):
    base = [("Piso porcelanato 60x60", "m²", [("87263", "REVESTIMENTO CERÂMICO PARA PISO COM PLACAS PORCELANATO 60X60"),
                                               ("1", "PISO DE BORRACHA CANELADO")]),
            ("Bacia sanitária com caixa acoplada", "un", [("86931", "VASO SANITÁRIO SIFONADO COM CAIXA ACOPLADA"),
                                                          ("2", "CUBA DE EMBUTIR")]),
            ("Spot LED de embutir", "un", [("3", "CUBA DE EMBUTIR REDONDA EM LOUÇA")])]
    out = []
    for k in range(n):
        d, u, cs = base[k % len(base)]
        out.append({"description": d + ("" if k < len(base) else " %d" % k), "unit": u,
                    "candidates": [{"codigo": c, "descricao": t, "unidade": "UN"} for c, t in cs]})
    return out


def _certo(desc):
    if desc.startswith("Piso"):
        return "87263"
    if desc.startswith("Bacia"):
        return "86931"
    return None                                  # o spot: o SINAPI não tem


@pytest.fixture
def ambiente(monkeypatch):
    monkeypatch.delenv("SINAPI_ESCOLHA_GUARDADA", raising=False)
    banco, ia = _Banco(), _IA(_certo)
    monkeypatch.setattr(sm, "_client", lambda: object())
    monkeypatch.setattr(sm, "_rest_do_banco", lambda: banco)
    monkeypatch.setattr(llm_retry, "call_with_retry", ia)
    return banco, ia


# ── 1. a escolha guardada ────────────────────────────────────────────────────
def test_a_primeira_vez_pergunta_e_guarda_cada_item(ambiente):
    banco, ia = ambiente
    assert sm.pick_best_batch(_itens()) == {0: "87263", 1: "86931", 2: None}
    assert len(ia.pedidos) == 1
    assert len(banco.posts) == 1 and sorted(l["response_text"] for l in banco.posts[0]) == ["-", "86931", "87263"]


def test_a_remontagem_com_os_mesmos_itens_nao_paga_de_novo(ambiente):
    banco, ia = ambiente
    sm.pick_best_batch(_itens())
    assert sm.pick_best_batch(_itens()) == {0: "87263", 1: "86931", 2: None}
    assert len(ia.pedidos) == 1, "a 2ª passada não pode chamar a IA"


def test_o_item_editado_volta_pra_ia_e_so_ele(ambiente):
    banco, ia = ambiente
    sm.pick_best_batch(_itens())
    itens = _itens()
    itens[1]["description"] = "Bacia sanitária convencional"
    assert sm.pick_best_batch(itens) == {0: "87263", 1: "86931", 2: None}
    assert len(ia.pedidos) == 2
    assert ia.pedidos[1].count("  i=") == 1 and "i=1 | ITEM: Bacia sanitária convencional" in ia.pedidos[1]


def test_CONTROLE_unidade_ou_candidato_diferente_e_outro_item(ambiente):
    banco, ia = ambiente
    sm.pick_best_batch(_itens())
    itens = _itens()
    itens[0]["unit"] = "ml"
    itens[1]["candidates"].append({"codigo": "9", "descricao": "OUTRA COISA", "unidade": "UN"})
    sm.pick_best_batch(itens)
    assert ia.pedidos[1].count("  i=") == 2


def test_o_codigo_guardado_que_saiu_dos_candidatos_nao_vale(ambiente):
    banco, ia = ambiente
    itens = _itens()
    sm.pick_best_batch(itens)
    # a mesma chave, mas o código guardado não está mais entre os candidatos
    banco.linhas[sm._chave_da_escolha(itens[0])] = "99999"
    assert sm.pick_best_batch(_itens())[0] == "87263"
    assert len(ia.pedidos) == 2 and ia.pedidos[1].count("  i=") == 1


def test_o_nenhum_que_a_ia_disse_tambem_fica_guardado(ambiente):
    banco, ia = ambiente
    sm.pick_best_batch(_itens())
    assert banco.linhas[sm._chave_da_escolha(_itens()[2])] == "-"
    assert sm.pick_best_batch(_itens())[2] is None and len(ia.pedidos) == 1


def test_o_codigo_inventado_pela_ia_nao_fica_guardado(ambiente, monkeypatch):
    banco, ia = ambiente
    monkeypatch.setattr(ia, "escolhe", lambda d: "00000" if d.startswith("Piso") else _certo(d))
    assert sm.pick_best_batch(_itens())[0] is None
    assert sm._chave_da_escolha(_itens()[0]) not in banco.linhas
    monkeypatch.setattr(ia, "escolhe", _certo)
    assert sm.pick_best_batch(_itens())[0] == "87263"
    assert ia.pedidos[1].count("  i=") == 1


def test_CONTROLE_com_a_chave_em_zero_nao_le_nem_grava(ambiente, monkeypatch):
    banco, ia = ambiente
    monkeypatch.setenv("SINAPI_ESCOLHA_GUARDADA", "0")
    sm.pick_best_batch(_itens())
    sm.pick_best_batch(_itens())
    assert banco.gets == 0 and banco.posts == [] and len(ia.pedidos) == 2


def test_banco_fora_a_ia_escolhe_como_antes(monkeypatch):
    banco, ia = _Banco(falha=True), _IA(_certo)
    monkeypatch.setattr(sm, "_client", lambda: object())
    monkeypatch.setattr(sm, "_rest_do_banco", lambda: banco)
    monkeypatch.setattr(llm_retry, "call_with_retry", ia)
    assert sm.pick_best_batch(_itens()) == {0: "87263", 1: "86931", 2: None}
    assert len(ia.pedidos) == 1


def test_o_lote_continua_de_12_e_cada_item_e_guardado(ambiente):
    banco, ia = ambiente
    escolhas = sm.pick_best_batch(_itens(13))
    assert len(ia.pedidos) == 2 and len(escolhas) == 13
    assert sum(len(b) for b in banco.posts) == 13


def test_o_pedido_a_ia_e_o_mesmo_de_antes(ambiente):
    """A linha do prompt passou a sair de `_linha_do_item` (a mesma da chave):
    o texto que vai pra IA tem de ser byte a byte o de antes."""
    banco, ia = ambiente
    itens = _itens()
    sm.pick_best_batch(itens)
    linhas = []
    for i, it in enumerate(itens):                    # a montagem de antes de 18/10
        cands = "\n".join(
            f'     - {c.get("codigo")}: {sm._texto_pra_ia(c.get("descricao"))} [un: {c.get("unidade") or "?"}]'
            for c in it['candidates'])
        linhas.append(f'  i={i} | ITEM: {(it.get("description") or "")[:sm._TETO_TEXTO_IA]} '
                      f'[un: {it.get("unit") or "?"}]\n     CANDIDATOS:\n{cands}')
    assert ia.pedidos[0] == sm._PICK_PROMPT.format(items="\n".join(linhas))


def test_a_chave_muda_com_o_modelo_e_com_o_pedido(monkeypatch):
    it = _itens()[0]
    k = sm._chave_da_escolha(it)
    monkeypatch.setattr(sm, "_MODELO_DA_ESCOLHA", "outro-modelo")
    assert sm._chave_da_escolha(it) != k
    monkeypatch.undo()
    monkeypatch.setattr(sm, "_PICK_PROMPT", sm._PICK_PROMPT + " ")
    assert sm._chave_da_escolha(it) != k


def test_a_chave_nao_leva_o_texto_do_cliente():
    k = sm._chave_da_escolha(_itens()[0])
    assert re.fullmatch(r"[0-9a-f]{64}", k)


# ── 2. a avaliação sem a etapa do SINAPI ─────────────────────────────────────
import main  # noqa: E402
from fastapi import HTTPException  # noqa: E402


@pytest.fixture
def sem_sinapi(monkeypatch):
    monkeypatch.setattr(main, "_SEM_SINAPI_DA_AVALIACAO", {"ev123456", "abcd1234"})


def test_so_a_avaliacao_que_pediu_pula(sem_sinapi):
    assert main._avaliacao_sem_sinapi("ev123456") is True
    assert main._avaliacao_sem_sinapi("ev654321") is False
    # job de cliente NUNCA pula, nem se o id estiver no conjunto
    assert main._avaliacao_sem_sinapi("abcd1234") is False
    assert main._avaliacao_sem_sinapi(None) is False


@pytest.mark.parametrize("valor, esperado", [("1", True), ("true", True), ("sim", True), ("0", False),
                                            ("", False), (None, False), ("nao", False)])
def test_o_pedido_da_opcao(valor, esperado):
    assert main._pediu_sem_sinapi(valor) is esperado


def test_a_rota_de_avaliacao_aceita_a_opcao_e_marca_o_nome():
    assert "sem_sinapi" in inspect.signature(main.admin_eval_reprocess).parameters
    fonte = inspect.getsource(main.admin_eval_reprocess)
    assert "_SEM_SINAPI_DA_AVALIACAO.add(eval_job_id)" in fonte
    assert '" [sem SINAPI]" if _sem_sinapi else ""' in fonte


def test_o_pipeline_pula_a_etapa_e_deixa_a_marca():
    fonte = inspect.getsource(main.process_job)
    assert "_pular_sinapi = _avaliacao_sem_sinapi(job_id)" in fonte
    assert "_ex.map(_cands, [] if _pular_sinapi else all_items)" in fonte
    assert "_log_error(_ETAPA_SINAPI_PULADA," in fonte
    # uma vez só: a etapa da conferência de unidade roda sobre o MESMO lote vazio
    assert fonte.count("_ex.map(_cands,") == 1


class _Req:
    def __init__(self, **q):
        self.query_params, self.headers = dict(q), {}


@pytest.fixture
def liberacao(monkeypatch):
    estado = {"marca": (200, []), "pai": [{"job_id": "pai00001", "user_id": "u1", "user_email": "",
                                           "user_name": "", "project_name": "P"}]}
    monkeypatch.setattr(main, "_require_admin", lambda *a, **k: True)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)

    def _rows(method, table, params=None, **k):
        if table == "projects" and params["job_id"] == "eq.ev123456":
            return [{"job_id": "ev123456", "parent_job_id": "pai00001", "is_eval": True,
                     "user_id": "eval", "project_name": "[TESTE] P — avaliação", "status": "done"}]
        if table == "projects":
            return estado["pai"]
        return []

    def _service(method, table, params=None, **k):
        assert table == "error_log" and params["stage"] == "eq.motor:sinapi-pulado"
        return estado["marca"]

    monkeypatch.setattr(main, "_supa_rows", _rows)
    monkeypatch.setattr(main, "_supa_rest_service", _service)
    # o que vem DEPOIS da trava: chegar aqui prova que ela deixou passar
    monkeypatch.setattr(main, "_contagem_para_liberar",
                        lambda *a: (_ for _ in ()).throw(RuntimeError("passou da trava")))
    return estado


def test_a_avaliacao_sem_sinapi_nao_e_liberada(liberacao):
    liberacao["marca"] = (200, [{"id": 1}])
    with pytest.raises(HTTPException) as e:
        main.admin_liberar_filhote("ev123456", _Req())
    assert e.value.status_code == 409 and "SINAPI" in e.value.detail


def test_CONTROLE_sem_a_marca_a_liberacao_segue(liberacao):
    with pytest.raises(RuntimeError, match="passou da trava"):
        main.admin_liberar_filhote("ev123456", _Req())


def test_sem_conseguir_ler_a_marca_nao_libera(liberacao):
    liberacao["marca"] = (500, None)
    with pytest.raises(HTTPException) as e:
        main.admin_liberar_filhote("ev123456", _Req())
    assert e.value.status_code == 502


def test_revogar_nao_passa_pela_trava(liberacao):
    liberacao["marca"] = (200, [{"id": 1}])
    with pytest.raises(RuntimeError, match="passou da trava"):
        main.admin_liberar_filhote("ev123456", _Req(revogar="1"))


@pytest.mark.parametrize("marca, motivo", [((200, [{"id": 1}]), "rodou sem a etapa do SINAPI"),
                                           ((500, None), "não consegui conferir")])
def test_o_vigia_automatico_tambem_nao_libera(monkeypatch, marca, motivo):
    import time as _t
    logs, lidos = [], []
    monkeypatch.setattr(_t, "sleep", lambda *_: None)
    monkeypatch.setattr(main, "_log_error", lambda st, msg, *a, **k: logs.append((st, msg)))

    def _rows(method, table, params=None, **k):
        lidos.append(params["job_id"])
        return [{"status": "done", "user_id": "eval"}]

    monkeypatch.setattr(main, "_supa_rows", _rows)
    monkeypatch.setattr(main, "_supa_rest_service", lambda *a, **k: marca)
    main._auto_liberar_filhote_quando_pronto("ev123456", "pai00001", timeout_min=1)
    assert ("filhote:auto", "não liberei: " + ("a avaliação rodou sem a etapa do SINAPI (sem_sinapi=1)"
                                                if marca[0] == 200 else
                                                "não consegui conferir se rodou com o SINAPI — na dúvida, não mexo")) in logs
    assert motivo
    assert "eq.pai00001" not in lidos, "não pode nem chegar a ler o original"
