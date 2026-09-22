# -*- coding: utf-8 -*-
"""Anexar o arquivo que JÁ está no projeto não pode refazer a leitura.

🩸 16/09/2026, cliente NOVO, primeiro projeto. O PDF dele foi lido e saiu sem
nenhuma linha medida — de PDF a quantidade sai como estimativa, por regra
nossa (`_pdf_downgrade`), não por defeito do arquivo. Às 16:05 ele anexou **o mesmo PDF** pela tela de anexar, provavelmente
achando que insistir ajudaria. O sistema aceitou sem conferir:

  · arquivou a versão que ele tinha (67 linhas);
  · refez a leitura do zero e entregou 52 — ainda zero medida;
  · gastou IA nossa pra piorar a planilha dele.

E ninguém nunca tinha dito a ele que o arquivo estava errado, porque o e-mail
automático afirmava *"Refizemos o projeto com o CAD que você anexou"* — com a
palavra CAD fixa, mesmo tendo entrado PDF. A frase CONFIRMAVA que ele havia
mandado a coisa certa.

Pedro, no mesmo dia: *"quando o cliente subir o mesmo arquivo, a gente pode ler
antes de rodar... travar isso e dizer um aviso na tela que é o mesmo arquivo."*

🔑 Identidade de arquivo é o CONTEÚDO (sha256), não o nome: o navegador dele
mandou `... (1).pdf`, nome diferente do que estava no Storage.

🚨 O guarda da rota usa o TestClient e prova a parte que importa: com anexo
repetido o motor NÃO é disparado.
"""
import hashlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import main  # noqa: E402

_JOB = "job-anexo-01"
_BYTES = b"%PDF-1.4 prancha do cliente" * 40
_OUTRO = b"%PDF-1.4 outra prancha bem diferente" * 37


def _arquivo(tmp_path, nome, dados):
    p = tmp_path / nome
    p.write_bytes(dados)
    return (nome, str(p), len(dados))


# ── a conferência ──────────────────────────────────────────────────────────
def _com_storage(monkeypatch, listagem, conteudos):
    monkeypatch.setattr(main, "_pranchas_com_tamanho", lambda job: listagem)
    monkeypatch.setattr(main, "_supabase_storage_download_prancha",
                        lambda job, nome, **k: conteudos.get(nome))


def test_o_mesmo_arquivo_com_NOME_diferente_ainda_e_o_mesmo(tmp_path, monkeypatch):
    """O caso real: o navegador do cliente renomeou pra `(1)`."""
    _com_storage(monkeypatch,
                 [("%s/prancha.pdf" % _JOB, len(_BYTES))],
                 {"prancha.pdf": _BYTES})
    rep, tem_cad = main._anexos_ja_no_projeto(
        _JOB, [_arquivo(tmp_path, "prancha (1).pdf", _BYTES)])
    assert rep == {"prancha (1).pdf": "prancha.pdf"}, rep
    assert tem_cad is False


def test_CONTROLE_arquivo_NOVO_passa(tmp_path, monkeypatch):
    _com_storage(monkeypatch,
                 [("%s/prancha.pdf" % _JOB, len(_BYTES))],
                 {"prancha.pdf": _BYTES})
    rep, _ = main._anexos_ja_no_projeto(
        _JOB, [_arquivo(tmp_path, "planta.dxf", _OUTRO)])
    assert rep == {}, "barrou um arquivo que é novo de verdade"


def test_MESMO_TAMANHO_com_conteudo_diferente_nao_e_repetido(tmp_path, monkeypatch):
    """🪤 O tamanho é só pré-filtro barato — quem decide é o conteúdo. Revisão
    do desenho costuma sair com o mesmo tamanho."""
    gemeo = bytes(len(_BYTES) - 1) + b"X"
    assert len(gemeo) == len(_BYTES)
    _com_storage(monkeypatch,
                 [("%s/prancha.pdf" % _JOB, len(_BYTES))],
                 {"prancha.pdf": gemeo})
    rep, _ = main._anexos_ja_no_projeto(
        _JOB, [_arquivo(tmp_path, "prancha.pdf", _BYTES)])
    assert rep == {}, "bloqueou uma revisão nova só porque tinha o mesmo tamanho"


def test_listagem_que_FALHA_deixa_subir(tmp_path, monkeypatch):
    """🪤 Fail-OPEN aqui, ao contrário da varredura: bloquear um anexo legítimo
    por causa de um 500 do banco tira do cliente a única saída que ele tem."""
    monkeypatch.setattr(main, "_pranchas_com_tamanho", lambda job: None)
    rep, _ = main._anexos_ja_no_projeto(
        _JOB, [_arquivo(tmp_path, "prancha.pdf", _BYTES)])
    assert rep == {}


