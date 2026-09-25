# -*- coding: utf-8 -*-
"""A falha leva o TIPO do catálogo desde onde nasce até o aviso.

📚 25/09/2026 — entrega 3 do catálogo de falhas (`falhas.py`). O motor levanta
`Falha(tipo, mensagem_antiga)` no ponto onde CONHECE a causa; o tipo vai pro log
(`falha:tipo`) sempre, e a varredura, o e-mail e o aviso interno leem dele.

🔑 Enquanto `falhas.LIGADO` for False, NADA muda pro cliente: a tela e o e-mail
são os de antes, e a re-tentativa automática decide pelo regex de sempre. Por
isso quase todo guarda aqui tem par: desligado = como antes; ligado = catálogo.

Regras do Pedro que os guardas prendem:
- re-tenta sozinho só servidor e sobrecarga ("automático é o servidor caiu");
- tipo automático não avisa o cliente na 1ª queda — só se esgotar;
- o aviso interno não se chama mais "erro terminal" ("parece que é o fim").
"""
import ast
import json
import os
import socket
import sys
import types
import urllib.request

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
_BACK = os.path.dirname(_AQUI)
sys.path.insert(0, _BACK)

import dwg_extractor as dx  # noqa: E402
import falhas  # noqa: E402
import main  # noqa: E402

_TIPOS = sorted(falhas.TIPOS)
_AUTOMATICOS = [t for t in _TIPOS if falhas.TIPOS[t]["automatico"]]
_JOB = "0000feed-2509-4000-8000-000000000025"


@pytest.fixture(autouse=True)
def _desligado_e_sem_rede(monkeypatch):
    """Todo teste começa DESLIGADO (como produção hoje) e sem falar com servidor."""
    monkeypatch.setattr(falhas, "LIGADO", False)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(main, "_notify_admin", lambda *a, **k: True)
    monkeypatch.setattr(main, "_send_email_smtp", lambda *a, **k: True)


def _liga(monkeypatch):
    monkeypatch.setattr(falhas, "LIGADO", True)


# ══════════════════════════════════════════════════════════════════════════
#  1. A exceção e a tela
# ══════════════════════════════════════════════════════════════════════════
def test_desligado_a_Falha_mostra_a_mensagem_de_antes():
    e = falhas.Falha("leitor-conversao", "texto antigo da tela", arquivo=" Planta.dwg ")
    assert str(e) == "texto antigo da tela"
    assert (e.tipo, e.arquivo) == ("leitor-conversao", "Planta.dwg")


def test_CONTROLE_ligado_a_Falha_mostra_o_catalogo(monkeypatch):
    _liga(monkeypatch)
    e = falhas.Falha("leitor-conversao", "texto antigo da tela", arquivo="Planta.dwg")
    assert str(e) == falhas.texto_da_tela("leitor-conversao", "", "Planta.dwg")
    assert "texto antigo" not in str(e)


def test_tipo_inventado_vira_desconhecido_e_nao_estoura():
    e = falhas.Falha("tipo-que-nao-existe", "x")
    assert e.tipo == "desconhecido" and str(e) == "x"


def test_desligado_erro_de_programacao_segue_na_tela_como_antes():
    e = AttributeError("'str' object has no attribute 'get'")
    tipo, arquivo, tela = main._tipo_e_tela_da_falha(e)
    assert (tipo, arquivo, tela) == ("erro-no-sistema", "", str(e))


def test_CONTROLE_ligado_erro_de_programacao_nao_aparece_cru(monkeypatch):
    _liga(monkeypatch)
    e = AttributeError("'str' object has no attribute 'get'")
    tipo, _, tela = main._tipo_e_tela_da_falha(e)
    assert tipo == "erro-no-sistema"
    assert "attribute" not in tela and tela == falhas.texto_da_tela("erro-no-sistema")


def test_ligado_a_Falha_do_motor_chega_inteira_na_tela(monkeypatch):
    _liga(monkeypatch)
    e = falhas.Falha("dwg-autocad-mep", "antigo", arquivo="Hidraulica.dwg")
    assert main._tipo_e_tela_da_falha(e) == ("dwg-autocad-mep", "Hidraulica.dwg", str(e))


