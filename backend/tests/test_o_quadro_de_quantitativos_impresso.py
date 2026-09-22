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


# ══════════════════════════════════════════════════════════════════════════
#  🩸 22/09/2026 — O QUE A REVISÃO ADVERSÁRIA DA 1ª VERSÃO ACHOU
# ══════════════════════════════════════════════════════════════════════════
# A 1ª versão (fb1126e) passou 28/28 e a sabotagem dela deu 23/23 — e mesmo
# assim a revisão achou: (1) o /inform-area enchia as linhas que o conserto
# deixa em branco DE PROPÓSITO, e a frase velha ficava colada contradizendo o
# número; (2) a conta da prova pelo TOTAL, o caminho da retomada, o "quadro de
# áreas" e o milhar de 3 casas não tinham guarda nenhum (5 mutações dela
# sobreviveram); (3) duas frases afirmavam o que não era verdade.
_PISO_LIDO = "Área extraída diretamente do Quadro Quantitativo | Piso da prancha."


def _piso_do_quadro():
    """Quadro de PAGINAÇÃO DE PISO (a população existe no acervo: um job com
    quadro de piso e área informada de 400 m²). Números neutros."""
    return [_Item("Piso porcelanato 120x120 — sala", "m²", 134.95, _PISO_LIDO),
            _Item("Piso porcelanato 60x60 — quartos", "m²", 55.19, _PISO_LIDO),
            _Item("Piso porcelanato — TOTAL", "m²", 190.14,
                  "Soma do quadro quantitativo de piso.")]


def _inform_area(itens, area=400):
    """A chamada EXATA da rota /inform-area (itens reidratados do banco)."""
    return main._apply_area_honesty(itens, area, "informado", pe_direito=0,
                                    apenas_preencher=True)


def test_o_inform_area_nao_enche_o_TOTAL_do_quadro():
    """R1: com as duas parcelas provadas pelo texto, o TOTAL fica em branco pra
    não contar em dobro. A área informada depois NÃO pode entrar nele — antes
    ela entrava (vaga de "piso zerado") e a planilha ia a 590,14 m²."""
    itens = _piso_do_quadro()
    main._apply_area_honesty(itens, numeros_do_texto_por_prancha={
        (ARQ.lower(), 0): frozenset({13495, 5519})})
    sala, quartos, total = itens
    assert (sala.quantity, quartos.quantity, total.quantity) == (134.95, 55.19, 0)
    assert main._e_total_do_quadro_em_branco(total.observations), total.observations[:80]
    _inform_area(itens)
    assert total.quantity == 0, (
        "o /inform-area encheu o TOTAL do quadro: %s m² contam duas vezes"
        % total.quantity)
    assert round(sum(i.quantity for i in itens), 2) == 190.14
    assert total.observations.startswith("Linha de TOTAL")


def test_CONTROLE_o_inform_area_ainda_enche_a_vaga_de_verdade():
    """A trava do TOTAL não pode desligar o /inform-area: a mesma descrição de
    piso, zerada pelo motor com a frase de sempre, recebe a área informada."""
    vaga = _Item("Piso porcelanato — TOTAL", "m²", 190.14, "Área estimada pela IA.")
    main._apply_area_honesty([vaga], numeros_do_texto_por_prancha={})
    assert vaga.quantity == 0 and "Área NÃO medida" in vaga.observations
    assert not main._e_total_do_quadro_em_branco(vaga.observations)
    preench, _ = _inform_area([vaga])
    assert (preench, vaga.quantity) == (1, 400.0)


def test_o_inform_area_que_enche_a_parcela_sem_prova_tira_o_Em_branco():
    """R1: parcela de quadro SEM prova sai do motor com "Em branco: a leitura
    diz que o quadro … traz 134,95 m²". Se a área informada entra nela, a
    frase sai — linha com número não pode começar dizendo "Em branco"."""
    sala, quartos = _piso_do_quadro()[:2]
    main._apply_area_honesty([sala, quartos], numeros_do_texto_por_prancha={})
    assert sala.quantity == 0 and sala.observations.startswith("Em branco:")
    preench, _ = _inform_area([sala, quartos])
    assert preench == 1
    com_numero = [i for i in (sala, quartos) if i.quantity]
    assert [i.quantity for i in com_numero] == [400.0]
    assert "Em branco" not in com_numero[0].observations, com_numero[0].observations
    assert "Área informada por você" in com_numero[0].observations
    # a que continua vazia continua dizendo o número que a leitura viu
    vazia = [i for i in (sala, quartos) if not i.quantity][0]
    assert vazia.observations.startswith("Em branco: a leitura diz que o quadro")


