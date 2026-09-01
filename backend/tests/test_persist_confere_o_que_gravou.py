# -*- coding: utf-8 -*-
"""O persist não pode AFIRMAR que gravou N sem perguntar ao banco.

🩸 MEDIDO NO ACERVO em 01/09/2026: **24 de 144 jobs concluídos (16,7%) têm
menos linhas em `project_items` do que o `items_count` que o projeto anuncia —
647 itens perdidos**, desde o primeiro job da base (19/04). Nenhum deles deixou
uma linha de erro: o HTTP voltou 2xx e o resto era suposição.

    `_persist_items_to_supabase` montava as linhas, mandava UM POST, e fazia
    `return len(rows)` — o número que ELA MANDOU, nunca o que entrou. Quem
    chamava descartava até esse retorno, e `items_count` virava len(all_items).

Assinatura do estrago: nos 120 jobs sãos o `sort_order` é contíguo 0..N-1; nos
24 afetados ele SEMPRE tem buraco. Caso vivo — job d5e073cf (Flavio Hermolin,
01/09): 50 linhas montadas, 33 no banco, faltando 14,15,18-21,23,30-33,35,40,
42,47-49, numa gravação só. O cliente vê os 50 itens na planilha que baixa e
33 na tela de revisão do site.

🔑 Este guarda NÃO depende de saber a causa (que continua em investigação): ele
compara o que mandamos com o que o banco tem, e grita a diferença. É a família
do [[feedback_escrita_que_falha_calada]] — a mesma que já mordeu em 14/07 (NaN
derrubando o batch inteiro) e em 25/08 (teto de 1000 linhas do PostgREST).

🪤 A contagem usa HEAD + `Prefer: count=exact` e lê o Content-Range, em vez de
baixar as linhas e contar: o PostgREST corta a listagem em 1000 e devolve 200
sem avisar. Contar o que voltou mentiria justamente no job grande — que é onde
a perda acontece.
"""
import io
import os
import sys
import textwrap

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

_INI_CONTA = "def _contar_itens_no_banco(job_id: str):"
_FIM_CONTA = "def _persist_items_to_supabase("
_INI_VERIF = "        _gravadas = _contar_itens_no_banco(job_id)"
_FIM_VERIF = "    except urllib.error.HTTPError as e:"


def _fonte():
    return io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


class _Resp:
    """Resposta HTTP falsa com o header que importa."""
    def __init__(self, content_range):
        self.headers = {"Content-Range": content_range} if content_range else {}


def _contador(content_range=None, explode=False):
    """Executa O TRECHO REAL de `_contar_itens_no_banco`."""
    src = _fonte()
    assert src.count(_INI_CONTA) == 1, "a âncora do contador mudou"
    i = src.index(_INI_CONTA)
    trecho = src[i:src.index(_FIM_CONTA, i)]

    class _UrlReq:
        Request = staticmethod(lambda *a, **k: type(
            "R", (), {"add_header": lambda self, *_: None})())

        @staticmethod
        def urlopen(*a, **k):
            if explode:
                raise OSError("rede caiu")
            return _Resp(content_range)

    class _UrlErr:
        HTTPError = Exception

    import types
    fake = types.ModuleType("urllib")
    fake.request, fake.error = _UrlReq, _UrlErr
    ns = {"SUPABASE_URL": "http://x", "SUPABASE_KEY": "k",
          "SUPABASE_SERVICE_ROLE_KEY": "s"}
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) \
        else __builtins__.__import__

    def _imp(name, *a, **k):
        if name == "urllib.request":
            sys.modules.setdefault("urllib.request", _UrlReq)
            return fake
        if name == "urllib.error":
            return fake
        return real_import(name, *a, **k)

    ns["__builtins__"] = dict(
        (k, getattr(__builtins__, k, None)) if not isinstance(__builtins__, dict)
        else (k, v) for k, v in (
            __builtins__.items() if isinstance(__builtins__, dict)
            else [(n, getattr(__builtins__, n)) for n in dir(__builtins__)]))
    ns["__builtins__"]["__import__"] = _imp
    exec(compile(trecho, "conta_slice", "exec"), ns)
    return ns["_contar_itens_no_banco"]


# ── O contador ─────────────────────────────────────────────────────────────
def test_le_o_total_do_Content_Range():
    """'0-0/57' quer dizer 57 linhas no banco."""
    assert _contador("0-0/57")("j") == 57


def test_banco_vazio_e_ZERO_e_nao_None():
    """🪤 0 e 'não sei' são coisas MUITO diferentes aqui: 0 dispara o alarme de
    perda total, None diz que a conferência não rodou."""
    assert _contador("*/0")("j") == 0


