# -*- coding: utf-8 -*-
"""O arquivo do Financeiro sai com o SELO da quantidade — regra dura nº1.

🩸 O QUE ESTAVA ERRADO (achado nº9 da auditoria de 06/09/2026):
`financeiro.html` deixa o arquiteto lançar uma despesa a partir de um item do
quantitativo. A linha guarda `origem_quantidade` e `origem_unidade` — "819 m² de
alvenaria" — e o `.xlsx`/PDF saía com esse número e NADA dizendo se ele foi
medido do desenho ou estimado pelo motor. Esse arquivo vai pro FORNECEDOR e pro
BANCO. Medido em 07/09/2026 na base: **9.518 itens laranja** (estimados) e ZERO
lançamentos — dava pra consertar antes do primeiro cliente usar.

O que este guarda prova, EXECUTANDO o export (nunca lendo o fonte):
  1. item medido    → sai "Medido do CAD";
  2. item estimado  → NÃO sai como medido, e o texto avisa pra conferir;
  3. referência que não achou item → "Não confirmado", o terceiro estado —
     `origem_ref_id` não tem FK, então depois de um reprocesso a referência fica
     pendurada e a resposta honesta é "não deu pra conferir";
  4. linha digitada à mão (sem `origem_ref_id`) → selo VAZIO: não há quantidade
     nossa pra carimbar, e "não confirmado" ali sugeriria falha nossa;
  5. a legenda do selo entra no arquivo quando existe alguma linha com selo;
  6. 🪤 as datas continuam saindo como DATA. Os índices de coluna eram números
     cravados na mão (`i in (7, 10)`); inserir SELO no meio moveria VENCIMENTO e
     PAGO EM sem erro nenhum e elas sairiam como 46296 na planilha.

🧪 Controle positivo (o guarda prova que REPROVA) em
`test_o_guarda_do_selo_reprova_de_verdade`.
"""
import datetime
import io
import os
import re
import sys
import tempfile

import pytest
from openpyxl import load_workbook

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from financeiro_export import (  # noqa: E402
    FMT_DATA, FMT_MOEDA, SELO_LABEL, SELO_NOTA, _esc, montar_dados_export,
    montar_html_financeiro, gerar_financeiro_xlsx,
)

#: 🪤 O TEXTO DO SELO APARECE DUAS VEZES NO PDF: no carimbo de cada linha E na
#: legenda que explica os três estados. Procurar "Medido do CAD" no documento
#: inteiro acha a LEGENDA e passa mesmo com todos os carimbos errados — foi
#: exatamente o que este arquivo fez na primeira escrita. `_selos_do_pdf` lê só
#: os carimbos. (E a legenda sai ESCAPADA: comparar com `_esc(...)`.)
_RE_BADGE = re.compile(r'<span class="selo (\w+)">(.*?)</span>')


def _selos_do_pdf(html):
    """[(classe, texto)] de cada carimbo de linha — nunca da legenda."""
    return _RE_BADGE.findall(html)

HOJE = datetime.date(2026, 9, 7)

# Uma linha de cada estado. Os ref_id são UUID de verdade porque o backend só
# consulta o que tem forma de UUID (o resto vira "não confirmado" de propósito).
REF_MEDIDO = "11111111-1111-4111-8111-111111111111"
REF_ESTIMADO = "22222222-2222-4222-8222-222222222222"
REF_SUMIU = "33333333-3333-4333-8333-333333333333"

