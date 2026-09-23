# -*- coding: utf-8 -*-
"""DXF do libredwg com SORTENTSTABLE torta: o motor abre em vez de desistir.

🩸 23/09/2026 — CLIENTE NOVO, PRIMEIRA TENTATIVA, ZERO ITEM. Job b48999f0:
cadastrou 09:23, subiu 2 DWG às 09:30, informou o pé-direito (4,0 m) — fez
tudo certo. O ODA recusou os dois pela tabela de estilos (o defeito conhecido
desde 14/09), o libredwg assumiu como manda o plano B, e o DXF que ele escreveu
o nosso ezdxf recusou:

    DXFStructureError: Invalid sort handle code 331, expected 5

🪤 E O `recover` TAMBÉM CAIU — primeira vez que os dois degraus da rede
falharam juntos. O cliente recebeu "problema técnico do nosso lado; reprocessar
não resolve" e ficou travado.

🔑 A SORTENTSTABLE é a tabela de ORDEM DE EXIBIÇÃO das entidades no CAD: não
tem geometria, não tem medida, não entra em quantitativo. O libredwg escreve os
pares desemparelhados (dois códigos 331 seguidos, sem o 5 do par) e o ezdxf
recusa em `entities/dxfobj.py: load_table`. Jogar a tabela fora não custa nada
do desenho — e é o 3º degrau de `abrir_dxf`.

🚨 Estes guardas ABREM ARQUIVO DE VERDADE: montam um DXF válido com ezdxf,
injetam a tabela torta como o libredwg escreve, e chamam `abrir_dxf`. O
controle positivo é a GEOMETRIA: o arquivo consertado tem que entregar as
mesmas entidades que o original.
"""
import io
import os
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))

from dxf_open import _dxf_sem_sortentstable, abrir_dxf  # noqa: E402

NL = chr(10)

#: O objeto como o libredwg escreve: dois 331 seguidos, sem o 5 do par.
_SORTENTS_TORTA = NL.join([
    "0", "SORTENTSTABLE", "5", "2AA", "330", "1F",
    "100", "AcDbSortentsTable", "331", "2AB", "331", "2AC"])


def _dxf_bom(tmp_path, nome="bom.dxf"):
    d = ezdxf.new("R2013")
    msp = d.modelspace()
    msp.add_line((0, 0), (10, 0))
    msp.add_lwpolyline([(0, 0), (5, 0), (5, 5), (0, 5), (0, 0)])
    p = str(tmp_path / nome)
    d.saveas(p)
    return p


def _injeta(caminho_bom, destino, bloco=_SORTENTS_TORTA):
    txt = io.open(caminho_bom, encoding="utf-8").read()
    i = txt.rfind(NL.join(["0", "ENDSEC"]))
    assert i > 0, "o DXF de teste mudou de forma"
    io.open(destino, "w", encoding="utf-8", newline=NL).write(
        txt[:i] + bloco + NL + txt[i:])
    return destino


# ── o caso do cliente ──────────────────────────────────────────────────────
def test_CONTROLE_o_arquivo_torto_REALMENTE_quebra_o_ezdxf(tmp_path):
    """🧪 Sem isto, o guarda de baixo passaria por mérito falso — provando que
    abre um arquivo que nunca esteve quebrado."""
    ruim = _injeta(_dxf_bom(tmp_path), str(tmp_path / "ruim.dxf"))
    with pytest.raises(Exception) as e1:
        ezdxf.readfile(ruim)
    assert "sort handle" in str(e1.value)
    import ezdxf.recover as _rec
    with pytest.raises(Exception) as e2:
        _rec.readfile(ruim)
    assert "sort handle" in str(e2.value), (
        "o recover passou a salvar este caso — o 3º degrau virou desnecessário")


def test_o_motor_ABRE_o_arquivo_que_o_ezdxf_recusa(tmp_path):
    ruim = _injeta(_dxf_bom(tmp_path), str(tmp_path / "ruim.dxf"))
    doc = abrir_dxf(ruim)
    assert doc is not None


def test_a_GEOMETRIA_sobrevive_inteira(tmp_path):
    """🔑 O que não pode acontecer é abrir o arquivo perdendo desenho. A
    tabela removida é ordem de exibição; as entidades são as mesmas."""
    bom = _dxf_bom(tmp_path)
    ruim = _injeta(bom, str(tmp_path / "ruim.dxf"))
    esperado = [e.dxftype() for e in ezdxf.readfile(bom).modelspace()]
    obtido = [e.dxftype() for e in abrir_dxf(ruim).modelspace()]
    assert obtido == esperado, (
        "o conserto comeu geometria: esperava %r e veio %r" % (esperado, obtido))