@pytest.mark.parametrize("classe,esperado", [
    ("nosso", "erro-no-sistema"), ("passageiro", "servidor-instavel"),
    ("arquivo", "desconhecido"), ("", "desconhecido")])
def test_excecao_sem_tipo_herda_a_classificacao_de_antes(classe, esperado):
    """'arquivo' NÃO vira tipo do cliente: sem prova, o balde é o desconhecido
    (que é nosso) — nunca o que acusa o arquivo."""
    assert falhas.tipo_da_excecao(RuntimeError("x"), classe) == esperado


# ══════════════════════════════════════════════════════════════════════════
#  2. Os classificadores dos pontos do motor
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("blob,conversao,esperado", [
    ("Your credit balance is too low to access the API", False, "interno-da-conta"),
    ("arquivo grande demais pra processar com segurança", False, "limite-arquivo-grande"),
    ("ezdxf.DXFStructureError: invalid group code", True, "leitor-conversao"),
    ("ezdxf.DXFStructureError: invalid group code", False, "leitor-extracao"),
    ("extração isolada falhou: exit 1", False, "leitor-extracao"),
    ("anthropic: status=401 authentication_error", False, "interno-da-conta"),
    ("algo que ninguém previu", False, "desconhecido"),
])
def test_erro_permanente_de_leitura_pelo_texto_tecnico(blob, conversao, esperado):
    assert falhas.tipo_do_erro_de_leitura(blob, conversao) == esperado


@pytest.mark.parametrize("estrutura,vetoriais,pdf,cad,esperado", [
    (True, 0, True, False, "tipo-errado-estrutura"),
    (False, 3, True, False, "pdf-sem-quantidade"),
    (False, 0, True, False, "pdf-escaneado"),
    (False, 0, False, True, "leitor-extracao"),
    (False, 0, True, True, "leitor-extracao"),
])
def test_sem_nenhum_item(estrutura, vetoriais, pdf, cad, esperado):
    """Quem mandou CAD e saiu zero não leva 'PDF escaneado' — o defeito que abriu o caso."""
    assert falhas.tipo_sem_itens(estrutura, vetoriais, pdf, cad) == esperado


@pytest.mark.parametrize("aec,truncado,esperado", [
    (True, False, "dwg-autocad-mep"), (True, True, "dwg-autocad-mep"),
    (False, True, "leitor-dwg-parou"), (False, False, "leitor-dwg-versao")])
def test_dwg_que_nao_abriu(aec, truncado, esperado):
    assert falhas.tipo_do_dwg_que_nao_abriu(aec, truncado) == esperado


def _literais_de_tipo_no_motor():
    """Todo tipo ESCRITO À MÃO no main.py: `Falha("x", …)`, `tipo="x"` e
    `_registrar_tipo_da_falha(job, "x")`. Lido pela AST, não pelo texto."""
    arvore = ast.parse(open(os.path.join(_BACK, "main.py"), encoding="utf-8").read())
    achados = []
    for n in ast.walk(arvore):
        if not isinstance(n, ast.Call):
            continue
        nome = (n.func.attr if isinstance(n.func, ast.Attribute)
                else getattr(n.func, "id", ""))
        if nome == "Falha" and n.args and isinstance(n.args[0], ast.Constant):
            achados.append((n.lineno, n.args[0].value))
        if (nome == "_registrar_tipo_da_falha" and len(n.args) > 1
                and isinstance(n.args[1], ast.Constant)):
            achados.append((n.lineno, n.args[1].value))
        for k in n.keywords:
            if (k.arg == "tipo" and isinstance(k.value, ast.Constant)
                    and nome in ("_email_falha_cliente", "Falha")):
                achados.append((n.lineno, k.value.value))
    return achados