ROWS = [
    {"categoria": "Alvenaria", "descricao": "Bloco ceramico 14 cm", "origem": "quantitativo",
     "origem_ref_id": REF_MEDIDO, "origem_quantidade": 819.0, "origem_unidade": "m2",
     "valor": 12000.0, "status": "contratado", "venc_tipo": "data", "venc_data": "2026-10-01"},
    {"categoria": "Alvenaria", "descricao": "Argamassa de assentamento", "origem": "quantitativo",
     "origem_ref_id": REF_ESTIMADO, "origem_quantidade": 40.0, "origem_unidade": "m3",
     "valor": 3000.0, "status": "pago", "pago_em": "2026-09-02"},
    {"categoria": "Alvenaria", "descricao": "Item de projeto reprocessado", "origem": "quantitativo",
     "origem_ref_id": REF_SUMIU, "origem_quantidade": 10.0, "origem_unidade": "un",
     "valor": 900.0, "status": "cotado"},
    {"categoria": "Extras", "descricao": "Frete digitado a mao", "origem": "livre",
     "valor": 150.0, "status": "cotado"},
]
# O que o backend teria achado em `project_items`: o terceiro ref não está aqui.
SELOS = {REF_MEDIDO: "confirmado", REF_ESTIMADO: "estimado"}


def _dados(selos=SELOS, rows=None):
    return montar_dados_export(rows if rows is not None else ROWS, [], HOJE, selos=selos)


def _por_descricao(dados):
    return {l["descricao"]: l for g in dados["grupos"] for l in g["linhas"]}


def _xlsx(dados):
    """Gera o .xlsx de verdade e devolve a planilha aberta."""
    caminho = os.path.join(tempfile.mkdtemp(prefix="fin_selo_"), "financeiro.xlsx")
    gerar_financeiro_xlsx(dados, caminho, {"project_name": "Obra de teste"})
    with open(caminho, "rb") as fh:
        return load_workbook(io.BytesIO(fh.read()))


def _linhas_do_xlsx(ws):
    """[(cabecalho -> valor da celula)] só das linhas de lançamento."""
    cab, saida = None, []
    for linha in ws.iter_rows():
        vals = [c.value for c in linha]
        if not cab:
            if vals and str(vals[0] or "").strip() in ("Nº", "N°", "No"):
                cab = [str(v or "").strip() for v in vals]
            continue
        if isinstance(vals[0], int):        # linha de lançamento (numerada)
            saida.append(dict(zip(cab, linha)))
    return saida


# ══════════════════════════════════════════════════════════════════════════
#  1-4 · os quatro estados, na estrutura que alimenta planilha E PDF
# ══════════════════════════════════════════════════════════════════════════
def test_os_quatro_estados_do_selo():
    linhas = _por_descricao(_dados())

    medido = linhas["Bloco ceramico 14 cm"]
    assert medido["selo"] == SELO_LABEL["confirmado"], \
        "item medido do CAD tem que sair dito como medido"
    assert medido["selo_key"] == "medido"

    est = linhas["Argamassa de assentamento"]
    assert est["selo_key"] == "estimado"
    assert est["selo"] != SELO_LABEL["confirmado"], \
        "🚨 regra nº1: item ESTIMADO saindo como medido do CAD"
    assert "confira" in est["selo"].lower(), \
        "o selo do estimado tem que MANDAR conferir, não só deixar de afirmar"

    # 🪤 o terceiro estado: a referência existe, o item não. `origem_ref_id` não
    # tem FK — depois de um reprocesso os itens renascem com UUID novo.
    sumiu = linhas["Item de projeto reprocessado"]
    assert sumiu["selo_key"] == "nao_confirmado"
    assert sumiu["selo"] == SELO_LABEL[""]
    assert sumiu["selo"] != SELO_LABEL["confirmado"], \
        "🚨 referência pendurada NÃO pode virar 'medido do CAD'"
    assert sumiu["selo"] != est["selo"], \
        "'não deu pra conferir' é diferente de 'estimado' — dois estados, dois textos"

    livre = linhas["Frete digitado a mao"]
    assert livre["selo"] == "" and livre["selo_key"] == "", \
        "linha digitada à mão não tem quantidade nossa: selo vazio, não 'não confirmado'"


