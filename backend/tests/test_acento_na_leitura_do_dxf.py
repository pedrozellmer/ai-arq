# -*- coding: utf-8 -*-
"""O DXF antigo em cp1252 é lido COM os acentos.

🩸 10/10/2026 — o laço "utf-8, depois latin-1" esperava um UnicodeDecodeError,
mas o padrão do `ezdxf.readfile` é errors="surrogateescape": o byte inválido não
levanta erro, o utf-8 "passava" e o DXF que o cliente envia direto (R2004, R12,
página ANSI_1252) saía sem acento — "TELHA METÁLICA" virava um surrogate solto,
que a limpeza antes da IA apaga. Toda régua por palavra acentuada falhava.
Medido no acervo: 33 de 342 DXF em 9 jobs; num deles, 130 de 403 textos.

🔑 utf-8 ESTRITO → a detecção do ezdxf → latin-1.

🪤 Nomes FICTÍCIOS (repositório público, regra nº6).
"""
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

import dwg_extractor as dx  # noqa: E402

AMBIENTES = ["CIRCULAÇÃO", "DORMITÓRIO", "ESCRITÓRIO", "DEPÓSITO", "SALÃO", "SUÍTE", "ÁREA DE SERVIÇO"]
TRAVESSAO = "FORRO – GESSO"            # "–" é 0x96 no cp1252; no latin-1 o 0x96 é um caractere de controle


def _dxf(tmp_path, versao, textos, nome="planta.dxf"):
    doc = ezdxf.new(versao)
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    for i, t in enumerate(textos):
        msp.add_text(t, dxfattribs={"height": 0.2, "layer": "TEXTO", "insert": (0, -1.0 * i)})
    msp.add_line((0, 5), (10, 5), dxfattribs={"layer": "PAREDE"})
    p = str(tmp_path / nome)
    doc.saveas(p)
    return p


def _utf8_valido(p):
    try:
        open(p, "rb").read().decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _quebrado(s):
    return any(0xDC80 <= ord(c) <= 0xDCFF or c == "�" for c in s)


def _textos(p):
    return [t.text for t in dx.extract_dxf(p).texts]


# ══════════════════════════════════════════════════════════════════════════
#  O caso
# ══════════════════════════════════════════════════════════════════════════
def test_o_caso_dxf_em_cp1252_sai_com_o_acento(tmp_path):
    p = _dxf(tmp_path, "R2000", AMBIENTES + [TRAVESSAO])
    assert not _utf8_valido(p), "o arquivo de teste tem de ter byte que NÃO é utf-8 (cp1252)"
    lidos = _textos(p)
    assert not any(_quebrado(t) for t in lidos), lidos
    for a in AMBIENTES:
        assert a in lidos, (a, lidos)


def test_a_regua_por_palavra_acentuada_volta_a_casar(tmp_path):
    """Sem o acento, "CIRCULAÇÃO" não é nome de ambiente pra régua da planta."""
    lidos = _textos(_dxf(tmp_path, "R2000", AMBIENTES))
    casam = [t for t in lidos if dx._RE_NOME_DE_AMBIENTE.match(t)]
    assert sorted(casam) == sorted(AMBIENTES), casam


def test_o_travessao_do_cp1252_nao_vira_caractere_de_controle(tmp_path):
    """A detecção do ezdxf vem ANTES do latin-1: a página do cabeçalho é cp1252,
    e o latin-1 lê o 0x96 (travessão) como caractere de controle."""
    lidos = _textos(_dxf(tmp_path, "R2000", [TRAVESSAO]))
    assert TRAVESSAO in lidos, [ascii(t) for t in lidos]


def test_a_sondagem_de_unidade_usa_a_mesma_porta(tmp_path, monkeypatch):
    p = _dxf(tmp_path, "R2000", AMBIENTES)
    chamadas = []
    real = dx._ler_dxf_pelos_encodings

    def espiao(f):
        chamadas.append(f)
        return real(f)
    monkeypatch.setattr(dx, "_ler_dxf_pelos_encodings", espiao)
    dx.probe_unit(p)                                  # sem cota: devolve None, mas abre pela porta
    assert chamadas == [os.path.abspath(p)]


# ══════════════════════════════════════════════════════════════════════════
#  CONTROLES — o que fica como era
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_dxf_em_utf8_fica_igual(tmp_path):
    p = _dxf(tmp_path, "R2018", AMBIENTES + [TRAVESSAO])
    assert _utf8_valido(p)
    lidos = _textos(p)
    assert sorted(lidos) == sorted(AMBIENTES + [TRAVESSAO])