def test_todo_tipo_escrito_no_motor_existe_no_catalogo():
    """🪤 Tipo com erro de digitação não quebra nada: vira 'desconhecido' calado,
    e o cliente leva o texto genérico no lugar do certo."""
    achados = _literais_de_tipo_no_motor()
    assert len(achados) >= 6, achados       # os pontos ligados hoje
    for linha, tipo in achados:
        assert tipo in falhas.TIPOS, "main.py:%d usa o tipo %r, que não existe" % (linha, tipo)


# ══════════════════════════════════════════════════════════════════════════
#  3. Quem re-tenta sozinho
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("tipo", _TIPOS)
@pytest.mark.parametrize("ligado", [False, True], ids=["desligado", "ligado"])
def test_a_tela_do_catalogo_sem_tipo_decide_igual_ao_tipo(monkeypatch, tipo, ligado):
    """Se o registro do tipo se perder (rede), o regex de sempre, lendo a tela do
    catálogo, tem que chegar na MESMA decisão que o tipo — senão uma leitura
    quebrada seria re-tentada sozinha, ou um servidor caído ficaria parado."""
    if ligado:
        _liga(monkeypatch)
    tela = falhas.texto_da_tela(tipo, "Obra Exemplo", "Planta.dwg")
    assert main._re_tenta_sozinho(tela, "") is falhas.TIPOS[tipo]["automatico"], tipo


def test_ligado_leitura_quebrada_NAO_re_tenta_mesmo_com_palavra_de_servidor(monkeypatch):
    _liga(monkeypatch)
    assert main._re_tenta_sozinho("excedeu o tempo limite na conversão", "leitor-conversao") is False


def test_CONTROLE_desligado_a_mesma_frase_re_tenta_como_antes():
    assert main._re_tenta_sozinho("excedeu o tempo limite na conversão", "leitor-conversao") is True


def test_ligado_servidor_caido_re_tenta_mesmo_sem_a_palavra(monkeypatch):
    _liga(monkeypatch)
    assert main._re_tenta_sozinho("texto qualquer", "servidor-instavel") is True


def test_CONTROLE_desligado_o_tipo_nao_decide_nada():
    assert main._re_tenta_sozinho("texto qualquer", "servidor-instavel") is False


def test_so_servidor_e_sobrecarga_sao_automaticos():
    """Pedro, 25/09: 'automático é o servidor caiu'. Tipo novo automático é
    decisão dele — mexer aqui é mexer nesta lista de propósito."""
    assert _AUTOMATICOS == ["leitura-sobrecarregada", "servidor-instavel"]


# ══════════════════════════════════════════════════════════════════════════
#  4. O aviso interno
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("tipo", _TIPOS)
def test_o_aviso_interno_diz_quem_age_e_o_que_fazer(tipo):
    assunto, bloco = main._alerta_interno_da_falha(tipo, "Obra Exemplo")
    t = falhas.TIPOS[tipo]
    esperado = "Para acompanhar" if t["quem"] == "cliente" else "Precisa de você"
    assert assunto.startswith(esperado + ": Obra Exemplo"), assunto
    assert "terminal" not in assunto.lower()
    assert "O que fazer:" in bloco and "O que aconteceu:" in bloco
    assert tipo in bloco


def test_falha_sem_tipo_ainda_avisa_e_diz_que_nao_tem_tipo():
    assunto, bloco = main._alerta_interno_da_falha("", "")
    assert assunto.startswith("Precisa de você") and "sem tipo" in assunto
    assert "O que aconteceu:" in bloco


# ══════════════════════════════════════════════════════════════════════════
#  5. O e-mail ao cliente
# ══════════════════════════════════════════════════════════════════════════
class _R(object):
    def __init__(self, dados):
        self._d = dados

    def read(self, *a):
        return json.dumps(self._d).encode("utf-8")