def test_sem_nenhum_selo_lido_ninguem_vira_medido():
    """O backend falha ABERTO: se `project_items` não responde, `selos` vem {}.

    Nesse dia o arquivo ainda sai — mas nenhuma linha pode dizer "medido".
    """
    linhas = _por_descricao(_dados(selos={}))
    for desc, l in linhas.items():
        assert l["selo"] != SELO_LABEL["confirmado"], \
            f"🚨 sem conseguir ler os selos, '{desc}' saiu como MEDIDO DO CAD"
    assert linhas["Bloco ceramico 14 cm"]["selo_key"] == "nao_confirmado"


# ══════════════════════════════════════════════════════════════════════════
#  5 · o arquivo de verdade: .xlsx
# ══════════════════════════════════════════════════════════════════════════
def test_xlsx_tem_a_coluna_selo_preenchida():
    ws = _xlsx(_dados()).active
    linhas = _linhas_do_xlsx(ws)
    assert len(linhas) == 4, f"esperava 4 lançamentos na planilha, vieram {len(linhas)}"
    assert "SELO" in linhas[0], "a planilha saiu SEM a coluna SELO"

    por_item = {str(l["ITEM"].value): l for l in linhas}
    assert por_item["Bloco ceramico 14 cm"]["SELO"].value == SELO_LABEL["confirmado"]
    assert por_item["Argamassa de assentamento"]["SELO"].value != SELO_LABEL["confirmado"]
    assert por_item["Item de projeto reprocessado"]["SELO"].value == SELO_LABEL[""]
    assert por_item["Frete digitado a mao"]["SELO"].value in (None, "")


def test_xlsx_traz_a_legenda_do_selo():
    """Quem recebe a planilha nunca viu o site: a explicação vai DENTRO dela."""
    ws = _xlsx(_dados()).active
    texto = "\n".join(str(c.value) for linha in ws.iter_rows() for c in linha if c.value)
    assert "SELO" in texto and "Medido do CAD" in texto
    # a legenda inteira, não só a palavra
    assert SELO_NOTA[:60] in texto, "a planilha saiu sem a legenda que explica o selo"


def test_planilha_sem_linha_com_selo_nao_ganha_legenda():
    """Documento só de linhas digitadas à mão não explica coluna que está vazia."""
    so_livre = [dict(ROWS[3])]
    ws = _xlsx(_dados(rows=so_livre)).active
    texto = "\n".join(str(c.value) for linha in ws.iter_rows() for c in linha if c.value)
    assert SELO_NOTA[:60] not in texto


def test_as_datas_continuam_saindo_como_data():
    """🪤 O conserto que quase entrou quebrado.

    Os índices de coluna eram números cravados (`i in (7, 10)`). Inserir SELO na
    posição 5 empurra VENCIMENTO e PAGO EM uma casa — sem erro, sem aviso: as
    datas sairiam como 46296 no arquivo que vai pro banco.
    """
    linhas = _linhas_do_xlsx(_xlsx(_dados()).active)
    por_item = {str(l["ITEM"].value): l for l in linhas}

    # 🪤 Não basta exigir "tem YYYY no formato": o openpyxl carimba sozinho um
    # 'yyyy-mm-dd h:mm:ss' em qualquer célula que receba `date`. Essa versão
    # frouxa do teste deixou o mutante dos índices passar batido. O que prova
    # que a NOSSA linha rodou é o formato brasileiro.
    venc = por_item["Bloco ceramico 14 cm"]["VENCIMENTO"]
    assert isinstance(venc.value, (datetime.date, datetime.datetime)), \
        f"VENCIMENTO virou {venc.value!r} — a coluna andou de lugar"
    assert venc.number_format == FMT_DATA, \
        f"VENCIMENTO com formato {venc.number_format!r} em vez de {FMT_DATA} — " \
        "o índice da coluna de data ficou pra trás"

    pago = por_item["Argamassa de assentamento"]["PAGO EM"]
    assert isinstance(pago.value, (datetime.date, datetime.datetime))
    assert pago.number_format == FMT_DATA

    valor = por_item["Bloco ceramico 14 cm"]["VALOR (R$)"]
    assert valor.value == 12000.0, "a coluna do VALOR andou junto com o selo"
    assert valor.number_format == FMT_MOEDA

    # e a última coluna da linha é mesmo a do valor — se a lista de valores
    # encurtar (o selo sumindo de `vals`), o R$ escorrega uma casa pra esquerda
    # e a planilha fica com o dinheiro na coluna errada, sem erro nenhum.
    ultima = max(c.column for c in linhas[0].values() if c.value is not None)
    assert linhas[0]["VALOR (R$)"].column == ultima, \
        "o valor não está na última coluna: a linha ficou curta pro cabeçalho"


