# Roteiro de validação com pessoas reais (5 minutos por pessoa)

> **Para a equipe.** Este é o único diferencial que só vocês podem produzir. Nada aqui pode ser inventado:
> registrem o que as pessoas de fato disseram. Se não der tempo de conversar com ninguém, a seção do PDF
> fica como "pendente" — é melhor do que um depoimento fabricado.

## Quem procurar (meta: 5 a 8 pessoas até 19/11 à tarde)

| Perfil | Por quê | Onde achar rápido |
|---|---|---|
| Quem mora ou já morou perto de córrego / em rua que alaga | é o cidadão beneficiado | família, vizinhos, colegas de trabalho, grupos de bairro no WhatsApp |
| Pessoa com 60+ ou que usa celular simples | testa a linguagem e a acessibilidade | pais, avós, porteiros, comerciantes |
| Alguém de Defesa Civil, subprefeitura, bombeiro, agente comunitário de saúde, líder de associação | é quem usaria o painel | contatos da equipe; vale mensagem por WhatsApp com o vídeo |

Não precisa ser presencial: mande o vídeo do pitch ou 3 prints (pasta `docs/evidencias/prints/`) e faça as perguntas por áudio ou mensagem.

## Antes de começar (30 segundos)

"Estamos fazendo um trabalho da faculdade sobre aviso de enchente. Posso te mostrar uma tela e fazer 5 perguntas rápidas?
Não vou guardar seu nome, só o que você achar." — **Anote só o primeiro nome ou um apelido, o bairro e a faixa de idade.**
Não coletem telefone, endereço nem documento.

## O que mostrar (1 minuto)

1. A tela **"Minha área"** em risco alto (print `03_minha_area.png` ou o app aberto em `/minha-area`).
2. O **texto do SMS**: `VigIA RISCO ALTO: Corrego Aricanduva pode transbordar em ate 1h. Guarde documentos no alto e prepare-se para sair. Defesa Civil 199`
3. (Para quem é da Defesa Civil ou liderança) o **painel** com a tabela "Onde agir primeiro".

## As 5 perguntas (3 minutos)

| # | Pergunta | O que estamos testando |
|---|---|---|
| 1 | "Olhando essa tela por 5 segundos: o que ela está te dizendo? O que você faria?" | a mensagem é entendida sem explicação? |
| 2 | "Hoje, como você fica sabendo que vai alagar? Com quanto tempo de antecedência?" | o problema é real para essa pessoa? qual é o 'antes'? |
| 3 | "Se esse aviso chegasse 40 minutos antes da água subir, o que daria tempo de fazer?" | o ganho medido pela IA (40 min) tem valor prático? |
| 4 | "Você confiaria nesse aviso? O que te faria desconfiar ou parar de prestar atenção?" | confiança e alarme falso |
| 5 | "Por onde você preferia receber: SMS, WhatsApp, sirene na rua, aplicativo? Tem algo que falta ou que você mudaria?" | canal e melhorias |

Para Defesa Civil / liderança, troque a 3 e a 5 por:
- "Essa tabela de prioridade ajudaria a decidir para onde mandar equipe primeiro? O que falta nela?"
- "O que impediria vocês de usar isso de verdade?"

## Como registrar (1 minuto)

Preencham uma linha por pessoa em [`respostas.csv`](respostas.csv) (abra no Excel) **logo depois da conversa**:
`data, perfil, bairro_ou_cidade, faixa_etaria, entendeu_a_tela (sim/parcial/nao), como_fica_sabendo_hoje, antecedencia_hoje_min,
o_que_faria_com_40_min, confiaria (sim/depende/nao), canal_preferido, sugestao, frase_marcante`

- **Frase marcante**: copiem uma frase curta com as palavras da pessoa (com autorização para citar sem o nome).
- Se alguém pedir uma mudança que dá para fazer rápido (ex.: trocar uma palavra), façam e anotem em "O que mudou".

## Depois das conversas (5 minutos, uma pessoa da equipe)

1. Confiram se cada conversa virou uma linha em `respostas.csv`.
2. Se alguma conversa fez vocês mudarem algo no produto (uma palavra, uma cor, a ordem das informações), escrevam em
   `docs/validacao/o_que_mudou.md`, um item por linha começando com `- `.
3. Rodem um comando só, na raiz do projeto:

   ```
   python -m devops.finalizar --video LINK_DO_VIDEO
   ```

   Ele conta as respostas, escreve a seção "Validação com pessoas reais" do PDF (só com o que está no CSV),
   grava o link do vídeo, regera o PDF, faz o commit e monta o ZIP. Sem o link ainda? Rodem sem `--video`.
4. No vídeo, se couber: 1 frase ("Conversamos com N moradores; X entenderam o alerta sem explicação").

## O que NÃO fazer

- Não inventar entrevista, número ou frase.
- Não induzir ("você gostou, né?"). Mostre e ouça.
- Não registrar nome completo, telefone ou endereço de ninguém.
