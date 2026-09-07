# -*- coding: utf-8 -*-
"""A sombra não repete, dentro do servidor e sem teto, a página que matou o filho.

🔬 05/09/2026, PASSO 7 do estudo do teto. A medição vetorial de PDF roda em
DOIS lugares: (A) num filho com RLIMIT_AS de 2 GB (promoção) e (B) na sombra,
uma thread DENTRO do processo do servidor, SEM teto. Quando o filho morre de
memória, a sombra refaz a mesma página no pai — hoje a A08 do cliente-39 rodou
assim 3 vezes e o servidor sobreviveu; mas o pai (300-400 MB) + a sombra da
página que estourou 2 GB + o filho do próximo job (até 2 GB) num contêiner de
4 GB é exatamente o risco de 03/09 (contêiner a 3,1 GB, site fora por 2 min).

Regra: página cujo filho morreu por MEMÓRIA (rc≠0 ou MemoryError engolido,
motivos "processo"/"memoria") NÃO vai à sombra — e o skip fica registrado
("recusada de propósito" não é silêncio). Página perdida por TEMPO continua
indo: a sombra é hoje a única que mede além dos 75 s.

🧪 Controles: sem `pular` a sombra mede tudo como antes (o teste antigo
test_sombras_nao_perdem_evidencia segue verde); página por tempo NÃO é pulada.
"""
import json
import os
import sys
import textwrap

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)
sys.path.insert(0, _AQUI)

import pdf_vector as pv  # noqa: E402
from _corpo import fonte, sem_comentarios  # noqa: E402

_SRC_MAIN = sem_comentarios(fonte("main.py"))


def _roda(monkeypatch, tmp_path, paginas, pular):
    """_run de verdade: sleep anulado, _measure_page falso, log capturado."""
    monkeypatch.setattr(pv.time, "sleep", lambda *_: None)
    medidas = []

    def _mp(pdf, page, key):
        medidas.append((pdf, page))
        return {"file": os.path.basename(pdf), "page": page, "scale": 100.0, "n_rooms": 2, "rooms_m2": 40.0}
    monkeypatch.setattr(pv, "_measure_page", _mp)
    logs = []
    pv._run(paginas, "job-teste", "chave-fake", lambda *a, **k: logs.append(a), pular=pular)
    payload = next((json.loads(a[1]) for a in logs if a[0] == "pdfvec:shadow" and '"n"' in a[1]), None)
    return medidas, payload


def _pdfs(tmp_path, n):
    out = []
    for i in range(n):
        f = tmp_path / f"p{i}.pdf"
        f.write_bytes(b"%PDF-1.4 x")
        out.append(str(f))
    return out


# ── a regra ────────────────────────────────────────────────────────────────
def test_a_pagina_que_matou_o_filho_NAO_e_medida_e_o_skip_fica_registrado(monkeypatch, tmp_path):
    a, b = _pdfs(tmp_path, 2)
    paginas = [(a, "a.pdf", "x", 0), (b, "b.pdf", "x", 0)]
    medidas, payload = _roda(monkeypatch, tmp_path, paginas, pular={(a, 0)})
    assert medidas == [(b, 0)], f"a sombra mediu a página proibida: {medidas}"
    assert payload and payload["n"] == 2
    skips = [p.get("skip") for p in payload["pages"] if p.get("skip")]
    assert skips == ["filho morreu por memória — não repetir no servidor"], payload


def test_so_a_pagina_certa_e_pulada_nao_o_arquivo_inteiro(monkeypatch, tmp_path):
    (a,) = _pdfs(tmp_path, 1)
    paginas = [(a, "a.pdf", "x", 0), (a, "a.pdf", "x", 1)]
    medidas, _ = _roda(monkeypatch, tmp_path, paginas, pular={(a, 0)})
    assert medidas == [(a, 1)]


