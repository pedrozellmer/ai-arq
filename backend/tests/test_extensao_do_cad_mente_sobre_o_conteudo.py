# -*- coding: utf-8 -*-
"""Um DWG salvo como .dxf tem que ser tratado como DWG — pelo CONTEÚDO, não pelo nome.

🩸 05/09/2026, caso cliente-39 (job 8b7a2b71): engenheiro de orçamento, veio do
Google, subiu HNSC-...-A01-R02.dxf de 5,4 MB. O arquivo começa com `AC1024`:
é um DWG do AutoCAD 2010 com a extensão trocada. A gente decidia o caminho só
pelo nome, jogou o DWG no leitor de DXF e ele morreu ("is not a DXF file");
o cliente leu que o arquivo "foi lido, mas não rendeu nenhum item".
Aí ele anexou o .dwg de verdade — e a regra "DXF supera DWG do mesmo nome"
APAGOU o DWG bom por causa do .dxf que nem era DXF. Duas mordidas do mesmo bug.

Primeira ocorrência em 120 dias de log. Reproduzido aqui com bytes reais.

🧪 Controles positivos no fim: o defeito EXISTE (o ezdxf recusa o DWG
renomeado) e o guarda de cobertura falha quando a chamada some.
"""
import ast
import io
import os
import sys

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import main  # noqa: E402

# Cabeçalhos REAIS: o do cliente-39 (AC1024, 2010) e o de um DWG local (AC1032, 2018).
DWG_2010 = b"AC1024\x00\x00\x00\x00\x00\xe2\x03 \x01\x00\x00!\xe7\x1e\x00\x00" + b"\x00" * 200
DWG_2018 = b"AC1032\x00\x00\x00\x00\x00\x00" + b"\x00" * 200
DXF_ASCII = b"  0\r\nSECTION\r\n  2\r\nHEADER\r\n  9\r\n$ACADVER\r\n  1\r\nAC1027\r\n  0\r\nENDSEC\r\n  0\r\nEOF\r\n"
DXF_COMENTARIO = b"999\r\nexportado pelo QCAD\r\n  0\r\nSECTION\r\n"
DXF_BINARIO = b"AutoCAD Binary DXF\r\n\x1a\x00" + b"\x00" * 50
PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"


def _escreve(tmp_path, nome, conteudo):
    p = tmp_path / nome
    p.write_bytes(conteudo)
    return str(p)


# ══════════════════════════════════════════════════════════════════════════
#  1. O farejo: 'dwg' / 'dxf' / None pelos primeiros bytes
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("conteudo,esperado", [
    (DWG_2010, "dwg"),
    (DWG_2018, "dwg"),
    (DXF_ASCII, "dxf"),
    (DXF_COMENTARIO, "dxf"),
    (DXF_BINARIO, "dxf"),
    (PDF, None),
    (b"", None),
    (b"ACAD nao e assinatura", None),   # 'AC' sozinho não basta — tem que ser AC1 + 3 dígitos
])
def test_o_farejo_le_o_conteudo(tmp_path, conteudo, esperado):
    p = _escreve(tmp_path, "qualquer.bin", conteudo)
    assert main._formato_cad_pelo_conteudo(p) == esperado


def test_arquivo_inexistente_nao_derruba():
    assert main._formato_cad_pelo_conteudo("/nao/existe/x.dxf") is None


# ══════════════════════════════════════════════════════════════════════════
#  2. A normalização: renomeia no disco, avisa o cliente, devolve o mapa
# ══════════════════════════════════════════════════════════════════════════
def test_dwg_com_nome_dxf_vira_dwg_no_disco(tmp_path, monkeypatch):
    logs = []
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: logs.append((a, k)))
    p = _escreve(tmp_path, "HNSC-CADT-ELE-PB-ILU-A01-R02.dxf", DWG_2010)
    novos, avisos, mapa = main._normalizar_extensao_cad([p], "job-x")
    alvo = str(tmp_path / "HNSC-CADT-ELE-PB-ILU-A01-R02.dwg")
    assert novos == [alvo]
    assert os.path.exists(alvo) and not os.path.exists(p), "tem que renomear NO DISCO"
    assert mapa == {p: alvo}
    assert len(avisos) == 1
    assert "DWG" in avisos[0] and "não é defeito do arquivo" in avisos[0]
    assert any(a[0][0] == "motor:extensao-corrigida" for a in logs), "tem que deixar rastro no error_log"


