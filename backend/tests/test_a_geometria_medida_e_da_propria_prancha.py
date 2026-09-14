# -*- coding: utf-8 -*-
"""A frase "Medido da GEOMETRIA do PDF" só sai com a medição da PRÓPRIA prancha.

🩸 11/09/2026, job b0fa9104 — PDF de 16 pranchas de uma loja de shopping. Uma
folha de TABELA, sem escala escrita, recebeu "1:500" por votação de cotas que
eram os dígitos do endereço e do telefone no carimbo, e "mediu" 1.071,9 m². A
trava 3 da honestidade de área comparava o número do item com o TETO DO JOB
(1,3 × a maior prancha = 1.393 m²), então três linhas de 180 m² vindas da CAPA
— que não tem escala nenhuma — passaram com a frase "Medido da GEOMETRIA do
PDF". São 540 dos 743 m² que o cliente recebeu, e o número não saiu de medição
nossa: é o metro quadrado do espaço da loja no shopping, escrito na capa.

📏 Medido na base (30 dias, 193 linhas com a frase em 26 jobs, 12.208 m²): 73
declaram a página e, destas, 10 perdem o número — 1.575,83 m². Ou seja, 183 das
193 seguem (94,8%). Das 10: 3 são as de 180 m² da capa deste caso, 3 vêm de
prancha com `rooms_m2 = 0` e 4 são de um job de 10/09 cuja frase a auditoria já
tinha acusado de falsa.

🪤 Três exceções DELIBERADAS, cada uma com controle aqui: caller sem mapa por
prancha, `medicao_incompleta=True` (a mordida do mezanino da cliente-45, 02/09)
e item que não declara a página. Nesses três a régua antiga continua valendo —
não punir cliente por falha nossa.

🪤 Nome de arquivo aqui é FICTÍCIO de propósito: repositório público (regra
dura nº6). A convenção da casa é `cliente-NN`.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


class _Item:
    def __init__(self, desc, unit, qty, ref_sheet="", obs="", origem="",
                 conf="estimado"):
        self.description = desc
        self.unit = unit
        self.quantity = qty
        self.ref_sheet = ref_sheet
        self.observations = obs
        self.origem = origem
        self.confidence = conf


def _prancha(arquivo, m2, pagina=None, scale=50, scale_src="carimbo"):
    return {"arquivo": arquivo, "rooms_m2": m2, "n_rooms": 3, "walls_m": 0,
            "n_walls": 0, "grupo_maior_m2": m2, "scale": scale,
            "scale_src": scale_src, "escala_validada": False, "pagina": pagina}


# o formato do caso: a capa (p0) não mediu nada e não entra no mapa; a p3 mediu
# 21,2 m²; a folha de tabela (p7) "mediu" 1.071,9 m² com escala inventada.
ARQ = "planta cliente-nn.pdf"
ARQ2 = "detalhes cliente-nn.pdf"
PP_LOJA = {
    "p3": _prancha(ARQ, 21.2, pagina=3, scale=13, scale_src="viewport"),
    "p7": _prancha(ARQ, 1071.9, pagina=7, scale=500, scale_src="cotas"),
}
_SOMA = 21.2 + 1071.9
_TETO_ANTIGO = 1.3 * 1071.9        # 1.393,5 — o teto da maior prancha do job


def _piso(qty, pagina_no_ref, arquivo=ARQ):
    """Item de piso apontando pra página N do `ref_sheet` (1-based, como o motor
    escreve: `_pagina_do_ref_sheet` devolve N-1)."""
    return _Item("Piso cerâmico da área de vendas", "m²", qty,
                 ref_sheet="%s (p%d)" % (arquivo, pagina_no_ref))


def _valor(it):
    return round(float(it.quantity or 0), 2)


def _obs(it):
    return (it.observations or "").lower()


def _roda(itens, **kw):
    kw.setdefault("pdfvec_m2", _SOMA)
    kw.setdefault("pdfvec_por_prancha", PP_LOJA)
    return main._apply_area_honesty(itens, **kw)


# ── o caso ────────────────────────────────────────────────────────────────
def test_numero_da_CAPA_sem_escala_nao_vira_medicao_por_causa_de_outra_prancha():
    """🚨 O caso: 180 m² numa página que não mediu nada."""
    capa = _piso(180.0, 1)          # p1 no ref_sheet = página 0 = capa
    _roda([capa])
    assert _valor(capa) == 0, (
        "180 m² de uma prancha SEM medição sobreviveram — a trava voltou a olhar "
        "o teto do job")
    assert "geometria do pdf" not in _obs(capa), (
        "a linha zerada ainda afirma que foi medida da geometria: %r" % capa.observations)


def test_CONTROLE_numero_que_cabe_na_propria_prancha_continua_e_diz_qual_prancha():
    piso = _piso(21.2, 4)           # p4 no ref_sheet = página 3, que mediu 21,2
    _roda([piso])
    assert _valor(piso) == 21.2, "a medição da própria prancha foi apagada"
    o = _obs(piso)
    assert "geometria do pdf" in o and "21.20" in o, o
    assert "caixa de recorte" in o, (
        "a frase não diz de onde veio a escala DESTA prancha (viewport): %r" % piso.observations)


def test_numero_grande_demais_PRA_PROPRIA_prancha_zera_mesmo_com_prancha_maior_no_job():
    grande = _piso(900.0, 4)        # cabe nos 1.071,9 da p7, não nos 21,2 da p3
    _roda([grande])
    assert _valor(grande) == 0, "900 m² sobreviveram numa prancha que mediu 21,2"


def test_a_pagina_declarada_tem_que_BATER_com_a_da_medicao():
    """🩸 Achado da revisão: arquivo com UMA página medida não entra no mapa por
    página, o casamento cai no NOME e devolvia a medição de outra prancha — com
    a frase nova nomeando, com número, uma prancha de onde o item não veio."""
    uma_pagina = {"p3": _prancha(ARQ, 200.0, pagina=3)}
    fora = _piso(180.0, 1)          # o item diz p1; a única medida é a p3
    main._apply_area_honesty([fora], pdfvec_m2=200.0, pdfvec_por_prancha=uma_pagina)
    assert _valor(fora) == 0, (
        "a medição da p3 preencheu um item que diz ter vindo da p1: %r" % fora.observations)


def test_registro_de_medicao_SEM_pagina_nao_acusa_o_item():
    """🩸 2ª revisão: o item que não declara página é POUPADO de propósito, mas o
    REGISTRO sem página condenava o item cuja página está certa — regra invertida.
    A porta é o checkpoint antigo, que volta sem a chave `pagina`."""
    sem_pagina_no_registro = {"a": _prancha(ARQ, 200.0, pagina=None),
                              "b": _prancha(ARQ, 90.0, pagina=None)}
    piso = _piso(180.0, 2)
    main._apply_area_honesty([piso], pdfvec_m2=290.0,
                             pdfvec_por_prancha=sem_pagina_no_registro)
    assert _valor(piso) == 180.0, (
        "registro sem página zerou item que declara a página — a régua antiga é "
        "que vale quando a pergunta não tem resposta")
    # 🪤 e NÃO pode citar a medição daquela prancha: ninguém confirmou que é a
    # do item. Sem esta asserção o conserto passa preservando pela razão errada.
    assert "200.00" not in _obs(piso), piso.observations
    assert int(getattr(main._apply_area_honesty, "ultimo_zerados_sem_prancha", 0)) == 0, (
        "o contador creditou ao conserto uma linha que ele não deveria julgar")


def test_UMA_prancha_medida_sem_a_chave_de_pagina_tambem_nao_acusa():
    """A outra forma do mesmo buraco: com UMA página medida o arquivo entra no
    índice por NOME, o casamento acha o registro — e ele não diz a página. Também
    é pergunta sem resposta: vale a régua antiga, não o zero."""
    uma_sem_pagina = {"unica": _prancha(ARQ, 200.0, pagina=None)}
    piso = _piso(180.0, 2)
    main._apply_area_honesty([piso], pdfvec_m2=200.0, pdfvec_por_prancha=uma_sem_pagina)
    assert _valor(piso) == 180.0, (
        "registro achado pelo nome, sem página, zerou o item: %r" % piso.observations)
    assert "200.00" not in _obs(piso), (
        "a frase nomeou a medição de uma prancha que pode não ser a do item: %r"
        % piso.observations)


def test_a_pagina_do_registro_e_comparada_com_o_MESMO_tipo_do_mapa():
    """🪤 O mapa faz `int(_pg)`; aqui a comparação era crua, e "3" != 3 zerava."""
    texto = {"p3": _prancha(ARQ, 21.2, pagina="3", scale=50)}
    piso = _piso(21.2, 4)
    main._apply_area_honesty([piso], pdfvec_m2=21.2, pdfvec_por_prancha=texto)
    assert _valor(piso) == 21.2, (
        "página em texto ('3') não casou com a página 3 do item: %r" % piso.observations)
    assert "geometria do pdf" in _obs(piso)


def test_CONTROLE_pagina_do_registro_DIFERENTE_continua_zerando():
    """🧪 O controle do par acima: quando as duas páginas existem e divergem, é
    outra prancha — e aí zera mesmo."""
    outra = {"p5": _prancha(ARQ, 200.0, pagina=5)}
    piso = _piso(180.0, 4)              # item diz p4 (página 3), registro é a 5
    main._apply_area_honesty([piso], pdfvec_m2=200.0, pdfvec_por_prancha=outra)
    assert _valor(piso) == 0, "item de outra página sobreviveu"


def test_a_frase_nomeia_a_prancha_DO_ITEM_nao_a_maior_do_job():
    """🪤 O comentário de 31/08 dentro da própria função conta o estrago de
    nomear a prancha errada; a fixture tem DOIS arquivos pra provar."""
    pp = {"a": _prancha(ARQ, 21.2, pagina=3, scale=50),
          "b": _prancha(ARQ2, 500.0, pagina=0, scale=50)}
    piso = _piso(21.2, 4)           # veio do ARQ, página 3
    main._apply_area_honesty([piso], pdfvec_m2=521.2, pdfvec_por_prancha=pp)
    o = _obs(piso)
    assert ARQ in o and ARQ2 not in o, (
        "a frase nomeou a prancha errada (a maior do job): %r" % piso.observations)


def test_a_frase_traz_a_RESSALVA_em_toda_fonte_de_escala():
    """🚨 Regra dura nº1: afirmação de medição nunca sai sem a ressalva — e ela
    vem COLADA na afirmação, porque a observação é cortada em 1.000 chars."""
    for fonte, (_como, ressalva) in main._FONTE_DA_ESCALA.items():
        pp = {"p3": _prancha(ARQ, 21.2, pagina=3, scale=50, scale_src=fonte)}
        piso = _piso(21.2, 4)
        main._apply_area_honesty([piso], pdfvec_m2=21.2, pdfvec_por_prancha=pp)
        o = it_obs = (piso.observations or "")
        assert ressalva in o, "fonte %r saiu sem ressalva: %r" % (fonte, it_obs)
        assert o.index(ressalva) < o.index("Prancha "), (
            "a ressalva veio DEPOIS do número — o corte de 1.000 chars deixaria "
            "a afirmação sozinha (%r)" % fonte)


def test_a_escala_sai_formatada_e_nunca_como_None():
    pp = {"p3": _prancha(ARQ, 21.2, pagina=3, scale=None)}
    piso = _piso(21.2, 4)
    main._apply_area_honesty([piso], pdfvec_m2=21.2, pdfvec_por_prancha=pp)
    assert "1:none" not in _obs(piso), piso.observations
    pp2 = {"p3": _prancha(ARQ, 21.2, pagina=3, scale=13.0)}
    piso2 = _piso(21.2, 4)
    main._apply_area_honesty([piso2], pdfvec_m2=21.2, pdfvec_por_prancha=pp2)
    assert "1:13" in _obs(piso2) and "1:13.0" not in _obs(piso2), piso2.observations


# ── os contadores: cada população conta a sua ─────────────────────────────
def test_o_contador_separa_quem_o_conserto_zerou():
    capa = _piso(180.0, 1)
    _roda([capa])
    assert int(getattr(main._apply_area_honesty, "ultimo_zerados_sem_prancha", 0)) == 1, (
        "o instrumento não conta as linhas que a regra da própria prancha zerou")
    assert int(getattr(main._apply_area_honesty, "ultimo_apertou_teto", 0)) == 0, (
        "a linha entrou TAMBÉM no contador do teto — o aviso ao cliente diria "
        "que 180 m² não cabem em 1.072 m²")


def test_CONTROLE_o_contador_novo_NAO_credita_quem_o_teto_ANTIGO_ja_zerava():
    """🧪 1.300 m² já não cabia na maior prancha (1,3 × 1.071,9 = 1.393)… cabe;
    1.400 não. Quem cai pelo teto antigo é do teto antigo."""
    velho = _piso(1400.0, 4)
    _roda([velho])
    assert _valor(velho) == 0
    assert int(getattr(main._apply_area_honesty, "ultimo_zerados_sem_prancha", 0)) == 0, (
        "o contador novo levou o crédito de uma linha que o teto antigo já zerava")


def test_o_caller_LE_o_contador_novo_e_avisa_com_a_frase_certa():
    """🪤 Guarda de ponto de chamada: contador que ninguém lê é instrumento morto,
    e o aviso do teto antigo seria falso pra esta população."""
    import io
    fonte = io.open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 "main.py"), encoding="utf-8").read()
    limpo = "\n".join(l for l in fonte.splitlines() if not l.lstrip().startswith("#"))
    assert "ultimo_zerados_sem_prancha" in limpo, "o caller não lê o contador novo"
    assert "motor:geometria-de-outra-prancha" in limpo, (
        "o descarte não vira linha no error_log")
    assert "não mediu essa área" in limpo, (
        "o cliente não recebe o aviso próprio desta população")


def test_CONTROLE_a_checagem_de_chamada_sabe_REPROVAR():
    """🧪 Sem isto, o teste acima passaria com as linhas comentadas."""
    falso = "\n".join(["        # _zsp = ultimo_zerados_sem_prancha  (comentado)",
                       "        pass"])
    limpo = "\n".join(l for l in falso.splitlines() if not l.lstrip().startswith("#"))
    assert "ultimo_zerados_sem_prancha" not in limpo


# ── as três exceções deliberadas ──────────────────────────────────────────
def test_CONTROLE_item_que_NAO_declara_a_pagina_segue_no_teto_antigo():
    """🪤 Não virar tesoura. 120 das 193 linhas com a frase, em 30 dias, não
    dizem de qual prancha vieram — pra elas a pergunta não tem resposta, e o
    teto da maior prancha continua sendo o limite honesto."""
    sem_pagina = _Item("Piso cerâmico da área de vendas", "m²", 900.0,
                       ref_sheet=ARQ)          # sem "(pN)"
    _roda([sem_pagina])
    assert _valor(sem_pagina) == 900.0, (
        "zerou item que não declara página — o conserto virou tesoura em quem "
        "não tinha como responder")


def test_CONTROLE_medicao_INCOMPLETA_nao_cobra_a_propria_prancha():
    """🩸 02/09, cliente-45: uma das 3 páginas estourou o tempo e o teto apertado
    zerou um mezanino de 255,66 m² ESCRITO na prancha. Quando a gente sabe que
    não mediu tudo, não cobra."""
    capa = _piso(180.0, 1)
    _roda([capa], medicao_incompleta=True)
    assert _valor(capa) == 180.0, (
        "com medição incompleta o conserto apertou assim mesmo — é a mordida do "
        "mezanino de volta")


def test_CONTROLE_sem_mapa_por_prancha_o_comportamento_ANTIGO_continua():
    """🪤 Caller antigo (job sem medição por prancha): o teto de antes vale."""
    piso = _Item("Piso cerâmico", "m²", 13.6)
    main._apply_area_honesty([piso], pdfvec_m2=13.6)
    assert _valor(piso) == 13.6, (
        "o conserto zerou quem não tem mapa por prancha — regressão no caso cliente-41")
    assert "geometria do pdf" in _obs(piso)


# ── o que não pode mudar ──────────────────────────────────────────────────
def test_CONTROLE_o_passo_7_continua_preenchendo_linha_zerada_da_propria_prancha():
    """A extração do casamento item→prancha não pode mexer no passo 7."""
    vazio = _piso(0, 4)
    _roda([vazio])
    assert _valor(vazio) == 21.2, "o passo 7 parou de preencher a linha zerada"
    assert "medidos nesta prancha" in _obs(vazio), vazio.observations


def test_CONTROLE_o_selo_continua_estimado_nos_dois_lados():
    piso, vazio = _piso(21.2, 4), _piso(0, 4)
    _roda([piso])
    _roda([vazio])
    for it in (piso, vazio):
        assert str(getattr(it.confidence, "value", it.confidence)) == "estimado", (
            "item de PDF saiu confirmado — regra dura nº1: %r" % it.confidence)


def test_o_casamento_item_prancha_e_CHAMAVEL_e_nao_chuta_no_empate():
    """A função extraída: nome mais longo ganha, empate não atribui nada."""
    a = _prancha("planta baixa cliente-nn.pdf", 80.5)
    b = _prancha("planta baixa cliente-nn 2 pavimento.pdf", 198.4)
    por_arquivo = {"planta baixa cliente-nn.pdf": a,
                   "planta baixa cliente-nn 2 pavimento.pdf": b}
    achou, amb = main._prancha_do_ref_sheet(
        "planta baixa cliente-nn 2 pavimento.pdf (planta)", por_arquivo, {})
    assert achou and achou[1] is b, "o nome mais longo perdeu pro prefixo"
    achou2, _ = main._prancha_do_ref_sheet("planta baixa cliente-nn.pdf", por_arquivo, {})
    assert achou2 and achou2[1] is a, achou2
    achou3, amb3 = main._prancha_do_ref_sheet("nada a ver.pdf", por_arquivo, {})
    assert achou3 is None and amb3 is None, (achou3, amb3)