def _email(monkeypatch, **kw):
    enviados, pedidos = [], []

    def falso(req, timeout=None):
        url = getattr(req, "full_url", str(req))
        pedidos.append(url)
        if "/projects?job_id=eq." in url:
            return _R([{"user_email": "cliente@exemplo.com", "user_name": "Cliente Exemplo",
                        "project_name": "Obra Exemplo", "parent_job_id": None,
                        "reprocess_count": 0, "created_at": "2026-09-25T12:00:00+00:00",
                        "error_message": "texto da tela", "items_count": 0}])
        return _R([])
    monkeypatch.setattr(main, "SUPABASE_URL", "https://exemplo.supabase.co")
    monkeypatch.setattr(urllib.request, "urlopen", falso)
    monkeypatch.setattr(main, "_resolve_client_name", lambda *a, **k: "Cliente Exemplo")
    monkeypatch.setattr(main, "_send_email_smtp",
                        lambda to, assunto, html, *a, **k: enviados.append(
                            (assunto, html, k.get("log_kind"))) or True)
    monkeypatch.setattr(main, "_falha_emailed", set())
    ok = main._email_falha_cliente(_JOB, **kw)
    return ok, enviados, pedidos


def test_desligado_o_tipo_e_ignorado_e_o_email_e_o_de_antes(monkeypatch):
    ok, enviados, _ = _email(monkeypatch, reprocessavel=True, tipo="leitor-conversao")
    assert ok and enviados[0][2] == "erro_reprocessar", enviados


def test_ligado_o_email_sai_pelo_tipo(monkeypatch):
    _liga(monkeypatch)
    ok, enviados, _ = _email(monkeypatch, reprocessavel=True, tipo="leitor-conversao",
                             arquivo="Planta.dwg")
    assert ok and enviados[0][2] == "falha:leitor-conversao", enviados
    assert "problema do nosso lado" in enviados[0][0].lower()


@pytest.mark.parametrize("tipo", _AUTOMATICOS)
def test_ligado_tipo_automatico_NAO_avisa_na_primeira_queda(monkeypatch, tipo):
    _liga(monkeypatch)
    ok, enviados, pedidos = _email(monkeypatch, tipo=tipo)
    assert ok is False and enviados == [] and pedidos == []


@pytest.mark.parametrize("tipo", _AUTOMATICOS)
def test_CONTROLE_ligado_tipo_automatico_avisa_quando_esgota(monkeypatch, tipo):
    _liga(monkeypatch)
    ok, enviados, _ = _email(monkeypatch, tipo=tipo, terminal=True)
    assert ok and enviados[0][2] == "falha:" + tipo, enviados


def test_o_alerta_interno_reconhece_os_avisos_novos(monkeypatch):
    """🩸 `erro_nosso` (19/09) nunca entrou na consulta: o dia em que saísse, o
    aviso interno diria 'não há e-mail de falha'. E o catálogo grava `falha:<tipo>`."""
    pedidos = []

    def falso(req, timeout=None):
        pedidos.append(getattr(req, "full_url", str(req)))
        return _R([{"kind": "falha:servidor-instavel", "sent_at": "2026-09-25T12:05:00+00:00"}])
    monkeypatch.setattr(main, "SUPABASE_URL", "https://exemplo.supabase.co")
    monkeypatch.setattr(urllib.request, "urlopen", falso)
    linha = main._linha_do_email_ao_cliente("cliente@exemplo.com", "2026-09-25T12:00:00+00:00")
    assert "erro_nosso" in pedidos[0] and "kind.like.falha*" in pedidos[0], pedidos
    assert "falha:servidor-instavel" in linha and "não há" not in linha, linha


