# -*- coding: utf-8 -*-
"""Na planta de fôrma que numera os layers, a SEÇÃO escrita ao lado prova o pilar.

🩸 11/10/2026 — job f588da0e. Planta de fôrma de um subsolo, exportada de
software de estrutura: DXF R12, 200 layers com NÚMERO no nome, 56 pilares, cada
um com a seção ("45x100") e o nome ("P12C") escritos AO LADO. Saiu `pilares=0`,
20 linhas zeradas, e no topo: "este arquivo parece ser de ARQUITETURA" e "o
arquivo enviado não traz planta de fôrma" — pra quem enviou a planta de fôrma.

Eram duas travas em série no extrator, e o contador de descarte saía todo zerado:
  1. os 206 retângulos vinham FECHADOS PELO 1º PONTO REPETIDO, sem a marca de
     fechada — o laço só olhava polilinha com a marca;
  2. layer '3' não nomeia pilar — retângulo jogado fora antes de qualquer rótulo.
E o atalho de 05/08 ("layer numerado: o rótulo vira o filtro") nunca recebeu
retângulo de layer numerado numa extração de verdade: o teste dele entrega os
retângulos prontos, já no layer '4'.

📏 Anatomia medida no arquivo: os rótulos de seção casam com um retângulo do
MESMO tamanho a 0,42–2,73 lados maiores; o nome fica a até 9,5 lados; 59
retângulos do tamanho de pilar não têm rótulo (furos, escada). Contra-exemplos
medidos: dois FUROS de laje com o tamanho escrito ("100x15") e pilar por perto;
"19/60" (seção de VIGA) casando com um retângulo que não é pilar; e, no acervo,
14 vãos de esquadria desenhados no tamanho escrito, sem nome "P<n>".

🪤 Nomes de layer e rótulos FICTÍCIOS (repositório público, regra nº6).
"""
import io
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

import dwg_extractor as dx  # noqa: E402
import main  # noqa: E402
import structural_extractor as se  # noqa: E402
from structural_extractor import StructRect, count_pillars, pilares_provados_pela_secao  # noqa: E402

CM = 0.01            # o desenho está em centímetro


# ── o arquivo: pilares de layer numerado, fechados pelo 1º ponto repetido ─────
def _ret(msp, x, y, a, b, layer="3", marca=False, repete=True, lw=False):
    pts = [(x, y), (x + a, y), (x + a, y + b), (x, y + b)]
    if repete:
        pts.append((x, y))
    if lw:
        msp.add_lwpolyline(pts, close=marca, dxfattribs={"layer": layer})
    else:
        msp.add_polyline2d(pts, close=marca, dxfattribs={"layer": layer})


def _txt(msp, s, x, y, layer):
    msp.add_text(s, dxfattribs={"layer": layer, "height": 12, "insert": (x, y)})


def _pilar(msp, i, a, b, layer="3", secao=None, nome=True, **kw):
    """Pilar a×b (cm) na posição i, com a seção 1,3 lado acima do centro e o nome 1,4 lado à esquerda."""
    x, y = 1000.0 * i, 0.0
    _ret(msp, x, y, a, b, layer=layer, **kw)
    cx, cy, lado = x + a / 2, y + b / 2, max(a, b)
    if secao is not False:
        _txt(msp, secao or ("%gx%g" % (a, b)), cx, cy + 1.3 * lado, "12")
    if nome:
        _txt(msp, "P%dC" % (i + 1), cx - 1.4 * lado, cy, "9")
    return cx, cy


def _planta(tmp_path, monta, versao="R12", nome="forma.dxf"):
    doc = ezdxf.new(versao)
    if versao != "R12":
        doc.header["$INSUNITS"] = 5              # centímetros (o R12 não declara unidade)
    msp = doc.modelspace()
    monta(msp)
    p = str(tmp_path / nome)
    doc.saveas(p)
    ex = dx.extract_dxf(p, unit_factor_override=CM)
    assert float(ex.metadata.get("fator_para_metros")) == pytest.approx(CM), ex.metadata.get("fator_para_metros")
    return ex


_SECOES = [(45, 100), (45, 100), (50, 100), (100, 100), (25, 52.5)]


def _cinco(msp, **kw):
    for i, (a, b) in enumerate(_SECOES):
        _pilar(msp, i, a, b, **kw)


