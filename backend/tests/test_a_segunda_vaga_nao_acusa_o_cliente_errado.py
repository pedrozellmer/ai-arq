# -*- coding: utf-8 -*-
"""Dois projetos podem rodar ao mesmo tempo — sem mentir pra ninguém.

🩸 17/09/2026. A fila de UM POR VEZ custou 58 minutos de espera a um cliente
num dia de três projetos. O plano hoje é 4 GB e a medição na fonte (métricas
do Render) diz que o pior job do dia ocupou 1,13 GB — 26% do container, com o
servidor ocioso em 130 MB. Dois cabem. Mas abrir a 2ª vaga acorda dois
defeitos que **não existiam** enquanto era um por vez:

  1. **A porta falhava ABERTA.** A admissão perguntava `not _mem_pressure(0.55)`,
     e `_mem_pressure` devolve False quando NÃO CONSEGUE MEDIR — de propósito,
     pra ignorância não travar o produto. Invertendo: num container sem cgroup
     legível a 2ª vaga abriria às cegas. E não é hipótese confortável: a fração
     nunca foi registrada em lugar nenhum e o freio de 85% nunca disparou na
     história (0 linhas em `error_log`), então **ninguém nunca viu esse
     instrumento funcionar**.

  2. **O freio acusava o cliente errado.** `_mem_pressure` lê a fração do
     CONTAINER, não a do job. Com dois no ar, o job A podia morrer pela memória
     do job B e o cliente A receber *"Seu projeto é grande demais. Divida em
     2-3 envios menores"* — acusação falsa sobre um arquivo sem defeito nenhum.
     Com uma vaga só era impossível: a memória era toda dele, a frase era
     verdade.

🔑 Todo guarda daqui CHAMA o código. Os dois que não têm como chamar (os
pontos de freio moram dentro de um `process_job` de 3.000 linhas) leem a
**AST**, não o texto — guarda que lê fonte já nos traiu três vezes este mês.
"""
import ast
import io
import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

_FONTE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "main.py")


@pytest.fixture(autouse=True)
def _vagas_limpas(monkeypatch):
    """Cada teste começa com o contador zerado e devolve o mundo como achou.

    🪤 E NINGUÉM aqui toca a rede. `_anotar_vaga` chama `_log_error`, que faz um
    POST com timeout de **20 s** — enquanto três guardas deste arquivo dão
    `join(timeout=10)` na thread que o dispara. Numa máquina com DNS lento o join
    estoura antes do POST, a thread não terminou, e o teste quebra sem existir
    defeito nenhum. Conferido no banco que nada foi gravado (a anon não passa no
    RLS do `error_log`), então isto é sobre FLAPPING, não sobre sujeira — mas os
    dois motivos levam ao mesmo lugar: guarda não fala com servidor de verdade.
    """
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    _antes = main._JOBS_RODANDO
    _teto = main._JOBS_SIMULTANEOS
    main._JOBS_RODANDO = 0
    main._VAGA_EXTRA.set(False)
    main._FREIO_POUPOU.set(0)
    main._DIVIDIU_O_SERVIDOR.set(False)
    # 🔒 Nada aqui pode sair da máquina. `_abort_job_mem` dispara `_notify_admin`
    # e `_email_falha_cliente` de VERDADE; hoje eles morrem por falta de
    # credencial de SMTP, mas quem tiver o .env completo e rodar a bancada manda
    # alarme falso pro Pedro. Guarda que depende de a credencial estar ausente
    # não é guarda seguro, é guarda com sorte.
    monkeypatch.setattr(main, "_notify_admin", lambda *a, **k: True)
    monkeypatch.setattr(main, "_email_falha_cliente", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supabase_update", lambda *a, **k: None)
    monkeypatch.setattr(main, "_supabase_insert", lambda *a, **k: None)
    # 🩸 18/09: a fila de senhas FALTAVA aqui, e isso não é detalhe. Uma senha
    # deixada pra trás por um teste fica na CABEÇA da fila e faz todo
    # `_esperar_vaga` seguinte esperar pra sempre — inclusive um que usa o
    # `_espera_s` padrão de 2 s e não tem timeout. A sabotagem N03 provou:
    # o teste dela falhava certinho e a SUÍTE INTEIRA travava depois, derrubando
    # a corrida de mutação em 900 s. Guarda que suja estado compartilhado
    # contamina o vizinho — a mesma doença que este arquivo persegue no produto.
    main._FILA_DE_SENHAS.clear()
    yield
    main._JOBS_RODANDO = _antes
    main._JOBS_SIMULTANEOS = _teto
    main._VAGA_EXTRA.set(False)
    main._FREIO_POUPOU.set(0)
    main._DIVIDIU_O_SERVIDOR.set(False)
    main._FILA_DE_SENHAS.clear()


# ══════════════════════════════════════════════════════════════════════════
#  1. A PORTA FALHA FECHADA — o defeito que a revisão não pegou
# ══════════════════════════════════════════════════════════════════════════
def test_sem_conseguir_medir_a_memoria_a_2a_vaga_NAO_abre(monkeypatch):
    """O coração. Sem leitura de cgroup, a resposta é NÃO — e o produto volta
    a se comportar exatamente como hoje (um por vez), que é o pior caso
    aceitável. Abrir às cegas seria trocar espera por OOM."""
    monkeypatch.setattr(main, "_container_mem_frac", lambda: None)
    assert main._cabe_um_segundo_job() is False
    assert main._tem_vaga_agora(1) is False


def test_CONTROLE_a_regua_ANTIGA_abriria_a_vaga_as_cegas(monkeypatch):
    """Controle positivo: prova que o guarda acima prende algo de verdade.
    Com a memória ilegível, a fórmula que eu tinha escrito (`not
    _mem_pressure`) diz SIM. Se um dia `_cabe_um_segundo_job` voltar a ser
    isso, o teste de cima fica vermelho — e este explica por quê."""
    monkeypatch.setattr(main, "_container_mem_frac", lambda: None)
    assert main._mem_pressure(main._MEM_TETO_2O_JOB) is False
    assert (not main._mem_pressure(main._MEM_TETO_2O_JOB)) is True


def test_com_memoria_folgada_a_2a_vaga_abre(monkeypatch):
    """26% foi o pior job medido hoje; abaixo do teto de 55% cabe mais um."""
    monkeypatch.setattr(main, "_container_mem_frac", lambda: 0.26)
    assert main._cabe_um_segundo_job() is True
    assert main._tem_vaga_agora(1) is True


def test_com_memoria_apertada_a_2a_vaga_NAO_abre(monkeypatch):
    monkeypatch.setattr(main, "_container_mem_frac", lambda: 0.60)
    assert main._cabe_um_segundo_job() is False
    assert main._tem_vaga_agora(1) is False


def test_o_teto_da_2a_vaga_e_uma_FRONTEIRA_nao_um_enfeite(monkeypatch):
    """Exatamente no teto NÃO entra; um fio abaixo entra. Um `<=` no lugar do
    `<` passaria despercebido em qualquer teste de número redondo."""
    monkeypatch.setattr(main, "_container_mem_frac", lambda: main._MEM_TETO_2O_JOB)
    assert main._cabe_um_segundo_job() is False
    monkeypatch.setattr(main, "_container_mem_frac",
                        lambda: main._MEM_TETO_2O_JOB - 0.001)
    assert main._cabe_um_segundo_job() is True


def test_o_PRIMEIRO_job_entra_mesmo_com_a_memoria_no_teto(monkeypatch):
    """Se o primeiro dependesse da memória, um pico de outra coisa (backup,
    deploy, varredura) travaria o produto inteiro — a trava viraria a queda
    que ela deveria evitar."""
    monkeypatch.setattr(main, "_container_mem_frac", lambda: 0.99)
    assert main._tem_vaga_agora(0) is True


def test_a_terceira_vaga_nunca_abre(monkeypatch):
    monkeypatch.setattr(main, "_container_mem_frac", lambda: 0.01)
    assert main._tem_vaga_agora(2) is False
    assert main._tem_vaga_agora(7) is False


def test_desligar_pelo_env_volta_pro_um_por_vez(monkeypatch):
    """`JOBS_SIMULTANEOS=1` tem que devolver o comportamento antigo mesmo com
    memória sobrando — é a saída de emergência sem deploy."""
    monkeypatch.setattr(main, "_JOBS_SIMULTANEOS", 1)
    monkeypatch.setattr(main, "_container_mem_frac", lambda: 0.01)
    assert main._tem_vaga_agora(1) is False
    assert main._tem_vaga_agora(0) is True


# ══════════════════════════════════════════════════════════════════════════
#  2. O TETO DE VAGAS NÃO ACEITA APOSTA
# ══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("digitado,esperado", [
    ("1", 1), ("2", 2),
    ("3", 2), ("4", 2), ("99", 2),   # aposta pra cima é aparada
    ("0", 1), ("-5", 1),             # aposta pra baixo também
    ("", 2), ("dois", 2), (None, 2),  # lixo cai no padrão
])
def test_o_env_nao_consegue_apostar_alto(monkeypatch, digitado, esperado):
    """O env serve pra DESLIGAR a concorrência sem deploy, não pra apostar 4 —
    isso viraria OOM sem passar por revisão nenhuma."""
    if digitado is None:
        monkeypatch.delenv("JOBS_SIMULTANEOS", raising=False)
    else:
        monkeypatch.setenv("JOBS_SIMULTANEOS", digitado)
    assert main._quantos_jobs_simultaneos() == esperado


