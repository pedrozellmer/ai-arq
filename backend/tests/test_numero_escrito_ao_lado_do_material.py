# -*- coding: utf-8 -*-
"""Número com unidade ESCRITO na prancha, ao lado do material, não é chute — não zera.

🩸 05/10/2026 — job de 16 PDFs: a legenda escreve "PISO EM GRANITINA … 66,00
m²", a leitura copiou o 66,00 e a honestidade de área zerou (idem forro,
lamato, revitalização; a cliente preenchia à mão). Noutro job, "Volume de
concreto (C-25) = 6.16 m³" e "Área de forma = 77.80 m²" do quadro impresso,
zerados — a régua do quadro só vale quando a leitura diz "quadro de
quantitativos".

🔑 Decisão (05/10, delegada pelo Pedro): fica, ESTIMADO (nunca ✓), com a frase
do trecho. A régua mora em `engine_rules.numero_escrito_da_linha`: o mesmo
número (± 0,01), a mesma família de unidade (só m² e m³) e um material escrito
até 70 caracteres ANTES do número, sem outro número com unidade no meio, que a
própria linha cita.

📏 Medido no acervo (41 jobs com PDF): a maioria do que as linhas zeradas citam
é área de AMBIENTE, de terreno ou parcela de soma — segue zerando (controles).

🪤 Nomes de arquivo e textos FICTÍCIOS (repositório público, regra nº6).
"""
import ast
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402
import engine_rules as er  # noqa: E402

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARQ = "prancha-A.pdf"
ARQ_B = "prancha-B.pdf"
_LIDO = "Quantidade lida da legenda da prancha. | Estimativa: lido de PDF, não medido em geometria"

LEGENDA = ("LEGENDA DE REVESTIMENTOS\nPISO EM GRANITINA CINZA A DEFINIR 120×120\n"
           "1 SOLEIRA EM GRANITINA\n66,00m²\n")
FORRO = "FORRO EM GESSO PLACA COM PINTURA EM PVA, COR BRANCO FOSCO 39,80m²\n"
QUADRO = ("PESO TOTAL (kg) CA50 369.9 CA60 81.9 Volume de concreto (C-25) = 6.16 m³ "
          "Área de forma = 77.80 m² P1 P2\n")
VISTA = ("PORTA E ALISAR EM ACM COR BRANCA DIVISÓRIAS EM GRANITO CINZA ESCOVADO FUNDO "
         "PAREDE REVESTIDA COM PORCELANATO LINHA X 90X90cm - FABRICANTE Y A=11,27 m² "
         "BACIA SANITÁRIA\n")


class _Item:
    def __init__(self, desc, unit, qty, obs=_LIDO, ref_sheet=ARQ + " (PLANTA)", origem="vision_pdf"):
        self.description = desc
        self.unit = unit
        self.quantity = qty
        self.observations = obs
        self.ref_sheet = ref_sheet
        self.origem = origem
        self.confidence = "estimado"


def _mapa(*paginas):
    """{(arquivo, página): registros} do jeito que o laço de páginas monta."""
    out = {}
    for arq, pg, texto in paginas:
        regs = er.numeros_escritos_com_material(texto)
        if regs:
            out[(arq.lower(), pg)] = regs
    return out


def _roda(itens, mapa, **kw):
    main._apply_area_honesty(itens, numeros_com_material_por_prancha=mapa, **kw)
    return itens


def _selo(it):
    return str(getattr(it.confidence, "value", it.confidence))


def _um(desc, unit, qty, texto, **kw):
    it = _Item(desc, unit, qty, **kw)
    _roda([it], _mapa((ARQ, 0, texto)))
    return it


# ══════════════════════════════════════════════════════════════════════════
#  O que FICA
# ══════════════════════════════════════════════════════════════════════════
def test_o_numero_da_legenda_ao_lado_do_material_fica_ESTIMADO():
    it = _um("Piso em granitina cinza — formato 120×120", "m²", 66.0, LEGENDA)
    assert it.quantity == 66.0, "o número escrito na legenda foi zerado"
    assert _selo(it) == "estimado", "PDF não foi medido: nunca ✓"
    assert it.observations.startswith(er.MARCA_VALOR_ESCRITO), (
        "a procedência vem NA FRENTE (a revisão mostra 110 caracteres): %r"
        % it.observations[:120])
    assert "66,00m²" in it.observations and "GRANITINA" in it.observations, (
        "a frase diz o trecho de onde veio o número")
    assert "Área NÃO medida" not in it.observations
    assert main._apply_area_honesty.ultimo_escritos_preservados == 1


