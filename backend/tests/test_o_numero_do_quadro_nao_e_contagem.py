# -*- coding: utf-8 -*-
"""O número ESCRITO num quadro do desenho não sai ✓ MEDIDO só porque a
observação também cita uma contagem.

🩸 12/10/2026 — achado na revisão da seção QUADROS COM QUANTIDADE, antes de ela
subir. A seção manda a IA ficar com a quantidade do quadro, marcar 'estimado' e
citar a contagem do desenho. Se a IA marca 'confirmado' assim mesmo, a rede de
procedência (`selos_sem_geometria`) não rebaixa: "contagem de blocos", "bloco
'X' = 13 un", "13 inserções do bloco", "seção ESQUADRIAS … 13 un" e "hachura"
são prova de geometria e passam na frente da palavra "quadro". A linha saía
com 12 (o número do projetista), selo de medido, e a observação dizendo que a
contagem deu 13.

A régua (`selo_apos_numero_do_quadro`) usa o que o motor LEU, não a redação da
IA, e só rebaixa com as três juntas:
  (a) a linha está 'confirmado' e a observação cita "quadro" (não o de aço);
  (b) a quantidade é a de alguma linha dos quadros lidos neste arquivo, em 2
      casas;
  (c) nenhuma geometria citada dá o MESMO número (contagem do bloco fonte, ou
      layer medido).
Quadro e desenho batendo, o ✓ fica. Sem quadro lido, a régua não mexe em nada.

🪤 Nomes e layers FICTÍCIOS (repositório público, regra nº6).
"""
import ast
import importlib.util
import io
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import engine_rules as E  # noqa: E402

_MAIN_PY = os.path.join(os.path.dirname(_AQUI), "main.py")
QUADRO = [2.0, 5.0, 12.0, 148.5, 1250.0]          # as quantidades lidas nos quadros do arquivo
BLOCOS = {"PX6": 13, "JX2": 5, "LUM-A": 30}       # a contagem de blocos do mesmo arquivo
INDICE = {"comprimento": [], "area": [("COB-TELHA", 151.2)], "contagem": []}

#: do jeito que a seção pede que a IA escreva — o quadro diz 12, o desenho 13
FUROS = [
    "Quantidade do quadro de esquadrias: 12. Contagem de blocos: bloco 'PX6' = 13 un (inclui o desenho de detalhe).",
    "QUADRO 1: 12 un. Na contagem de blocos, bloco 'PX6': 13 un.",
    "Quantidade 12 do QUADRO 2; 13 inserções do bloco PX6 no arquivo.",
    "Quadro de esquadrias: 12 un. Seção ESQUADRIAS do desenho: PX6 13 un.",
    "Quantidade do quadro (12). A contagem geométrica dos blocos deu 13.",
]


def regua(obs, q=12.0, unit="un", conf="confirmado", quantidades=QUADRO, blocos=BLOCOS, indice=INDICE):
    return E.selo_apos_numero_do_quadro(conf, obs, q, unit, quantidades, blocos, indice)


# ── o furo ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("obs", FUROS)
def test_o_numero_do_quadro_com_a_contagem_citada_nao_sai_medido(obs):
    # o furo existe: a rede de procedência deixa passar
    assert E.selos_sem_geometria([{"confidence": "confirmado", "observations": obs, "unit": "un",
                                   "quantity": 12.0, "origem": "dxf_geom"}]) == []
    conf, nova, rebaixou = regua(obs)
    assert (conf, rebaixou) == ("estimado", True)
    assert nova.startswith(E.MARCA_NUMERO_DO_QUADRO + " — é a quantidade que o projetista escreveu no quadro; "
                           "a contagem do desenho deu outro valor ou não foi citada. ")
    assert nova.endswith(obs), "a observação da IA tem de ficar inteira depois do aviso"


def test_so_o_quadro_citado_tambem_nao_sai_medido():
    conf, nova, rebaixou = regua("QUADRO 1: QTD 12 ← Ref.: PX6 | Tipo: de abrir | Dimensões (cm): 170 x 215")
    assert (conf, rebaixou) == ("estimado", True) and E.MARCA_NUMERO_DO_QUADRO in nova


