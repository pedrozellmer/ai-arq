# -*- coding: utf-8 -*-
"""O número da IA que só CABE na geometria medida não pode dizer "Medido".

🩸 21/09/2026 — job a3366fbb, reforma de clínica, só PDF. A cliente abriu a
página e 2 minutos depois votou "👎 Não muito" (sem comentário). Oito linhas
diziam "Medido da GEOMETRIA do PDF, com escala lida do carimbo e NÃO
confirmada por cota":

  · duas afirmações falsas na mesma frase. O ramo que a escreve NÃO mede o
    item — só confere se o número da IA não passa de 1,3× a área dos ambientes
    medidos. Uma das linhas, 200 m² de porcelanato, começava com "Área
    estimada para consultórios" e terminava com o nosso "Medido";
  · e as DUAS pranchas medidas daquele job (planta e corte, PDFs de uma
    página) tinham a escala PROVADA por cota — 15 e 2 cotas.

📏 Base de 30 dias (projetos de cliente): 253 linhas em 24 projetos com a
frase genérica; em 86 o texto da própria IA diz "estimada"; 62 eram de
projeto com TODAS as pranchas medidas com escala conferida.

🩸 Quatro revisões adversariais no MESMO dia derrubaram versões deste conserto:
  1ª · a IA escreve SOZINHA "Medido do desenho com escala 1:X…" (o nosso
       prompt manda) — 62 de 248 linhas preservadas;
     · PDF de uma página não tem "(pN)", e a frase caía no genérico;
     · "cabe na área" prometia mais que a régua de 1,3×;
     · com medição INCOMPLETA dizia "todas conferidas".
  2ª · a busca da prancha pelo nome casava por PREFIXO e sem a página —
       emprestava "escala conferida" de OUTRA folha;
     · "não é medição desta linha" era falso quando a IA usou mesmo um
       ambiente medido — a frase passou a dizer QUEM pôs o número (a IA) e O
       QUE conferimos, que vale nos dois casos;
     · a consolidação escrevia "Cada linha é a medição da prancha dela" em
       linha LIDA, desmentindo a frase nova na mesma célula;
     · este arquivo chamava de "caso real" um cenário com o corte SEM prova —
       no job real o corte também era provado.
  3ª · o aviso "a área informada não foi usada" dizia "a gente mediu" até sem
       medição nenhuma;
     · "Esta linha é o que foi lido" (consolidação) era decidido por um selo
       PROVISÓRIO — o passo 7 depois punha a nossa medição na mesma linha. A
       frase agora fala só da ORIGEM: "Esta linha vem da prancha dela";
     · o ramo da prancha própria ainda nomeava a prancha por casamento frouxo.
  4ª · tirar "a planta não trazia cota" do aviso do UPLOAD quebrava a rota
       /inform-area, que apaga esse aviso por essa marca — ficou como estava,
       pro conserto dos avisos da área informada (rota + projeto.html juntos).

🔑 A regra que fica: a frase diz o que o código confere, e da escala só o
que os registros das pranchas sustentam.

🚫 O conserto é de TEXTO. Nenhum número muda: os casos conferem que a
quantidade saiu igual à que entrou.

🪤 Nomes de arquivo FICTÍCIOS: o repositório é público (regra dura nº6).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402
from models import BudgetItem, Confidence  # noqa: E402


class _Item:
    def __init__(self, desc, unit, qty, ref_sheet="", obs="", origem="vision_pdf"):
        self.description = desc
        self.unit = unit
        self.quantity = qty
        self.ref_sheet = ref_sheet
        self.observations = obs
        self.origem = origem
        self.confidence = "estimado"


def _prancha(arquivo, m2, validada, pagina=0, scale=100, scale_src="carimbo"):
    # `pagina` 0 = PDF de uma página, como o motor grava (`page_index`)
    return {"arquivo": arquivo, "rooms_m2": m2, "n_rooms": 19, "walls_m": 0,
            "n_walls": 0, "grupo_maior_m2": m2, "scale": scale,
            "scale_src": scale_src, "escala_validada": validada, "pagina": pagina}


PLANTA = "planta tecnica cliente-nn.pdf"
CORTE = "corte fachada cliente-nn.pdf"
MEMORIAL = "memorial descritivo cliente-nn.pdf"
#: o job real: as duas pranchas medidas com a escala provada por cota
PP_REAL = {"a": _prancha(PLANTA, 656.3, True), "b": _prancha(CORTE, 100.4, True)}
#: HIPOTÉTICO: uma provada, outra não — pra exercitar o "só parte"
PP_MISTO = {"a": _prancha(PLANTA, 656.3, True), "b": _prancha(CORTE, 100.4, False)}
PP_NENHUMA = {"a": _prancha(PLANTA, 656.3, False), "b": _prancha(CORTE, 100.4, False)}
_SOMA = 656.3 + 100.4

# a observação REAL da linha, texto da IA, sem o nosso segmento
_OBS_DA_IA = ("Legenda: 'PORCELANATO, FORMATO 60×60 CM'. Área estimada para "
              "consultórios, salas de equipe e demais ambientes secos. Confirmar "
              "distribuição por ambiente.")
# a sentença que o NOSSO prompt manda a IA escrever (main.py, "medido do
# desenho com escala 1:{scale} lida …")
_MEDIDO_DA_IA = ("Medido do desenho com escala 1:100 lida do carimbo da prancha "
                 "— confira a escala do seu PDF.")

_RESSALVA = "não conferimos item a item"
_AFIRMACAO = "não passa de 30% acima"


#: a descrição REAL da linha do job a3366fbb (é o "em pisos de ambientes
#: internos" do fim que a faz passar em `_is_floor_surface`)
_DESC_REAL = ("Porcelanato formato 60×60 cm, modelo Minimum Areia PO, cor Bege "
              "(Berge), rejunte na tonalidade Bege — assentamento com argamassa "
              "colante AC-III, em pisos de ambientes internos")


def _porcelanato(qty=200.0, ref=PLANTA, obs=_OBS_DA_IA):
    return _Item(_DESC_REAL, "m²", qty, ref_sheet=ref, obs=obs)


def _roda(itens, pp=PP_MISTO, **kw):
    kw.setdefault("pdfvec_m2", _SOMA)
    return main._apply_area_honesty(itens, pdfvec_por_prancha=pp, **kw)


def _o(it):
    return (it.observations or "").lower()


def _nao_afirma_medicao(o):
    return ("medido da geometria" not in o and "medido do desenho" not in o)


# ── o caso ────────────────────────────────────────────────────────────────
def test_o_numero_que_so_CABE_nao_diz_MEDIDO():
    """🚨 O caso: 200 m² "estimados" pela IA, que cabem em 1,3 × 656,3."""
    it = _porcelanato()
    _roda([it], pp=PP_REAL)
    assert it.quantity == 200.0, "o conserto é de TEXTO — o número mudou"
    o = _o(it)
    assert _nao_afirma_medicao(o), (
        "a linha ainda afirma que o número foi MEDIDO: %r" % it.observations)
    assert "quantidade atribuída pela ia a esta linha" in o, it.observations
    assert _RESSALVA in o, it.observations
    assert "geometria do pdf" in o, (
        "a procedência sumiu — guardas antigos a cobram por essa marca")


def test_o_caso_REAL_a_planta_provada_e_achada_pelo_NOME():
    """🚨 PDF de uma página não tem "(pN)". A linha vem da planta, e a planta
    tinha a escala provada por 15 cotas: a frase tem que dizer isso."""
    it = _porcelanato(ref=PLANTA)
    _roda([it], pp=PP_REAL)
    o = _o(it)
    assert "escala da prancha desta linha 1:100 conferida por cota" in o, it.observations
    assert "não confirmada" not in o and "só parte" not in o, it.observations


def test_o_MEDIDO_que_a_propria_IA_escreve_sai_da_linha_preservada():
    """🚨 1ª revisão: o nosso prompt manda a IA escrever "Medido do desenho com
    escala…". Sem tirar, a linha diria "medido" e "não conferimos"."""
    it = _porcelanato(obs=_OBS_DA_IA + " " + _MEDIDO_DA_IA)
    _roda([it])
    assert it.quantity == 200.0
    o = _o(it)
    assert _nao_afirma_medicao(o), (
        "a sentença da IA dizendo MEDIDO sobreviveu ao lado da nossa ressalva: %r"
        % it.observations)
    assert "área estimada para consultórios" in o, (
        "a limpeza levou junto o resto do texto da IA: %r" % it.observations)


