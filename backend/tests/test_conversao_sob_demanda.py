# -*- coding: utf-8 -*-
"""O /tmp do Render tem 2 GB: a conversão de DWG não pode guardar tudo antes de ler.

🩸 04/11/2026 (job 3e171e10, 24 DWG): os DXF convertidos somados passaram de 2 GB,
o Render despejou a instância, o job voltou, caiu de novo e foi pra quarentena.
🔑 Acima de `_ORCAMENTO_CONVERSAO_MB` convertido no disco, o DWG espera a hora de
ler; e as cópias pro preview têm teto próprio (`_ORCAMENTO_PREVIEW_MB`).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402
import dwg_extractor  # noqa: E402

_MB = 1048576


def _arquivo(pasta, nome, mb):
    os.makedirs(pasta, exist_ok=True)
    caminho = os.path.join(pasta, nome)
    with open(caminho, "wb") as f:
        f.truncate(int(mb * _MB))
    return caminho


def test_so_conta_dxf_de_pasta_de_conversao(tmp_path):
    conv = _arquivo(str(tmp_path / "arq_dxf_abc"), "a.dxf", 3)
    do_cliente = _arquivo(str(tmp_path / "job"), "b.dxf", 5)
    dwg = _arquivo(str(tmp_path / "arq_dxf_def"), "c.dwg", 7)
    sumiu = str(tmp_path / "arq_dxf_xyz" / "d.dxf")
    assert main._mb_convertidos_em_disco([conv, do_cliente, dwg, sumiu, None]) == 3


def test_adia_quando_o_convertido_chega_no_orcamento(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "_ORCAMENTO_CONVERSAO_MB", 4)
    a = _arquivo(str(tmp_path / "arq_dxf_1"), "a.dxf", 3)
    assert main._adia_a_conversao([a]) is False
    b = _arquivo(str(tmp_path / "arq_dxf_2"), "b.dxf", 1)
    assert main._adia_a_conversao([a, b]) is True


def test_o_orcamento_padrao_cabe_no_tmp_de_2gb():
    assert main._ORCAMENTO_CONVERSAO_MB + main._ORCAMENTO_PREVIEW_MB <= 1400


def test_mb_da_pasta(tmp_path):
    _arquivo(str(tmp_path / "p"), "a", 2)
    _arquivo(str(tmp_path / "p" / "sub"), "b", 1)
    assert main._mb_da_pasta(str(tmp_path / "p")) == 3
    assert main._mb_da_pasta(str(tmp_path / "nao-existe")) == 0
    assert main._mb_da_pasta(None) == 0


def _prepara(monkeypatch, devolve):
    logs = []
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: logs.append(a))
    monkeypatch.setattr(dwg_extractor, "convert_dwg_to_dxf", lambda p: devolve)
    monkeypatch.setattr(dwg_extractor, "dwg_has_aec_markers", lambda p: True)
    return logs


def test_converte_na_hora_de_ler_ok(monkeypatch):
    logs = _prepara(monkeypatch, "/tmp/arq_dxf_1/planta.dxf")
    falhas, caminhos, libre = [], [], []
    assert main._converte_na_hora_de_ler("/j/planta.dwg", "j", falhas, caminhos, libre) \
        == "/tmp/arq_dxf_1/planta.dxf"
    assert (falhas, caminhos, libre) == ([], [], [])
    assert logs[0][0] == "motor:conversao-adiada" and "planta.dwg: convertido" in logs[0][1]
    assert "(ok;" in logs[0][1]


def test_converte_na_hora_de_ler_pelo_libredwg(monkeypatch):
    _prepara(monkeypatch, "/tmp/arq_dxf_1/planta_libredwg.dxf")
    libre = []
    main._converte_na_hora_de_ler("/j/planta.dwg", "j", [], [], libre)
    assert libre == ["planta.dwg"]


def test_falha_entra_nas_listas_de_sempre(monkeypatch):
    logs = _prepara(monkeypatch, None)
    falhas, caminhos = [], []
    assert main._converte_na_hora_de_ler("/j/corte.dwg", "j", falhas, caminhos, []) is None
    assert falhas == ["corte.dwg"] and caminhos == ["/j/corte.dwg"]
    assert [l[0] for l in logs] == ["motor:conversao-adiada", "dwg:convert-fail"]
    assert "(falhou;" in logs[0][1] and "AEC" in logs[1][1]


def test_excecao_do_conversor_vira_falha(monkeypatch):
    logs = []
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: logs.append(a))

    def _quebra(p):
        raise RuntimeError("x")
    monkeypatch.setattr(dwg_extractor, "convert_dwg_to_dxf", _quebra)
    falhas = []
    assert main._converte_na_hora_de_ler("/j/x.dwg", "j", falhas, [], []) is None
    assert falhas == ["x.dwg"] and "AEC" not in logs[1][1]


def test_preview_respeita_o_orcamento(tmp_path, monkeypatch):
    logs = []
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: logs.append(a))
    monkeypatch.setattr(main, "_ORCAMENTO_PREVIEW_MB", 5)
    work = str(tmp_path / "job")
    _arquivo(os.path.join(work, "_preview"), "ja.dxf", 3)
    a = _arquivo(str(tmp_path / "arq_dxf_a"), "a.dxf", 1)
    assert main._guarda_dxf_pro_preview(a, work, "j") == os.path.join(work, "_preview", "a.dxf")
    b = _arquivo(str(tmp_path / "arq_dxf_b"), "b.dxf", 2)
    descartadas = set()
    assert main._guarda_dxf_pro_preview(b, work, "j", descartadas) is None
    assert not os.path.exists(b) and descartadas == {b}
    assert "passariam de 5MB" in logs[-1][1]


def _fonte():
    with open(main.__file__, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


def test_o_laco_de_conversao_adia_antes_de_converter():
    f = _fonte()
    i = f.index("                    if ext == 'dwg' and _adia_a_conversao(dxf_paths):\n"
                "                        # 04/11: converte na hora de ler (ver `_ORCAMENTO_CONVERSAO_MB`)\n"
                "                        dxf_paths.append(cad_path)\n"
                "                        _conversao_adiada.add(cad_path)\n"
                "                        continue\n"
                "                    if ext == 'dwg':\n")
    assert i > f.index("for ci, cad_path in enumerate(cad_paths):")
    assert i < f.index("                            dxf_path = convert_dwg_to_dxf(cad_path)\n")


def test_a_leitura_converte_antes_do_checkpoint_e_a_sondagem_pula():
    f = _fonte()
    i = f.index("                    if dxf_path in _conversao_adiada:\n"
                "                        dxf_path = _converte_na_hora_de_ler(\n"
                "                            dxf_path, job_id, dwg_failed, dwg_failed_paths, dwg_via_libredwg)\n"
                "                        if not dxf_path:\n")
    assert i < f.index('_dxf_raw_stem = "dxfck_" + os.path.splitext(os.path.basename(dxf_path))[0]')
    assert i > f.index("for idx, dxf_path in enumerate(dxf_paths):")
    assert "(p for p in dxf_paths if p not in _conversao_adiada)," in f
    assert f.count("_conversao_adiada = set()") == 1


def test_etapa_de_diagnostico():
    assert "motor:conversao-adiada" in main._STAGES_DIAGNOSTICO