# ══════════════════════════════════════════════════════════════════════════
#  6 · o arquivo de verdade: PDF (o HTML que vira PDF)
# ══════════════════════════════════════════════════════════════════════════
def test_pdf_carimba_o_selo_em_cada_linha():
    html = montar_html_financeiro(_dados(), {"project_name": "Obra de teste"})
    assert _esc(SELO_NOTA)[:60] in html, "o PDF saiu sem a legenda do selo"

    carimbos = _selos_do_pdf(html)
    assert len(carimbos) == 3, \
        f"3 linhas vêm do quantitativo, mas saíram {len(carimbos)} carimbos"
    por_classe = dict(carimbos)
    assert por_classe["med"] == _esc(SELO_LABEL["confirmado"])
    assert "confira" in por_classe["est"].lower()
    assert por_classe["nc"] == _esc(SELO_LABEL[""])


def test_pdf_sem_selos_lidos_nao_afirma_medicao():
    html = montar_html_financeiro(_dados(selos={}), {"project_name": "Obra de teste"})
    carimbos = _selos_do_pdf(html)
    assert carimbos, "sumiram os carimbos: o teste parou de olhar pro lugar certo"
    for classe, texto in carimbos:
        assert classe != "med", "🚨 sem os selos lidos, o PDF carimbou MEDIDO"
        assert texto != _esc(SELO_LABEL["confirmado"])


# ══════════════════════════════════════════════════════════════════════════
#  7 · o selo sai da RÉGUA ÚNICA, não de uma consulta paralela
# ══════════════════════════════════════════════════════════════════════════
#  🩸 A primeira versão do conserto tinha consulta própria por `origem_ref_id`
#  e NÃO religava o item por descrição. Como o `/add-file` recria os itens com
#  UUID novo, a tela diria "ok" e a planilha diria "não confirmado" pra MESMA
#  linha. Régua copiada perde as absolvições da original sem ninguém ver.
_ITEM = {"id": "44444444-4444-4444-8444-444444444444",
         "description": "Porcelanato 60x60", "quantity": 1062.0, "unit": "m2",
         "confidence": "confirmado"}


def _lanc(**k):
    base = {"origem": "quantitativo", "origem_ref_id": _ITEM["id"],
            "origem_quantidade": 1062.0, "origem_unidade": "m2",
            "descricao": "Porcelanato 60x60"}
    base.update(k)
    return base


def _regua(lanc, itens):
    import main
    por_desc = {}
    for i in itens:
        por_desc.setdefault(main._fin_norm(i.get("description")), []).append(i)
    return main._fin_estado_da_origem(lanc, {str(i["id"]): i for i in itens}, por_desc)


def test_a_regua_devolve_o_selo_junto_com_o_estado():
    r = _regua(_lanc(), [_ITEM])
    assert r["origem_estado"] == "ok"
    assert r["origem_selo"] == "confirmado", \
        "a régua tem que devolver o selo do item que ELA resolveu"