def test_a_limpeza_do_aviso_de_linha_vazia_leva_a_frase_do_quadro():
    """`_limpa_aviso_nao_medida` é chamada em TODO ponto onde linha zerada volta
    a ter número (passo 7, pé-direito, pdfvec, recuperação do layer)."""
    obs = ("Em branco: a leitura diz que o quadro de quantitativos impresso na "
           "prancha prancha-A.pdf traz 4,90 m³ para esta linha, mas não "
           "conseguimos conferir esse número no texto do PDF. Confira no quadro e "
           "preencha na revisão. | Concreto C30, cobrimento 5,0 cm.")
    assert main._limpa_aviso_nao_medida(obs) == "Concreto C30, cobrimento 5,0 cm."


def test_CONTROLE_TOTAL_LIDO_que_NAO_bate_nao_prova_nada():
    """R3: a prova (b2) é a SOMA bater. 4,90 + 3,80 + 13,20 = 21,90, e o TOTAL
    "lido" diz 30,00: nenhuma parcela fica com número."""
    ps = [_Item("Concreto — Estrutura %d" % n, "m³", q, _LIDO)
          for n, q in enumerate((4.90, 3.80, 13.20), start=1)]
    t = _Item("Concreto — TOTAL GERAL", "m³", 30.00,
              "Total lido diretamente do quadro de quantitativos da prancha: 30,00 m³.")
    _roda(ps + [t], numeros={})
    assert [i.quantity for i in ps + [t]] == [0, 0, 0, 0], (
        "um TOTAL que não bate provou as parcelas: %r" % [i.quantity for i in ps])
    assert all("as linhas do quadro somam o TOTAL" not in i.observations for i in ps)
    # 🧪 e o mesmo TOTAL batendo (21,90) prova — senão o controle não controla
    t.quantity, t.observations = 21.90, "Total lido diretamente do quadro de quantitativos: 21,90 m³."
    for p, q in zip(ps, (4.90, 3.80, 13.20)):
        p.quantity, p.observations = q, _LIDO
    _roda(ps + [t], numeros={})
    assert [p.quantity for p in ps] == [4.90, 3.80, 13.20]


def test_sem_prova_o_TOTAL_nao_diz_que_evita_contar_em_dobro():
    """R4: é o ee801b82 sem camada de texto. As 5 parcelas zeram, o TOTAL
    também — e a frase "pra a mesma quantidade não contar duas vezes" era falsa:
    não conta nenhuma. O cliente precisa saber que escolhe ONDE pôr o número."""
    itens = _roda(_quadro_do_caso(total_somado_pela_ia=True), numeros={})
    totais = [i for i in itens if "TOTAL" in i.description]
    for t in totais:
        assert t.quantity == 0
        assert t.observations.startswith(
            "Linha de TOTAL do quadro de quantitativos da prancha prancha-A.pdf "
            "(a leitura trouxe"), t.observations[:120]
        assert "nenhuma das 5 linhas que ele resume" in t.observations
        assert "Preencha as parcelas OU esta linha, não as duas." in t.observations
        assert "não contar duas vezes" not in t.observations
    info = engine_rules.veredito_do_quadro_impresso(_tres_linhas(), {})
    assert info[2][0] == "e_o_total" and info[2][1]["parcelas_com_numero"] == 0


def _tres_linhas():
    """Duas parcelas lidas e um TOTAL que é a SOMA da IA (não prova nada)."""
    soma = "Soma dos valores do quadro de quantitativos: 4,90 + 3,80 = 8,70 m³."
    return [{"arquivo": "a.pdf", "pagina": 0, "unidade": "m³", "quantidade": q,
             "texto": t, "descricao": d}
            for d, q, t in (("E1", 4.9, _LIDO), ("E2", 3.8, _LIDO), ("TOTAL", 8.7, soma))]


