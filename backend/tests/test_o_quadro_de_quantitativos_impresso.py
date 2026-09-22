# -*- coding: utf-8 -*-
"""Número de QUADRO DE QUANTITATIVOS impresso na prancha não é chute — nem medição.

🩸 22/09/2026 — jobs ee801b82 (ontem, tipo estrutura) e f8d8e6d8 (hoje, os
MESMOS 7 PDFs). A 1ª prancha traz um quadro de quantitativos que o projetista
imprimiu: concreto 4,90 / 3,80 / 13,20 / 3,90 / 1,00 m³ (26,8 m³) e fôrma
37,20 / 31,20 / 82,70 / 28,10 / 4,00 m² (183,2 m²). Duas leituras
independentes da IA deram os mesmos dez números. A honestidade de área zerou
os dez nos DOIS dias — trata todo m²/m³ de PDF como chute — e a planilha saiu
com 0 m³ de concreto num projeto que declara 26,8. NPS 2 no dia seguinte.

🔑 O CONSERTO: o número do quadro fica, como ESTIMADO (nunca branco: é a conta
do projetista, copiada; não medimos nada), com a frase dizendo de onde veio —
mas SÓ com uma prova que não saia da boca da IA:
  (b1) o número está escrito no TEXTO do PDF daquela prancha (e o quadro
       aparece lá: pelo menos dois números dele), ou
  (b2) as linhas do quadro somam uma linha de TOTAL que a leitura diz ter
       LIDO — não somado.
Sem prova, a linha continua zerada e a frase diz qual número a leitura viu. A
linha de TOTAL que só repete a soma fica em branco (não conta em dobro).

🪤 Por que a palavra não basta: "lido do quadro" é o que a IA escreve até em
número que inventou (família "a palavra ≠ o comportamento"). E o "TOTAL GERAL"
do ee801b82 era a conta da própria IA ("Soma dos valores do quadro: 4,90 +
3,80 + …") — conta de chegada, prova nenhuma. O controle abaixo cobra isso.

📏 Alcance medido (22/09, 90 dias, sem avaliação, m²/m³/m fora do CAD): 30
linhas em 5 jobs afirmam transcrição de quadro de quantitativos, 28 zeradas;
fora deste caso, 8 zeradas em 2 jobs — e as respostas da IA nesses jobs são
quadros de verdade (memória de cálculo, tabela de termo de referência, quadro
de paginação).

🪤 Nomes de arquivo FICTÍCIOS de propósito (repositório público, regra nº6).
"""
import ast
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402
import engine_rules  # noqa: E402

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARQ = "prancha-A.pdf"
ARQ_B = "prancha-B.pdf"
_REF = ARQ + " (DE-X)"
_LIDO = ("Valor lido diretamente do quadro de quantitativos da prancha. "
         "Concreto C30, cobrimento 5,0 cm. | Estimativa: lido de PDF, não "
         "medido em geometria — envie DWG/DXF pra medir")
_CONCRETO = (4.90, 3.80, 13.20, 3.90, 1.00)
_FORMA = (37.20, 31.20, 82.70, 28.10, 4.00)


class _Item:
    def __init__(self, desc, unit, qty, obs="", ref_sheet=_REF, origem="vision_pdf"):
        self.description = desc
        self.unit = unit
        self.quantity = qty
        self.observations = obs
        self.ref_sheet = ref_sheet
        self.origem = origem
        self.confidence = "estimado"


def _quadro_do_caso(total_somado_pela_ia=True):
    """As 12 linhas da 1ª prancha como o ee801b82 gravou: 10 parcelas + 2 TOTAL."""
    itens = []
    for n, (c, f) in enumerate(zip(_CONCRETO, _FORMA), start=1):
        itens.append(_Item("Concreto estrutural C30 — Estrutura %d" % n, "m³", c, _LIDO))
        itens.append(_Item("Fôrma de madeira — Estrutura %d" % n, "m²", f, _LIDO))
    if total_somado_pela_ia:
        obs_c = ("Soma dos valores do quadro de quantitativos: E1 (4,90) + E2 (3,80) "
                 "+ E3 (13,20) + E4 (3,90) + E5 (1,00) = 26,80 m³.")
        obs_f = ("Soma dos valores do quadro de quantitativos: E1 (37,20) + E2 (31,20) "
                 "+ E3 (82,70) + E4 (28,10) + E5 (4,00) = 183,20 m².")
    else:
        obs_c = "Total lido diretamente do quadro de quantitativos da prancha: 26,80 m³."
        obs_f = "Total lido diretamente do quadro de quantitativos da prancha: 183,20 m²."
    itens.append(_Item("Concreto estrutural C30 — TOTAL GERAL", "m³", 26.80, obs_c))
    itens.append(_Item("Fôrma de madeira — TOTAL GERAL", "m²", 183.20, obs_f))
    return itens