def test_gemeo_que_NAO_BAIXA_nao_vira_alarme_de_perda(tmp_path, monkeypatch):
    """🩸 Achado pela bancada, por um guarda de OUTRO arquivo: a casa exige que
    quem baixa do Storage num laço e descarta prancha chame
    `_alerta_pranchas_perdidas`. Aqui não cabe — o arquivo segue no Storage e a
    leitura do cliente não depende deste download, que só serviria pra
    comparar. Alarme de perda onde não houve perda é como se perde um
    instrumento. O que cabe é fail-open com rastro: não consegui comparar,
    então trato como novo.
    """
    _com_storage(monkeypatch, [("%s/prancha.pdf" % _JOB, len(_BYTES))], {})
    rep, _ = main._anexos_ja_no_projeto(
        _JOB, [_arquivo(tmp_path, "prancha.pdf", _BYTES)])
    assert rep == {}, "barrou o anexo sem ter conseguido comparar com nada"


def test_gemeo_que_EXPLODE_ao_baixar_tambem_deixa_subir(tmp_path, monkeypatch):
    def _explode(job, nome, **k):
        raise RuntimeError("storage fora do ar")
    monkeypatch.setattr(main, "_pranchas_com_tamanho",
                        lambda job: [("%s/prancha.pdf" % _JOB, len(_BYTES))])
    monkeypatch.setattr(main, "_supabase_storage_download_prancha", _explode)
    rep, _ = main._anexos_ja_no_projeto(
        _JOB, [_arquivo(tmp_path, "prancha.pdf", _BYTES)])
    assert rep == {}


def test_o_projeto_que_ja_tem_CAD_e_reconhecido(tmp_path, monkeypatch):
    _com_storage(monkeypatch,
                 [("%s/planta.dxf" % _JOB, 99), ("%s/prancha.pdf" % _JOB, len(_BYTES))],
                 {"prancha.pdf": _BYTES})
    _rep, tem_cad = main._anexos_ja_no_projeto(
        _JOB, [_arquivo(tmp_path, "prancha.pdf", _BYTES)])
    assert tem_cad is True


# ── o recado da tela ───────────────────────────────────────────────────────
# 🩸 22/09/2026 (job ee801b82): o recado passou a CHEGAR à pessoa pelo painel e
# dizia "O PDF é uma imagem da prancha: as medidas não viajam dentro dele" —
# 5 das 7 pranchas dela tinham camada de texto, e a primeira trazia impresso o
# quadro de quantitativos. O recado não abre o PDF, então não pode afirmar o
# que tem dentro dele; o que ele pode dizer é a NOSSA regra, verdadeira por
# construção (`_pdf_downgrade`): de PDF sai estimativa, nunca medida.
_O_QUE_O_RECADO_NAO_SABE = ("imagem", "viajam", "camada", "texto", "escaneado")


def _afirma_o_conteudo_do_pdf(txt):
    return [p for p in _O_QUE_O_RECADO_NAO_SABE if p in txt.lower()]


def test_o_recado_PEDE_o_CAD_quando_o_projeto_so_tem_PDF():
    txt = main._recado_do_anexo_repetido({"a (1).pdf": "a.pdf"}, tem_cad=False)
    assert "a.pdf" in txt, "o cliente precisa saber QUAL arquivo"
    assert "DWG" in txt and "DXF" in txt, txt
    assert "estimativa" in txt and "nunca como medida" in txt, (
        "o recado não diz a regra que vale pra qualquer PDF: %r" % txt)
    assert _afirma_o_conteudo_do_pdf(txt) == [], (
        "o recado afirma o que tem dentro do PDF sem ter olhado: %r" % txt)


def test_CONTROLE_o_guarda_pega_a_frase_que_mentiu():
    antigo = ("Esse arquivo já está no projeto (a.pdf). O PDF é uma imagem da "
              "prancha: as medidas não viajam dentro dele.")
    assert _afirma_o_conteudo_do_pdf(antigo), "o guarda não enxerga a frase de 22/09"


def test_o_recado_de_VARIOS_arquivos_fala_no_plural():
    """Os 7 do caso: "Esse arquivo já está no projeto" de 7 arquivos."""
    nomes = ["prancha-%s.pdf" % l for l in "ABCDEFG"]
    txt = main._recado_do_anexo_repetido({n: n for n in nomes}, tem_cad=False)
    assert txt.startswith("Esses 7 arquivos já estão no projeto ("), txt[:120]
    assert "Esse arquivo" not in txt and "uma versão nova" not in txt, txt[:200]
    assert "prancha-A.pdf" in txt and "prancha-G.pdf" in txt, txt