def test_com_prova_o_TOTAL_conta_as_parcelas_com_numero():
    info = engine_rules.veredito_do_quadro_impresso(
        _tres_linhas(), {("a.pdf", 0): frozenset({490, 380})})
    assert [v[0] for v in info] == ["texto", "texto", "e_o_total"]
    assert info[2][1]["parcelas_com_numero"] == 2


def test_parcela_igual_a_soma_das_outras_a_frase_PERGUNTA():
    """R7: 2,00 = 1,00 + 1,00. A régua "igual à soma de todas as outras" erra
    pra menos de propósito e zera o bloco de 2,00 — mas a frase não pode
    AFIRMAR que ele é o total: pode ser uma parcela."""
    a = _Item("Concreto — bloco B1", "m³", 2.00, _LIDO)
    b = _Item("Concreto — bloco B2", "m³", 1.00, _LIDO)
    c = _Item("Concreto — bloco B3", "m³", 1.00, _LIDO)
    _roda([a, b, c], {(ARQ.lower(), 0): frozenset({200, 100})})
    assert (a.quantity, b.quantity, c.quantity) == (0, 1.0, 1.0)
    assert a.observations.startswith("Linha de TOTAL? O número é igual à soma das "
                                     "outras 2 linhas"), a.observations[:100]
    assert "Se for uma parcela, preencha na revisão." in a.observations
    assert main._e_total_do_quadro_em_branco(a.observations)


def test_CONTROLE_quadro_de_AREAS_nao_e_quadro_de_quantitativos():
    """R3: "quadro de áreas" fica de fora de propósito (é outra doença: a área
    do imóvel colada num item). Mesmo com os números no texto, zera como antes."""
    assert not engine_rules.afirma_quadro_de_quantitativos(
        "Área lida diretamente do quadro de áreas da prancha.")
    sala = _Item("Piso — sala", "m²", 85.40, "Área lida diretamente do quadro de áreas da prancha.")
    coz = _Item("Piso — cozinha", "m²", 12.30, "Área lida diretamente do quadro de áreas da prancha.")
    # sem medição vetorial: piso não tem outro ramo que o preserve
    main._apply_area_honesty([sala, coz], numeros_do_texto_por_prancha={
        (ARQ.lower(), 0): frozenset({8540, 1230})})
    for it in (sala, coz):
        assert it.quantity == 0
        assert "Área NÃO medida" in it.observations
        assert "quadro de quantitativos impresso" not in it.observations


def test_CONTROLE_numero_com_TRES_casas_nao_e_decimal():
    """R3: "1.234" é mil duzentos e trinta e quatro em pt-BR ou 1,234 — ambíguo,
    fica de fora da prova. Com vírgula decimal ele vale."""
    ns = engine_rules.numeros_decimais_do_texto("EL. 1.234  COTA 2.500  1.234,50  4,90")
    assert ns == frozenset({123450, 490}), sorted(ns)


# ── R3: o laço de páginas EXECUTADO, nos dois ramos ─────────────────────────
def _laco_de_pdf():
    """O `if _ck_key in _ckpt_cache:` do laço de pranchas de PDF, no `process_job`."""
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    pj = next(n for n in ast.parse(src).body
              if isinstance(n, ast.FunctionDef) and n.name == "process_job")
    ifs = [n for n in ast.walk(pj) if isinstance(n, ast.If)
           and isinstance(n.test, ast.Compare)
           and getattr(n.test.left, "id", "") == "_ck_key"]
    assert len(ifs) == 1, "esperava 1 `if _ck_key in _ckpt_cache` no process_job: %d" % len(ifs)
    return src.splitlines(True), ifs[0]


def _codigo(linhas, nos):
    import textwrap
    return textwrap.dedent("".join(linhas[nos[0].lineno - 1:nos[-1].end_lineno]))


