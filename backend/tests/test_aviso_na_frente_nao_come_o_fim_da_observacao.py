# -*- coding: utf-8 -*-
"""Quem junta aviso à observação não pode comer o FIM dela.

🩸 22/09/2026 — revisão do conserto do caso ee801b82/f8d8e6d8. O conserto de
antes trocou o corte da GRAVAÇÃO (`obs[:1000]` → `_observacao_que_cabe`, que
guarda a cabeça e o fim e corta o meio). Mas treze pontos do motor põem um
aviso NA FRENTE da observação e cortavam `[:1000]` EM MEMÓRIA — cinco deles
DEPOIS da honestidade de área, que escreve o motivo do zero e a ressalva
"atribuída pela IA — confira" no FIM. A observação chegava à gravação com
exatamente 1000 caracteres e o fim já comido; o conserto da gravação não tinha
o que recuperar.

📏 Medido em 22/09/2026 15:42 (Brasília), 60 dias e sem eval: 813 linhas no
teto de 1000, em 39 jobs; 57 delas começam pelo prepend do SINAPI — grandeza
13, unidade 4 e base de medição 40, que saem do MESMO `if` —, e para essas o
conserto de antes não mudava nada. Caso real: a linha de fôrma "32,4 m" do
f8d8e6d8 tem 1000 caracteres, começa com "⚠ CONFERIR A GRANDEZA" e acaba no
meio da lista de pranchas, num parêntese aberto.

Cada guarda EXECUTA o ponto real: as regras que são função são chamadas; os
laços que moram dentro do `process_job` são recortados do próprio main.py pela
árvore sintática e rodados com um escopo montado à mão (o método de
`_executa.py`). O controle está em cada teste: a observação que sai tem a
emenda do corte do MEIO — prova de que passou de 1000, ou seja, de que o
`[:1000]` de antes teria levado o fim junto.
"""
import ast
import os
import sys
import textwrap

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import main  # noqa: E402
from models import BudgetItem, Confidence  # noqa: E402

#: a ressalva que a honestidade escreve no FIM — é ela que o corte comia
_FIM = " | Quantidade atribuída pela IA a esta linha — confira."


def _obs_longa(cabeca="Cálculo lido da prancha: "):
    """Uma observação que já está perto do teto quando o aviso chega."""
    corpo = cabeca + "trecho da leitura da IA sobre esta peça; " * 30
    return corpo[:960 - len(_FIM)] + _FIM


def _confere(obs, aviso):
    assert obs.startswith(aviso), "o aviso não ficou na frente: %r" % obs[:120]
    assert obs.endswith(_FIM), (
        "o fim da observação — a ressalva da IA — foi comido: ...%r" % obs[-120:])
    assert len(obs) <= main._OBS_TETO_GRAVADO, len(obs)
    # 🧪 controle: passou do teto e foi cortada no MEIO — o `[:1000]` de antes
    # teria levado o fim
    assert main._OBS_EMENDA in obs, "o cenário não passou de 1000 — não prova nada"


@pytest.fixture(autouse=True)
def _sem_rede(monkeypatch):
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supa_log", lambda *a, **k: None)


def _item(descricao, unidade, quantidade, obs, selo="estimado", **extra):
    it = BudgetItem(item_num="", description=descricao, unit=unidade,
                    quantity=quantidade, observations=obs, ref_sheet="prancha-A.pdf",
                    confidence=Confidence(selo), discipline=extra.pop("discipline", ""))
    for k, v in extra.items():
        setattr(it, k, v)
    return it


# ── os laços que moram dentro do process_job ────────────────────────────────
def _laco_do_process_job(marcador):
    """O MENOR `for` do `process_job` que contém `marcador`, dedentado."""
    from _executa import _funcao
    no_fn, src = _funcao("process_job")
    linhas = src.splitlines(True)
    achados = []
    for no in ast.walk(no_fn):
        if isinstance(no, ast.For):
            bruto = "".join(linhas[no.lineno - 1:no.end_lineno])
            if marcador in bruto:
                achados.append((no.end_lineno - no.lineno, bruto))
    assert achados, "o laço com %r sumiu do process_job" % marcador
    achados.sort(key=lambda t: t[0])
    return textwrap.dedent(achados[0][1])