def test_o_selo_acompanha_o_religamento_por_descricao():
    """🪤 Depois do /add-file o item renasce com UUID novo.

    A régua religa pela descrição — e o selo TEM que vir do item religado. Se
    viesse de uma consulta pelo `origem_ref_id` velho, esta linha sairia como
    'não confirmado' na planilha enquanto a tela diz 'ok'.
    """
    renascido = dict(_ITEM, id="55555555-5555-4555-8555-555555555555")
    r = _regua(_lanc(), [renascido])
    assert r["origem_estado"] == "ok", "a régua não religou — o teste perdeu o alvo"
    assert r["origem_selo"] == "confirmado", \
        "🚨 o selo ficou preso ao UUID velho: tela e planilha vão discordar"
    assert r.get("origem_ref_id_atual") == renascido["id"]


def test_item_estimado_nao_vira_medido_na_regua():
    r = _regua(_lanc(), [dict(_ITEM, confidence="estimado")])
    assert r["origem_selo"] == "estimado"
    assert r["origem_selo"] != "confirmado"


def test_item_sem_confidence_no_banco_nao_vira_medido():
    """Coluna nula/ausente é NÃO SEI — nunca 'medido'."""
    sem = dict(_ITEM)
    sem.pop("confidence")
    r = _regua(_lanc(), [sem])
    assert r["origem_selo"] == "", "NULL virou afirmação"
    # e o export transforma isso em "Não confirmado", não em medido
    from financeiro_export import _selo_key
    assert _selo_key(r["origem_selo"]) == "nao_confirmado"


def test_item_removido_nao_carrega_selo():
    r = _regua(_lanc(), [])
    assert r["origem_estado"] == "removido"
    assert "origem_selo" not in r, \
        "item que sumiu não tem selo pra dar — nem vazio, que o export leria como estado"


# ══════════════════════════════════════════════════════════════════════════
#  8 · a tela recebe o selo — rota EXECUTADA, com o banco fingido
# ══════════════════════════════════════════════════════════════════════════
JOB = "selo0001"
_ITEM_TELA = dict(_ITEM, job_id=JOB)
_LANC_TELA = {"id": "aaaa1111-1111-4111-8111-111111111111", "job_id": JOB, "escopo": "obra",
              "origem": "quantitativo", "origem_ref_id": _ITEM["id"], "origem_ref_pos": None,
              "origem_quantidade": 1062.0, "origem_unidade": "m2", "categoria": "Pisos",
              "descricao": "Porcelanato 60x60", "fornecedor": "", "valor": 8000.0,
              "forma_pagamento": "", "venc_tipo": "fase", "venc_fase": "Pisos",
              "venc_quando": "inicio", "venc_data": None, "status": "cotado", "pago_em": None}


class _BancoFalso:
    """Guarda as consultas feitas — é assim que se prova o SELECT sem ler fonte."""

    def __init__(self, itens):
        self.itens = itens
        self.caminhos = []

    def __call__(self, request, method, path, body=None, params=None, prefer=None, timeout=15):
        self.caminhos.append(path)
        if "/project_items" in path:
            return (200, list(self.itens))
        return (200, [dict(_LANC_TELA)])


def _lista(monkeypatch, itens):
    import main
    banco = _BancoFalso(itens)
    monkeypatch.setattr(main, "_require_project_owner", lambda request, job_id: "uid-dono")
    monkeypatch.setattr(main, "_get_user_from_request",
                        lambda request, tolerante=False: {"id": "uid-dono", "email": "x@y.z"})
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supa_rest_as_user", banco)
    return banco, main.financeiro_listar(JOB, object())


def test_a_rota_pede_confidence_ao_banco(monkeypatch):
    """🪤 O selo depende da coluna vir NO SELECT.

    Tirar `confidence` da consulta não quebra nada e não dá erro: toda linha
    passa a sair "não confirmado" — degradação silenciosa. Este guarda observa
    a consulta que a rota REALMENTE fez, não o texto do fonte.
    """
    banco, _ = _lista(monkeypatch, [_ITEM_TELA])
    itens = [c for c in banco.caminhos if "/project_items" in c]
    assert itens, "a rota nem consultou os itens"
    assert "confidence" in itens[0], \
        f"o SELECT dos itens não pede confidence: {itens[0]}"