# ══════════════════════════════════════════════════════════════════════════
#  3. O FREIO NÃO MATA O JOB DO VIZINHO — o achado da revisão
# ══════════════════════════════════════════════════════════════════════════
def test_sozinho_o_freio_acusa_o_projeto_porque_e_VERDADE():
    """Com um job só, a memória era toda dele: "seu projeto é grande demais" é
    uma afirmação honesta, e o freio age como sempre agiu."""
    main._JOBS_RODANDO = 1
    main._VAGA_EXTRA.set(False)
    assert main._decisao_do_freio() == "projeto"


def test_quem_JA_ESTAVA_rodando_NAO_morre_pela_memoria_do_vizinho():
    """O achado. Dois no ar; este aqui não pegou a vaga extra — ou seja, ia
    rodar de qualquer jeito. O freio tem que poupá-lo: matá-lo seria acusar um
    cliente de um arquivo grande que não é dele."""
    main._JOBS_RODANDO = 2
    main._VAGA_EXTRA.set(False)
    assert main._decisao_do_freio() is None


def test_o_SOBREVIVENTE_nao_e_acusado_quando_o_vizinho_sai(monkeypatch):
    """🚨 18/09, 2ª revisão adversarial — o defeito voltando pela porta dos
    fundos, e o pior de todos, porque é EXATAMENTE o que este commit existe
    pra matar.

    A decisão lia `_JOBS_RODANDO` do INSTANTE. O contador cai no segundo em que
    o vizinho sai; a memória do contêiner NÃO cai junto (o job que saiu devolve
    objetos ao alocador, e as conversões dele foram movidas pro work_dir). Então
    o sobrevivente batia de novo, lia "estou sozinho", e recebia *"Seu projeto é
    grande demais. Divida em 2-3 envios"* — acusação falsa sobre um arquivo que
    ninguém mediu.

    🪤 Nenhum dos 54 guardas pegava, porque todos fixavam o contador na mão e
    NENHUM simulava o vizinho saindo. É esse movimento que este teste faz."""
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    main._VAGA_EXTRA.set(False)          # este é o que JÁ ESTAVA rodando
    main._FREIO_POUPOU.set(0)
    main._DIVIDIU_O_SERVIDOR.set(False)

    main._JOBS_RODANDO = 2               # dividindo o servidor
    assert main._decisao_do_freio() is None, "a 1ª batida tinha que poupar"

    main._JOBS_RODANDO = 1               # 🔑 o vizinho SAIU; a memória não saiu
    assert main._decisao_do_freio() == "concorrencia", (
        "o sobrevivente levou a acusação de 'projeto grande demais' — o defeito "
        "que o commit inteiro existe pra impedir, entrando por outra porta")


def test_quem_pegou_a_vaga_extra_NUNCA_e_acusado_nem_sozinho(monkeypatch):
    """O outro lado do mesmo defeito: o job que furou a fila dividiu o contêiner
    desde o primeiro segundo. Se o incumbente terminar antes dele, ele fica
    sozinho — e mesmo assim não pode ser acusado do tamanho do próprio arquivo,
    porque a memória que ele encontrou nunca foi só dele."""
    monkeypatch.setattr(main, "_container_mem_frac", lambda: 0.10)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    main._JOBS_RODANDO = 1
    main._FILA_DE_SENHAS.clear()
    main._esperar_vaga(_espera_s=0.01)               # entra na 2ª vaga
    assert main._VAGA_EXTRA.get() is True
    assert main._DIVIDIU_O_SERVIDOR.get() is True

    main._JOBS_RODANDO = 1                           # o incumbente terminou
    assert main._decisao_do_freio() == "concorrencia"
    main._liberar_vaga()