# ── controles ─────────────────────────────────────────────────────────────
def test_CONTROLE_sem_pular_mede_tudo_como_antes(monkeypatch, tmp_path):
    a, b = _pdfs(tmp_path, 2)
    paginas = [(a, "a.pdf", "x", 0), (b, "b.pdf", "x", 0)]
    medidas, payload = _roda(monkeypatch, tmp_path, paginas, pular=None)
    assert medidas == [(a, 0), (b, 0)]
    assert not any(p.get("skip") for p in payload["pages"])


def test_CONTROLE_shadow_measure_async_repassa_o_pular(monkeypatch, tmp_path):
    (a,) = _pdfs(tmp_path, 1)
    recebido = {}

    class _T:
        def __init__(self, target=None, args=(), daemon=None, name=None):
            recebido["args"] = args

        def start(self):
            pass
    monkeypatch.setattr(pv.threading, "Thread", _T)
    monkeypatch.delenv("PDFVEC_SHADOW", raising=False)
    pv.shadow_measure_async([(a, "a.pdf", "x", 0)], "job", "k", lambda *a, **k: None, pular={(a, 0)})
    assert recebido["args"][4] == {(a, 0)}, "o conjunto a pular não chegou na thread"


_INI_SOMBRA = "            from pdf_vector import shadow_measure_async"
_FIM_SOMBRA = "        except Exception as _sve:"


def _chamar_a_sombra(monkeypatch, falhas):
    """RODA o código de produção que decide o que a sombra NÃO vai refazer, e
    devolve exatamente o que chegou em `shadow_measure_async`."""
    src = fonte("main.py")
    assert src.count(_INI_SOMBRA) == 1 and src.count(_FIM_SOMBRA) == 1
    a = src.index(_INI_SOMBRA)
    codigo = textwrap.dedent(src[a:src.index(_FIM_SOMBRA, a)])
    recebido = {}

    def _falsa(*args, **kwargs):
        recebido["args"] = args
        recebido["kwargs"] = kwargs
    monkeypatch.setattr(pv, "shadow_measure_async", _falsa)
    ns = {"page_units": [("/tmp/a.pdf", "a.pdf", "x", 0)], "job_id": "job-teste",
          "api_key": "chave", "_log_error": lambda *a, **k: None,
          "_pdfvec_falhas": list(falhas)}
    exec(compile(codigo, "sombra-pai", "exec"), ns)
    assert recebido, "a sombra nem foi chamada"
    return recebido, ns.get("_pular_sombra")


def _falha(motivo, path="/tmp/A08.pdf", pagina=7, **extra):
    d = {"prancha": "A08", "arquivo": "A08.pdf", "motivo": motivo, "pagina": pagina}
    if path is not None:
        d["pdf_path"] = path
    d.update(extra)
    return d


def test_a_sombra_pula_a_pagina_que_matou_o_filho_e_SO_ela(monkeypatch):
    """🚨 EXECUTA o bloco do pai e olha o conjunto que sai. O guarda antigo lia
    900 caracteres do fonte antes da chamada, procurando o texto
    `in ("processo", "memoria")` — trocar o `and f.get("pdf_path")` por `or`
    deixava o texto idêntico e passava a pular também a página perdida por
    TEMPO, que é justamente a única que a sombra ainda consegue medir."""
    recebido, pular = _chamar_a_sombra(monkeypatch, [
        _falha("processo", "/tmp/A08.pdf", 7),
        _falha("memoria", "/tmp/A09.pdf", 2),
        _falha("tempo", "/tmp/A10.pdf", 3),
        _falha("JSONDecodeError", "/tmp/A11.pdf", 0),
    ])
    assert pular == {("/tmp/A08.pdf", 7), ("/tmp/A09.pdf", 2)}, (
        "o conjunto a pular saiu %r. Página perdida por TEMPO tem que continuar "
        "indo à sombra — ela é hoje a única que mede além dos 75 s." % (pular,))
    assert recebido["kwargs"].get("pular") == pular, (
        "a sombra foi chamada SEM o `pular=` (recebeu %r / %r) — ela vai refazer, "
        "dentro do servidor e sem teto, a página que acabou de estourar 2 GB"
        % (recebido["args"], recebido["kwargs"]))