# ══════════════════════════════════════════════════════════════════════════
#  6. A varredura de 5 min
# ══════════════════════════════════════════════════════════════════════════
def _varredura(monkeypatch, *, tipo, msg, count, retoma=True, ja_avisou_cliente=False):
    """Roda a varredura REAL com um projeto em erro cujo tipo registrado é `tipo`."""
    cena = types.SimpleNamespace(retomados=[], avisos=[], emails=[], fichas=[])
    linha = {"job_id": _JOB, "user_email": "cliente@exemplo.com",
             "project_name": "Obra Exemplo", "error_message": msg,
             "typology": "office", "project_type": "arquitetura",
             "auto_resume_count": count, "created_at": "2026-09-25T12:00:00Z"}
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _R([linha]))

    def _supa(metodo, caminho, **k):
        if caminho.startswith("error_log"):
            assert "stage=eq.falha:tipo" in caminho and _JOB in caminho, caminho
            return 200, ([{"message": "tipo=%s arquivo=Planta.dwg" % tipo}] if tipo else [])
        assert "parent_job_id=eq.%s" % _JOB in caminho, caminho
        return 200, []
    monkeypatch.setattr(main, "_supa_rest_service", _supa)
    monkeypatch.setattr(main, "_retomar_job_do_storage",
                        lambda j, *a, **k: cena.retomados.append(j) or retoma)
    monkeypatch.setattr(main, "_email_auto_ja_enviado",
                        lambda email, kind, ref="", **k: ja_avisou_cliente and kind == "falha_parada")
    monkeypatch.setattr(main, "_email_auto_registrar",
                        lambda email, kind, ref="", **k: cena.fichas.append((email, kind, ref)))
    monkeypatch.setattr(main, "_notify_admin",
                        lambda assunto, corpo="", *a, **k: cena.avisos.append((assunto, corpo)) or True)
    monkeypatch.setattr(main, "_email_falha_cliente",
                        lambda job_id, *a, **k: cena.emails.append(dict(k, job_id=job_id)) or True)
    monkeypatch.setattr(main, "_error_log_causa_real", lambda *a, **k: "")
    monkeypatch.setattr(main, "_linha_do_email_ao_cliente", lambda *a, **k: "")
    main._auto_retry_erros_transitorios()
    return cena


def test_ligado_servidor_caido_re_tenta_sozinho_com_a_tela_do_catalogo(monkeypatch):
    _liga(monkeypatch)
    cena = _varredura(monkeypatch, tipo="servidor-instavel",
                      msg=falhas.texto_da_tela("servidor-instavel"), count=0)
    assert cena.retomados == [_JOB] and cena.avisos == [] and cena.emails == []


def test_ligado_leitura_quebrada_NAO_re_tenta_e_chama_o_Pedro(monkeypatch):
    _liga(monkeypatch)
    cena = _varredura(monkeypatch, tipo="leitor-conversao",
                      msg="a conversão excedeu o tempo limite", count=0)
    assert cena.retomados == []
    assert cena.avisos and cena.avisos[0][0].startswith("Precisa de você: Obra Exemplo")
    assert "leitor-conversao" in cena.avisos[0][1]
    assert cena.emails == [], "tipo que não é automático não ganha o e-mail de 'tentamos de novo'"


def test_CONTROLE_desligado_a_mesma_frase_re_tenta_como_antes(monkeypatch):
    cena = _varredura(monkeypatch, tipo="leitor-conversao",
                      msg="a conversão excedeu o tempo limite", count=0)
    assert cena.retomados == [_JOB] and cena.avisos == []


def test_ligado_esgotou_o_cliente_recebe_UM_aviso_e_fica_registrado(monkeypatch):
    _liga(monkeypatch)
    cena = _varredura(monkeypatch, tipo="servidor-instavel",
                      msg=falhas.texto_da_tela("servidor-instavel"), count=2)
    assert cena.retomados == []
    assert len(cena.emails) == 1, cena.emails
    assert cena.emails[0] == {"job_id": _JOB, "tipo": "servidor-instavel",
                              "arquivo": "Planta.dwg", "terminal": True}, cena.emails
    assert ("cliente@exemplo.com", "falha_parada", _JOB) in cena.fichas, cena.fichas
    assert cena.avisos[0][0].startswith("Precisa de você: Obra Exemplo")


def test_ligado_esgotou_mas_o_cliente_ja_foi_avisado_nao_repete(monkeypatch):
    _liga(monkeypatch)
    cena = _varredura(monkeypatch, tipo="servidor-instavel",
                      msg=falhas.texto_da_tela("servidor-instavel"), count=2,
                      ja_avisou_cliente=True)
    assert cena.emails == [] and cena.avisos