def test_a_marca_de_ter_DIVIDIDO_nao_vaza_entre_threads():
    """A marca é da vida DESTE job, não do processo. Se fosse global, o projeto
    seguinte herdaria "dividiu o servidor" de um que já terminou — e a decisão
    do freio passaria a depender do passado de outro cliente.

    🩸 A sabotagem P04 (trocar o ContextVar por um global) SOBREVIVEU à primeira
    versão destes guardas, porque o controle setava e lia na MESMA thread, onde
    os dois se comportam igual. É aqui que a escolha do ContextVar vira carga."""
    main._DIVIDIU_O_SERVIDOR.set(True)
    main._VAGA_EXTRA.set(False)
    main._FREIO_POUPOU.set(0)
    main._JOBS_RODANDO = 1
    visto = {}

    def _job_novo():
        visto["dividiu"] = main._DIVIDIU_O_SERVIDOR.get()
        visto["decisao"] = main._decisao_do_freio()

    t = threading.Thread(target=_job_novo)
    t.start()
    t.join(timeout=10)
    assert visto["dividiu"] is False, \
        "o job novo herdou a marca de um projeto que já terminou"
    assert visto["decisao"] == "projeto"


def test_CONTROLE_quem_rodou_SOZINHO_a_vida_toda_continua_sendo_acusado():
    """Controle positivo: sem ele, bastaria devolver "concorrencia" sempre e os
    dois guardas acima passariam. Projeto que nunca dividiu o servidor É grande
    demais de verdade, e a orientação de dividir é a útil."""
    main._VAGA_EXTRA.set(False)
    main._FREIO_POUPOU.set(0)
    main._DIVIDIU_O_SERVIDOR.set(False)
    main._JOBS_RODANDO = 1
    assert main._decisao_do_freio() == "projeto"


def test_poupar_NAO_e_pra_sempre_senao_o_servidor_cai_pra_todo_mundo(monkeypatch):
    """O buraco que poupar sem limite abriria: se o vizinho já saiu do laço de
    pranchas, ele nunca mais passa num ponto de freio e ninguém aborta. A
    segunda batida tem que parar o job — o que não pode voltar é a ACUSAÇÃO."""
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    main._JOBS_RODANDO = 2
    main._VAGA_EXTRA.set(False)
    main._FREIO_POUPOU.set(0)
    assert main._decisao_do_freio() is None, "a 1ª batida tinha que poupar"
    assert main._decisao_do_freio() == "concorrencia", \
        "a 2ª batida tem que parar o job, senão a memória fica em 85% sem dono"
    assert main._decisao_do_freio() == "concorrencia"


def test_a_conta_de_chances_e_POR_JOB_nao_do_processo():
    """Se o contador fosse global, o segundo projeto do dia nasceria sem
    nenhuma chance e seria abortado na primeira batida."""
    main._JOBS_RODANDO = 2
    main._VAGA_EXTRA.set(False)
    main._FREIO_POUPOU.set(main._FREIO_CHANCES)
    visto = {}

    def _outro_job():
        visto["decisao"] = main._decisao_do_freio()

    t = threading.Thread(target=_outro_job)
    t.start()
    t.join(timeout=10)
    assert visto["decisao"] is None, "o job novo herdou as chances gastas do outro"


def test_quem_FUROU_A_FILA_e_quem_para():
    """O outro lado: quem só está ali porque a gente abriu a 2ª vaga é quem
    cede o lugar — e com mensagem que não culpa o arquivo dele."""
    main._JOBS_RODANDO = 2
    main._VAGA_EXTRA.set(True)
    assert main._decisao_do_freio() == "concorrencia"


def test_a_marca_da_vaga_extra_NAO_vaza_entre_threads():
    """`_VAGA_EXTRA` é ContextVar justamente pra isso. Se fosse global, o
    segundo job marcaria o primeiro e o freio pararia o cliente errado — o
    defeito exato que este arquivo existe pra impedir."""
    main._JOBS_RODANDO = 2
    main._VAGA_EXTRA.set(True)
    visto = {}

    def _outro_job():
        visto["extra"] = main._VAGA_EXTRA.get()
        visto["decisao"] = main._decisao_do_freio()

    t = threading.Thread(target=_outro_job)
    t.start()
    t.join(timeout=10)
    assert visto["extra"] is False, "a marca de uma thread contaminou a outra"
    assert visto["decisao"] is None


# ══════════════════════════════════════════════════════════════════════════
#  4. A MENSAGEM QUE CHEGA NO CLIENTE
# ══════════════════════════════════════════════════════════════════════════
def _mensagem_gravada(monkeypatch, motivo):
    """Roda `_abort_job_mem` de verdade e devolve o texto que ele gravaria."""
    guardado = {}

    def _finge_update(job_id, **campos):
        guardado.update(campos)

    monkeypatch.setattr(main.jobs, "update_field", _finge_update)
    monkeypatch.setattr(main, "_supabase_update",
                        lambda *a, **k: guardado.update(a[3] if len(a) > 3 else {}))
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    main._abort_job_mem("job-de-teste", 3, 9, motivo=motivo)
    return guardado.get("error_message", "")


def test_com_dois_projetos_a_mensagem_NAO_culpa_o_arquivo_do_cliente(monkeypatch):
    """O cliente não pode ser mandado dividir um arquivo que não tem defeito."""
    msg = _mensagem_gravada(monkeypatch, "concorrencia")
    assert msg, "não gravou mensagem nenhuma"
    baixo = msg.lower()
    assert "grande demais" not in baixo, "voltou a acusar o tamanho do arquivo"
    assert "nosso lado" in baixo, "não assume de quem é a falha"
    # 🪤 A orientação de dividir pode aparecer — mas como plano B ("se repetir"),
    # nunca como diagnóstico. O que este guarda proíbe é a AFIRMAÇÃO sobre o
    # arquivo do cliente, não a palavra.
    assert "se repetir" in baixo or "divida" not in baixo


def test_sozinho_a_mensagem_CONTINUA_mandando_dividir(monkeypatch):
    """Controle positivo do guarda acima: quando a acusação é verdadeira, a
    orientação útil tem que continuar saindo. Um guarda que só proíbe texto
    passaria verde com a mensagem apagada."""
    msg = _mensagem_gravada(monkeypatch, "projeto")
    assert "grande demais" in msg.lower()
    assert "divida" in msg.lower()