def test_CONTROLE_sem_falha_de_memoria_a_sombra_mede_tudo(monkeypatch):
    """🧪 'Vazio não é falhou': sem morte por memória, nada é pulado."""
    recebido, pular = _chamar_a_sombra(monkeypatch, [_falha("tempo", "/tmp/A10.pdf", 3)])
    assert pular == set()
    assert recebido["kwargs"].get("pular") == set()


def test_CONTROLE_job_sem_PDF_nao_derruba_o_processo(monkeypatch):
    """🪤 `_pdfvec_falhas` só existe se o laço de PDF rodou — o `except NameError`
    é o que segura job só-DXF."""
    src = fonte("main.py")
    a = src.index(_INI_SOMBRA)
    codigo = textwrap.dedent(src[a:src.index(_FIM_SOMBRA, a)])
    recebido = {}
    monkeypatch.setattr(pv, "shadow_measure_async",
                        lambda *ar, **kw: recebido.update(kwargs=kw))
    ns = {"page_units": [], "job_id": "j", "api_key": "k", "_log_error": lambda *a, **k: None}
    exec(compile(codigo, "sombra-pai", "exec"), ns)      # sem `_pdfvec_falhas`
    assert recebido["kwargs"].get("pular") == set()


def test_toda_falha_do_filho_carrega_pdf_path_e_pagina():
    assert _SRC_MAIN.count('"pdf_path": pdf_path, "pagina": page_index,') == 3, (
        "os 3 appends de _pdfvec_falhas (processo, memoria, tempo/exceção) têm que dizer QUAL página")


# ══════════════════════════════════════════════════════════════════════════
#  O CONTRATO ENTRE OS DOIS LADOS
#
#  🔬 07/09/2026. Lacuna do cético: o conjunto de motivos é um contrato entre
#  pontos DISTANTES de main.py — três `append` lá em cima (~10513/10527/10710)
#  escrevem o motivo, e o filtro da sombra (~13037) decide por ele. Os testes
#  acima só rodavam o lado do CONSUMO, com os motivos digitados no próprio
#  teste. Renomear "memoria" pra "oom" no `append` deixava tudo verde e a
#  página que acabou de estourar 2 GB voltava a rodar dentro do servidor.
#  Agora os DOIS lados executam: o produtor grava, o consumidor filtra.
# ══════════════════════════════════════════════════════════════════════════
import subprocess  # noqa: E402

import main  # noqa: E402

#: (âncora inicial, âncora final) de cada `append` real de `_pdfvec_falhas`.
_PRODUTORES = {
    "processo": ('                    if _pr.returncode != 0:',
                 '                    _vm = _jv.loads('),
    "memoria": ('                    if _tipo_saida == "memoria":',
                '                    elif _tipo_saida == "sem_escala":'),
    "excecao": ('                    _eh_tempo = isinstance(_ve, _sp.TimeoutExpired)',
                '                    print(f"[pdfvec-promo] '),
}


def _produz(qual, **extra):
    """RODA o `append` de produção e devolve a linha que ele grava."""
    src = fonte("main.py")
    ini, fim = _PRODUTORES[qual]
    assert src.count(ini) == 1, (
        "a âncora inicial do produtor %r não é única — o bloco mudou de forma "
        "e este guarda passou a auditar outra coisa" % qual)
    a = src.index(ini)
    codigo = textwrap.dedent(src[a:src.index(fim, a)])
    falhas = []
    ns = {"_pdfvec_falhas": falhas, "_log_error": lambda *a, **k: None,
          "_stem": "A08", "filename": "A08.pdf", "job_id": "job-teste"}
    ns.update(extra)
    exec(compile(codigo, "produtor-%s" % qual, "exec"), ns)
    assert len(falhas) == 1, (
        "o bloco %r não gravou UMA falha (gravou %d) — sem isso o contrato "
        "com a sombra não pode ser medido" % (qual, len(falhas)))
    return falhas[0]


class _Filho:
    def __init__(self, rc):
        self.returncode = rc
        self.stderr = "MemoryError\n  File pdfvec_x.py, line 1"
        self.stdout = ""