def test_ligado_sem_arquivo_pra_re_tentar_o_cliente_NAO_ouve_tentamos_de_novo(monkeypatch):
    """A frase 'tentamos de novo' seria mentira: a retomada nem começou."""
    _liga(monkeypatch)
    cena = _varredura(monkeypatch, tipo="servidor-instavel",
                      msg=falhas.texto_da_tela("servidor-instavel"), count=0, retoma=False)
    assert cena.retomados == [_JOB] and cena.emails == [] and cena.avisos


def test_desligado_esgotou_ninguem_novo_e_avisado_mas_o_Pedro_ve_o_tipo(monkeypatch):
    cena = _varredura(monkeypatch, tipo="servidor-instavel",
                      msg="Processamento interrompido por reinício do servidor.", count=2)
    assert cena.emails == []
    assunto = cena.avisos[0][0]
    assert assunto.startswith("Precisa de você: Obra Exemplo")
    assert falhas.TIPOS["servidor-instavel"]["rotulo"] in assunto
    assert "terminal" not in assunto.lower()


def test_ligado_problema_do_cliente_e_para_acompanhar(monkeypatch):
    _liga(monkeypatch)
    cena = _varredura(monkeypatch, tipo="pdf-escaneado",
                      msg=falhas.texto_da_tela("pdf-escaneado"), count=0)
    assert cena.retomados == [] and cena.emails == []
    assert cena.avisos[0][0].startswith("Para acompanhar: Obra Exemplo")


# ══════════════════════════════════════════════════════════════════════════
#  7. Os pontos fora do `process_job`: freio de memória e teto de páginas
# ══════════════════════════════════════════════════════════════════════════
def _freio(monkeypatch, motivo):
    cena = types.SimpleNamespace(tela={}, logs=[], emails=[])
    monkeypatch.setattr(main.jobs, "update_field", lambda job_id, **c: cena.tela.update(c))
    monkeypatch.setattr(main, "_supabase_update", lambda *a, **k: True)
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, message, *a, **k: cena.logs.append((stage, str(message))))
    monkeypatch.setattr(main, "_email_falha_cliente",
                        lambda job_id, *a, **k: cena.emails.append(k) or True)
    main._abort_job_mem(_JOB, 3, 9, motivo=motivo)
    return cena


@pytest.mark.parametrize("motivo,tipo,antes", [
    ("projeto", "limite-memoria", "Seu projeto é grande demais"),
    ("concorrencia", "servidor-instavel", "O servidor ficou sem memória")])
def test_freio_desligado_tela_de_antes_mas_o_tipo_ja_vai_pro_log(monkeypatch, motivo, tipo, antes):
    cena = _freio(monkeypatch, motivo)
    assert cena.tela.get("error_message", "").startswith(antes), cena.tela
    assert ("falha:tipo", "tipo=%s arquivo=" % tipo) in cena.logs, cena.logs
    assert cena.emails and cena.emails[0].get("tipo") == tipo, cena.emails


@pytest.mark.parametrize("motivo,tipo", [
    ("projeto", "limite-memoria"), ("concorrencia", "servidor-instavel")])
def test_CONTROLE_freio_ligado_tela_do_catalogo(monkeypatch, motivo, tipo):
    _liga(monkeypatch)
    cena = _freio(monkeypatch, motivo)
    assert cena.tela.get("error_message") == falhas.texto_da_tela(tipo), cena.tela


def _teto(monkeypatch):
    cena = types.SimpleNamespace(gravado={}, logs=[], emails=[])
    monkeypatch.setattr(main, "_paginas_do_envio",
                        lambda fps: (main.TETO_PAGINAS_DO_ENVIO + 50,
                                     [("envio.pdf", main.TETO_PAGINAS_DO_ENVIO + 50,
                                       main.TETO_PAGINAS_DO_ENVIO + 50)]))
    monkeypatch.setattr(main, "_complement_base_has_items", lambda *a, **k: False)
    monkeypatch.setattr(main, "_supabase_update",
                        lambda t, c, v, dados, *a, **k: cena.gravado.update(dados) or True)
    monkeypatch.setattr(main, "_ler_marca_do_anexo", lambda *a, **k: (True, None))
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, message, *a, **k: cena.logs.append((stage, str(message))))
    monkeypatch.setattr(main, "_email_falha_cliente",
                        lambda job_id, *a, **k: cena.emails.append(k) or True)
    assert main._recusa_por_paginas(_JOB, ["/tmp/envio.pdf"]) is True
    return cena