def test_o_EMAIL_nao_desmente_a_tela(monkeypatch):
    """🩸 18/09, revisão adversarial — o achado mais sutil do commit.

    `_abort_job_mem` passou a escrever DUAS mensagens na tela, mas o e-mail
    escolhe o texto por palavra-chave do `error_message`. A frase nova de
    concorrência não casa com nenhum ramo e caía no genérico de "PDF escaneado":
    a tela dizia *"pode reenviar"* e o e-mail, no mesmo minuto, *"Reprocessar não
    resolve este caso: reenvie a planta exportada direto do CAD"*. Duas mentiras
    numa — contradiz a tela e AFIRMA uma causa sobre o arquivo do cliente que
    ninguém mediu (regra nº1).

    🔑 O guarda roda o construtor do e-mail DE VERDADE."""
    msg_conc = ("O servidor ficou sem memória enquanto processava mais de um "
                "projeto ao mesmo tempo. Isso é do nosso lado.")
    _, html = main._build_falha_email("Cliente", "Projeto X", True,
                                      error_hint=msg_conc)
    corpo = html.lower()
    assert "reprocessar" in corpo and "resolve" in corpo, \
        "o e-mail de concorrência não diz que reprocessar resolve"
    assert "escaneada" not in corpo and "sem cotas" not in corpo, \
        "o e-mail inventou um diagnóstico sobre o arquivo do cliente (regra nº1)"


def test_o_EMAIL_de_projeto_grande_CONTINUA_orientando(monkeypatch):
    """Controle positivo: quando a acusação é verdadeira, a orientação útil tem
    que continuar saindo — senão o guarda acima passaria com o e-mail mudo."""
    msg_proj = ("Seu projeto é grande demais pra processar de uma vez e chegou "
                "perto do limite de memória do servidor.")
    _, html = main._build_falha_email("Cliente", "Projeto X", False,
                                      error_hint=msg_proj)
    assert "purge" in html.lower() or "prancha necessária" in html.lower()


@pytest.mark.parametrize("motivo,espera_reprocessavel", [
    ("concorrencia", True),    # a culpa foi nossa: reprocessar É a saída
    ("projeto", False),        # o arquivo é grande mesmo: reprocessar não resolve
])
def test_o_aborto_ENTREGA_ao_email_o_que_a_tela_disse(monkeypatch, motivo,
                                                      espera_reprocessavel):
    """A ligação ponta a ponta, rodando `_abort_job_mem` DE VERDADE e capturando
    o que chegou no e-mail.

    🩸 18/09, 2ª revisão: o guarda anterior fixava `reprocessavel=True` na mão e
    chamava o construtor direto — ou seja, provava que o RAMO existe, não que o
    aborto usa o ramo certo. Um `reprocessavel=False` fixo voltaria a fazer o
    e-mail desmentir a tela com este guarda VERDE."""
    capturado = {}
    monkeypatch.setattr(main.jobs, "update_field",
                        lambda job_id, **c: capturado.update(c))
    # 🪤 `**k` de propósito: dublê com assinatura EXATA desarma calado quando o
    # original ganha parâmetro (aconteceu 2× em 3 dias; em 18/09 derrubou 12
    # guardas de uma vez). `culpa_nossa` entrou em 19/09.
    monkeypatch.setattr(main, "_email_falha_cliente",
                        lambda job_id, reprocessavel=True, **k: capturado.update(
                            {"reprocessavel": reprocessavel}))
    main._abort_job_mem("jobteste1", 2, 7, motivo=motivo)
    assert capturado.get("reprocessavel") is espera_reprocessavel, (
        f"motivo={motivo}: o e-mail recebeu "
        f"reprocessavel={capturado.get('reprocessavel')} e a tela disse outra coisa")
    # e a tela e o e-mail têm que contar a MESMA história
    na_tela = (capturado.get("error_message") or "").lower()
    if motivo == "concorrencia":
        assert "pode reenviar" in na_tela and "grande demais" not in na_tela
    else:
        assert "grande demais" in na_tela


def test_o_freio_de_email_NAO_depende_mais_da_ordem_de_chegada():
    """🚨 18/09, 2ª revisão adversarial. O freio anti-spam do e-mail de falha
    tinha a premissa escrita no próprio comentário: *"Como o semáforo processa 1
    por vez na ORDEM, basta avisar a falha MAIS ANTIGA do usuário na janela"* —
    e este commit matou essa premissa.

    Com duas vagas, quem falha primeiro costuma ser o mais NOVO (é ele quem pega
    a vaga extra e é o primeiro que o freio manda parar). Com o filtro por ordem
    de criação, nenhum dos dois enxergava o outro e o cliente levava DOIS avisos
    no mesmo incidente — a regressão exata do caso cliente-88."""
    url = main._url_de_falha_recente("alguem@exemplo.com",
                                     "2026-09-18T00:00:00+00:00", "job1234")
    assert "created_at=lt." not in url, \
        "o freio voltou a olhar só pra trás no tempo de criação"
    assert "created_at=gte." in url, "perdeu a janela de 15 min"
    assert "status=eq.error" in url
    assert "job_id=neq.job1234" in url, "o projeto ia encontrar a si mesmo"


def test_o_freio_de_email_ainda_e_POR_CLIENTE():
    """Controle positivo: sem o filtro por e-mail, a falha de um cliente calaria
    o aviso de outro — o remédio seria pior que o spam."""
    url = main._url_de_falha_recente("fulano@exemplo.com",
                                     "2026-09-18T00:00:00+00:00", "jobABCD")
    assert "user_email=eq.fulano%40exemplo.com" in url


def test_o_aborto_LIGA_o_motivo_ao_email():
    """A ligação, pela AST: `_abort_job_mem` tem que decidir `reprocessavel` a
    partir do `motivo`. Voltar a fixar `False` reabre a contradição — e os dois
    guardas acima continuariam verdes, porque chamam o construtor direto."""
    fn = next(n for n in ast.walk(_arvore())
              if isinstance(n, ast.FunctionDef) and n.name == "_abort_job_mem")
    chamadas = [c for c in ast.walk(fn)
                if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                and c.func.id == "_email_falha_cliente"]
    assert chamadas, "o aborto por memória parou de avisar o cliente por e-mail"
    for c in chamadas:
        kw = {k.arg: k for k in c.keywords}
        assert "reprocessavel" in kw, "o e-mail perdeu o parâmetro que escolhe o texto"
        assert not isinstance(kw["reprocessavel"].value, ast.Constant), \
            "`reprocessavel` voltou a ser fixo — o e-mail desmente a tela de novo"


def test_o_motivo_PADRAO_e_o_de_sempre(monkeypatch):
    """Chamada sem `motivo` não pode virar a mensagem nova por acidente."""
    guardado = {}
    monkeypatch.setattr(main.jobs, "update_field",
                        lambda job_id, **c: guardado.update(c))
    monkeypatch.setattr(main, "_supabase_update", lambda *a, **k: None)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    main._abort_job_mem("job-de-teste", 1, 2)
    assert "grande demais" in guardado.get("error_message", "").lower()


