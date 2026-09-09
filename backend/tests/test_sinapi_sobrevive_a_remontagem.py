# -*- coding: utf-8 -*-
"""A referência SINAPI não pode sumir quando a planilha é remontada do banco.

🩸 `project_items` NÃO guarda `sinapi_matches` — não existe coluna pra isso.
Então toda planilha remontada a partir do banco saía com a coluna REF vazia e
SEM a aba "Referências SINAPI". O TCPO, logo abaixo no mesmo bloco, JÁ era
refeito desde sempre; o SINAPI não. A assimetria passou batida porque a planilha
continua saindo bonita — só que sem a referência oficial, que é metade do que a
gente promete ("XLSX com referência SINAPI/TCPO").

Remontagem acontece em dois casos REAIS de cliente:
  1. depois que ele revisa a planilha (`finalize_review`);
  2. no download, quando a retenção de 90 dias já apagou o arquivo.

📏 MEDIDO em 01/09/2026: **21 jobs de 17 clientes** já foram revisados — todos
receberam a versão remontada. Revisão é justo o momento em que o cliente mais
precisa confiar no arquivo.

🪤 Achado por um agente que conferia a planilha corrigida do cliente-102 contra a
original e percebeu que a coluna REF tinha 126 células e nenhum código.
"""
import io
import os

import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

from models import BudgetItem, ProjectData, Confidence  # noqa: E402
from spreadsheet import generate_spreadsheet            # noqa: E402
from openpyxl import load_workbook                      # noqa: E402

_ABA = "Referências SINAPI"


def _item(sinapi=None):
    it = BudgetItem(item_num="", description="Piso em porcelanato 60x60 cm",
                    unit="m²", quantity=48.0, discipline="Pisos",
                    confidence=Confidence.ESTIMADO)
    if sinapi:
        it.sinapi_matches = sinapi
    return it


_MATCH = [{"codigo": "87263", "descricao": "REVESTIMENTO CERAMICO PARA PISO",
           "unidade": "M2", "familia_id": 1, "similarity": 0.91}]


# ── A CONSEQUÊNCIA REAL, testada de verdade ────────────────────────────────
def test_COM_sinapi_a_aba_de_referencias_EXISTE(tmp_path):
    saida = str(tmp_path / "com.xlsx")
    generate_spreadsheet(ProjectData(name="t"), [_item(_MATCH)], saida)
    wb = load_workbook(saida)
    assert _ABA in wb.sheetnames, (
        "item com match SINAPI e a aba de referências não saiu: %s" % wb.sheetnames)
    txt = " ".join(str(c) for row in wb[_ABA].iter_rows(values_only=True)
                   for c in row if c is not None)
    assert "87263" in txt, "a aba existe mas não traz o código"


def test_CONTROLE_SEM_sinapi_a_aba_NAO_existe(tmp_path):
    """🧪 É exatamente isto que os 17 clientes revisados receberam. Se este
    teste falhasse, o de cima não estaria provando nada."""
    saida = str(tmp_path / "sem.xlsx")
    generate_spreadsheet(ProjectData(name="t"), [_item()], saida)
    wb = load_workbook(saida)
    assert _ABA not in wb.sheetnames, (
        "a aba apareceu sem nenhum match — o teste de cima vira tautologia")


def test_CONTROLE_a_coluna_REF_fica_vazia_sem_sinapi(tmp_path):
    """A perda não é só a aba: a coluna REF de cada linha também esvazia."""
    com = str(tmp_path / "a.xlsx")
    sem = str(tmp_path / "b.xlsx")
    generate_spreadsheet(ProjectData(name="t"), [_item(_MATCH)], com)
    generate_spreadsheet(ProjectData(name="t"), [_item()], sem)

    def _tem_codigo(p):
        wb = load_workbook(p)
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                if any(c is not None and "87263" in str(c) for c in row):
                    return True
        return False

    assert _tem_codigo(com), "o código não apareceu nem com match"
    assert not _tem_codigo(sem), "apareceu código sem match — impossível"


# ── O ponto de chamada: os DOIS caminhos têm que enriquecer ────────────────
def _fonte_sem_comentarios(inicio, fim=None):
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index(inicio)
    j = src.index(fim, i) if fim else len(src)
    return "\n".join(l for l in src[i:j].splitlines()
                     if not l.lstrip().startswith("#"))


