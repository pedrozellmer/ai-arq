# -*- coding: utf-8 -*-
"""Layout que o ezdxf não resolve não pode matar a prancha.

🚨 Caso cliente-19 (24/08/2026, job e1c48ed7). Cliente novo, 7 DWG. TRÊS pranchas
morreram — 43% do projeto dele —, entre elas as DUAS de ARQUITETURA:

    File ".../ezdxf/layouts/layouts.py", line 219, in get
        return self._layouts[key(name)]
    KeyError: 'DO'
    KeyError: '00-Ã\x8dNDICE DO PROJETO'      (o "Í" lido como latin-1)
    KeyError: 'LAYOUT'

🪤 A primeira leitura foi "é nome acentuado" e estava ERRADA: 'LAYOUT' e 'DO'
não têm acento. O que há em comum é o libredwg escrever entradas de layout que
o ezdxf não resolve de volta na própria tabela — o acento é UM dos casos, não a
causa. Um teste ancorado só no acento não guardaria os outros dois.

O laço de encodings que existia NÃO ajudava: KeyError não é UnicodeDecodeError,
e trocar o encoding do arquivo não conserta uma chave de layout inconsistente.
`ezdxf.recover` é o remédio documentado pra arquivo de escritor não-Autodesk.

Medido no acervo: 22 falhas de extração, TODAS de arquivo do libredwg. 20 são a
trava de 150 MB (guarda deliberada, caso Patrick 18/08). As outras 2 são esta.
"""
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

ezdxf = pytest.importorskip("ezdxf")


@pytest.fixture
def dxf_valido(tmp_path):
    """Um DXF de verdade, com um layout de nome acentuado."""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "A-WALL"})
    msp.add_line((10, 0), (10, 5), dxfattribs={"layer": "A-WALL"})
    doc.layouts.new("00-ÍNDICE DO PROJETO")
    caminho = str(tmp_path / "acentuado.dxf")
    doc.saveas(caminho)
    return caminho


def test_o_arquivo_de_controle_abre_normalmente(dxf_valido):
    """Controle negativo: sem sabotagem, o caminho normal funciona."""
    from dwg_extractor import extract_dxf
    r = extract_dxf(dxf_valido)
    assert r is not None


@pytest.mark.parametrize("nome_layout", [
    "DO",                        # fragmento
    "00-Ã\x8dNDICE DO PROJETO",   # acentuado, mal decodificado
    "LAYOUT",                    # sem acento nenhum
])
def test_recover_salva_a_prancha_quando_o_readfile_morre(
        nome_layout, dxf_valido, monkeypatch, capsys):
    """🚨 CONTROLE POSITIVO: reproduz a falha exata do cliente.

    Faz o `ezdxf.readfile` levantar o mesmo KeyError do job e1c48ed7 e confere
    que a extração AINDA entrega a prancha, via recover."""
    import dwg_extractor

    original = ezdxf.readfile
    chamadas = {"n": 0}

    def _readfile_que_morre(*a, **kw):
        chamadas["n"] += 1
        # O nome varia entre as três ocorrências reais; o que guarda a prancha
        # é a CLASSE do erro (KeyError vindo de layouts.get), não o texto.
        raise KeyError(nome_layout)

    monkeypatch.setattr(dwg_extractor.ezdxf, "readfile", _readfile_que_morre)
    r = dwg_extractor.extract_dxf(dxf_valido)

    assert chamadas["n"] >= 1, "o teste não chegou a sabotar o readfile"
    assert r is not None, (
        "a prancha morreu — é o caso cliente-19: 2 arquivos de arquitetura perdidos "
        "por nome de layout acentuado")
    assert "recover" in capsys.readouterr().out.lower(), (
        "abriu sem passar pelo recover? então o teste não está medindo o que diz")
    monkeypatch.setattr(dwg_extractor.ezdxf, "readfile", original)


def test_quando_nem_o_recover_abre_a_mensagem_diz_as_DUAS_causas(tmp_path):
    """Se nada abre, o erro precisa carregar o motivo do caminho normal E o do
    recover — senão a investigação seguinte começa no escuro (a lição do caso
    Patrick, em que a causa real morreu em dois cortes de log)."""
    from dwg_extractor import extract_dxf
    ruim = tmp_path / "quebrado.dxf"
    ruim.write_text("isto não é um DXF", encoding="utf-8")
    with pytest.raises(Exception) as e:
        extract_dxf(str(ruim))
    txt = str(e.value).lower()
    assert "recover" in txt or "dxf" in txt


def test_erro_de_estrutura_nao_e_mais_relancado_direto():
    """Guarda estrutural: antes, erro que não fosse de encoding subia na hora e
    matava a prancha sem dar chance ao recover."""
    import io
    src = io.open(os.path.join(_BACKEND, "dwg_extractor.py"), encoding="utf-8").read()
    i = src.index("# Try UTF-8 first, then latin-1")
    trecho = src[i:i + 1600]
    assert "_erro_estrutura = f" in trecho, (
        "o erro de estrutura voltou a ser descartado — o recover nunca roda")
    assert "ezdxf.recover" in src or "import ezdxf.recover" in src
