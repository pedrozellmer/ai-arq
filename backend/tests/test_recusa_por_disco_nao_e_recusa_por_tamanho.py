# -*- coding: utf-8 -*-
"""Recusa por DISCO não pode ser entregue como recusa por TAMANHO.

🩸 04/09/2026, varredura adversarial dos commits de 03/09. `_dxf_grande_pode_
seguir` devolve False por DUAS razões diferentes — o arquivo passou de
`_DXF_TETO_ARQUIVO` (900 MB), ou não sobrou espaço temporário — e o chamador
tratava as duas como a mesma coisa. O cliente lia sempre:

    "essa prancha é grande demais pro nosso limite de memória de hoje
     (409 MB depois de convertida) — o que resolve é um PURGE no desenho"

Pra recusa por DISCO isso é falso duas vezes: o arquivo NÃO é grande demais, e
o PURGE não é o que resolve.

🔑 MEDIDO com a função real (8 pranchas iguais de 409 MB, 4 GB livres):

    pranchas 1-5 → PASSAM
    pranchas 6-8 → RECUSADAS por disco

Mesmo arquivo, mesmo tamanho, resultado decidido pela **posição na fila**. Do
lado do cliente isso não tem explicação possível: ele reenvia a mesma prancha,
ela passa, e nunca entende o que mudou. É a nossa fila que encheu o disco —
mandar ele mexer no desenho é cobrar dele um limite nosso.

🪤 O caso `dbd0d97e` (18/08, 8 pranchas de ~340 MB) perdeu TODAS. Com a divisão
feita aqui, as que caírem por disco passam a ouvir a única coisa que resolve:
mandar em lotes menores.
"""
import main as _m

MB = 1048576
TETO = 250 * MB


def _motivos_da_fila(tam, livre_inicial, n):
    """Simula uma fila de `n` pranchas iguais e devolve o motivo de cada uma.

    Cada prancha aceita FICA no disco (nada apaga DXF dentro do laço de
    conversão), então ela desconta do livre das seguintes.
    """
    livre = livre_inicial
    saida = []
    for _ in range(n):
        motivo = _m._motivo_de_nao_seguir_dxf(tam, TETO, livre)
        saida.append(motivo)
        if motivo is None:
            livre -= tam
    return saida


def test_a_recusa_por_disco_tem_nome_proprio():
    """🩸 O achado. Antes as duas razões saíam pela mesma porta."""
    assert _m._motivo_de_nao_seguir_dxf(409 * MB, TETO, 2200 * MB) == "disco", (
        "prancha que cabe mas não tem espaço voltou a ser classificada como "
        "outra coisa — e aí o cliente lê 'grande demais, faça um PURGE'")


