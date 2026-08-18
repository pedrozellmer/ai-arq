# -*- coding: utf-8 -*-
"""Emagrecimento STREAMING de DXF gigante (19/07).

Problema: DWG leve explode em DXF gigante na conversão ODA
(ver caso escola 17/07 — OOM no Render 2GB), e `ezdxf.readfile`
carrega o arquivo INTEIRO na RAM. A defesa era recusar acima de 150 MB.

Solução: acima de um teto de leitura segura, um passe com
`ezdxf.addons.iterdxf` — que lê entidade por entidade, memória O(1) —
copia pra um DXF enxuto SÓ o que o motor mede/lê:

  mantém: LINE, LWPOLYLINE, POLYLINE, ARC, CIRCLE, ELLIPSE, HATCH,
          TEXT, MTEXT, INSERT, DIMENSION, POINT, SOLID, ATTRIB
  descarta: 3DSOLID, MESH, IMAGE, WIPEOUT, ACAD_PROXY_ENTITY, SPLINE,
            REGION, BODY e afins — lastro que não vira quantitativo.

O header/tables/blocks são copiados como estão (o iterdxf preserva a
estrutura), então INSERTs continuam resolvendo. Se o resultado ainda for
grande demais, o guard de 150 MB do dwg_extractor continua valendo como
backstop — recusa com mensagem clara em vez de derrubar o servidor.
"""
import os
from typing import Optional

# Acima disso o readfile começa a ser arriscado no Render 2GB (o DXF em RAM
# vira ~5-10× o tamanho em disco, e ainda tem o resto do job).
LIMIAR_SLIM_MB = 60

# Tipos que alimentam medição (paredes/áreas/contagens) ou leitura (textos).
_KEEP = {
    "LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "ELLIPSE",
    "HATCH", "TEXT", "MTEXT", "INSERT", "DIMENSION", "POINT",
    "SOLID", "ATTRIB",
}


# 🚨 SUB-ENTIDADES. No arquivo, POLYLINE é seguido de N VERTEX e um SEQEND
# como entidades SEPARADAS (o mesmo vale pros ATTRIB de um INSERT). Quem filtra
# por TEXTO tem que manter esses três, senão a POLYLINE fica sem vértice e o DXF
# vira lixo. O caminho do ezdxf não precisa disso porque lá a POLYLINE já vem
# montada com os vértices dentro — armadilha exclusiva do filtro textual.
_KEEP_TEXTO = _KEEP | {"VERTEX", "SEQEND", "ATTDEF"}


def emagrecer_por_texto(path: str, out: str) -> tuple:
    """Emagrece um DXF SEM ezdxf, lendo o arquivo como bytes em pares de linhas.

    🎯 Por que existe (18/08/2026, caso Patrick): o caminho do `iterdxf` quebra
    em `AssertionError: dictionary handle #X not resolved` na hora de ESCREVER.
    Medido em 11 DXF reais convertidos por libredwg: **9 falharam**; um DXF
    escrito pelo próprio ezdxf passou (controle negativo). Ou seja, o
    emagrecedor funciona — quem quebra ele é a saída do libredwg, que é o
    caminho de TODO cliente que manda DWG (o ODA recusa quase tudo).
    Descartar o dicionário de extensão antes de escrever só salvou 3 de 11.

    Como o DXF é um formato de pares (código, valor) em linhas alternadas, dá
    pra filtrar a seção ENTITIES sem interpretar handle nenhum. Memória O(1):
    só uma entidade por vez fica no buffer.

    🪤 Trabalha em BYTES, nunca decodifica. DXF de AutoCAD antigo vem em cp1252
    e um `decode('utf-8')` estoura em acento — foi assim que um dos 11 trocou
    AssertionError por UnicodeEncodeError na tentativa anterior.

    HEADER, TABLES, BLOCKS e OBJECTS são copiados intactos, então INSERT
    continua resolvendo o bloco dele.

    Devolve (mantidas, descartadas).
    """
    keep = {t.encode("ascii") for t in _KEEP_TEXTO}
    mantidas = descartadas = 0
    dentro_entities = False
    esperando_nome = False
    buf = None
    tipo = None

    def _despeja(fo):
        nonlocal buf, tipo, mantidas, descartadas
        if buf is None:
            return
        if tipo in keep:
            fo.write(b"".join(buf))
            mantidas += 1
        else:
            descartadas += 1
        buf = None
        tipo = None

    with open(path, "rb") as fi, open(out, "wb") as fo:
        while True:
            l_cod = fi.readline()
            if not l_cod:
                break
            l_val = fi.readline()
            cod = l_cod.strip()
            val = l_val.strip()

            if cod == b"0":
                _despeja(fo)
                if val == b"SECTION":
                    esperando_nome = True
                    fo.write(l_cod); fo.write(l_val)
                elif val == b"ENDSEC":
                    dentro_entities = False
                    fo.write(l_cod); fo.write(l_val)
                elif val == b"EOF":
                    fo.write(l_cod); fo.write(l_val)
                elif dentro_entities:
                    buf = [l_cod, l_val]      # começa entidade nova
                    tipo = val
                else:
                    fo.write(l_cod); fo.write(l_val)
                continue

            if esperando_nome and cod == b"2":
                esperando_nome = False
                dentro_entities = (val == b"ENTITIES")
                fo.write(l_cod); fo.write(l_val)
                continue

            if buf is not None:
                buf.append(l_cod); buf.append(l_val)
            else:
                fo.write(l_cod); fo.write(l_val)
        _despeja(fo)
    return mantidas, descartadas


