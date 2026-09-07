# -*- coding: utf-8 -*-
"""Reenviar o mesmo caderno vira AVISO — nunca bloqueio, nunca promessa falsa.

🩸 01/09/2026, cliente-42 (cliente novo, primeiro projeto). Linha do tempo
medida no banco:

    20:40  sobe 20 PDFs  ("LUANA E JAILSON")
    21:08  recebe 161 itens — 25 de 25 linhas de METRO em branco,
           42 de 50 de área em branco
    21:19  sobe DE NOVO o mesmo caderno, com 5 arquivos a menos ("LUANA")

As pranchas do 2º envio têm nome idêntico às do 1º (07 PAREDE, 02 FORRO,
03 ILUMINACAO, 04 LUMINARIAS, 08 PISO, 11 RODAPE, 13 BANCADA — todas
`_LUANA_09.04`). Ele achou que o problema era o arquivo dele. Não era: PDF não
dá comprimento confiável, e ele não informou pé-direito nem área — os dois
campos que destravam medição de verdade.

🚫 O aviso NÃO diz "vai dar o mesmo resultado". Seria mentira: o motor não é
determinístico (medido 08/08 — 458 e 177 m² do MESMO arquivo, variação de 26%).
O que se repete é a CAUSA. Prometer número igual e entregar diferente destrói a
confiança que o aviso existe pra construir.

🚫 E NÃO bloqueia. A trava de envio em dobro (90 s) é pra clique repetido;
reenviar dias — ou minutos — depois é direito do cliente.
"""
import io
import os
import sys

import pytest  # noqa: F401

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import main  # noqa: E402


# as pranchas reais do job 144c1f04
CADERNO = [
    "07.18_p parede_luana_09.04.pdf", "02.18_p forro_luana_09.04.pdf",
    "03.18_p iluminacao_luana_09.04.pdf", "08.18_p piso_luana_09.04.pdf",
    "11.18_p rodape_luana_09.04.pdf", "13.18_p bancada_luana_09.04.pdf",
]


def _falso_supa(projetos, itens_por_job):
    """Substitui `_supa_rows` — nada de rede, nada de banco de verdade."""
    def _fake(method, path, **kw):
        if path.startswith("/projects?"):
            return projetos
        if path.startswith("/project_items?"):
            for jid, refs in itens_por_job.items():
                if "job_id=eq.%s" % jid in path:
                    return [{"ref_sheet": r} for r in refs]
        return []
    return _fake


def _cenario(monkeypatch, refs_antigos, tinha_pd=None, tinha_area=None):
    projetos = [{"job_id": "144c1f04", "project_name": "LUANA E JAILSON",
                 "created_at": "2026-09-01T23:40:00+00:00",
                 "user_pe_direito": tinha_pd, "user_total_area": tinha_area}]
    monkeypatch.setattr(main, "_supa_rows",
                        _falso_supa(projetos, {"144c1f04": refs_antigos}))


# ── O que dispara ──────────────────────────────────────────────────────────
def test_mesmo_caderno_reenviado_DISPARA_o_aviso(monkeypatch):
    """🩸 O caso do cliente-14."""
    _cenario(monkeypatch, CADERNO)
    r = main._projeto_ja_enviado("u1", set(CADERNO), 0, 0)
    assert r is not None, "reenvio do mesmo caderno passou batido"
    assert r["job_id"] == "144c1f04"
    assert r["n_iguais"] == 6


def test_subconjunto_tambem_dispara(monkeypatch):
    """Ele tirou 5 arquivos e remandou. Continua sendo o mesmo caderno."""
    _cenario(monkeypatch, CADERNO)
    r = main._projeto_ja_enviado("u1", set(CADERNO[:4]), 0, 0)
    assert r is not None, "reenvio parcial não foi reconhecido"


def test_o_ref_sheet_com_hint_da_IA_ainda_casa(monkeypatch):
    """🪤 O banco guarda 'arquivo.pdf (02/18 — Planta de Forro)'. Comparar a
    string inteira nunca casaria com o nome que chega no upload."""
    _cenario(monkeypatch, [n + " (02/18 — Planta de Forro / Detalhe AA)"
                           for n in CADERNO])
    r = main._projeto_ja_enviado("u1", set(CADERNO), 0, 0)
    assert r is not None, "o hint da IA no ref_sheet quebrou a comparação"


