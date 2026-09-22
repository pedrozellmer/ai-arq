# -*- coding: utf-8 -*-
"""Contagem, verba, peso e volume não dizem "medido do desenho".

🩸 22/09/2026 — job 844603fb: 1 PDF de 1 página, planta de pontos elétricos de
um residencial. 26 das 35 linhas diziam ao cliente "Medido do desenho com
escala 1:50 lida do rótulo escrito ao lado do próprio desenho — confira a
escala do seu PDF", e a MESMA célula dizia "Contagem visual estimada". No job
f8d8e6d8 (estrutura), 9 linhas de un e kg com a frase — uma é 1.850 kg de aço
por taxa de 100 kg/m³. Nenhuma foi medida: a geometria do PDF só mede m² de
ambiente e m de parede.

🔑 A frase é o molde que o NOSSO prompt manda a IA escrever — a regra não dizia
em quais itens. O conserto tem duas pontas, e as duas são chamadas aqui:
  · `_regra_da_medicao_sem_prova` — a regra do prompt diz ONDE a frase cabe;
  · `_tira_medido_do_desenho_de_quem_nao_foi_medido` — a IA não obedece
    sempre, então o texto é limpo depois, fora de m²/m.

📏 60 d, sem avaliação: 294 linhas em 16 jobs com a frase fora de m²/m.

🪤 Nomes neutros: repositório público. As observações imitam a FORMA real das
linhas (a frase, o conector, a nota que vem depois), não o texto do cliente.
"""
import ast
import io
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

_MAIN_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")

_FRASE_VISTA = ("Medido do desenho com escala 1:50 lida do rótulo escrito ao lado "
                "do próprio desenho — confira a escala do seu PDF.")


class _It:
    """Item mínimo: só o que a limpeza lê e escreve."""

    def __init__(self, desc, unit, qty, obs, conf="estimado"):
        self.description, self.unit, self.quantity = desc, unit, qty
        self.observations, self.confidence = obs, conf


def _tem_a_frase(obs):
    return "medido do desenho com escala" in (obs or "").lower()


# ══════════════════════════════════════════════════════════════════════════
#  O caso: a planta de pontos elétricos (job 844603fb)
# ══════════════════════════════════════════════════════════════════════════
def _planilha_de_pontos():
    """35 linhas na forma do job: 24 un + 2 vb com a frase, 1 vb sem, 8 ml."""
    itens = []
    for i in range(24):
        itens.append(_It(
            "Tomada 2P+T 10A H=0,40 m — ponto %d" % i, "un", 10 + i,
            "Contagem visual estimada na planta do pavimento tipo (H=0,40m). "
            "Confirmar com quadro de cargas e projeto executivo. " + _FRASE_VISTA
            + (" | Fundido de 2 entradas com mesma qty %d.0 un — descrições "
               "similares." % (10 + i) if i % 5 == 0 else "")))
    for i in range(2):
        itens.append(_It(
            "Alimentação para equipamento — eletroduto %d" % i, "vb", 1,
            "Item indicado na planta com nota. Bitola a confirmar com diagrama "
            "unifilar. Medido do desenho com escala 1:75 lida do rótulo escrito "
            "ao lado do próprio desenho — confira a escala do seu PDF."))
    itens.append(_It("Verba de quadro", "vb", 1, "Verba sem prancha."))
    for i in range(8):
        itens.append(_It(
            "Eletroduto PVC 3/4\" — trecho %d" % i, "ml", 0,
            "Comprimento NÃO medido (lido de PDF por IA, não da geometria) — "
            "preencha a metragem."))
    return itens


def test_a_planta_de_pontos_perde_as_26_frases_falsas():
    itens = _planilha_de_pontos()
    antes = sum(1 for it in itens if _tem_a_frase(it.observations))
    assert antes == 26, "o cenário não reproduz o caso: %d linhas com a frase" % antes

    limpos = main._tira_medido_do_desenho_de_quem_nao_foi_medido(itens)

    assert limpos == 26, limpos
    sobrou = [it.description for it in itens if _tem_a_frase(it.observations)]
    assert not sobrou, "ainda dizem 'medido do desenho': %s" % sobrou[:3]