def test_a_tela_recebe_o_selo_de_cada_lancamento(monkeypatch):
    _, resp = _lista(monkeypatch, [_ITEM_TELA])
    l = resp["lancamentos"][0]
    assert l["origem_estado"] == "ok"
    assert l["origem_selo"] == "confirmado"


def test_a_tela_nao_recebe_medido_quando_o_item_e_estimado(monkeypatch):
    _, resp = _lista(monkeypatch, [dict(_ITEM_TELA, confidence="estimado")])
    assert resp["lancamentos"][0]["origem_selo"] == "estimado"


def test_itens_ilegiveis_nao_viram_medido_na_tela(monkeypatch):
    """Sem conseguir ler os itens, a rota devolve 'indisponivel' e NENHUM selo."""
    _, resp = _lista(monkeypatch, [])
    l = resp["lancamentos"][0]
    assert l["origem_estado"] == "removido"
    assert not l.get("origem_selo"), "item que sumiu voltou com selo"


# ══════════════════════════════════════════════════════════════════════════
#  9 · o export busca o selo pela MESMA régua (execução, banco fingido)
# ══════════════════════════════════════════════════════════════════════════
def _selos_do_export(monkeypatch, itens, linhas=None):
    import main
    banco = _BancoFalso(itens)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supa_rest_as_user", banco)
    return main._fin_selos_das_origens(object(), JOB, linhas or [dict(_LANC_TELA)])


def test_o_export_acha_o_selo_do_item_religado(monkeypatch):
    """🪤 Depois do /add-file o item renasce com UUID novo.

    O mapa TEM que sair com a chave do `origem_ref_id` VELHO — é essa a chave
    que o arquivo usa. Sem isso a planilha diria "não confirmado" na mesma
    linha que a tela mostra em dia.
    """
    renascido = dict(_ITEM_TELA, id="66666666-6666-4666-8666-666666666666")
    selos = _selos_do_export(monkeypatch, [renascido])
    assert selos.get(_ITEM["id"]) == "confirmado", \
        f"o selo não seguiu o religamento: {selos}"


def test_o_export_nao_inventa_selo_pra_item_que_sumiu(monkeypatch):
    selos = _selos_do_export(monkeypatch, [])
    assert selos.get(_ITEM["id"], "") != "confirmado", \
        "🚨 item removido do quantitativo saiu como MEDIDO"


def test_o_export_pede_confidence_ao_banco(monkeypatch):
    """O caminho do ARQUIVO tem a própria consulta: ela também precisa da coluna."""
    import main
    banco = _BancoFalso([_ITEM_TELA])
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supa_rest_as_user", banco)
    main._fin_selos_das_origens(object(), JOB, [dict(_LANC_TELA)])
    itens = [c for c in banco.caminhos if "/project_items" in c]
    assert itens, "o export nem consultou os itens"
    assert "confidence" in itens[0], f"o SELECT do export não pede confidence: {itens[0]}"
    assert "description" in itens[0] and "quantity" in itens[0], \
        "sem descrição/quantidade a régua não consegue religar item recriado"


def test_o_export_nao_afirma_medicao_quando_a_leitura_e_cortada(monkeypatch):
    """🪤 O PostgREST corta em 1000 CALADO.

    Com o corte, item que existe pode ter ficado DE FORA da leitura — e aí o
    arquivo carimbaria em cima de uma lista incompleta. Melhor não carimbar
    nada do que carimbar errado sobre dinheiro combinado.

    🧪 O item de verdade vai NO MEIO dos mil: sem a trava do corte, esta linha
    sairia carimbada "confirmado" e o teste passaria à toa.
    """
    muitos = [dict(_ITEM_TELA, id=f"{i:08d}-0000-4000-8000-000000000000",
                   description=f"Item generico {i}")
              for i in range(999)] + [dict(_ITEM_TELA)]
    assert len(muitos) == 1000
    assert _selos_do_export(monkeypatch, muitos) == {}, \
        "leitura cortada em 1000 e o arquivo carimbou assim mesmo"
    # e com 999 (sem corte) ele carimba — senão o teste acima passaria sempre
    assert _selos_do_export(monkeypatch, muitos[1:]).get(_ITEM["id"]) == "confirmado"