def _roda_laco(marcador, **escopo):
    ns = dict(vars(main))
    ns.update(escopo)
    exec(compile(_laco_do_process_job(marcador), "<process_job>", "exec"), ns)
    return ns


def test_o_aviso_SINAPI_de_grandeza_nao_come_a_ressalva_do_fim():
    """🩸 O caso da fôrma "32,4 m" do f8d8e6d8: roda DEPOIS da honestidade."""
    it = _item("Fôrma de madeira para parede do poço", "m", 32.4, _obs_longa())
    it.sinapi_matches = [{"_llm_picked": True, "unidade": "M2", "codigo": "92263"}]
    _roda_laco("contra a prancha antes de usar este número. ",
               lote=[{"_item": it}], _n_unid=0, _n_base=0, _n_reb_un=0)
    _confere(it.observations, "⚠ CONFERIR A GRANDEZA")


def test_o_aviso_de_numero_PARCIAL_nao_come_a_ressalva_do_fim():
    from engine_rules import numero_declarado_parcial
    it = _item("Tubulação de esgoto", "m", 1.42,
               _obs_longa("layer SAN = 1,42 m. Valor provavelmente parcial. "),
               selo="confirmado")
    _roda_laco("como quantidade fechada: cobre só parte do que existe. ",
               all_items=[it], _e_parcial=numero_declarado_parcial,
               _CfPar=Confidence, _n_par=0)
    _confere(it.observations, "⚠ O número mede só PARTE")


def test_o_rebaixamento_por_procedencia_de_TEXTO_nao_come_o_fim():
    it = _item("Piso cerâmico", "m²", 264.54, _obs_longa(), selo="confirmado")
    _roda_laco('"não medido da geometria. " + _o', all_items=[it],
               _sem_geo=[{"indice": 0}], _CfG=Confidence, _falhou_rebaixar=0)
    _confere(it.observations, "⚠ ESTIMADO — este número foi LIDO")


def test_o_rebaixamento_por_ESCALA_divergente_nao_come_o_fim():
    it = _item("Condutos no teto", "m", 9.92, _obs_longa(), selo="confirmado")
    _roda_laco("pode estar 1000× fora. Confira contra a prancha. ", all_items=[it],
               _e_escala=lambda u: True, _da_suspeita=lambda _i: True,
               _CfE=Confidence, _reb=0)
    _confere(it.observations, "⚠ ESTIMADO — as pranchas deste projeto")


def test_o_aviso_de_PAREDE_abaixo_do_minimo_nao_come_o_fim():
    it = _item("Alvenaria de vedação", "m²", 44.67, _obs_longa(), selo="confirmado",
               discipline="Fechamentos Verticais")
    _roda_laco("trate este número como piso, não como medida. ", all_items=[it],
               _e_escala_p=lambda u: True, _CfP=Confidence, _reb_p=0,
               _maior=17.18, _min_per=27.36, _area_ref=46.79)
    _confere(it.observations, "⚠ A leitura encontrou MENOS parede")


# ── as regras que são função ────────────────────────────────────────────────
def test_o_EXISTENTE_nao_come_o_fim():
    it = _item("[EXISTENTE - manter] Piso cerâmico da sala", "m²", 18.5, _obs_longa())
    assert main.existente_nao_leva_quantidade([it]) == 1
    _confere(it.observations, "Levantado: 18.5 m² do que JÁ EXISTE")


def test_o_bloco_SEM_IDENTIDADE_nao_come_o_fim():
    it = _item("Equipamento não identificado — bloco CAD '1258C37_v' — verificar "
               "com projetista", "un", 3, _obs_longa(), selo="confirmado")
    main.rebaixar_itens_sem_identidade([it])
    _confere(it.observations, "⚠ A CONTAGEM é do desenho")


def test_o_pe_direito_da_ESTRUTURA_nao_come_o_fim():
    """Roda DEPOIS da honestidade (`_derive_estrutura_pe_direito`)."""
    pilar = _item("Pilar P1 20x40 cm", "un", 4, "")
    conc = _item("Concreto fck 30 MPa para pilares", "m³", 0, _obs_longa())
    forma = _item("Fôrma de madeira para pilares", "m²", 12.0, _obs_longa())
    assert main._derive_estrutura_pe_direito([pilar, conc, forma], 3.0) == 2
    _confere(conc.observations, "Derivado das seções contadas")
    # o ramo que ACRESCENTA no fim: a conferência nova é que não pode sumir
    assert "Conferência por seção×PD" in forma.observations, forma.observations[-160:]
    assert forma.observations.startswith("Cálculo lido da prancha")
    assert main._OBS_EMENDA in forma.observations