def test_em_metro_quadrado_o_layer_com_outro_valor_nao_segura_o_selo():
    obs = "Quadro de cobertura: 148,50 m². Hachura do layer 'COB-TELHA' = 151,20 m²."
    assert regua(obs, q=148.5, unit="m²")[2] is True


# ── quando o desenho dá o MESMO número, é medida ───────────────────────────

def test_CONTROLE_quadro_e_contagem_batendo_o_selo_fica():
    for obs in ("Quadro de esquadrias: 13 un; bloco 'PX6' = 13 un.",
                "Fonte: 13 inserções do bloco 'PX6'. Confere com o quadro de esquadrias (13)."):
        assert regua(obs, q=13.0, quantidades=QUADRO + [13.0]) == ("confirmado", obs, False), obs


def test_CONTROLE_o_layer_medido_com_o_mesmo_valor_segura_o_selo():
    obs = "Quadro de cobertura: 148,50 m². Hachura do layer 'COB-TELHA' = 148,50 m²."
    igual = {"comprimento": [], "area": [("COB-TELHA", 148.5)], "contagem": []}
    assert regua(obs, q=148.5, unit="m²", indice=igual) == ("confirmado", obs, False)
    assert regua(obs, q=148.5, unit="m²", indice=INDICE)[2] is True          # o layer mede 151,20: rebaixa
    # o layer tem de ser o CITADO: o mesmo número noutro layer é acaso
    outro = {"comprimento": [], "area": [("PISO-GERAL", 148.5)], "contagem": []}
    assert regua(obs, q=148.5, unit="m²", indice=outro)[2] is True


def test_CONTROLE_a_contagem_citada_sem_a_palavra_bloco_tambem_segura():
    """🪤 A seção ESQUADRIAS do prompt lista "nome: N un", e a IA cita assim —
    sem escrever "bloco". "1" e "2" são linha de quase todo quadro: rebaixar
    essa contagem e dizer ao cliente que ela é "do quadro" seria o erro caro."""
    obs = ("Fonte: seção ESQUADRIAS — 'JX2: 5 un | ~1,20m × 1,00m = 1,20 m²'. "
           "Confirmar quadro de esquadrias completo em projeto executivo.")
    assert regua(obs, q=5.0) == ("confirmado", obs, False)
    assert regua(obs.replace("5 un", "6 un"), q=6.0, quantidades=QUADRO + [6.0])[2] is True     # o JX2 tem 5


def test_CONTROLE_a_familia_do_bloco_conta_pela_soma_dos_tipos():
    """O prompt mostra a RAIZ do nome ("Porta Lisa"), com a soma das inserções
    de todos os tipos; é esse nome e esse número que a IA cita."""
    familia = {"Porta Lisa - Tipo A-1234567-Planta Baixa": 3, "Porta Lisa - Tipo A-1234568-Planta Baixa": 2,
               "PX6": 13}
    obs = "Fonte: Porta Lisa = 5 un no desenho; confere com o quadro de esquadrias."
    assert regua(obs, q=5.0, blocos=familia) == ("confirmado", obs, False)
    assert regua(obs, q=5.0, blocos={"PX6": 13})[2] is True                    # sem a família no desenho
    estranho = {"PX6": "treze"}                                               # contagem que não é número
    assert regua(FUROS[0], blocos=estranho)[2] is True


def test_CONTROLE_contagem_so_vale_em_unidade_de_peca():
    """Em m² o número igual à contagem de um bloco é acaso, não prova."""
    obs = "Quadro de cobertura: 13,00 m²; bloco 'PX6' = 13 un."
    assert regua(obs, q=13.0, unit="m²", quantidades=[13.0])[2] is True
    assert regua(obs, q=13.0, unit="un", quantidades=[13.0])[2] is False


def test_so_o_bloco_FONTE_da_linha_segura_o_selo():
    """A linha tira o número do quadro (12) e cita de passagem um bloco que por
    acaso tem 12: quem conta é o bloco fonte (o 1º citado), que deu 13."""
    obs = "Fonte: bloco 'PX6' = 13 un; quadro de esquadrias diz 12. Bloco 'OUTRO' também tem 12."
    assert regua(obs, blocos=dict(BLOCOS, OUTRO=12))[2] is True


# ── (a), (b): quem a régua não toca ────────────────────────────────────────