def test_o_resto_da_linha_fica_numero_unidade_selo_e_o_que_ela_diz_de_si():
    """🚫 Muda só TEXTO: a contagem continua dizendo que é contagem, a nota da
    fusão continua, e número, unidade e selo não se mexem."""
    itens = _planilha_de_pontos()
    retrato = [(it.quantity, it.unit, it.confidence) for it in itens]
    main._tira_medido_do_desenho_de_quem_nao_foi_medido(itens)

    assert [(it.quantity, it.unit, it.confidence) for it in itens] == retrato
    t0 = itens[0].observations
    assert t0.startswith("Contagem visual estimada"), t0
    assert "Confirmar com quadro de cargas e projeto executivo." in t0, t0
    assert "| Fundido de 2 entradas com mesma qty 10.0 un" in t0, t0
    assert "  " not in t0 and ". ." not in t0 and ".." not in t0, repr(t0)
    vb = itens[24].observations
    assert vb == ("Item indicado na planta com nota. Bitola a confirmar com "
                  "diagrama unifilar."), repr(vb)


def test_CONTROLE_linha_de_metro_fica_com_a_honestidade_de_area():
    """m²/m é o que a geometria do PDF mede — lá quem decide o texto é
    `_apply_area_honesty`, e esta limpeza não pode passar por cima."""
    piso = _It("Piso vinílico", "m²", 95.3,
               "Área dos ambientes medidos geometricamente: 95,3 m². "
               "Medido do desenho com escala 1:100 lida da caixa de recorte do "
               "PDF — confira a escala do seu PDF.")
    rodape = _It("Rodapé", "m", 40.0, "Perímetro. " + _FRASE_VISTA)
    # 🪤 `ml` é a grafia de metro que a IA mais usa (revisão de 22/09, R03)
    divisoria = _It("Divisória", "ml", 12.0, "Trecho. " + _FRASE_VISTA)
    itens = [piso, rodape, divisoria]
    obs = [it.observations for it in itens]
    assert main._tira_medido_do_desenho_de_quem_nao_foi_medido(itens) == 0
    assert [it.observations for it in itens] == obs


# ══════════════════════════════════════════════════════════════════════════
#  O caso da estrutura (job f8d8e6d8): kg por taxa, minúscula, nota depois
# ══════════════════════════════════════════════════════════════════════════
def test_aco_por_taxa_deixa_de_dizer_medido_e_continua_dizendo_taxa():
    aco = _It("Armadura em aço CA-50 e CA-60 — estruturas enterradas", "kg", 1850,
              "Estimativa por taxa de consumo: ~18,5m³ × taxa 100kg/m³ = 1.850kg. "
              "Confirmar com projeto estrutural complementar. Medido do desenho "
              "com escala 1:25 lida do rótulo escrito ao lado do próprio desenho "
              "— confira a escala do seu PDF.")
    sapata = _It("Armação de aço para sapatas", "kg", 52,
                 "Estimativa: taxa de armação ≈ 20kg/m³ × 2,59m³ ≈ 52kg. Confirmar "
                 "com projeto estrutural de armação. medido do desenho com escala "
                 "1:50 lida do rótulo escrito ao lado do próprio desenho — confira "
                 "a escala do seu PDF. ⚠ Este serviço aparece em 3 pranchas do "
                 "projeto (prancha-a, prancha-b). Esta linha vem da prancha dela.")
    tampa = _It("Tampa de concreto armado para poço", "un", 1,
                "1 tampa identificada na planta. Medido do desenho com escala 1:25 "
                "lida do rótulo escrito ao lado do próprio desenho — confira a "
                "escala do seu PDF.")
    volume = _It("Concreto C30 — laje de fundo", "m³", 0,
                 "Dimensões lidas da planta. " + _FRASE_VISTA)
    itens = [aco, sapata, tampa, volume]
    assert main._tira_medido_do_desenho_de_quem_nao_foi_medido(itens) == 4
    for it in itens:
        assert not _tem_a_frase(it.observations), it.observations
    assert "taxa 100kg/m³" in aco.observations and aco.quantity == 1850
    assert "⚠ Este serviço aparece em 3 pranchas" in sapata.observations, (
        "a nota de outra frente foi junto: " + sapata.observations)
    assert sapata.observations.startswith("Estimativa: taxa de armação")


