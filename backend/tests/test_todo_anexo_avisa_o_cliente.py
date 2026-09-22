# -*- coding: utf-8 -*-
"""Todo anexo que termina de processar avisa o cliente por e-mail.

🩸 21/09/2026 — job 7b60c43b, projeto elétrico em DWG, cliente de primeiro dia.
O 1º aviso ("planilha pronta") saiu às 12:54. A pessoa baixou a planilha às
13:17, anexou um PDF de detalhe, e a planilha nova ficou pronta 29,5 minutos
depois do 1º aviso — e o e-mail NÃO saiu:

    email:aviso-de-fim-ja-saiu — pulei o aviso de fim: a família 7b60c43b já
    avisou este cliente há menos de 30 min

Pedro, no mesmo dia: *"tem que receber e-mail em todos"*.

POR QUE ANEXO FICAVA SEM AVISO — a causa de cada caso (revisão adversarial de
21/09, cruzando os 25 alertas "Cliente anexou arquivo" do Gmail com os logs):
  1. a janela de 30 min da FAMÍLIA (16/09) segurava também o anexo — é o caso
     7b60c43b. O comentário do próprio ramo prometia o contrário ("Email
     PRÓPRIO (não cai no dedup dos outros)… SEMPRE notifica");
  2. a RETOMADA depois de um reinício perdia o `is_complement` e o fim caía na
     janela da família ou na trava vitalícia do reprocesso (e ainda APAGAVA a
     planilha-base) — ver test_a_retomada_nao_apaga_o_anexo.py;
  3. anexo que não abria ou rendia 0 item saía por `return` ANTES do e-mail —
     8b7a2b71, 05/09, 3 anexos — ver test_o_anexo_que_nao_mudou_nada_avisa.py.
  A trava `ref=job_id` "pra sempre" também estava errada, mas pelos dados nunca
  chegou a calar ninguém — era latente.

🔑 O anexo tem trava PRÓPRIA, por PEDIDO: `job_id:anexo_em_curso`, o id que a
rota grava junto com o status. Ela só segura o MESMO pedido terminando duas
vezes (janela de 30 min). 🩸 A 1ª versão deste conserto (não subiu) usava os
nomes dos arquivos PROCESSADOS — e com CAD no projeto a rota manda só os CADs:
dois PDFs diferentes anexados davam a mesma chave. Os nomes ficam só de
reserva, pra rodada sem marca.

🪤 Executa a fatia REAL do fim do `process_job` (tests/_fim_do_job.py), com
rede e SMTP injetados. Ler o fonte não prova nada aqui: a condição que
calava o e-mail era uma palavra (`not _ja_avisado`) numa linha longa.
"""
import os
import sys
import urllib.request


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import main  # noqa: E402
from _fim_do_job import roda_ate_o_email  # noqa: E402

_EMAIL = "cliente-nn@example.com"


class _Item(object):
    def __init__(self, confidence="estimado"):
        self.description = "piso ceramico"
        self.unit = "m2"
        self.quantity = 10.0
        self.confidence = confidence
        self.discipline = "Pisos"
        self.origem = "ia"


def _janela(familia_avisou=False, rodada_avisou=False, chamadas=None, minutos_vistos=None):
    """Dublê de `_aviso_de_fim_recente` que responde POR TIPO de aviso.

    🪤 `**k` de propósito (feedback: dublê com assinatura exata desarma calado
    quando nasce parâmetro novo)."""
    def _f(email, ref, minutos=30, kind="fim_de_job", **k):
        if chamadas is not None:
            chamadas.append((kind, ref))
        if minutos_vistos is not None:
            minutos_vistos.append((kind, minutos))
        if kind == "complemento_pronto":
            return rodada_avisou
        return familia_avisou
    return _f


def _fim(*, is_complement, familia_avisou=False, rodada_avisou=False,
         n_pdf=0, n_cad=1, exige_email=True, job_id="job-anexo",
         anexo_em_curso=None, envio_ok=True, minutos_vistos=None,
         anexados=None, done_grava=True):
    registros, chamadas = [], []
    extra = {
        "_aviso_de_fim_recente": _janela(familia_avisou, rodada_avisou, chamadas,
                                         minutos_vistos),
        "_email_auto_registrar":
            lambda mail, kind, ref="", **k: registros.append((kind, ref)),
    }
    if not envio_ok:
        # o envio FALHA (SMTP fora): nada pode ser registrado como avisado
        extra["_send_email_smtp"] = lambda *a, **k: False
    diario = roda_ate_o_email(
        [_Item(), _Item("confirmado")], is_complement=is_complement,
        n_pdf=n_pdf, n_cad=n_cad, email=_EMAIL, job_id=job_id,
        exige_email=exige_email, anexo_em_curso=anexo_em_curso,
        anexados=anexados, done_grava=done_grava,
        antes_do_email=extra)
    return diario, registros, chamadas