def emagrecer_dxf_se_preciso(path: str, limiar_mb: int = LIMIAR_SLIM_MB,
                             log=None) -> Optional[str]:
    """Se o DXF passa do limiar, gera `<nome>.slim.dxf` só com o que o motor
    usa e devolve o caminho novo. Devolve None quando: arquivo já é pequeno,
    o emagrecimento não rendeu (>95% do original) ou qualquer erro — nesses
    casos o chamador segue com o original (comportamento antigo).
    """
    try:
        size = os.path.getsize(path)
    except OSError:
        return None
    if size <= limiar_mb * 1024 * 1024:
        return None

    out = os.path.splitext(path)[0] + ".slim.dxf"
    mantidas = descartadas = 0
    try:
        from ezdxf.addons import iterdxf
        doc = iterdxf.opendxf(path)
        try:
            exporter = doc.export(out)
            try:
                for e in doc.modelspace():
                    if e.dxftype() in _KEEP:
                        exporter.write(e)
                        mantidas += 1
                    else:
                        descartadas += 1
            finally:
                exporter.close()
        finally:
            doc.close()
    except Exception as exc:
        # 🔁 PLANO B: o caminho do ezdxf quebra em 9 de 11 DXF de libredwg
        # (medido 18/08/2026) — e libredwg é o caminho de TODO cliente que
        # manda DWG, porque o ODA recusa quase tudo. Cair fora aqui deixava o
        # arquivo INTEIRO ir pro extrator, sem proteção nenhuma.
        # 🪤 O ganho do filtro textual nos 11 arquivos medidos foi de só 4% de
        # disco e 0% de RAM — ele NÃO resolve estouro de memória sozinho. Vale
        # porque nunca quebra e porque 4% de proteção é mais que 0%. Quem
        # prometer que isto conserta OOM está inventando.
        # 🚨 NÃO ESCREVER CÓPIA QUE NÃO SALVA NINGUÉM (18/08/2026, mesmo dia).
        # O plano B rende ~4% (medido em 11 arquivos). Se 96% do tamanho ainda
        # passa da trava dura do extrator (150 MB), a cópia vai ser escrita,
        # medida e apagada — só queima disco. No filhote do Patrick isso
        # aconteceu com 5 pranchas de 370 MB, com o disco do Render em 83%:
        # 1,85 GB de DXF + a tentativa do ezdxf + mais 355 MB do plano B.
        # 🪤 Quem introduziu esse custo fui eu, horas antes, "de graça".
        _LIMITE_DURO = 150 * 1024 * 1024        # espelha _MAX_DXF_BYTES
        if size * 0.96 > _LIMITE_DURO:
            if log is not None:
                try:
                    log("motor:dxf-slim",
                        f"arq={os.path.basename(path)} plano B textual PULADO: "
                        f"{size // 1048576} MB, nem 4% de ganho traria pra baixo "
                        f"do limite de {_LIMITE_DURO // 1048576} MB — evitando "
                        f"escrever cópia inútil em disco")
                except Exception:
                    pass
            try: os.remove(out)
            except OSError: pass
            return None
        try:
            _m, _d = emagrecer_por_texto(path, out)
            _novo = os.path.getsize(out)
            if _d > 0 and _novo < size * 0.95:
                if log is not None:
                    try:
                        log("motor:dxf-slim",
                            f"arq={os.path.basename(path)} ezdxf falhou "
                            f"({type(exc).__name__}) mas o filtro TEXTUAL salvou: "
                            f"{size // 1048576} MB -> {_novo // 1048576} MB "
                            f"({_m} mantidas, {_d} descartadas)")
                    except Exception:
                        pass
                print(f"[dxf-slim] {os.path.basename(path)}: plano B textual "
                      f"{size // 1048576} MB -> {_novo // 1048576} MB")
                return out
            try: os.remove(out)
            except OSError: pass
        except Exception as _e2:
            print(f"[dxf-slim] {os.path.basename(path)}: plano B textual também "
                  f"falhou ({type(_e2).__name__}: {_e2})")
            try: os.remove(out)
            except OSError: pass
        print(f"[dxf-slim] {os.path.basename(path)}: emagrecimento falhou "
              f"({type(exc).__name__}: {exc}) — segue com o original")
        # 🚨 A FALHA TEM QUE APARECER NO BANCO. Este passo existe pra evitar
        # ESTOURO DE MEMÓRIA em DXF grande (fix do OOM multi-DXF). Quando ele
        # falha, o arquivo segue INTEIRO pro extrator — ou seja, a proteção
        # some justamente no caso que ela deveria cobrir.
        # Até 11/08/2026 isto era só `print`: `error_log` tinha ZERO linha de
        # slim, e não dava pra saber a frequência. Medido no mesmo dia: falhou
        # em 4 de 4 arquivos testados (HWB e rafael), todos com
        # "AssertionError: dictionary handle não resolvido" — um padrão, não
        # azar. É a mesma família do preview que falhava calado.
        # 🪤 O registrador vem por PARÂMETRO, não por import de `main`: este
        # módulo também roda dentro do `dxf_extract_worker`, num subprocesso —
        # importar a app FastAPI lá seria pesado e circular. Sem `log`, cai no
        # print de sempre e nada quebra.
        if log is not None:
            try:
                log("motor:dxf-slim",
                    f"arq={os.path.basename(path)} FALHOU {type(exc).__name__}: "
                    f"{str(exc)[:160]} — segue com o arquivo INTEIRO (sem "
                    f"proteção de memória)")
            except Exception:
                pass      # log nunca pode derrubar o processamento
        try:
            if os.path.exists(out):
                os.remove(out)
        except OSError:
            pass
        return None

    try:
        novo = os.path.getsize(out)
    except OSError:
        return None
    # 🚨 O PRINT DE SUCESSO NÃO PODE MATAR O SUCESSO. A seta unicode aqui
    # estourava UnicodeEncodeError em stdout cp1252 — e como o print vem DEPOIS
    # do emagrecimento dar certo, a exceção subia e o arquivo emagrecido era
    # descartado. Medido em 18/08/2026: dos 11 DXF testados, os DOIS únicos em
    # que o ezdxf conseguiu emagrecer eram justamente os que morriam aqui.
    # 🪤 Mesma armadilha do preview de prancha (dxf_render), que já tinha
    # custado o mesmo diagnóstico errado: "falhou" quando na verdade funcionou.
    try:
        print(f"[dxf-slim] {os.path.basename(path)}: {size // 1048576} MB -> "
              f"{novo // 1048576} MB ({mantidas} entidades mantidas, "
              f"{descartadas} descartadas)")
    except Exception:
        pass
    if novo >= size * 0.95:
        # não rendeu — evita duplicar disco à toa
        try:
            os.remove(out)
        except OSError:
            pass
        return None
    return out