def test_a_frase_no_MEIO_da_sentenca_sai_so_a_oracao():
    """Forma real: "… na prancha — medido do desenho … PDF. Incluir …". Sai o
    trecho do meio; o ponto é da frase de fora e fica."""
    t = ("Área de parede não calculada por falta de cota de pé-direito na "
         "prancha — medido do desenho com escala 1:75 lida do carimbo — confira "
         "a escala do seu PDF. Incluir área de parede após confirmação.")
    assert main._sem_medido_do_desenho(t) == (
        "Área de parede não calculada por falta de cota de pé-direito na "
        "prancha. Incluir área de parede após confirmação.")


def test_a_frase_SEM_o_confira_para_no_ponto_e_nao_come_a_nota_seguinte():
    """Forma real (14 de 300 linhas): a IA encurta o molde e para em "lida do
    carimbo." — a limpeza tem que parar ali, sem levar o aviso que vem depois."""
    t = ("Confirmar com projeto de marcenaria. Medido do desenho com escala 1:25 "
         "lida do carimbo. ⚠ Este serviço aparece em 3 pranchas do projeto "
         "(prancha-a, prancha-b). | Fundido de 2 entradas.")
    assert main._sem_medido_do_desenho(t) == (
        "Confirmar com projeto de marcenaria. ⚠ Este serviço aparece em 3 "
        "pranchas do projeto (prancha-a, prancha-b). | Fundido de 2 entradas.")


def test_linha_que_era_SO_a_frase_diz_de_onde_veio_o_numero():
    it = _It("Verba de instalação", "vb", 1,
             "Medido do desenho com escala 1:50 lida do carimbo da prancha — "
             "confira a escala do seu PDF.")
    assert main._tira_medido_do_desenho_de_quem_nao_foi_medido([it]) == 1
    assert it.observations == main._FRASE_NUMERO_DA_LEITURA
    assert "não é medição" in it.observations


def test_CONTROLE_a_negacao_verdadeira_fica():
    """'não medido do desenho' é o que o motor escreve do pé-direito informado —
    verdade, não afirmação de medida."""
    t = ("Pé-direito informado pelo cliente — não medido do desenho com escala "
         "nenhuma. Descontar vãos.")
    it = _It("Chapisco", "un", 3, t)
    assert main._tira_medido_do_desenho_de_quem_nao_foi_medido([it]) == 0
    assert it.observations == t


# ══════════════════════════════════════════════════════════════════════════
#  As bordas da limpeza (revisão de 22/09). Nenhuma forma apareceu em 90 d —
#  mas a regra nova do prompt manda a IA NÃO escrever a frase, e o jeito mais
#  provável de ela obedecer é negando-a ("Não é medido do desenho…").
# ══════════════════════════════════════════════════════════════════════════
_NEGACOES = [
    "Não é medido do desenho com escala nenhuma",
    "não foi medido do desenho com escala 1:50",
    "nao medido do desenho com escala 1:50",       # sem acento (mutante R04)
    "NÃO É MEDIDO DO DESENHO COM ESCALA nenhuma",
]


@pytest.mark.parametrize("negacao", _NEGACOES)
def test_a_negacao_com_verbo_ou_sem_acento_fica(negacao):
    t = "Contagem visual. %s; contagem na legenda." % negacao
    it = _It("Tomada", "un", 12, t)
    assert main._tira_medido_do_desenho_de_quem_nao_foi_medido([it]) == 0, it.observations
    assert it.observations == t


@pytest.mark.parametrize("negacao", _NEGACOES)
def test_CONTROLE_sem_o_nao_a_mesma_frase_sai(negacao):
    """A mesma linha sem a palavra "não": prova que quem a segura acima é a
    negação, e não uma frase que a limpeza nem reconheceria."""
    afirma = re.sub(r"(?i)n[ãa]o ", "", negacao)
    t = "Contagem visual. %s; contagem na legenda." % afirma
    novo = main._sem_medido_do_desenho(t)
    assert "medido do desenho" not in novo.lower(), novo
    assert novo.startswith("Contagem visual.") and novo.endswith("contagem na legenda."), novo