def test_o_laco_de_paginas_EXECUTADO_guarda_anexa_salva_e_restaura(tmp_path):
    """R3: o guarda de AST só CONTAVA as chamadas. Anexar os números DEPOIS do
    `_ckpt_save`, ou restaurar dentro de um `if` morto, passava verde — e o job
    retomado perdia a prova calado. Aqui roda o código REAL do laço: a página
    nova (texto → números), o checkpoint (o que `_ckpt_save` RECEBE) e a
    retomada (de volta do checkpoint), e a honestidade no fim."""
    from processor import extract_text
    linhas, ck = _laco_de_pdf()
    pdf = str(tmp_path / ARQ)
    _pdf_com_quadro(pdf, enchimento=900)        # o quadro fica depois dos 6000

    # 1) página nova: do extract_text até o `del _texto_inteiro`
    k = next(n for n, st in enumerate(ck.orelse) if isinstance(st, ast.Delete)
             and any(getattr(t, "id", "") == "_texto_inteiro" for t in st.targets))
    ns1 = {"__name__": "pagina_ns", "extract_text": extract_text, "pdf_path": pdf,
           "page_index": 0, "filename": ARQ,
           "_TETO_TEXTO_DA_PROVA": main._TETO_TEXTO_DA_PROVA,
           "_guarda_numeros_do_texto": main._guarda_numeros_do_texto,
           "_numeros_do_texto_por_prancha": {}}
    exec(compile(_codigo(linhas, ck.orelse[:k + 1]), "pagina", "exec"), ns1)
    mapa = ns1["_numeros_do_texto_por_prancha"]
    assert len(ns1["text"]) <= 6000, "a IA passou a receber mais que 6000 caracteres"
    assert {490, 8270} <= set(mapa.get((ARQ.lower(), 0), ())), (
        "a página nova não guardou os números do quadro: %r" % sorted(mapa))

    # 2) o checkpoint: o `if not result.get("error")` que chama `_ckpt_save`
    bloco = [n for n in ast.walk(ck) if isinstance(n, ast.If)
             and any(isinstance(s, ast.Expr) and isinstance(s.value, ast.Call)
                     and getattr(s.value.func, "id", "") == "_ckpt_save" for s in n.body)]
    assert len(bloco) == 1, len(bloco)
    salvos = []
    ns2 = {"__name__": "ckpt_ns", "result": {"items": []}, "_stem": "prancha-A_p0",
           "_pdfvec_por_prancha": {}, "_pdfvec_falhas": [], "filename": ARQ,
           "page_index": 0, "job_id": "ee801b82", "print": lambda *a, **k: None,
           "_numeros_do_texto_por_prancha": mapa,
           "_anexa_numeros_do_texto": main._anexa_numeros_do_texto,
           # o checkpoint é JSON: guarda o que o save RECEBEU, na hora
           "_ckpt_save": lambda job, stem, res, **k: salvos.append(json.loads(json.dumps(res)))}
    exec(compile(_codigo(linhas, bloco), "ckpt", "exec"), ns2)
    assert len(salvos) == 1 and salvos[0].get("_numeros_do_texto"), (
        "o checkpoint foi gravado SEM os números do texto: %r" % sorted(salvos[0]))

    # 3) a retomada: o corpo inteiro do ramo do checkpoint
    class _Jobs:
        def update_field(self, *a, **k):
            pass
    ns3 = {"__name__": "retomada_ns", "_ckpt_cache": {"k": salvos[0]}, "_ck_key": "k",
           "jobs": _Jobs(), "i": 0, "total": 1, "_u_total": "", "_sufixo_total": "",
           "_disp": ARQ, "_stem": "prancha-A_p0", "print": lambda *a, **k: None,
           "_a_escala_sustenta_a_medicao": lambda *a, **k: (True, ""),
           "_log_error": lambda *a, **k: None, "_pdfvec_falhas": [],
           "_pdfvec_por_prancha": {}, "_pdfvec_area_m2": 0.0, "_pdfvec_compr_m": 0.0,
           "pdf_path": pdf, "filename": ARQ, "page_index": 0, "job_id": "ee801b82",
           "_restaura_numeros_do_texto": main._restaura_numeros_do_texto,
           "_numeros_do_texto_por_prancha": {}}
    exec(compile(_codigo(linhas, ck.body), "retomada", "exec"), ns3)
    volta = ns3["_numeros_do_texto_por_prancha"]
    assert volta == mapa, "a retomada não trouxe os números de volta: %r" % sorted(volta)

    # 4) e a prova chega: o quadro do caso fica com número no job RETOMADO
    itens = _roda(_quadro_do_caso(), volta)
    assert _soma(itens, "m³") == 26.8 and _soma(itens, "m²") == 183.2