def test_o_caso_pilares_em_layer_numerado_fechados_pelo_ponto_repetido(tmp_path):
    ex = _planta(tmp_path, _cinco)
    assert ex.struct_rects == [], "layer '3' não nomeia pilar: nada entra pela porta do nome"
    assert len(ex.struct_rects_sem_nome) == 5
    pil = count_pillars(ex)
    assert pil and pil["total"] == 5, pil
    assert pil["por_rotulo"] is True and pil["por_secao_escrita"] is True
    por = {s["secao_cm"]: s for s in pil["por_secao"]}
    assert por["45x100 cm"]["qtd"] == 2 and por["45x100 cm"]["nomes"] == ["P1C", "P2C"]
    assert por["25x52 cm"]["qtd"] == 1 or por.get("25x53 cm", {}).get("qtd") == 1    # 52,5 arredonda
    txt = ex.to_structured_prompt()
    assert "SEÇÃO ESCRITA ao lado" in txt and "[MEDIDO] 5 pilares contados" in txt
    assert main._pilares_contados(ex) == 5


def test_o_caso_tambem_em_lwpolyline_sem_a_marca(tmp_path):
    ex = _planta(tmp_path, lambda m: _cinco(m, lw=True), versao="R2018")
    assert count_pillars(ex)["total"] == 5


def test_o_descarte_agora_conta_o_retangulo_de_layer_sem_nome(tmp_path):
    """Antes saía TODO zerado — nenhum retângulo chegava ao contador."""
    ex = _planta(tmp_path, _cinco)
    assert ex.pilares_descartados["nome_do_layer"] == 5
    assert dict(ex.pilares_descartados["amostra_layers"]) == {"3": 5}


# ── o layer que NOMEIA pilar: muda só o fechamento ────────────────────────────
@pytest.mark.parametrize("lw, versao", [(False, "R12"), (True, "R2018")])
def test_layer_de_pilar_fechado_pelo_ponto_repetido_passa_a_contar(tmp_path, lw, versao):
    ex = _planta(tmp_path, lambda m: [_ret(m, 1000 * i, 0, 20, 40, layer="EST-PILAR", lw=lw) for i in range(4)],
                 versao=versao)
    assert len(ex.struct_rects) == 4
    pil = count_pillars(ex)
    assert pil["total"] == 4 and pil["por_rotulo"] is False and pil["por_secao_escrita"] is False


def test_CONTROLE_layer_de_pilar_com_a_marca_segue_como_era(tmp_path):
    ex = _planta(tmp_path, lambda m: [_ret(m, 1000 * i, 0, 20, 40, layer="EST-PILAR", marca=True, repete=False)
                                      for i in range(4)])
    assert len(ex.struct_rects) == 4 and ex.struct_rects_sem_nome == []


def test_CONTROLE_polilinha_aberta_nao_e_contorno(tmp_path):
    """Quatro pontos sem marca e sem repetir o 1º: é um 'U', não um pilar."""
    def monta(m):
        for i in range(4):
            _ret(m, 1000 * i, 0, 20, 40, layer="EST-PILAR", repete=False)
            _ret(m, 1000 * i, 500, 45, 100, layer="3", repete=False)
            _txt(m, "45x100", 1000 * i + 22, 500 + 180, "12")
            _txt(m, "P%dC" % i, 1000 * i - 120, 550, "9")
    ex = _planta(tmp_path, monta)
    assert ex.struct_rects == [] and ex.struct_rects_sem_nome == []
    assert count_pillars(ex) is None


def test_CONTROLE_com_layer_de_pilar_a_secao_escrita_nao_opina(tmp_path):
    """Quando o desenho nomeia o layer, quem manda é o nome — como sempre."""
    def monta(m):
        for i in range(3):
            _ret(m, 1000 * i, 3000, 20, 40, layer="EST-PILAR", marca=True, repete=False)
        _cinco(m)
    ex = _planta(tmp_path, monta)
    pil = count_pillars(ex)
    assert pil["total"] == 3 and pil["por_secao_escrita"] is False


# ── o que NÃO é pilar ─────────────────────────────────────────────────────────
def test_CONTROLE_furo_com_o_tamanho_escrito_nao_tem_nome_proprio(tmp_path):
    """O furo de laje "100x15" ao lado de um pilar: o nome mais perto é do PILAR."""
    def monta(m):
        _cinco(m)
        _ret(m, 300, 0, 15, 100, layer="241")                 # o furo, a 3 m do 1º pilar
        _txt(m, "100x15", 307, 50 + 42, "83")
    ex = _planta(tmp_path, monta)
    pil = count_pillars(ex)
    assert pil["total"] == 5 and pil["layers"] == ["3"], pil


def test_CONTROLE_secao_que_nao_bate_com_o_desenho_nao_prova(tmp_path):
    ex = _planta(tmp_path, lambda m: [_pilar(m, i, 45, 100, secao="40x60") for i in range(5)])
    assert count_pillars(ex) is None


