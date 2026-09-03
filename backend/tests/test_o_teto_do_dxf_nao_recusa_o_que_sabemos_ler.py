# -*- coding: utf-8 -*-
"""O teto do DXF convertido recusava arquivo que a gente SABE ler.

🩸 03/09/2026, RAFAEL LIMA (job 28f140ef), primeiro projeto dele, canal novo
(ChatGPT). DWG de 11,7 MB → DXF de 376 MB → recusado pelo teto de 250 MB, com
o arquivo APAGADO na hora. Baixei o DWG dele do nosso Storage e rodei o worker
de verdade (`dxf_extract_worker.py`) na minha máquina:

    DXF 409 MB  --dxf-slim-->  34 MB   (72.201 entidades mantidas, 245 fora)
    pico de RSS 305 MB = 0,7x o DXF    (a previsão do motor era 9,6x → 13x errado)
    19 segundos, código de saída 0
    67.953 paredes · 1.636 cotas · 1.780 textos · 511 hachuras · 47 camadas

Ou seja: o `dxf_extract_worker` SEMPRE chama o emagrecedor antes de parsear, e
este teto apagava o arquivo antes do worker existir. Um emagrecedor que
funciona, atrás de uma porta que fecha primeiro.

🪤 Duas ideias minhas morreram medindo, e valem ficar escritas:
  • "é bloat do libredwg" — o ODA gerou 409 MB contra os 376 MB do libredwg.
    O desenho é grande mesmo; o conversor não tem culpa.
  • "prever a RAM pelo tamanho do DXF" — 9,6x errou por 13x neste arquivo.
    Quem sabe se cabe na memória é o processo filho, que TEM trava de 2,5 GB e
    morre sozinho sem levar o site junto.

🔑 O que se decide neste ponto é DISCO, não memória — e disco se MEDE. Nada
apaga os DXF convertidos dentro do laço: eles se somam até o fim do job. O
`dbd0d97e` de 18/08 tinha 8 pranchas de ~340 MB e perdeu TODAS, e mesmo assim
foi entregue como `done`: o cliente recebeu planilha sem elas.
"""
import main

MB = 1024 * 1024
GB = 1024 * MB

_TETO_ANTIGO = 250 * MB          # o valor de `_MAX_DXF_BYTES` em 03/09/2026
_RAFAEL = 376 * MB               # o DXF que o libredwg gerou pro arquivo dele


def _pode(tam, livre):
    return main._dxf_grande_pode_seguir(tam, _TETO_ANTIGO, livre)


def test_o_arquivo_do_rafael_passa():
    """O caso que originou tudo: 376 MB, disco folgado."""
    assert _pode(_RAFAEL, 8 * GB), (
        "o DXF de 376 MB do Rafael voltou a ser recusado antes do emagrecedor "
        "— medido, ele emagrece pra 34 MB e extrai em 19 s com 305 MB")


def test_as_oito_pranchas_do_job_de_18_08_passariam():
    """Cada uma tinha ~340 MB e as oito morreram no teto antigo."""
    for mb in (337, 341, 343, 347, 349, 350, 370, 376):
        assert _pode(mb * MB, 8 * GB), (
            "prancha de %d MB continua recusada" % mb)


def test_CONTROLE_o_absurdo_continua_recusado():
    """Sem um teto de sanidade, isto vira 'qualquer coisa passa'."""
    assert not _pode(901 * MB, 8 * GB)
    assert not _pode(3 * GB, 20 * GB)


def test_CONTROLE_disco_apertado_recusa():
    """A recusa que sobrou é de DISCO, e ela precisa reprovar de verdade.

    Nada apaga os DXF convertidos dentro do laço, então um envio de várias
    pranchas grandes enche o disco do Render — foi por isso que o teto nasceu.
    """
    assert not _pode(_RAFAEL, 2 * GB), (
        "com 2 GB livres, guardar mais 376 MB deixaria menos que a margem — "
        "tinha que recusar")
    assert not _pode(_RAFAEL, 400 * MB)


def test_a_margem_de_disco_e_a_regra_e_nao_um_detalhe():
    """A reserva real é MARGEM + o tamanho do arquivo, e isso é de propósito.

    🪤 Este teste dizia só "2 GB de folga", subestimando a própria garantia. A
    revisão adversarial de 03/09 mostrou por quê o extra importa: `livre` é
    lido DEPOIS de o DXF estar escrito (já o desconta), e subtrair `tam` de
    novo reserva um segundo espaço do mesmo tamanho — que tem dono, o
    `<nome>.slim.dxf` que o emagrecedor escreve AO LADO do original sem apagá-lo
    no caminho principal, e que pode ter até 95% do tamanho dele.

    Documentação que promete menos do que garante é convite pra alguém
    "simplificar" e quebrar.
    """
    margem = main._DXF_MARGEM_DISCO
    assert margem == 2 * GB
    # A fronteira fica em MARGEM + tam, não em MARGEM.
    assert _pode(_RAFAEL, _RAFAEL + margem + 1)
    assert not _pode(_RAFAEL, _RAFAEL + margem)
    # E o extra reservado dá pra uma cópia do arquivo inteiro — que é o pior
    # caso do enxuto (95% do original).
    _livre_no_limite = _RAFAEL + margem + 1
    assert _livre_no_limite - _RAFAEL >= margem, (
        "sobrou menos que a margem depois de guardar o original")
    assert _livre_no_limite >= margem + _RAFAEL, (
        "a reserva parou de cobrir a cópia .slim.dxf que o emagrecedor escreve")


def test_disco_que_nao_deu_pra_medir_nao_vira_recusa():
    """Recusar por não ter medido é recusar por medo.

    O pior caso de deixar seguir é o filho morrer na trava de memória dele —
    o cliente recebe a mesma recusa honesta, e o site não sente.
    """
    assert _pode(_RAFAEL, None)
    # mas o teto de sanidade continua valendo mesmo sem medir o disco
    assert not _pode(2 * GB, None)


def test_prancha_normal_nem_chega_a_ser_pergunta():
    """O caminho que funciona não pode ter mudado em nada."""
    for mb in (0, 1, 12, 20, 120, 249):
        assert _pode(mb * MB, 8 * GB)


def test_CONTROLE_a_regra_antiga_REPROVARIA_neste_teste():
    """Prova que os testes acima medem a MUDANÇA, e não um sempre-verde.

    A regra antiga era literalmente "passou do teto, recusa". Se ela ainda
    estivesse valendo, o teste do Rafael cairia.
    """
    def regra_antiga(tam, teto, livre):
        return tam <= teto
    assert not regra_antiga(_RAFAEL, _TETO_ANTIGO, 8 * GB), (
        "o controle está errado: a regra antiga precisa REPROVAR o arquivo do "
        "Rafael, senão os testes acima não estão medindo nada")


def test_o_laco_usa_a_funcao_e_nao_uma_copia_da_regra():
    """Função testável que o código de produção não chama é decoração."""
    import io
    import os
    fonte = io.open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "main.py"), encoding="utf-8").read()
    assert fonte.count("_dxf_grande_pode_seguir(") >= 2, (
        "a decisão foi definida mas não é chamada no laço de conversão — "
        "o teste estaria guardando código morto")