def test_qualquer_material_do_item_vale_nao_so_o_mais_perto():
    """"FORRO EM GESSO PLACA COM PINTURA …": a linha do forro diz só forro."""
    it = _um("Forro em gesso placa — liso", "m²", 39.8, FORRO)
    assert it.quantity == 39.8


def test_o_quadro_impresso_com_PONTO_decimal_fica():
    concreto = _Item("Concreto armado C-25 — vigas", "m³", 6.16)
    forma = _Item("Fôrma de madeira — vigas", "m²", 77.8)
    _roda([concreto, forma], _mapa((ARQ, 0, QUADRO)))
    assert (concreto.quantity, forma.quantity) == (6.16, 77.8)


def test_milhar_e_arredondamento_de_um_centesimo():
    assert _um("Piso em granitina", "m²", 1447.65, "PISO EM GRANITINA 1.447,65 m²").quantity == 1447.65
    assert _um("Piso em granitina", "m²", 66.01, LEGENDA).quantity == 66.01


def test_a_pagina_do_ref_sheet_escolhe_a_prancha():
    it = _Item("Piso em granitina", "m²", 66.0, ref_sheet=ARQ + " (p2 · PLANTA DE PISO)")
    _roda([it], _mapa((ARQ, 0, FORRO), (ARQ, 1, LEGENDA)))
    assert it.quantity == 66.0


# ══════════════════════════════════════════════════════════════════════════
#  CONTROLES — o que continua zerando
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_o_numero_e_de_OUTRO_material_da_mesma_vista():
    """O pdfium junta a vista numa linha só: o 11,27 é do porcelanato (colado), o
    granito fica ~90 antes. A divisória de granito NÃO herda a área da parede."""
    it = _um("Divisória de banheiro em granito cinza escovado", "m²", 11.27, VISTA)
    assert it.quantity == 0, "a divisória herdou o número do porcelanato"
    assert er.MARCA_VALOR_ESCRITO not in it.observations
    assert _um("Revestimento de parede em porcelanato 90×90", "m²", 11.27, VISTA).quantity == 11.27


def test_CONTROLE_material_que_a_linha_nao_cita():
    assert _um("Forro em gesso acartonado", "m²", 66.0, LEGENDA).quantity == 0


def test_CONTROLE_material_DEPOIS_do_numero_nao_conta():
    t = "ÁREA DA EDIFICAÇÃO A=125,46m² TELHA CERÂMICA 2 ÁGUAS"
    assert _um("Cobertura em telha cerâmica", "m²", 125.46, t).quantity == 0


def test_CONTROLE_o_material_DEPOIS_e_do_proximo_item_da_legenda():
    """🧬 Mutante vivo (05/10): o controle de cima só tinha material DEPOIS — e aí
    o trecho sai vazio e a linha cai por outro caminho. No acervo o caso é este:
    o material do item antes, e o do próximo item colado depois do número."""
    t = ("FUNDO PAREDE REVESTIDA COM PORCELANATO LINHA X - FABRICANTE Y A=69,68 m² "
         "ESQUADRIA EM ALUMÍNIO PRETO FOSCO")
    assert _um("Esquadria em alumínio preto fosco", "m²", 69.68, t).quantity == 0
    assert _um("Revestimento de parede em porcelanato", "m²", 69.68, t).quantity == 69.68


def test_CONTROLE_material_LONGE_do_numero():
    t = "PISO EM GRANITINA " + "x " * 40 + "66,00m²"
    assert _um("Piso em granitina", "m²", 66.0, t).quantity == 0


def test_CONTROLE_nao_atravessa_outro_numero_com_unidade():
    t = "PISO EM GRANITINA 66,00m²\nBANHO\n12,40m²"
    assert _um("Piso em granitina", "m²", 12.4, t).quantity == 0


def test_CONTROLE_area_de_AMBIENTE_nao_e_material():
    t = "SALA\n15,77 m2\nPD:2,50\nQUARTO\n9,74 m2"
    assert _um("Pintura acrílica — sala", "m²", 15.77, t).quantity == 0


def test_CONTROLE_forma_dentro_de_PLATAFORMA_nao_e_forma():
    """No acervo: "PLATAFORMA OPERACIONAL = 10,24m²" (área de piso de um ambiente)."""
    t = "ÁREA DE PÚBLICO\nPLATAFORMA OPERACIONAL = 10,24m²"
    assert er.numeros_escritos_com_material(t) == []
    assert _um("Fôrma de madeira — vigas", "m²", 10.24, t).quantity == 0


def test_CONTROLE_material_dentro_de_outra_palavra_da_descricao():
    t = "Área de forma = 77,80 m²"
    assert _um("Plataforma metálica — piso técnico elevado", "m²", 77.8, t).quantity == 0