def test_item_que_MUDOU_nao_sai_carimbado_como_medido(monkeypatch):
    """🚨 Achado crítico da revisão adversarial de 07/09.

    A linha cujo item mudou no quantitativo ia pro fornecedor carimbada
    "Medido do CAD" — enquanto a TELA, ao lado, no mesmo dia, dizia "item mudou
    no quantitativo — conferir valor". O selo do item descreve a quantidade de
    HOJE; o dinheiro daquela linha foi fechado contra o RETRATO, que já não é o
    mesmo. Afirmar medição sobre número que mudou é a regra nº1 pelo avesso.
    """
    mudou = dict(_ITEM_TELA, quantity=2000.0)      # o retrato dizia 1062,0
    selos = _selos_do_export(monkeypatch, [mudou])
    assert selos.get(_ITEM["id"], "") != "confirmado", (
        "🚨 item que MUDOU saiu como medido do CAD: %r" % selos)
    # e o arquivo escreve o terceiro estado, não "Medido do CAD"
    linhas = _por_descricao(montar_dados_export([dict(_LANC_TELA)], [], HOJE, selos=selos))
    assert linhas["Porcelanato 60x60"]["selo"] == SELO_LABEL[""]


def test_CONTROLE_item_em_dia_continua_carimbado(monkeypatch):
    """O outro lado: sem mudança, o selo sai — senão o conserto matou a coluna."""
    selos = _selos_do_export(monkeypatch, [_ITEM_TELA])
    assert selos.get(_ITEM["id"]) == "confirmado"


def test_a_legenda_nao_AFIRMA_a_causa_do_nao_confirmado():
    """🩸 A legenda dizia que "Não confirmado" = "o projeto foi reprocessado".

    O mesmo selo sai quando a leitura falhou, quando o PostgREST cortou em 1000
    e quando o item só mudou. Num projeto grande, ou numa noite de 5xx, o
    arquivo INTEIRO afirmaria pro fornecedor e pro banco um reprocesso que não
    houve. É o log que chuta a causa — e aqui vai impresso pra fora da casa.
    """
    n = SELO_NOTA.lower()
    assert "não foi possível confirmar" in n
    assert "o projeto foi reprocessado" not in n, (
        "a legenda voltou a afirmar a causa: %r" % SELO_NOTA)
    # a causa continua sendo citada, mas como POSSIBILIDADE
    assert "pode ter" in n


def test_a_faixa_de_kpis_cobre_a_tabela_inteira():
    """🪤 Terceiro índice cravado que a coluna SELO desalinhou.

    `slots` parava na coluna 11 e a tabela passou a ter 12 — buraco branco no
    canto direito, em cima da coluna do dinheiro.

    🪤 A 1ª versão deste teste olhava a MAIOR mesclagem da planilha inteira — e
    o título já cobre as 12 colunas, então ele passava com a faixa torta. A
    mutação pegou. Agora o teste ancora na LINHA dos KPIs.
    """
    import financeiro_export as fx
    ws = _xlsx(_dados()).active
    linha_kpi = next((c.row for linha in ws.iter_rows() for c in linha
                      if c.value == "Contratado" and c.column == 1), None)
    assert linha_kpi, "não achei a faixa de KPIs na planilha"
    faixa = [r for r in ws.merged_cells.ranges
             if r.min_row in (linha_kpi, linha_kpi + 1)]
    assert faixa, "a faixa de KPIs não tem mesclagem nenhuma"
    assert max(r.max_col for r in faixa) == fx._COL_VALOR, (
        "a faixa de KPIs vai até a coluna %d e a tabela tem %d — sobra buraco "
        "em cima da coluna do dinheiro"
        % (max(r.max_col for r in faixa), fx._COL_VALOR))