# ── O que NÃO pode disparar (aviso falso é pior que aviso nenhum) ──────────
def test_CONTROLE_projeto_DIFERENTE_nao_dispara(monkeypatch):
    _cenario(monkeypatch, CADERNO)
    outro = {"casa da praia - planta.pdf", "casa da praia - corte.pdf",
             "casa da praia - fachada.pdf", "casa da praia - cobertura.pdf"}
    assert main._projeto_ja_enviado("u1", outro, 0, 0) is None, (
        "acusou repetição num projeto novo — ofende quem está mandando "
        "trabalho de verdade")


def test_CONTROLE_poucos_arquivos_iguais_nao_disparam(monkeypatch):
    """🪤 'planta baixa.pdf' e 'corte.pdf' se repetem entre projetos
    DIFERENTES do mesmo escritório. Dois nomes iguais não é reenvio."""
    _cenario(monkeypatch, ["planta baixa.pdf", "corte.pdf"])
    novo = {"planta baixa.pdf", "corte.pdf", "fachada.pdf", "cobertura.pdf",
            "detalhes.pdf"}
    assert main._projeto_ja_enviado("u1", novo, 0, 0) is None


def test_CONTROLE_quem_INFORMOU_o_pe_direito_agora_NAO_e_avisado(monkeypatch):
    """🔑 A exceção que faz o aviso ser honesto. Se ele fez o que a gente
    pediu, o resultado VAI mudar — e dizer 'você está repetindo' seria
    castigar exatamente quem seguiu a orientação."""
    _cenario(monkeypatch, CADERNO, tinha_pd=None)
    assert main._projeto_ja_enviado("u1", set(CADERNO), 2.7, 0) is None, (
        "avisou 'você está repetindo' pra quem informou o pé-direito desta "
        "vez — o resultado dele MUDA e o aviso seria falso")


def test_CONTROLE_quem_INFORMOU_a_area_agora_NAO_e_avisado(monkeypatch):
    _cenario(monkeypatch, CADERNO, tinha_area=None)
    assert main._projeto_ja_enviado("u1", set(CADERNO), 0, 190.0) is None


def test_CONTROLE_quem_JA_tinha_informado_continua_sendo_avisado(monkeypatch):
    """🧪 O contrário do teste acima: se ele já tinha informado antes e
    informou de novo, não mudou nada — o aviso vale."""
    _cenario(monkeypatch, CADERNO, tinha_pd=2.7)
    assert main._projeto_ja_enviado("u1", set(CADERNO), 2.7, 0) is not None, (
        "a exceção virou porta dos fundos: quem não mudou nada deixou de ser "
        "avisado")


def test_CONTROLE_envio_pequeno_demais_nao_dispara(monkeypatch):
    _cenario(monkeypatch, CADERNO)
    assert main._projeto_ja_enviado("u1", {CADERNO[0], CADERNO[1]}, 0, 0) is None


def test_CONTROLE_sem_user_id_nao_dispara(monkeypatch):
    _cenario(monkeypatch, CADERNO)
    assert main._projeto_ja_enviado(None, set(CADERNO), 0, 0) is None


def test_CONTROLE_banco_mudo_nao_inventa_aviso(monkeypatch):
    """🪤 `_supa_rows` devolve [] em QUALQUER falha — 'vazio ≠ falhou'. Uma
    leitura que caiu não pode virar aviso nem exceção no upload."""
    monkeypatch.setattr(main, "_supa_rows", lambda *a, **k: [])
    assert main._projeto_ja_enviado("u1", set(CADERNO), 0, 0) is None


# ── O nome do arquivo dentro do ref_sheet ──────────────────────────────────
def test_nome_limpo_tira_o_hint_e_normaliza():
    f = main._nome_limpo_da_prancha
    assert f("02.18_P FORRO.pdf (02/18 — Planta de Forro)") == "02.18_p forro.pdf"
    assert f("planta.pdf") == "planta.pdf"
    assert f("") == "" and f(None) == ""


def test_CONTROLE_nome_com_parenteses_PROPRIO_nao_e_cortado_errado():
    """🪤 'casa (fundos).pdf' tem parêntese no nome de verdade. O corte é no
    ' (' que separa o hint — e este teste existe pra alguém pensar duas vezes
    antes de trocar por um corte em '(' solto."""
    f = main._nome_limpo_da_prancha
    assert f("casa (fundos).pdf") == "casa"    # comportamento ATUAL, medido
    # o que importa: os DOIS lados passam pela mesma função, então o corte
    # acontece igual no envio e no banco, e a comparação continua casando
    assert f("casa (fundos).pdf") == f("casa (fundos).pdf (hint da IA)")