# ══════════════════════════════════════════════════════════════════════════
#  A REMONTAGEM RODANDO DE VERDADE
#
#  🚨 06/09/2026 — POR QUE MUDOU. Os dois guardas de ponto de chamada abaixo
#  liam o fonte de `rebuild_planilha_from_review` e afirmavam por string.
#  Provados cegos em três mutações:
#    (a) `if _e["candidates"]:` -> `if not _e["candidates"]:` — nenhum item
#        recebe `sinapi_matches`, a planilha revisada volta a sair sem
#        referência (o bug de 01/09 que criou este arquivo). PASSOU.
#    (b) `_nc_rb = apply_llm_pick(...)` -> `_nc_rb = 0   # apply_llm_pick(...)`
#        — o comentário no FIM da linha não é apagado pelo filtro de
#        comentários, o código sai por SIMILARIDADE e volta a chamar piso de
#        porcelanato de PISO DE BORRACHA (17/07). PASSOU.
#    (c) `except Exception as _esr:` -> `except ValueError as _esr:` — o
#        timeout do SINAPI (caso de 22/07) sobe e mata a remontagem inteira,
#        com o `try:` e a string do log ainda no fonte. PASSOU.
#  Agora a rota RODA e a prova é o .xlsx que o cliente baixa.
# ══════════════════════════════════════════════════════════════════════════
JOB = "job-sinapi-rebuild"

# O erro de 17/07: a busca por texto dá 93% pra PISO DE BORRACHA e 71% pro
# porcelanato certo. Quem manda no código da REF é a IA, não a similaridade.
_ERRADO = {"codigo": "88484", "descricao": "PISO EM BORRACHA NATURAL",
           "unidade": "M2", "familia_id": 9, "similarity": 0.93}
_CERTO = {"codigo": "87263", "descricao": "REVESTIMENTO CERAMICO PARA PISO",
          "unidade": "M2", "familia_id": 1, "similarity": 0.71}

# ══════════════════════════════════════════════════════════════════════════
#  🪤 06/09/2026 (cético) — A REMONTAGEM RODAVA COM **UM** ITEM.
#  Com um item só, o guarda não distinguia "todos os itens receberam a
#  referência" de "o PRIMEIRO item recebeu": `_lote_rb[:1]`, um `break` no
#  laço que grava `sinapi_matches`, ou um `if` que só vale pro primeiro
#  deixavam a aba "Referências SINAPI" existir, com o 87263 dentro, e
#  `visto["pick"] == 1` continuava batendo — enquanto na planilha real do
#  caso (126 linhas) 125 saíam com a coluna REF VAZIA. E o log ainda dizia
#  "N/N conferidos", o que apagaria a suspeita de quem investigasse.
#  Agora são TRÊS linhas, de três disciplinas, cada uma com o seu par
#  (similaridade alta ERRADA × escolha da IA CERTA), e a conferência é linha
#  por linha.
# ══════════════════════════════════════════════════════════════════════════
_CENARIO = [
    # descricao,                                  errado (sim. alta),  certo (IA)
    ("Piso em porcelanato 60x60 cm", "Pisos", 48.0,
     ("88484", "PISO EM BORRACHA NATURAL", 0.93),
     ("87263", "REVESTIMENTO CERAMICO PARA PISO", 0.71)),
    ("Pintura látex acrílica em parede interna", "Pintura", 210.0,
     ("88497", "APLICACAO DE FUNDO SELADOR ACRILICO", 0.90),
     ("88489", "APLICACAO DE PINTURA LATEX ACRILICA", 0.68)),
    ("Forro em gesso acartonado", "Forros", 96.0,
     ("96116", "FORRO EM REGUA DE PVC", 0.88),
     ("96113", "FORRO EM PLACAS DE GESSO ACARTONADO", 0.70)),
]


def _cand(t):
    return {"codigo": t[0], "descricao": t[1], "unidade": "M2",
            "familia_id": 1, "similarity": t[2]}


_CANDIDATOS = {d: [_cand(e), _cand(c)] for d, _di, _q, e, c in _CENARIO}
_ESCOLHA_DA_IA = {d: c[0] for d, _di, _q, _e, c in _CENARIO}
_CODIGOS_CERTOS = [c[0] for _d, _di, _q, _e, c in _CENARIO]
_CODIGOS_ERRADOS = [e[0] for _d, _di, _q, e, _c in _CENARIO]


