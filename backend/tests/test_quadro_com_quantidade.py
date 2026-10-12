# -*- coding: utf-8 -*-
"""QUADRO COM QUANTIDADE — as linhas do quadro que o projetista desenhou, lidas
pela GRADE do próprio quadro.

📏 11/10/2026 — estudo do acervo (342 DXF). O projetista escreve a quantidade num
quadro (esquadrias, luminárias, lista de material); o motor entregava cada célula
como texto solto e a quantidade não chegava à planilha — em 4 de 5 jobs conferidos
no banco o quadro de esquadrias sumiu e a contagem de bloco ficou no lugar.

O leitor: a horizontal embaixo do cabeçalho "QTD" dá a largura do quadro, as
verticais que descem dela dão as colunas, e o texto entra na coluna em que o ponto
dele cai. O texto só refina DENTRO de uma célula da grade, e só sem dúvida.
Medido: 39 quadros em 23 arquivos de 17 jobs, 627 linhas com quantidade.

Todo caso passa pelo `extract_dxf` (um DXF sintético de verdade).
🪤 Nomes e layers FICTÍCIOS (repositório público, regra nº6).
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402
import engine_rules as er  # noqa: E402

CAB = ["COD", "TIPO", "QTD", "MATERIAL"]
LARG = [8, 20, 8, 20]
LINHAS = [["J1", "Janela basculante", "2", "Vidro"],
          ["J2", "Janela de correr", "5", "Alumínio"],
          ["P1", "Porta de abrir", "12", "Madeira"]]


class Desenho:
    """O desenho sintético: textos e trechos retos, que viram um DXF."""

    def __init__(self):
        self.textos, self.hs, self.vs, self.etiquetas = [], [], [], []

    def t(self, x, y, s, h=1.0, giro=0.0, centrado_na_caixa=0.0):
        """Um texto. `centrado_na_caixa` = W faz dele um MTEXT de caixa W presa pela esquerda com o
        parágrafo CENTRADO: o que se vê fica W/2 à direita do ponto de inserção."""
        self.textos.append({"x": float(x), "y": float(y), "s": s, "h": h, "giro": giro, "w": centrado_na_caixa})
        return self

    def tag(self, x, y, s, h=1.0):
        """A etiqueta solta (ATTDEF fora de bloco): o CAD desenha o TAG."""
        self.etiquetas.append((float(x), float(y), s, h))
        return self

    def h(self, y, xa, xb):
        self.hs.append((float(y), float(min(xa, xb)), float(max(xa, xb))))
        return self

    def v(self, x, ya, yb):
        self.vs.append((float(x), float(min(ya, yb)), float(max(ya, yb))))
        return self

    def grava(self, tmp_path, traco="line", mtext=False):
        doc = ezdxf.new("R2018")
        doc.header["$INSUNITS"] = 6
        msp = doc.modelspace()
        for t in self.textos:
            if t["w"]:
                msp.add_mtext("\\pxqc;" + t["s"], dxfattribs={
                    "char_height": t["h"], "layer": "ARQ-TEXTO", "insert": (t["x"], t["y"]),
                    "attachment_point": 7, "width": t["w"]})
            elif mtext:
                msp.add_mtext(t["s"], dxfattribs={"char_height": t["h"], "layer": "ARQ-TEXTO",
                                                  "insert": (t["x"], t["y"]), "attachment_point": 7})
            else:
                msp.add_text(t["s"], dxfattribs={"height": t["h"], "layer": "ARQ-TEXTO",
                                                 "insert": (t["x"], t["y"]), "rotation": t["giro"]})
        for x, y, s, h in self.etiquetas:
            msp.add_attdef(s, (x, y), dxfattribs={"height": h, "layer": "ARQ-SIMB"})
        for p0, p1 in [((a, y), (b, y)) for y, a, b in self.hs] + [((x, a), (x, b)) for x, a, b in self.vs]:
            if traco == "line":
                msp.add_line(p0, p1, dxfattribs={"layer": "ARQ-QUADRO"})
            elif traco == "lwpolyline":
                msp.add_lwpolyline([p0, p1], dxfattribs={"layer": "ARQ-QUADRO"})
            else:
                msp.add_polyline2d([p0, p1], dxfattribs={"layer": "ARQ-QUADRO"})
        p = str(tmp_path / "quadro.dxf")
        doc.saveas(p)
        return p


def tabela(d, x0, topo, larg, cab, linhas, alt=3.0, alt_cab=None, verticais="todas", horizontais=True,
           v_no_cab=True, cab_dx=None, regua_ate=None):
    """Desenha um quadro em `d`: `larg` = largura de cada coluna; `cab` = o cabeçalho (None = sem
    texto); `linhas` = lista de linhas (cada uma uma lista de células, None = vazia). A linha de base
    do cabeçalho fica 1 acima da régua de baixo dele; a de cada célula, 1 acima da horizontal de baixo
    da linha.
    verticais: "todas" | "moldura" | conjunto de índices de borda (0 = a da esquerda).
    horizontais=False tira as horizontais ENTRE as linhas (ficam a régua do cabeçalho e a base).
    v_no_cab=False faz as verticais pararem na régua do cabeçalho (não sobem até o topo).
    regua_ate: x onde a régua de baixo do cabeçalho acaba (padrão: a borda da direita).
    Devolve (xs das bordas, y da régua do cabeçalho, y da base do quadro)."""
    alt_cab = alt if alt_cab is None else alt_cab
    xs = [float(x0)]
    for w in larg:
        xs.append(xs[-1] + w)
    yb = topo - alt_cab
    base = yb - alt * len(linhas)
    d.h(topo, xs[0], xs[-1])
    d.h(yb, xs[0], xs[-1] if regua_ate is None else regua_ate)
    for k in range(len(linhas)):
        if horizontais or k == len(linhas) - 1:
            d.h(yb - alt * (k + 1), xs[0], xs[-1])
    for i, x in enumerate(xs):
        if verticais == "todas" or (verticais == "moldura" and i in (0, len(xs) - 1)) \
                or (not isinstance(verticais, str) and i in verticais):
            d.v(x, base, topo if v_no_cab else yb)
    for i, c in enumerate(cab):
        if c:
            d.t(xs[i] + (cab_dx[i] if cab_dx else 0.5), yb + 1.0, c)
    for k, ln in enumerate(linhas):
        for i, c in enumerate(ln):
            if c:
                d.t(xs[i] + 0.5, yb - alt * (k + 1) + 1.0, c)
    return xs, yb, base


def registro(tmp_path, d, **kw):
    return (dx.extract_dxf(d.grava(tmp_path, **kw)).metadata or {}).get("quadros_com_quantidade") or {}


def lidos(tmp_path, d, **kw):
    return registro(tmp_path, d, **kw).get("quadros") or []


def como_dict(q):
    """[{coluna: célula}] das linhas com quantidade, com a quantidade na chave '#'."""
    out = []
    for l in q["linhas"]:
        if l["q"] is None:
            continue
        r = {"#": l["q"]}
        for i, c in enumerate(l["cel"]):
            if c and i != q["iq"]:
                r[q["colunas"][i]] = c
        out.append(r)
    return out


@pytest.fixture(autouse=True)
def _chaves(monkeypatch):
    monkeypatch.delenv("QUADRO_COM_QUANTIDADE", raising=False)
    monkeypatch.delenv("ATTDEF_SOLTO_E_TEXTO", raising=False)


# ── o quadro simples ─────────────────────────────────────────────────────────────────────────
def test_quadro_simples_le_linhas_e_colunas(tmp_path):
    d = Desenho()
    tabela(d, 0, 100, LARG, CAB, LINHAS)
    (q,) = lidos(tmp_path, d)
    assert q["colunas"] == CAB and q["colunas"][q["iq"]] == "QTD"
    assert como_dict(q) == [
        {"#": "2", "COD": "J1", "TIPO": "Janela basculante", "MATERIAL": "Vidro"},
        {"#": "5", "COD": "J2", "TIPO": "Janela de correr", "MATERIAL": "Alumínio"},
        {"#": "12", "COD": "P1", "TIPO": "Porta de abrir", "MATERIAL": "Madeira"}]
    assert q["faltam"] == [] and q["copia_de"] is None


@pytest.mark.parametrize("traco", ["line", "lwpolyline", "polyline"])
def test_a_grade_em_linha_ou_em_polilinha(tmp_path, traco):
    d = Desenho()
    tabela(d, 0, 100, LARG, CAB, LINHAS)
    (q,) = lidos(tmp_path, d, traco=traco)
    assert [r["#"] for r in como_dict(q)] == ["2", "5", "12"]


def test_as_celulas_em_mtext(tmp_path):
    d = Desenho()
    tabela(d, 0, 100, LARG, CAB, LINHAS)
    (q,) = lidos(tmp_path, d, mtext=True)
    assert como_dict(q)[2] == {"#": "12", "COD": "P1", "TIPO": "Porta de abrir", "MATERIAL": "Madeira"}


def test_sem_a_regua_embaixo_do_cabecalho_nao_e_quadro(tmp_path):
    d = Desenho()
    tabela(d, 0, 100, LARG, CAB, LINHAS)
    d.hs, d.vs = [], []
    assert registro(tmp_path, d) == {}


def test_os_nomes_do_cabecalho_de_quantidade(tmp_path):
    for k, nome in enumerate(("QUANT.", "Qtde", "QUANTIDADE", "QTD.", "Quant", "QTD (un)")):
        d = Desenho()
        tabela(d, 0, 100, LARG, ["COD", "TIPO", nome, "MATERIAL"], LINHAS)
        sub = tmp_path / ("sim%d" % k)
        sub.mkdir()
        assert len(lidos(sub, d)) == 1, nome
    for k, nome in enumerate(("QUANTITATIVO", "QUANTIDADE DE PEÇAS", "QTD DE FOLHAS")):
        d = Desenho()
        tabela(d, 0, 100, LARG, ["COD", "TIPO", nome, "MATERIAL"], LINHAS)
        sub = tmp_path / ("nao%d" % k)
        sub.mkdir()
        assert registro(sub, d) == {}, nome


def test_uma_linha_so_e_quadro(tmp_path):
    d = Desenho()
    tabela(d, 0, 100, LARG, CAB, LINHAS[:1])
    (q,) = lidos(tmp_path, d)
    assert como_dict(q) == [{"#": "2", "COD": "J1", "TIPO": "Janela basculante", "MATERIAL": "Vidro"}]


def test_descricao_e_quantidade_sao_quadro(tmp_path):
    d = Desenho()
    tabela(d, 0, 100, [40, 12], ["DESCRIÇÃO", "QUANTIDADE"], [["TELHA METÁLICA", "1.234,56 m²"], ["CUMEEIRA", "98,70 ml"]])
    (q,) = lidos(tmp_path, d)
    assert como_dict(q) == [{"#": "1.234,56 m²", "DESCRIÇÃO": "TELHA METÁLICA"},
                            {"#": "98,70 ml", "DESCRIÇÃO": "CUMEEIRA"}]


# ── a coluna é a da GRADE, não a do cabeçalho mais perto ─────────────────────────────────────
def test_cabecalho_centrado_e_celula_a_esquerda_ficam_na_coluna_da_grade(tmp_path):
    # a descrição começa a 6 do "SIMB." e a 17,5 do "DESCRIÇÃO": por proximidade sairia como símbolo
    d = Desenho()
    tabela(d, 0, 100, [6, 6, 40], ["QTD", "SIMB.", "DESCRIÇÃO"],
           [["41", None, "SPOT DE EMBUTIR SIMPLES"], ["04", None, "SPOT DE EMBUTIR DUPLO"]], cab_dx=[0.5, 0.5, 18])
    (q,) = lidos(tmp_path, d)
    assert como_dict(q) == [{"#": "41", "DESCRIÇÃO": "SPOT DE EMBUTIR SIMPLES"},
                            {"#": "04", "DESCRIÇÃO": "SPOT DE EMBUTIR DUPLO"}]
    assert q["faltam"] == ["SIMB."]


def test_sem_verticais_a_mesma_duvida_cala_o_quadro(tmp_path):
    d = Desenho()
    tabela(d, 0, 100, [6, 6, 40], ["QTD", "SIMB.", "DESCRIÇÃO"],
           [["41", None, "SPOT DE EMBUTIR SIMPLES"], ["04", None, "SPOT DE EMBUTIR DUPLO"]], cab_dx=[0.5, 0.5, 18],
           verticais="moldura")
    reg = registro(tmp_path, d)
    assert reg["quadros"] == []
    assert [n["motivo"] for n in reg["nao_lidos"]] == ["a coluna da quantidade não se separa das vizinhas"]


def test_coluna_sem_texto_e_declarada(tmp_path):
    d = Desenho()
    tabela(d, 0, 100, [10, 12, 30], ["FOTO", "QUANTIDADE", "DESCRIÇÃO"],
           [[None, "11 unid.", "BALIZADOR"], [None, "03 unid.", "EMBUTIDO"]])
    (q,) = lidos(tmp_path, d)
    assert q["faltam"] == ["FOTO"]
    assert como_dict(q) == [{"#": "11 unid.", "DESCRIÇÃO": "BALIZADOR"}, {"#": "03 unid.", "DESCRIÇÃO": "EMBUTIDO"}]


def test_CONTROLE_coluna_com_texto_numa_linha_nao_falta(tmp_path):
    d = Desenho()
    tabela(d, 0, 100, [10, 12, 30], ["FOTO", "QUANTIDADE", "DESCRIÇÃO"],
           [[None, "11 unid.", "BALIZADOR"], ["12V", "03 unid.", "EMBUTIDO"]])
    (q,) = lidos(tmp_path, d)
    assert q["faltam"] == []


def test_coluna_sem_titulo_e_sem_celula_sai_do_quadro(tmp_path):
    # a 1ª coluna é a do símbolo: sem cabeçalho e sem texto em linha nenhuma
    d = Desenho()
    tabela(d, 0, 100, [6, 8, 30], [None, "QTD", "ESPECIFICAÇÃO"],
           [[None, "41", "LUMINÁRIA SPOT"], [None, "09", "LUMINÁRIA DE EMBUTIR"]])
    (q,) = lidos(tmp_path, d)
    assert q["colunas"] == ["QTD", "ESPECIFICAÇÃO"] and q["iq"] == 0 and q["faltam"] == []
    assert [l["cel"] for l in q["linhas"]] == [["41", "LUMINÁRIA SPOT"], ["09", "LUMINÁRIA DE EMBUTIR"]]


def test_CONTROLE_coluna_sem_titulo_mas_com_celula_fica(tmp_path):
    d = Desenho()
    tabela(d, 0, 100, [6, 8, 30], [None, "QTD", "ESPECIFICAÇÃO"],
           [["12V", "41", "LUMINÁRIA SPOT"], [None, "09", "LUMINÁRIA DE EMBUTIR"]])
    (q,) = lidos(tmp_path, d)
    assert q["colunas"] == ["", "QTD", "ESPECIFICAÇÃO"] and q["iq"] == 1
    assert q["linhas"][0]["cel"] == ["12V", "41", "LUMINÁRIA SPOT"]


def test_a_etiqueta_solta_e_celula_do_quadro(tmp_path):
    # a coluna "Ref." do quadro de esquadrias é ATTDEF fora de bloco: sem ele a coluna falta
    d = Desenho()
    xs, yb, _b = tabela(d, 0, 100, [8, 10, 20], ["Ref.", "Quantidade", "Tipo"],
                        [[None, "12", "de abrir"], [None, "03", "de correr"]])
    d.tag(xs[0] + 0.5, yb - 3 + 1.0, "PA6").tag(xs[0] + 0.5, yb - 6 + 1.0, "PA7")
    (q,) = lidos(tmp_path, d)
    assert q["faltam"] == []
    assert como_dict(q) == [{"#": "12", "Ref.": "PA6", "Tipo": "de abrir"}, {"#": "03", "Ref.": "PA7", "Tipo": "de correr"}]


# 🩸 12/10/2026 — a 1ª planilha com a etiqueta solta: a IA leu a ressalva do ×N e
# pôs o ×N cru como quantidade (13 onde o quadro diz 12). 📏 No único arquivo do
# acervo em que a etiqueta é célula de quadro lido, o ×N é o quadro + 2 em 29 de
# 29 códigos (a planta, a célula do quadro, o título do detalhe). A seção não casa
# código nenhum: diz quem manda.
_O_QUADRO_MANDA = ("⚠ Este arquivo tem QUADRO COM QUANTIDADE (acima): a etiqueta cujo código é linha de um quadro "
                   "leva a quantidade do QUADRO — o ×N conta também a célula do quadro e o título do detalhe. "
                   "Cite o ×N na observação.")


def _quadro_com_etiquetas():
    d = Desenho()
    xs, yb, _b = tabela(d, 0, 100, [8, 10, 20], ["Ref.", "Quantidade", "Tipo"],
                        [[None, "12", "de abrir"], [None, "03", "de correr"]])
    d.tag(xs[0] + 0.5, yb - 3 + 1.0, "PA6").tag(xs[0] + 0.5, yb - 6 + 1.0, "PA7")
    for k in range(3):                                  # as mesmas etiquetas na "planta", longe do quadro
        d.tag(200 + 5 * k, 20, "PA6")
    return d


def test_com_quadro_lido_o_bloco_de_etiquetas_diz_que_o_quadro_manda(tmp_path):
    linhas = dx.extract_dxf(_quadro_com_etiquetas().grava(tmp_path)).to_structured_prompt().splitlines()
    i = next(k for k, l in enumerate(linhas) if l.startswith("  ETIQUETAS SOLTAS NO DESENHO"))
    assert " ".join(l.strip() for l in linhas[i + 4:i + 7]) == _O_QUADRO_MANDA
    assert linhas[i + 7].startswith("  [") and "PA6 ×4" in linhas[i + 7], linhas[i:i + 9]   # a lista vem DEPOIS da frase
    # "(acima)" é verdade: a seção dos quadros vem antes do bloco das etiquetas
    assert next(k for k, l in enumerate(linhas) if l.startswith("QUADROS COM QUANTIDADE")) < i
    # diz o que FAZER e não lista número: nenhuma quantidade do quadro na frase
    assert "12" not in _O_QUADRO_MANDA and "PA6" not in _O_QUADRO_MANDA


def test_CONTROLE_sem_quadro_lido_o_bloco_fica_como_estava(tmp_path, monkeypatch):
    d = Desenho()
    for k in range(3):
        d.tag(200 + 5 * k, 20, "PA6")
    d.t(0, 0, "SALA")
    p = dx.extract_dxf(d.grava(tmp_path)).to_structured_prompt()
    assert "ETIQUETAS SOLTAS NO DESENHO" in p and "PA6 ×3" in p
    assert "QUADRO COM QUANTIDADE (acima)" not in p
    # e com o quadro no desenho mas a chave do leitor desligada: sem registro, sem frase
    monkeypatch.setenv("QUADRO_COM_QUANTIDADE", "0")
    p2 = dx.extract_dxf(_quadro_com_etiquetas().grava(tmp_path)).to_structured_prompt()
    assert "ETIQUETAS SOLTAS NO DESENHO" in p2 and "QUADRO COM QUANTIDADE (acima)" not in p2


def test_CONTROLE_quadro_visto_e_nao_lido_nao_e_quadro_acima(tmp_path):
    """O registro existe (o quadro foi visto e recusado), mas a seção dos quadros
    não sai — "acima" não haveria nada: a frase também não sai."""
    d = Desenho()
    tabela(d, 0, 100, LARG, CAB, [["J1", "Janela", "00", "v"], ["J2", "Janela", "0", "v"], ["J3", "Janela", "00", "v"]])
    for k in range(3):
        d.tag(200 + 5 * k, 20, "PA6")
    ex = dx.extract_dxf(d.grava(tmp_path))
    reg = ex.metadata["quadros_com_quantidade"]
    assert reg["quadros"] == [] and reg["nao_lidos"]
    p = ex.to_structured_prompt()
    assert "ETIQUETAS SOLTAS NO DESENHO" in p and "PA6 ×3" in p
    assert "QUADROS COM QUANTIDADE" not in p and "QUADRO COM QUANTIDADE (acima)" not in p


def test_CONTROLE_sem_ler_a_etiqueta_solta_a_coluna_falta(tmp_path, monkeypatch):
    monkeypatch.setenv("ATTDEF_SOLTO_E_TEXTO", "0")
    d = Desenho()
    xs, yb, _b = tabela(d, 0, 100, [8, 10, 20], ["Ref.", "Quantidade", "Tipo"],
                        [[None, "12", "de abrir"], [None, "03", "de correr"]])
    d.tag(xs[0] + 0.5, yb - 3 + 1.0, "PA6").tag(xs[0] + 0.5, yb - 6 + 1.0, "PA7")
    (q,) = lidos(tmp_path, d)
    assert q["faltam"] == ["Ref."]


# ── as linhas ────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("horizontais", [True, False])
def test_quantidade_que_nao_e_numero_nao_para_o_quadro(tmp_path, horizontais):
    linhas = [["A", "x", "2", "m"], ["B", "x", "V", "m"], ["C", "x", "3", "m"], ["D", "x", "*ver projeto*", "m"],
              ["E", "x", "5", "m"]]
    d = Desenho()
    tabela(d, 0, 100, LARG, CAB, linhas, horizontais=horizontais)
    (q,) = lidos(tmp_path, d)
    assert [r["#"] for r in como_dict(q)] == ["2", "V", "3", "*ver projeto*", "5"]
    assert [r["COD"] for r in como_dict(q)] == ["A", "B", "C", "D", "E"]


def test_linha_sem_quantidade_entre_reguas_sai_marcada_na_posicao(tmp_path):
    linhas = [["P1", "Porta", "2", "m"], ["JANELAS", None, None, None], ["J1", "Janela", "3", "m"]]
    d = Desenho()
    tabela(d, 0, 100, LARG, CAB, linhas)
    (q,) = lidos(tmp_path, d)
    assert [l["q"] for l in q["linhas"]] == ["2", None, "3"]
    assert q["linhas"][1]["cel"] == ["JANELAS"]


def test_sem_horizontais_o_que_sobra_entre_duas_faixas_e_linha_sem_quantidade(tmp_path):
    # o subtítulo fica mais perto da linha de BAIXO (a 2,6 dela, a 3,4 da de cima): com a faixa indo
    # até o meio do caminho ele entraria na linha de baixo; com meio passo pra cada lado, sobra
    linhas = [["P1", "Porta", "2", "m"], ["P2", "Porta", "4", "m"], [None, None, None, None],
              ["J1", "Janela", "3", "m"], ["J2", "Janela", "1", "m"]]
    d = Desenho()
    xs, yb, _b = tabela(d, 0, 100, LARG, CAB, linhas, horizontais=False)
    d.t(xs[0] + 0.5, yb - 9 + 1.0 - 0.4, "JANELAS")
    (q,) = lidos(tmp_path, d)
    assert [l["q"] for l in q["linhas"]] == ["2", "4", None, "3", "1"]
    assert q["linhas"][2]["cel"] == ["JANELAS"]
    assert [r["COD"] for r in como_dict(q)] == ["P1", "P2", "J1", "J2"]


def test_celula_de_duas_linhas_e_pedacos_da_mesma_linha(tmp_path):
    d = Desenho()
    xs, yb, _b = tabela(d, 0, 100, LARG, CAB,
                        [["J1", "Janela de correr", "3", "Alumínio"], ["J2", "Fixa", "1", "Vidro"]], alt=4.0)
    d.t(xs[1] + 0.5, yb - 4 + 2.4, "2 folhas")          # 2ª linha de texto da célula TIPO, acima da de base
    d.t(xs[2] + 3.0, yb - 4 + 1.0, "MT")                # a unidade num texto ao lado do número
    (q,) = lidos(tmp_path, d)
    assert como_dict(q)[0] == {"#": "3 MT", "COD": "J1", "TIPO": "2 folhas / Janela de correr", "MATERIAL": "Alumínio"}


def test_texto_sobreposto_conta_uma_vez(tmp_path):
    d = Desenho()
    xs, yb, _b = tabela(d, 0, 100, LARG, CAB, LINHAS)
    d.t(xs[0] + 0.5, yb - 3 + 1.0, "J1")
    (q,) = lidos(tmp_path, d)
    assert como_dict(q)[0]["COD"] == "J1"


def test_outro_cabecalho_de_quantidade_embaixo_acaba_o_quadro(tmp_path):
    # dois quadros empilhados com as MESMAS verticais: o de cima acaba no cabeçalho do de baixo
    d = Desenho()
    _xs, _yb, base = tabela(d, 0, 100, LARG, CAB, LINHAS[:2])
    tabela(d, 0, base, LARG, CAB, LINHAS[2:])
    a, b = lidos(tmp_path, d)
    assert [r["COD"] for r in como_dict(a)] == ["J1", "J2"]
    assert [r["COD"] for r in como_dict(b)] == ["P1"]


def test_quadro_em_grupos_com_vao_continua_enquanto_as_verticais_o_ladeiam(tmp_path):
    d = Desenho()
    xs, _yb, base = tabela(d, 0, 100, LARG, CAB, LINHAS[:2])
    topo2 = base - 2                                     # 2º grupo, um vão de 2 abaixo, sem cabeçalho
    d.h(topo2, xs[0], xs[-1]).h(topo2 - 3, xs[0], xs[-1])
    for x in xs:
        d.v(x, topo2 - 3, topo2)
    for i, c in enumerate(LINHAS[2]):
        d.t(xs[i] + 0.5, topo2 - 3 + 1.0, c)
    (q,) = lidos(tmp_path, d)
    assert [r["COD"] for r in como_dict(q)] == ["J1", "J2", "P1"]


def test_o_quadro_acaba_onde_as_verticais_acabam(tmp_path):
    d = Desenho()
    xs, _yb, base = tabela(d, 0, 100, LARG, CAB, LINHAS[:2])
    for i, c in enumerate(LINHAS[2]):                    # textos no mesmo passo, mas FORA da grade
        d.t(xs[i] + 0.5, base - 3 + 1.0, c)
    (q,) = lidos(tmp_path, d)
    assert [r["COD"] for r in como_dict(q)] == ["J1", "J2"]


def test_o_salto_de_passo_acaba_o_quadro(tmp_path):
    # as verticais seguem pra baixo (a moldura da prancha), e 12 abaixo da última linha há um número
    # na coluna da quantidade: o passo era 3, o salto de 4× não é a próxima linha
    d = Desenho()
    xs, _yb, base = tabela(d, 0, 100, LARG, CAB, LINHAS)
    for x in xs:
        d.v(x, base - 20, base)
    d.t(xs[2] + 0.5, base - 12 + 1.0, "99")
    (q,) = lidos(tmp_path, d)
    assert [r["#"] for r in como_dict(q)] == ["2", "5", "12"]


def test_CONTROLE_no_mesmo_passo_a_linha_continua(tmp_path):
    d = Desenho()
    xs, _yb, base = tabela(d, 0, 100, LARG, CAB, LINHAS)
    for x in xs:
        d.v(x, base - 20, base)
    d.t(xs[2] + 0.5, base - 3 + 1.0, "99")
    (q,) = lidos(tmp_path, d)
    assert [r["#"] for r in como_dict(q)] == ["2", "5", "12", "99"]


def test_numero_longe_embaixo_do_cabecalho_nao_e_a_primeira_linha(tmp_path):
    # cabeçalho com régua e verticais, e o 1º número da coluna só 15 alturas abaixo: não é linha dele
    d = Desenho()
    xs, yb, _b = tabela(d, 0, 100, LARG, CAB, [])
    for x in xs:
        d.v(x, yb - 30, yb)
    d.t(xs[2] + 0.5, yb - 15, "7")
    reg = registro(tmp_path, d)
    assert reg["quadros"] == [] and reg["nao_lidos"][0]["motivo"] == "sem linha com quantidade"


def test_paragrafo_centrado_numa_caixa_larga_cai_na_coluna_do_ponto_de_alinhamento(tmp_path):
    # o MTEXT da última coluna começa a caixa DENTRO da coluna vizinha e centra o parágrafo: o ponto
    # de inserção está no MATERIAL, o texto que se vê está na OBSERVAÇÃO
    d = Desenho()
    cab = ["COD", "QTD", "MATERIAL", "OBSERVAÇÃO"]
    xs, yb, _b = tabela(d, 0, 100, [8, 8, 20, 24], cab, [["J1", "3", "Vidro", "Janela fixa"], ["J2", "1", "Vidro", None]])
    d.t(xs[3] - 2.0, yb - 6 + 1.0, "Janela maxim-ar", centrado_na_caixa=28.0)
    (q,) = lidos(tmp_path, d)
    assert como_dict(q)[1] == {"#": "1", "COD": "J2", "MATERIAL": "Vidro", "OBSERVAÇÃO": "Janela maxim-ar"}


def test_celula_centrada_e_celula_a_esquerda_da_mesma_coluna_agrupam_pelo_ponto_de_insercao(tmp_path):
    # quadro só com moldura: na coluna "Ambiente" uma célula é de parágrafo centrado (o ponto de
    # alinhamento fica 6 à direita) e as outras não — a caixa começa no mesmo x, e é por ele que as
    # células viram coluna
    d = Desenho()
    xs, yb, _b = tabela(d, 0, 100, [8, 8, 20], ["Quant", "Cor", "Ambiente"],
                        [["41", "Branco", None], ["04", "Branco", "Hall"], ["02", "Preto", "Escada"], ["07", "Preto", "Copa"]],
                        verticais="moldura", horizontais=False)
    d.t(xs[2] + 0.5, yb - 3 + 1.0, "Circulação", centrado_na_caixa=12.0)
    (q,) = lidos(tmp_path, d)
    assert q["colunas"] == ["Quant", "Cor", "Ambiente"]
    assert como_dict(q)[0] == {"#": "41", "Cor": "Branco", "Ambiente": "Circulação"}


def test_giro_de_359_98_graus_e_texto_deitado(tmp_path):
    d = Desenho()
    tabela(d, 0, 100, LARG, CAB, LINHAS)
    for t in d.textos:
        t["giro"] = 359.98
    (q,) = lidos(tmp_path, d)
    assert [r["#"] for r in como_dict(q)] == ["2", "5", "12"]


def test_texto_girado_nao_e_do_quadro(tmp_path):
    d = Desenho()
    xs, yb, _b = tabela(d, 0, 100, LARG, CAB, LINHAS)
    d.t(xs[1] + 12, yb - 3 + 1.0, "VER DETALHE", giro=90.0)
    (q,) = lidos(tmp_path, d)
    assert como_dict(q)[0]["TIPO"] == "Janela basculante"


def test_cabecalho_de_quantidade_girado_nao_abre_quadro(tmp_path):
    d = Desenho()
    tabela(d, 0, 100, LARG, CAB, LINHAS)
    for t in d.textos:
        if t["s"] == "QTD":
            t["giro"] = 90.0
    assert registro(tmp_path, d) == {}


# ── o cabeçalho ──────────────────────────────────────────────────────────────────────────────
def test_cabecalho_de_duas_linhas_e_uma_folha(tmp_path):
    d = Desenho()
    xs, yb, _b = tabela(d, 0, 100, LARG, ["COD", "(cm)", "QTD", "MATERIAL"], LINHAS, alt_cab=5.0)
    d.t(xs[1] + 2.5, yb + 2.6, "Dimensões")             # em cima do "(cm)", com outro x (centrado)
    (q,) = lidos(tmp_path, d)
    assert q["colunas"] == ["COD", "Dimensões (cm)", "QTD", "MATERIAL"]


def test_titulo_de_grupo_vira_prefixo_das_colunas_dele(tmp_path):
    # COD | [ABERTURAS: VÃO | PEITORIL] | QTD — a vertical entre os dois não sobe até a linha do grupo
    d = Desenho()
    xs = [0, 8, 18, 28, 36]
    topo, meio, yb, base = 100, 97, 94, 88
    d.h(topo, xs[0], xs[-1]).h(meio, xs[1], xs[3]).h(yb, xs[0], xs[-1]).h(yb - 3, xs[0], xs[-1]).h(base, xs[0], xs[-1])
    for i, x in enumerate(xs):
        d.v(x, base, meio if i == 2 else topo)
    d.t(xs[1] + 0.5, meio + 1, "ABERTURAS")
    for i, c in enumerate(["COD", "VÃO", "PEITORIL", "QTD"]):
        d.t(xs[i] + 0.5, yb + 1, c)
    for k, ln in enumerate([["P1", "80 x 210", "-", "4"], ["J1", "120 x 150", "100", "9"]]):
        for i, c in enumerate(ln):
            d.t(xs[i] + 0.5, yb - 3 * (k + 1) + 1, c)
    (q,) = lidos(tmp_path, d)
    assert q["colunas"] == ["COD", "ABERTURAS · VÃO", "ABERTURAS · PEITORIL", "QTD"]
    assert como_dict(q)[1] == {"#": "9", "COD": "J1", "ABERTURAS · VÃO": "120 x 150", "ABERTURAS · PEITORIL": "100"}


def test_titulo_do_quadro_dentro_da_faixa_do_cabecalho_fica_de_fora(tmp_path):
    d = Desenho()
    xs, yb, _b = tabela(d, 0, 100, LARG, CAB, LINHAS, alt_cab=6.0, v_no_cab=False)
    d.t(xs[1], yb + 4.0, "QUADRO DE ESQUADRIAS")        # sozinho na linha dele, sem vertical: ocupa tudo
    (q,) = lidos(tmp_path, d)
    assert q["colunas"] == CAB


def test_CONTROLE_dois_textos_na_linha_de_cima_sao_segunda_linha_do_cabecalho(tmp_path):
    d = Desenho()
    xs, yb, _b = tabela(d, 0, 100, LARG, CAB, LINHAS, alt_cab=6.0, v_no_cab=False)
    d.t(xs[1] + 0.5, yb + 4.0, "ESQUADRIA")
    d.t(xs[3] + 0.5, yb + 4.0, "ACABAMENTO")
    (q,) = lidos(tmp_path, d)
    assert q["colunas"] == ["COD", "ESQUADRIA TIPO", "QTD", "ACABAMENTO MATERIAL"]


def test_vertical_que_nao_sobe_ao_cabecalho_vale_o_intervalo_do_texto(tmp_path):
    d = Desenho()
    tabela(d, 0, 100, LARG, CAB, LINHAS, v_no_cab=False)
    (q,) = lidos(tmp_path, d)
    assert q["colunas"] == CAB
    assert como_dict(q)[0] == {"#": "2", "COD": "J1", "TIPO": "Janela basculante", "MATERIAL": "Vidro"}


def test_regua_que_acaba_antes_da_borda_a_ponta_dela_e_a_borda(tmp_path):
    # a quantidade é a ÚLTIMA coluna e a régua do cabeçalho para 2 antes da vertical da direita
    d = Desenho()
    linhas = [[a, b, m, n] for a, b, n, m in LINHAS]
    tabela(d, 0, 100, [8, 20, 20, 8], ["COD", "TIPO", "MATERIAL", "QTD"], linhas, regua_ate=54.0)
    (q,) = lidos(tmp_path, d)
    assert [r["#"] for r in como_dict(q)] == ["2", "5", "12"]
    assert como_dict(q)[2] == {"#": "12", "COD": "P1", "TIPO": "Porta de abrir", "MATERIAL": "Madeira"}


# ── o vizinho ────────────────────────────────────────────────────────────────────────────────
def test_quadro_vizinho_com_a_regua_dele_fica_de_fora(tmp_path):
    d = Desenho()
    tabela(d, 0, 100, LARG, CAB, LINHAS)
    tabela(d, 60, 100, LARG, ["REF", "NOME", "QTD", "OBS"],
           [["X1", "Outro", "7", "a"], ["X2", "Outro", "8", "b"], ["X3", "Outro", "9", "c"]])
    a, b = lidos(tmp_path, d)
    assert a["colunas"] == CAB and b["colunas"] == ["REF", "NOME", "QTD", "OBS"]
    assert [r["#"] for r in como_dict(a)] == ["2", "5", "12"] and [r["#"] for r in como_dict(b)] == ["7", "8", "9"]
    assert all(set(r) == {"#", "COD", "TIPO", "MATERIAL"} for r in como_dict(a))
    assert all(set(r) == {"#", "REF", "NOME", "OBS"} for r in como_dict(b))


def test_vizinho_colado_na_mesma_regua_corta_onde_o_nome_da_coluna_se_repete(tmp_path):
    d = Desenho()
    cab = ["ITEM", "TIPO", "QTD", "DESCRIÇÃO"]
    linhas = [["01", "L1", "1", "CHG", "29", "L2", "3", "FT-1"], ["02", "L1", "2", "DJ-1", "30", "L2", "4", "TR-1"]]
    tabela(d, 0, 100, [6, 6, 6, 20] * 2, cab * 2, linhas)
    a, b = lidos(tmp_path, d)
    assert a["colunas"] == cab and b["colunas"] == cab
    assert como_dict(a) == [{"#": "1", "ITEM": "01", "TIPO": "L1", "DESCRIÇÃO": "CHG"},
                            {"#": "2", "ITEM": "02", "TIPO": "L1", "DESCRIÇÃO": "DJ-1"}]
    assert como_dict(b) == [{"#": "3", "ITEM": "29", "TIPO": "L2", "DESCRIÇÃO": "FT-1"},
                            {"#": "4", "ITEM": "30", "TIPO": "L2", "DESCRIÇÃO": "TR-1"}]


def test_duas_colunas_de_quantidade_sem_nome_repetido_e_um_quadro_so(tmp_path):
    d = Desenho()
    tabela(d, 0, 100, [8, 20, 8, 8], ["COD", "TIPO", "QTD", "QUANT."], [["J1", "Janela", "2", "3"], ["J2", "Janela", "5", "6"]])
    (q,) = lidos(tmp_path, d)
    assert q["colunas"] == ["COD", "TIPO", "QTD", "QUANT."] and q["colunas"][q["iq"]] == "QTD"
    assert como_dict(q) == [{"#": "2", "COD": "J1", "TIPO": "Janela", "QUANT.": "3"},
                            {"#": "5", "COD": "J2", "TIPO": "Janela", "QUANT.": "6"}]


def test_a_segunda_coluna_de_quantidade_nao_vira_a_ancora_mesmo_escrita_mais_alta(tmp_path):
    d = Desenho()
    tabela(d, 0, 100, [8, 20, 8, 8], ["COD", "TIPO", "QTD", "QUANT."], [["J1", "Janela", "2", "3"], ["J2", "Janela", "5", "6"]])
    for t in d.textos:
        if t["s"] == "QUANT.":
            t["y"] += 0.3                                # sai primeiro na ordem de cima pra baixo
    (q,) = lidos(tmp_path, d)
    assert q["colunas"][q["iq"]] == "QTD"
    assert [r["#"] for r in como_dict(q)] == ["2", "5"]


def test_duas_colunas_de_quantidade_com_o_MESMO_nome_sao_um_quadro_so(tmp_path):
    # "QTD" repetido não é o nome de coluna que se repete num quadro vizinho: é a outra quantidade
    d = Desenho()
    tabela(d, 0, 100, [8, 20, 8, 8], ["COD", "TIPO", "QTD", "QTD"], [["J1", "Janela", "2", "3"], ["J2", "Janela", "5", "6"]])
    reg = registro(tmp_path, d)
    (q,) = reg["quadros"]
    assert reg["nao_lidos"] == []
    assert q["colunas"] == ["COD", "TIPO", "QTD", "QTD"] and q["iq"] == 2
    assert [l["cel"] for l in q["linhas"]] == [["J1", "Janela", "2", "3"], ["J2", "Janela", "5", "6"]]


# ── o quadro só com moldura: o texto refina dentro da célula da grade ────────────────────────
def test_quadro_so_com_moldura_abre_sub_colunas_quando_as_celulas_fecham_com_o_cabecalho(tmp_path):
    d = Desenho()
    tabela(d, 0, 100, [8, 8, 8, 8], ["Legenda", "Quant", "Larg", "Compr"],
           [["A", "2363", "40", "49"], ["B", "46", "34", "49"], ["C", "2", "30", "49"]],
           verticais="moldura", horizontais=False)
    (q,) = lidos(tmp_path, d)
    assert q["colunas"] == ["Legenda", "Quant", "Larg", "Compr"]
    assert como_dict(q)[1] == {"#": "46", "Legenda": "B", "Larg": "34", "Compr": "49"}


def test_na_duvida_o_intervalo_sai_inteiro(tmp_path):
    # COD | (VÃO e PEITORIL sem vertical entre eles) | QTD — o peitoril só aparece numa linha de quatro
    d = Desenho()
    xs, yb, _b = tabela(d, 0, 100, [8, 24, 8], ["COD", "VÃO", "QTD"],
                        [["P1", "80 x 210", "4"], ["P2", "90 x 210", "2"], ["P3", "70 x 210", "1"], ["J1", "120 x 150", "9"]])
    d.t(xs[1] + 14, yb + 1, "PEITORIL")
    d.t(xs[1] + 14, yb - 12 + 1, "100")
    (q,) = lidos(tmp_path, d)
    assert q["colunas"] == ["COD", "VÃO / PEITORIL", "QTD"]
    assert como_dict(q)[3] == {"#": "9", "COD": "J1", "VÃO / PEITORIL": "120 x 150 100"}
    assert como_dict(q)[0] == {"#": "4", "COD": "P1", "VÃO / PEITORIL": "80 x 210"}


def test_CONTROLE_com_o_peitoril_em_toda_linha_abre_as_duas_sub_colunas(tmp_path):
    d = Desenho()
    xs, yb, _b = tabela(d, 0, 100, [8, 24, 8], ["COD", "VÃO", "QTD"],
                        [["P1", "80 x 210", "4"], ["P2", "90 x 210", "2"], ["P3", "70 x 210", "1"], ["J1", "120 x 150", "9"]])
    d.t(xs[1] + 14, yb + 1, "PEITORIL")
    for k, v in enumerate(["-", "-", "-", "100"]):
        d.t(xs[1] + 14, yb - 3 * (k + 1) + 1, v)
    (q,) = lidos(tmp_path, d)
    assert q["colunas"] == ["COD", "VÃO", "PEITORIL", "QTD"]
    assert como_dict(q)[3] == {"#": "9", "COD": "J1", "VÃO": "120 x 150", "PEITORIL": "100"}


def test_celula_solta_entre_duas_sub_colunas_cheias_o_intervalo_sai_inteiro(tmp_path):
    # as duas sub-colunas estão cheias, mas há um texto solto no meio delas numa linha: de quem é?
    d = Desenho()
    xs, yb, _b = tabela(d, 0, 100, [8, 24, 8], ["COD", "VÃO", "QTD"],
                        [["P1", "80 x 210", "4"], ["P2", "90 x 210", "2"], ["P3", "70 x 210", "1"], ["J1", "120 x 150", "9"]])
    d.t(xs[1] + 16, yb + 1, "PEITORIL")
    for k, v in enumerate(["-", "-", "-", "100"]):
        d.t(xs[1] + 16, yb - 3 * (k + 1) + 1, v)
    d.t(xs[1] + 9, yb - 6 + 1, "ver nota")
    (q,) = lidos(tmp_path, d)
    assert q["colunas"] == ["COD", "VÃO / PEITORIL", "QTD"]
    assert como_dict(q)[1] == {"#": "2", "COD": "P2", "VÃO / PEITORIL": "90 x 210 ver nota -"}


# ── o que NÃO é lido ─────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("cab", [["AÇO", "POS", "BIT", "QUANT", "COMPRIMENTO"],
                                 ["AÇO", "N", "DIAM (mm)", "QUANT", "C.TOTAL (cm)"],
                                 ["TIPO", "POS.", "BIT.", "QUANT.", "C.Tot. (cm)"]])
def test_quadro_de_aco_fica_de_fora_calado(tmp_path, cab):
    d = Desenho()
    tabela(d, 0, 100, [8, 8, 12, 8, 14], cab, [["CA50", "1", "8.0", "26", "482"], ["CA50", "2", "10.0", "30", "328"]])
    assert registro(tmp_path, d) == {}


def test_a_regua_da_bitola_e_a_do_leitor_de_aco(tmp_path, monkeypatch):
    # o vocabulário da coluna de bitola é o do leitor de aço (um lugar só): trocando a régua DELE
    # por uma que não casa nada, o quadro de aço passa a ser lido como quadro de quantidade
    import re
    import structural_extractor as se
    assert se._BITOLA_HDR_RE.search("BIT.") and se._BITOLA_HDR_RE.search("DIAM (mm)")
    monkeypatch.setattr(se, "_BITOLA_HDR_RE", re.compile("NUNCA-CASA"))
    d = Desenho()
    tabela(d, 0, 100, [8, 8, 12, 8, 14], ["AÇO", "POS", "BIT", "QUANT", "COMPRIMENTO"],
           [["CA50", "1", "8.0", "26", "482"], ["CA50", "2", "10.0", "30", "328"]])
    assert len(lidos(tmp_path, d)) == 1


def test_CONTROLE_diametro_sem_comprimento_nao_e_aco(tmp_path):
    d = Desenho()
    tabela(d, 0, 100, [10, 10, 30], ["DIÂM.", "QUANT.", "DESCRIÇÃO"], [["25", "12", "JOELHO 90°"], ["32", "4", "TÊ"]])
    (q,) = lidos(tmp_path, d)
    assert como_dict(q)[0] == {"#": "12", "DIÂM.": "25", "DESCRIÇÃO": "JOELHO 90°"}


def test_quantidade_toda_em_zero_nao_e_lida(tmp_path):
    d = Desenho()
    tabela(d, 0, 100, LARG, CAB, [["J1", "Janela", "00", "v"], ["J2", "Janela", "0", "v"], ["J3", "Janela", "00", "v"]])
    reg = registro(tmp_path, d)
    assert reg["quadros"] == [] and reg["nao_lidos"][0]["motivo"] == "a coluna da quantidade está toda em zero"


def test_CONTROLE_um_zero_entre_numeros_e_lido(tmp_path):
    d = Desenho()
    tabela(d, 0, 100, LARG, CAB, [["J1", "Janela", "00", "v"], ["J2", "Janela", "61", "v"], ["J3", "Janela", "00", "v"]])
    (q,) = lidos(tmp_path, d)
    assert [r["#"] for r in como_dict(q)] == ["00", "61", "00"]


def test_coluna_da_quantidade_quase_sem_numero_nao_e_lida(tmp_path):
    d = Desenho()
    tabela(d, 0, 100, [30, 22], ["DESCRIÇÃO", "QUANTIDADE"],
           [["TOMADA BAIXA", "XX UNID. DE 10A"], ["TOMADA MÉDIA", "XX UNID. DE 20A"], ["INTERRUPTOR", "3"]])
    reg = registro(tmp_path, d)
    assert reg["quadros"] == [] and reg["nao_lidos"][0]["motivo"] == "a coluna da quantidade quase não tem número"


def test_cabecalho_sem_linha_embaixo_nao_e_lido(tmp_path):
    d = Desenho()
    tabela(d, 0, 100, LARG, CAB, [])
    reg = registro(tmp_path, d)
    assert reg["quadros"] == [] and reg["nao_lidos"][0]["motivo"] == "sem linha com quantidade"


# ── o registro, a chave e a seção do prompt ──────────────────────────────────────────────────
def test_a_copia_do_quadro_no_mesmo_arquivo_sai_uma_vez(tmp_path):
    d = Desenho()
    tabela(d, 0, 100, LARG, CAB, LINHAS)
    tabela(d, 0, 0, LARG, CAB, LINHAS)
    ex = dx.extract_dxf(d.grava(tmp_path))
    a, b = ex.metadata["quadros_com_quantidade"]["quadros"]
    assert a["copia_de"] is None and b["copia_de"] == 1 and a["assinatura"] == b["assinatura"]
    p = ex.to_structured_prompt()
    assert p.count("= o MESMO conteúdo do QUADRO 1, desenhado de novo: conte UMA vez.") == 1
    assert p.count("COD: J1") == 1, "as linhas da cópia não são repetidas"


def test_CONTROLE_quadro_de_conteudo_diferente_nao_e_copia(tmp_path):
    d = Desenho()
    tabela(d, 0, 100, LARG, CAB, LINHAS)
    tabela(d, 0, 0, LARG, CAB, [["J1", "Janela basculante", "3", "Vidro"]] + LINHAS[1:])
    a, b = lidos(tmp_path, d)
    assert a["copia_de"] is None and b["copia_de"] is None and a["assinatura"] != b["assinatura"]


def test_a_secao_do_prompt(tmp_path):
    d = Desenho()
    tabela(d, 0, 100, [10, 10, 30], ["FOTO", "QTD", "DESCRIÇÃO"],
           [[None, "11", "BALIZADOR"], ["JANELAS", None, None], [None, "V", "FITA DE LED"]])
    p = dx.extract_dxf(d.grava(tmp_path)).to_structured_prompt()
    linhas = p.splitlines()
    assert "QUADROS COM QUANTIDADE (a quantidade que o projetista escreveu num quadro — lido do arquivo, não é chute):" in linhas
    # só o título da seção fica sem recuo (linha sem recuo abre seção); a seção fecha com linha em branco
    i = linhas.index("QUADROS COM QUANTIDADE (a quantidade que o projetista escreveu num quadro — lido do arquivo, não é chute):")
    fim = linhas.index("", i)
    assert all(l.startswith("  ") for l in linhas[i + 1:fim]) and fim - i > 12
    assert "  QUADRO 1 — colunas: FOTO | QTD | DESCRIÇÃO" in p
    assert "    QTD 11  ←  DESCRIÇÃO: BALIZADOR" in p
    assert "    QTD V  ←  DESCRIÇÃO: FITA DE LED" in p
    assert "    (sem quantidade)  JANELAS" in p
    assert "⚠ a coluna 'FOTO' não tem texto no arquivo" in p
    # o que FAZER, e qual número vale quando o item também foi contado
    assert "→ COMO USAR: cada linha de quadro é UM item da planilha" in p and "marque 'estimado'" in p
    assert "fique com a quantidade do QUADRO e cite a contagem na observação" in p
    assert "não invente o" in p


def test_o_registro_cru_nao_vai_nos_metadados_do_prompt(tmp_path):
    # 🩸 o A/B do acervo pegou: a seção de METADADOS despeja toda chave do registro, e o dicionário
    # do quadro saía inteiro no prompt (1,6 mil letras num arquivo), além da seção própria
    d = Desenho()
    tabela(d, 0, 100, LARG, CAB, LINHAS)
    ex = dx.extract_dxf(d.grava(tmp_path))
    assert "quadros_com_quantidade" in ex.metadata
    p = ex.to_structured_prompt()
    assert "quadros_com_quantidade" not in p and "'colunas'" not in p and "assinatura" not in p
    assert "QTD 2  ←  COD: J1 | TIPO: Janela basculante | MATERIAL: Vidro" in p


def test_sem_quadro_nao_ha_secao(tmp_path):
    d = Desenho()
    tabela(d, 0, 100, LARG, ["COD", "TIPO", "ÁREA", "MATERIAL"], LINHAS)
    ex = dx.extract_dxf(d.grava(tmp_path))
    assert "quadros_com_quantidade" not in (ex.metadata or {})
    assert "QUADROS COM QUANTIDADE" not in ex.to_structured_prompt()


def test_quadro_nao_lido_nao_abre_secao(tmp_path):
    d = Desenho()
    tabela(d, 0, 100, LARG, CAB, [["J1", "Janela", "00", "v"], ["J2", "Janela", "0", "v"]])
    ex = dx.extract_dxf(d.grava(tmp_path))
    assert ex.metadata["quadros_com_quantidade"]["quadros"] == []
    assert "QUADROS COM QUANTIDADE" not in ex.to_structured_prompt()


def test_a_chave_desliga(tmp_path, monkeypatch):
    monkeypatch.setenv("QUADRO_COM_QUANTIDADE", "0")
    d = Desenho()
    tabela(d, 0, 100, LARG, CAB, LINHAS)
    ex = dx.extract_dxf(d.grava(tmp_path))
    assert "quadros_com_quantidade" not in (ex.metadata or {})
    assert "QUADROS COM QUANTIDADE" not in ex.to_structured_prompt()


def test_CONTROLE_a_chave_em_1_le(tmp_path, monkeypatch):
    monkeypatch.setenv("QUADRO_COM_QUANTIDADE", "1")
    d = Desenho()
    tabela(d, 0, 100, LARG, CAB, LINHAS)
    assert len(lidos(tmp_path, d)) == 1


def test_o_teto_de_linhas_diz_quantas_ficaram_de_fora(tmp_path):
    d = Desenho()
    n = dx._QQ_LINHAS_MAX + 10
    tabela(d, 0, 1000, LARG, CAB, [["J%d" % k, "Janela", str(k + 1), "Vidro"] for k in range(n)])
    ex = dx.extract_dxf(d.grava(tmp_path))
    assert len(ex.metadata["quadros_com_quantidade"]["quadros"][0]["linhas"]) == n, "o registro guarda todas"
    p = ex.to_structured_prompt()
    assert sum(1 for l in p.splitlines() if l.startswith("    QTD ") and "  ←  " in l) == dx._QQ_LINHAS_MAX
    assert "(+10 linha(s) deste quadro não listada(s))" in p


def test_o_teto_de_quadros_diz_quantos_ficaram_de_fora():
    reg = {"quadros": [{"colunas": ["COD", "QTD"], "iq": 1, "faltam": [], "copia_de": None,
                        "linhas": [{"q": str(k), "cel": ["X%d" % k, str(k)]}]}
                       for k in range(dx._QQ_QUADROS_MAX + 3)]}
    ls = dx._linhas_dos_quadros(reg)
    assert sum(1 for l in ls if l.startswith("  QUADRO ")) == dx._QQ_QUADROS_MAX
    assert "  (+3 quadro(s) não listado(s))" in ls


def test_o_teto_do_arquivo_corta_o_quadro_seguinte():
    um = {"colunas": ["COD", "QTD"], "iq": 1, "faltam": [], "copia_de": None,
          "linhas": [{"q": "1", "cel": ["X", "1"]}] * dx._QQ_LINHAS_MAX}
    n = dx._QQ_LINHAS_ARQUIVO_MAX // dx._QQ_LINHAS_MAX
    ls = dx._linhas_dos_quadros({"quadros": [dict(um) for _ in range(n + 1)]})
    assert sum(1 for l in ls if "  ←  " in l) == dx._QQ_LINHAS_ARQUIVO_MAX
    assert "    (+%d linha(s) deste quadro não listada(s))" % dx._QQ_LINHAS_MAX in ls


def test_o_registro_e_serializavel(tmp_path):
    import json
    d = Desenho()
    tabela(d, 0, 100, LARG, CAB, LINHAS)
    reg = registro(tmp_path, d, traco="lwpolyline")
    assert json.loads(json.dumps(reg)) == reg


def test_sem_cabecalho_de_quantidade_o_modelo_nao_e_lido():
    class Msp:
        def query(self, _q):
            raise AssertionError("leu o modelo sem haver cabeçalho de quantidade")

    class T:
        def __init__(self, s):
            self.text, self.position, self.height, self.layer = s, (0.0, 0.0), 1.0, "0"
    assert dx._trechos_retos_dos_quadros(Msp(), [T("COD"), T("ÁREA")]) == ([], [])
    assert dx.quadros_do_modelo(Msp(), [T("COD"), T("ÁREA")]) == {}
    with pytest.raises(AssertionError):
        dx._trechos_retos_dos_quadros(Msp(), [T("QTD")])


def test_o_lado_em_arco_da_polilinha_nao_e_linha_de_quadro(tmp_path):
    # a régua do cabeçalho desenhada em ARCO (bulge) não é régua: sem ela não há quadro
    d = Desenho()
    xs, yb, _b = tabela(d, 0, 100, LARG, CAB, LINHAS)
    d.hs = [h for h in d.hs if h[0] != yb]
    doc = ezdxf.readfile(d.grava(tmp_path))
    doc.modelspace().add_lwpolyline([(xs[0], yb, 0.3), (xs[-1], yb, 0.0)], format="xyb", dxfattribs={"layer": "ARQ-QUADRO"})
    p = str(tmp_path / "arco.dxf")
    doc.saveas(p)
    assert (dx.extract_dxf(p).metadata or {}).get("quadros_com_quantidade") is None


def test_o_leitor_nao_muta_os_textos(tmp_path):
    d = Desenho()
    tabela(d, 0, 100, LARG, CAB, LINHAS)
    ex = dx.extract_dxf(d.grava(tmp_path))
    antes = [(t.text, t.position, t.height) for t in ex.texts]
    hs = [(y, a, b) for y, a, b in d.hs]
    vs = [(x, a, b) for x, a, b in d.vs]
    assert len([q for q in er.quadros_com_quantidade(ex.texts, hs, vs) if not q["motivo"]]) == 1
    assert [(t.text, t.position, t.height) for t in ex.texts] == antes