def test_CONTROLE_sem_citar_quadro_a_regua_nao_toca():
    obs = "Contagem de blocos: bloco 'JX2' = 5 un."
    assert regua(obs, q=5.0) == ("confirmado", obs, False)
    obs = "12 un conforme a tabela de esquadrias; bloco 'PX6' = 13 un."      # "tabela" não é a palavra
    assert regua(obs) == ("confirmado", obs, False)
    assert regua("enquadrou 12 un no esquadro; bloco 'PX6' = 13 un")[2] is False   # palavra inteira


def test_CONTROLE_quantidade_que_nao_e_de_quadro_nenhum_a_regua_nao_toca():
    obs = "Quadro de esquadrias cita o tipo; bloco 'LUM-A' = 30 un."
    assert regua(obs, q=30.0) == ("confirmado", obs, False)
    assert regua(FUROS[0], q=7.0)[2] is False


def test_CONTROLE_linha_que_ja_esta_estimada_ou_zerada_fica_como_esta():
    assert regua(FUROS[0], conf="estimado") == ("estimado", FUROS[0], False)
    assert regua(FUROS[0], q=0.0)[2] is False
    assert regua(FUROS[0], q=None)[2] is False
    assert regua(FUROS[0], q="doze")[2] is False


def test_CONTROLE_o_quadro_de_aco_tem_a_excecao_dele():
    obs = "Peso conforme quadro de aço da prancha: CA-50 Ø10 = 148,50 kg."
    assert regua(obs, q=148.5, unit="kg") == ("confirmado", obs, False)
    assert regua("Peso conforme quadro de cargas: 148,50 kg.", q=148.5, unit="kg")[2] is True   # controle


def test_SEM_quadro_lido_a_regua_nao_mexe_em_linha_nenhuma():
    """Sem chave própria: o registro só existe com QUADRO_COM_QUANTIDADE ligada,
    e sem ele não há quantidade pra comparar — mesmo citando "quadro"."""
    for vazio in ([], None, ()):
        for obs in FUROS:
            assert regua(obs, quantidades=vazio) == ("confirmado", obs, False)
    assert E.quantidades_dos_quadros(None) == [] and E.quantidades_dos_quadros({}) == []
    assert E.quantidades_dos_quadros({"quadros": []}) == [] and E.quantidades_dos_quadros({"nao_lidos": [{}]}) == []
    assert E.quantidades_dos_quadros("lixo") == [] and E.quantidades_dos_quadros({"quadros": [None, 3]}) == []


# ── (b): o número como o projetista escreve ────────────────────────────────

def test_o_numero_escrito_no_quadro():
    le = E.numero_escrito_no_quadro
    assert [le(s) for s in ("12", "12 un", "12,00", " 03 unid.", "12.5")] == [12.0, 12.0, 12.0, 3.0, 12.5]
    assert le("148,50 m²") == 148.5 and le("1.250") == 1250.0 and le("2.404,96") == 2404.96
    assert le("10.000") == 10000.0 and le("1.25") == 1.25
    for nao in ("V", "*ver projeto*", "ver projeto", "2 x 3", "12 a 15", "IND.", "___", "", None, "0", "00", "0,00"):
        assert le(nao) is None, nao


def test_as_quantidades_dos_quadros_saem_sem_repeticao_e_sem_o_que_nao_e_numero():
    reg = {"quadros": [{"linhas": [{"q": "12"}, {"q": "12,00"}, {"q": "V"}, {"q": None}, {"q": "1.250"}]},
                       {"linhas": [{"q": "148,50 m²"}, {"q": "12 un"}, {"q": "0"}]}],
           "nao_lidos": [{"colunas": ["QTD"], "motivo": "x"}]}
    assert E.quantidades_dos_quadros(reg) == [12.0, 148.5, 1250.0]


def test_a_comparacao_e_no_arredondamento_da_planilha():
    obs = "Quadro de cobertura: ver linha; hachura do layer 'COB-TELHA' = 151,20 m²."
    assert regua(obs, q=148.504, unit="m²")[2] is True            # 148,50 na planilha
    assert regua(obs, q=148.496, unit="m²")[2] is True
    assert regua(obs, q=148.51, unit="m²")[2] is False            # 148,51 é outro número
    assert regua(obs, q=148.49, unit="m²")[2] is False
    assert regua(FUROS[0], q=1250.0, quantidades=[1250.0])[2] is True
    assert regua(FUROS[0], q=1.25, quantidades=[1250.0])[2] is False


