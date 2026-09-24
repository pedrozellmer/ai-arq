# -*- coding: utf-8 -*-
"""O símbolo do AI.arq no conector do Claude (23/09/2026).

Pedro, vendo a lista de conectores com o nosso aparecendo sem marca:
*"não dá pra deixar nosso símbolo?"*

🔑 A causa não era o ícone faltar — era ONDE ele mora. O favicon do AI.arq
está em `ai.arq.br` (GitHub Pages); o conector aponta pro backend, e nem
`ai-arq.onrender.com` nem `api.ai.arq.br` servem favicon (404 nos dois,
medido). Pior: a zona `ai.arq.br` responde **403 pra ClaudeBot**, então
apontar o ícone pra lá seria construir em cima de um bloqueio conhecido.

✅ O caminho certo é o da spec: em 2025-11-25 (a versão que o claude.ai fala
de verdade, medida na prova) `Implementation extends BaseMetadata, Icons`,
então o `serverInfo` anuncia `icons`. E `Icon.src` aceita `data:` URI — o
ícone viaja DENTRO da resposta, sem rota nova, sem DNS e sem Cloudflare.

🪤 O modo de falhar aqui é CALADO: base64 truncado ou trocado não levanta
exceção nenhuma — o ícone simplesmente não aparece, e a gente culparia o
Claude. Por isso o guarda principal DECODIFICA os bytes e confere que são um
PNG de verdade, no tamanho anunciado.
"""
import base64
import os
import struct
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import conector_teste as ct  # noqa: E402

# Assinatura PNG por HEX, de propósito: escrever b"\x89PNG..." num arquivo
# gerado é a armadilha de escape que já custou 16 erros nesta casa.
_ASSINATURA_PNG = bytes.fromhex("89504e470d0a1a0a")
_IHDR = bytes.fromhex("49484452")  # b"IHDR"


def _server_info():
    """O serverInfo como o Claude recebe — executando o initialize de verdade."""
    r = ct._responder({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                       "params": {"protocolVersion": ct.VERSAO_PADRAO}},
                      {"exp": 0}, ct.VERSAO_PADRAO)
    return r["result"]["serverInfo"]


def _png_de(src):
    """data URI -> bytes do PNG. Levanta se não for data URI de PNG."""
    prefixo = "data:image/png;base64,"
    assert src.startswith(prefixo), "src tem que ser data URI de PNG: " + src[:40]
    return base64.b64decode(src[len(prefixo):], validate=True)


def _dimensoes(png):
    """(largura, altura) lidas do IHDR — o cabeçalho obrigatório do PNG."""
    assert png[:8] == _ASSINATURA_PNG, "não tem assinatura de PNG"
    assert png[12:16] == _IHDR, "primeiro chunk não é IHDR"
    return struct.unpack(">II", png[16:24])


# ══════════════════════════════════════════════════════════════════════════
#  O ANÚNCIO
# ══════════════════════════════════════════════════════════════════════════
def test_o_serverinfo_anuncia_pelo_menos_um_icone():
    icones = _server_info().get("icons")
    assert isinstance(icones, list) and icones, "serverInfo sem `icons`"


def test_TODO_icone_e_um_PNG_DE_VERDADE():
    """🩸 O guarda que importa: base64 truncado não dá erro, só some o ícone.
    Percorre TODOS — validar só o primeiro deixaria o segundo sem guarda."""
    for i, ic in enumerate(_server_info()["icons"]):
        larg, alt = _dimensoes(_png_de(ic["src"]))
        assert larg > 0 and alt > 0, (i, larg, alt)


def test_o_tamanho_ANUNCIADO_bate_com_o_PNG_em_TODOS():
    """Anunciar um tamanho e mandar outro faz o cliente escalar errado."""
    for ic in _server_info()["icons"]:
        larg, alt = _dimensoes(_png_de(ic["src"]))
        assert ic.get("sizes") == ["%dx%d" % (larg, alt)], (ic.get("sizes"), larg, alt)


def test_tem_um_PEQUENO_e_um_GRANDE():
    """🪤 O nome "AI.Arq" só cabe no grande: em 32x32 teria ~4 px de altura.
    Por isso são dois — um tamanho só obrigaria a escolher entre ilegível
    (nome espremido) e pobre (sem nome onde cabia)."""
    lados = sorted(_dimensoes(_png_de(ic["src"]))[0]
                   for ic in _server_info()["icons"])
    assert len(lados) >= 2, lados
    assert lados[0] <= 32, "falta um ícone pequeno de verdade: %s" % lados
    assert lados[-1] >= 64, "falta um ícone grande o bastante pro nome: %s" % lados