def test_a_recusa_por_tamanho_continua_sendo_por_tamanho():
    """CONTROLE do irmão: separar não pode apagar a recusa legítima."""
    assert _m._motivo_de_nao_seguir_dxf(950 * MB, TETO, 99999 * MB) == "tamanho", (
        "arquivo acima do teto de %d MB parou de ser recusado por tamanho"
        % (_m._DXF_TETO_ARQUIVO // MB))


def test_o_que_pode_seguir_continua_seguindo():
    for tam, livre, porque in (
            (100 * MB, 1 * MB, "abaixo do teto antigo, nem era caso"),
            (409 * MB, 99999 * MB, "cabe e tem disco de sobra"),
            (409 * MB, None, "não deu pra medir o disco — segue, o filho tem "
                             "trava de memória própria")):
        assert _m._motivo_de_nao_seguir_dxf(tam, TETO, livre) is None, porque


def test_o_booleano_NAO_pode_discordar_do_motivo():
    """🪤 Se fossem duas contas paralelas, um dia a mensagem diria uma coisa e a
    decisão faria outra. O booleano é implementado EM CIMA do motivo."""
    for tam in (100 * MB, 409 * MB, 700 * MB, 950 * MB):
        for livre in (None, 300 * MB, 2200 * MB, 99999 * MB):
            assert (_m._dxf_grande_pode_seguir(tam, TETO, livre)
                    is (_m._motivo_de_nao_seguir_dxf(tam, TETO, livre) is None)), (
                "o booleano e o motivo discordaram em tam=%d MB livre=%s"
                % (tam // MB, livre))


def test_a_fila_prova_que_o_motivo_e_POSICAO_e_nao_o_arquivo():
    """🩸 O coração do achado, medido: mesma prancha, resultado diferente.

    Se um dia isto deixar de valer (porque a limpeza passou a rodar dentro do
    laço de conversão, por exemplo), ótimo — mas aí a mensagem tem que mudar
    junto, então o teste precisa cair e avisar.
    """
    motivos = _motivos_da_fila(409 * MB, 4096 * MB, 8)
    passaram = [i for i, mv in enumerate(motivos, 1) if mv is None]
    por_disco = [i for i, mv in enumerate(motivos, 1) if mv == "disco"]
    assert passaram and por_disco, (
        "a fila não reproduz mais o caso: passaram=%s por_disco=%s" %
        (passaram, por_disco))
    assert all(mv != "tamanho" for mv in motivos), (
        "409 MB não pode ser recusado por TAMANHO — o teto de arquivo é %d MB"
        % (_m._DXF_TETO_ARQUIVO // MB))


# ══════════════════════════════════════════════════════════════════════════
#  A MENSAGEM que o cliente lê — é ela que estava mentindo
# ══════════════════════════════════════════════════════════════════════════
import io  # noqa: E402
import os  # noqa: E402

_FONTE = io.open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "main.py"), encoding="utf-8").read()


def _ramo_da_recusa():
    i = _FONTE.index("if _tam_conv > _TETO_DXF:\n", _FONTE.index("_bn_conv ="))
    return _FONTE[i:_FONTE.index("jobs.update_field(job_id, current_step=_passo_rec)", i)]


def test_o_PURGE_nao_e_RECOMENDADO_na_recusa_por_disco():
    """🚨 O defeito exato: PURGE oferecido pra quem não tem problema de tamanho.

    🪤 A 1ª versão deste teste cobrava `"PURGE" not in bloco_disco` e reprovou o
    texto CERTO: a mensagem de disco cita o PURGE pra **negar** ("um PURGE não
    muda isso"), que é justamente o que poupa o cliente de tentar. Guarda preso
    à PALAVRA em vez do CONSELHO vira obstáculo ao conserto bom — é a mesma
    família do guarda que ancorou numa redação e barrou o preheader honesto,
    em 03/09. O que se cobra aqui é a RECOMENDAÇÃO.
    """
    ramo = _ramo_da_recusa()
    i_disco = ramo.index('if _motivo_rec == "disco":')
    i_else = ramo.index("else:", i_disco)
    bloco_disco, bloco_tamanho = ramo[i_disco:i_else], ramo[i_else:]
    assert "resolve é um PURGE" not in bloco_disco, (
        "a recusa por DISCO voltou a RECOMENDAR o PURGE — ele ia mexer no "
        "desenho por causa de um limite nosso, e a mesma prancha passa se for "
        "a primeira da fila")
    assert "resolve é um PURGE" in bloco_tamanho, (
        "a recusa por TAMANHO perdeu o conselho que de fato resolve")
    assert "lotes menores" in bloco_disco, (
        "sumiu a única saída verdadeira da recusa por disco")
    assert "lotes menores" not in bloco_tamanho, (
        "lotes menores não resolve prancha grande de verdade — cada lote "
        "continuaria com a mesma prancha acima do teto")


def test_o_log_separa_os_dois_para_a_gente_tambem():
    """Se os dois caem no mesmo stage, ninguém nunca vai saber que houve disco."""
    ramo = _ramo_da_recusa()
    assert "motor:disco-cheio-na-conversao" in ramo, (
        "a recusa por disco voltou a ser gravada como prancha-grande-demais — "
        "some do radar e a próxima investigação começa errada")
    assert "motor:prancha-grande-demais" in ramo


# ══════════════════════════════════════════════════════════════════════════
#  🧪 CONTROLE POSITIVO — a regra de ANTES, na MESMA função de julgamento
# ══════════════════════════════════════════════════════════════════════════
def _motivo_ANTIGO(tam_bytes, teto_antigo, livre_bytes):
    """Como era: um booleano, sem dizer por quê. Tudo virava 'tamanho'."""
    if tam_bytes <= teto_antigo:
        return None
    if tam_bytes > _m._DXF_TETO_ARQUIVO:
        return "tamanho"
    if livre_bytes is None:
        return None
    if (livre_bytes - tam_bytes) > _m._DXF_MARGEM_DISCO:
        return None
    return "tamanho"          # ← a mentira: disco entregue como tamanho


def test_CONTROLE_a_regra_ANTIGA_chama_disco_de_tamanho():
    antigo = _motivo_ANTIGO(409 * MB, TETO, 2200 * MB)
    atual = _m._motivo_de_nao_seguir_dxf(409 * MB, TETO, 2200 * MB)
    assert antigo == "tamanho" and atual == "disco", (
        "o julgamento não distingue as duas regras — ele não está julgando "
        "nada (antigo=%r, atual=%r)" % (antigo, atual))
