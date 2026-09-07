# -*- coding: utf-8 -*-
"""O motor mediu a área do PDF, mandou a IA usar — e depois apagou.

🚨 26/08/2026, caso **cliente-41** (job das 12:50, cliente novo do dia).
O log conta o filme inteiro:

    12:51  pdfvec:promo         3 ambientes, 13,6 m² medidos da geometria vetorial
                                "SEM prova de cota — injetado como estimado"
    12:52  motor:consenso-area  campo=total_area n=0 leituras=[]
    12:53  motor:honestidade    preenchidos=0 zerados=9

`_apply_area_honesty` só reconhece `origem='dxf_geom'`, então apagou os 9. E
o contador `zerados` só sobe quando a quantidade era **maior que zero** — ou
seja, havia número e ele foi apagado.

A planilha que ele **baixou às 13:20** ficou assim:

    0 m²  Piso cerâmico ou porcelanato        0 m²  Pintura látex acrílica
    0 m²  Forro em gesso acartonado           0 m²  Massa corrida
    0 m²  Parede em alvenaria de bloco        0 m²  Revestimento de banheiro
    0 m²  Parede em drywall                   0 m²  Demolição de paredes
    0 ml  Rodapé

E a observação que sobrou dizia *"Área NÃO medida (lida de PDF por IA, não da
geometria)"* — **falso**: foi medida da geometria vetorial do PDF. As contagens
saíram certas (11 pontos de esgoto, 10 tomadas, 8 luminárias, 6 portas), então
ele recebeu tudo que se conta e nada do que se mede.

🔑 **Não é decisão de produto nova.** A de 12/08 (Hospital 2 de julho, onde 56
ambientes e 1.167 m² viraram ZERO) já definiu: medição de PDF sem prova de cota
VALE, como estimativa com a procedência escrita. O passo de injeção implementa
essa decisão; a regra de honestidade é que não ficava sabendo dela.

🚫 E continua NÃO virando 'confirmado': a escala veio do carimbo, e carimbo é
declaração, não prova — mesma família do "cabeçalho mente a unidade", que já
custou erro de 1000×.
"""
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_M2_MEDIDO = 13.6          # o que o motor vetorial mediu no PDF dele