def test_CONTROLE_secao_com_barra_e_de_viga(tmp_path):
    ex = _planta(tmp_path, lambda m: [_pilar(m, i, 19, 60, secao="19/60") for i in range(5)])
    assert count_pillars(ex) is None


def test_CONTROLE_vao_de_esquadria_sem_nome_de_pilar(tmp_path):
    """A prancha de detalhe de esquadrias: vãos desenhados no tamanho escrito, sem "P<n>"."""
    ex = _planta(tmp_path, lambda m: [_pilar(m, i, 60, 150, nome=False) for i in range(6)])
    assert len(ex.struct_rects_sem_nome) == 6
    assert count_pillars(ex) is None


def test_CONTROLE_porta_em_vista_com_nome_e_tamanho_nao_e_pilar(tmp_path):
    """A prancha de esquadrias: a porta desenhada em vista (80 × 210), "80x210" e "P1"
    ao lado. É o mesmo desenho de um pilar com nome e seção — o que separa é a altura."""
    def monta(m):
        for i in range(6):
            _ret(m, 1000 * i, 0, 80, 210, layer="7")
            _txt(m, "80x210", 1000 * i + 40, 105 + 1.3 * 210, "8")
            _txt(m, "P%d" % (i + 1), 1000 * i + 40 - 1.4 * 210, 105, "8")
    ex = _planta(tmp_path, monta)
    assert len(ex.struct_rects_sem_nome) == 6
    assert count_pillars(ex) is None


@pytest.mark.parametrize("b, casa", [(130.0, True), (199.0, True), (200.0, False), (210.0, False)])
def test_secao_com_lado_de_2_metros_ou_mais_nao_entra_pela_prova(b, casa):
    rects = [StructRect(layer="3", w_m=0.45, h_m=b * CM, w_raw=45.0, h_raw=b, cx=5000.0 * i, cy=0.0) for i in range(4)]
    texts = []
    for i in range(4):
        texts.append(T("45x%g" % b, 5000.0 * i, 1.3 * b))
        texts.append(T("P%dC" % (i + 1), 5000.0 * i - 1.4 * b, 0.0))
    assert bool(pilares_provados_pela_secao(rects, texts)) is casa


def test_CONTROLE_etiqueta_com_P1_dentro_do_quadrinho_nao_vira_pilar(tmp_path):
    """Etiqueta de porta: um quadrinho com "P1" DENTRO, em layer sem nome. O atalho de
    05/08 (rótulo dentro do retângulo) continua sem ver os retângulos de layer sem nome."""
    def monta(m):
        for i in range(6):
            _ret(m, 1000 * i, 0, 30, 20, layer="7")
            _txt(m, "P%d" % (i + 1), 1000 * i + 12, 8, "7")
    ex = _planta(tmp_path, monta)
    assert len(ex.struct_rects_sem_nome) == 6
    assert count_pillars(ex) is None


def test_CONTROLE_dois_provados_e_acaso(tmp_path):
    ex = _planta(tmp_path, lambda m: [_pilar(m, i, 45, 100) for i in range(2)])
    assert count_pillars(ex) is None
    ex3 = _planta(tmp_path, lambda m: [_pilar(m, i, 45, 100) for i in range(3)], nome="tres.dxf")
    assert count_pillars(ex3)["total"] == 3


def test_CONTROLE_retangulo_fora_do_tamanho_de_pilar_nao_e_candidato(tmp_path):
    def monta(m):
        _cinco(m)
        _ret(m, 0, 5000, 300, 400, layer="3")                 # 3 × 4 m: laje, não pilar
        _ret(m, 1000, 5000, 5, 5, layer="3")                  # 5 cm: símbolo
    ex = _planta(tmp_path, monta)
    assert len(ex.struct_rects_sem_nome) == 5


# ── a prova, peça por peça ────────────────────────────────────────────────────
class T:
    def __init__(self, text, x, y):
        self.text, self.position = text, (x, y)


def _r(i, a=45.0, b=100.0, layer="3"):
    return StructRect(layer=layer, w_m=a * CM, h_m=b * CM, w_raw=a, h_raw=b, cx=1000.0 * i, cy=0.0)


def _provas(n, a=45.0, b=100.0, dsec=1.3, dnome=1.4, secao=None):
    rects = [_r(i, a, b) for i in range(n)]
    texts = []
    for i in range(n):
        texts.append(T(secao or "45x100", 1000.0 * i, dsec * max(a, b)))
        texts.append(T("P%dC" % (i + 1), 1000.0 * i - dnome * max(a, b), 0.0))
    return rects, texts