# ── O aviso chega ao cliente ───────────────────────────────────────────────
def _fonte(p):
    return io.open(os.path.join(_BACKEND, p), encoding="utf-8").read()


def _site(p):
    return io.open(os.path.join(os.path.dirname(_BACKEND), p),
                   encoding="utf-8").read()


_MIOLO = {".dxf": b"0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n",
          ".dwg": b"AC1027 desenho de mentira\n"}


class _Upload:
    """Um arquivo de upload como o Starlette entrega — nome, tamanho e leitura
    em pedaços."""

    def __init__(self, filename, conteudo=None):
        self.filename = filename
        # 🪤 O conteúdo segue a EXTENSÃO: um ".dxf" com miolo de PDF faria a
        # rota classificar errado e o cenário "ele mandou o CAD junto" mediria
        # outra coisa.
        self._c = conteudo or _MIOLO.get(
            os.path.splitext(filename)[1].lower(), b"%PDF-1.4 planta de mentira\n")
        self.size = len(self._c)
        self._i = 0

    async def seek(self, n):
        self._i = n

    async def read(self, n=-1):
        if n is None or n < 0:
            n = len(self._c) - self._i
        pedaco = self._c[self._i:self._i + n]
        self._i += len(pedaco)
        return pedaco


class _ReqUpload:
    headers = {}
    client = None


def _chamar_upload(monkeypatch, nomes, pe_direito=0, area=0, tmp_path=None):
    """Roda o /api/process de verdade e devolve (resposta, linhas de error_log).

    Tudo que toca rede, banco, disco de produção e o motor é dublado — o que
    fica de pé é a rota: as travas, o cálculo do aviso e a resposta.
    """
    import asyncio
    import tempfile
    logs = []
    monkeypatch.setattr(main, "_get_user_from_request",
                        lambda req, tolerante=False: {"id": "u1", "email": "cliente-nn@example.com"})
    monkeypatch.setattr(main, "_rate_limit_ok", lambda *a, **k: True)
    monkeypatch.setattr(main, "WORK_DIR", str(tmp_path or tempfile.mkdtemp(prefix="upl_")))
    monkeypatch.setattr(main, "_supabase_insert", lambda *a, **k: None)
    monkeypatch.setattr(main, "_process_job_throttled", lambda *a, **k: None)
    monkeypatch.setattr(main, "_notify_admin", lambda *a, **k: None)
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, msg, job=None, severity="error":
                        logs.append((stage, msg, severity)))
    # 🪤 A trava de envio em dobro guarda assinatura em memória entre testes.
    monkeypatch.setattr(main, "_ENVIOS_RECENTES", {})
    # 🪤 `sheet_types` e `sheet_ambientes` têm `Form(default=[])` na assinatura:
    # chamada direta recebe o OBJETO Form, não a lista, e a rota estoura num
    # `len()`. Quem chama por fora do FastAPI passa as listas na mão.
    resp = asyncio.run(main.process_files(
        _ReqUpload(), None, files=[_Upload(n) for n in nomes],
        sheet_types=[], sheet_ambientes=[],
        project_name="LUANA", user_id="u1", user_email="cliente-nn@example.com",
        user_total_area=area, user_pe_direito=pe_direito))
    return resp, logs


# ── A tela: o aviso RENDERIZADO, não a string no dashboard.html ───────────
# 🪤 06/09 — a metade "o site mostra" deste guarda era
# `"data.aviso_repetido" in site`: substring do dashboard.html inteiro. Ler a
# chave e não renderizar nada passava verde, e o cliente ficava sem o aviso.
# Aqui o JS de verdade RODA: o despacho (`if (data.aviso_repetido) ...`) e o
# `mostrarAvisoAec` que monta o HTML, com a resposta que o backend acabou de
# devolver na mão.
from _navegador import atributos, bloco_a_partir_de, montar, rodar  # noqa: E402