def test_a_juncao_da_ADMINISTRACAO_LOCAL_nao_come_o_fim():
    fica = _item("Administração local de obra — encarregado, mestre e equipe de "
                 "gestão da obra", "vb", 1, _obs_longa(), discipline="Serviços Preliminares")
    sai = _item("Administração local de obra — engenheiro residente", "vb", 1, "",
                discipline="Serviços Preliminares")
    todos = [fica, sai]
    assert main._juntar_admin_local(todos) == 1 and todos == [fica]
    _confere(fica.observations, main._MARCA_ADMIN_JUNTADA)


def test_a_fusao_das_REVISOES_do_cliente_nao_come_o_fim(monkeypatch):
    """Roda DEPOIS da honestidade: a linha que o cliente revisou volta com a
    observação do pai — e o fim dela é o veredito que o pai gravou."""
    obs_pai = _obs_longa()

    def _svc(method, path, **kw):
        if path == "item_reviews":
            return 200, [{"item_id": "i1", "reviewed_at": "2026-09-01T10:00:00Z",
                          "edits": {"description": "Piso cerâmico da sala",
                                    "unit": "m²", "quantity": 20,
                                    "_antes": {"quantity": 18, "unit": "m²"}}}]
        return 200, []
    monkeypatch.setattr(main, "_supa_rest_service", _svc)
    monkeypatch.setattr(main, "_supa_rest_tudo", lambda *a, **k: (200, [
        {"id": "i1", "description": "Piso cerâmico da sala", "unit": "m²",
         "quantity": 20, "observations": obs_pai, "confidence": "estimado"}]))
    itens = [_item("Piso cerâmico da sala", "m²", 18, "leitura nova")]
    itens, resumo = main._fundir_revisoes_do_cliente(itens, "pai00001")
    assert resumo["casadas"] == 1, resumo
    _confere(itens[0].observations, "✏️ QUANTIDADE CORRIGIDA POR VOCÊ")

    # o outro ramo: a leitura nova não tem a linha, e a revisão é ACRESCENTADA
    outros = [_item("Forro de gesso acartonado", "m²", 30, "leitura nova")]
    outros, resumo = main._fundir_revisoes_do_cliente(outros, "pai00001")
    assert resumo["acrescentadas"] == 1 and len(outros) == 2, resumo
    _confere(outros[-1].observations, "✏️ REVISADO POR VOCÊ — mantido")


def _grava_correcao_do_cliente(monkeypatch, obs_no_banco, quantidade_nova=20):
    """RODA a rota real `submit_item_review` e devolve o que ela mandou gravar.

    O banco é de mentira dos dois lados: o `antes` vem do `_supa_rest_service`
    e o PATCH sai pelo `urllib.request.urlopen`, que é onde a rota escreve.
    """
    import urllib.request as _ur

    enviado = {}

    def _svc(metodo, caminho, **k):
        if metodo == "GET" and caminho.startswith("project_items?"):
            return 200, [{"description": "Piso cerâmico da sala", "unit": "m²",
                          "quantity": 18, "observations": obs_no_banco,
                          "confidence": "confirmado", "discipline": "Pisos",
                          "ref_sheet": "prancha-A.pdf"}]
        return 200, []

    class _Resp(object):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _urlopen(req, **k):
        enviado["url"] = req.full_url
        enviado["body"] = __import__("json").loads(req.data.decode("utf-8"))
        return _Resp()

    monkeypatch.setattr(main, "_supa_rest_service", _svc)
    monkeypatch.setattr(main, "_supabase_insert", lambda t, r: True)
    monkeypatch.setattr(main, "_supa_log", lambda *a, **k: None)
    monkeypatch.setattr(main, "_get_user_from_request",
                        lambda r: {"id": "u1", "email": "x@y.com"})
    # 🪤 regra dura nº2: sem o dono dublado a rota morre no 401 antes da marca
    monkeypatch.setattr(main, "_require_project_owner", lambda r, j: None)
    monkeypatch.setattr(_ur, "urlopen", _urlopen)
    main.submit_item_review(
        "job00001", "22222222-2222-4222-8222-222222222222",
        main.ReviewPayload(action="edit", reviewed_by="x@y.com", comment="",
                           edits={"quantity": quantidade_nova, "unit": "m²"}),
        type("R", (), {"headers": {}})())
    assert "body" in enviado, "a rota não chegou a gravar o item"
    return enviado["body"]


