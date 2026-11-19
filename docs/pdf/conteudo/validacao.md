Conversamos com **3 pessoa(s)** seguindo o roteiro de 5 perguntas (docs/validacao/ROTEIRO_VALIDACAO.md). As respostas brutas, sem dados pessoais, estão em docs/validacao/respostas.csv. Os números abaixo são contagens diretas dessas respostas.

### Quem ouvimos

- Perfis: morador(a) ou ex-morador(a) de área que alaga (3).
- Onde moram ou moraram: Rochdale, Osasco (SP) (2), Boqueirão, Curitiba (PR) (1).
- Faixa etária: 50 anos (1), 60-69 anos (1), 30 anos (1).

### O que as respostas mostram

- **Entenderam a tela de alerta sem explicação:** 3 de 3 (parcialmente: 0; não: 0).
- **Antecedência com que ficam sabendo hoje** (3 resposta(s) com número): mediana de 20 min (de 0 a 120 min).
- **Confiariam no aviso:** sim (2), depende (1).
- **Canal preferido:** sms e aplicativo (1), whatsapp (1), whatsapp e sms (1).

### Como ficam sabendo hoje

- Previsão do tempo e alertas da Defesa Civil
- Avisos do governo no celular, vizinhos próximos ou jornal na televisão
- Não há sinalização efetiva; fica sabendo somente quando já aconteceu

### O que fariam com 40 minutos de antecedência

- Salvar documentos e, se a situação for pior, até sair do local antes
- Retirar os eletrodomésticos mais importantes e separar os documentos, caso precise sair; disse que é o máximo que daria tempo de fazer
- Buscar abrigo e deixar o carro estacionado em lugar menos afetado

### Sugestões recebidas

- Aba com telefones de emergência e endereço do hospital e dos bombeiros mais próximos
- Evitar excesso de anúncios, que atrapalharia o objetivo principal do aplicativo, que é alertar

### Frases de quem ouvimos (transcritas, sem identificação)

- “Confio em meios mais tradicionais, como televisão ou mesmo em vizinhos.”
- “Hoje não tem uma sinalização efetiva e acabamos sabendo somente quando já aconteceu.”

### O que mudou no produto por causa das conversas

- **Nova tela "Telefones de emergência"** (`/emergencia`, no menu e no rodapé): uma das pessoas pediu um lugar só com os telefones de emergência e o endereço do hospital e dos bombeiros mais próximos. Entraram os telefones (199, 193, 192, 190 e 156), com toque para ligar. Os endereços por área ainda não: dependem de cadastro com a Defesa Civil local, e a tela diz isso.
- **WhatsApp entrou como próximo canal de aviso:** duas das três pessoas citaram WhatsApp (uma delas junto com SMS) e a outra, SMS e aplicativo. O protótipo envia por aplicativo, SMS e sirene; WhatsApp ainda não foi implementado.
- **Decisão: o aplicativo não terá anúncios.** Uma das pessoas disse que excesso de anúncios atrapalharia o objetivo de alertar. O modelo proposto é de serviço para prefeituras, sem publicidade para o morador.
- **Reforço do papel da sirene e dos vizinhos:** uma das pessoas disse confiar mais em meios tradicionais (televisão e vizinhos). Mantivemos a sirene na própria estação e o cadastro por lideranças do bairro como parte central da proposta.
- **O que aprendemos sobre a antecedência:** duas pessoas já recebem algum aviso hoje (20 minutos e até 2 horas, por previsão do tempo, Defesa Civil e avisos do governo no celular); a terceira só fica sabendo quando já aconteceu. Os avisos que existem são regionais; o VigIA mede o córrego da rua. Para quem já recebe aviso com 2 horas, os 40 minutos do VigIA complementam, não substituem.