def test_dxf_com_nome_dwg_vira_dxf(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    p = _escreve(tmp_path, "planta.dwg", DXF_ASCII)
    novos, avisos, mapa = main._normalizar_extensao_cad([p], "job-x")
    assert novos == [str(tmp_path / "planta.dxf")] and len(avisos) == 1


def test_arquivo_honesto_nao_e_tocado(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    dxf = _escreve(tmp_path, "ok.dxf", DXF_ASCII)
    dwg = _escreve(tmp_path, "ok2.dwg", DWG_2018)
    pdf = _escreve(tmp_path, "x.pdf", PDF)
    novos, avisos, mapa = main._normalizar_extensao_cad([dxf, dwg, pdf], "job-x")
    assert novos == [dxf, dwg, pdf] and avisos == [] and mapa == {}


def test_colisao_descarta_a_copia_renomeada_e_preserva_o_dwg_bom(tmp_path, monkeypatch):
    """O 2º envio do cliente-39: x.dwg (real) + x.dxf (o mesmo DWG renomeado).
    Sem isto, ou a prancha era medida DUAS vezes, ou — pior, como aconteceu —
    a regra 'DXF supera DWG do mesmo nome' apagava o DWG bom."""
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    dwg = _escreve(tmp_path, "x.dwg", DWG_2010)
    falso = _escreve(tmp_path, "x.dxf", DWG_2010)
    novos, avisos, mapa = main._normalizar_extensao_cad([dwg, falso], "job-x")
    assert novos == [dwg], "só o DWG de verdade segue"
    assert mapa == {falso: None}, "o mapa diz que a cópia foi descartada"
    assert avisos == [], "descarte de duplicata não é aviso pro cliente"
    assert os.path.exists(dwg)


# ══════════════════════════════════════════════════════════════════════════
#  3. Cobertura por NOME: o process_job CHAMA a normalização e USA o mapa
# ══════════════════════════════════════════════════════════════════════════
def _funcao(nome):
    src = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    arvore = ast.parse(src)
    for n in ast.walk(arvore):
        if isinstance(n, ast.FunctionDef) and n.name == nome:
            return n
    raise AssertionError(f"função {nome} sumiu do main.py")


def _chamadas(fn, alvo):
    return [n for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == alvo]


def test_process_job_normaliza_antes_de_decidir_pela_extensao():
    fn = _funcao("process_job")
    chamadas = _chamadas(fn, "_normalizar_extensao_cad")
    assert chamadas, "process_job não chama _normalizar_extensao_cad — o nome volta a decidir o caminho"
    # o resultado tem que ser ATRIBUÍDO a cad_paths (senão a lista velha segue)
    atrib = [n for n in ast.walk(fn) if isinstance(n, ast.Assign)
             and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name)
             and n.value.func.id == "_normalizar_extensao_cad"]
    assert atrib, "a chamada existe mas o retorno é jogado fora"
    nomes = [e.id for t in atrib for e in (t.targets[0].elts if isinstance(t.targets[0], ast.Tuple) else [t.targets[0]])
             if isinstance(e, ast.Name)]
    assert "cad_paths" in nomes, f"o retorno tem que virar cad_paths, virou {nomes}"
    # e o mapa tem que reescrever file_paths (é ele que alimenta a gravação dos originais)
    src_fn = ast.get_source_segment(io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read(), fn)
    assert "_mapa_ext.get(_p, _p)" in src_fn, "file_paths não acompanha a renomeação — a gravação dos originais quebraria"


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLES POSITIVOS
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_o_defeito_existe_o_ezdxf_recusa_o_dwg_renomeado(tmp_path):
    ezdxf = pytest.importorskip("ezdxf")
    p = _escreve(tmp_path, "dwg_renomeado.dxf", DWG_2010)
    with pytest.raises(Exception) as ex:
        ezdxf.readfile(p)
    assert "not a DXF" in str(ex.value) or "DXF" in type(ex.value).__name__


def test_CONTROLE_guarda_de_cobertura_reprova_sem_a_chamada():
    fn = _funcao("process_job")
    # um process_job sem a chamada: removemos os nós e o guarda tem que ficar vazio
    class _Apaga(ast.NodeTransformer):
        def visit_Call(self, node):
            if isinstance(node.func, ast.Name) and node.func.id == "_normalizar_extensao_cad":
                return ast.Constant(value=None)
            return self.generic_visit(node)
    mutado = _Apaga().visit(fn)
    assert not _chamadas(mutado, "_normalizar_extensao_cad"), "o controle está mal montado"


def test_CONTROLE_farejo_reprova_lixo_que_comeca_com_AC():
    # se alguém afrouxar pra `startswith(b"AC")`, 'ACAD...' viraria DWG
    assert main._formato_cad_pelo_conteudo.__code__.co_consts  # função existe
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=".dxf") as f:
        f.write(b"AC abc")
        nome = f.name
    try:
        assert main._formato_cad_pelo_conteudo(nome) is None
    finally:
        os.remove(nome)