def test_a_prova_devolve_os_retangulos():
    rects, texts = _provas(4)
    assert pilares_provados_pela_secao(rects, texts) == rects


@pytest.mark.parametrize("a, b, casa", [
    (45.0, 100.0, True),
    (46.3, 100.0, True),        # 2,9 % no lado menor
    (45.0, 102.9, True),        # 2,9 % no lado maior
    (46.7, 100.0, False),       # 3,8 %
    (45.0, 104.0, False),       # 4 %
])
def test_o_lado_bate_com_o_numero_escrito_em_3_por_cento(a, b, casa):
    rects, texts = _provas(4, a, b)
    assert bool(pilares_provados_pela_secao(rects, texts)) is casa


@pytest.mark.parametrize("dsec, casa", [(0.4, True), (2.7, True), (3.9, True), (4.2, False)])
def test_a_secao_fica_a_ate_4_lados(dsec, casa):
    rects, texts = _provas(4, dsec=dsec)
    assert bool(pilares_provados_pela_secao(rects, texts)) is casa


@pytest.mark.parametrize("dnome, casa", [(0.8, True), (9.5, True), (11.9, True), (12.5, False)])
def test_o_nome_fica_a_ate_12_lados(dnome, casa):
    rects, texts = _provas(4, dnome=dnome)
    # 🪤 pilares a 5.000 um do outro: o nome a 12,5 lados (1.250) não pode cair no vizinho
    for i, r in enumerate(rects):
        r.cx = 5000.0 * i
    texts = []
    for i in range(4):
        texts.append(T("45x100", 5000.0 * i, 130.0))
        texts.append(T("P%dC" % (i + 1), 5000.0 * i - dnome * 100.0, 0.0))
    assert bool(pilares_provados_pela_secao(rects, texts)) is casa


def test_um_rotulo_prova_um_retangulo_so():
    """Dois retângulos iguais e UMA seção escrita: prova o mais perto."""
    rects = [_r(0), _r(1), _r(2), _r(3)]
    gemeo = StructRect(layer="3", w_m=0.45, h_m=1.0, w_raw=45.0, h_raw=100.0, cx=150.0, cy=0.0)
    _rs, texts = _provas(4)
    assert pilares_provados_pela_secao(rects + [gemeo], texts) == rects


def test_o_gemeo_com_nome_mas_sem_secao_propria_nao_e_provado():
    """A seção escrita é de UM retângulo. O gêmeo ao lado, mesmo com nome próprio,
    não herda a prova do vizinho: sem a seção dele, não se sabe o que ele é."""
    rects, texts = _provas(4)
    gemeo = StructRect(layer="3", w_m=0.45, h_m=1.0, w_raw=45.0, h_raw=100.0, cx=300.0, cy=0.0)
    texts.append(T("P9C", 300.0 + 140.0, 0.0))                # nome DELE, à direita
    assert pilares_provados_pela_secao(rects + [gemeo], texts) == rects


def test_a_secao_mais_perto_do_vizinho_ainda_prova_o_seu_retangulo():
    """Dois pilares iguais lado a lado, a seção do 2º escrita ENTRE os dois e mais perto
    do 1º: o 1º já tem a dele, então ela prova o 2º — não se perde no vizinho."""
    rects, texts = _provas(4)
    vizinho = StructRect(layer="3", w_m=0.45, h_m=1.0, w_raw=45.0, h_raw=100.0, cx=300.0, cy=0.0)
    texts.append(T("45x100", 140.0, 130.0))                   # a 191 do 1º e a 206 do 2º
    texts.append(T("P9C", 300.0 + 140.0, 0.0))
    provados = pilares_provados_pela_secao(rects + [vizinho], texts)
    assert sorted(map(id, provados)) == sorted(map(id, rects + [vizinho]))


def test_o_nome_e_de_um_retangulo_so():
    """O retângulo casado que NENHUM nome escolhe como o mais perto fica de fora."""
    rects, texts = _provas(4)
    furo = StructRect(layer="241", w_m=0.15, h_m=1.0, w_raw=15.0, h_raw=100.0, cx=300.0, cy=0.0)
    texts.append(T("100x15", 300.0, 40.0))
    assert pilares_provados_pela_secao(rects + [furo], texts) == rects


def test_CONTROLE_circulo_nao_tem_secao_AxB():
    rects, texts = _provas(4)
    for r in rects:
        r.circular = True
    assert pilares_provados_pela_secao(rects, texts) == []


@pytest.mark.parametrize("rects, texts", [([], []), (None, None), ([_r(0)], [T("45x100", 0, 130)])])
def test_CONTROLE_sem_o_que_provar_devolve_vazio(rects, texts):
    assert pilares_provados_pela_secao(rects, texts) == []