@pytest.mark.parametrize("dentro", [
    "medido do desenho com escala 1:50 lida do carimbo da prancha — confira a escala do seu PDF",
    "medido do desenho com escala 1:50 lida do carimbo da prancha",
    ("medido do desenho com escala 1:50 lida das cotas escritas na prancha (por "
     "votação) — confira a escala do seu PDF"),
])
def test_a_frase_entre_PARENTESES_sai_com_os_parenteses(dentro):
    """Sobrava "Contagem ()." — e, sem o "confira", um "(" aberto."""
    assert main._sem_medido_do_desenho("Contagem (%s). Fim." % dentro) == "Contagem. Fim."


def test_CONTROLE_o_parentese_DA_FONTE_fica_dentro_da_frase_que_sai():
    """"(por votação)" é parte da fonte `cotas`: fora de parênteses, a frase
    sai inteira e o resto da linha fica."""
    t = ("Contagem. Medido do desenho com escala 1:50 lida das cotas escritas na "
         "prancha (por votação) — confira a escala do seu PDF. Fim.")
    assert main._sem_medido_do_desenho(t) == "Contagem. Fim."


def test_travessao_no_comeco_nao_deixa_so_o_ponto():
    it = _It("Verba", "vb", 1, "— Medido do desenho com escala 1:50 lida do carimbo "
                               "— confira a escala do seu PDF.")
    assert main._tira_medido_do_desenho_de_quem_nao_foi_medido([it]) == 1
    assert it.observations == main._FRASE_NUMERO_DA_LEITURA, repr(it.observations)


def test_se_a_IA_so_disse_a_frase_a_nota_do_motor_nao_fica_sozinha():
    """O 1º segmento é o que a IA disse da linha; a nota da fusão não diz de
    onde veio o número."""
    it = _It("Tomada", "un", 3,
             "Medido do desenho com escala 1:50 lida do carimbo da prancha — "
             "confira a escala do seu PDF. | Fundido de 2 entradas com mesma qty "
             "3.0 un — descrições similares.")
    assert main._tira_medido_do_desenho_de_quem_nao_foi_medido([it]) == 1
    assert it.observations == (
        main._FRASE_NUMERO_DA_LEITURA + " | Fundido de 2 entradas com mesma qty "
        "3.0 un — descrições similares."), it.observations


def test_CONTROLE_com_texto_da_IA_no_1o_segmento_nao_entra_a_frase_de_reserva():
    t = ("Contagem visual. Medido do desenho com escala 1:50 lida do carimbo — "
         "confira a escala do seu PDF. | Fundido de 2 entradas.")
    assert main._sem_medido_do_desenho(t) == "Contagem visual. | Fundido de 2 entradas."


def test_nota_do_meio_que_era_so_a_frase_sai_inteira():
    t = ("Contagem visual. | Medido do desenho com escala 1:50 lida do carimbo — "
         "confira a escala do seu PDF. | Fundido de 2 entradas.")
    assert main._sem_medido_do_desenho(t) == "Contagem visual. | Fundido de 2 entradas."


def test_observacao_que_so_tinha_a_frase_depois_do_separador_nao_fica_vazia():
    """1º segmento vazio de origem e a frase sozinha depois do "|": sem a
    reserva, a linha sairia sem observação nenhuma."""
    t = "| Medido do desenho com escala 1:50 lida do carimbo — confira a escala do seu PDF."
    assert main._sem_medido_do_desenho(t) == main._FRASE_NUMERO_DA_LEITURA


def test_a_frase_curta_para_no_ponto_e_virgula_e_nao_come_o_resto():
    t = ("Contagem. Medido do desenho com escala 1:50 lida do carimbo; 12 pontos "
         "contados na legenda")
    assert main._sem_medido_do_desenho(t) == "Contagem. 12 pontos contados na legenda"