def test_o_mimetype_anunciado_bate_com_os_bytes():
    for ic in _server_info()["icons"]:
        assert ic.get("mimeType") == "image/png"
        assert _png_de(ic["src"])[:8] == _ASSINATURA_PNG


def test_nenhum_icone_depende_de_rede():
    """🔑 O motivo de ser `data:` — a zona ai.arq.br bloqueia crawler de treino
    e os hosts do backend não servem favicon. URL aqui seria defeito conhecido."""
    for ic in _server_info()["icons"]:
        src = ic["src"]
        assert src.startswith("data:"), src[:60]
        for proibido in ("ai.arq.br", "onrender.com", "http://", "https://"):
            assert proibido not in src, proibido


def test_os_icones_nao_estouram_o_initialize():
    """🪤 O ícone viaja em TODA conexão. O 256x256 pesava 11 KB de base64 e foi
    trocado pelo 128 por isso. Teto pra não voltar a crescer sem querer."""
    total = sum(len(ic["src"]) for ic in _server_info()["icons"])
    assert total < 12000, "ícones somam %d chars — pesado pra cada initialize" % total


def test_o_site_do_servidor_e_o_nosso_e_por_https():
    site = _server_info().get("websiteUrl", "")
    assert site.startswith("https://"), site
    assert "ai.arq.br" in site, site


# ══════════════════════════════════════════════════════════════════════════
#  A DESCRIÇÃO — é texto que o cliente lê
# ══════════════════════════════════════════════════════════════════════════
def test_a_descricao_diz_que_e_TESTE_e_que_nao_le_dado():
    """Regra dura nº1 aplicada ao texto: a prova não lê projeto de ninguém, e
    quem instala tem que ler isso ANTES de conectar."""
    d = (_server_info().get("description") or "").lower()
    assert "teste" in d, d
    assert "nao le" in d or "não lê" in d, d


def test_a_descricao_nao_promete_o_que_a_prova_nao_faz():
    """A prova NÃO lista projeto nem mede nada — prometer isso na vitrine é a
    mesma falha de 'mande a prancha e eu detalho', de hoje mais cedo."""
    d = (_server_info().get("description") or "").lower()
    for promessa in ("orcamento", "orçamento", "preco", "preço", "sinapi"):
        assert promessa not in d, promessa


# ══════════════════════════════════════════════════════════════════════════
#  CONTROLES — todo guarda prova que REPROVA
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_base64_truncado_seria_reprovado(monkeypatch):
    """Se o ícone chegasse cortado, o guarda do PNG tem que pegar."""
    cortado = ct._ICONE_B64[: len(ct._ICONE_B64) // 2]
    monkeypatch.setattr(ct, "_ICONES",
                        [{"src": "data:image/png;base64," + cortado,
                          "mimeType": "image/png", "sizes": ["32x32"]}])
    with pytest.raises(Exception):
        _dimensoes(_png_de(_server_info()["icons"][0]["src"]))


def test_CONTROLE_tamanho_mentido_seria_reprovado(monkeypatch):
    ic = dict(_server_info()["icons"][0])
    ic["sizes"] = ["512x512"]          # o PNG é 32x32
    monkeypatch.setattr(ct, "_ICONES", [ic])
    larg, alt = _dimensoes(_png_de(_server_info()["icons"][0]["src"]))
    assert _server_info()["icons"][0]["sizes"] != ["%dx%d" % (larg, alt)], (
        "o controle parou de provar: o tamanho mentido passou")


def test_CONTROLE_so_o_pequeno_seria_reprovado(monkeypatch):
    """Prova que o guarda do par pega se alguém apagar o ícone grande."""
    monkeypatch.setattr(ct, "_ICONES", [_server_info()["icons"][0]])
    lados = sorted(_dimensoes(_png_de(ic["src"]))[0]
                   for ic in _server_info()["icons"])
    assert not (len(lados) >= 2 and lados[-1] >= 64), (
        "o controle parou de provar: sobreviveu com um ícone só")


def test_CONTROLE_sem_icones_o_guarda_principal_cai(monkeypatch):
    monkeypatch.setattr(ct, "_ICONES", [])
    assert not _server_info().get("icons"), (
        "o controle parou de provar: `icons` sobreviveu à lista vazia")