def test_CONTROLE_numero_diferente_e_familia_diferente():
    assert _um("Piso em granitina", "m²", 66.02, LEGENDA).quantity == 0
    assert _um("Piso em granitina", "m³", 66.0, LEGENDA).quantity == 0


def test_CONTROLE_metro_linear_fica_de_fora():
    """Em metro, o número ao lado do material é quase sempre ALTURA."""
    t = "GUARDA-CORPO EM VIDRO H=1,10 m\nRODAPÉ EM GRANITINA 34,60 m"
    assert er.numeros_escritos_com_material(t) == [], "número em metro não vira registro"
    assert _um("Rodapé em granitina", "ml", 34.6, t).quantity == 0
    assert _um("Guarda-corpo em vidro", "m", 1.1, t).quantity == 0


def test_CONTROLE_o_texto_de_OUTRA_prancha_nao_vale():
    it = _Item("Piso em granitina", "m²", 66.0)
    _roda([it], _mapa((ARQ_B, 0, LEGENDA)))
    assert it.quantity == 0


def test_CONTROLE_arquivo_de_varias_paginas_sem_pagina_na_linha():
    it = _Item("Piso em granitina", "m²", 66.0, ref_sheet=ARQ + " (PLANTA)")
    _roda([it], _mapa((ARQ, 0, LEGENDA), (ARQ, 1, FORRO)))
    assert it.quantity == 0, "sem a página, não se sabe de qual prancha é o texto"


def test_CONTROLE_sem_o_mapa_nada_muda():
    it = _Item("Piso em granitina", "m²", 66.0)
    main._apply_area_honesty([it])
    assert it.quantity == 0


def test_rodar_de_novo_nao_empilha_a_frase():
    it = _Item("Piso em granitina", "m²", 66.0)
    mapa = _mapa((ARQ, 0, LEGENDA))
    _roda([it], mapa)
    _roda([it], mapa)
    assert it.observations.count(er.MARCA_VALOR_ESCRITO) == 1


# ══════════════════════════════════════════════════════════════════════════
#  Com a régua do quadro (22/09): quem tem PROVA vence, o TOTAL fica em branco
# ══════════════════════════════════════════════════════════════════════════
_QUADRO_LIDO = "Valor lido diretamente do quadro de quantitativos da prancha."
_QUADRO_TXT = ("QUADRO DE QUANTITATIVOS\nFÔRMA ESTRUTURA 1 = 37,20 m²\n"
               "FÔRMA ESTRUTURA 2 = 31,20 m²\nTOTAL DE FÔRMA = 68,40 m²\n")


def _quadro():
    return [_Item("Fôrma de madeira — Estrutura 1", "m²", 37.2, _QUADRO_LIDO),
            _Item("Fôrma de madeira — Estrutura 2", "m²", 31.2, _QUADRO_LIDO),
            _Item("Fôrma de madeira — TOTAL", "m²", 68.4, _QUADRO_LIDO)]


def test_o_quadro_COM_prova_sai_pelo_ramo_do_quadro_e_o_TOTAL_fica_em_branco():
    itens = _quadro()
    main._apply_area_honesty(
        itens, numeros_do_texto_por_prancha={(ARQ.lower(), 0): er.numeros_decimais_do_texto(_QUADRO_TXT)},
        numeros_com_material_por_prancha=_mapa((ARQ, 0, _QUADRO_TXT)))
    assert [i.quantity for i in itens] == [37.2, 31.2, 0]
    assert all(er.MARCA_VALOR_ESCRITO not in i.observations for i in itens)
    assert main._apply_area_honesty.ultimo_quadro_preservados == 2


def test_o_quadro_SEM_prova_com_o_numero_ao_lado_do_material_fica_ESTIMADO():
    """Sem o mapa da prova e sem TOTAL lido (que provaria as parcelas), o quadro
    zeraria (`sem_prova`): o número escrito ao lado da palavra FÔRMA salva as
    parcelas — estimado, pelo ramo novo."""
    itens = _quadro()[:2]
    _roda(itens, _mapa((ARQ, 0, _QUADRO_TXT)))
    assert [i.quantity for i in itens] == [37.2, 31.2]
    assert all(_selo(i) == "estimado" for i in itens)
    assert all(i.observations.startswith(er.MARCA_VALOR_ESCRITO) for i in itens)


def test_CONTROLE_o_quadro_SEM_prova_e_SEM_material_continua_zerado():
    itens = _quadro()[:2]
    _roda(itens, _mapa((ARQ, 0, "ESTRUTURA 1 = 37,20 m²\nESTRUTURA 2 = 31,20 m²\n")))
    assert [i.quantity for i in itens] == [0, 0]