class _RespRPC:
    """A rota lê os itens pela RPC `list_project_items` com `urlopen` DIRETO,
    sem passar por helper — patchar `_supa_rest_service` não intercepta nada."""

    def __init__(self, payload):
        import json as _j
        self._b = _j.dumps(payload).encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _remontar(monkeypatch, tmp_path, candidatos=None, escolha_da_ia="87263",
              explode=None):
    """Roda `rebuild_planilha_from_review` de verdade e devolve
    (resposta, caminho do .xlsx gerado, logs)."""
    import asyncio
    import urllib.request
    import sinapi_matcher
    import main

    logs = []
    _VISTO.clear()
    _VISTO["pick"] = 0
    linhas = [{"item_num": "%d.1" % (i + 1), "description": _d,
               "unit": "m²", "quantity": _q, "confidence": "estimado",
               "observations": "", "ref_sheet": "", "origem": "cad",
               "discipline": _di}
              for i, (_d, _di, _q, _e, _c) in enumerate(_CENARIO)]
    proj = {"job_id": JOB, "project_name": "Projeto cliente-NN",
            "typology": "office", "total_area": 120.0, "warnings": [],
            "layout_area": 0, "address": ""}
    cands = [dict(c) for c in (candidatos or [_ERRADO, _CERTO])]

    monkeypatch.setattr(main, "_require_project_owner", lambda *a, **k: None)
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, msg, job=None, **k: logs.append((stage, msg)))
    monkeypatch.setattr(main, "_supa_rest_as_user", lambda *a, **k: (200, [dict(proj)]))
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _RespRPC(linhas))
    # 🪤 candidatos POR DESCRIÇÃO: com a lista fixa de antes, item errado e
    # item certo recebiam o mesmo par e o guarda não veria linha trocada.
    def _cands_por_desc(desc, limit=60):
        return [dict(c) for c in _CANDIDATOS.get(desc, cands)]
    monkeypatch.setattr(sinapi_matcher, "candidates_for", _cands_por_desc)
    if explode is not None:
        # 🪤 O erro TEM que estourar em `apply_llm_pick`. `candidates_for` roda
        # dentro de um `try/except` interno (`_cands_rb`), que engoliria a
        # exceção antes de ela chegar no `except` que este guarda mede — e o
        # teste passaria pelo motivo errado.
        def _explode(*a, **k):
            raise explode
        monkeypatch.setattr(sinapi_matcher, "apply_llm_pick", _explode)
    else:
        # `apply_llm_pick` é o REAL — só a chamada à IA é dublada. É ele quem
        # põe o código escolhido em 1º lugar, e é esse movimento que a mutação
        # (b) mata.
        def _escolhe(itens, **k):
            # a IA responde por ITEM do lote — se a produção truncar o lote,
            # a resposta encolhe junto e as linhas de baixo saem sem REF
            return {i: _ESCOLHA_DA_IA.get(e.get("description"), escolha_da_ia)
                    for i, e in enumerate(itens)}
        monkeypatch.setattr(sinapi_matcher, "pick_best_batch", _escolhe)
        _pick_real = sinapi_matcher.apply_llm_pick

        def _pick_contado(*a, **k):
            _VISTO["pick"] += 1
            return _pick_real(*a, **k)
        monkeypatch.setattr(sinapi_matcher, "apply_llm_pick", _pick_contado)
    monkeypatch.setattr(main, "_supabase_storage_upload", lambda *a, **k: True)
    monkeypatch.setattr(main, "_carimbar_planilha", lambda *a, **k: None)
    monkeypatch.setattr(main, "WORK_DIR", str(tmp_path))

    r = asyncio.run(main.rebuild_planilha_from_review(JOB, request=None))
    saida = os.path.join(str(tmp_path), JOB, "orcamento_%s_revisado.xlsx" % JOB)
    return r, saida, logs


#: contador de chamadas de `apply_llm_pick` (a escolha da IA) na remontagem.
_VISTO = {"pick": 0}


def _remontar_v(monkeypatch, tmp_path, **kw):
    """A mesma remontagem, no formato que o guarda convertido pede:
    (resposta, visto, workbook aberto)."""
    r, saida, _logs = _remontar(monkeypatch, tmp_path, **kw)
    return r, _VISTO, load_workbook(saida)