@pytest.mark.parametrize("sep", ["; ", ". "])
def test_o_molde_partido_antes_do_confira_sai_inteiro(sep):
    """"… lida do carimbo; confira a escala do seu PDF." é o MOLDE com outro
    separador — parar no ";" deixaria um "confira a escala" órfão."""
    t = ("Contagem. Medido do desenho com escala 1:50 lida do carimbo%sconfira a "
         "escala do seu PDF. Fim." % sep)
    assert main._sem_medido_do_desenho(t) == "Contagem. Fim.", sep


# ══════════════════════════════════════════════════════════════════════════
#  A regra do prompt: onde a frase cabe
# ══════════════════════════════════════════════════════════════════════════
def _regra():
    fonte, ressalva = main._frase_da_escala_sem_prova("vista")
    return main._regra_da_medicao_sem_prova(50, fonte, ressalva), fonte


def test_a_regra_diz_EM_QUAIS_itens_a_procedencia_cabe():
    regra, _ = _regra()
    assert "Só na observação de item de ÁREA (m²) ou de COMPRIMENTO (m)" in regra, regra
    for proibido in ("contagem (un)", "verba (vb)", "peso (kg)", "volume (m³)"):
        assert proibido in regra, (proibido, regra)
    assert "NÃO escreva essa frase" in regra, regra
    # regra dura nº1 continua escrita
    assert "NUNCA 'confirmado'" in regra, regra


def test_o_molde_da_regra_e_o_mesmo_que_as_duas_limpezas_reconhecem():
    """🪤 Texto é dominó: se a regra mudar a frase, a limpeza da honestidade
    (`_limpa_afirmacao_de_medida`) e a desta frente param de reconhecer o que
    a IA escreve — calado. O molde sai da PRÓPRIA regra, não daqui."""
    regra, fonte = _regra()
    ini = regra.index("'medido do desenho")
    molde = regra[ini + 1:regra.index("'", ini + 1)]
    assert molde == ("medido do desenho com escala 1:50 lida %s — confira a "
                     "escala do seu PDF" % fonte), molde
    linha = "Contagem visual estimada. " + molde[0].upper() + molde[1:] + "."
    assert main._sem_medido_do_desenho(linha) == "Contagem visual estimada."
    assert not _tem_a_frase(main._limpa_afirmacao_de_medida(linha))


# ══════════════════════════════════════════════════════════════════════════
#  INTEGRAÇÃO — o process_job usa as duas pontas, na ordem certa
# ══════════════════════════════════════════════════════════════════════════
def _chamadas_no_process_job():
    arv = ast.parse(io.open(_MAIN_PY, encoding="utf-8").read())
    pj = next(n for n in arv.body
              if isinstance(n, ast.FunctionDef) and n.name == "process_job")
    linhas = {}
    for n in ast.walk(pj):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            linhas.setdefault(n.func.id, []).append(n.lineno)
    return pj, linhas


def test_o_process_job_monta_a_regra_pela_funcao():
    """🪤 Guarda de FONTE, assumido: prova que a regra que vai pro prompt é a
    que os testes acima executam, e que o molde antigo não voltou inline."""
    pj, linhas = _chamadas_no_process_job()
    assert "_regra_da_medicao_sem_prova" in linhas, "a regra voltou a ser montada inline"
    for n in ast.walk(pj):
        if isinstance(n, ast.JoinedStr):
            lit = "".join(p.value for p in n.values
                          if isinstance(p, ast.Constant) and isinstance(p.value, str))
            assert "escreva a procedência" not in lit, (
                "molde de procedência inline no process_job (linha %s)" % n.lineno)


def test_a_limpeza_roda_depois_da_honestidade_e_antes_do_resgate_de_comprimento():
    _, linhas = _chamadas_no_process_job()
    limpa = linhas.get("_tira_medido_do_desenho_de_quem_nao_foi_medido")
    assert limpa and len(limpa) == 1, "a limpeza não é chamada no process_job"
    honestidade = min(linhas["_apply_area_honesty"])
    resgate = min(linhas["_corrigir_comprimento_medido"])
    assert honestidade < limpa[0] < resgate, (honestidade, limpa[0], resgate)


def _chamada(pj, nome):
    (c,) = [n for n in ast.walk(pj) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name) and n.func.id == nome]
    return c