def test_o_recado_de_UM_arquivo_fica_no_singular():
    txt = main._recado_do_anexo_repetido({"a (1).pdf": "a.pdf"}, tem_cad=True)
    assert txt.startswith("Esse arquivo já está no projeto (a.pdf)"), txt[:120]


def test_o_recado_NAO_pede_CAD_pra_quem_ja_mandou():
    txt = main._recado_do_anexo_repetido({"p.dxf": "p.dxf"}, tem_cad=True)
    assert "DWG" not in txt, "pediu CAD pra quem já mandou CAD: %r" % txt
    assert "Reprocessar" in txt, txt


# ── a rota: barra ANTES de disparar o motor ────────────────────────────────
@pytest.fixture()
def _rota(monkeypatch):
    from fastapi.testclient import TestClient

    disparos = []
    subidas = []

    monkeypatch.setattr(main, "_require_project_owner", lambda *a, **k: "dono-1")
    monkeypatch.setattr(main, "_rate_limit_ok", lambda *a, **k: True)
    monkeypatch.setattr(main, "_supabase_storage_upload_prancha",
                        lambda p, j, n: subidas.append(n) or True)
    monkeypatch.setattr(main, "_process_job_throttled",
                        lambda *a, **k: disparos.append(a))
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)

    class _Resp(object):
        def __init__(self_, payload):
            self_._p = payload

        def read(self_):
            import json
            return json.dumps(self_._p).encode("utf-8")

        def getcode(self_):
            return 200

        def __enter__(self_):
            return self_

        def __exit__(self_, *a):
            return False

    _PROJETO = [{"typology": "office", "project_type": "arquitetura",
                 "status": "done", "user_total_area": 0, "user_pe_direito": 0}]

    def _urlopen(req, *a, **k):
        # 🪤 A rota fala com DOIS endereços por urllib (a linha do projeto e a
        # listagem do Storage). Um dublê que responde a mesma coisa pros dois
        # faz o guarda morrer numa etapa que não é a medida aqui.
        url = getattr(req, "full_url", "") or str(req)
        if "/storage/v1/object/list/" in url:
            return _Resp([{"name": "prancha.pdf", "metadata": {"size": len(_BYTES)}},
                          {"name": "planta.dxf", "metadata": {"size": len(_OUTRO)}}])
        return _Resp(_PROJETO)

    monkeypatch.setattr(main.urllib.request, "urlopen", _urlopen)
    return TestClient(main.app, raise_server_exceptions=False), disparos, subidas


def test_a_ROTA_barra_o_anexo_repetido_SEM_disparar_o_motor(_rota, monkeypatch):
    cliente, disparos, subidas = _rota
    _com_storage(monkeypatch,
                 [("%s/prancha.pdf" % _JOB, len(_BYTES))],
                 {"prancha.pdf": _BYTES})
    r = cliente.post("/api/project/%s/add-file" % _JOB,
                     files={"files": ("prancha (1).pdf", io.BytesIO(_BYTES), "application/pdf")})
    assert r.status_code == 409, (r.status_code, r.text[:300])
    assert "já está no projeto" in r.json().get("detail", ""), r.json()
    assert disparos == [], "gastou IA num arquivo que já estava lá"
    assert subidas == [], "sobrescreveu o arquivo original no Storage"


def test_a_ROTA_com_UM_repetido_e_UM_novo_roda_so_com_o_novo(_rota, monkeypatch):
    """🪤 Meio-termo que existe de verdade: o cliente seleciona a pasta inteira
    e manda o que já subiu junto com a prancha nova. Barrar tudo seria tão
    errado quanto refazer tudo — sobe o novo, ignora o gêmeo."""
    cliente, disparos, subidas = _rota
    _com_storage(monkeypatch,
                 [("%s/prancha.pdf" % _JOB, len(_BYTES))],
                 {"prancha.pdf": _BYTES, "planta.dxf": _OUTRO})
    r = cliente.post(
        "/api/project/%s/add-file" % _JOB,
        files=[("files", ("prancha (1).pdf", io.BytesIO(_BYTES), "application/pdf")),
               ("files", ("planta.dxf", io.BytesIO(_OUTRO), "application/octet-stream"))])
    assert r.status_code == 200, (r.status_code, r.text[:300])
    assert subidas == ["planta.dxf"], (
        "subiu o gêmeo por cima do original: %r" % (subidas,))
    assert disparos, "o arquivo novo entrou mas o motor não rodou"