def test_CONTROLE_linha_de_prancha_SEM_prova_diz_de_onde_veio_a_escala():
    it = _porcelanato(ref=CORTE, qty=80.0)
    _roda([it], pp=PP_MISTO)
    o = _o(it)
    assert "escala da prancha desta linha 1:100" in o, it.observations
    assert "declaração não é medida" in o, (
        "prancha sem prova perdeu a ressalva do carimbo: %r" % it.observations)
    assert "conferida por cota" not in o, it.observations


def test_a_frase_nao_promete_mais_que_a_regua_de_1_3x():
    """1ª revisão: "cabe na área" com 104,6 m² ao lado de "80,50 m²"."""
    it = _porcelanato()
    _roda([it])
    o = _o(it)
    assert ("única checagem, na geometria do pdf: não passa de 30% acima da área "
            "dos ambientes que medimos nas pranchas") in o, it.observations
    assert "cabe na área" not in o, it.observations


# ── a busca da prancha pelo NOME é estrita (2ª revisão) ──────────────────
def test_nome_que_so_COMECA_igual_nao_empresta_a_escala():
    """`planta.pdf` (provada) e `planta - cortes.pdf` (não medida): a linha do
    corte casava por prefixo e saía "conferida por cota"."""
    pp = {"a": _prancha("planta cliente-nn.pdf", 656.3, True)}
    it = _porcelanato(ref="planta cliente-nn - cortes.pdf", qty=120.0)
    _roda([it], pp=pp, pdfvec_m2=656.3)
    o = _o(it)
    assert "prancha desta linha" not in o, (
        "a escala de OUTRO arquivo foi atribuída a esta linha: %r" % it.observations)