# ══════════════════════════════════════════════════════════════════════════
#  O mapa chega: laço de páginas, checkpoint e chamada
# ══════════════════════════════════════════════════════════════════════════
def test_os_registros_viajam_no_checkpoint_e_voltam_na_retomada():
    nums, mat = {}, {}
    main._guarda_numeros_do_texto(nums, ARQ, 0, LEGENDA, mapa_material=mat)
    assert mat, "a página não guardou o número com material"
    result = {"items": []}
    main._anexa_numeros_do_texto(nums, ARQ, 0, result, mapa_material=mat)
    result = json.loads(json.dumps(result))          # o checkpoint é JSON
    volta_n, volta_m = {}, {}
    main._restaura_numeros_do_texto(volta_n, ARQ, 0, result, mapa_material=volta_m)
    assert volta_m == mat and volta_n == nums


def test_pagina_so_com_material_volta_sem_os_outros_numeros():
    """O registro volta mesmo se a página não tiver nenhum outro decimal."""
    result = json.loads(json.dumps({"_numeros_com_material": [[6600, "m2", ["granitina"], "GRANITINA 66,00m²"]]}))
    volta_m = {}
    main._restaura_numeros_do_texto({}, ARQ, 0, result, mapa_material=volta_m)
    assert volta_m == {(ARQ.lower(), 0): [(6600, "m2", ("granitina",), "GRANITINA 66,00m²")]}


def test_as_tres_pontas_do_laco_passam_o_MESMO_mapa_novo():
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    pj = next(n for n in ast.parse(src).body
              if isinstance(n, ast.FunctionDef) and n.name == "process_job")
    for nome in ("_guarda_numeros_do_texto", "_restaura_numeros_do_texto", "_anexa_numeros_do_texto"):
        cs = [n for n in ast.walk(pj) if isinstance(n, ast.Call)
              and getattr(n.func, "id", "") == nome]
        assert len(cs) == 1, nome
        kw = {k.arg: getattr(k.value, "id", "") for k in cs[0].keywords}
        assert kw.get("mapa_material") == "_numeros_com_material_por_prancha", (nome, kw)


def test_a_chamada_REAL_entrega_o_mapa_novo_a_honestidade():
    """Executa o trecho real do `process_job` com um espião no lugar da função
    (a mesma fatia do guarda do quadro)."""
    import textwrap
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
    visto = {}

    def _espiao(*a, **k):
        visto.update(k)
        return 0, 0

    mapa = _mapa((ARQ, 0, LEGENDA))

    class _PD:
        total_area = 0
        total_area_source = ""
        user_pe_direito = 0
        warnings = []

    ns = {"__name__": "chamada_ns", "project_data": _PD(), "all_items": [],
          "job_id": "teste", "_apply_area_honesty": _espiao,
          "_log_error": lambda *a, **k: None, "_pdfvec_area_m2": 0.0,
          "_pdfvec_por_prancha": {}, "_pdfvec_falhas": [],
          "_avisos_da_medicao_pdfvec": lambda *a, **k: ([], ""),
          "_linha_pdfvec_memoria": lambda *a, **k: "",
          "_pranchas_perto_do_teto": lambda *a, **k: [],
          "_numeros_do_texto_por_prancha": {},
          "_numeros_com_material_por_prancha": mapa}
    exec(compile(textwrap.dedent("".join(linhas[i:fim[0] + 1])), "chamada", "exec"), ns)
    assert visto.get("numeros_com_material_por_prancha") == mapa, sorted(visto)


def test_o_texto_REAL_do_PDF_pelo_caminho_da_producao(tmp_path):
    """reportlab → extract_text (pypdfium2, o da produção) → registros → honestidade."""
    from reportlab.lib.pagesizes import A3
    from reportlab.pdfgen import canvas
    from processor import extract_text
    pdf = str(tmp_path / ARQ)
    c = canvas.Canvas(pdf, pagesize=A3)
    c.drawString(60, 900, "LEGENDA DE REVESTIMENTOS")
    c.drawString(60, 880, "PISO EM GRANITINA CINZA A DEFINIR 120x120")
    c.drawString(60, 860, "66,00m2")
    c.drawString(60, 700, "SALA")
    c.drawString(60, 680, "15,77 m2")
    c.save()
    nums, mat = {}, {}
    main._guarda_numeros_do_texto(nums, ARQ, 0, extract_text(pdf, 0, char_budget=main._TETO_TEXTO_DA_PROVA),
                                  mapa_material=mat)
    piso = _Item("Piso em granitina cinza", "m²", 66.0)
    pintura = _Item("Pintura acrílica — sala", "m²", 15.77)
    _roda([piso, pintura], mat)
    assert (piso.quantity, pintura.quantity) == (66.0, 0)
