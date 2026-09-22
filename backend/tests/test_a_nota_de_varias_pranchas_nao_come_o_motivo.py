# -*- coding: utf-8 -*-
"""A nota "aparece em N pranchas" conta PRANCHA e não apaga o motivo do zero.

🩸 22/09/2026 — jobs ee801b82 e f8d8e6d8 (cliente de 1 dia, NPS 2). Os mesmos
7 PDFs de uma página, de concreto armado. A nota que a consolidação escreve
quando o mesmo serviço aparece em pranchas diferentes:

  · disse "12 pranchas", "14 pranchas", "19 pranchas" num envio de 7 PDFs —
    contava STRINGS de `ref_sheet`, e o hint da IA ("arquivo.pdf (VISTA 3 –
    PLANTA / CORTE)") faz uma folha virar várias;
  · listava cada ITEM cortado em 40 caracteres — a mesma prancha 13 vezes —,
    e a nota passava de 700 caracteres;
  · a honestidade de área escreve o motivo do zero DEPOIS, no fim, e a
    gravação cortava a observação em 1000: 31 das 61 linhas zeradas chegaram
    à tela sem o motivo. A cliente via "Cálculo: … = 0,69 m³" ao lado de um 0.

📏 Alcance (60 dias, sem eval): 622 linhas com a observação cortada em 1000,
571 delas com esta nota; 255 linhas zeradas sem o motivo visível.

Os testes RODAM a consolidação, a honestidade e a gravação de verdade — o banco
é dublado, o resto é o código do motor.
"""
import json
import os
import sys
import urllib.request

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import main  # noqa: E402
from models import BudgetItem, Confidence  # noqa: E402

#: o que a IA escreveu na observação — o "Cálculo" que a cliente via ao lado do 0
_OBS_DA_IA = ("Cálculo: parede do poço Ø2,00 m × h 2,90 m × e 0,20 m = 3,64 m³; "
              "descontada a abertura da tubulação (0,60 × 0,60 × 1,90 = 0,69 m³); "
              "volume lido do corte AA e da planta de fôrma — conferir no quadro.")
#: a frase que a honestidade escreve quando zera — o motivo do zero
_MOTIVO = "NÃO medida"

_PECAS = ["parede do poço de sucção", "laje de fundo da caixa de válvulas",
          "bloco do guindaste", "viga do pórtico", "tampa do poço",
          "pilar do pórtico", "parede da caixa de válvulas",
          "laje de cobertura do poço", "radier da caixa", "cortina do poço",
          "mísula da laje", "parede do reservatório",
          "fundo do poço de drenagem", "viga baldrame do pórtico"]


def _o_caso(obs=_OBS_DA_IA):
    """14 linhas de concreto de DOIS PDFs de uma página — 11 da prancha-B e 3
    da prancha-C —, cada uma com um hint de vista diferente, como a IA grava."""
    itens = []
    for i, peca in enumerate(_PECAS):
        arq = "prancha-B.pdf" if i < 11 else "prancha-C.pdf"
        itens.append(BudgetItem(
            item_num="", description="Concreto estrutural fck 30 MPa — " + peca,
            unit="m³", quantity=round(0.37 + 0.41 * i, 2), observations=obs,
            ref_sheet="%s (VISTA %d – PLANTA / CORTE)" % (arq, i),
            confidence=Confidence("estimado"), discipline="Estrutura"))
    return itens


def _nota(obs):
    i = obs.find("⚠ Este serviço aparece em")
    assert i >= 0, "a nota não saiu: %r" % obs
    return obs[i:obs.index("que não soma.", i) + len("que não soma.")]


# ── a contagem ──────────────────────────────────────────────────────────────
def test_a_nota_conta_PRANCHA_e_nao_variacao_de_hint():
    """🩸 O caso: 14 linhas de 2 PDFs viravam '14 pranchas'."""
    out = main._consolidate_items(_o_caso())
    assert len(out) == 14, "a consolidação apagou linha: %d de 14" % len(out)
    for it in out:
        nota = _nota(it.observations)
        assert "aparece em 2 pranchas" in nota, (
            "a nota contou variações do hint da IA como prancha: %r" % nota)