def test_nome_de_outra_prancha_DENTRO_da_dica_da_IA_nao_empresta_a_escala():
    """A dica entre parênteses citava a planta provada; a linha é do corte."""
    pp = {"a": _prancha(PLANTA, 656.3, True), "b": _prancha(CORTE, 100.4, False)}
    it = _porcelanato(ref="%s (conforme %s)" % (CORTE, PLANTA), qty=80.0)
    _roda([it], pp=pp)
    o = _o(it)
    assert "conferida por cota" not in o, it.observations
    assert "declaração não é medida" in o, it.observations


def test_pagina_NAO_medida_nao_herda_a_escala_da_pagina_medida():
    """Caderno de 2 páginas, só a p1 medida (a p2 estourou o tempo): a linha
    da p2 herdava "conferida por cota" da p1."""
    cad = "caderno cliente-nn.pdf"
    pp = {"p1": _prancha(cad, 90.0, True, pagina=0)}
    it = _porcelanato(ref="%s (p2)" % cad, qty=60.0)
    _roda([it], pp=pp, pdfvec_m2=90.0, medicao_incompleta=True)
    o = _o(it)
    assert "prancha desta linha" not in o, it.observations
    assert "nem todas as pranchas foram medidas" in o, it.observations


def test_registro_SEM_pagina_nao_responde_por_linha_que_diz_a_pagina():
    """Checkpoint antigo: registro sem `pagina`, linha da p3."""
    cad = "caderno cliente-nn.pdf"
    pp = {"x": _prancha(cad, 90.0, True, pagina=None)}
    it = _porcelanato(ref="%s (p3)" % cad, qty=60.0)
    _roda([it], pp=pp, pdfvec_m2=90.0, medicao_incompleta=True)
    assert "prancha desta linha" not in _o(it), it.observations