def _fatia():
    """Roda só o pedaço do main.py com a honestidade (importar o módulo inteiro
    abre conexão com Supabase/Stripe). Mesmo molde de test_area_honesty_pd.py."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = src.index("_RX_SECAO_PILAR")
    i = src.rindex("\n", 0, i) + 1
    j = src.index("\ndef _dedupe_revisoes", i)
    from engine_rules import (AREA_UNITS_HONESTY as _A, FLOOR_M2_UNITS as _F,
                              is_floor_surface as _isf,
                              is_floor_surface_para_criar as _isfc)
    from models import Confidence
    import re as _re
    ns = {"__name__": "honesty_ns", "_AREA_UNITS_HONESTY": _A,
          "_FLOOR_M2_UNITS": _F, "_is_floor_surface": _isf, "_is_floor_surface_criar": _isfc,
          "Confidence": Confidence, "_re_honesty": _re, "_re": _re, "re": _re}
    exec(compile(src[i:j], "main_slice", "exec"), ns)
    return ns


class _Item:
    def __init__(self, description, unit, quantity, observations="", origem=""):
        self.description = description
        self.unit = unit
        self.quantity = quantity
        self.observations = observations
        self.origem = origem
        self.confidence = None


def _piso(q=13.6):
    return _Item("Piso cerâmico ou porcelanato — tipo, dimensão, cor e "
                 "fabricante a confirmar", "m²", q)


def _forro(q=13.6):
    return _Item("Forro em gesso acartonado ou forro modular — tipo, "
                 "espessura a confirmar", "m²", q)


def _valor(it):
    return float(getattr(it, "quantity", 0) or 0)


class _ProjetoDeMentira:
    """O minimo de `project_data` que a fatia do call site toca."""

    def __init__(self, total_area=0, total_area_source="", user_pe_direito=0):
        self.total_area = total_area
        self.total_area_source = total_area_source
        self.user_pe_direito = user_pe_direito
        self.warnings = None


def _fatia_do_call_site():
    """A fatia REAL do `process_job`: do `try:` que le `_pdfvec_area_m2` ate a
    chamada de `_apply_area_honesty`.

    ANCORA no ramo do `except NameError` (nao na linha que a mutacao troca) e
    no fim exato da chamada. Nunca por tamanho fixo.
    """
    import textwrap
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    linhas = src.splitlines(True)
    marca = "_pv_m2 = 0.0          # job sem PDF: o loop nem existiu"
    ini = [i for i, l in enumerate(linhas) if marca in l]
    assert len(ini) == 1, "a ancora do except NameError deixou de ser unica"
    i = ini[0]
    while linhas[i].strip() != "try:":
        i -= 1
        assert ini[0] - i < 10, "nao achei o `try:` que abre o bloco"
    fim = "            medicao_incompleta=bool(_pdfvec_falhas_flag))"
    j = [k for k, l in enumerate(linhas) if l.rstrip(chr(10)) == fim]
    assert len(j) == 1, "a ancora do fim da chamada deixou de ser unica"
    fatia = textwrap.dedent("".join(linhas[i:j[0] + 1]))
    # sanidade: fatia truncada nao pode 'passar' sem exercitar nada
    assert "_pv_m2 = float(_pdfvec_area_m2)" in fatia, fatia[:200]
    assert "pdfvec_m2=_pv_m2" in fatia, "a fatia nao chega na chamada"
    return fatia


def _fatia_da_soma():
    """As DUAS cópias do bloco que ACUMULA a medição, página a página.

    🪤 06/09 (cético): o guarda do call site injetava `_pdfvec_area_m2`
    PRONTO, então o título prometia "ACUMULA e PASSA" e só a metade "PASSA"
    era executada. A soma mora no laço por página, em duas cópias: a do ramo
    "escala validada por cota" e a do ramo "escala SEM prova de cota" — que é
    justamente o ramo do caso cliente-41. O ramo sem prova não tinha guarda
    nenhum.

    ANCORA no `_vet_secao = ...` de cada ramo (a linha que identifica o ramo) e
    no `except (TypeError, ValueError):` que fecha o bloco. Nunca por tamanho.
    """
    import textwrap
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    linhas = src.splitlines(True)
    marcas = {"com_prova_de_cota": '_vet_secao = "\\n".join(_linhas)',
              "sem_prova_de_cota": '_vet_secao = "\\n".join(_l2)'}
    fatias = {}
    for rotulo, marca in marcas.items():
        achados = [i for i, l in enumerate(linhas) if l.strip() == marca]
        assert len(achados) == 1, (
            "a ancora do ramo %s deixou de ser unica (%d)" % (rotulo, len(achados)))
        i = achados[0] + 1
        while linhas[i].strip() != "try:":
            i += 1
            assert i - achados[0] < 6, "nao achei o `try:` da soma do ramo " + rotulo
        j = i
        while linhas[j].strip() != "except (TypeError, ValueError):":
            j += 1
            assert j - i < 80, "nao achei o `except` que fecha a soma do ramo " + rotulo
        assert linhas[j + 1].strip() == "pass", "o except da soma mudou de corpo"
        fatia = textwrap.dedent("".join(linhas[i:j + 2]))
        # sanidade: fatia truncada nao pode 'passar' sem exercitar nada.
        # 🪤 confere PRESENCA, nunca o operador: ancorar em "+=" faria a
        # propria ancora reprovar a mutacao `+= -> =` e esconder a assercao de
        # COMPORTAMENTO que e o guarda de verdade.
        assert "_pdfvec_area_m2" in fatia, fatia[:200]
        assert "_pdfvec_por_prancha[_stem]" in fatia, fatia[:200]
        fatias[rotulo] = fatia
    assert fatias["com_prova_de_cota"] != "" and fatias["sem_prova_de_cota"] != ""
    return fatias


def _pagina_medida(stem, rooms_m2, walls_m, page_index):
    """O que o filho da medição devolve pra UMA prancha."""
    return {"_stem": stem, "filename": stem + ".pdf", "page_index": page_index,
            "_vm": {"rooms_m2": rooms_m2, "n_rooms": 3, "walls_m": walls_m,
                    "n_walls": 12, "grupo_maior_m2": rooms_m2,
                    "scale": 50, "scale_src": "carimbo", "escala_validada": False,
                    "cotas_batem": 0, "secs": 4.0, "mem_kb": {"VmPeak": 800000},
                    "mem_kb_inicio": {"VmSize": 200000}, "etapas": {},
                    "mem_etapas": {}}}


def _acumula(rotulo, paginas):
    """EXECUTA o bloco real da soma uma vez por prancha (o laço por página) e
    devolve (soma_m2, soma_compr, por_prancha)."""
    codigo = compile(_fatia_da_soma()[rotulo], "soma_" + rotulo, "exec")
    ns = {"__name__": "soma_ns", "_pdfvec_area_m2": 0.0, "_pdfvec_compr_m": 0.0,
          "_pdfvec_por_prancha": {}}
    for _p in paginas:
        ns["_vm"] = _p["_vm"]
        ns["_stem"] = _p["_stem"]
        ns["filename"] = _p["filename"]
        ns["page_index"] = _p["page_index"]
        exec(codigo, ns)
    return (ns["_pdfvec_area_m2"], ns["_pdfvec_compr_m"],
            ns["_pdfvec_por_prancha"])


def _entrega_do_call_site(**mundo):
    """EXECUTA a fatia real e devolve o que a honestidade RECEBEU.

    `_apply_area_honesty` e um espiao que repassa pro de verdade (o `_fatia()`
    que ja existia neste arquivo) — entao os itens sao mexidos de verdade.
    """
    real = _fatia()["_apply_area_honesty"]
    visto = {}

    def _espiao(items, total_area=0, total_area_source="", pe_direito=0,
                apenas_preencher=False, pdfvec_m2=0, pdfvec_por_prancha=None,
                medicao_incompleta=False):
        visto["pdfvec_m2"] = pdfvec_m2
        visto["por_prancha"] = pdfvec_por_prancha
        visto["medicao_incompleta"] = medicao_incompleta
        visto["total_area"] = total_area
        return real(items, total_area, total_area_source,
                    pe_direito=pe_direito, apenas_preencher=apenas_preencher,
                    pdfvec_m2=pdfvec_m2, pdfvec_por_prancha=pdfvec_por_prancha,
                    medicao_incompleta=medicao_incompleta)

    proj = mundo.pop("project_data", None) or _ProjetoDeMentira()
    ns = {"__name__": "call_site_ns", "project_data": proj,
          "all_items": mundo.pop("all_items", []),
          "job_id": "job-do-cliente-41",
          "_apply_area_honesty": _espiao,
          "_log_error": lambda *a, **k: None}
    ns.update(mundo)
    exec(compile(_fatia_do_call_site(), "call_site", "exec"), ns)
    visto["n_fill"] = ns.get("_n_fill")
    visto["blanked"] = ns.get("_blanked")
    visto["avisos"] = list(getattr(proj, "warnings", None) or [])
    assert "pdfvec_m2" in visto, "a fatia rodou e nunca chamou a honestidade"
    return visto



def test_a_area_medida_do_PDF_sobrevive():
    """O caso do cliente-41, do jeito que a produção roda."""
    h = _fatia()["_apply_area_honesty"]
    piso, forro = _piso(), _forro()
    h([piso, forro], total_area=0, total_area_source="", pe_direito=0,
      pdfvec_m2=_M2_MEDIDO)
    assert _valor(piso) == 13.6, (
        "o piso medido do PDF foi apagado de novo — o cliente recebe 0 m² numa "
        "planta que a gente MEDIU")
    assert _valor(forro) == 13.6, "o forro foi apagado"


def test_a_procedencia_vai_escrita_na_linha():
    """Estimativa sem procedência é chute. Com procedência é o que o produto
    promete entregar quando não dá pra provar a escala."""
    h = _fatia()["_apply_area_honesty"]
    piso = _piso()
    h([piso], total_area=0, total_area_source="", pe_direito=0,
      pdfvec_m2=_M2_MEDIDO)
    obs = (piso.observations or "").lower()
    assert "geometria do pdf" in obs, (
        "a linha não diz de onde veio o número: %r" % piso.observations)
    assert "carimbo" in obs, "não avisa que a escala veio do carimbo"
    assert "não medida" not in obs and "nao medida" not in obs, (
        "sobrou o aviso ANTIGO dizendo que não foi medida — era justamente a "
        "frase falsa que o cliente-41 recebeu")


def test_NUNCA_vira_confirmado():
    """🚨 Regra dura nº1. Carimbo é declaração, cota é prova."""
    h = _fatia()["_apply_area_honesty"]
    piso = _piso()
    h([piso], total_area=0, total_area_source="", pe_direito=0,
      pdfvec_m2=_M2_MEDIDO)
    assert str(getattr(piso.confidence, "value", piso.confidence)) == "estimado", (
        "área de PDF com escala de carimbo saiu como MEDIDA: %r" % piso.confidence)


def test_parede_e_pintura_CONTINUAM_zerando():
    """🚨 Trava nº2. O motor vetorial mede o CHÃO dos ambientes, não a altura.

    Parede e pintura dependem do pé-direito, que ninguém mediu. Se passassem,
    a gente estaria entregando a multiplicação do LLM como se fosse medição.
    """
    h = _fatia()["_apply_area_honesty"]
    parede = _Item("Parede em alvenaria de bloco cerâmico 9×19×19cm", "m²", 12.0)
    pintura = _Item("Pintura látex acrílica — cor a confirmar", "m²", 11.0)
    h([parede, pintura], total_area=0, total_area_source="", pe_direito=0,
      pdfvec_m2=_M2_MEDIDO)
    assert _valor(parede) == 0, "parede sobreviveu — não medimos altura nenhuma"
    assert _valor(pintura) == 0, "pintura sobreviveu — mesma coisa"


def test_numero_que_NAO_CABE_na_medicao_e_apagado():
    """🚨 Trava nº3. Sem ela, um chute da IA pegaria carona na medição.

    13,6 m² de ambientes não viram 310 m² de piso. O teto é 1,3× o medido.
    """
    h = _fatia()["_apply_area_honesty"]
    chute = _piso(310.0)
    h([chute], total_area=0, total_area_source="", pe_direito=0,
      pdfvec_m2=_M2_MEDIDO)
    assert _valor(chute) == 0, (
        "310 m² sobreviveram numa planta de 13,6 m² medidos — a trava de "
        "plausibilidade furou e a porta do m² inventado reabriu")


def test_sem_medicao_do_PDF_nada_muda():
    """Regressão: job sem motor vetorial se comporta EXATAMENTE como antes.

    O caso cliente-21 (20/07) é o motivo de a regra existir: Vision chuta
    "Forro Sala 52 m²" numa planta sem cota. Isso tem que continuar zerando.
    """
    h = _fatia()["_apply_area_honesty"]
    chute = _Item("Forro de gesso — Sala", "m²", 52.0)
    n_fill, blanked = h([chute], total_area=0, total_area_source="",
                        pe_direito=0, pdfvec_m2=0)
    assert _valor(chute) == 0, "m² de Vision sem medição sobreviveu"
    assert blanked == 1, "o contador de zerados parou de contar"


def test_edicao_do_cliente_continua_intocada():
    """🚨 Regra dura nº7: o que o cliente corrigiu não se toca, nunca."""
    h = _fatia()["_apply_area_honesty"]
    dele = _piso(45.30)
    dele.origem = "revisao_cliente"
    h([dele], total_area=0, total_area_source="", pe_direito=0,
      pdfvec_m2=_M2_MEDIDO)
    assert _valor(dele) == 45.30, "encostou no número que o cliente digitou"


def test_o_call_site_acumula_e_PASSA_a_medicao():
    """🪤 Guarda de CALL SITE: a função pode estar certa e nunca receber o dado.

    Foi exatamente esse o defeito — `pdfvec` media, e a honestidade nunca
    ficava sabendo. Testar só a função não pega isso.
    """
    piso, forro = _piso(), _forro()
    r = _entrega_do_call_site(_pdfvec_area_m2=_M2_MEDIDO,
                              _pdfvec_por_prancha={}, _pdfvec_falhas=[],
                              all_items=[piso, forro])
    assert r["pdfvec_m2"] == _M2_MEDIDO, (
        "a medição do PDF chegou na honestidade como %r em vez de %.1f m² — "
        "a função existe e não recebe o dado, que é o defeito de origem"
        % (r.get("pdfvec_m2"), _M2_MEDIDO))
    # E o que o cliente recebe por causa disso:
    assert _valor(piso) == 13.6 and _valor(forro) == 13.6, (
        "o call site entregou o número e a planilha saiu zerada assim mesmo")


@pytest.mark.parametrize("rotulo", ["com_prova_de_cota", "sem_prova_de_cota"])
def test_o_call_site_ACUMULA_a_medicao_pagina_a_pagina(rotulo):
    """A metade "ACUMULA" do título, executada nos DOIS ramos.

    Um caderno de 3 pranchas do mesmo imóvel: a soma é das TRÊS, e o mapa por
    prancha tem TRÊS entradas. Trocar o `+=` por `=`, ou gravar só a primeira
    prancha, deixa a honestidade recebendo um número de UMA prancha — e o
    ramo "sem prova de cota" é o do caso cliente-41.
    """
    paginas = [_pagina_medida("4366-AR-A", 129.1, 88.0, 0),
               _pagina_medida("4366-EL-E", 116.4, 61.5, 1),
               _pagina_medida("4366-HI-H", 40.5, 12.0, 2)]
    m2, compr, pp = _acumula(rotulo, paginas)

    assert round(m2, 2) == 286.0, (
        "a soma das 3 pranchas saiu %r (esperado 286.0) — o laço parou de "
        "acumular e a honestidade recebe a medição de UMA prancha só" % m2)
    assert round(compr, 2) == 161.5, (
        "o comprimento de parede parou de acumular: %r" % compr)
    assert sorted(pp) == ["4366-AR-A", "4366-EL-E", "4366-HI-H"], (
        "o mapa por prancha ficou com %r — prancha que não entra no mapa some "
        "do teto por prancha e do aviso" % sorted(pp))
    assert pp["4366-EL-E"]["rooms_m2"] == 116.4, pp["4366-EL-E"]
    assert pp["4366-HI-H"]["pagina"] == 2, pp["4366-HI-H"]


# ══════════════════════════════════════════════════════════════════════════
#  🚨 Os OUTROS dois argumentos do mesmo call site
# ══════════════════════════════════════════════════════════════════════════
_TETO_PP = [
    # rotulo,                falhas,                                 sobrevive
    ("medicao_completa",     [],                                     False),
    ("prancha_nao_medida",   [{"arquivo": "p3.pdf", "pagina": 2,
                               "motivo": "tempo"}],                  True),
]


@pytest.mark.parametrize("rotulo,falhas,sobrevive", _TETO_PP)
def test_o_call_site_PASSA_o_teto_por_prancha_e_a_medicao_incompleta(
        rotulo, falhas, sobrevive):
    """🪤 06/09 (cético): o guarda do call site passava SEMPRE
    `_pdfvec_por_prancha={}` e `_pdfvec_falhas=[]`, então os outros dois
    argumentos entregues na MESMA chamada eram invisíveis. Desligar o teto por
    prancha (`_pp_map = {}`) reabre a porta do m² inventado, e desligar o
    `medicao_incompleta` traz de volta a mordida do mezanino da cliente-45.

    Cenário: duas pranchas medidas, 129,1 e 116,4 m² (soma 245,5). A IA
    escreveu 200 m² de piso.
      · medição COMPLETA  → teto = 1,3 × 129,1 = 167,8 → os 200 m² MORREM;
      · prancha não medida → a gente SABE que não sabe: teto volta pra soma
        (1,3 × 245,5 = 319,2) e os 200 m² VIVEM — é o mezanino de 255,66 m².
    """
    _pp = {"p1": {"arquivo": "p1.pdf", "pagina": 0, "rooms_m2": 129.1,
                  "n_rooms": 4, "walls_m": 88.0, "n_walls": 20},
           "p2": {"arquivo": "p2.pdf", "pagina": 1, "rooms_m2": 116.4,
                  "n_rooms": 3, "walls_m": 61.5, "n_walls": 14}}
    piso = _piso(200.0)
    r = _entrega_do_call_site(_pdfvec_area_m2=245.5,
                              _pdfvec_por_prancha=_pp,
                              _pdfvec_falhas=list(falhas),
                              all_items=[piso])

    # 1) os três argumentos chegaram — e chegaram com CONTEÚDO, não vazios
    assert r["pdfvec_m2"] == 245.5, r
    assert sorted(r["por_prancha"] or {}) == ["p1", "p2"], (
        "o mapa por prancha chegou como %r — sem ele o teto vira a SOMA e a "
        "trava 3 (regra dura nº1) fica ~2× mais frouxa" % (r["por_prancha"],))
    assert (r["por_prancha"] or {})["p1"]["rooms_m2"] == 129.1, r["por_prancha"]
    assert r["medicao_incompleta"] is bool(falhas), (
        "medicao_incompleta chegou %r com falhas=%r" % (r["medicao_incompleta"], falhas))

    # 2) e o que o cliente recebe por causa deles
    if sobrevive:
        assert _valor(piso) == 200.0, (
            "prancha que NÃO deu pra medir e mesmo assim o teto apertado mordeu "
            "os 200 m² — é a mordida do mezanino (cliente-45, 02/09) de volta")
    else:
        assert _valor(piso) == 0, (
            "200 m² sobreviveram com a maior prancha medindo 129,1 m² — o teto "
            "por prancha está desligado e a porta do m² inventado reabriu")


def test_CONTROLE_job_SEM_PDF_chega_com_ZERO_e_o_chute_morre():
    """🧪 O `except NameError` é o que faz o job sem PDF não explodir. Sem este
    controle, um call site que passasse 0,0 SEMPRE passaria no teste de cima
    pelo motivo errado... e um que passasse a medição sempre esconderia esta
    metade. Aqui o nome `_pdfvec_area_m2` nem existe — o laço nem rodou."""
    chute = _Item("Forro de gesso — Sala", "m²", 52.0)
    r = _entrega_do_call_site(all_items=[chute])
    assert r["pdfvec_m2"] == 0.0, r
    assert _valor(chute) == 0, "m² de Vision sem medição nenhuma sobreviveu"