def test_linha_do_comparativo_nao_ganha_selo_nosso():
    """A quantidade veio da COTAÇÃO do fornecedor — não é medição nem estimativa
    nossa. "Não confirmado" ali sugeriria falha nossa onde não há nada nosso."""
    comp = {"categoria": "Pisos", "descricao": "Porcelanato cotado", "origem": "comparativo",
            "origem_ref_id": "77777777-7777-4777-8777-777777777777",
            "valor": 5000.0, "status": "cotado"}
    linhas = _por_descricao(montar_dados_export([comp], [], HOJE, selos={}))
    assert linhas["Porcelanato cotado"]["selo"] == "", \
        "linha do Comparativo saiu carimbada com selo nosso"


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE POSITIVO — o guarda tem que REPROVAR de verdade
# ══════════════════════════════════════════════════════════════════════════
def test_o_guarda_do_selo_reprova_de_verdade(monkeypatch):
    """Faz o defeito voltar e exige que os testes acima quebrem.

    O defeito reproduzido é o original: o selo some do arquivo. Se depois de
    apagá-lo os testes ainda passassem, eles não estariam olhando pro arquivo.
    """
    import financeiro_export as fx

    original = fx.montar_dados_export

    def sem_selo(rows, fases, hoje, selos=None):
        dados = original(rows, fases, hoje, selos=selos)
        for g in dados["grupos"]:
            for l in g["linhas"]:
                l["selo"] = ""
                l["selo_key"] = ""
        return dados

    monkeypatch.setattr(fx, "montar_dados_export", sem_selo)

    dados = fx.montar_dados_export(ROWS, [], HOJE, selos=SELOS)

    # o .xlsx perde a coluna preenchida
    ws = _xlsx(dados).active
    linhas = _linhas_do_xlsx(ws)
    por_item = {str(l["ITEM"].value): l for l in linhas}
    assert por_item["Bloco ceramico 14 cm"]["SELO"].value in (None, ""), \
        "o mutante não pegou: revisar o controle positivo"

    # ...e a legenda some junto, porque nenhuma linha tem selo
    texto = "\n".join(str(c.value) for linha in ws.iter_rows() for c in linha if c.value)
    assert SELO_NOTA[:60] not in texto

    # o PDF também
    html = montar_html_financeiro(dados, {"project_name": "Obra de teste"})
    assert not _selos_do_pdf(html), "o mutante não apagou os carimbos do PDF"


def test_o_guarda_pega_selo_que_mente(monkeypatch):
    """Segundo mutante, o PERIGOSO: o selo existe, mas diz 'medido' pra tudo.

    Esse é o defeito que um guarda preguiçoso (que só confere "tem coluna SELO?")
    deixaria passar — e é exatamente a regra dura nº1 violada.
    """
    import financeiro_export as fx

    monkeypatch.setitem(fx.SELO_LABEL, "estimado", fx.SELO_LABEL["confirmado"])
    monkeypatch.setitem(fx.SELO_LABEL, "", fx.SELO_LABEL["confirmado"])

    linhas = _por_descricao(fx.montar_dados_export(ROWS, [], HOJE, selos=SELOS))
    mentiu = [d for d, l in linhas.items()
              if l["selo"] == fx.SELO_LABEL["confirmado"] and l["selo_key"] != "medido"]
    assert mentiu, "o mutante não mentiu: revisar o controle positivo"

    # E é isto que o guarda de cima checa — aqui só provamos que ele TEM o que pegar.
    with pytest.raises(AssertionError):
        for l in linhas.values():
            if l["selo_key"] in ("estimado", "nao_confirmado"):
                assert l["selo"] != fx.SELO_LABEL["confirmado"]