def test_nome_em_MAIUSCULAS_como_chega_da_producao():
    """Os nomes reais vêm em maiúsculas; a busca compara em minúsculas."""
    arq = "PLANTA TECNICA CLIENTE-NN.PDF"
    pp = {"a": _prancha(arq, 656.3, True), "b": _prancha(CORTE, 100.4, False)}
    it = _porcelanato(ref="%s (PLANTA BAIXA TÉRREO)" % arq)
    _roda([it], pp=pp)
    assert "escala da prancha desta linha 1:100 conferida por cota" in _o(it), it.observations


def test_numero_maior_que_a_PROPRIA_prancha_nao_cita_a_escala_dela():
    """400 m² numa linha do corte (100,4 m²): só entrou pelo teto do job (a
    planta). Citar "a escala da prancha desta linha" soaria como endosso."""
    it = _porcelanato(ref=CORTE, qty=400.0)
    _roda([it], pp=PP_REAL)
    o = _o(it)
    assert it.quantity == 400.0, "o conserto é de TEXTO — o número mudou"
    assert "prancha desta linha" not in o, it.observations
    assert "as pranchas em que medimos ambientes têm escala conferida por cota" in o, it.observations


# ── quando não se sabe de qual prancha a linha veio ───────────────────────
def test_pranchas_MISTAS_e_linha_sem_prancha_nao_afirmam_nem_uma_coisa_nem_outra():
    """A linha vem do MEMORIAL, que não mediu nada: não se sabe a prancha. Com
    uma prancha provada e outra não (cenário HIPOTÉTICO), afirmar qualquer
    lado seria chute."""
    it = _porcelanato(ref=MEMORIAL)
    _roda([it], pp=PP_MISTO)
    o = _o(it)
    assert it.quantity == 200.0
    assert "só parte das pranchas medidas teve a escala conferida" in o, it.observations
    assert "têm escala conferida" not in o and "nenhuma prancha" not in o, o


def test_escala_PROVADA_em_todas_nao_sai_como_NAO_confirmada():
    it = _porcelanato(ref=MEMORIAL)
    _roda([it], pp=PP_REAL)
    o = _o(it)
    assert "não confirmada" not in o, it.observations
    assert "as pranchas em que medimos ambientes têm escala conferida por cota" in o, it.observations


def test_CONTROLE_nenhuma_prancha_provada_CONTINUA_avisando():
    """Controle positivo: onde a escala de fato não foi conferida, o aviso fica.
    Sem este par, um conserto que calasse o aviso da escala passaria verde."""
    it = _porcelanato(ref=MEMORIAL)
    _roda([it], pp=PP_NENHUMA)
    o = _o(it)
    assert "nenhuma prancha medida teve a escala conferida por cota" in o, it.observations
    assert "confira a escala do seu pdf" in o, it.observations


def test_medicao_INCOMPLETA_nao_diz_todas_conferidas():
    """🚨 1ª revisão: uma página estourou o tempo; as medidas são todas
    provadas, mas "têm escala conferida" seria sobre um conjunto parcial."""
    it = _porcelanato(ref=MEMORIAL)
    _roda([it], pp=PP_REAL, medicao_incompleta=True)
    o = _o(it)
    assert "têm escala conferida" not in o, it.observations
    assert "nem todas as pranchas foram medidas" in o, it.observations
    assert "confira a escala do seu pdf" in o, it.observations


def test_prancha_com_ZERO_de_ambientes_nao_entra_no_conjunto():
    """Prancha que não mediu ambiente (rooms_m2 = 0) não é "prancha medida"."""
    pp = dict(PP_REAL)
    pp["c"] = _prancha("detalhes cliente-nn.pdf", 0.0, False)
    it = _porcelanato(ref=MEMORIAL)
    _roda([it], pp=pp)
    assert "as pranchas em que medimos ambientes têm escala conferida" in _o(it), it.observations