def _texto(wb, aba):
    return " | ".join(str(c) for row in wb[aba].iter_rows(values_only=True)
                      for c in row if c is not None)


def _texto_das_abas(caminho, abas=None):
    wb = load_workbook(caminho)
    alvo = wb.sheetnames if abas is None else [a for a in abas if a in wb.sheetnames]
    return " | ".join(str(c) for nome in alvo
                      for row in wb[nome].iter_rows(values_only=True)
                      for c in row if c is not None)


def test_a_remontagem_REFAZ_o_sinapi(monkeypatch, tmp_path, capsys):
    """🩸 A planilha revisada tem que sair COM referência — em TODAS as linhas,
    e com a referência CERTA, que só sai porque a escolha da IA roda.

    🪤 06/09 (cético): com UM item no cenário, `_lote_rb[:1]` e um `break` no
    laço passavam verdes. Aqui são três linhas e a conferência é uma a uma.
    """
    r, visto, wb = _remontar_v(monkeypatch, tmp_path)
    assert r["items_count"] == len(_CENARIO), r

    assert _ABA in wb.sheetnames, (
        "a planilha remontada saiu SEM a aba de referências SINAPI — é o que "
        "21 jobs de 17 clientes receberam antes de 01/09. Abas: %s"
        % wb.sheetnames)
    aba = _texto(wb, _ABA)
    orc = _texto(wb, "Orçamento")

    faltando = [c for c in _CODIGOS_CERTOS if ("SINAPI %s" % c) not in orc]
    assert not faltando, (
        "%d de %d linhas saíram com a coluna REF VAZIA (faltaram %r) — é o "
        "defeito das 126 linhas: a primeira recebe a referência e o resto do "
        "cliente vai sem. Orçamento: %s"
        % (len(faltando), len(_CODIGOS_CERTOS), faltando, orc[:600]))
    for c in _CODIGOS_CERTOS:
        assert c in aba, (
            "o código %s ficou de fora da aba de referências: %s" % (c, aba[:600]))

    # A REF que vai na linha do orçamento é o PRIMEIRO match. Sem
    # `apply_llm_pick` ela seria a de similaridade maior — PISO DE BORRACHA.
    for c in _CODIGOS_ERRADOS:
        assert ("SINAPI %s" % c) not in orc, (
            "a REF de alguma linha ficou com o candidato de similaridade maior "
            "(%s) — a busca por texto sozinha chamou porcelanato de PISO DE "
            "BORRACHA (17/07); `apply_llm_pick` deixou de rodar em todas as "
            "linhas. Orçamento: %s" % (c, orc[:600]))
    assert visto["pick"] == 1, (
        "a escolha da IA nunca foi chamada na remontagem (%d chamadas)"
        % visto["pick"])

    # 🪤 O log é a única coisa que quem investiga vê. Com o lote truncado ele
    # dizia "1/1 conferidos" — honesto na aparência e cego no fato.
    saiu = capsys.readouterr().out
    assert ("[sinapi-rebuild]" in saiu
            and ("%d/%d" % (len(_CENARIO), len(_CENARIO))) in saiu), (
        "o log da remontagem não contou as %d linhas do lote — com o lote "
        "cortado ele diz '1/1 conferidos' e apaga a suspeita. Saída: %r"
        % (len(_CENARIO), saiu[-400:]))


def test_a_remontagem_usa_a_ESCOLHA_DA_IA_e_nao_a_similaridade(monkeypatch, tmp_path):
    """🚨 17/07: a busca por texto sozinha chamou piso de porcelanato de PISO
    DE BORRACHA. `apply_llm_pick` é o que promove o código escolhido pra 1º —
    sem essa chamada, quem manda na coluna REF é a similaridade.

    🪤 A mutação que enganou o guarda antigo (`_nc_rb = 0   # apply_llm_pick(
    _lote_rb, job_id=job_id)`) deixa a string `apply_llm_pick` no fonte, e o
    filtro de comentários do teste antigo só descartava linha que COMEÇA com
    `#`."""
    r, saida, _ = _remontar(monkeypatch, tmp_path)
    ref = _texto_das_abas(saida)
    assert "87263" in ref, (
        "o código que a IA escolheu não chegou na planilha revisada")

    wb = load_workbook(saida)
    primeira = None
    for nome in wb.sheetnames:
        if nome == _ABA:
            continue        # a aba técnica lista os dois de propósito
        for row in wb[nome].iter_rows(values_only=True):
            for c in row:
                if c is not None and ("87263" in str(c) or "88484" in str(c)):
                    primeira = str(c)
                    break
            if primeira:
                break
        if primeira:
            break
    assert primeira and "87263" in primeira and "88484" not in primeira, (
        "a REF da linha saiu com o código da SIMILARIDADE e não com o que a "
        "IA conferiu — piso de porcelanato voltou a virar PISO DE BORRACHA. "
        "Célula: %r" % (primeira,))