# ── do DXF ao número: o registro que o leitor grava ────────────────────────

def test_do_desenho_ate_a_regua(tmp_path):
    """Um quadro desenhado de verdade (o mesmo construtor dos testes do
    leitor): as quantidades saem do registro do `extract_dxf`."""
    spec = importlib.util.spec_from_file_location(
        "quadro_base", os.path.join(_AQUI, "test_quadro_com_quantidade.py"))
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    d = base.Desenho()
    base.tabela(d, 0, 100, base.LARG, base.CAB, base.LINHAS)
    reg = base.registro(tmp_path, d)
    qs = E.quantidades_dos_quadros(reg)
    assert qs == [2.0, 5.0, 12.0], qs
    assert regua("QUADRO 1: 12 un; bloco 'PX6' = 13 un", quantidades=qs)[2] is True
    assert regua("QUADRO 1: 13 un; bloco 'PX6' = 13 un", q=13.0, quantidades=qs)[2] is False


# ── ponta a ponta: nada devolve o ✓ depois ─────────────────────────────────

def _passa_pelas_redes(obs, q, unit, quantidades, blocos, indice):
    """A ordem do process_job: a régua, a rede de procedência, a chave que promove."""
    conf, obs2, _ = E.selo_apos_numero_do_quadro("confirmado", obs, q, unit, quantidades, blocos, indice)
    it = {"confidence": conf, "observations": obs2, "unit": unit, "quantity": q, "origem": "dxf_geom",
          "description": "Item do quadro"}
    if E.selos_sem_geometria([it]):
        it["confidence"] = "estimado"
    if E.selo_com_prova_da_geometria([it], indice):
        it["confidence"] = "confirmado"
    return it["confidence"]


@pytest.mark.parametrize("obs", [
    "Quadro de esquadrias: 12 un. Contagem de blocos: bloco 'PX6' = 13 un.",          # o quadro primeiro
    "Contagem de blocos: bloco 'PX6' = 13 un. Quantidade adotada: 12, do quadro.",    # a contagem primeiro
])
def test_ponta_a_ponta_a_contagem_diferente_termina_estimada_nas_duas_ordens(obs):
    assert _passa_pelas_redes(obs, 12.0, "un", QUADRO, BLOCOS, INDICE) == "estimado"


@pytest.mark.parametrize("obs", [
    "Quadro de cobertura: 148,50 m². Hachura do layer 'COB-TELHA' = 151,20 m².",
    "Hachura do layer 'COB-TELHA' = 151,20 m². Quantidade do quadro de cobertura: 148,50 m².",
])
def test_ponta_a_ponta_o_layer_diferente_termina_estimado_nas_duas_ordens(obs):
    assert _passa_pelas_redes(obs, 148.5, "m²", QUADRO, BLOCOS, INDICE) == "estimado"


@pytest.mark.parametrize("obs", [
    "Quadro de esquadrias: 13 un; bloco 'PX6' = 13 un.",
    "Bloco 'PX6' = 13 un; confere com o quadro de esquadrias (13).",
])
def test_ponta_a_ponta_CONTROLE_batendo_termina_confirmada_nas_duas_ordens(obs):
    assert _passa_pelas_redes(obs, 13.0, "un", QUADRO + [13.0], BLOCOS, INDICE) == "confirmado"


def test_a_chave_que_promove_respeita_a_marca():
    """A linha rebaixada pela régua não volta a ✓ nem que um layer citado
    passe a medir o mesmo número: a marca é de rebaixamento."""
    assert E.MARCA_NUMERO_DO_QUADRO in E.MARCAS_DE_REBAIXAMENTO
    obs = E.MARCA_NUMERO_DO_QUADRO + " — … Quadro: 148,50 m². Hachura do layer 'COB-TELHA' = 148,50 m²."
    igual = {"comprimento": [], "area": [("COB-TELHA", 148.5)], "contagem": []}
    it = {"confidence": "estimado", "observations": obs, "unit": "m²", "quantity": 148.5, "origem": "dxf_geom"}
    assert E.selo_com_prova_da_geometria([it], igual) == []
    sem_marca = dict(it, observations=obs.replace(E.MARCA_NUMERO_DO_QUADRO, "Nota"))
    assert len(E.selo_com_prova_da_geometria([sem_marca], igual)) == 1          # controle


