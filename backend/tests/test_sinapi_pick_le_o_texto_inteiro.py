# -*- coding: utf-8 -*-
"""A IA do `sinapi_pick` tem que ENXERGAR o que separa um código do outro.

🩸 27/09/2026 — `pick_best_batch` mandava à IA só `[:110]` de cada candidato e
do item. O kit de porta COM fechadura (91314) e o SEM fechadura (91320) chegavam
IGUAIS letra por letra: a diferença começa no 111º caractere. Na base toda,
2.835 dos 10.284 códigos eram gêmeos de outro pro que a IA via (mesmo texto
visível, mesma unidade) — ela escolhia entre eles no chute.

Os textos abaixo são descrições OFICIAIS da base SINAPI (catálogo público da
Caixa), copiadas como estão, com o bordão do fim. Nada aqui é texto de cliente.

Todos os testes rodam a FUNÇÃO REAL (`pick_best_batch` + `call_with_retry`) e
leem o prompt que chegaria à API — não a função auxiliar isolada.
"""
import os
import re
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import llm_retry  # noqa: E402
import sinapi_matcher  # noqa: E402

KIT_COM_FECHADURA = (
    "91314", "KIT DE PORTA DE MADEIRA PARA PINTURA, SEMI-OCA (LEVE OU MÉDIA), "
    "PADRÃO POPULAR, 80X210CM, ESPESSURA DE 3,5CM, ITENS INCLUSOS: DOBRADIÇAS, "
    "MONTAGEM E INSTALAÇÃO DO BATENTE, FECHADURA COM EXECUÇÃO DO FURO - "
    "FORNECIMENTO E INSTALAÇÃO. AF_10/2025", "UN")
KIT_SEM_FECHADURA = (
    "91320", "KIT DE PORTA DE MADEIRA PARA PINTURA, SEMI-OCA (LEVE OU MÉDIA), "
    "PADRÃO POPULAR, 80X210CM, ESPESSURA DE 3,5CM, ITENS INCLUSOS: DOBRADIÇAS, "
    "MONTAGEM E INSTALAÇÃO DO BATENTE, SEM FECHADURA - FORNECIMENTO E "
    "INSTALAÇÃO. AF_10/2025", "UN")
CORTA_FOGO = (
    "106139", "PORTA CORTA-FOGO 80X210X5CM - FORNECIMENTO E INSTALAÇÃO. AF_10/2025",
    "UN")
ABRIGO_HIDROMETRO = (
    "104994", "CAIXA DE EMBUTIR EM POLICARBONATO PARA ABRIGO DE HIDRÔMETRO - "
    "FORNECIMENTO E INSTALAÇÃO (EXCLUSIVE HIDRÔMETRO). AF_03/2024", "UN")
# Os dois mais longos que só diferem no FIM (311 e 305 car.): um teto de 240,
# que parecia folgado, ainda deixava estes dois gêmeos.
USINA_DEPRECIACAO = (
    "106089", "USINA DE LAMA ASFÁLTICA, PROD 30 A 50 T/H, SILO DE AGREGADO 7 M3, "
    "RESERVATÓRIOS PARA EMULSÃO E ÁGUA DE 2,3 M3 CADA, MISTURADOR TIPO PUG MILL "
    "MONTADA SOBRE CAVALO MECÂNICO TRAÇÃO 4 X 2, PESO BRUTO 16000 KG, CAPACIDADE "
    "MÁXIMA DE TRAÇÃO DE 36000 KG, POTÊNCIA 286 CV, EXCLUSIVE SEMIREBOQUE - "
    "DEPRECIAÇÃO. AF_08/2025", "H")
USINA_JUROS = (
    "106090", "USINA DE LAMA ASFÁLTICA, PROD 30 A 50 T/H, SILO DE AGREGADO 7 M3, "
    "RESERVATÓRIOS PARA EMULSÃO E ÁGUA DE 2,3 M3 CADA, MISTURADOR TIPO PUG MILL "
    "MONTADA SOBRE CAVALO MECÂNICO TRAÇÃO 4 X 2, PESO BRUTO 16000 KG, CAPACIDADE "
    "MÁXIMA DE TRAÇÃO DE 36000 KG, POTÊNCIA 286 CV, EXCLUSIVE SEMIREBOQUE - "
    "JUROS. AF_08/2025", "H")


# ── Dublês ──────────────────────────────────────────────────────────────────
class _Bloco:
    def __init__(self, texto):
        self.text = texto
        self.type = "text"


class _RespostaFalsa:
    def __init__(self):
        self.content = [_Bloco('[{"i": 0, "codigo": null}]')]
        self.stop_reason = "end_turn"
        self.usage = None
        self.model = "claude-haiku-4-5-20251001"


class _ClienteFalso:
    def __init__(self, chamadas):
        self.messages = self
        self._chamadas = chamadas

    # 🪤 `**k` de propósito: parâmetro novo no call site não pode desarmar o
    # guarda em silêncio (feedback_duble_com_assinatura_exata_desarma_calado).
    def create(self, **k):
        self._chamadas.append(k)
        return _RespostaFalsa()


