# -*- coding: utf-8 -*-
"""A escala ESCRITA na prancha tem que ser lida antes de pagar Vision.

🩸 23/09/2026 — prancha de estrutura de um cliente (job `f57e3dba`). O log do
motor dizia:

    sem escala (viewport, carimbo nem cota)
      carimbo = indicadas
      vista   = n=6 lidas=[None, None, None, None, None, None]

E a página trazia **`ESC/ 1:50` e `ESC/ 1:25` setenta vezes**, uma por viga
(VT1..VT14, VS1..VS23), cada uma com coordenada própria no PDF.

🔑 O módulo já recortava a vista CERTA. Só que ele renderizava o recorte em
JPEG e perguntava a escala ao Vision — que devolveu `None` nas 6. Pagamos uma
chamada de IA pra adivinhar um dado escrito no arquivo, e erramos.

🪤 O formato era `ESC/ 1:50`, com BARRA. Guarda que exigisse `ESC:` passaria
verde e o cliente continuaria sem medida.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdfvec_escala_por_vista import (  # noqa: E402
    caixa_absoluta,
    escala_do_rotulo,
    escalas_do_texto,
    escala_principal,
    recorte_da_vista,
)

# O texto REAL de uma vista daquela prancha, como o PDF entrega (os tokens
# saem separados por quebra de linha). Nomes de viga são rótulo técnico, não
# dado de cliente.
_VISTA_REAL = (
    "2 N34 ø16.0 C=1196\n37\n423\n28\n2 N35 ø16.0 C=447\n"
    "ESC/ 1:50\nVT1 (20 x 35)\nA\nA\nSEÇÃO A-A\nESC/ 1:25\n35\n20\n14\n29\n"
    "83 N1 ø5.0 C=97\n-484\n"
)


# ══════════════════════════════════════════════════════════════════════════
#  O RÓTULO — a função pura
# ══════════════════════════════════════════════════════════════════════════
def test_le_a_prancha_REAL_que_o_motor_deixou_passar():
    den, fonte = escala_do_rotulo(_VISTA_REAL)
    assert den == 50, (den, fonte)
    assert fonte == "esc"


def test_a_BARRA_depois_de_ESC_e_o_formato_que_nos_pegou():
    assert escala_do_rotulo("ESC/ 1:50")[0] == 50


def test_os_outros_formatos_de_rotulo_que_rodam_por_ai():
    casos = {
        "ESC: 1:50": 50, "ESC 1:100": 100, "esc. 1:25": 25,
        "ESCALA 1:200": 200, "ESCALA: 1/75": 75, "Esc 1/20": 20,
        "ESCALAS 1:125": 125, "ESC.1:150": 150,
    }
    for texto, esperado in casos.items():
        assert escala_do_rotulo(texto)[0] == esperado, texto


def test_quando_a_vista_tem_DUAS_escalas_vence_o_desenho_PRINCIPAL():
    """Elevação 1:50 + seção A-A 1:25 no mesmo recorte: manda a elevação."""
    den, _ = escala_do_rotulo("ESC/ 1:50 VT1 SEÇÃO A-A ESC/ 1:25")
    assert den == 50


def test_a_mais_FREQUENTE_ganha_do_maior():
    den, _ = escala_do_rotulo("ESC/ 1:25 ... ESC/ 1:25 ... ESC/ 1:50")
    assert den == 25


def test_razao_SOLTA_vale_quando_a_vista_inteira_concorda():
    den, fonte = escala_do_rotulo("PLANTA BAIXA\n1:50\nPAVIMENTO TIPO")
    assert den == 50
    assert fonte == "solta"


def test_razao_SOLTA_em_DESACORDO_nao_chuta():
    """Erro de escala multiplica a prancha inteira — regra dura nº1."""
    den, fonte = escala_do_rotulo("1:50 ... 1:25 ... 1:100")
    assert den is None, (den, fonte)
    assert fonte is None


def test_texto_sem_escala_nenhuma_devolve_nada():
    for vazio in (None, "", "PLANTA BAIXA", "2 N34 ø16.0 C=1196", "VT1 (20 x 35)"):
        assert escala_do_rotulo(vazio) == (None, None), vazio


def test_nao_confunde_cota_com_escala():
    """'C=1196' e '20 x 35' são medida de viga, não razão de escala."""
    assert escala_do_rotulo("2 N35 ø16.0 C=447\n35\n20\n14\n29")[0] is None


# ══════════════════════════════════════════════════════════════════════════
#  A GEOMETRIA — o texto sai do MESMO lugar que a imagem sairia
# ══════════════════════════════════════════════════════════════════════════
def test_a_caixa_do_texto_volta_pro_lugar_da_imagem():
    caixa = (0.0, 0.0, 1000.0, 500.0)
    frac = (0.1, 0.2, 0.6, 0.8)
    assert caixa_absoluta(caixa, frac) == (100.0, 100.0, 600.0, 400.0)


def test_a_caixa_respeita_pagina_com_ORIGEM_DESLOCADA():
    """🪤 Há PDF de CAD com a folha centrada na origem — foi o que fez a
    análise de 09/09 ler papel em branco."""
    caixa = (-1192.0, -842.0, 1192.0, 842.0)
    frac = (0.0, 0.0, 1.0, 1.0)
    l, b, r, t = caixa_absoluta(caixa, frac)
    assert (round(l), round(b), round(r), round(t)) == (-1192, -842, 1192, 842)


def test_o_texto_sai_da_MESMA_regiao_que_o_recorte_da_imagem():
    """Se as duas fontes olhassem lugares diferentes, discordariam sem motivo."""
    caixa = (0.0, 0.0, 2000.0, 1000.0)
    bbox = (800.0, 300.0, 1200.0, 700.0)
    frac = recorte_da_vista(caixa, bbox)
    l, b, r, t = caixa_absoluta(caixa, frac)
    assert l == 0.0, "o recorte estende até a margem esquerda; o texto também"
    assert r > 1200.0 and t > 700.0, (l, b, r, t)


# ══════════════════════════════════════════════════════════════════════════
#  A LEITURA POR VISTA — com a página encenada
# ══════════════════════════════════════════════════════════════════════════
class _TextPageFalso:
    def __init__(self, por_regiao):
        self.por_regiao = por_regiao
        self.pedidos = []

    def get_text_bounded(self, l, b, r, t):
        self.pedidos.append((l, b, r, t))
        return self.por_regiao.pop(0) if self.por_regiao else ""


class _PaginaFalsa:
    def __init__(self, por_regiao, explode=False):
        self.tp = _TextPageFalso(list(por_regiao))
        self.explode = explode

    def get_textpage(self):
        if self.explode:
            raise RuntimeError("PDF sem camada de texto")
        return self.tp


def test_le_a_escala_de_cada_vista_sem_tocar_na_rede():
    pag = _PaginaFalsa([_VISTA_REAL, "PLANTA\nESC 1:100", "sem nada aqui"])
    dens, fontes = escalas_do_texto(pag, (0, 0, 100, 100),
                                    [(0, 0, .3, .3), (.3, 0, .6, .3), (.6, 0, 1, .3)])
    assert dens == [50, 100, None]
    assert fontes == ["esc", "esc", None]


def test_prancha_ESCANEADA_nao_quebra_e_devolve_tudo_vazio():
    """Imagem pura não tem texto: o Vision assume, como antes."""
    pag = _PaginaFalsa([], explode=True)
    dens, fontes = escalas_do_texto(pag, (0, 0, 100, 100), [(0, 0, 1, 1)])
    assert dens == [None]
    assert fontes == [None]


def test_a_maior_vista_manda_na_escala_da_prancha():
    """Planta grande 1:50 e detalhe 1:25: quem vale pro quantitativo é a planta."""
    assert escala_principal([25, 50], areas=[100.0, 9000.0]) == 50


# ══════════════════════════════════════════════════════════════════════════
#  CONTROLES — cada um prova que o guarda REPROVA
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_um_padrao_que_exigisse_DOIS_PONTOS_perderia_a_prancha_real():
    """Era exatamente esse o buraco: o arquivo usa ESC/ com BARRA."""
    import re
    so_dois_pontos = re.compile(r"\bESC(?:ALA)?S?\b\s*:\s*1\s*[:/]\s*(\d{1,4})", re.I)
    assert so_dois_pontos.search(_VISTA_REAL) is None, (
        "se este padrão achasse, o controle parou de provar o defeito")
    assert escala_do_rotulo(_VISTA_REAL)[0] == 50, "e o nosso TEM que achar"


def test_CONTROLE_aceitar_razao_solta_em_desacordo_traria_escala_ERRADA():
    """Prova que a salvaguarda da razão solta não é decorativa."""
    texto = "1:50 ... 1:25 ... 1:100"
    import re
    ingenuo = re.compile(r"\b1\s*[:/]\s*(\d{1,4})\b").search(texto)
    assert ingenuo and int(ingenuo.group(1)) == 50, (
        "o ingênuo pegaria a PRIMEIRA razao")
    assert escala_do_rotulo(texto)[0] is None, "o nosso se recusa a chutar"


# ══════════════════════════════════════════════════════════════════════════
#  A ECONOMIA — o Vision só é chamado pelo que o texto NÃO resolveu
# ══════════════════════════════════════════════════════════════════════════
class _DocFalso:
    """Um PDF de mentira com UMA página, que conta o que foi renderizado."""

    def __init__(self, textos):
        self.pagina = _PaginaComRender(textos)
        self.fechado = False

    def __len__(self):
        return 1

    def __getitem__(self, i):
        return self.pagina

    def close(self):
        self.fechado = True


class _PaginaComRender(_PaginaFalsa):
    def __init__(self, textos):
        super().__init__(textos)
        self.renders = 0

    def get_cropbox(self):
        return (0.0, 0.0, 1000.0, 1000.0)

    def get_mediabox(self):
        return self.get_cropbox()

    def get_width(self):
        return 1000.0

    def get_height(self):
        return 1000.0

    def render(self, **k):
        self.renders += 1
        raise AssertionError("render NAO devia rodar pra vista que o texto leu")


class _ClienteQueContaria:
    def __init__(self):
        self.chamadas = 0


def _rodar(monkeypatch, textos, views):
    import pdfvec_escala_por_vista as mod
    doc = _DocFalso(textos)
    monkeypatch.setattr(mod.pdfium, "PdfDocument", lambda *a, **k: doc)
    cli = _ClienteQueContaria()

    def _nao_pode(*a, **k):
        cli.chamadas += 1
        raise AssertionError("call_with_retry NAO devia ser chamado")

    import llm_retry
    monkeypatch.setattr(llm_retry, "call_with_retry", _nao_pode)
    saida = mod.read_view_scales("qualquer.pdf", 0, views=views, _cliente=cli)
    return saida, doc, cli


def test_texto_resolvendo_TUDO_nao_paga_Vision_nem_renderiza(monkeypatch):
    """🎉 O caso que motivou o conserto: zero token, zero imagem."""
    views = [{"bbox": (100.0, 100.0, 400.0, 400.0)},
             {"bbox": (500.0, 100.0, 800.0, 400.0)}]
    saida, doc, cli = _rodar(monkeypatch, [_VISTA_REAL, "CORTE AA\nESC/ 1:25"], views)
    assert saida["por_vista"] == [50, 25], saida
    assert saida["main_scale"] == 50
    assert saida["vision_pediu"] == 0, "pediu Vision tendo o texto na mao"
    assert cli.chamadas == 0
    assert doc.pagina.renders == 0, "renderizou imagem a toa"
    assert saida["fonte_da_escala"] == ["esc", "esc"]
    assert doc.fechado, "o PDF ficou aberto"


def test_o_que_o_texto_NAO_leu_ainda_vai_pro_Vision(monkeypatch):
    """A rede de segurança continua armada — prancha escaneada depende dela."""
    import pdfvec_escala_por_vista as mod
    views = [{"bbox": (100.0, 100.0, 400.0, 400.0)},
             {"bbox": (500.0, 100.0, 800.0, 400.0)}]
    doc = _DocFalso([_VISTA_REAL, "desenho sem rotulo"])
    doc.pagina.render = lambda **k: _BitmapFalso()
    monkeypatch.setattr(mod.pdfium, "PdfDocument", lambda *a, **k: doc)

    vistos = {}

    def _resp(cli, **k):
        vistos["imagens"] = sum(
            1 for c in k["messages"][0]["content"] if c.get("type") == "image")
        return _RespostaFalsa('{"vistas": [{"i": 0, "escala": "1:75"}]}')

    import llm_retry
    monkeypatch.setattr(llm_retry, "call_with_retry", _resp)
    saida = mod.read_view_scales("x.pdf", 0, views=views, _cliente=object())

    assert vistos["imagens"] == 1, "mandou imagem da vista que o texto JA resolveu"
    assert saida["por_vista"] == [50, 75], saida
    assert saida["fonte_da_escala"] == ["esc", "vision"]
    assert saida["vision_pediu"] == 1


def test_Vision_caindo_NAO_joga_fora_o_que_o_texto_leu(monkeypatch):
    """🪤 Antes, um erro aqui devolvia a pagina inteira sem escala."""
    import pdfvec_escala_por_vista as mod
    views = [{"bbox": (100.0, 100.0, 400.0, 400.0)},
             {"bbox": (500.0, 100.0, 800.0, 400.0)}]
    doc = _DocFalso([_VISTA_REAL, "nada"])
    doc.pagina.render = lambda **k: _BitmapFalso()
    monkeypatch.setattr(mod.pdfium, "PdfDocument", lambda *a, **k: doc)

    import llm_retry
    monkeypatch.setattr(llm_retry, "call_with_retry",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("503")))
    saida = mod.read_view_scales("x.pdf", 0, views=views, _cliente=object())

    assert saida["por_vista"][0] == 50, "perdeu a escala que o texto ja tinha"
    assert saida["main_scale"] == 50
    assert "erro" in saida


class _BitmapFalso:
    def to_pil(self):
        from PIL import Image
        return Image.new("RGB", (8, 8), "white")


class _BlocoTexto:
    type = "text"

    def __init__(self, t):
        self.text = t


class _RespostaFalsa:
    def __init__(self, texto):
        self.content = [_BlocoTexto(texto)]


def test_CONTROLE_sem_a_leitura_do_texto_o_Vision_seria_chamado_pelas_DUAS(monkeypatch):
    """Encena o fluxo VELHO: manda todas as vistas, sempre."""
    import pdfvec_escala_por_vista as mod
    views = [{"bbox": (100.0, 100.0, 400.0, 400.0)},
             {"bbox": (500.0, 100.0, 800.0, 400.0)}]
    doc = _DocFalso([_VISTA_REAL, "CORTE AA\nESC/ 1:25"])
    doc.pagina.render = lambda **k: _BitmapFalso()
    monkeypatch.setattr(mod.pdfium, "PdfDocument", lambda *a, **k: doc)
    # o velho nao lia texto: finge que a leitura nunca acha nada
    monkeypatch.setattr(mod, "escalas_do_texto",
                        lambda *a, **k: ([None, None], [None, None]))

    vistos = {}

    def _resp(cli, **k):
        vistos["imagens"] = sum(
            1 for c in k["messages"][0]["content"] if c.get("type") == "image")
        return _RespostaFalsa('{"vistas": []}')

    import llm_retry
    monkeypatch.setattr(llm_retry, "call_with_retry", _resp)
    saida = mod.read_view_scales("x.pdf", 0, views=views, _cliente=object())

    assert vistos["imagens"] == 2, (
        "o controle parou de provar: o fluxo velho mandava as DUAS imagens")
    assert saida["vision_pediu"] == 2
