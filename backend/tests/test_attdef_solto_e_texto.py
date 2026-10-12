# -*- coding: utf-8 -*-
"""O ATTDEF solto no modelo é texto na folha: o TAG.

📏 11/10/2026 — estudo do acervo (342 DXF): a etiqueta de porta e janela de 4
jobs ("PA6", "JA-09") é ATTDEF de 1º nível no modelo — o que sobra quando o
bloco da etiqueta é explodido. O CAD desenha o tag como um texto; o motor só
lia TEXT e MTEXT, e a coluna "Ref." do quadro de esquadrias chegava vazia.
1.740 ATTDEF soltos em 44 arquivos de 19 jobs; 1 invisível.

A prova, num arquivo: lendo os tags, as 29 linhas do quadro de esquadrias fecham
com a contagem das etiquetas desenhadas — a quantidade escrita é o nº de
etiquetas fora do quadro menos 1 (o desenho de detalhe de cada tipo).

🪤 Nomes e layers FICTÍCIOS (repositório público, regra nº6).
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402

H = 0.20


def _arquivo(tmp_path, monta):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "ARQ-PAREDE"})
    monta(doc, msp)
    p = str(tmp_path / "etiquetas.dxf")
    doc.saveas(p)
    return p


def _etiquetas(msp):
    """Três portas PA1 e uma janela JA-02 etiquetadas na planta, com ATTDEF solto."""
    for i in range(3):
        msp.add_attdef("PA1", (1 + i * 2, 2), dxfattribs={"height": H, "layer": "ARQ-SIMB"})
    msp.add_attdef("JA-02", (8, 2), dxfattribs={"height": H, "layer": "ARQ-SIMB", "rotation": 90})


def _por_texto(ex):
    r = {}
    for t in ex.texts:
        r.setdefault(t.text, []).append(t)
    return r


def test_o_attdef_solto_chega_como_texto_com_o_tag(tmp_path, monkeypatch):
    monkeypatch.delenv("ATTDEF_SOLTO_E_TEXTO", raising=False)
    ex = dx.extract_dxf(_arquivo(tmp_path, lambda doc, msp: _etiquetas(msp)))
    tx = _por_texto(ex)
    assert len(tx["PA1"]) == 3 and len(tx["JA-02"]) == 1
    pa = sorted(tx["PA1"], key=lambda t: t.position[0])[0]
    assert pa.layer == "ARQ-SIMB" and pa.height == pytest.approx(H)
    assert pa.position == pytest.approx((1.0, 2.0)) and pa.rotation == 0.0
    assert tx["JA-02"][0].rotation == pytest.approx(90.0), "a etiqueta girada leva o ângulo"
    assert all(t.de_attdef for t in tx["PA1"] + tx["JA-02"]), "a origem fica marcada"


def test_text_e_mtext_nao_levam_a_marca_de_attdef(tmp_path, monkeypatch):
    monkeypatch.delenv("ATTDEF_SOLTO_E_TEXTO", raising=False)

    def monta(doc, msp):
        _etiquetas(msp)
        msp.add_text("SALA", dxfattribs={"height": H, "layer": "ARQ-TEXTO", "insert": (1, 5)})
        msp.add_mtext("COZINHA", dxfattribs={"char_height": H, "layer": "ARQ-TEXTO", "insert": (4, 5)})
    tx = _por_texto(dx.extract_dxf(_arquivo(tmp_path, monta)))
    assert not tx["SALA"][0].de_attdef and not tx["COZINHA"][0].de_attdef
    assert dx.TextAnnotation(layer="X", text="Y").de_attdef is False


def test_o_attdef_invisivel_nao_e_texto(tmp_path, monkeypatch):
    """O bit 1 do grupo 70: o CAD não desenha esse atributo."""
    monkeypatch.delenv("ATTDEF_SOLTO_E_TEXTO", raising=False)

    def monta(doc, msp):
        _etiquetas(msp)
        msp.add_attdef("CODIGO_INTERNO", (5, 5), dxfattribs={"height": H, "layer": "ARQ-SIMB", "flags": 1})
        msp.add_attdef("PRESET", (6, 5), dxfattribs={"height": H, "layer": "ARQ-SIMB", "flags": 8})   # visível
    tx = _por_texto(dx.extract_dxf(_arquivo(tmp_path, monta)))
    assert "CODIGO_INTERNO" not in tx
    assert "PRESET" in tx, "só o bit de INVISÍVEL tira; constante, verificar e predefinido aparecem na folha"


def test_o_attdef_de_dentro_do_bloco_nao_e_texto(tmp_path, monkeypatch):
    """Dentro da definição de bloco o ATTDEF é molde: na folha aparece o ATTRIB
    do INSERT, que o motor lê por outro caminho."""
    monkeypatch.delenv("ATTDEF_SOLTO_E_TEXTO", raising=False)

    def monta(doc, msp):
        b = doc.blocks.new("ETIQUETA_PORTA")
        b.add_attdef("CODIGO_DA_PORTA", (0, 0), dxfattribs={"height": H})
        b.add_circle((0, 0), 0.3)
        msp.add_blockref("ETIQUETA_PORTA", (3, 3)).add_attrib("CODIGO_DA_PORTA", "PM7", (3, 3))
        _etiquetas(msp)
    tx = _por_texto(dx.extract_dxf(_arquivo(tmp_path, monta)))
    assert "CODIGO_DA_PORTA" not in tx
    assert len(tx["PA1"]) == 3


def test_a_chave_desliga_sem_deploy(tmp_path, monkeypatch):
    p = _arquivo(tmp_path, lambda doc, msp: _etiquetas(msp))
    monkeypatch.setenv("ATTDEF_SOLTO_E_TEXTO", "0")
    assert not [t for t in dx.extract_dxf(p).texts if t.text in ("PA1", "JA-02")]
    monkeypatch.setenv("ATTDEF_SOLTO_E_TEXTO", "1")
    assert len([t for t in dx.extract_dxf(p).texts if t.text == "PA1"]) == 3


def test_o_tag_do_attdef_solto():
    class _Dxf:
        def __init__(self, **kw):
            self._kw = kw

        def get(self, k, padrao=None):
            return self._kw.get(k, padrao)

    class _E:
        def __init__(self, **kw):
            self.dxf = _Dxf(**kw)
    assert dx._tag_do_attdef_solto(_E(tag="PA6")) == "PA6"
    assert dx._tag_do_attdef_solto(_E(tag="  JA-09 ", flags=0)) == "JA-09"
    assert dx._tag_do_attdef_solto(_E(tag="PA6", flags=1)) == ""          # invisível
    assert dx._tag_do_attdef_solto(_E(tag="PA6", flags=9)) == ""          # invisível + predefinido
    assert dx._tag_do_attdef_solto(_E(tag="PA6", flags=2)) == "PA6"       # constante: aparece
    assert dx._tag_do_attdef_solto(_E(tag="")) == ""
    assert dx._tag_do_attdef_solto(_E()) == ""
    assert dx._tag_do_attdef_solto(object()) == "", "nunca levanta"


def test_o_tag_chega_ao_prompt(tmp_path, monkeypatch):
    """Do arquivo ao prompt: a etiqueta entra na lista de textos que a IA lê."""
    monkeypatch.delenv("ATTDEF_SOLTO_E_TEXTO", raising=False)

    def monta(doc, msp):
        _etiquetas(msp)
        msp.add_text("SALA", dxfattribs={"height": H, "layer": "ARQ-TEXTO", "insert": (1, 5)})   # a seção já existe
    p = _arquivo(tmp_path, monta)
    com = dx.extract_dxf(p).to_structured_prompt()
    monkeypatch.setenv("ATTDEF_SOLTO_E_TEXTO", "0")
    sem = dx.extract_dxf(p).to_structured_prompt()
    assert "PA1" not in sem and "JA-02" not in sem and "ETIQUETAS SOLTAS" not in sem
    so_com = [l for l in com.splitlines() if l not in set(sem.splitlines())]
    # o bloco das etiquetas: o cabeçalho (4 linhas) e UMA linha por camada, com o ×N
    assert so_com[0].startswith("  ETIQUETAS SOLTAS NO DESENHO (o código que o CAD mostra")
    assert "conta a etiqueta, não a" in " ".join(so_com[:4])
    assert so_com[4:] == ["  [ARQ-SIMB]: PA1 ×3; JA-02"], so_com
    assert [l for l in sem.splitlines() if l not in set(com.splitlines())] == [], "o prompt só GANHA linha"
    linhas = com.splitlines()
    assert linhas.index(so_com[0]) > linhas.index("TEXTOS/LEGENDAS:"), "o bloco fica dentro da seção de textos"


def _camada_cheia(msp, n=55):
    """Uma camada com mais textos distintos que o teto de 50 da lista."""
    for i in range(n):
        msp.add_text("NOTA %02d DA PRANCHA" % i, dxfattribs={"height": H, "layer": "ARQ-SIMB",
                                                             "insert": (i % 10, 10 + i // 10)})


def test_a_etiqueta_nao_disputa_o_teto_da_camada(tmp_path, monkeypatch):
    """🩸 A/B no acervo: misturada aos textos da camada, a etiqueta empurrava pra
    fora do teto de 50 textos que a IA lia (4 textos em 2 arquivos)."""
    def monta(doc, msp):
        _camada_cheia(msp)
        for i in range(12):
            msp.add_attdef("AA%d" % i, (i, 2), dxfattribs={"height": H, "layer": "ARQ-SIMB"})   # vêm antes no alfabeto
            msp.add_attdef("AA%d" % i, (i, 3), dxfattribs={"height": H, "layer": "ARQ-SIMB"})   # e repetidas: ×2
    p = _arquivo(tmp_path, monta)
    monkeypatch.delenv("ATTDEF_SOLTO_E_TEXTO", raising=False)
    com = dx.extract_dxf(p).to_structured_prompt().splitlines()
    monkeypatch.setenv("ATTDEF_SOLTO_E_TEXTO", "0")
    sem = dx.extract_dxf(p).to_structured_prompt().splitlines()
    assert [l for l in sem if l not in set(com)] == [], "nenhuma linha que a IA lia some ou muda"
    assert "    (+5 texto(s) desta camada não listado(s))" in com
    assert any(l.startswith("  [ARQ-SIMB]: AA0 ×2; AA1 ×2") for l in com)


def test_a_etiqueta_de_duas_letras_e_listada_e_a_de_uma_nao(tmp_path, monkeypatch):
    """ "P1" e "J3" são código de porta e janela; "A" é eixo — o contador de texto
    repetido corta em 3 letras, e aqui o corte é 2."""
    monkeypatch.delenv("ATTDEF_SOLTO_E_TEXTO", raising=False)

    def monta(doc, msp):
        msp.add_text("SALA", dxfattribs={"height": H, "layer": "ARQ-TEXTO", "insert": (1, 5)})
        for i, tag in enumerate(("P1", "P1", "J3", "A", "+0.15", "+0.15")):
            msp.add_attdef(tag, (i, 2), dxfattribs={"height": H, "layer": "ARQ-SIMB"})
    linhas = dx.extract_dxf(_arquivo(tmp_path, monta)).to_structured_prompt().splitlines()
    linha = next(l for l in linhas if l.startswith("  [ARQ-SIMB]: "))
    assert linha == "  [ARQ-SIMB]: P1 ×2; J3", linha         # "A" não entra; o nível sai da lista (12/10)
    assert linhas[linhas.index(linha) + 1:][:2] == _CORTE


#: 12/10/2026 — a etiqueta de nível é referência de altura, nunca peça; no acervo
#: é 22 % das etiquetas soltas listáveis, e em 5 arquivos de 3 jobs, todas. (A linha
#: "marcadores de nível" da 1ª planilha com o bloco veio da contagem do BLOCO do
#: símbolo de nível, não da etiqueta — é outra régua.)
#: 🪤 O corte é dito SEM dizer quantas: "N etiquetas de nível" é número com cara
#: de resposta (vira "N marcadores de nível").
_CORTE = ["  (as etiquetas de NÍVEL soltas no desenho não são listadas: são referência de",
          "   altura, não peça — NÃO gere item a partir delas)"]


def test_o_corte_nao_traz_numero():
    assert not any(c.isdigit() for c in "".join(_CORTE))


def _com_etiquetas(tmp_path, tags):
    def monta(doc, msp):
        msp.add_text("SALA", dxfattribs={"height": H, "layer": "ARQ-TEXTO", "insert": (1, 5)})
        for i, tag in enumerate(tags):
            msp.add_attdef(tag, (i, 2), dxfattribs={"height": H, "layer": "ARQ-SIMB"})
    return dx.extract_dxf(_arquivo(tmp_path, monta))


def test_a_forma_de_nivel_e_o_que_nao_e():
    e_nivel = dx._RE_ETIQUETA_DE_NIVEL.match
    # as formas do acervo, mais o "±" e o "(NO)" da mesma notação
    for t in ("+0.19", "+0,19", "-0.02", "+12,50", "+12.50", "+0.20(NA)", "±0,00", "+0.10(NO)", "-1,250", "+882,70",
              "0.00", "0,0", "0,00", "0.000"):          # o zero vem sem sinal
        assert e_nivel(t), t
    for t in ("-2,00%",                    # inclinação de rampa
              "882,70", "0,15", "0.10", "1.00", "1,0",  # sem sinal e não é zero: confunde com dimensão
              "0", "00.00", "0.0000", "0.00%", "0,00(NA)",
              "+12", "-3", "+0.5",         # sem decimal, ou com um só
              "+1.2345", "+1234.50",       # fora do tamanho de um nível
              "+0.20NA", "+0.20(NB)", "+0.20(NA)x",
              "P+1", "JA-09", "PA6", "1:50", "+0.15x2", "+0.15/+0.20", "N+1", "x+0.15"):
        assert not e_nivel(t), t


def test_a_etiqueta_de_nivel_sai_do_bloco_e_a_secao_diz_que_cortou(tmp_path, monkeypatch):
    monkeypatch.delenv("ATTDEF_SOLTO_E_TEXTO", raising=False)
    ex = _com_etiquetas(tmp_path, ("PA1", "PA1", "+0.19", "+0.19", "+0.19", "-0,02", "+0.20(NA)", "-2,00%", "882,70"))
    linhas = ex.to_structured_prompt().splitlines()
    i = next(k for k, l in enumerate(linhas) if l.startswith("  ETIQUETAS SOLTAS NO DESENHO"))
    assert linhas[i + 4] == "  [ARQ-SIMB]: PA1 ×2; -2,00%; 882,70", linhas[i:i + 6]    # rampa e cota sem sinal ficam
    assert linhas[i + 5:i + 7] == _CORTE
    assert not any(l.startswith("  (") and "NÍVEL" in l and any(c.isdigit() for c in l) for l in linhas)
    # sai só da LISTA: a etiqueta continua nos textos da extração, com a marca
    niveis = [t for t in ex.texts if getattr(t, "de_attdef", False) and dx._RE_ETIQUETA_DE_NIVEL.match(t.text)]
    assert len(niveis) == 5


def test_o_titulo_do_bloco_nao_cita_nivel(tmp_path, monkeypatch):
    monkeypatch.delenv("ATTDEF_SOLTO_E_TEXTO", raising=False)
    linhas = _com_etiquetas(tmp_path, ("PA1", "+0.19")).to_structured_prompt().splitlines()
    i = next(k for k, l in enumerate(linhas) if l.startswith("  ETIQUETAS SOLTAS NO DESENHO"))
    titulo = " ".join(l.strip() for l in linhas[i:i + 4])
    assert "foi explodido — porta, janela, eixo. Lido do arquivo" in titulo, titulo
    assert "nível" not in titulo.lower() and "nivel" not in titulo.lower()
    assert "conta a etiqueta, não a peça" in titulo


def test_arquivo_so_com_nivel_fica_sem_o_bloco_e_com_a_linha_do_corte(tmp_path, monkeypatch):
    """Sem código nenhum pra listar, o cabeçalho do bloco não tem o que
    encabeçar — mas o corte não é calado: as duas linhas dele vêm sozinhas."""
    monkeypatch.delenv("ATTDEF_SOLTO_E_TEXTO", raising=False)
    linhas = _com_etiquetas(tmp_path, ("+0.19", "+0.19", "+2.90", "0,00")).to_structured_prompt().splitlines()
    assert not any("ETIQUETAS SOLTAS" in l for l in linhas)
    assert not any(l.startswith("  [ARQ-SIMB]") for l in linhas)
    assert linhas.count(_CORTE[0]) == 1
    k = linhas.index(_CORTE[0])
    assert linhas[k:k + 2] == _CORTE and k > linhas.index("TEXTOS/LEGENDAS:")


@pytest.mark.parametrize("camadas_com_nivel", [("ARQ-ANOT",), ("ARQ-SIMB",), ("ARQ-ANOT", "ARQ-SIMB")])
def test_o_corte_vale_pra_qualquer_camada_e_sai_uma_vez(tmp_path, monkeypatch, camadas_com_nivel):
    """O nível pode estar só na 1ª camada, só na última ou nas duas: o corte sai,
    uma vez, depois da lista."""
    monkeypatch.delenv("ATTDEF_SOLTO_E_TEXTO", raising=False)

    def monta(doc, msp):
        tags = [("PA1", "ARQ-ANOT"), ("PA2", "ARQ-SIMB")] + [("+0.19", c) for c in camadas_com_nivel]
        for i, (tag, layer) in enumerate(tags):
            msp.add_attdef(tag, (i, 2), dxfattribs={"height": H, "layer": layer})
    linhas = dx.extract_dxf(_arquivo(tmp_path, monta)).to_structured_prompt().splitlines()
    assert linhas.count(_CORTE[0]) == 1, [l for l in linhas if "NÍVEL" in l]
    k = linhas.index(_CORTE[0])
    assert linhas[k - 2:k] == ["  [ARQ-ANOT]: PA1", "  [ARQ-SIMB]: PA2"] and linhas[k:k + 2] == _CORTE


def test_camada_so_de_nivel_nao_ganha_linha(tmp_path, monkeypatch):
    monkeypatch.delenv("ATTDEF_SOLTO_E_TEXTO", raising=False)

    def monta(doc, msp):
        for i, (tag, layer) in enumerate((("+0.19", "ARQ-ANOT"), ("+2.90", "ARQ-ANOT"), ("PA1", "ARQ-SIMB"))):
            msp.add_attdef(tag, (i, 2), dxfattribs={"height": H, "layer": layer})
    linhas = dx.extract_dxf(_arquivo(tmp_path, monta)).to_structured_prompt().splitlines()
    assert not any(l.startswith("  [ARQ-ANOT]") for l in linhas)
    k = linhas.index(_CORTE[0])
    assert linhas[k - 1] == "  [ARQ-SIMB]: PA1"


def test_CONTROLE_sem_etiqueta_de_nivel_nao_ha_linha_de_corte(tmp_path, monkeypatch):
    monkeypatch.delenv("ATTDEF_SOLTO_E_TEXTO", raising=False)
    p = _com_etiquetas(tmp_path, ("PA1", "PA1", "JA-02")).to_structured_prompt()
    assert "de NÍVEL soltas" not in p and "NÃO gere item a partir delas" not in p
    assert "QUADRO COM QUANTIDADE (acima)" not in p


def test_a_lista_de_etiquetas_tem_teto_e_diz_o_que_ficou_de_fora(tmp_path, monkeypatch):
    monkeypatch.delenv("ATTDEF_SOLTO_E_TEXTO", raising=False)
    monkeypatch.setattr(dx, "_TAGS_SOLTAS_MAX", 5)

    def monta(doc, msp):
        msp.add_text("SALA", dxfattribs={"height": H, "layer": "ARQ-TEXTO", "insert": (1, 5)})
        for i in range(8):
            msp.add_attdef("PA%d" % i, (i, 2), dxfattribs={"height": H, "layer": "ARQ-SIMB"})
    linhas = dx.extract_dxf(_arquivo(tmp_path, monta)).to_structured_prompt().splitlines()
    assert "  [ARQ-SIMB]: PA0; PA1; PA2; PA3; PA4 (+3 não listada(s))" in linhas


def test_a_etiqueta_nao_vira_rotulo_de_regiao(tmp_path, monkeypatch):
    """🩸 A/B no acervo: 507 linhas "PA7 → 0,26 m²" em 12 arquivos — a etiqueta
    caía dentro da hachura do próprio símbolo ou do cômodo da porta."""
    monkeypatch.delenv("ATTDEF_SOLTO_E_TEXTO", raising=False)

    def monta(doc, msp):
        for x0, rot in ((0, "COZINHA"), (20, None)):
            h = msp.add_hatch(dxfattribs={"layer": "ARQ-PISO"})
            h.paths.add_polyline_path([(x0, 10), (x0 + 6, 10), (x0 + 6, 15), (x0, 15)], is_closed=True)
            if rot:
                msp.add_text(rot, dxfattribs={"height": H, "layer": "ARQ-TEXTO", "insert": (x0 + 2, 12)})
        msp.add_attdef("PA7", (22, 12), dxfattribs={"height": H, "layer": "ARQ-SIMB"})     # dentro da 2ª hachura
        msp.add_attdef("PA7", (2, 13), dxfattribs={"height": H, "layer": "ARQ-SIMB"})      # e da 1ª, junto do nome
    prompt = dx.extract_dxf(_arquivo(tmp_path, monta)).to_structured_prompt()
    assert '"COZINHA"  →  30.00 m²' in prompt, "o rótulo de verdade continua casando"
    assert '"PA7"  →' not in prompt
    assert "PA7 ×2" in prompt, "a etiqueta continua chegando — no bloco dela"


@pytest.mark.parametrize("como_etiqueta", [True, False])
def test_a_etiqueta_nao_vira_sigla_de_legenda(tmp_path, monkeypatch, como_etiqueta):
    """🩸 A/B no acervo: "PM = JANELAS DE ALUMÍNIO NATURAL" — o código da coluna
    Ref. do quadro (três, um embaixo do outro) virava sigla de legenda e pegava
    a descrição escrita à direita. CONTROLE: a mesma coluna em TEXT continua
    sendo legenda."""
    monkeypatch.delenv("ATTDEF_SOLTO_E_TEXTO", raising=False)
    linhas_do_quadro = [("PM1", "PORTA DE MADEIRA LISA"), ("PM2", "PORTA DE MADEIRA COM VISOR"),
                        ("PM3", "PORTA METALICA DE ABRIR")]

    def monta(doc, msp):
        for i, (cod, nome) in enumerate(linhas_do_quadro):
            y = 8 - i * 3 * H
            if como_etiqueta:
                msp.add_attdef(cod, (2, y), dxfattribs={"height": H, "layer": "ARQ-SIMB"})
            else:
                msp.add_text(cod, dxfattribs={"height": H, "layer": "ARQ-SIMB", "insert": (2, y)})
            msp.add_text(nome, dxfattribs={"height": H, "layer": "ARQ-TEXTO", "insert": (2 + 6 * H, y)})
    prompt = dx.extract_dxf(_arquivo(tmp_path, monta)).to_structured_prompt()
    if como_etiqueta:
        assert "SIGLAS DA LEGENDA" not in prompt and "PM1 = " not in prompt
        assert "  [ARQ-SIMB]: PM1; PM2; PM3" in prompt.splitlines()
    else:
        assert "  PM1 = PORTA DE MADEIRA LISA" in prompt.splitlines(), "o controle: em TEXT é legenda"