@pytest.mark.parametrize("s, casa", [
    ("45x100", True), ("45 x 100", True), ("45X100", True), ("25x52.5", True), ("25x52,5", True),
    ("45x100cm", True), ("45x100 cm", True),
    ("19/60", False), ("P12 45x100", False), ("0.80x2.10", False), ("4x8", False), ("1000x2000", False),
    ("45x100x3", False), ("h=23", False), ("", False),
])
def test_o_que_e_rotulo_de_secao(s, casa):
    assert bool(se._SECAO_ROTULO_RE.match(s)) is casa


@pytest.mark.parametrize("s, casa", [
    ("P1", True), ("P12C", True), ("P341C", True), ("P 12", True),
    ("p12", False), ("PILAR", False), ("P12CD", False), ("P12 45x100", False), ("V301", False), ("P12345", False),
])
def test_o_que_e_nome_de_pilar(s, casa):
    assert bool(se._PNAME_SUFIXO_RE.match(s)) is casa


# ── o aviso do topo deixa de acusar o arquivo certo ──────────────────────────
@pytest.mark.parametrize("arqs, e", [
    ([{"nome": "A", "pilares_contados": 54}], True),
    ([{"nome": "A", "pilares_contados": 0}, {"nome": "B", "pilares_contados": 3}], True),
    ([{"nome": "A", "pilares_contados": 2}], False),
    ([{"nome": "A"}], False),
    ([{"nome": "A", "pilares_contados": "x"}], False),
    ([None, "texto"], False),
    ([], False),
    (None, False),
])
def test_pilar_contado_na_geometria_prova_que_o_arquivo_e_de_estrutura(arqs, e):
    assert main._arquivo_de_estrutura_pelos_pilares(arqs) is e


def test_a_contagem_que_falha_vale_zero():
    """Quem lê a contagem só deixa de acusar o arquivo — um erro nela não pode derrubar o job."""
    class Quebrada:
        @property
        def struct_rects(self):
            raise RuntimeError("extração pela metade")
    assert main._pilares_contados(Quebrada()) == 0
    assert main._pilares_contados(object()) == 0
    assert main._pilares_contados(None) == 0


def _fonte():
    return io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def _condicao_do_if_que_atribui(fonte, alvo, valor_contem):
    """O texto da condição do `if` que guarda a atribuição `alvo = ...<valor_contem>...`."""
    import ast
    arv = ast.parse(fonte)
    for no in ast.walk(arv):
        if not isinstance(no, ast.If):
            continue
        for st in no.body:
            if (isinstance(st, ast.Assign) and any(getattr(t, "id", "") == alvo for t in st.targets)
                    and valor_contem in ast.dump(st.value)):
                return ast.unparse(no.test)
    return None


def test_o_parece_arquitetura_cala_quando_ha_pilares_contados():
    cond = _condicao_do_if_que_atribui(_fonte(), "_warn_tipo", "parece ser de ARQUITETURA")
    assert cond and "not _estrut_pelos_pilares" in cond and "_is_likely_wrong_type" in cond, cond


def test_o_nao_traz_planta_de_forma_cala_quando_ha_pilares_contados():
    """O ramo que NÃO acusa o arquivo é o `if`; o que acusa é o `else` dele."""
    cond = _condicao_do_if_que_atribui(_fonte(), "_aviso_estrut", "o desenho foi lido")
    assert cond and "_pilares_na_geometria" in cond and "_n_aco_resumo" in cond, cond


def test_CONTROLE_o_guarda_da_condicao_reprova():
    fonte = ("if a and not b:\n    _warn_tipo = 'parece ser de ARQUITETURA'\n"
             "if c:\n    _aviso_estrut = 'o desenho foi lido'\nelse:\n    _aviso_estrut = 'não traz'\n")
    assert _condicao_do_if_que_atribui(fonte, "_warn_tipo", "parece ser de ARQUITETURA") == "a and (not b)"
    assert _condicao_do_if_que_atribui(fonte, "_aviso_estrut", "o desenho foi lido") == "c"
    assert _condicao_do_if_que_atribui(fonte, "_aviso_estrut", "outra frase") is None


def test_o_processamento_guarda_a_contagem_por_arquivo():
    fonte = _fonte()
    fio = '_res_esc["pilares_contados"] = _pilares_contados(extraction)'
    assert fio in fonte
    assert "_arquivo_de_estrutura_pelos_pilares(_escala_arqs)" in fonte
    assert fio not in fonte.replace(fio, "pass")
