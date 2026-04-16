# Controle de Congestionamento Minimalista Usando UDP

Projeto desenvolvido para a disciplina de Tópicos Avançados em Redes.

## Objetivo

Simular o algoritmo de controle de congestionamento do TCP (como Slow Start e Congestion Avoidance) utilizando UDP. A ideia é implementar manualmente o envio de pacotes, reconhecimentos (ACKs),  etransmissões e lógica da janela de congestionamento (CWND).

## Estrutura do pacote

- **Número de Sequência** (16 bits): O número de sequência do primeiro octeto de dados neste pacote (exceto quando o bit SYN está presente). Se o bit SYN estiver presente, o número de sequência é o número de sequência inicial (ISN) e o primeiro octeto de dados será ISN+1.
- **Número de Reconhecimento** (16 bits): Se o bit de controle ACK estiver ativado, este campo conterá o valor do próximo número de sequência que o remetente do segmento espera receber. Uma vez que a conexão esteja estabelecida, este campo é sempre enviado.
- **Buffer de recebimento** (16 bits): O número de octetos de dados que o remetente deste pacote está disposto a aceitar. Não será usado nesta atividade.
- **Quantidade de bytes de dados** (13 bits): Quantidade de bytes sendo enviados neste segmento.
- **A** (ACK, 1 bit): Indica que o valor do campo de Número de Reconhecimento é válido.
- **S** (SYN, 1 bit): Sincroniza os números de sequência (estabelecimento de conexão TCP).
- **F** (FIN, 1 bit): Indica que não há mais dados a serem enviados pelo remetente (encerramento da conexão TCP).

## Organização do projeto

Funções importantes: 
- `server.create_header()`: 
- `server.decode_header()`: 