# ══════════════════════════════════════════════════════════════════════════
#  5. O QUE A 2ª VAGA ACORDA NO RESTO DO MOTOR (regra dura nº2)
# ══════════════════════════════════════════════════════════════════════════
def test_o_motivo_da_falha_de_um_projeto_NAO_vaza_pro_outro(monkeypatch):
    """Com um projeto por vez, um global bastava pra carregar o motivo da falha
    de upload até quem registra. Com dois, o projeto B zera (ou sobrescreve) o
    motivo do projeto A — e A grava no registro dele a falha DE OUTRO CLIENTE,
    ou um "não registrado" mentiroso. Isolamento de projetos é regra dura nº2.

    🔑 Chama o upload de verdade, com a rede quebrada de propósito."""
    monkeypatch.setattr(main, "_supa_log", lambda *a, **k: None)

    class _Falha(Exception):
        pass

    def _rede_quebrada(req, *a, **k):
        # 🩸 A 1ª versão deste guarda fazia os DOIS projetos falharem com o MESMO
        # texto — e aí a contaminação ficava invisível: A lia a string de B e ela
        # era igual à dele. A sabotagem M28 sobreviveu por causa disso. Falha de
        # projetos diferentes tem que ter texto diferente, senão o teste não
        # consegue distinguir vazamento de funcionamento.
        alvo = getattr(req, "full_url", "") or ""
        raise _Falha("falha-do-B" if "jobBBBB" in alvo else "falha-do-A")

    monkeypatch.setattr(main.urllib.request, "urlopen", _rede_quebrada)
    monkeypatch.setattr(main.os.path, "getsize", lambda p: 1048576)
    monkeypatch.setattr(main, "open", lambda *a, **k: io.BytesIO(b"x"), raising=False)

    visto = {}

    def _projeto_A():
        main._supabase_storage_upload_prancha("/tmp/a.dxf", "jobAAAA", "a.dxf")
        visto["A_antes"] = main._FALHA_UPLOAD_DO_JOB.get()
        pronto.wait(timeout=10)          # deixa o B correr no meio
        visto["A_depois"] = main._FALHA_UPLOAD_DO_JOB.get()

    def _projeto_B():
        main._supabase_storage_upload_prancha("/tmp/b.dxf", "jobBBBB", "b.dxf")
        visto["B"] = main._FALHA_UPLOAD_DO_JOB.get()
        pronto.set()

    pronto = threading.Event()
    ta = threading.Thread(target=_projeto_A)
    tb = threading.Thread(target=_projeto_B)
    ta.start()
    time.sleep(0.05)
    tb.start()
    ta.join(timeout=20)
    tb.join(timeout=20)

    assert "falha-do-A" in (visto.get("A_antes") or ""), \
        "o projeto A nem registrou a própria falha"
    assert "falha-do-B" in (visto.get("B") or ""), "o projeto B não falhou"
    assert visto["A_depois"] == visto["A_antes"], \
        "o projeto B apagou/trocou o motivo da falha do projeto A"
    assert "falha-do-B" not in visto["A_depois"], \
        "o projeto A ficou com a falha DE OUTRO CLIENTE no próprio registro"


def test_CONTROLE_o_global_e_mesmo_compartilhado(monkeypatch):
    """Controle positivo: prova que o teste acima mede algo. O global que o
    motor lia ANTES é de verdade compartilhado entre threads — se fosse
    isolado sozinho, o guarda de cima passaria sem mérito nenhum."""
    main._ULTIMA_FALHA_UPLOAD_PRANCHA = "de-quem-escreveu-primeiro"
    visto = {}

    def _outra_thread():
        visto["leu"] = main._ULTIMA_FALHA_UPLOAD_PRANCHA

    t = threading.Thread(target=_outra_thread)
    t.start()
    t.join(timeout=10)
    assert visto["leu"] == "de-quem-escreveu-primeiro"
    main._ULTIMA_FALHA_UPLOAD_PRANCHA = ""


def test_dois_clientes_com_a_MESMA_prancha_nao_trocam_o_motivo_da_falha():
    """🩸 18/09, revisão adversarial. Os mapas de falha do `dwg_extractor` eram
    indexados por `basename` — seguro com um projeto por vez, contaminação com
    dois. "PRANCHA 01 - ARQUITETURA.dwg" é dos nomes mais banais da profissão.

    E não é só diagnóstico trocado: o texto do ODA começa com "OdError thrown
    during readFile of drawing <caminho>", então o CAMINHO do arquivo de um
    cliente entraria na mensagem que o OUTRO lê — isolamento (nº2) e nome de
    arquivo de cliente fora do lugar (nº6) no mesmo defeito."""
    import dwg_extractor as dx

    a = os.path.join("job-aaaa", "PRANCHA 01 - ARQUITETURA.dwg")
    b = os.path.join("job-bbbb", "PRANCHA 01 - ARQUITETURA.dwg")
    assert os.path.basename(a) == os.path.basename(b), "o teste perdeu o sentido"

    dx._FALHA_DETALHE[dx._chave_da_falha(a)] = "motivo-do-A"
    dx._FALHA_DETALHE[dx._chave_da_falha(b)] = "motivo-do-B"
    dx._FALHA_MOTIVO[dx._chave_da_falha(a)] = "truncado"
    try:
        assert dx.dwg_failure_detail(a) == "motivo-do-A"
        assert dx.dwg_failure_detail(b) == "motivo-do-B", \
            "o projeto B leu o motivo da falha do projeto A"
        assert dx.dwg_failure_reason(a) == "truncado"
        assert dx.dwg_failure_reason(b) == "", \
            "o projeto B herdou o veredito do projeto A"
    finally:
        for k in (dx._chave_da_falha(a), dx._chave_da_falha(b)):
            dx._FALHA_DETALHE.pop(k, None)
            dx._FALHA_MOTIVO.pop(k, None)


def test_CONTROLE_pelo_NOME_os_dois_colidiriam():
    """Controle positivo do guarda acima: prova que os dois caminhos realmente
    colidem quando a chave é o nome — senão o teste passaria sem mérito."""
    a = os.path.join("job-aaaa", "PRANCHA 01 - ARQUITETURA.dwg")
    b = os.path.join("job-bbbb", "PRANCHA 01 - ARQUITETURA.dwg")
    por_nome = {}
    por_nome[os.path.basename(a)] = "motivo-do-A"
    por_nome[os.path.basename(b)] = "motivo-do-B"
    assert len(por_nome) == 1
    assert por_nome[os.path.basename(a)] == "motivo-do-B"


