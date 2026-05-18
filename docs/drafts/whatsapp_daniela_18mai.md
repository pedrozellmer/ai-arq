# WhatsApp pra Daniela — 2026-05-18 noite

**Status:** ⏳ Aguardando Pedro mandar. Texto preparado pelo Claude.
**Pra quem:** Daniela Teixeira (DTZ Arquitetura) — única usuária ativa hoje.
**Por quê:** ela ficou 5 dias sem conseguir baixar a planilha por bug que o
Claude introduziu na Wave A de proteção (13/05). Hoje (18/05) ela tentou
3× o "Projeto Naty" achando que era erro dela.

---

## Mensagem (mandar do número pessoal do Pedro)

```
Oi Daniela, é o Pedro.

Te devo uma desculpa direta. Esses dias você tentou baixar a planilha
e não rolava — não era erro seu, era um bug que eu mesmo introduzi
no sistema na semana passada e demorei mais do que devia pra fechar.
Você ficou batendo no botão sem retorno por dias por causa disso.
Sinto muito.

Subi o conserto definitivo agora. Pra funcionar do seu lado, abre
qualquer projeto, dá Ctrl+Shift+R pra forçar atualizar a página, e
clica em "Baixar XLSX". Vai descer normal. Se ainda der erro, manda
print que eu olho na hora.

Pra compensar o tempo perdido: o cashback dos 5 projetos que você
rodou hoje fica por minha conta — R$ 150 que eu credito direto no
próximo, sem você precisar enviar planilha revisada nem cotação.

Uma pergunta pra eu não errar de novo: no "Projeto Naty", o que você
esperava ver na planilha que não apareceu? Suspeito que como você
subiu só o PDF de acabamentos, o sistema não calculou a área (não
tinha planta arquitetônica). Se você me confirmar, eu já trato pra
ele mostrar isso explícito antes de processar, em vez de devolver
uma planilha parcial sem aviso.

Posso te ligar amanhã de manhã? Que horário fica bom?
```

---

## Por que esse texto

- **Admite o erro direto** — sem rodeio, sem "alguns usuários relataram"
- **Localiza a culpa em mim, não no sistema** — usuário não tem que entender bug
- **Instrução de hard refresh explícita** — sem isso ela cai no JS cacheado
- **Compensação concreta** (R$150) — não um vale-genérico, dinheiro de verdade no próximo projeto
- **Próxima pergunta útil** — vira "queixa" em informação que melhora o produto
- **Pede horário pra ligar** — toque humano, mostra que ela importa

## O que NÃO está nesse texto (de propósito)

- Não cita "RLS", "JWT", "Authorization header" — voz do cliente
- Não cita "Wave A de proteção", "_require_project_owner" — interno
- Não promete features novas pra compensar — só dinheiro e fix
- Não diz "isso não vai mais acontecer" — humildemente, pode acontecer
  de novo. O que está acontecendo é o smoke test E2E sendo construído
  AGORA pra reduzir muito a chance.