# ── o caso ────────────────────────────────────────────────────────────────
def test_o_ANEXO_avisa_mesmo_com_a_familia_avisada_ha_pouco():
    """🚨 O caso do job 7b60c43b: a família tinha avisado há 29,5 min."""
    diario, _reg, _ch = _fim(is_complement=True, familia_avisou=True)
    assert diario["emails"], "o anexo terminou e o cliente não foi avisado"
    assert diario["emails"][-1]["kind"] == "complemento_pronto", diario["emails"][-1]["kind"]
    assert not any("aviso-de-fim-ja-saiu" in l for l in diario["logs"]), (
        "o log diz que pulou o aviso, e o aviso saiu: %r" % diario["logs"])


def test_CONTROLE_projeto_sem_anexo_continua_respeitando_a_familia():
    """A regra de 16/09 fica: projeto que termina duas vezes pela mesma causa
    (varredura + reprocesso) não manda dois avisos."""
    diario, _reg, _ch = _fim(is_complement=False, familia_avisou=True,
                             exige_email=False)
    assert diario["emails"] == [], diario["emails"]
    assert any("aviso-de-fim-ja-saiu" in l for l in diario["logs"]), diario["logs"]


def test_a_MESMA_rodada_terminando_duas_vezes_nao_manda_dois():
    diario, _reg, _ch = _fim(is_complement=True, rodada_avisou=True,
                             exige_email=False)
    assert diario["emails"] == [], (
        "a mesma rodada de anexo mandou o aviso duas vezes: %r" % diario["emails"])
    assert any("anexo-ja-avisado" in l for l in diario["logs"]), (
        "segurou o e-mail sem deixar rastro: %r" % diario["logs"])


# ── a chave é a RODADA ────────────────────────────────────────────────────
def _ref_registrada(**kw):
    _d, registros, _ch = _fim(is_complement=True, **kw)
    refs = [r for (k, r) in registros if k == "complemento_pronto"]
    assert len(refs) == 1, registros
    return refs[0]


def test_a_chave_e_o_PROJETO_mais_os_ARQUIVOS_da_rodada():
    r1 = _ref_registrada(n_cad=1)
    r2 = _ref_registrada(n_cad=2)
    assert r1.startswith("job-anexo:") and r2.startswith("job-anexo:"), (r1, r2)
    assert r1 != r2, (
        "dois anexos com arquivos diferentes caem na mesma chave — o 2º nunca "
        "seria avisado (o defeito do `ref=job_id`)")


def test_a_chave_e_estavel_pra_mesma_rodada():
    assert _ref_registrada(n_cad=2) == _ref_registrada(n_cad=2)


def test_a_chave_NAO_e_mais_so_o_job():
    """🩸 `ref=job_id` segurava pra sempre qualquer anexo seguinte."""
    assert _ref_registrada(n_cad=1) != "job-anexo"


def test_a_janela_da_rodada_e_consultada_com_a_MESMA_chave_que_registra():
    diario, registros, chamadas = _fim(is_complement=True)
    ref = [r for (k, r) in registros if k == "complemento_pronto"][0]
    assert ("complemento_pronto", ref) in chamadas, (
        "a trava consulta uma chave e o registro grava outra — ela nunca "
        "acharia a rodada anterior: consultou %r, gravou %r" % (chamadas, ref))


def test_o_anexo_deixa_a_ficha_da_FAMILIA_pra_varredura_nao_duplicar():
    """O anexo avisado grava a ficha `fim_de_job` da família (a raiz).
    🪤 Isto prova a CHAMADA, não o efeito: `email_auto_log` tem UNIQUE(email,
    kind, ref), então se a família já tinha ficha o banco recusa a nova e a
    janela de 30 min segue contando da PRIMEIRA (revisão de 21/09)."""
    _d, registros, _ch = _fim(is_complement=True)
    assert ("fim_de_job", "job-anexo") in registros, registros


