# -*- coding: utf-8 -*-
"""O teto de 1 e-mail por semana não valia na porta da liberação.

🚨 29/08/2026. A cliente-20 (a cliente do NPS 2) recebeu TRÊS e-mails num dia:

    08:00  "Que tal ajudar a afinar seu quantitativo?"   esteira automática
    13:59  "ARMAÇÃO FUNDAÇÃO — refizemos a leitura"      disparado pela liberação
    14:23  o do Pedro, escrito à mão

Os dois últimos dizem a mesma coisa, com 24 minutos de diferença. E o Pedro
mandou o dele porque **eu garanti que nenhum automático sairia** — eu tinha lido
a trava de "cliente que revisou não recebe" e concluído que ela pegaria. Não
pegou: as 3 correções dela são em OUTRO projeto, e a trava olha o projeto-pai.
Descobri esse fato sozinho minutos depois e não voltei a ligar os pontos.

🔑 A CAUSA ESTRUTURAL: o cooldown de 7 dias (`_email_auto_recente`) mora DENTRO
do `emails_auto_tick` — ele filtra a esteira de nutrição. A liberação de filhote
chama `_email_leitura_nova` por fora, então nunca passava por ele. A regra do
Pedro é "no máximo 1 automático por pessoa por semana"; esta porta estava fora
da regra desde que nasceu.

🪤 O CONSERTO NÃO É BLOQUEAR CALADO. Segurar o aviso e não dizer nada seria pior:
o cliente deixa de saber que a leitura melhorou, que é o ponto do mecanismo
inteiro (Pedro, 08/08: *"aviso só na tela não resolve — 1 de 44 clientes voltou
numa semana diferente"*). No botão manual o motivo VOLTA na resposta, e quem
libera decide se fala à mão. No caminho automático não há ninguém pra decidir,
então ele segura e registra no log.

📌 Mesma saída da trava de cliente-que-revisou: a máquina não manda, e o humano
sabe que precisa mandar.
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_MAIN = io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()


def _sem_comentarios(txt):
    """🪤 Sexta ou sétima vez que preciso disto: comentário não é código, e
    testes que leem comentário aprovam pelo motivo errado."""
    return "\n".join(l for l in txt.split("\n") if not l.strip().startswith("#"))


def _bloco(marca, tamanho=2600):
    i = _MAIN.find(marca)
    assert i > 0, "não achei %r em main.py" % marca
    return _sem_comentarios(_MAIN[i:i + tamanho])


def test_o_botao_MANUAL_consulta_o_teto_antes_de_mandar():
    """🚨 O caso da cliente-20. Sem esta checagem, liberar dispara e-mail mesmo
    pra quem já recebeu outro na mesma semana."""
    b = _bloco('email_motivo = "NÃO enviado: a versão nova não ficou melhor')
    assert "_email_auto_recente" in b, (
        "a liberação manual voltou a mandar e-mail sem olhar o teto de 1 por "
        "semana — foi assim que a cliente-20 recebeu 3 num dia")


def test_e_o_caminho_AUTOMATICO_tambem():
    """A liberação automática (juíza) usa a mesma porta e tem o mesmo risco —
    com o agravante de não ter ninguém pra ler o aviso."""
    b = _bloco("# LIBERAR — mesmo movimento do botão manual")
    assert "_email_auto_recente" in b, (
        "o caminho automático de liberação não consulta o teto")


def test_o_motivo_VOLTA_pra_quem_libera_em_vez_de_sumir():
    """🪤 Bloquear calado seria pior que mandar: o cliente deixaria de saber que
    a leitura melhorou, e ninguém saberia que ele não soube.

    O texto tem que dizer as duas coisas: que não mandou, e que a leitura já
    está no painel — senão quem lê acha que a liberação falhou."""
    b = _bloco('email_motivo = "NÃO enviado: a versão nova não ficou melhor')
    i = b.find("_email_auto_recente")
    trecho = b[i:i + 700]
    assert "NÃO enviado" in trecho, "não devolve motivo pra quem libera"
    assert "painel" in trecho, (
        "o motivo não diz que a leitura JÁ está no painel — quem lê vai achar "
        "que a liberação falhou")
    assert "à mão" in trecho or "a mão" in trecho, (
        "não aponta a saída (falar à mão), que é o que a regra do Pedro manda "
        "quando a máquina se cala")


def test_o_automatico_deixa_RASTRO_quando_segura():
    """Sem log, "não mandei" e "falhou o SMTP" viram a mesma coisa no escuro."""
    b = _bloco("# LIBERAR — mesmo movimento do botão manual")
    assert "SEGURADO" in b, "segura o e-mail sem registrar por quê"


def test_a_liberacao_acontece_mesmo_quando_o_email_e_segurado():
    """🔒 O que NÃO pode: o teto de e-mail impedir a leitura nova de chegar ao
    painel. São duas coisas diferentes — uma é avisar, a outra é entregar."""
    b = _bloco("# LIBERAR — mesmo movimento do botão manual")
    i_patch = b.find('_supa_rest_service("PATCH", "projects"')
    i_teto = b.find("_email_auto_recente")
    assert i_patch > 0 and i_teto > i_patch, (
        "a checagem do teto ficou ANTES da liberação — se ela barrar, o cliente "
        "deixa de receber a leitura nova, e não só o aviso")


def test_CONTROLE_o_teto_existe_e_e_de_7_dias():
    """🧪 Se `_email_auto_recente` sumir ou mudar de assinatura, os testes acima
    passariam lendo um nome que não faz mais nada."""
    assert "def _email_auto_recente(email: str, dias: int = 7)" in _MAIN, (
        "a função do cooldown mudou de forma — os guardas acima viraram "
        "leitura de nome, não de comportamento")
    i = _MAIN.find("def _email_auto_recente")
    corpo = _sem_comentarios(_MAIN[i:i + 1800])
    assert "email_auto_log" in corpo, "o cooldown não consulta mais o log de envios"
    assert re.search(r"return\s+True", corpo), (
        "o cooldown não tem caminho que devolve True — nunca seguraria nada")
