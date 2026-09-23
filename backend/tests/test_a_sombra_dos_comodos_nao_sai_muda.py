# -*- coding: utf-8 -*-
"""A sombra de cômodos não pode sair muda quando não mede nada.

🩸 23/09/2026 — MEDIDO NO ACERVO. A sombra roda desde 31/07. Desde então:

| desde 31/07 | |
|---|---|
| projetos concluídos | 130 |
| **com CAD** | **87** |
| com CAD **e** log da sombra | **18 (20,7%)** |
| com CAD **sem uma linha** | **69** |

Não é que ela falhou nos 69: é que ela saía MUDA. Dois silêncios em sequência
dentro do `_run`:

    if not os.path.exists(path): continue   # pula sem dizer nada
    ...
    if not results: return                  # sai sem registrar

🔑 E a sombra é a fonte que autorizaria ligar a medição de ambiente nas linhas
vazias de piso/forro — o maior conserto da fila. Sem log, não há prova; sem
prova, o conserto fica parado. O silêncio não custava só diagnóstico: custava
a decisão inteira.

🪤 A suspeita que este log existe pra confirmar OU DERRUBAR: a sombra dorme
`ESPERA_S` (10 s) depois do `done`, e o job apaga os `arq_dxf_*` durante o
processamento. Se for isso, os 69 vão aparecer como `arquivo-apagado`.
🚨 Este guarda NÃO afirma que é essa a causa — ele garante que a causa passe a
ser DIZÍVEL. Afirmar antes de medir é o erro que esta casa persegue.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dxf_rooms_shadow import ESPERA_S, diagnostico_do_silencio  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════
#  O DIAGNÓSTICO — função pura, é o que o guarda consegue CHAMAR
# ══════════════════════════════════════════════════════════════════════════
def test_o_caso_dos_69_o_arquivo_sumiu_antes_da_sombra_acordar():
    """O cenário suspeito: pediu 3 DXF, os 3 já tinham sido apagados."""
    d = diagnostico_do_silencio(3, 3, pasta_existe=False)
    assert d["motivo"] == "arquivo-apagado", d
    assert d["pedidos"] == 3
    assert d["sumiram"] == 3
    assert d["pasta_existe"] is False
    assert str(int(ESPERA_S)) in d["explica"], (
        "a explicação tem que dizer quantos segundos ela esperou: " + d["explica"])


def test_parte_apagada_e_um_diagnostico_DIFERENTE():
    """Sobrou arquivo e ainda assim não mediu: a causa é outra."""
    d = diagnostico_do_silencio(4, 2)
    assert d["motivo"] == "parte-apagada", d
    assert d["sumiram"] == 2


def test_arquivos_intactos_e_medicao_vazia_e_o_terceiro_caso():
    """🔑 Aqui o problema é da MONTAGEM, não do arquivo — e é o único dos três
    que aponta pro algoritmo."""
    d = diagnostico_do_silencio(2, 0)
    assert d["motivo"] == "medicao-vazia", d
    assert "estavam la" in d["explica"]


def test_job_sem_DXF_nenhum_nao_vira_alarme_falso():
    """Projeto só de PDF não tem o que a sombra medir — não é defeito."""
    for n in (0, -1):
        d = diagnostico_do_silencio(n, 0)
        assert d["motivo"] == "sem-dxf", (n, d)


def test_os_QUATRO_motivos_sao_distintos_entre_si():
    """Se dois cenários derem o mesmo motivo, o log não separa causa nenhuma."""
    motivos = {
        diagnostico_do_silencio(0, 0)["motivo"],
        diagnostico_do_silencio(3, 3)["motivo"],
        diagnostico_do_silencio(4, 2)["motivo"],
        diagnostico_do_silencio(2, 0)["motivo"],
    }
    assert len(motivos) == 4, motivos


def test_o_diagnostico_cabe_no_log():
    """O log corta em 1000 bytes — diagnóstico truncado não se lê."""
    for args in ((0, 0), (3, 3), (4, 2), (2, 0)):
        bruto = json.dumps(diagnostico_do_silencio(*args), ensure_ascii=False)
        assert len(bruto.encode("utf-8")) < 600, (args, len(bruto))


def test_todo_motivo_vem_com_explicacao_em_portugues():
    for args in ((0, 0), (3, 3), (4, 2), (2, 0)):
        d = diagnostico_do_silencio(*args)
        assert d.get("explica"), args
        assert len(d["explica"]) > 20, d


# ══════════════════════════════════════════════════════════════════════════
#  O CAMINHO INTEIRO — `_run` com o disco encenado
# ══════════════════════════════════════════════════════════════════════════
class _LogFalso:
    def __init__(self):
        self.linhas = []

    def __call__(self, stage, message, job_id=None, severity=None):
        self.linhas.append({"stage": stage, "message": message,
                            "job_id": job_id, "severity": severity})


def _rodar(monkeypatch, caminhos_que_existem, pedidos):
    """Roda `_run` de verdade, com o disco e o relógio encenados."""
    import dxf_rooms_shadow as mod
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(mod.os.path, "exists",
                        lambda p: p in caminhos_que_existem)
    monkeypatch.setattr(mod.os.path, "isdir", lambda p: False)
    log = _LogFalso()
    mod._run([(p, 1.0) for p in pedidos], "job123", log)
    return log


def test_o_RUN_registra_quando_todos_os_arquivos_sumiram(monkeypatch):
    """🩸 Era exatamente aqui que os 69 morriam em silêncio."""
    log = _rodar(monkeypatch, set(), ["/tmp/a.dxf", "/tmp/b.dxf"])
    assert len(log.linhas) == 1, "a sombra saiu MUDA de novo: %s" % log.linhas
    assert log.linhas[0]["stage"] == "dxfrooms:nao-mediu"
    corpo = json.loads(log.linhas[0]["message"])
    assert corpo["motivo"] == "arquivo-apagado", corpo
    assert corpo["sumiram"] == 2
    assert log.linhas[0]["job_id"] == "job123"


def test_o_RUN_leva_EXEMPLOS_do_que_sumiu(monkeypatch):
    """Nome de arquivo é o que deixa conferir a hipótese no caso real."""
    log = _rodar(monkeypatch, set(),
                 ["/tmp/arq_dxf_1/planta.dxf", "/tmp/arq_dxf_2/corte.dxf"])
    corpo = json.loads(log.linhas[0]["message"])
    assert "exemplos" in corpo, corpo
    assert "planta.dxf" in corpo["exemplos"]


def test_job_sem_DXF_nao_gera_linha_de_alarme(monkeypatch):
    """🪤 Projeto só de PDF não pode virar ruído no log."""
    import dxf_rooms_shadow as mod
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    log = _LogFalso()
    mod._run([], "job123", log)
    assert log.linhas == [], log.linhas


def test_um_log_que_EXPLODE_nao_derruba_a_sombra(monkeypatch):
    """A sombra não participa do resultado do cliente — não pode quebrar nada."""
    import dxf_rooms_shadow as mod
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(mod.os.path, "exists", lambda p: False)
    monkeypatch.setattr(mod.os.path, "isdir", lambda p: False)

    def _explode(*a, **k):
        raise RuntimeError("banco fora do ar")

    mod._run([("/tmp/a.dxf", 1.0)], "job123", _explode)   # não pode levantar


# ══════════════════════════════════════════════════════════════════════════
#  CONTROLES — provam que o guarda REPROVA
# ══════════════════════════════════════════════════════════════════════════
def test_CONTROLE_o_return_seco_antigo_nao_registraria_nada(monkeypatch):
    """Encena o código VELHO: dois silêncios em sequência."""
    chamadas = []

    def _velho(dxf_units, job_id, log_fn):
        results = []
        for path, _f in dxf_units:
            if not os.path.exists(path):
                continue          # 1º silêncio
            results.append({"x": 1})
        if not results:
            return                # 2º silêncio
        log_fn("dxfrooms:shadow", "{}", job_id)

    monkeypatch.setattr(os.path, "exists", lambda p: False)
    _velho([("/tmp/a.dxf", 1.0)], "job123", lambda *a, **k: chamadas.append(a))
    assert chamadas == [], (
        "o controle parou de provar: o codigo velho TINHA que sair mudo")


def test_CONTROLE_um_motivo_generico_nao_separaria_os_69(monkeypatch):
    """Se todo silêncio virasse 'nao-mediu' sem motivo, o log não diria nada
    sobre a CAUSA — e a hipótese do arquivo apagado continuaria indecidível."""
    generico = {"motivo": "nao-mediu"}
    assert generico["motivo"] != diagnostico_do_silencio(3, 3)["motivo"], (
        "o nosso tem que distinguir arquivo-apagado de medicao-vazia")
    assert (diagnostico_do_silencio(3, 3)["motivo"]
            != diagnostico_do_silencio(2, 0)["motivo"])