def test_as_duas_pontas_recebem_os_argumentos_certos():
    """🪤 22/09 (revisão, mutantes R06 e R08): "a chamada existe" não diz o que
    ela recebe. Chamar a limpeza com `[]` ou trocar a fonte pela ressalva na
    regra desligava o conserto com a bancada verde."""
    pj, _ = _chamadas_no_process_job()
    limpa = _chamada(pj, "_tira_medido_do_desenho_de_quem_nao_foi_medido")
    assert [ast.dump(a) for a in limpa.args] == [ast.dump(ast.Name("all_items", ast.Load()))], (
        ast.dump(limpa))
    regra = _chamada(pj, "_regra_da_medicao_sem_prova")
    assert not regra.keywords and len(regra.args) == 3, ast.dump(regra)
    assert [getattr(a, "id", None) for a in regra.args[1:]] == ["_fonte_txt", "_ressalva"], (
        ast.dump(regra))


def _recorte(ini, fim):
    """Do começo da linha de `ini` até o fim da linha de `fim`, dedentado."""
    import textwrap
    from _corpo import fonte
    src = fonte("main.py")
    assert src.count(ini) == 1 and src.count(fim) == 1, (ini, fim)
    a = src.rindex(chr(10), 0, src.index(ini)) + 1
    b = src.index(chr(10), src.index(fim))
    return textwrap.dedent(src[a:b + 1])


def test_o_prompt_EXECUTADO_leva_a_regra_com_a_fonte_e_a_ressalva_no_lugar():
    """Executa o trecho REAL do `process_job` que monta a seção de medição do
    prompt — da escolha da fonte até `_vet_secao`."""
    codigo = _recorte("_fonte_txt, _ressalva = _frase_da_escala_sem_prova(_fonte)",
                      '_vet_secao = "\\n".join(_l2)')
    ns = {"_vm": {"scale": 50, "scale_src": "vista", "n_rooms": 3, "rooms_m2": 95.3,
                  "walls_m": 40.0, "n_walls": 12},
          "_fonte": "vista",
          "_frase_da_escala_sem_prova": main._frase_da_escala_sem_prova,
          "_regra_da_medicao_sem_prova": main._regra_da_medicao_sem_prova}
    exec(compile(codigo, "secao-da-medicao", "exec"), ns)
    fonte, ressalva = main._frase_da_escala_sem_prova("vista")
    assert ns["_l2"][-1] == main._regra_da_medicao_sem_prova(50, fonte, ressalva), ns["_l2"][-1]
    regra = ns["_vet_secao"].splitlines()[-1]
    assert ("lida %s — confira a escala do seu PDF" % fonte) in regra, regra
    assert ("porque %s." % ressalva) in regra, regra


def test_a_limpeza_EXECUTADA_no_process_job_recebe_os_itens_do_job():
    """Executa o `try:` real da limpeza, com o log trocado por um gravador."""
    from _corpo import bloco_desde, fonte
    src = fonte("main.py")
    i = src.index("_n_proc = _tira_medido_do_desenho_de_quem_nao_foi_medido(")
    # do COMEÇO da linha: `bloco_desde` mede o fim pela indentação dela
    k = src.rindex(chr(10), 0, src.rindex("try:", 0, i)) + 1
    codigo = bloco_desde("try:", src=src[k:])
    assert "_n_proc = _tira_medido" in codigo and "except Exception" in codigo, codigo
    log = []
    it = _It("Tomada", "un", 12, "Contagem visual. " + _FRASE_VISTA)
    ns = {"all_items": [it], "job_id": "teste",
          "_tira_medido_do_desenho_de_quem_nao_foi_medido":
              main._tira_medido_do_desenho_de_quem_nao_foi_medido,
          "_log_error": lambda *a, **k: log.append((a, k))}
    exec(compile(codigo, "limpeza-da-procedencia", "exec"), ns)
    assert it.observations == "Contagem visual.", it.observations
    assert log and log[0][0][0] == "motor:procedencia-ia", log
    assert "limpos=1" in log[0][0][1] and log[0][1].get("severity") == "info", log
