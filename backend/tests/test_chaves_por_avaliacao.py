# -*- coding: utf-8 -*-
"""A avaliação isolada liga ou desliga chaves do extrator SÓ PRA ELA.

🩸 11/10/2026 — a seção AMBIENTE ↔ ÁREA ESCRITA subiu ligada com teste, mutação,
A/B de prompt em 129 arquivos e bancada verdes, e a 1ª planilha de verdade
trocou 18 linhas de piso por uma de 491 m² (um total que a seção listava). O que
a IA faz com um texto novo só a avaliação isolada mede — e ela só via a seção
com a chave ligada pra todo cliente.

🔑 A extração roda num subprocesso por prancha, e é nele que a chave é lida:
`?chaves=NOME=1` na rota de avaliação põe a chave no ambiente DO FILHO daquele
job. Job de cliente nunca ganha ambiente próprio.
"""
import io
import os
import subprocess
import sys

import ezdxf
import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_AQUI)
sys.path.insert(0, _BACKEND)

import main  # noqa: E402

SECAO = "AMBIENTE ↔ ÁREA ESCRITA"


@pytest.fixture(autouse=True)
def _limpa(monkeypatch):
    monkeypatch.setattr(main, "_CHAVES_DA_AVALIACAO", {})
    logs = []
    monkeypatch.setattr(main, "_log_error", lambda etapa, msg, *a, **k: logs.append((etapa, msg)))
    return logs


# ── o que a rota aceita ──────────────────────────────────────────────────────
@pytest.mark.parametrize("texto, esperado", [
    ("", {}), (None, {}), ("  ", {}),
    ("AMBIENTE_AREA_ESCRITA=1", {"AMBIENTE_AREA_ESCRITA": "1"}),
    ("ambiente_area_escrita=1", {"AMBIENTE_AREA_ESCRITA": "1"}),
    ("AMBIENTE_AREA_ESCRITA=1,ATTDEF_SOLTO_E_TEXTO=0", {"AMBIENTE_AREA_ESCRITA": "1", "ATTDEF_SOLTO_E_TEXTO": "0"}),
    (" QUADRO_COM_QUANTIDADE = 1 ; LEITURA_POR_FOLHA = 0 ,", {"QUADRO_COM_QUANTIDADE": "1", "LEITURA_POR_FOLHA": "0"}),
])
def test_as_chaves_pedidas(texto, esperado):
    assert main._chaves_pedidas(texto) == esperado


@pytest.mark.parametrize("texto", [
    "AMBIENTE_AREA_ESCRITA",              # sem valor
    "AMBIENTE_AREA_ESCRITA=sim",          # valor que não é 0/1
    "AMBIENTE_AREA_ESCRITA=2",
    "AMBIENTE_AREA_ESCRIT=1",             # digitada errado: rodaria SEM ela e pareceria ter rodado com
    "ANTHROPIC_API_KEY=1",                # não é chave do extrator
    "PATH=1", "DXF_EXTRACT_MEM_MB=1",
    "AMBIENTE_AREA_ESCRITA=1,OUTRA=1",    # uma boa não salva a ruim
])
def test_CONTROLE_chave_torta_ou_desconhecida_e_recusada(texto):
    with pytest.raises(ValueError):
        main._chaves_pedidas(texto)


def test_so_chave_do_extrator_e_avaliavel():
    """Toda chave avaliável é LIDA no extrator (ou num ramo que já a declara), na forma
    `os.environ.get("NOME", …)`: chave que ninguém lê seria avaliação de nada."""
    fonte = io.open(os.path.join(_BACKEND, "dwg_extractor.py"), encoding="utf-8").read()
    lidas = {k for k in main._CHAVES_AVALIAVEIS if 'os.environ.get("%s"' % k in fonte}
    # 18/10: chave que o PRÓPRIO process_job lê (depois da IA) passa por
    # `_chave_do_job`, que respeita a avaliação — também é lida
    fonte_main = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    lidas |= {k for k in main._CHAVES_AVALIAVEIS if '_chave_do_job(job_id, "%s")' % k in fonte_main}
    ainda_em_ramo = {"ATTDEF_SOLTO_E_TEXTO", "QUADRO_COM_QUANTIDADE", "LEGENDA_PELA_FORMA"}
    assert main._CHAVES_AVALIAVEIS - lidas <= ainda_em_ramo, main._CHAVES_AVALIAVEIS - lidas
    assert "AMBIENTE_AREA_ESCRITA" in lidas and "LEITURA_POR_FOLHA" in lidas


# ── de quem é o ambiente próprio ─────────────────────────────────────────────
def test_job_de_cliente_nunca_tem_ambiente_proprio():
    main._CHAVES_DA_AVALIACAO["a1b2c3d4"] = {"AMBIENTE_AREA_ESCRITA": "1"}     # não deveria existir: e mesmo assim
    assert main._env_da_extracao("a1b2c3d4") is None
    assert main._env_da_extracao("") is None and main._env_da_extracao(None) is None


def test_avaliacao_sem_chaves_herda_o_servidor():
    assert main._env_da_extracao("evabc123") is None


def test_avaliacao_com_chaves_leva_o_servidor_mais_as_dela(monkeypatch):
    monkeypatch.setenv("AMBIENTE_AREA_ESCRITA", "0")
    monkeypatch.setenv("UMA_DO_SERVIDOR", "fica")
    main._CHAVES_DA_AVALIACAO["evabc123"] = {"AMBIENTE_AREA_ESCRITA": "1"}
    env = main._env_da_extracao("evabc123")
    assert env["AMBIENTE_AREA_ESCRITA"] == "1" and env["UMA_DO_SERVIDOR"] == "fica"
    assert os.environ["AMBIENTE_AREA_ESCRITA"] == "0", "o ambiente do SERVIDOR não muda"
    assert main._env_da_extracao("evoutra1") is None, "a chave é de UMA avaliação"