def test_o_tcpo_continua_sendo_refeito_junto():
    """O TCPO já estava certo. Não pode ter quebrado no caminho."""
    bloco = _fonte_sem_comentarios(
        "async def rebuild_planilha_from_review", "\n@app.")
    assert "from tcpo_matcher import" in bloco and "tcpo_matches" in bloco


def test_CONTROLE_a_checagem_de_chamada_sabe_REPROVAR():
    """🧪 Sem isto, o teste acima passaria com o conserto desligado."""
    falso = "\n".join([
        "async def rebuild_planilha_from_review(job_id, request):",
        "    # from sinapi_matcher import candidates_for",
        "    from tcpo_matcher import match_item",
    ])
    limpo = "\n".join(l for l in falso.splitlines()
                      if not l.lstrip().startswith("#"))
    assert "from sinapi_matcher import" not in limpo, (
        "a checagem aceita o import COMENTADO — não guarda nada")
    assert "from tcpo_matcher import" in limpo, (
        "o controle não exercita o mesmo padrão do teste real")


def test_CONTROLE_a_falha_do_matcher_NAO_derruba_a_planilha(monkeypatch, tmp_path):
    """Best-effort de verdade: um timeout do SINAPI (já aconteceu em 22/07) não
    pode matar a remontagem — a planilha sai, sem a referência, e o log conta.

    🪤 O guarda antigo conferia que existia um `try:` ANTES do import e a string
    `sinapi-rebuild-falhou` DEPOIS. Trocar `except Exception` por
    `except ValueError` deixa os dois no lugar e faz o timeout subir de
    `_trabalho`, virar HTTP 500 e derrubar tudo. Por isso o erro aqui é um
    `TimeoutError`, que NÃO é ValueError."""
    r, saida, logs = _remontar(monkeypatch, tmp_path,
                               explode=TimeoutError("read timed out"))

    assert r["status"] == "ok", (
        "uma falha do matcher SINAPI derrubou a remontagem inteira — o cliente "
        "que revisou não recebe planilha nenhuma")
    assert os.path.exists(saida), "a planilha revisada não foi gerada"
    wb = load_workbook(saida)
    assert _ABA not in wb.sheetnames, (
        "o matcher falhou e a aba apareceu mesmo assim — o teste não exercitou "
        "o caminho de falha")
    assert any("sinapi-rebuild-falhou" in s for s, _ in logs), (
        "o matcher estourou e não saiu log nenhum — ou o `except` deixou de "
        "registrar, ou o enriquecimento SINAPI nem chegou a ser chamado. Nos "
        "dois casos a referência some sem ninguém descobrir. Logs: %r" % (logs,))


def test_CONTROLE_a_falha_que_NAO_e_do_matcher_continua_subindo():
    """🧪 Controle positivo do de cima: o `except` do bloco SINAPI não pode ser
    tão largo que engula a rota inteira. Se `_supa_rest_as_user` estoura, o
    cliente tem que receber erro — não uma planilha vazia com cara de sucesso."""
    import asyncio
    import main
    import pytest as _pt

    _orig = main._supa_rest_as_user
    main._supa_rest_as_user = lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("supabase fora do ar"))
    _orig_owner = main._require_project_owner
    main._require_project_owner = lambda *a, **k: None
    try:
        with _pt.raises(Exception) as e:
            asyncio.run(main.rebuild_planilha_from_review(JOB, request=None))
        assert "supabase fora do ar" in str(e.value) or isinstance(
            e.value, main.HTTPException)
    finally:
        main._supa_rest_as_user = _orig
        main._require_project_owner = _orig_owner