def _tela_do_envio(resp_do_backend):
    """Roda o dashboard de verdade com a resposta do upload e devolve o que a
    caixa de aviso ficou mostrando."""
    import json as _json
    site = _site("dashboard.html")
    k = site.index("currentJobId = data.job_id;")
    i = site.rindex("const data = await res.json();", 0, k)
    fim = site.index("\n", site.index("if (data.aviso_area)", k))
    despacho = site[i:fim]
    # 🧪 controle do recorte: janela errada mediria outra coisa em silêncio.
    assert "aviso_repetido" in despacho and len(despacho) < 3000, despacho[:200]
    caixa = atributos(site, "aviso-aec")
    assert caixa, "o id 'aviso-aec' sumiu do dashboard — o JS escreve nele"
    from _navegador import sem_await
    js = [montar([{"id": "aviso-aec", "tag": caixa["tag"],
                   "attrs": caixa["attrs"], "html": ""}]),
          "_ligarTelemetria();",
          "var currentJobId = null, userCreditsCents = 0;",
          "var DADOS = %s;" % _json.dumps(resp_do_backend, ensure_ascii=False),
          "var res = { json: function () { return DADOS; } };",
          bloco_a_partir_de(site, "function mostrarAvisoAec(", "dashboard.html",
                            fecho=""),
          "(function () { %s })();" % sem_await(despacho)]
    return rodar(js, "({html: document.getElementById('aviso-aec').innerHTML,"
                     " visivel: _visivel('aviso-aec')})")


# 🔑 As três alavancas que o aviso existe pra oferecer. O pé-direito é a maior:
# medido em 26/08, informar derruba a fatia de linha em branco de 59,5% pra
# 27,3% — e era exatamente o que faltava no caso de 01/09.
_ALAVANCAS = ("PÉ-DIREITO", "ÁREA TOTAL", "DXF")

# 🪤 06/09 — o guarda antigo conferia `av["titulo"] and av["texto"]`: pura
# truthiness. O texto tem um FALLBACK ("abra a revisão do projeto e preencha as
# linhas que faltam") que mantém a chave preenchida mesmo com `_saidas` vazia,
# então as três alavancas podiam sumir inteiras e o aviso continuava
# "existindo". Cada linha aqui varia uma dimensão que o fixture não variava:
# o que ele JÁ informou, e se ele mandou o CAD junto.
_CENARIOS = [
    # rótulo, pd_antes, area_antes, pd_agora, area_agora, extras, alavancas
    ("nada_informado_so_pdf", None, None, 0, 0, [],
     ("PÉ-DIREITO", "ÁREA TOTAL", "DXF")),
    ("ja_tinha_pe_direito", 2.7, None, 2.7, 0, [],
     ("ÁREA TOTAL", "DXF")),
    ("ja_tinha_area", None, 190.0, 0, 190.0, [],
     ("PÉ-DIREITO", "DXF")),
    ("mandou_o_dxf_junto", None, None, 0, 0, ["planta geral.dxf"],
     ("PÉ-DIREITO", "ÁREA TOTAL")),
    ("nada_a_oferecer", 2.7, 190.0, 2.7, 190.0, ["planta geral.dxf"], ()),
]


@pytest.mark.parametrize("rotulo,pd_antes,area_antes,pd_agora,area_agora,"
                         "extras,alavancas", _CENARIOS,
                         ids=[c[0] for c in _CENARIOS])
def test_o_upload_devolve_o_aviso_e_o_site_mostra(
        monkeypatch, tmp_path, rotulo, pd_antes, area_antes, pd_agora,
        area_agora, extras, alavancas):
    """🩸 O caso do cliente-42, de ponta a ponta: reenviou o mesmo caderno, a
    RESPOSTA do upload traz o aviso — e o aviso diz O QUE MUDA.

    🪤 "existe" não basta. Aviso que só diz "você repetiu" é reclamação; o
    valor está na saída que ele oferece, e a saída depende do que ESTE cliente
    já informou. Cada cenário cobra as alavancas que cabem nele e proíbe as
    que não cabem — oferecer 'informe o pé-direito' pra quem acabou de
    informar é o mesmo tipo de mentira que o aviso existe pra evitar."""
    _cenario(monkeypatch, CADERNO, tinha_pd=pd_antes, tinha_area=area_antes)
    nomes = CADERNO + list(extras)
    resp, logs = _chamar_upload(monkeypatch, nomes, pe_direito=pd_agora,
                                area=area_agora, tmp_path=tmp_path)
    av = resp.get("aviso_repetido")
    assert av, "o aviso não sai do backend — a resposta foi %r" % sorted(resp)
    assert av["job_anterior"] == "144c1f04"
    assert av["arquivos_iguais"] == 6 and av["arquivos_enviados"] == len(nomes)
    assert any(s == "upload:projeto-repetido" for s, _m, _sev in logs), (
        "não vira linha em error_log: %r" % [s for s, _m, _sev in logs])

    texto = av["texto"]
    # Conteúdo, não presença: o aviso conta o que aconteceu com ESTE envio.
    assert "%d dos %d arquivos" % (6, len(nomes)) in texto, texto
    for alavanca in _ALAVANCAS:
        if alavanca in alavancas:
            assert alavanca in texto, (
                "%s: o aviso não oferece a alavanca %s — sem ela ele só diz "
                "'você repetiu'. Texto: %r" % (rotulo, alavanca, texto))
        else:
            assert alavanca not in texto, (
                "%s: o aviso manda informar %s, que este cliente JÁ informou "
                "(ou já mandou) — conselho falso. Texto: %r"
                % (rotulo, alavanca, texto))
    if not alavancas:
        # 🔑 O fallback é legítimo AQUI e só aqui: quando não sobrou alavanca.
        assert "abra a revisão do projeto" in texto, texto

    # E a tela mostra: o JS do dashboard roda com esta resposta na mão.
    tela = _tela_do_envio(resp)
    assert tela["visivel"], (
        "%s: a caixa de aviso continuou escondida — o backend avisou e o "
        "cliente não viu" % rotulo)
    assert av["titulo"] in tela["html"], (
        "%s: o título do aviso não chegou à tela" % rotulo)
    for alavanca in alavancas:
        assert alavanca in tela["html"], (
            "%s: a alavanca %s morreu entre o JSON e a tela" % (rotulo, alavanca))


