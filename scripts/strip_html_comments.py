# -*- coding: utf-8 -*-
"""Remove comentários HTML (<!-- -->) do site SERVIDO, no build do deploy.

🔒 30/08/2026 (auditoria): páginas públicas serviam, em comentários HTML,
métricas internas de negócio — taxas de funil, nº de clientes, contagens —
lidas por qualquer um com F12. Estas são NOTAS DE DESENVOLVIMENTO valiosas: a
solução não é apagá-las do fonte (perde o porquê de cada conserto), é não
SERVI-LAS. Este script roda no deploy-pages.yml sobre a cópia em _site/, então
o git mantém os comentários e o público não os vê.

🪤 O que NÃO se toca (senão quebra o site):
- conteúdo dentro de <script>, <style>, <pre>, <textarea> — lá "<!--" não é
  comentário HTML, e um "-->" pode estar dentro de uma string JS;
- comentários condicionais (<!--[if ...]>) e SSI (<!--#...) — não existem hoje
  no site, mas o guarda os preserva por segurança.
Comentário JS (// e /* */) dentro de <script> NÃO é removido aqui — exigiria um
minificador que entende string/regex/URL, risco alto. Fica pro Pedro decidir
(repo é público de qualquer forma).

Uso: python scripts/strip_html_comments.py <dir>   (default: _site)
"""
import os
import re
import sys

# blocos cujo interior é intocável (o "<!--" ali não é comentário HTML)
_PROTEGE = re.compile(
    r"(<(script|style|pre|textarea)\b[^>]*>.*?</\2>)",
    re.IGNORECASE | re.DOTALL)

# comentário HTML comum; NÃO casa condicional (<!--[if) nem SSI (<!--#)
_COMENTARIO = re.compile(r"<!--(?!\[if)(?!#).*?-->", re.DOTALL)


def limpa_html(texto):
    partes = []
    ultimo = 0
    for m in _PROTEGE.finditer(texto):
        # trecho FORA de script/style: pode limpar
        partes.append(_COMENTARIO.sub("", texto[ultimo:m.start()]))
        # bloco protegido: passa intacto
        partes.append(m.group(1))
        ultimo = m.end()
    partes.append(_COMENTARIO.sub("", texto[ultimo:]))
    return "".join(partes)


def main(raiz):
    n_arq = n_com = 0
    for base, _dirs, arqs in os.walk(raiz):
        for a in arqs:
            if not a.endswith(".html"):
                continue
            p = os.path.join(base, a)
            with open(p, encoding="utf-8") as f:
                orig = f.read()
            novo = limpa_html(orig)
            if novo != orig:
                # nº de comentários removidos (aproximado, pra log)
                antes = len(_COMENTARIO.findall(orig))
                depois = len(_COMENTARIO.findall(novo))
                n_com += antes - depois
                with open(p, "w", encoding="utf-8", newline="") as f:
                    f.write(novo)
                n_arq += 1
    print(f"[strip-comentarios] {n_arq} HTML limpos, ~{n_com} comentários removidos")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "_site")