def _as_quatro_falhas_reais():
    """As quatro falhas como o PAI as grava — nada digitado à mão aqui."""
    # 🔗 O tipo vem do classificador REAL: classificador → append → filtro.
    tipo, det = main._saida_do_filho_pdfvec(0, {"err_rooms": "MemoryError: ..."})
    assert tipo == "memoria", (
        "`_saida_do_filho_pdfvec` parou de classificar MemoryError engolido "
        "como 'memoria' (devolveu %r) — o append nem chega a rodar" % (tipo,))
    return [
        _produz("processo", _pr=_Filho(-9),
                pdf_path="/tmp/A08.pdf", page_index=7),
        _produz("memoria", _tipo_saida=tipo, _det_saida=det,
                pdf_path="/tmp/A09.pdf", page_index=2),
        _produz("excecao", _sp=subprocess,
                _ve=subprocess.TimeoutExpired(["python"], 75),
                pdf_path="/tmp/A10.pdf", page_index=3),
        _produz("excecao", _sp=subprocess, _ve=ValueError("JSON quebrado"),
                pdf_path="/tmp/A11.pdf", page_index=0),
    ]


def test_o_motivo_que_o_PAI_GRAVA_e_o_que_a_SOMBRA_RECONHECE(monkeypatch):
    """🚨 O contrato inteiro, executado ponta a ponta.

    Renomear o motivo em QUALQUER um dos três `append` (ou apertar a tupla do
    filtro) quebra aqui — e só aqui, porque os outros testes escrevem os
    motivos eles mesmos.
    """
    falhas = _as_quatro_falhas_reais()
    motivos = [f.get("motivo") for f in falhas]
    _, pular = _chamar_a_sombra(monkeypatch, falhas)
    assert pular == {("/tmp/A08.pdf", 7), ("/tmp/A09.pdf", 2)}, (
        "o pai grava os motivos %r e a sombra montou o skip %r. As duas mortes "
        "por MEMÓRIA (filho com rc≠0 e MemoryError engolido) TÊM que ser "
        "puladas — a sombra roda no processo do servidor, sem teto. E a perda "
        "por TEMPO tem que continuar indo: é a única que mede além dos 75 s."
        % (motivos, pular))


def test_o_lado_da_MEMORIA_grava_a_pagina_que_o_filtro_procura():
    """🪤 O de 'processo' já estava coberto no arquivo do teto; o de 'memoria'
    não estava em lugar nenhum. Sem `pdf_path`/`pagina` o filtro descarta a
    linha (`and f.get("pdf_path")`) e a página volta pra sombra calada."""
    tipo, det = main._saida_do_filho_pdfvec(0, {"err_views": "MemoryError"})
    linha = _produz("memoria", _tipo_saida=tipo, _det_saida=det,
                    pdf_path="/tmp/A09.pdf", page_index=2)
    assert linha.get("pdf_path") == "/tmp/A09.pdf" and linha.get("pagina") == 2, linha


def test_CONTROLE_a_excecao_que_NAO_e_timeout_vira_o_nome_do_erro():
    """Controle do produtor: os dois ramos do `if _eh_tempo` são exercitados —
    sem isso o teste acima poderia estar medindo só metade do bloco."""
    t = _produz("excecao", _sp=subprocess,
                _ve=subprocess.TimeoutExpired(["python"], 75),
                pdf_path="/tmp/A10.pdf", page_index=3)
    x = _produz("excecao", _sp=subprocess, _ve=ValueError("JSON quebrado"),
                pdf_path="/tmp/A11.pdf", page_index=0)
    assert t["motivo"] != x["motivo"], (
        "timeout e exceção comum saíram com o MESMO motivo (%r) — o diagnóstico "
        "de 31/08 (caso cliente-14) volta a ficar indistinguível" % (t["motivo"],))


def test_CONTROLE_guarda_reprova_a_chamada_antiga():
    antiga = "shadow_measure_async(page_units, job_id, api_key, _log_error)"
    assert "pular=" not in antiga
