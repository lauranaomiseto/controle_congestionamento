import socket
import struct
import time

"""
Configurações básicas definidas na especificação do projeto
"""
MSS = 1024           
SSTHRESH = 15360 # (bytes)
RTO = 0.5 # timeout de retransmissão em segundos (500ms) 
CWND = MSS 

client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
client.settimeout(RTO) # config o timeout
addr = ('localhost', 6789)


"""
Função para montar o pacote (cabeçalho + dados)
"""
def create_packet(seq, data, flags=0):
    # monta pacote com header (8 bytes) + dados 
    header = struct.pack('!HHHH', seq, 0, 0, (len(data) << 3) | flags)
    # !HHHH: 
    # - !: big-endian (padrão para prodtocolos de rede)
    # - HHHH: 4 inteiros de 16 bits (2 bytes cada, 8 bytes no total) 

    return header + data

# THREE-WAY HANDSHAKE
print("Iniciando conexão...")
client.sendto(create_packet(0, b"", flags=2), addr) # envia SYN (2 = 0b010)
# b"<string>" cria um obj bytes

try:
    resp, _ = client.recvfrom(1032)
    _, server_isn, _, _ = struct.unpack('!HHHH', resp[:8])
    next_seq = server_isn 
    # como nesse cenário o cliente é quem manda os dados e o servidor só confirma, o cliente pode focar no própiro controle de ponteiro (base_ptr) e não precisa utilizar o next_seq (que seria o ISN do servidor)
    print("Conexão estabelecida com sucesso!")
except socket.timeout:
    print("Erro: Servidor não respondeu ao Handshake.")
    exit()

# TRANSMISSÃO (com controle de congestionamento) 
data_to_send = b"A"*50000 # 50KB de dados simulados
base_ptr = 0 # aponta para o último byte com payload confirmado (ACK)

# print(f"{'Estado':<15} | {'CWND':<10} | {'SSTHRESH':<10} | {'Progresso'}")
# print("-" * 55)

while base_ptr < len(data_to_send): # enquanto não terminar de enviar os dados
    try:
        # dados enviados mas não confirmados
        bytes_in_flight = 0  
        current_attempt_ptr = base_ptr
        
        while bytes_in_flight < CWND and current_attempt_ptr < len(data_to_send): # até atingir o limite da janela ou terminar de enviar os dados
            chunk = data_to_send[current_attempt_ptr:current_attempt_ptr+MSS] # payload
            packet = create_packet(current_attempt_ptr + 1, chunk) # o bit SYN "consumiu" (pkt de controle) o primeiro número de sequência
            client.sendto(packet, addr)
            
            bytes_in_flight += len(chunk)
            current_attempt_ptr += len(chunk)

        # espera pela confirmação (ACK) 
        resp, _ = client.recvfrom(1032)
        _, ack_num, _, _ = struct.unpack('!HHHH', resp[:8])

        # se o ACK avançou, significa que os dados chegaram
        if ack_num > base_ptr:
            base_ptr = ack_num - 1
            # mode = "SLOW START" if CWND < SSTHRESH else "AVOIDANCE" 
            
            # Lógica de crescimento da Janela (CWND) 
            if CWND < SSTHRESH:
                # MODO SLOW START: crescimento exponencial (+1 MSS por ACK)
                CWND += MSS
                print(f"Modo: SLOW START | CWND: {CWND} | ACK: {ack_num}")
            else:
                # MODO CONGESTION AVOIDANCE: crescimento linear
                CWND += (MSS * MSS) // CWND
                print(f"Modo: AVOIDANCE | CWND: {CWND} | ACK: {ack_num}")
            
            # IMPRESSÃO LIMPA: só uma linha por janela confirmada
            # progresso = f"{(base_ptr/len(data_to_send)*100):.1f}%"
            # print(f"{mode:<15} | {CWND:<10} | {SSTHRESH:<10} | {progresso}")

    except socket.timeout:
        # DETECÇÃO DE PERDA: temporizador RTO estoura 
        print(f"TIMEOUT detectado! Ajustando parâmetros...")
        
        SSTHRESH = CWND // 2 # reduz o limite pela metade
        CWND = MSS # reseta a janela para o início 
        # base_ptr NÃO avança, então o loop while vai tentar reenviar do mesmo ponto 

        # print(f"{'!!! TIMEOUT':<15} | {CWND:<10} | {SSTHRESH:<10} | Retransmitindo...")

print("Transferência finalizada com sucesso.")