# o formato do caso: a 1ª prancha "mediu" 2,1 m² de ambiente; a 2ª, 892 m²
_PP = {
    "prancha-A_p0": {"arquivo": ARQ, "rooms_m2": 2.1, "walls_m": 12.2, "pagina": 0,
                     "scale": 25, "scale_src": "vista", "escala_validada": False},
    "prancha-B_p0": {"arquivo": ARQ_B, "rooms_m2": 892.0, "walls_m": 28.4, "pagina": 0,
                     "scale": 125, "scale_src": "vista", "escala_validada": False},
}


def _roda(itens, numeros=None):
    main._apply_area_honesty(itens, pdfvec_m2=894.1, pdfvec_por_prancha=_PP,
                             numeros_do_texto_por_prancha=numeros)
    return itens


def _selo(it):
    return str(getattr(it.confidence, "value", it.confidence))


def _soma(itens, unit):
    return round(sum(i.quantity for i in itens
                     if i.unit == unit and "TOTAL" not in i.description), 2)


def _pdf_com_quadro(caminho, enchimento=0):
    """Um PDF de uma página com o quadro em TEXTO de verdade (reportlab).

    `enchimento` põe rótulos SEM decimal antes do quadro — pra provar que a
    prova lê a página inteira, e não só os 6000 caracteres que a IA recebe."""
    from reportlab.lib.pagesizes import A1
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(caminho, pagesize=A1)      # 1684 × 2384 pt, em pé
    y = 2300
    for k in range(enchimento):
        c.drawString(20 + (k % 16) * 100, y - (k // 16) * 12, "N%d c/15 C=VAR" % k)
    c.drawString(1100, 700, "QUADRO DE QUANTITATIVOS")
    c.drawString(1100, 680, "ELEMENTO   CONCRETO (m3)   FORMA (m2)")
    for n, (cc, ff) in enumerate(zip(_CONCRETO, _FORMA), start=1):
        c.drawString(1100, 680 - 20 * n, "ESTRUTURA %d   %s   %s" % (
            n, ("%.2f" % cc).replace(".", ","), ("%.2f" % ff).replace(".", ",")))
    c.drawString(1100, 540, "EL.331,419   ESC.: 1:25")
    c.save()


def _numeros_do_pdf(tmp_path, enchimento=0):
    """O caminho de PRODUÇÃO: extract_text com o teto da prova → os números."""
    from processor import extract_text
    pdf = str(tmp_path / ARQ)
    _pdf_com_quadro(pdf, enchimento=enchimento)
    mapa = {}
    texto = extract_text(pdf, 0, char_budget=main._TETO_TEXTO_DA_PROVA)
    main._guarda_numeros_do_texto(mapa, ARQ, 0, texto)
    return mapa, pdf


# ══════════════════════════════════════════════════════════════════════════
#  O caso, com o quadro no texto do PDF
# ══════════════════════════════════════════════════════════════════════════
def test_com_o_quadro_no_texto_do_PDF_os_dez_numeros_ficam_como_ESTIMADOS(tmp_path):
    mapa, _ = _numeros_do_pdf(tmp_path)
    itens = _roda(_quadro_do_caso(), mapa)
    parcelas = [i for i in itens if "TOTAL" not in i.description]
    assert _soma(itens, "m³") == 26.8, [i.quantity for i in parcelas]
    assert _soma(itens, "m²") == 183.2, [i.quantity for i in parcelas]
    for i in parcelas:
        assert _selo(i) == "estimado", "número de quadro NUNCA sai branco: %r" % i.description
        assert i.observations.startswith(
            "Número COPIADO do quadro de quantitativos impresso na prancha prancha-A.pdf"), (
            "a procedência tem que vir NA FRENTE (a revisão mostra 110 caracteres): %r"
            % i.observations[:140])
        assert "não é medição nossa" in i.observations
        assert "Confira no quadro" in i.observations
        assert "medido do desenho" not in i.observations.lower()
    assert main._apply_area_honesty.ultimo_quadro_preservados == 10
    assert main._apply_area_honesty.ultimo_quadro_totais == 2


def test_a_linha_de_TOTAL_nao_conta_em_dobro(tmp_path):
    mapa, _ = _numeros_do_pdf(tmp_path)
    itens = _roda(_quadro_do_caso(), mapa)
    totais = [i for i in itens if "TOTAL" in i.description]
    assert [t.quantity for t in totais] == [0, 0], (
        "a linha de TOTAL repete a soma das parcelas — com número, a planilha "
        "diria 53,6 m³ de concreto")
    assert all(t.observations.startswith("Linha de TOTAL: é a soma de 5 linhas")
               for t in totais), [t.observations[:90] for t in totais]
    assert sum(i.quantity for i in itens if i.unit == "m³") == 26.8


def test_parcela_que_se_diz_total_nao_esconde_o_TOTAL_GERAL(tmp_path):
    """🪤 Erro PRA MAIS que a 1ª versão deixava passar: se cada parcela diz
    "volume total da estrutura N", a régua da PALAVRA não acha quem é o total, e
    a linha de 26,80 (também escrita no texto) contaria junto com as cinco. Ela
    é igual à soma de todas as outras do quadro — então é o total."""
    mapa, _ = _numeros_do_pdf(tmp_path)
    mapa[(ARQ.lower(), 0)] = mapa[(ARQ.lower(), 0)] | {2680}
    itens = [_Item("Concreto — volume total da Estrutura %d" % n, "m³", c, _LIDO)
             for n, c in enumerate(_CONCRETO, start=1)]
    geral = _Item("Concreto — soma do quadro", "m³", 26.80, _LIDO)
    _roda(itens + [geral], mapa)
    assert round(sum(i.quantity for i in itens + [geral]), 2) == 26.8, (
        [i.quantity for i in itens + [geral]])
    assert geral.quantity == 0 and geral.observations.startswith("Linha de TOTAL")
    assert engine_rules.e_linha_de_total("Subtotal — bloco A")


def test_TOTAL_de_uma_linha_so_nao_conta_em_dobro():
    """Quadro com UMA estrutura e a linha de total igual a ela: as duas no
    texto do PDF, e mesmo assim só uma fica com número."""
    bloco = _Item("Concreto — Estrutura única", "m³", 4.90, _LIDO)
    total = _Item("Concreto — TOTAL", "m³", 4.90,
                  "Total lido diretamente do quadro de quantitativos: 4,90 m³.")
    forma = _Item("Fôrma — Estrutura única", "m²", 37.20, _LIDO)
    _roda([bloco, total, forma], {(ARQ.lower(), 0): frozenset({490, 3720})})
    assert (bloco.quantity, total.quantity, forma.quantity) == (4.9, 0, 37.2), (
        bloco.quantity, total.quantity, forma.quantity)
    assert total.observations.startswith("Linha de TOTAL: repete a única linha do quadro")


def test_a_prova_le_a_pagina_INTEIRA_e_nao_so_o_que_a_IA_recebe(tmp_path):
    """O quadro depois de 6000 caracteres de rótulos ainda prova. CONTROLE: com
    o corte de antes (6000), os números do quadro não estariam lá."""
    from processor import extract_text
    mapa, pdf = _numeros_do_pdf(tmp_path, enchimento=900)
    curto = engine_rules.numeros_decimais_do_texto(extract_text(pdf, 0))
    assert 490 not in curto and 8270 not in curto, (
        "o enchimento não empurrou o quadro pra depois dos 6000 — o teste não "
        "está provando nada sobre o teto da prova")
    itens = _roda(_quadro_do_caso(), mapa)
    assert _soma(itens, "m³") == 26.8


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLES POSITIVOS — sem prova, nada vira número
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_sem_o_texto_o_quadro_fica_zerado_e_a_linha_DIZ_o_numero():
    """É o ee801b82 como ele é: sem prova por texto e com o TOTAL somado pela
    própria IA. Continua zerado — e a linha passa a dizer o que a leitura viu."""
    itens = _roda(_quadro_do_caso(total_somado_pela_ia=True), numeros={})
    assert all(i.quantity == 0 for i in itens), [(i.description, i.quantity) for i in itens]
    e1 = itens[0]
    assert e1.observations.startswith(
        "Em branco: a leitura diz que o quadro de quantitativos impresso na prancha "
        "prancha-A.pdf traz 4,90 m³ para esta linha"), e1.observations[:160]
    assert "não conseguimos conferir" in e1.observations
    assert main._apply_area_honesty.ultimo_quadro_sem_prova == 10
    assert main._apply_area_honesty.ultimo_quadro_preservados == 0


def test_o_TOTAL_LIDO_do_quadro_prova_as_parcelas_e_sai_da_soma():
    """(b2): sem texto, mas o TOTAL diz que foi LIDO (não somado) e as parcelas
    batem com ele ±1%."""
    itens = _roda(_quadro_do_caso(total_somado_pela_ia=False), numeros={})
    assert _soma(itens, "m³") == 26.8 and _soma(itens, "m²") == 183.2
    parcela = itens[0]
    assert "as linhas do quadro somam o TOTAL" in parcela.observations
    assert [i.quantity for i in itens if "TOTAL" in i.description] == [0, 0]


def test_CONTROLE_TOTAL_que_diz_LIDO_mas_mostra_a_conta_nao_prova():
    """Trava 2 sozinha: a linha diz "lido do quadro" e escreve a soma que ELA
    fez. É a mesma conta de chegada do ee801b82 com outra roupa."""
    itens = _quadro_do_caso(total_somado_pela_ia=False)
    itens[-2].observations = ("Total lido do quadro de quantitativos: 4,90 + 3,80 + "
                              "13,20 + 3,90 + 1,00 = 26,80 m³.")
    itens[-1].observations = ("Total lido do quadro de quantitativos: 37,20 + 31,20 + "
                              "82,70 + 28,10 + 4,00 = 183,20 m².")
    _roda(itens, numeros={})
    assert all(i.quantity == 0 for i in itens), [(i.description, i.quantity) for i in itens]
    # e o TOTAL que nem diz de onde veio também não prova nada
    itens = _quadro_do_caso(total_somado_pela_ia=False)
    itens[-2].observations = "Total do concreto: 26,80 m³."
    itens[-1].observations = "Total da fôrma: 183,20 m²."
    _roda(itens, numeros={})
    assert all(i.quantity == 0 for i in itens), [(i.description, i.quantity) for i in itens]


def test_CONTROLE_um_numero_solto_no_texto_nao_prova_o_quadro():
    """Trava 1: "1,00" aparece em qualquer desenho. Com só ele no texto, a linha
    de 1,00 m³ NÃO é preservada; com dois números do quadro, os dois ficam."""
    itens = _roda(_quadro_do_caso(), {(ARQ.lower(), 0): frozenset({100})})
    assert all(i.quantity == 0 for i in itens)
    itens = _roda(_quadro_do_caso(), {(ARQ.lower(), 0): frozenset({100, 490})})
    com_numero = sorted(i.quantity for i in itens if i.quantity)
    assert com_numero == [1.0, 4.9], com_numero


def test_CONTROLE_o_texto_de_OUTRA_prancha_nao_prova():
    mapa = {(ARQ_B.lower(), 0): engine_rules.numeros_decimais_do_texto(
        "4,90 37,20 3,80 31,20 13,20 82,70 3,90 28,10 1,00 4,00")}
    itens = _roda(_quadro_do_caso(), mapa)
    assert all(i.quantity == 0 for i in itens)


def test_CONTROLE_sem_verbo_de_transcricao_a_regua_antiga_segue():
    """Volume que a IA CALCULOU com cotas continua zerado com a frase de sempre,
    mesmo com o número no texto. E "não consta no quadro" é o contrário."""
    calc = _Item("Concreto — parede do poço", "m³", 2.94,
                 "Volume calculado pelas cotas: 2,94 m³.")
    nega = _Item("Concreto — caixa externa", "m³", 3.10,
                 "Quantitativo não foi lido do quadro de quantitativos: estimado.")
    _roda([calc, nega], {(ARQ.lower(), 0): frozenset({294, 310, 490})})
    for it in (calc, nega):
        assert it.quantity == 0
        assert "Área NÃO medida" in it.observations
        assert "quadro de quantitativos impresso" not in it.observations


def test_rodar_de_novo_nao_empilha_a_frase(tmp_path):
    mapa, _ = _numeros_do_pdf(tmp_path)
    itens = _roda(_quadro_do_caso(), mapa)
    antes = [i.observations for i in itens]
    _roda(itens, mapa)
    assert [i.observations for i in itens] == antes


# ══════════════════════════════════════════════════════════════════════════
#  A viagem dos números: página → checkpoint → honestidade
# ══════════════════════════════════════════════════════════════════════════
def test_os_numeros_viajam_no_checkpoint_e_voltam_na_retomada(tmp_path):
    mapa, _ = _numeros_do_pdf(tmp_path)
    result = {"items": []}
    main._anexa_numeros_do_texto(mapa, ARQ, 0, result)
    result = json.loads(json.dumps(result))          # o checkpoint é JSON
    volta = {}
    main._restaura_numeros_do_texto(volta, ARQ, 0, result)
    assert volta == mapa and 8270 in volta[(ARQ.lower(), 0)]


def _chamadas_no_process_job(nomes):
    """{nome: [chamadas]} dentro do `process_job` — um parse, uma varredura."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    arv = ast.parse(src)
    pj = next(n for n in arv.body
              if isinstance(n, ast.FunctionDef) and n.name == "process_job")
    out = {n: [] for n in nomes}
    for n in ast.walk(pj):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id in out):
            out[n.func.id].append(n)
    return out


def test_o_laco_de_paginas_guarda_restaura_e_anexa_no_MESMO_mapa():
    """🪤 Função certa que nunca recebe o dado é o defeito mais caro desta casa
    (o pdfvec media e a honestidade não ficava sabendo). As três pontas do laço
    têm que falar do mapa que a honestidade recebe."""
    nomes = ("_guarda_numeros_do_texto", "_restaura_numeros_do_texto",
             "_anexa_numeros_do_texto")
    todas = _chamadas_no_process_job(nomes)
    for nome in nomes:
        cs = todas[nome]
        assert len(cs) == 1, "%s: esperava 1 chamada no process_job, achei %d" % (nome, len(cs))
        assert getattr(cs[0].args[0], "id", "") == "_numeros_do_texto_por_prancha", nome


def _fatia_da_chamada():
    """Do `try:` que lê `_pdfvec_area_m2` até o fim da chamada da honestidade."""
    linhas = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read().splitlines(True)
    ini = [i for i, l in enumerate(linhas)
           if "_pv_m2 = 0.0          # job sem PDF: o loop nem existiu" in l]
    assert len(ini) == 1
    i = ini[0]
    while linhas[i].strip() != "try:":
        i -= 1
    fim = [k for k, l in enumerate(linhas)
           if l.rstrip("\n") == "            medicao_incompleta=bool(_pdfvec_falhas_flag))"]
    assert len(fim) == 1 and fim[0] > i
    import textwrap
    return textwrap.dedent("".join(linhas[i:fim[0] + 1]))


def test_a_chamada_REAL_entrega_o_mapa_a_honestidade():
    """Executa o trecho real do `process_job` com um espião no lugar da função."""
    visto = {}

    def _espiao(*a, **k):
        visto.update(k)
        return 0, 0

    mapa = {(ARQ.lower(), 0): frozenset({490, 3720})}

    class _PD:
        total_area = 0
        total_area_source = ""
        user_pe_direito = 0
        warnings = []

    ns = {"__name__": "chamada_ns", "project_data": _PD(), "all_items": [],
          "job_id": "ee801b82", "_apply_area_honesty": _espiao,
          "_log_error": lambda *a, **k: None, "_pdfvec_area_m2": 0.0,
          "_pdfvec_por_prancha": {}, "_pdfvec_falhas": [],
          "_avisos_da_medicao_pdfvec": lambda *a, **k: ([], ""),
          "_linha_pdfvec_memoria": lambda *a, **k: "",
          "_pranchas_perto_do_teto": lambda *a, **k: [],
          "_numeros_do_texto_por_prancha": mapa}
    exec(compile(_fatia_da_chamada(), "chamada", "exec"), ns)
    assert visto.get("numeros_do_texto_por_prancha") == mapa, (
        "a honestidade não recebeu os números do texto: %r" % sorted(visto))