def test_CONTROLE_versao_antiga_gravada_em_utf8_sem_declarar(tmp_path):
    """O arquivo R2000 cujos bytes são utf-8 (conversor que não declara): o
    utf-8 estrito, primeiro, lê certo — a página do cabeçalho leria errado."""
    p = _dxf(tmp_path, "R2000", AMBIENTES)
    bruto = open(p, "rb").read().decode("cp1252").encode("utf-8")
    with open(p, "wb") as fh:
        fh.write(bruto)
    assert _utf8_valido(p)
    lidos = _textos(p)
    assert sorted(lidos) == sorted(AMBIENTES), lidos


def _leitor_falso(monkeypatch, respostas):
    """ezdxf.readfile que responde, a cada chamada, a próxima de `respostas`
    (exceção → levanta). Guarda (encoding, errors) de cada chamada."""
    chamadas = []

    def falso(filepath, encoding=None, errors="surrogateescape"):
        chamadas.append((encoding, errors))
        r = respostas[len(chamadas) - 1]
        if isinstance(r, BaseException):
            raise r
        return r
    monkeypatch.setattr(dx.ezdxf, "readfile", falso)
    return chamadas


def _erro_de_decodificacao():
    return UnicodeDecodeError("utf-8", b"\xc1", 0, 1, "invalid start byte")


def test_a_ordem_e_utf8_estrito_deteccao_latin1(monkeypatch):
    chamadas = _leitor_falso(monkeypatch, [_erro_de_decodificacao(), _erro_de_decodificacao(), "DOC"])
    assert dx._ler_dxf_pelos_encodings("x.dxf") == ("DOC", None)
    assert chamadas == [("utf-8", "strict"), (None, "surrogateescape"), ("latin-1", "surrogateescape")]


def test_utf8_valido_abre_na_primeira(monkeypatch):
    chamadas = _leitor_falso(monkeypatch, ["DOC"])
    assert dx._ler_dxf_pelos_encodings("x.dxf") == ("DOC", None)
    assert chamadas == [("utf-8", "strict")]


def test_CONTROLE_erro_de_estrutura_continua_indo_pro_recover(monkeypatch):
    """KeyError de layout não é de encoding: não sobe, fica guardado (o
    extract_dxf chama o recover) — depois de tentar os três, como o laço antigo."""
    chamadas = _leitor_falso(monkeypatch, [KeyError("A"), KeyError("B"), KeyError("LAYOUT")])
    doc, erro = dx._ler_dxf_pelos_encodings("x.dxf")
    assert doc is None and erro == "KeyError: 'LAYOUT'", "o erro guardado é o ÚLTIMO"
    assert [c[0] for c in chamadas] == ["utf-8", None, "latin-1"]


def test_CONTROLE_o_arquivo_que_abria_antes_continua_abrindo(monkeypatch):
    """cp1252 em que a DETECÇÃO tropeça na estrutura: antes o utf-8 tolerante
    abria; agora o utf-8 é estrito e cai pelo acento — o latin-1 (que, como o
    tolerante, nunca falha ao decodificar) ainda tem de abrir."""
    chamadas = _leitor_falso(monkeypatch, [_erro_de_decodificacao(), KeyError("DO"), "DOC"])
    doc, erro = dx._ler_dxf_pelos_encodings("x.dxf")
    assert doc == "DOC" and erro == "KeyError: 'DO'"
    assert [c[0] for c in chamadas] == ["utf-8", None, "latin-1"]


def test_CONTROLE_estrutura_quebrada_no_utf8_e_a_deteccao_abre(monkeypatch):
    chamadas = _leitor_falso(monkeypatch, [KeyError("DO"), "DOC", "NUNCA"])
    doc, erro = dx._ler_dxf_pelos_encodings("x.dxf")
    assert doc == "DOC" and erro == "KeyError: 'DO'"
    assert len(chamadas) == 2, "abriu: não tenta o próximo"


def test_o_extract_chama_o_recover_quando_a_estrutura_quebra(tmp_path, monkeypatch):
    p = _dxf(tmp_path, "R2000", AMBIENTES)
    bom = ezdxf.readfile(p)
    monkeypatch.setattr(dx, "_ler_dxf_pelos_encodings", lambda f: (None, "KeyError: 'LAYOUT'"))
    import dxf_open
    pedidos = []

    def recupera(f, motivo=""):
        pedidos.append(motivo)
        return bom
    monkeypatch.setattr(dxf_open, "recuperar_dxf", recupera)
    ex = dx.extract_dxf(p)
    assert pedidos == ["KeyError: 'LAYOUT'"]
    assert "CIRCULAÇÃO" in [t.text for t in ex.texts]


@pytest.mark.parametrize("versao", ["R12", "R2000", "R2004"])
def test_as_versoes_antigas_que_o_cliente_envia(tmp_path, versao):
    lidos = _textos(_dxf(tmp_path, versao, AMBIENTES, nome="v_%s.dxf" % versao))
    assert sorted(lidos) == sorted(AMBIENTES), lidos