def test_sem_registro_por_prancha_NAO_afirma_nada_da_escala():
    """Caller sem mapa por prancha: antes a frase inventava "carimbo e NÃO
    confirmada". Sem dado, não se afirma a fonte — só se pede pra conferir."""
    it = _porcelanato()
    main._apply_area_honesty([it], pdfvec_m2=_SOMA)
    assert it.quantity == 200.0
    o = _o(it)
    assert _RESSALVA in o, it.observations
    assert "carimbo" not in o and "conferida" not in o, (
        "sem registro de prancha, a frase afirmou algo da escala: %r" % it.observations)
    assert "confira a escala do seu pdf" in o, it.observations


def test_escala_AUSENTE_nao_vira_frase_torta():
    """Defesa contra registro incompleto (checkpoint antigo, fonte nova): a 1ª
    versão escrevia "escala sem escala escrita conferida por cota"."""
    pp = {"a": _prancha(PLANTA, 656.3, False, scale=None)}
    it = _porcelanato(ref=PLANTA)
    _roda([it], pp=pp, pdfvec_m2=656.3)
    o = _o(it)
    assert "sem escala escrita" not in o and "1:none" not in o, it.observations
    assert "não identificada" in o, it.observations


# ── a variante que conhece a PRÓPRIA prancha do item (tem "(pN)") ────────
_MULTI = "caderno cliente-nn.pdf"


def _pp_multipagina(validada):
    return {"p2": _prancha(_MULTI, 80.5, validada, pagina=1, scale=50),
            "p3": _prancha(_MULTI, 120.0, False, pagina=2, scale=50)}


def test_com_a_propria_prancha_tambem_nao_diz_MEDIDO():
    it = _porcelanato(qty=75.0, ref="%s (p2)" % _MULTI)
    _roda([it], pp=_pp_multipagina(False), pdfvec_m2=200.5)
    assert it.quantity == 75.0
    o = _o(it)
    assert _nao_afirma_medicao(o), it.observations
    assert _RESSALVA in o and "80.50" in o, it.observations
    assert _AFIRMACAO in o, it.observations
    assert "carimbo" in o, (
        "a prancha sem prova tem que dizer de onde veio a escala: %r" % it.observations)


def test_com_a_propria_prancha_PROVADA_diz_conferida_e_nao_nega():
    it = _porcelanato(qty=75.0, ref="%s (p2)" % _MULTI)
    _roda([it], pp=_pp_multipagina(True), pdfvec_m2=200.5)
    o = _o(it)
    assert "escala desta prancha 1:50 conferida por cota" in o, it.observations
    assert "declaração não é medida" not in o, (
        "prancha com escala PROVADA saiu com a ressalva de carimbo: %r" % it.observations)


# ── a consolidação não pode desmentir a frase na mesma célula ────────────
def _linha(desc, qty, prancha, conf):
    return BudgetItem(item_num="", description=desc, unit="m²", quantity=qty,
                      observations="", ref_sheet=prancha,
                      confidence=Confidence(conf), discipline="Pisos")


def test_consolidacao_fala_da_ORIGEM_e_nao_da_natureza_do_numero():
    """🚨 2ª revisão: "Cada linha é a medição da prancha dela" saía em linha
    LIDA. 🚨 3ª revisão: decidir pelo selo DAQUI também não serve — este passo
    roda antes do passo 7, que põe a NOSSA medição em linha que aqui estava
    zerada, e antes dos rebaixamentos. A frase fala só da origem."""
    grupo = [_linha(_DESC_CONSOL, 200.0, "planta cliente-nn.pdf", "estimado"),
             _linha(_DESC_CONSOL, 144.6, "detalhe cliente-nn.pdf", "estimado"),
             _linha(_DESC_CONSOL, 80.0, "layout cliente-nn.dxf", "confirmado")]
    out = main._consolidate_items(grupo)
    com_aviso = [x for x in out if "aparece em" in (x.observations or "")]
    assert len(com_aviso) == 3, [x.observations for x in out]
    for x in com_aviso:
        o = (x.observations or "").lower()
        assert "esta linha vem da prancha dela" in o, x.observations
        assert "medição da prancha" not in o and "o que foi lido" not in o, (
            "a consolidação afirmou a natureza do número antes de ela existir: %r"
            % x.observations)