def test_a_nota_lista_cada_prancha_UMA_vez_e_cabe():
    """A lista repetia a mesma prancha 11 vezes e a nota passava de 700
    caracteres."""
    out = main._consolidate_items(_o_caso())
    nota = _nota(out[0].observations)
    assert nota.count("prancha-B.pdf") == 1 and nota.count("prancha-C.pdf") == 1, nota
    assert "VISTA" not in nota, "o hint da IA voltou pra lista de pranchas: %r" % nota
    assert len(nota) <= 500, "a nota tem %d caracteres: %r" % (len(nota), nota)


def test_prancha_de_PDF_de_varias_paginas_conta_por_pagina():
    """🔑 Em PDF de várias páginas cada página É uma prancha — o "pN" que
    `monta_ref_sheet` põe entra na conta; o hint, não."""
    f = main._prancha_de_verdade
    assert f("caderno.pdf (p3 · VISTA 2 – PLANTA)") == "caderno.pdf (p3)"
    assert f("caderno.pdf (p3)") == f("caderno.pdf (p3 · outro hint)")
    assert f("caderno.pdf (p3)") != f("caderno.pdf (p4)")
    assert f("prancha-B.pdf (VISTA 1 – PLANTA)") == "prancha-B.pdf"
    assert f("") == "" and f(None) == ""


def test_a_nota_resume_quando_ha_muitas_pranchas():
    """Oito pranchas: quatro nomes e o resto em número, sem estourar."""
    itens = []
    for i in range(8):
        itens.append(BudgetItem(
            item_num="", description="Concreto estrutural fck 30 MPa — peça %d" % i,
            unit="m³", quantity=1.0 + i, observations="",
            ref_sheet="prancha-%s.pdf (VISTA %d)" % ("ABCDEFGH"[i], i),
            confidence=Confidence("estimado"), discipline="Estrutura"))
    nota = _nota(main._consolidate_items(itens)[0].observations)
    assert "aparece em 8 pranchas" in nota and "e mais 4" in nota, nota
    nomeadas = sum(nota.count("prancha-%s.pdf" % l) for l in "ABCDEFGH")
    assert nomeadas == 4, "a nota nomeou %d pranchas, não 4: %r" % (nomeadas, nota)
    assert len(nota) <= 500, len(nota)


def test_CONTROLE_mesma_prancha_com_hints_diferentes_NAO_leva_nota():
    """🧪 Duas linhas da MESMA folha, com hints diferentes, não são "cross-
    prancha" — a nota não pode sair (antes saía, com "2 pranchas")."""
    itens = [BudgetItem(item_num="", description="Concreto estrutural fck 30 MPa — radier",
                        unit="m³", quantity=5.6, observations="",
                        ref_sheet="prancha-G.pdf (NÍVEL 1 – PLANTA / CORTE BB)",
                        confidence=Confidence("estimado"), discipline="Estrutura"),
             BudgetItem(item_num="", description="Concreto estrutural fck 30 MPa — laje",
                        unit="m³", quantity=4.1, observations="",
                        ref_sheet="prancha-G.pdf (NÍVEL 2 – PLANTA)",
                        confidence=Confidence("estimado"), discipline="Estrutura")]
    out = main._consolidate_items(itens)
    assert len(out) == 2
    assert not any("aparece em" in (x.observations or "") for x in out), (
        [x.observations for x in out])


# ── o motivo do zero chega à tela ───────────────────────────────────────────
class _Resp(object):
    def __init__(self, dados, headers=None):
        self._b = json.dumps(dados).encode("utf-8")
        self.headers = headers or {}

    def read(self):
        return self._b