def test_quem_pergunta_o_motivo_da_falha_passa_o_CAMINHO():
    """A chave virou caminho completo; quem consultar por nome recebe "" — e
    calado. Este guarda prende o único ponto do motor que fazia isso."""
    fonte = io.open(_FONTE, encoding="utf-8").read()
    assert "_motivo_falha(_p) == \"truncado\"" in fonte, \
        "a consulta do motivo voltou a não usar o caminho"
    assert "for n in dwg_failed if _motivo_falha(n)" not in fonte, \
        "voltou a perguntar o motivo pelo NOME do arquivo — devolve vazio calado"


def test_a_recusa_por_disco_para_de_apontar_o_envio_do_proprio_cliente():
    """Terceira aparição da mesma doença. A recusa por falta de espaço AFIRMAVA
    que "as pranchas anteriores deste mesmo envio ocuparam o espaço" — verdade
    com um projeto por vez, palpite com dois: pode ter sido o vizinho."""
    main._JOBS_RODANDO = 1
    sozinho = main._por_que_faltou_espaco()
    assert "mesmo envio" in sozinho, \
        "sozinho a causa É o próprio envio, e dizer isso ajuda o cliente"

    main._JOBS_RODANDO = 2
    acompanhado = main._por_que_faltou_espaco()
    assert "mesmo envio" not in acompanhado, \
        "com dois projetos no ar isso virou afirmação sem medida"
    assert "mais de um projeto" in acompanhado


def test_a_recusa_por_disco_NAO_promete_o_que_nao_controla():
    """"mande sozinha que ela passa" é promessa; com outro projeto ocupando o
    disco, ela pode não valer. O texto entregue tem que dizer o que a gente
    sustenta."""
    fonte = io.open(_FONTE, encoding="utf-8").read()
    assert "em lotes menores, que ela passa" not in fonte
    assert "que costuma passar" in fonte


def test_a_mensagem_do_disco_PERGUNTA_de_quem_era_o_espaco():
    """🩸 A sabotagem M32 sobreviveu à primeira versão destes guardas: eu
    testava a função isolada e o texto da promessa, mas NUNCA que a mensagem
    chama a função. Dava pra arrancar a pergunta e recolar a frase antiga que
    aponta o envio do cliente, com tudo verde. É o mesmo buraco de 09/09 —
    guarda que procura a peça e não a LIGAÇÃO."""
    chamadas = [n for n in ast.walk(_arvore())
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "_por_que_faltou_espaco"]
    assert chamadas, \
        "a mensagem de recusa por disco parou de perguntar de quem era o espaço"


def test_o_motor_le_a_copia_DO_JOB_nao_o_global():
    """O `_log_error` que explica o CAD não guardado tem que ler o ContextVar.

    🩸 18/09, revisão adversarial: a 1ª versão deste guarda PROMETIA "pela AST"
    no docstring e fazia dois `in`/`not in` de texto cru — e passava verde com o
    defeito presente (bastava reescrever a leitura do global com outra aspa ou
    outro espaçamento). Docstring que promete rigor que o código não tem é
    exatamente o que deixou o defeito da miniatura viver 5 meses. Agora é AST de
    verdade: o global não pode ser LIDO em nenhum lugar do motor fora da própria
    função que o escreve e da rota de diagnóstico do admin."""
    arv = _arvore()
    escritores = {"_supabase_storage_upload_prancha", "debug_storage_limit"}
    leitores_do_global = []
    for fn in ast.walk(arv):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if fn.name in escritores:
            continue
        for no in ast.walk(fn):
            if (isinstance(no, ast.Name) and no.id == "_ULTIMA_FALHA_UPLOAD_PRANCHA"
                    and isinstance(no.ctx, ast.Load)):
                leitores_do_global.append(f"{fn.name}:{no.lineno}")
    assert not leitores_do_global, (
        "o motor voltou a LER o global da falha de upload — com dois projetos "
        f"no ar isso mistura cliente: {leitores_do_global}")

    # e o ponto de leitura do motor tem que usar a cópia do job
    achou = [n for n in ast.walk(arv)
             if isinstance(n, ast.Attribute) and n.attr == "get"
             and isinstance(n.value, ast.Name) and n.value.id == "_FALHA_UPLOAD_DO_JOB"]
    assert achou, "ninguém lê `_FALHA_UPLOAD_DO_JOB` — a cópia por job virou enfeite"


def test_TODO_boot_registra_se_consegue_medir_a_memoria():
    """Sem isto, o banco não sabe distinguir duas coisas MUITO diferentes:
    "a 2ª vaga nunca abriu porque não houve fila" e "a 2ª vaga nunca abriu
    porque não sabemos ler o cgroup". A admissão falha FECHADA, então o segundo
    caso deixa o produto em um job por vez — seguro e MUDO, e a mudança inteira
    não entrega nada sem ninguém perceber.

    🪤 É a lição do "0 evento ≠ recusou cookie": medição que não distingue
    ausência de causa de ausência de oportunidade não responde nada."""
    fn = next(n for n in ast.walk(_arvore())
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and n.name == "_on_startup_recover_jobs")
    assert "_container_mem_frac" in _chamadas(fn), \
        "o boot parou de registrar se a memória do contêiner é legível"


def test_NENHUM_nome_de_modulo_e_declarado_DUAS_vezes():
    """🚨 18/09 — o defeito mais caro deste commit, e o mais bobo.

    A fila nova declarou `_JOBS_LOCK = Lock()` sem saber que esse nome já existia
    na linha 3309 como o RLock **reentrante** do store de jobs. O módulo executa
    de cima pra baixo, então os 8 usos do store passaram a apontar pra minha
    trava não-reentrante: `update_field` pegava a trava, chamava `_load_jobs` e
    tentava pegar de novo — **deadlock eterno, sem exceção e sem log**. Nenhum
    projeto processaria. A bancada acusou TRAVANDO em 91%.

    🔑 É a 2ª vez que dois nomes iguais custam caro nesta casa (o incidente do
    smoke foi com duas FUNÇÕES de mesmo nome). Num arquivo de 33 mil linhas
    ninguém "lembra" o que já existe — então o guarda lembra."""
    arv = _arvore()
    onde = {}
    for no in arv.body:                      # só o nível do MÓDULO
        alvos = []
        if isinstance(no, ast.Assign):
            alvos = [t for t in no.targets if isinstance(t, ast.Name)]
        elif isinstance(no, ast.AnnAssign) and isinstance(no.target, ast.Name):
            alvos = [no.target]
        elif isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            onde.setdefault(no.name, []).append(no.lineno)
            continue
        for t in alvos:
            onde.setdefault(t.id, []).append(no.lineno)
    repetidos = {n: ls for n, ls in onde.items() if len(ls) > 1}
    assert not repetidos, (
        "nome declarado duas vezes no módulo — a segunda apaga a primeira em "
        f"silêncio e TODO mundo passa a usar a de baixo: {repetidos}")