def test_quando_NAO_da_pra_contar_devolve_None():
    assert _contador(None)("j") is None, "sem Content-Range tem que ser None"
    assert _contador("0-0/nao-numero")("j") is None
    assert _contador(explode=True)("j") is None, "rede caiu tem que ser None"


# ── A verificação dentro do persist ────────────────────────────────────────
def _verificador(gravadas):
    """Executa O TRECHO REAL da verificação, embrulhado numa função."""
    src = _fonte()
    assert src.count(_INI_VERIF) == 1, "a âncora da verificação mudou"
    i = src.index(_INI_VERIF)
    corpo = textwrap.dedent(src[i:src.index(_FIM_VERIF, i)])
    fonte = "def _v(job_id, rows):\n" + textwrap.indent(corpo, "    ")
    logs, supa = [], []
    ns = {
        "_contar_itens_no_banco": lambda _j: gravadas,
        "_log_error": lambda *a, **k: logs.append((a, k)),
        "_supa_log": lambda m: supa.append(m),
    }
    exec(compile(fonte, "verif_slice", "exec"), ns)
    return ns["_v"], logs, supa


def test_perda_vira_ERRO_CRITICO_e_devolve_o_numero_REAL():
    """🩸 O caso do Flavio: mandou 50, entraram 33."""
    v, logs, _ = _verificador(33)
    assert v("d5e073cf", [None] * 50) == 33, (
        "devolveu o número que MANDOU em vez do que entrou")
    assert logs, "perdeu 17 itens e não registrou nada"
    (args, kw) = logs[0]
    assert args[0] == "motor:persist-perdeu-item", args
    assert "17" in args[1], args[1]
    assert kw.get("severity") == "critical", kw


def test_gravacao_completa_NAO_alarma():
    """🧪 Controle: se alarmasse sempre, o alarme não valeria nada."""
    v, logs, supa = _verificador(50)
    assert v("j", [None] * 50) == 50
    assert not logs, "alarmou numa gravação completa: %s" % logs
    assert any("conferido" in m for m in supa)


def test_perda_TOTAL_tambem_alarma():
    v, logs, _ = _verificador(0)
    assert v("j", [None] * 12) == 0
    assert logs and logs[0][1].get("severity") == "critical"


def test_quando_nao_deu_pra_conferir_NAO_afirma_sucesso():
    """🪤 None ≠ 0. Aqui a gente devolve o que mandou (não há o que corrigir)
    mas DECLARA que não conferiu — em vez de fingir que está tudo certo."""
    v, logs, supa = _verificador(None)
    assert v("j", [None] * 20) == 20
    assert logs, "não conferiu e não avisou"
    assert logs[0][0][0] == "motor:persist-nao-conferido"
    assert logs[0][1].get("severity") == "warning"
    assert any("NAO consegui conferir" in m for m in supa)


# ── CONTROLES DE PONTO DE CHAMADA ──────────────────────────────────────────
def test_quem_chama_USA_o_retorno():
    """🪤 Antes o retorno era descartado e `items_count` saía como len(all_items).
    Guarda de ponto de chamada — o controle abaixo prova que sabe reprovar."""
    limpo = "\n".join(l for l in _fonte().splitlines()
                      if not l.lstrip().startswith("#"))
    assert "_n_gravados = _persist_items_to_supabase(job_id, all_items)" in limpo, (
        "o retorno do persist voltou a ser descartado")
    assert '"items_count": _itens_no_banco' in limpo, (
        "items_count voltou a ser o que a gente MANDOU, não o que o banco tem")


def test_CONTROLE_a_checagem_de_chamada_sabe_REPROVAR():
    """🧪 Sem isto, o teste acima passaria com o conserto desligado."""
    falso = "\n".join([
        "        # _n_gravados = _persist_items_to_supabase(job_id, all_items)",
        "        _persist_items_to_supabase(job_id, all_items)",
        '            "items_count": len(all_items),',
    ])
    limpo = "\n".join(l for l in falso.splitlines()
                      if not l.lstrip().startswith("#"))
    assert "_n_gravados = _persist_items_to_supabase" not in limpo, (
        "a checagem aceita a linha COMENTADA — não guarda nada")
    assert '"items_count": _itens_no_banco' not in limpo


def test_o_cliente_e_avisado_da_perda():
    """A perda não pode ficar só no nosso log: quem revisa pelo site precisa
    saber que a planilha tem mais linha do que a tela."""
    limpo = "\n".join(l for l in _fonte().splitlines()
                      if not l.lstrip().startswith("#"))
    assert "não chegaram na tela de revisão do site" in limpo, (
        "a perda não vira aviso pro cliente")
    assert "ESTÃO na planilha em anexo" in limpo, (
        "o aviso não diz onde os itens ainda existem — é a parte acionável")