def test_a_tabela_e_contada_ao_ser_removida(tmp_path):
    bom = _dxf_bom(tmp_path)
    ruim = _injeta(bom, str(tmp_path / "ruim.dxf"))
    assert _dxf_sem_sortentstable(ruim, str(tmp_path / "limpo.dxf")) == 1


def test_DUAS_tabelas_tortas_saem_as_duas(tmp_path):
    bom = _dxf_bom(tmp_path)
    ruim = _injeta(bom, str(tmp_path / "ruim2.dxf"),
                   bloco=_SORTENTS_TORTA + NL + _SORTENTS_TORTA)
    assert _dxf_sem_sortentstable(ruim, str(tmp_path / "limpo2.dxf")) == 2
    assert abrir_dxf(ruim) is not None


# ── controles positivos ────────────────────────────────────────────────────
def test_CONTROLE_arquivo_SADIO_nao_e_reescrito(tmp_path):
    """O 3º degrau é caro (reescreve 110 MB nos casos reais) e só pode rodar
    quando os dois primeiros já falharam."""
    bom = _dxf_bom(tmp_path)
    assert abrir_dxf(bom) is not None
    assert not os.path.exists(bom + ".sem_sortents.dxf"), (
        "reescreveu um arquivo que abria normalmente")


def test_CONTROLE_nenhuma_tabela_torta_nao_tira_nada(tmp_path):
    bom = _dxf_bom(tmp_path)
    assert _dxf_sem_sortentstable(bom, str(tmp_path / "igual.dxf")) == 0


def test_CONTROLE_a_palavra_como_VALOR_de_outro_codigo_nao_liga_o_pulo(tmp_path):
    """🪤 A decisão é sempre no marcador de objeto (código 0). Um texto do
    desenho escrito "SORTENTSTABLE" não pode fazer o filtro comer o vizinho."""
    bom = _dxf_bom(tmp_path)
    d = ezdxf.readfile(bom)
    d.modelspace().add_text("SORTENTSTABLE").set_placement((1, 1))
    p = str(tmp_path / "com_texto.dxf")
    d.saveas(p)
    antes = [e.dxftype() for e in ezdxf.readfile(p).modelspace()]
    saida = str(tmp_path / "filtrado.dxf")
    assert _dxf_sem_sortentstable(p, saida) == 0, "pulou por causa de um TEXTO"
    assert [e.dxftype() for e in ezdxf.readfile(saida).modelspace()] == antes


def test_CONTROLE_arquivo_irrecuperavel_continua_LEVANTANDO(tmp_path):
    """A rede não pode virar "abre qualquer coisa": lixo continua sendo erro,
    e a mensagem tem que trazer as causas dos degraus."""
    p = str(tmp_path / "lixo.dxf")
    io.open(p, "w", encoding="utf-8").write("isto não é um DXF" + NL)
    with pytest.raises(RuntimeError) as e:
        abrir_dxf(p)
    assert "normal:" in str(e.value) and "recover:" in str(e.value)


def test_CONTROLE_quando_o_RECOVER_salva_o_3o_degrau_nem_roda(tmp_path,
                                                              monkeypatch):
    """🩸 A sabotagem "reescrever sempre" passou VERDE no guarda de cima:
    forçar o `readfile` a falhar não chega ao 3º degrau, porque o `recover`
    abre antes. O guarda cobria só o caminho normal.

    🔑 Aqui o fato fica ancorado: com o readfile caindo e o recover abrindo, a
    reescrita NÃO pode acontecer — ela custa 110 MB de disco nos casos reais.
    """
    import dxf_open as _mod
    bom = _dxf_bom(tmp_path)
    chamou = {"n": 0}
    real_readfile = _mod.ezdxf.readfile

    def _readfile_que_cai(caminho, *a, **k):
        raise ValueError("forçado: o 1º degrau caiu")

    def _sem_sortents_espiao(origem, destino):
        chamou["n"] += 1
        return _mod._dxf_sem_sortentstable(origem, destino)

    monkeypatch.setattr(_mod.ezdxf, "readfile", _readfile_que_cai)
    monkeypatch.setattr(_mod, "_dxf_sem_sortentstable", _sem_sortents_espiao)
    doc = _mod.abrir_dxf(bom)          # o recover abre o arquivo sadio
    assert doc is not None
    assert chamou["n"] == 0, (
        "o 3º degrau rodou mesmo com o recover tendo aberto o arquivo")
    assert not os.path.exists(bom + ".sem_sortents.dxf")
    monkeypatch.setattr(_mod.ezdxf, "readfile", real_readfile)