def test_CONTROLE_a_ROTA_deixa_passar_arquivo_novo(_rota, monkeypatch):
    cliente, disparos, subidas = _rota
    _com_storage(monkeypatch,
                 [("%s/prancha.pdf" % _JOB, len(_BYTES))],
                 {"prancha.pdf": _BYTES, "planta.dxf": _OUTRO})
    r = cliente.post("/api/project/%s/add-file" % _JOB,
                     files={"files": ("planta.dxf", io.BytesIO(_OUTRO), "application/octet-stream")})
    assert r.status_code == 200, (r.status_code, r.text[:300])
    assert subidas == ["planta.dxf"], subidas
    assert disparos, "o arquivo novo entrou mas o motor não rodou"


# ── o e-mail para de afirmar CAD ───────────────────────────────────────────
def _voz(**k):
    base = dict(nome_escapado="Petropolis", nome_cru="Petropolis", n_itens=52,
                n_medidos=0, n_geo=0)
    base.update(k)
    return main.voz_do_email_de_reprocesso(**base)


def test_o_email_NAO_afirma_CAD_quando_entrou_PDF():
    abertura, assunto, titulo, _selo, _pre = _voz(anexo="PDF")
    for pedaco in (abertura, assunto, titulo):
        assert "CAD" not in pedaco, (
            "o e-mail afirmou CAD pra quem anexou PDF: %r" % pedaco[:160])
    assert "PDF" in assunto and "PDF" in abertura
    assert "DWG" in abertura and "DXF" in abertura, (
        "disse a verdade mas não pediu o que falta: %r" % abertura[:200])


def test_o_padrao_e_vago_NUNCA_mentiroso():
    """🪤 Quem esquecer de passar o que entrou fica vago — afirmar sem prova é o
    defeito que esta função existe pra barrar."""
    abertura, assunto, titulo, _s, _p = _voz()
    for pedaco in (abertura, assunto, titulo):
        assert "CAD" not in pedaco, pedaco[:160]


def test_CONTROLE_com_CAD_o_texto_continua_dizendo_CAD():
    abertura, assunto, _t, _s, _p = _voz(anexo="CAD")
    assert "CAD" in assunto and "CAD" in abertura
    assert "DWG" not in abertura, "pediu CAD pra quem acabou de mandar CAD"


def test_o_ramo_que_MEDIU_tambem_diz_o_que_entrou():
    abertura, assunto, _t, _s, _p = _voz(anexo="PDF", n_medidos=7)
    assert "CAD" not in abertura and "CAD" not in assunto, abertura[:160]


def test_o_FIM_DO_JOB_passa_o_que_entrou_de_verdade(monkeypatch):
    """🔑 Guarda de CHAMADA: a voz pode estar certa e o call site continuar
    mandando 'CAD'. Este roda a fatia real do process_job com um complemento de
    PDF e lê o e-mail que sai.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _fim_do_job import roda_ate_o_email

    class _It(object):
        description = "piso ceramico"
        unit = "m2"
        quantity = 10.0
        confidence = "estimado"
        discipline = "Pisos"
        origem = "ia"

    diario = roda_ate_o_email([_It(), _It()], is_complement=True,
                              n_pdf=1, n_cad=0)
    email = diario["emails"][-1]
    assert "CAD" not in email["assunto"], (
        "o fim do job mandou 'CAD' num complemento que só tinha PDF: %r"
        % email["assunto"])
    assert "PDF" in email["assunto"] or "PDF" in email["html"], email["assunto"]


def test_CONTROLE_complemento_com_CAD_continua_dizendo_CAD(monkeypatch):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _fim_do_job import roda_ate_o_email

    class _It(object):
        description = "piso ceramico"
        unit = "m2"
        quantity = 10.0
        confidence = "estimado"
        discipline = "Pisos"
        origem = "ia"

    diario = roda_ate_o_email([_It(), _It()], is_complement=True,
                              n_pdf=0, n_cad=1)
    assert "CAD" in diario["emails"][-1]["assunto"], diario["emails"][-1]["assunto"]


def test_o_sha256_le_em_pedacos_e_bate_com_o_do_python(tmp_path):
    p = tmp_path / "grande.bin"
    dados = os.urandom(200000)
    p.write_bytes(dados)
    assert main._sha256_do_arquivo(str(p)) == hashlib.sha256(dados).hexdigest()