def _prompt_do_pick(monkeypatch, descricao_item, candidatos):
    """Roda o `pick_best_batch` REAL e devolve o prompt que chegaria à API."""
    chamadas = []
    monkeypatch.setenv("LLM_CACHE_TELEMETRIA", "0")
    monkeypatch.setattr(llm_retry, "_gravar_uso", lambda **k: None)
    monkeypatch.setattr(sinapi_matcher, "_client", lambda: _ClienteFalso(chamadas))
    item = {"description": descricao_item, "unit": "un",
            "candidates": [{"codigo": c, "descricao": d, "unidade": u}
                           for c, d, u in candidatos]}
    sinapi_matcher.pick_best_batch([item], job_id="teste")
    assert len(chamadas) == 1, "esperava 1 chamada à IA: %d" % len(chamadas)
    return chamadas[0]["messages"][0]["content"]


def _o_que_a_ia_le(prompt, codigo):
    """O texto do candidato `codigo` como aparece no prompt (sem a unidade)."""
    m = re.search(r"^\s+- %s: (.*) \[un: [^\]]*\]$" % re.escape(codigo), prompt, re.M)
    assert m, "candidato %s não está no prompt:\n%s" % (codigo, prompt)
    return m.group(1)


# ── O caso que abriu a investigação ─────────────────────────────────────────
def test_a_ia_ve_a_diferenca_entre_o_kit_COM_e_o_SEM_fechadura(monkeypatch):
    prompt = _prompt_do_pick(monkeypatch, "Porta de madeira 80x210 com fechadura",
                             [KIT_COM_FECHADURA, KIT_SEM_FECHADURA])
    com = _o_que_a_ia_le(prompt, "91314")
    sem = _o_que_a_ia_le(prompt, "91320")
    assert com != sem, (
        "a IA recebe os kits COM e SEM fechadura com o MESMO texto — escolhe no "
        "chute:\n  91314: %s\n  91320: %s" % (com, sem))
    assert "FECHADURA COM EXECUÇÃO DO FURO" in com, com
    assert "SEM FECHADURA" in sem, sem


def test_o_item_do_cliente_chega_inteiro(monkeypatch):
    """O corte valia pro item também: 56,5% das descrições de item passam de
    110 car., e o detalhe que decide ("com fechadura") costuma vir no fim."""
    item = ("Porta de madeira semi-oca para pintura, 80x210cm, espessura 3,5cm, "
            "padrão popular, com batente, dobradiças e fechadura com execução do furo")
    assert len(item) > 110, "o item do teste precisa passar do corte antigo"
    prompt = _prompt_do_pick(monkeypatch, item, [KIT_COM_FECHADURA])
    assert "ITEM: %s [un:" % item in prompt, (
        "o item não chegou inteiro à IA:\n%s" % prompt)


def test_o_bordao_do_FIM_sai(monkeypatch):
    """O selo de versão (AF_10/2025) e o "- FORNECIMENTO E INSTALAÇÃO" do fim não
    separam uma composição da outra: medido na base toda, tirá-los não cria
    gêmeo nenhum. Sem eles a IA lê 119 car. em média por candidato em vez de
    138 — é o que segura o custo de ler o texto inteiro."""
    prompt = _prompt_do_pick(monkeypatch, "Porta corta-fogo 80x210", [CORTA_FOGO])
    assert _o_que_a_ia_le(prompt, "106139") == "PORTA CORTA-FOGO 80X210X5CM", (
        _o_que_a_ia_le(prompt, "106139"))


def test_CONTROLE_o_que_nao_e_bordao_fica(monkeypatch):
    """Só sai o bordão NO FIM. "(EXCLUSIVE HIDRÔMETRO)" muda o que está sendo
    orçado — se a limpeza comer isso, ela passou a apagar informação."""
    prompt = _prompt_do_pick(monkeypatch, "Abrigo para hidrômetro", [ABRIGO_HIDROMETRO])
    lido = _o_que_a_ia_le(prompt, "104994")
    assert lido.endswith("FORNECIMENTO E INSTALAÇÃO (EXCLUSIVE HIDRÔMETRO)"), lido
    assert "AF_" not in lido, lido


def test_os_dois_mais_longos_que_so_diferem_no_fim_nao_viram_gemeos(monkeypatch):
    """Guarda do TETO: um corte em 240 car. parecia folgado e ainda deixava 20
    códigos gêmeos na base — estes dois entre eles."""
    prompt = _prompt_do_pick(monkeypatch, "Usina de lama asfáltica",
                             [USINA_DEPRECIACAO, USINA_JUROS])
    dep = _o_que_a_ia_le(prompt, "106089")
    jur = _o_que_a_ia_le(prompt, "106090")
    assert dep != jur, "depreciação e juros chegaram iguais à IA:\n%s" % dep
    assert dep.endswith("DEPRECIAÇÃO") and jur.endswith("JUROS"), (dep, jur)


def test_o_teto_segura_texto_patologico(monkeypatch):
    """O teto não corta nada da base de hoje (a maior composição tem 324 car.
    sem o bordão); ele existe pra um texto absurdo não inflar o prompt 60×."""
    enorme = ("CODIGO DE TESTE", "X" * 5000, "UN")
    prompt = _prompt_do_pick(monkeypatch, "Y" * 5000, [enorme])
    lido = _o_que_a_ia_le(prompt, "CODIGO DE TESTE")
    assert len(lido) == sinapi_matcher._TETO_TEXTO_IA, len(lido)
    assert "Y" * (sinapi_matcher._TETO_TEXTO_IA + 1) not in prompt