# ── o LAÇO de produção, rodado de verdade ──────────────────────────────────

def _item(obs, q=12.0, unit="un", conf="confirmado", desc="Porta de abrir PX6 — fornecimento e instalação"):
    return {"item_num": "1", "description": desc, "unit": unit, "quantity": q, "confidence": conf,
            "observations": obs}


def _laco(itens, **extra):
    from test_medicao_estava_na_observacao import _laco_de_itens_de_producao
    saida, _esc, _logs = _laco_de_itens_de_producao(itens, areas={}, compr=extra.pop("compr", {}), extra=extra)
    return saida


def test_o_laco_de_producao_rebaixa_a_linha_do_quadro():
    (it,) = _laco([_item(FUROS[0])], _quadros_q=[2.0, 12.0], _blocos_n={"PX6": 13})
    assert it.confidence.value == "estimado", it.observations
    assert it.observations.startswith(E.MARCA_NUMERO_DO_QUADRO), it.observations
    assert it.quantity == 12.0, "a régua só rebaixa: a quantidade fica"


def test_CONTROLE_o_laco_sem_quadro_lido_nao_mexe():
    (it,) = _laco([_item(FUROS[0])], _blocos_n={"PX6": 13})
    assert E.MARCA_NUMERO_DO_QUADRO not in it.observations and it.confidence.value == "confirmado", it.observations


def test_CONTROLE_o_laco_com_a_contagem_batendo_nao_mexe():
    obs = "Fonte: 13 INSERTs do bloco 'PX6'. Confere com o quadro de esquadrias (13)."
    (it,) = _laco([_item(obs, q=13.0)], _quadros_q=[2.0, 12.0, 13.0], _blocos_n={"PX6": 13})
    assert E.MARCA_NUMERO_DO_QUADRO not in it.observations and it.confidence.value == "confirmado", it.observations


def _cats_do_cross_check():
    import _executa
    esc = {}
    _executa.roda("process_job", "_AREA_CATS = {", esc)
    _executa.roda("process_job", "_LEN_CATS = {", esc)
    return {"_AREA_CATS": esc["_AREA_CATS"], "_LEN_CATS": esc["_LEN_CATS"]}


_OBS_PAREDE = "Quadro de alvenarias: 347,90 m. Comprimento do layer 'A-WALL' = 351,00 m."


def test_com_o_cross_check_ligado_a_linha_rebaixada_pela_regua_nao_volta(monkeypatch):
    """O número do quadro (347,90) por acaso é uma medida dura da categoria: o
    cross-check promoveria — a linha rebaixada pela régua fica rebaixada."""
    monkeypatch.setenv("DXF_CONFIRM_CROSSCHECK", "1")
    (it,) = _laco([_item(_OBS_PAREDE, q=347.9, unit="ml", desc="Parede de alvenaria")],
                  compr={"A-WALL": 351.0}, _quadros_q=[347.9],
                  _hard_len_by_cat={"paredes": {347.9}}, **_cats_do_cross_check())
    assert it.confidence.value == "estimado" and E.MARCA_NUMERO_DO_QUADRO in it.observations, it.observations


def test_CONTROLE_com_o_cross_check_ligado_e_sem_quadro_a_mesma_linha_estimada_sobe(monkeypatch):
    """Prova que o controle de cima depende da régua: sem quadro lido, a mesma
    linha (estimada pela IA) é promovida pelo cross-check."""
    monkeypatch.setenv("DXF_CONFIRM_CROSSCHECK", "1")
    (it,) = _laco([_item(_OBS_PAREDE, q=347.9, unit="ml", conf="estimado", desc="Parede de alvenaria")],
                  compr={"A-WALL": 351.0}, _hard_len_by_cat={"paredes": {347.9}}, **_cats_do_cross_check())
    assert it.confidence.value == "confirmado", it.observations


# ── o motor CONSULTA (pontos de chamada, pela AST) ─────────────────────────