def test_a_marca_da_CORRECAO_do_cliente_nao_come_o_fim(monkeypatch):
    """🩸 22/09/2026 (revisão): o 14º ponto que antepõe aviso, e o único fora do
    motor. A rota lê a observação DO BANCO — já no teto — e somava a marca
    "QUANTIDADE CORRIGIDA POR VOCÊ" cortando `[:1000]`: ia embora justamente a
    procedência que a leitura gravou no fim. 📏 90 d: 126 correções de
    quantidade, 4 delas sobre observação de ≥ 945 caracteres."""
    gravado = _grava_correcao_do_cliente(monkeypatch, _obs_longa())
    _confere(gravado["observations"], "✏️ QUANTIDADE CORRIGIDA POR VOCÊ")
    assert gravado["confidence"] == "estimado", (
        "regra dura nº1: número digitado pelo cliente não é medida do CAD")


def test_CONTROLE_observacao_curta_do_cliente_sai_inteira(monkeypatch):
    """🧪 O outro lado: cabendo no teto, nada é cortado e não há emenda —
    prova de que a emenda do teste acima veio do cenário, não da função."""
    curta = "Fonte: área hachurada do layer PISO-01."
    gravado = _grava_correcao_do_cliente(monkeypatch, curta)
    assert gravado["observations"].endswith(curta), gravado["observations"]
    assert main._OBS_EMENDA not in gravado["observations"], gravado["observations"]


def test_o_MERGE_nao_come_o_fim_da_observacao_que_ja_estava_gravada(monkeypatch):
    """O merge copia linhas JÁ gravadas (≤ 1000) e antepõe o rebaixamento da
    regra nº1 — o `[:1000]` comia o fim que a leitura de origem gravou."""
    import _merge_bancada as _mb
    procedencia = "Fonte: texto do carimbo da prancha: 'AREA TOTAL = 264,54 m2'. "
    projetos = {
        "aa11bb22": {"job_id": "aa11bb22", "user_id": "u-cliente-01",
                     "user_email": "cliente-01@example.com", "user_name": "Cliente Um",
                     "project_name": "Obra do cliente-01", "status": "done",
                     "typology": "office", "project_type": "arquitetura",
                     "created_at": "2026-08-20T19:37:48+00", "warnings": []},
        "ev597afa": {"job_id": "ev597afa", "parent_job_id": "aa11bb22", "is_eval": True,
                     "status": "done", "user_id": "eval", "warnings": [],
                     "project_name": "[TESTE] Obra do cliente-01 — avaliação",
                     "created_at": "2026-08-24T19:37:48+00"}}
    pai = _mb.itens("ARQ-01", 8, 4, rotulo="orig") + _mb.itens("EL-02", 8, 2, rotulo="orig")
    for desc in ("Piso — revestimento de piso interno", "Forro — placa mineral removivel"):
        pai.append(_mb.item("ARQ-01", descricao=desc, confidence="confirmado", unit="m²",
                            quantity=200.0, observations=_obs_longa(procedencia)))
    filho = _mb.itens("ARQ-01", 10, 3, rotulo="rel") + _mb.itens("EL-02", 8, 5, rotulo="rel")
    b = _mb.Banco(projetos, {"aa11bb22": pai, "ev597afa": filho})
    _mb.instalar(monkeypatch, b)
    r = main.admin_merge_criar("ev597afa", _mb.Req())
    gravadas = {str(x.get("description")): x for x in b.itens_do(r["job_id"])}
    for desc in ("Piso — revestimento de piso interno", "Forro — placa mineral removivel"):
        obs = str(gravadas[desc]["observations"])
        assert obs.startswith("⚠ ESTIMADO — este número foi LIDO"), obs[:120]
        assert _FIM.strip(" |") in obs, "o merge comeu o fim da observação: ...%r" % obs[-200:]
        assert main._OBS_EMENDA in obs, "o cenário não passou de 1000 — não prova nada"