class _Banco(object):
    """`project_items` de mentira: guarda o que a gravação MANDOU."""

    def __init__(self):
        self.itens = []

    def rest(self, method, path, params=None, **kw):
        return 200, []

    def urlopen(self, req, timeout=None, **kw):
        tabela = req.full_url.split("/rest/v1/")[-1].partition("?")[0]
        metodo = req.get_method()
        corpo = json.loads(req.data.decode("utf-8")) if getattr(req, "data", None) else None
        if tabela == "project_items":
            if metodo == "HEAD":
                return _Resp([], {"Content-Range": "0-0/%d" % len(self.itens)})
            if metodo == "DELETE":
                self.itens = []
            if metodo == "POST":
                self.itens = [dict(l) for l in (corpo or [])]
            return _Resp([])
        return _Resp([])


def _grava(monkeypatch, itens):
    """Consolida, aplica a honestidade e GRAVA — o caminho do `process_job`."""
    banco = _Banco()
    monkeypatch.setattr(urllib.request, "urlopen", banco.urlopen)
    monkeypatch.setattr(main, "_supa_rest_service", banco.rest)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supa_log", lambda *a, **k: None)
    out = main._consolidate_items(itens)
    main._apply_area_honesty(out, pdfvec_m2=0)
    assert all(x.quantity == 0 for x in out), "controle: m³ de PDF tinha que zerar"
    assert all(_MOTIVO in (x.observations or "") for x in out), (
        "controle: a honestidade não escreveu o motivo em memória")
    main._persist_items_to_supabase("f8d8e6d8", out)
    assert len(banco.itens) == len(out), "a gravação não mandou as linhas"
    return banco.itens


def test_o_caso_o_motivo_do_zero_chega_ao_banco(monkeypatch):
    """🩸 O caso de 22/09, ponta a ponta: com a nota do tamanho certo, a
    observação cabe inteira — cálculo da IA, nota e motivo."""
    for linha in _grava(monkeypatch, _o_caso()):
        obs = linha["observations"]
        assert _MOTIVO in obs, (
            "a linha zerada chegou ao banco SEM o motivo do zero: %r" % obs[-200:])
        assert "0,69 m³" in obs, "o cálculo da IA sumiu"
        assert len(obs) <= 1000


def test_observacao_longa_perde_o_MEIO_e_nao_o_fim(monkeypatch):
    """Quando nem a nota curta salva (a IA escreveu muito — p90 do acervo), a
    gravação corta o meio e guarda o fim, que é onde o motivo está."""
    longa = _OBS_DA_IA + " " + ("Conferir espessura da parede no corte BB. " * 16)
    for linha in _grava(monkeypatch, _o_caso(obs=longa)):
        obs = linha["observations"]
        assert len(obs) <= 1000, len(obs)
        assert _MOTIVO in obs, "o fim foi cortado de novo: %r" % obs[-200:]
        assert obs.startswith("Cálculo: parede do poço"), "a cabeça sumiu"
        assert main._OBS_EMENDA.strip() in obs, "o corte do meio não ficou visível"


def test_CONTROLE_o_corte_antigo_perderia_o_motivo_neste_caso(monkeypatch):
    """🧪 O cenário reproduz o defeito: com o corte `[:1000]` de antes, o
    motivo do zero cai fora. Sem isto, o teste de cima poderia estar passando
    por uma observação que nunca chega a 1000."""
    longa = _OBS_DA_IA + " " + ("Conferir espessura da parede no corte BB. " * 16)
    out = main._consolidate_items(_o_caso(obs=longa))
    main._apply_area_honesty(out, pdfvec_m2=0)
    obs = out[0].observations
    assert len(obs) > 1000 and _MOTIVO not in obs[:1000], len(obs)


def test_observacao_que_cabe_nao_mexe_no_que_ja_cabe():
    f = main._observacao_que_cabe
    assert f("") == "" and f(None) == ""
    curta = "x" * 999 + "."
    assert f(curta) == curta
    longa = "começo. " + "meio " * 400 + "| o veredito final."
    r = f(longa)
    assert len(r) <= 1000 and r.startswith("começo.") and r.endswith("o veredito final.")