_DESC_CONSOL = "Piso porcelanato 60x60 cm cor bege"


def test_a_linha_que_o_PASSO_7_preenche_nao_se_contradiz():
    """O caso da 3ª revisão, ponta a ponta: linha zerada que aparece em 2
    pranchas, consolidada, e depois preenchida pelo passo 7 com a área medida
    da prancha dela."""
    cad = "planta terreo cliente-nn.pdf"
    grupo = [_linha(_DESC_CONSOL, 0.0, cad, "estimado"),
             _linha(_DESC_CONSOL, 0.0, "planta superior cliente-nn.pdf", "estimado")]
    out = main._consolidate_items(grupo)
    alvo = [x for x in out if (x.ref_sheet or "") == cad][0]
    pp = {"t": _prancha(cad, 80.5, True)}
    main._apply_area_honesty([alvo], pdfvec_m2=80.5, pdfvec_por_prancha=pp)
    o = (alvo.observations or "").lower()
    assert "medidos nesta prancha" in o, alvo.observations      # o passo 7 agiu
    assert "o que foi lido" not in o, alvo.observations


# ── a limpeza da linha zerada tem que reconhecer a frase nova ────────────
def test_linha_ZERADA_nao_carrega_a_frase_nova():
    """🪤 `_limpa_afirmacao_de_medida` procurava só "medido da geometria do pdf".
    Com a frase nova, uma linha zerada ficaria com 0 m² e a nossa frase."""
    frase = main._frase_do_numero_que_cabe_na_geometria(None, list(PP_MISTO.values()))
    obs = _OBS_DA_IA + " | " + frase
    limpa = main._limpa_afirmacao_de_medida(obs).lower()
    assert "geometria do pdf" not in limpa and "atribuída pela ia" not in limpa, limpa
    assert "área estimada para consultórios" in limpa, (
        "a limpeza levou junto o texto da IA: %r" % limpa)


def test_CONTROLE_a_frase_ANTIGA_continua_saindo_da_linha_zerada():
    obs = (_OBS_DA_IA + " | Medido da GEOMETRIA do PDF, com escala lida do "
           "carimbo e NÃO confirmada por cota — confira a escala do seu PDF "
           "antes de orçar.")
    limpa = main._limpa_afirmacao_de_medida(obs).lower()
    assert "geometria do pdf" not in limpa, limpa


# ── forma da frase ────────────────────────────────────────────────────────
def test_a_ressalva_vem_COLADA_no_comeco():
    """A observação é cortada em 1.000 caracteres na gravação. Se a ressalva
    viesse no fim, o corte deixaria a afirmação sozinha."""
    f = main._frase_do_numero_que_cabe_na_geometria
    for frase in (f(None, list(PP_MISTO.values())),
                  f(None, list(PP_MISTO.values()), prancha_pelo_nome=PP_MISTO["b"]),
                  f(_prancha(_MULTI, 80.5, False, pagina=1), None)):
        assert frase.startswith(main._PREFIXO_CABE_NA_GEOMETRIA), frase
        assert frase.index(_RESSALVA) <= len(main._PREFIXO_CABE_NA_GEOMETRIA) + 4, frase
        assert frase.index("escala") < frase.index("Única checagem"), (
            "a ressalva da escala veio DEPOIS da afirmação: %r" % frase)


def test_texto_da_IA_com_geometria_do_PDF_NAO_engole_a_ressalva():
    """1ª revisão: o `if "geometria do pdf" not in _o` evitava a duplicata, mas
    também pulava a frase inteira quando a IA escrevia "geometria do PDF" no
    texto dela — e aí não entrava ressalva nenhuma."""
    it = _porcelanato(obs="Área medida da geometria do PDF: 200 m² (13 ambientes).")
    _roda([it])
    assert _RESSALVA in _o(it), it.observations