def test_CONTROLE_a_tela_do_envio_sabe_ficar_MUDA():
    """🧪 Controle positivo do renderizador: sem `aviso_repetido` na resposta
    a caixa fica escondida e vazia. Sem isto, o guarda de cima poderia estar
    lendo uma caixa que aparece sempre."""
    tela = _tela_do_envio({"job_id": "j1", "status": "queued"})
    assert not tela["visivel"] and tela["html"].strip() == "", tela


def test_CONTROLE_projeto_novo_nao_leva_aviso_na_resposta(monkeypatch, tmp_path):
    """🧪 O outro lado: se a resposta trouxesse o aviso sempre, o teste acima
    passaria com a trava quebrada."""
    _cenario(monkeypatch, CADERNO)
    outros = ["casa da praia - planta.pdf", "casa da praia - corte.pdf",
              "casa da praia - fachada.pdf", "casa da praia - cobertura.pdf"]
    resp, logs = _chamar_upload(monkeypatch, outros, tmp_path=tmp_path)
    assert "aviso_repetido" not in resp, (
        "acusou repetição num projeto novo — ofende quem está mandando "
        "trabalho de verdade")
    assert resp.get("job_id") and resp.get("status") == "queued", resp


def test_o_aviso_NAO_promete_resultado_igual():
    """🚫 O motor não é determinístico. Prometer número igual e entregar
    diferente destrói a confiança que o aviso existe pra construir."""
    limpo = "\n".join(l for l in _fonte("main.py").splitlines()
                      if not l.lstrip().startswith("#"))
    i = limpo.index('resp["aviso_repetido"]')
    trecho = limpo[i:i + 1600].lower()
    for proibida in ("mesmo resultado", "resultado igual", "não vai mudar nada",
                     "vai dar a mesma"):
        assert proibida not in trecho, (
            "o aviso promete determinismo que o motor não tem: %r" % proibida)


def test_o_aviso_diz_O_QUE_MUDA():
    """Aviso que só diz 'você repetiu' é reclamação. O valor está na saída."""
    limpo = "\n".join(l for l in _fonte("main.py").splitlines()
                      if not l.lstrip().startswith("#"))
    i = limpo.index('resp["aviso_repetido"]')
    trecho = limpo[max(0, i - 2200):i + 1600]
    assert "PÉ-DIREITO" in trecho, "não oferece a maior alavanca (pé-direito)"
    assert "ÁREA TOTAL" in trecho
    assert "DXF" in trecho


def test_o_site_ESCAPA_o_texto_do_aviso():
    """🚨 O texto passou a carregar o NOME DO PROJETO, que é dado do cliente,
    e o renderizador insere como HTML. Sem escapar, um projeto chamado
    '<img onerror=...>' vira script na tela de quem enviou."""
    site = _site("dashboard.html")
    i = site.index("function mostrarAvisoAec")
    trecho = site[i:i + 3200]      # a função cresceu; janela curta dava falso negativo
    assert "const esc" in trecho, "o renderizador não tem função de escape"
    assert "${esc(t)}" in trecho, "o corpo do aviso entra sem escapar"


def test_CONTROLE_a_checagem_do_site_sabe_REPROVAR():
    """🧪 Sem isto o teste acima passaria com o escape desligado."""
    falso = "function mostrarAvisoAec(av, cor) { return `<p>${t}</p>`; }"
    assert "${esc(t)}" not in falso