# ── a consulta real ───────────────────────────────────────────────────────
class _Resp(object):
    def __init__(self, corpo):
        self._c = corpo

    def read(self):
        return self._c

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_a_consulta_filtra_pelo_TIPO_pedido(monkeypatch):
    urls = []

    def _abre(req, **k):
        urls.append(req.full_url if hasattr(req, "full_url") else str(req))
        return _Resp(b"[]")
    monkeypatch.setattr(urllib.request, "urlopen", _abre)
    assert main._aviso_de_fim_recente(_EMAIL, "job-x:abc", kind="complemento_pronto") is False
    assert urls and "kind=eq.complemento_pronto" in urls[0], urls
    assert "ref=eq.job-x%3Aabc" in urls[0] or "ref=eq.job-x:abc" in urls[0], urls
    assert "sent_at=gte." in urls[0], urls


def test_CONTROLE_sem_tipo_continua_sendo_o_fim_de_job(monkeypatch):
    urls = []
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, **k: urls.append(req.full_url) or _Resp(b"[]"))
    main._aviso_de_fim_recente(_EMAIL, "job-x")
    assert "kind=eq.fim_de_job" in urls[0], urls


def test_na_duvida_o_aviso_do_ANEXO_sai(monkeypatch):
    def _explode(*a, **k):
        raise RuntimeError("banco fora do ar")
    monkeypatch.setattr(urllib.request, "urlopen", _explode)
    assert main._aviso_de_fim_recente(_EMAIL, "job-x:abc", kind="complemento_pronto") is False


# ── 21/09 (2ª versão): a chave é o PEDIDO de anexo ─────────────────────────
def test_com_a_marca_a_chave_e_o_PEDIDO_de_anexo():
    r = _ref_registrada(anexo_em_curso="a1b2c3d4e5f6")
    assert r == "job-anexo:a1b2c3d4e5f6", r


def test_dois_anexos_com_os_MESMOS_arquivos_processados_tem_chaves_diferentes():
    """🩸 O caso que derrubou a 1ª versão: projeto com CAD, o cliente anexa um
    PDF e depois OUTRO — a rota manda ao motor só os CADs, então os arquivos
    processados são os mesmos nas duas rodadas. Com a chave pelos nomes, o 2º
    anexo calava; com a marca do pedido, cada um tem a sua."""
    r1 = _ref_registrada(n_cad=1, anexo_em_curso="pedido000001")
    r2 = _ref_registrada(n_cad=1, anexo_em_curso="pedido000002")
    assert r1 != r2, (r1, r2)


def test_a_janela_do_anexo_e_de_30_minutos_e_nao_pra_sempre():
    vistos = []
    _fim(is_complement=True, anexo_em_curso="pedido000001", minutos_vistos=vistos)
    do_anexo = [m for (k, m) in vistos if k == "complemento_pronto"]
    assert do_anexo == [30], (
        "a trava do anexo não é mais a janela de 30 min: %r" % vistos)


def test_envio_que_FALHA_nao_registra_como_avisado():
    """Se o SMTP falhou, a ficha não pode ser gravada — senão a próxima rodada
    acharia que o cliente já foi avisado."""
    _d, registros, _ch = _fim(is_complement=True, anexo_em_curso="pedido000001",
                              envio_ok=False, exige_email=False)
    assert not [r for r in registros if r[0] == "complemento_pronto"], registros


def test_o_fim_do_anexo_LIMPA_a_marca():
    """Pendurada, a marca faria uma retomada futura (de outro motivo) tratar o
    projeto como anexo."""
    diario, _reg, _ch = _fim(is_complement=True, anexo_em_curso="pedido000001")
    assert ("job-anexo", {"anexo_em_curso": None}) in diario["patches"], diario["patches"]


def test_a_marca_sai_mesmo_quando_o_aviso_da_rodada_ja_tinha_saido():
    diario, _reg, _ch = _fim(is_complement=True, anexo_em_curso="pedido000001",
                             rodada_avisou=True, exige_email=False)
    assert ("job-anexo", {"anexo_em_curso": None}) in diario["patches"], diario["patches"]


def test_CONTROLE_projeto_que_nao_e_anexo_nao_mexe_na_marca():
    diario, _reg, _ch = _fim(is_complement=False)
    assert not [p for p in diario["patches"] if "anexo_em_curso" in p[1]], diario["patches"]