def test_rodar_duas_vezes_nao_escreve_a_frase_duas_vezes():
    it = _porcelanato(obs=_OBS_DA_IA + " " + _MEDIDO_DA_IA)
    _roda([it])
    _roda([it])
    assert _o(it).count(_RESSALVA) == 1, it.observations
    assert "área estimada para consultórios" in _o(it), it.observations


# ── bordas da busca estrita (3ª revisão: mutações que passariam verdes) ──
def test_linha_sem_pagina_e_registro_de_OUTRA_pagina_cai_no_generico():
    """Sem "(pN)" na linha e registro de página > 0: arquivo de várias
    páginas, não se sabe qual."""
    cad = "caderno cliente-nn.pdf"
    pp = {"x": _prancha(cad, 90.0, True, pagina=1)}
    it = _porcelanato(ref=cad, qty=60.0)
    _roda([it], pp=pp, pdfvec_m2=90.0)
    assert "prancha desta linha" not in _o(it), it.observations


def test_DOIS_registros_iguais_nao_escolhem_um():
    pp = {"a": _prancha(PLANTA, 656.3, True), "b": _prancha(PLANTA, 600.0, False)}
    it = _porcelanato(ref=PLANTA)
    _roda([it], pp=pp)
    assert "prancha desta linha" not in _o(it), it.observations


def test_ref_com_DOIS_arquivos_nao_escolhe_um():
    it = _porcelanato(ref="%s, %s" % (PLANTA, CORTE))
    _roda([it], pp=PP_REAL)
    assert "prancha desta linha" not in _o(it), it.observations


def test_borda_de_1_3x_da_propria_prancha():
    """1,29× a prancha do corte ainda cita a escala dela; 1,31× não."""
    dentro = _porcelanato(ref=CORTE, qty=round(1.29 * 100.4, 2))
    fora = _porcelanato(ref=CORTE, qty=round(1.31 * 100.4, 2))
    _roda([dentro, fora], pp=PP_REAL)
    assert "prancha desta linha" in _o(dentro), dentro.observations
    assert "prancha desta linha" not in _o(fora), fora.observations


def test_a_propria_prancha_achada_por_PREFIXO_nao_vira_desta_prancha():
    """🚨 3ª revisão: `_m_pr` casa por prefixo (serve à régua do número). A
    linha de `planta - cortes.pdf (p1 · corte AA)` levava a escala de
    `planta.pdf`. O número fica como estava; a frase não nomeia a prancha."""
    pp = {"a": _prancha("planta cliente-nn.pdf", 656.3, True, pagina=0)}
    it = _porcelanato(ref="planta cliente-nn - cortes.pdf (p1 · corte AA)", qty=120.0)
    _roda([it], pp=pp, pdfvec_m2=656.3)
    o = _o(it)
    assert it.quantity == 120.0, "o conserto é de TEXTO — o número mudou"
    assert "desta prancha" not in o and "prancha desta linha" not in o, it.observations
    assert _RESSALVA in o, it.observations


# ── os avisos vizinhos, que o mesmo cliente lê na mesma página ───────────
def test_aviso_so_PDF_nao_diz_que_a_escala_SEMPRE_vem_do_carimbo():
    """3ª revisão: "a escala vem do carimbo" como regra — mas ela vem também do
    rótulo da vista, do recorte do arquivo, ou nem existe."""
    class _It(object):
        def __init__(self, q):
            self.quantity = q
            self.confidence = "estimado"
    aviso = main.aviso_do_projeto_so_pdf([_It(10), _It(0)], False)
    assert "vem do carimbo" not in aviso, aviso
    assert "quase sempre" in aviso and "declaração" in aviso, aviso
    assert "nunca carimbamos um número de PDF como medido" in aviso, aviso