# ── o ambiente chega ao subprocesso ──────────────────────────────────────────
class _Falhou:
    returncode, stderr, stdout = 1, b"", b""


def _espia_run(monkeypatch):
    visto = {}

    def falso(cmd, **kw):
        visto["kw"] = kw
        return _Falhou()
    monkeypatch.setattr(subprocess, "run", falso)
    return visto


def test_o_filho_da_avaliacao_recebe_o_ambiente_dela(monkeypatch):
    visto = _espia_run(monkeypatch)
    main._CHAVES_DA_AVALIACAO["evabc123"] = {"AMBIENTE_AREA_ESCRITA": "1"}
    with pytest.raises(RuntimeError):
        main._extract_dxf_isolated("nao_existe.dxf", None, job_id="evabc123")
    assert visto["kw"]["env"]["AMBIENTE_AREA_ESCRITA"] == "1"


def test_CONTROLE_o_filho_do_cliente_herda_o_servidor(monkeypatch):
    visto = _espia_run(monkeypatch)
    main._CHAVES_DA_AVALIACAO["evabc123"] = {"AMBIENTE_AREA_ESCRITA": "1"}
    with pytest.raises(RuntimeError):
        main._extract_dxf_isolated("nao_existe.dxf", None, job_id="a1b2c3d4")
    assert "env" not in visto["kw"], "job de cliente: o subprocesso herda o ambiente, sem nada por cima"


def test_no_caminho_in_process_a_chave_nao_vale_e_isso_fica_no_log(monkeypatch, _limpa):
    """O in-process lê a chave do SERVIDOR. A avaliação que cai nele roda sem as chaves dela —
    e tem de dizer, senão o resultado se lê como "rodou com a seção"."""
    def nao_lanca(cmd, **kw):
        raise OSError("sem subprocesso aqui")
    monkeypatch.setattr(subprocess, "run", nao_lanca)
    monkeypatch.setattr(main, "_extract_dxf_inprocess", lambda *a, **k: ("ext", "texto", "caminho"))
    main._CHAVES_DA_AVALIACAO["evabc123"] = {"AMBIENTE_AREA_ESCRITA": "1"}
    assert main._extract_dxf_isolated("p.dxf", None, job_id="evabc123") == ("ext", "texto", "caminho")
    assert [e for e, m in _limpa if e == "admin:filhote" and "NÃO aplicadas" in m], _limpa
    _limpa.clear()
    assert main._extract_dxf_isolated("p.dxf", None, job_id="a1b2c3d4") == ("ext", "texto", "caminho")
    assert not _limpa, "job de cliente não tem chave própria: nada a avisar"


# ── de verdade: o worker lê a chave do ambiente que recebeu ──────────────────
def _planta(tmp_path):
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 4
    msp = doc.modelspace()
    msp.add_text("SALA DE ESTAR", dxfattribs={"height": 100, "insert": (0, 300)})
    msp.add_text("A = 12,30 m²", dxfattribs={"height": 100, "insert": (0, 0)})
    msp.add_line((0, -500), (5000, -500))
    p = str(tmp_path / "planta.dxf")
    doc.saveas(p)
    return p


@pytest.mark.parametrize("servidor, da_avaliacao, job, tem_secao", [
    ("0", {"AMBIENTE_AREA_ESCRITA": "1"}, "evabc123", True),    # o caso: desligada pra todos, ligada na avaliação
    ("0", {}, "evabc123", False),                               # avaliação sem chave = como o cliente
    ("0", {"AMBIENTE_AREA_ESCRITA": "1"}, "a1b2c3d4", False),   # cliente NUNCA
    ("1", {"AMBIENTE_AREA_ESCRITA": "0"}, "evabc123", False),   # e o inverso: ligada pra todos, desligada na avaliação
    ("1", {}, "a1b2c3d4", True),
])
def test_a_chave_da_avaliacao_decide_so_o_prompt_dela(tmp_path, monkeypatch, servidor, da_avaliacao, job, tem_secao):
    monkeypatch.setenv("AMBIENTE_AREA_ESCRITA", servidor)
    if da_avaliacao:
        main._CHAVES_DA_AVALIACAO["evabc123"] = dict(da_avaliacao)
    _ext, texto, _p = main._extract_dxf_isolated(_planta(tmp_path), None, job_id=job)
    assert (SECAO in texto) is tem_secao


# ── a rota ───────────────────────────────────────────────────────────────────
def test_a_rota_recusa_antes_de_criar_e_registra_antes_de_disparar():
    fonte = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    i = fonte.index("def admin_eval_reprocess(")
    rota = fonte[i:fonte.index("\ndef ", i + 10)]
    assert "chaves: Optional[str] = None" in rota[:rota.index('"""')], "?chaves= é parâmetro da rota, como o project_type"
    le, recusa = rota.index("_chaves_pedidas(chaves)"), rota.index("raise HTTPException(400, str(_ech))")
    cria = rota.index('eval_job_id = "ev"')
    registra = rota.index("_CHAVES_DA_AVALIACAO[eval_job_id] = dict(_chaves_eval)")
    dispara = rota.index("target=_process_job_throttled")
    assert le < recusa < cria < registra < dispara
    assert '"chaves": dict(_chaves_eval)' in rota, "a resposta diz com que chaves a avaliação rodou"
    assert " — avaliação\"" in rota and "sorted(_chaves_eval.items())" in rota, "e o nome do projeto também"