# ══════════════════════════════════════════════════════════════════════════
#  6. A CONTABILIDADE DA VAGA
# ══════════════════════════════════════════════════════════════════════════
def test_pegar_e_devolver_a_vaga_fecha_a_conta(monkeypatch):
    monkeypatch.setattr(main, "_container_mem_frac", lambda: 0.10)
    main._esperar_vaga()
    assert main._JOBS_RODANDO == 1
    assert main._VAGA_EXTRA.get() is False
    main._liberar_vaga()
    assert main._JOBS_RODANDO == 0


def test_o_segundo_a_entrar_sai_MARCADO_como_vaga_extra(monkeypatch):
    monkeypatch.setattr(main, "_container_mem_frac", lambda: 0.10)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    main._JOBS_RODANDO = 1
    main._esperar_vaga()
    assert main._JOBS_RODANDO == 2
    assert main._VAGA_EXTRA.get() is True, \
        "sem esta marca o freio não sabe quem parar e volta a acusar o errado"


def test_quem_chegou_depois_NAO_passa_na_frente(monkeypatch):
    """🩸 18/09, revisão adversarial: a 1ª versão de `_esperar_vaga` era um
    `while True: sleep()` puro, e isso PERDEU de graça o que o `Semaphore(1)`
    dava — ordem de chegada. Foi reproduzido: um job que chegou 0,9 s DEPOIS
    começou 1,1 s ANTES, porque o primeiro tinha acabado de checar e dormia.
    Com fila movimentada vira inanição, e não há teto de espera.

    🔑 Este guarda é DETERMINÍSTICO de propósito: em vez de cronometrar uma
    corrida (que pisca sob carga), ele põe uma senha alheia na frente e prova
    que o recém-chegado NÃO entra, mesmo com a vaga livre."""
    monkeypatch.setattr(main, "_container_mem_frac", lambda: 0.10)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    main._JOBS_RODANDO = 0
    main._FILA_DE_SENHAS.clear()
    main._FILA_DE_SENHAS.append(-1)      # alguém chegou antes e ainda espera
    entrou = threading.Event()

    def _atrasado():
        main._esperar_vaga(_espera_s=0.02)
        entrou.set()

    t = threading.Thread(target=_atrasado, daemon=True)
    t.start()
    assert not entrou.wait(timeout=0.5), \
        "furou a fila: entrou com a vaga livre e alguém na frente"
    with main._VAGAS_LOCK:
        main._FILA_DE_SENHAS.remove(-1)  # o da frente foi embora
    assert entrou.wait(timeout=20), "não entrou nem depois de a frente liberar"
    t.join(timeout=20)
    main._liberar_vaga()


def test_a_fila_entrega_por_ORDEM_DE_CHEGADA(monkeypatch):
    """A tela afirma "começa por ordem de chegada". Esta é a prova — e a
    chegada é determinística: cada job só é considerado chegado depois que a
    senha dele aparece na fila, então o teste não depende de relógio."""
    monkeypatch.setattr(main, "_container_mem_frac", lambda: 0.90)   # só 1 vaga
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    main._JOBS_RODANDO = 1
    main._FILA_DE_SENHAS.clear()
    ordem = []
    trava = threading.Lock()

    def _job(nome):
        main._esperar_vaga(_espera_s=0.02)
        with trava:
            ordem.append(nome)
        time.sleep(0.01)
        main._liberar_vaga()

    nomes = ["1o", "2o", "3o", "4o"]
    ts = []
    for nome in nomes:
        t = threading.Thread(target=_job, args=(nome,), daemon=True)
        t.start()
        esperou = 0.0
        while len(main._FILA_DE_SENHAS) < len(ts) + 1 and esperou < 10:
            time.sleep(0.005)
            esperou += 0.005
        assert len(main._FILA_DE_SENHAS) == len(ts) + 1, \
            f"{nome} não pegou senha — a fila não está registrando chegada"
        ts.append(t)

    main._JOBS_RODANDO = 0               # abre a vaga
    for t in ts:
        t.join(timeout=60)
    assert ordem == nomes, f"a fila entregou fora de ordem de chegada: {ordem}"


def test_a_senha_de_quem_desiste_NAO_trava_a_fila(monkeypatch):
    """Senha abandonada na cabeça da fila seguraria todo mundo atrás dela — a
    fila entupida seria pior que a fila de um por vez que isto veio destravar."""
    monkeypatch.setattr(main, "_container_mem_frac", lambda: 0.10)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(main, "_tem_vaga_agora",
                        lambda rodando: (_ for _ in ()).throw(RuntimeError("boom")))
    main._JOBS_RODANDO = 0
    main._FILA_DE_SENHAS.clear()
    with pytest.raises(RuntimeError):
        main._esperar_vaga(_espera_s=0.01)
    assert len(main._FILA_DE_SENHAS) == 0, \
        "a senha ficou na fila sem dono e trava todo mundo atrás"


def test_a_vaga_nao_fica_negativa():
    """Contador negativo abriria vaga infinita — o oposto do que isto faz."""
    main._JOBS_RODANDO = 0
    main._liberar_vaga()
    main._liberar_vaga()
    assert main._JOBS_RODANDO == 0


def test_quem_nao_cabe_ESPERA_de_verdade_e_entra_quando_libera(monkeypatch):
    """Não basta devolver False: `_esperar_vaga` tem que SEGURAR a thread. Se
    ela passasse direto, o teto de 2 seria decorativo."""
    monkeypatch.setattr(main, "_container_mem_frac", lambda: 0.90)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    main._JOBS_RODANDO = 2
    entrou = threading.Event()

    def _terceiro():
        main._esperar_vaga(_espera_s=0.02)
        entrou.set()

    t = threading.Thread(target=_terceiro, daemon=True)
    t.start()
    assert not entrou.wait(timeout=0.4), "entrou sem vaga: o teto não segura"
    main._JOBS_RODANDO = 0
    assert entrou.wait(timeout=5), "não entrou nem depois de liberar"
    t.join(timeout=5)


def test_a_vaga_VOLTA_mesmo_quando_o_job_estoura(monkeypatch):
    """A vaga que não volta entope a fila pra sempre — seria PIOR que a fila
    de um por vez que isto veio destravar. Roda `_process_job_throttled` de
    verdade, com um `process_job` que levanta."""
    monkeypatch.setattr(main, "_container_mem_frac", lambda: 0.10)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)

    def _explode(*a, **k):
        raise RuntimeError("estourou no meio")

    monkeypatch.setattr(main, "process_job", _explode)
    main._JOBS_RODANDO = 0
    with pytest.raises(RuntimeError):
        main._process_job_throttled("abc12345", [], "/tmp/x")
    assert main._JOBS_RODANDO == 0, "a vaga vazou numa exceção"