def test_teto_de_paginas_desligado_tela_de_antes_e_tipo_no_log(monkeypatch):
    cena = _teto(monkeypatch)
    assert cena.gravado["error_message"] == main._mensagem_de_teto_de_paginas(
        main.TETO_PAGINAS_DO_ENVIO + 50,
        [("envio.pdf", main.TETO_PAGINAS_DO_ENVIO + 50, main.TETO_PAGINAS_DO_ENVIO + 50)])
    assert ("falha:tipo", "tipo=limite-paginas arquivo=") in cena.logs, cena.logs
    assert cena.emails[0].get("tipo") == "limite-paginas"


def test_CONTROLE_teto_de_paginas_ligado_tela_do_catalogo(monkeypatch):
    _liga(monkeypatch)
    cena = _teto(monkeypatch)
    assert cena.gravado["error_message"] == falhas.texto_da_tela("limite-paginas")


# ══════════════════════════════════════════════════════════════════════════
#  8. De ponta a ponta: o `process_job` DE VERDADE com um DWG que ninguém abre
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("aec,tipo", [(False, "leitor-dwg-versao"), (True, "dwg-autocad-mep")],
                         ids=["versao", "CONTROLE-mep"])
def test_o_motor_registra_o_tipo_do_DWG_que_nao_abriu(monkeypatch, tmp_path, aec, tipo):
    """Guarda de CALL SITE (molde: test_o_motivo_dos_dois_conversores_fica_no_log).
    A função pode estar certa e o motor nunca chamar."""
    import llm_retry

    dx._FALHA_LIBREDWG.clear()
    dx._FALHA_DETALHE.clear()
    _dwg = tmp_path / "prancha-de-teste.dwg"         # 🔒 nome neutro: repo público
    _dwg.write_bytes(b"AC1032" + b"\x00" * 64)
    logs, emails = [], []

    class _JobsMudo:
        def update_field(self, *a, **k):
            pass

    monkeypatch.setattr(dx, "convert_dwg_to_dxf", lambda *_a, **_k: None)
    monkeypatch.setattr(dx, "dwg_has_aec_markers", lambda *_a, **_k: aec)
    monkeypatch.setattr(main, "_supabase_storage_upload_prancha", lambda *a, **k: True)
    monkeypatch.setattr(socket.socket, "connect",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("rede bloqueada no guarda")))
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: _R([{"auto_resume_count": 0, "reprocess_count": 0}]))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-guarda-local")
    monkeypatch.setattr(main, "_log_error",
                        lambda stage, message, *a, **k: logs.append((stage, str(message))))
    monkeypatch.setattr(main, "_supabase_update", lambda *a, **k: None)
    monkeypatch.setattr(main, "_projeto_patch", lambda *a, **k: None)
    monkeypatch.setattr(main, "_email_falha_cliente",
                        lambda job_id, *a, **k: emails.append(k) or True)
    monkeypatch.setattr(main, "jobs", _JobsMudo())
    monkeypatch.setattr(llm_retry, "call_with_retry_stream",
                        lambda *a, **k: types.SimpleNamespace(
                            content=[types.SimpleNamespace(text="```json\n{\"items\": []}\n```")],
                            stop_reason="end_turn",
                            usage=types.SimpleNamespace(output_tokens=1, input_tokens=1)))
    try:
        main.process_job("guarda-tipo-dwg", [str(_dwg)], str(tmp_path),
                         project_type="arquitetura")
    except BaseException:
        pass        # o job termina em falha de propósito

    tipos = [m for s, m in logs if s == "falha:tipo"]
    assert tipos == ["tipo=%s arquivo=prancha-de-teste.dwg" % tipo], (
        tipos, [s for s, _ in logs][:25])
    assert emails and emails[-1].get("tipo") == tipo, emails
