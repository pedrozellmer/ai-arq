# -*- coding: utf-8 -*-
"""Os dois tetos de memória — e o lado que não tinha trava nenhuma.

🚨 26/08/2026, caso cliente-16 (job 43a799c0). A prancha 01 dela (24,58 MB de DWG →
176,5 MB de DXF) foi DESCARTADA por um teto de 150 MB calibrado quando o Render
tinha 2 GB. O plano subiu pra 4 GB em 21/07 e ninguém revisitou.

Medido nas 4 pranchas reais, com o dwg2dxf 0.14 (mesma versão do servidor) e
pico via peak_wset, processo novo por medição:

    arquivo         conversão      extração
    DWG  3,1 MB       165 MB         215 MB   (DXF  27,1 MB)
    DWG  5,4 MB       249 MB         374 MB   (DXF  45,7 MB)
    DWG  6,4 MB       337 MB         461 MB   (DXF  53,8 MB)
    DWG 24,6 MB     1.056 MB       1.476 MB   (DXF 176,5 MB)

Dois fatores estáveis:
    conversão ≈ 45 a 53 × o DWG
    extração  ≈  8,4 ×    o DXF

A prancha descartada roda completa em 82s e sobra 64% do container.

🚨 E o achado que a medição escancarou: **o lado do DWG não tinha teto nenhum**.
O upload aceita 450 MB no total; um único DWG de 100 MB pediria ~5 GB só pra
converter e mataria o container ANTES de qualquer medição. O teto de 150 MB só
olhava o DXF — que só existe DEPOIS da conversão, tarde demais.

Hoje o servidor estourou memória às 10:19 e reiniciou. Não fecha com este
modelo (o arquivo tinha 21,6 MB), então o OOM segue sem explicação — por isso o
health passou a ler o cgroup na mesma leva.
"""
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND)

import dwg_extractor as dx   # noqa: E402

_MB = 1024 * 1024
_CONTAINER_MB = 4096            # Render Pro

# 🩸 03/09/2026 — O FATOR DE CONVERSÃO ERA 53, E RECUSOU UM CLIENTE À TOA.
# Os 53× vinham de arquivos PEQUENOS (3,1 a 24,6 MB). Parte do custo da
# conversão é FIXA, então o fator CAI conforme o arquivo cresce. Medido em três
# arquivos GRANDES de cliente no mesmo dia:
#     11,7 MB → ~29×   (produção, Render)
#     44,5 MB →  18,8×  ← o do FÁBIO, recusado por 44 > 40 MB
#     53,2 MB →  26×
# Aplicar 53× a um arquivo de 44 MB previa 2.227 MB; o real foi 836 MB.
# O preço do erro: cliente novo recusado no primeiro projeto, e ele foi tentar
# de PDF — o caminho que só estima.
# 🪤 35 é PESSIMISTA de propósito (o pior medido é 29). Este número decide se a
# conversão cabe; ele não pode ser o melhor caso.
_FATOR_EXTRACAO = 8.6           # pior caso medido
_FATOR_CONVERSAO = 35           # pessimista sobre 18,8–29× medidos nos grandes


def test_os_dois_tetos_cabem_no_container():
    """A conta que justifica os números — se alguém mexer, isto refaz a conta."""
    pico_extracao = (dx._MAX_DXF_BYTES / _MB) * _FATOR_EXTRACAO
    pico_conversao = (dx._MAX_DWG_BYTES / _MB) * _FATOR_CONVERSAO
    assert pico_extracao < _CONTAINER_MB * 0.65, (
        "teto de DXF de %d MB pede ~%.0f MB de pico — passa de 65%% do container "
        "de %d MB" % (dx._MAX_DXF_BYTES // _MB, pico_extracao, _CONTAINER_MB))
    assert pico_conversao < _CONTAINER_MB * 0.65, (
        "teto de DWG de %d MB pede ~%.0f MB na conversão — passa de 65%% do "
        "container" % (dx._MAX_DWG_BYTES // _MB, pico_conversao))


def test_a_prancha_que_a_Amanda_perdeu_passa_agora():
    """O caso concreto que motivou a mudança."""
    assert 24.58 * _MB <= dx._MAX_DWG_BYTES, (
        "o DWG de 24,58 MB dela seria barrado antes de converter")
    assert 176.5 * _MB <= dx._MAX_DXF_BYTES, (
        "o DXF de 176,5 MB dela seria descartado depois de converter")


def test_existe_teto_do_lado_do_DWG():
    """🚨 O lado que não tinha trava — e é o que derruba o servidor.

    Sem isto, um DWG de 100 MB (aceito pelo limite de upload de 450 MB) pede
    ~5 GB de conversão e mata o container de 4 GB.
    """
    assert hasattr(dx, "_MAX_DWG_BYTES"), (
        "o teto de DWG sumiu — a conversão volta a rodar sem limite nenhum")
    dwg_que_derrubaria = 100 * _MB
    assert dwg_que_derrubaria > dx._MAX_DWG_BYTES, (
        "um DWG de 100 MB passaria pela trava e pediria ~%.1f GB"
        % (100 * _FATOR_CONVERSAO / 1024))


def test_o_teto_de_DWG_nao_barra_prancha_normal():
    """Controle negativo: apertar demais quebraria quem funciona hoje.

    As 3 pranchas da cliente-16 que converteram tinham 3,1 / 5,4 / 6,4 MB. A maior
    DWG do acervo local tem 2,9 MB.
    """
    for mb in (3.1, 5.4, 6.4, 24.58):
        assert mb * _MB <= dx._MAX_DWG_BYTES, (
            "DWG de %.1f MB — tamanho de prancha REAL — seria barrado" % mb)


def test_a_trava_de_DWG_roda_ANTES_da_conversao():
    """🪤 Checar depois de converter não adianta: o estouro acontece NA conversão.

    Guarda de FORMA (o byte só aparece rodando com um DWG de 100 MB, que não dá
    pra manter no repo). Lê o corpo sem comentários — comentário já me enganou
    3 vezes num dia.
    """
    import inspect
    import main
    fonte = inspect.getsource(main.process_job) if hasattr(main, "process_job") else ""
    if not fonte:
        import io as _io
        fonte = _io.open(os.path.join(_BACKEND, "main.py"), encoding="utf-8").read()
    linhas = [l for l in fonte.split(chr(10)) if not l.strip().startswith("#")]
    corpo = chr(10).join(linhas)
    i_trava = corpo.find("_MAX_DWG_BYTES as _TETO_DWG")
    i_conv = corpo.find("dxf_path = convert_dwg_to_dxf(cad_path)")
    assert i_trava > 0, "a trava de DWG sumiu do caminho de processamento"
    assert i_conv > 0, "não achei a chamada da conversão"
    assert i_trava < i_conv, (
        "a trava de tamanho ficou DEPOIS da conversão — nessa ordem ela não "
        "protege nada, o estouro já aconteceu")


def test_controle_positivo_o_teto_ANTIGO_barrava_a_prancha_dela():
    """Prova que a mudança tem efeito real, e não é número trocado por número."""
    teto_antigo = 150 * _MB
    assert 176.5 * _MB > teto_antigo, "controle positivo furado"
    assert 176.5 * _MB <= dx._MAX_DXF_BYTES, (
        "com o teto novo a prancha dela continua barrada — a mudança não fez nada")
