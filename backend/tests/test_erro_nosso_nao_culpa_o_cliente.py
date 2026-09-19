# -*- coding: utf-8 -*-
"""Quando o defeito é NOSSO, o cliente não leva a culpa.

🩸 19/09/2026 — cliente com UM DIA de conta, segundo projeto. O motor leu as
duas pranchas dele inteiras (139 itens, 16 medidos), quebrou ao escrever a capa
da planilha por um `AttributeError` nosso, e o sistema mandou pra ele:

    "Precisamos de outro arquivo pra continuar"
    "reprocessar o mesmo arquivo não vai resolver"

O arquivo dele estava perfeito. E 19 minutos antes, o MESMO job tinha entregue
uma planilha que ele baixou.

A causa não era o texto: era falta de ESTADO. O e-mail de falha tinha dois
(`reprocessavel=True` → "coisa passageira, reprocesse"; `False` → "o problema é
o seu arquivo"), e quem escolhia era um regex de oito palavras de erro
passageiro. Nome de exceção Python não casa com nenhuma delas → cai no default
→ **o balde do arquivo ruim recebe tudo que a casa não soube classificar**.

🔑 Falta de estado não é neutra: ela tem um default, e o default aqui acusava
o cliente. O terceiro estado (`culpa_nossa`) não pede nada a ele e não fala do
arquivo dele.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
#  (1) Reconhecer o que é nosso
# ─────────────────────────────────────────────────────────────────────────────

def test_a_excecao_que_derrubou_o_job_de_hoje_e_reconhecida_como_NOSSA():
    """O texto exato que o cliente recebeu em `error_message`."""
    assert main._ERRO_DE_PROGRAMACAO_RX.search("'str' object has no attribute 'get'")


def test_as_excecoes_de_programacao_mais_comuns_sao_reconhecidas():
    for erro in ("AttributeError: 'NoneType' object has no attribute 'items'",
                 "TypeError: unsupported operand type(s) for +: 'int' and 'str'",
                 "KeyError: 'total_area'",
                 "IndexError: list index out of range",
                 "NameError: name 'x' is not defined",
                 "'NoneType' object is not subscriptable",
                 "generate_spreadsheet() missing 1 required positional argument"):
        assert main._ERRO_DE_PROGRAMACAO_RX.search(erro), erro


def test_CONTROLE_mensagem_NOSSA_pro_cliente_nao_e_confundida_com_bug():
    """🪤 O regex decide o tom do e-mail. Se ele casasse com as mensagens que a
    casa escreve em português, todo erro de arquivo viraria "a culpa foi nossa"
    e o cliente nunca saberia o que fazer."""
    for texto in (
            "⚠ Não conseguimos abrir o seu DWG automaticamente. Exporte em DXF.",
            "O arquivo ficou grande demais pra processar com segurança.",
            "Não saiu nenhuma quantidade do desenho que lemos.",
            "A IA está sobrecarregada no momento — reprocessar costuma resolver.",
            "Tivemos um problema técnico do nosso lado; mande o mesmo arquivo de novo."):
        assert not main._ERRO_DE_PROGRAMACAO_RX.search(texto), texto


def test_a_DECISAO_manda_cada_falha_pro_balde_certo():
    """🩸 A sabotagem provou que eu tinha guardado o RAMO e não a DECISÃO:
    trocar a escolha por `False` deixava os dez guardas verdes. A classificação
    virou função justamente pra este guarda poder CHAMÁ-LA."""
    assert main.como_classificar_a_falha("'str' object has no attribute 'get'") == "nosso"
    assert main.como_classificar_a_falha("KeyError: 'total_area'") == "nosso"
    assert main.como_classificar_a_falha(
        "A IA está sobrecarregada no momento") == "passageiro"
    assert main.como_classificar_a_falha(
        "O servidor foi reiniciado no meio do processamento") == "passageiro"
    assert main.como_classificar_a_falha(
        "⚠ Não conseguimos abrir o seu DWG automaticamente") == "arquivo"
    assert main.como_classificar_a_falha("") == "arquivo"


def test_CONTROLE_o_fim_do_job_USA_a_classificacao():
    """🪤 A sabotagem W07 sobreviveu a tudo: trocar a decisão por `False` lá
    dentro do `except` de 5.800 linhas do `process_job` deixava os guardas
    verdes, porque bancada nenhuma executa aquele trecho. Então o guarda cobra
    o FATO onde ele mora — e lê o código SEM comentário, pra não aprovar a
    própria anotação (5ª vez nesta casa)."""
    import io
    import os as _os
    import re as _re
    from _corpo import sem_comentarios

    fonte = io.open(_os.path.join(_os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))), "main.py"), encoding="utf-8").read()
    limpo = sem_comentarios(fonte)
    i = limpo.index("_email_falha_cliente(job_id, reprocessavel=_reproc")
    vizinhanca = limpo[max(0, i - 900):i]
    assert "como_classificar_a_falha(" in vizinhanca, (
        "o fim do job parou de perguntar de quem é a culpa antes de avisar o "
        "cliente — sem isso, defeito nosso volta a sair como 'troque o arquivo'")
    assert _re.search(r"_nosso\s*=\s*\(?_classe\s*==\s*[\"']nosso", vizinhanca), (
        "a resposta da classificação não está mais ligada ao e-mail de culpa nossa")


def test_o_balde_que_ACUSA_o_cliente_e_o_ultimo_da_fila():
    """🔑 O default é o que acusa — então ele tem que ser o último a ser
    checado. Uma exceção nossa que por acaso cite a palavra 'conexão' continua
    sendo nossa; o contrário faria o cliente levar a culpa de novo."""
    assert main.como_classificar_a_falha(
        "AttributeError: conexão object has no attribute 'get'") == "nosso"


# ─────────────────────────────────────────────────────────────────────────────
#  (2) O que o cliente lê
# ─────────────────────────────────────────────────────────────────────────────

def _email(culpa_nossa=True, ja_entregou=False, reprocessavel=False):
    return main._build_falha_email("Fulano", "projeto de teste", reprocessavel,
                                   error_hint="'str' object has no attribute 'get'",
                                   job_id="abc123",
                                   culpa_nossa=culpa_nossa, ja_entregou=ja_entregou)


def test_o_email_de_culpa_NOSSA_nao_pede_nada_ao_cliente():
    assunto, html = _email()
    baixado = html.lower()
    assert "problema foi nosso" in assunto.lower(), assunto
    assert "não precisa fazer nada" in baixado, html[:600]
    for proibido in ("trocar o arquivo", "precisamos de outro arquivo",
                     "reenviar", "exporte em dxf", "outra prancha",
                     "reprocessar o mesmo arquivo"):
        assert proibido not in baixado, (
            "o e-mail de defeito NOSSO mandou o cliente mexer no arquivo dele: %r" % proibido)


def test_o_email_de_culpa_NOSSA_nao_despeja_jargao():
    """O cliente não tem que ler o nome da nossa exceção.

    🩸 A 1ª versão deste guarda só olhava UM dos dois textos (o de quem ainda
    não tinha planilha) — e a sabotagem passou o jargão pelo outro ramo sem
    ninguém reprovar. Os dois ramos, sempre."""
    for entregou in (False, True):
        _assunto, html = _email(ja_entregou=entregou)
        for jargao in ("AttributeError", "object has no attribute", "Traceback", "str'"):
            assert jargao not in html, (entregou, jargao)


def test_quando_a_planilha_JA_FOI_ENTREGUE_o_email_reconhece():
    """🩸 O cliente tinha BAIXADO a planilha 19 minutos antes de receber
    'tivemos um problema'. Dizer que não deu certo, pra quem está com o
    resultado aberto, é a casa desmentindo o que ela mesma entregou."""
    _a, html = _email(ja_entregou=True)
    assert "continua valendo" in html, html[:600]
    _a2, html2 = _email(ja_entregou=False)
    assert "continua valendo" not in html2, html2[:600]


def test_CONTROLE_os_outros_dois_estados_continuam_intactos():
    """Terceiro estado não pode ter comido os outros dois."""
    _a, passageiro = main._build_falha_email("Fulano", "p", True)
    assert "reprocessar" in passageiro.lower()
    _a2, arquivo = main._build_falha_email("Fulano", "p", False,
                                           error_hint="não conseguimos abrir o seu DWG")
    assert "dxf" in arquivo.lower(), "o ramo de arquivo perdeu a orientação"
    assert "problema foi nosso" not in arquivo.lower()


# ─────────────────────────────────────────────────────────────────────────────
#  (3) O caminho até o envio
# ─────────────────────────────────────────────────────────────────────────────

def test_o_envio_usa_o_kind_proprio(monkeypatch):
    """🪤 Sem kind próprio, o caso vira mais um 'erro_trocar' no registro e a
    Central de E-mails nunca mostra que a casa errou."""
    visto = {}
    monkeypatch.setattr(main, "_send_email_smtp",
                        lambda to, s, h, **k: visto.update(k) or True)
    monkeypatch.setattr(main, "_resolve_client_name", lambda *a, **k: "Fulano")
    monkeypatch.setattr(main, "_falha_emailed", set())
    monkeypatch.setattr(main, "_rows_do_job_de_falha", None, raising=False)

    import json as _j
    import urllib.request as _u

    class _Resp:
        def read(self):
            return _j.dumps([{"user_email": "c@exemplo.com", "user_name": "Fulano",
                              "project_name": "p", "parent_job_id": None,
                              "reprocess_count": 0, "created_at": "",
                              "error_message": "'str' object has no attribute 'get'",
                              "items_count": 76}]).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(_u, "urlopen", lambda *a, **k: _Resp())
    main._email_falha_cliente("jobteste9", reprocessavel=False, culpa_nossa=True)
    assert visto.get("log_kind") == "erro_nosso", visto


def test_a_ficha_do_email_novo_existe_no_catalogo():
    """🪤 Tipo que sai e não está no catálogo aparece como "Fora do catálogo" na
    Central — e a ficha nova é justamente a que conta quando a casa errou."""
    fichas = {c["key"] for c in main._EMAIL_CATALOG}
    assert "erro_nosso" in fichas, "o e-mail de culpa nossa ficou fora do catálogo"


def test_o_preview_do_admin_abre_o_email_novo():
    """🪤 A 1ª versão deste guarda tinha um ramo de fallback que passava
    sozinho — guarda vacuoso é pior que guarda nenhum, porque dá conforto.
    Aqui o preview REAL é renderizado: ficha no catálogo sem preview é botão
    que abre "(erro)" na cara do Pedro."""
    assunto, html = main._render_email_by_type("erro_nosso")
    assert "nosso" in assunto.lower(), assunto
    assert "não precisa fazer nada" in html.lower(), html[:400]
    assert "trocar o arquivo" not in html.lower()