def test_CONTROLE_a_consulta_real_diz_SIM_quando_ha_ficha(monkeypatch):
    """Controle positivo da trava real: com linha no email_auto_log, é True —
    senão um `_aviso_de_fim_recente` que nunca acha nada passaria verde."""
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, **k: _Resp(b'[{"id": 1}]'))
    assert main._aviso_de_fim_recente(_EMAIL, "job-x:pedido", kind="complemento_pronto") is True
    assert main._aviso_de_fim_recente(_EMAIL, "job-x") is True


# ── revisão final (21/09): a marca só sai com o `done` confirmado ──────────
def test_a_limpeza_confere_a_marca_DESTE_pedido():
    diario, _reg, _ch = _fim(is_complement=True, anexo_em_curso="pedido000001")
    assert diario["marcas_limpas"] == ["pedido000001"], diario["marcas_limpas"]


def test_sem_o_DONE_gravado_a_marca_FICA():
    """🩸 revisão final (21/09): sem o `done`, a marca é o que impede a
    varredura de retomar como UPLOAD e apagar a base."""
    diario, _reg, _ch = _fim(is_complement=True, anexo_em_curso="pedido000001",
                             done_grava=False, exige_email=False)
    assert diario["marcas_limpas"] == [] and diario["patches"] == [], diario["patches"]


# ── revisão final (21/09): o que foi anexado e NÃO entrou na leitura ───────
def test_PDF_anexado_que_nao_entrou_nao_vira_que_voce_anexou():
    """🩸 O caso 7b60c43b: projeto em DWG, o cliente anexa um PDF de detalhe —
    com CAD no projeto a rota manda SÓ os CADs pro motor. O e-mail dizia
    "medindo pelo CAD que você anexou": ele mandou um PDF, e o PDF nem entrou."""
    diario, _reg, _ch = _fim(is_complement=True, anexo_em_curso="pedido000001",
                             n_pdf=0, n_cad=1, anexados=["detalhe-do-quadro.pdf"])
    e = diario["emails"][-1]
    assert e["kind"] == "complemento_pronto"
    assert "que você anexou" not in e["html"].replace("O arquivo que você anexou (", ""), (
        "chamou o CAD do projeto de 'o que você anexou'")
    assert "detalhe-do-quadro.pdf" in e["html"] and "não entrou nesta leitura" in e["html"]
    assert "O CAD que você mandou depois" not in e["html"]


def test_CONTROLE_CAD_anexado_que_entrou_segue_que_voce_anexou():
    diario, _reg, _ch = _fim(is_complement=True, anexo_em_curso="pedido000001",
                             n_pdf=0, n_cad=1, anexados=["c0.dxf"])
    e = diario["emails"][-1]
    assert "que você anexou" in e["html"] and "não entrou nesta leitura" not in e["html"]


def test_sem_saber_o_que_foi_anexado_fica_como_antes():
    """A retomada não sabe o que foi anexado (None): não inventa a nota."""
    diario, _reg, _ch = _fim(is_complement=True, anexo_em_curso="pedido000001",
                             n_pdf=0, n_cad=1, anexados=None)
    assert "não entrou nesta leitura" not in diario["emails"][-1]["html"]


def test_CAD_que_a_rota_RENOMEOU_continua_sendo_o_anexado():
    """🩸 revisão dos consertos (21/09): a rota renomeia o CAD cuja extensão
    mente (DWG salvo como .dxf — cliente-39). O cliente anexou "c0.dwg", o motor
    leu "c0.dxf": é o MESMO arquivo, e a nota "não entrou" seria falsa."""
    diario, _reg, _ch = _fim(is_complement=True, anexo_em_curso="pedido000001",
                             n_pdf=0, n_cad=1, anexados=["c0.dwg"])
    html = diario["emails"][-1]["html"]
    assert "não entrou nesta leitura" not in html and "que você anexou" in html


def test_CONTROLE_PDF_de_mesmo_nome_que_o_CAD_nao_vira_o_CAD():
    """Só a extensão CAD sai da comparação: "c0.pdf" anexado não é o "c0.dxf" lido."""
    diario, _reg, _ch = _fim(is_complement=True, anexo_em_curso="pedido000001",
                             n_pdf=0, n_cad=1, anexados=["c0.pdf"])
    assert "não entrou nesta leitura" in diario["emails"][-1]["html"]