def test_o_caminho_FELIZ_tambem_devolve_a_vaga(monkeypatch):
    monkeypatch.setattr(main, "_container_mem_frac", lambda: 0.10)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    monkeypatch.setattr(main, "process_job", lambda *a, **k: None)
    main._JOBS_RODANDO = 0
    main._process_job_throttled("abc12345", [], "/tmp/x")
    assert main._JOBS_RODANDO == 0


def test_duas_threads_nao_viram_tres_vagas(monkeypatch):
    """Corrida real: dez threads largando no mesmo instante.

    🪤 A 1ª versão deste guarda lia `_JOBS_RODANDO` e passava VERDE com o
    incremento fora da trava — porque nessa corrida as dez leem 0, as dez
    escrevem 1, e o contador diz "1" com dez jobs dentro. O número que o código
    acha que tem é justamente o que a corrida corrompe; quem precisa ser contado
    é QUEM ENTROU. A sabotagem M18 foi quem mostrou isso.
    """
    monkeypatch.setattr(main, "_container_mem_frac", lambda: 0.10)
    monkeypatch.setattr(main, "_log_error", lambda *a, **k: None)
    main._JOBS_RODANDO = 0
    dentro = []
    pico = [0]
    conta = threading.Lock()
    barreira = threading.Barrier(10)

    def _corre():
        barreira.wait()
        main._esperar_vaga(_espera_s=0.01)
        with conta:
            dentro.append(1)
            pico[0] = max(pico[0], len(dentro))
        time.sleep(0.02)
        with conta:
            dentro.pop()
        main._liberar_vaga()

    ts = [threading.Thread(target=_corre, daemon=True) for _ in range(10)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=30)
    assert pico[0] <= main._JOBS_SIMULTANEOS, \
        f"{pico[0]} jobs dentro ao mesmo tempo, com teto de {main._JOBS_SIMULTANEOS}"
    assert main._JOBS_RODANDO == 0


# ══════════════════════════════════════════════════════════════════════════
#  7. A LIGAÇÃO — pela AST, porque process_job não roda num teste
# ══════════════════════════════════════════════════════════════════════════
def _arvore():
    return ast.parse(io.open(_FONTE, encoding="utf-8").read())


def _chamadas(no):
    return {c.func.id for c in ast.walk(no)
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}


def test_a_porta_unica_dos_jobs_PEGA_e_DEVOLVE_a_vaga():
    """`_process_job_throttled` é por onde todo projeto entra. Se ela parar de
    pedir vaga, o teto inteiro vira enfeite e ninguém percebe."""
    fn = next(n for n in ast.walk(_arvore())
              if isinstance(n, ast.FunctionDef) and n.name == "_process_job_throttled")
    assert "_esperar_vaga" in _chamadas(fn)
    tries = [n for n in ast.walk(fn) if isinstance(n, ast.Try) and n.finalbody]
    assert any("_liberar_vaga" in _chamadas(ast.Module(body=t.finalbody, type_ignores=[]))
               for t in tries), "a devolução da vaga não está num finally"


def test_TODO_freio_de_memoria_pergunta_ANTES_de_acusar():
    """Cada `_abort_job_mem` do motor tem que estar sob uma decisão de
    `_decisao_do_freio`. Um terceiro ponto de freio escrito amanhã sem
    perguntar voltaria a acusar o cliente errado — e passaria por todos os
    outros guardas deste arquivo."""
    arv = _arvore()
    abortos = [n for n in ast.walk(arv)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
               and n.func.id == "_abort_job_mem"]
    assert len(abortos) >= 2, f"esperava ao menos 2 pontos de freio, achei {len(abortos)}"
    for n in abortos:
        assert any(k.arg == "motivo" for k in n.keywords), \
            "um _abort_job_mem sem `motivo=` volta a culpar o arquivo do cliente"
    decisoes = [n for n in ast.walk(arv)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "_decisao_do_freio"]
    assert len(decisoes) >= len(abortos), \
        "há mais abortos que decisões: algum freio acusa sem perguntar"


def test_a_tela_NAO_promete_ao_cliente_um_projeto_por_vez():
    """A copy do painel afirmava "processamos um de cada vez" — verdade até
    hoje, mentira a partir da 2ª vaga. Quando o código passa a contradizer uma
    frase da tela, a frase é parte do conserto, não um detalhe pra depois.

    🪤 Este guarda lê TEXTO, e nos outros isso seria erro. Aqui não: o texto É o
    entregável. O que ele não pode virar é prova sobre comportamento — por isso
    ele só nega a promessa, e quem garante o comportamento são os guardas que
    chamam `_tem_vaga_agora`."""
    painel = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "dashboard.html")
    texto = io.open(painel, encoding="utf-8").read()
    # tira os comentários de JS, que é onde a frase velha fica documentada
    vivo = "\n".join(l for l in texto.splitlines()
                     if not l.lstrip().startswith("//"))
    for promessa in ("um de cada vez", "um projeto por vez", "um por vez"):
        assert promessa not in vivo, \
            f"a tela ainda promete '{promessa}', que a 2ª vaga torna falso"
    assert "Já começa" not in vivo, "com fila, 'Já começa' é falso (Pedro, 17/09)"
    # 🩸 18/09: minha 1ª correção trocou uma promessa falsa por outra. "quem
    # chegou antes TERMINA primeiro" é falso justamente porque a 2ª vaga existe:
    # o projeto de 2 min que entrou depois acaba antes do de 61 min.
    assert "termina primeiro" not in vivo, \
        "a tela promete ordem de TÉRMINO, que duas vagas tornam falsa"
    # E a frase que ficou ("por ordem de chegada") só pode existir enquanto o
    # motor garantir isso. Amarra a copy ao código que a sustenta.
    if "ordem de chegada" in vivo:
        assert "_FILA_DE_SENHAS" in io.open(_FONTE, encoding="utf-8").read(), \
            "a tela promete ordem de chegada e a fila de senhas sumiu do motor"


def test_a_admissao_NAO_volta_a_usar_a_regua_que_falha_aberta():
    """`_cabe_um_segundo_job` não pode chamar `_mem_pressure`: é a receita
    exata do defeito nº1, e ela parece certa lendo o código."""
    fn = next(n for n in ast.walk(_arvore())
              if isinstance(n, ast.FunctionDef) and n.name == "_cabe_um_segundo_job")
    assert "_mem_pressure" not in _chamadas(fn)
    assert "_container_mem_frac" in _chamadas(fn)