def _process_job():
    arv = ast.parse(io.open(_MAIN_PY, encoding="utf-8").read())
    fn = next((n for n in ast.walk(arv)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "process_job"), None)
    assert fn is not None, "não achei o process_job"
    return fn


def _nome_chamado(no):
    return getattr(no.func, "id", getattr(no.func, "attr", "")) if isinstance(no, ast.Call) else ""


def test_o_process_job_passa_a_linha_pela_regua_antes_da_chave():
    fn = _process_job()
    chamadas = [no for no in ast.walk(fn) if _nome_chamado(no) == "_regra_quadro"]
    assert len(chamadas) == 1, "o process_job não chama a régua do número do quadro (ou chama mais de uma vez)"
    c = chamadas[0]
    assert [getattr(a, "id", None) for a in c.args] == [
        "conf", "obs_raw", "qty", "normalized_unit", "_quadros_q", "_blocos_n", "_indice_geom"]
    # o resultado volta pra linha: (conf, obs_raw, …) = régua(…)
    atrib = [no for no in ast.walk(fn) if isinstance(no, ast.Assign) and no.value is c]
    assert atrib and [getattr(t, "id", None) for t in atrib[0].targets[0].elts][:2] == ["conf", "obs_raw"]
    # é a régua de verdade, pelo nome
    imp = [a for no in ast.walk(fn) if isinstance(no, ast.ImportFrom) and no.module == "engine_rules"
           for a in no.names if a.asname == "_regra_quadro"]
    assert [a.name for a in imp] == ["selo_apos_numero_do_quadro"]
    # e roda antes da chave que promove (senão a promoção viria antes do rebaixamento)
    chave = [no.lineno for no in ast.walk(fn) if _nome_chamado(no) == "_chave_selo"]
    assert chave and c.lineno < min(chave)


def test_a_linha_rebaixada_pela_regua_fica_marcada_pro_cross_check_nao_devolver_o_selo():
    """🪤 Depois das réguas vem o CROSS-CHECK, que promove 'estimado' quando a
    quantidade bate com uma medida dura da categoria — e só respeita a linha
    marcada com `_rebaixado_pela_fonte`. Sem a marca, o m² do quadro que por
    acaso bate com um layer voltaria a ✓."""
    fn = _process_job()
    regua_ln = next(no.lineno for no in ast.walk(fn) if _nome_chamado(no) == "_regra_quadro")
    marca = [no for no in ast.walk(fn) if isinstance(no, ast.If)
             and isinstance(no.test, ast.Name) and no.test.id == "_era_quadro"]
    assert len(marca) == 1, "ninguém olha se a régua do quadro rebaixou"
    alvo = [(getattr(t, "id", ""), getattr(a.value, "value", None)) for a in marca[0].body
            if isinstance(a, ast.Assign) for t in a.targets]
    assert alvo == [("_rebaixado_pela_fonte", True)], alvo
    cross = [no.lineno for no in ast.walk(fn) if isinstance(no, ast.If)
             and any(isinstance(d, ast.Name) and d.id == "_XCHECK_ON" for d in ast.walk(no.test))]
    assert cross, "sumiu o cross-check do process_job — o guarda perdeu o alvo"
    assert regua_ln < marca[0].lineno < min(cross)


def test_as_quantidades_vem_do_registro_dos_quadros_do_arquivo():
    fn = _process_job()
    atrib = [no for no in ast.walk(fn) if isinstance(no, ast.Assign)
             and any(getattr(t, "id", "") == "_quadros_q" for t in no.targets)]
    assert len(atrib) == 2, "eram 2: a leitura do registro e a lista vazia do except"
    le = next(no for no in atrib if isinstance(no.value, ast.Call))
    assert _nome_chamado(le.value) == "_qtd_quadros"
    assert "quadros_com_quantidade" in {d.value for d in ast.walk(le.value) if isinstance(d, ast.Constant)}
    vazio = next(no for no in atrib if not isinstance(no.value, ast.Call))
    assert isinstance(vazio.value, ast.List) and vazio.value.elts == []
    imp = [a for no in ast.walk(fn) if isinstance(no, ast.ImportFrom) and no.module == "engine_rules"
           for a in no.names if a.asname == "_qtd_quadros"]
    assert [a.name for a in imp] == ["quantidades_dos_quadros"]
