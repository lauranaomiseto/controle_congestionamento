import socket
import struct
import time
import csv

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
Logs
"""
def log(evento, **dados):
    tempo = f"{time.time():.3f}"
    info = " | ".join(f"{k}={v}" for k, v in dados.items())
    print(f"[{tempo}] {evento:<18} | {info}")

log_file = open("client_log.csv", "w", newline="")
writer = csv.writer(log_file)
writer.writerow(["tempo", "evento", "seq", "ack", "cwnd", "ssthresh"])

def log_csv(evento, seq=None, ack=None):
    writer.writerow([time.time(), evento, seq, ack, CWND, SSTHRESH])


"""
Função para montar o pacote (cabeçalho + dados)

- seq: 16 bits (2 bytes)
- ack_num: 16 bits (2 bytes)
- buffer: 16 bits (2 bytes)
- data_len: 13 bits
- flags (A|S|F): 3 bits 

"""
def create_packet(seq, data, flags=0):
    # monta pacote com header (8 bytes) + dados 
    header = struct.pack('!HHHH', seq, 0, 0, (len(data) << 3) | flags)
    # !HHHH: 
    # - !: big-endian (padrão para prodtocolos de rede)
    # - HHHH: 4 inteiros de 16 bits (2 bytes cada, 8 bytes no total) 

    return header + data

# THREE-WAY HANDSHAKE
log("HANDSHAKE_START")
log_csv("HANDSHAKE_START")
client.sendto(create_packet(0, b"", flags=2), addr) # envia SYN (2 = 0b010)
# b"<string>" cria um obj bytes

try:
    resp, _ = client.recvfrom(1032)
    _, server_isn, _, _ = struct.unpack('!HHHH', resp[:8])
    log("HANDSHAKE_OK")
    log_csv("HANDSHAKE_OK")
except socket.timeout:
    log("HANDSHAKE_FAIL")
    log_csv("HANDSHAKE_FAIL")
    exit()

# TRANSMISSÃO 
data_to_send = b"A"*50000 # 50KB de dados simulados
base_ptr = 0 # aponta para o último byte com payload confirmado (ACK)

while base_ptr < len(data_to_send): 
    try:
        # dados enviados mas não confirmados
        bytes_in_flight = 0  
        current_attempt_ptr = base_ptr
        
        while bytes_in_flight < CWND and current_attempt_ptr < len(data_to_send):
            chunk = data_to_send[current_attempt_ptr:current_attempt_ptr+MSS] # payload
            packet = create_packet(current_attempt_ptr+1, chunk) # o bit SYN "consumiu" (pkt de controle) o primeiro número de sequência
            client.sendto(packet, addr)
            
            log("ENVIO", seq=current_attempt_ptr+1, cwnd=CWND, ssthresh=SSTHRESH)
            log_csv("ENVIO", seq=current_attempt_ptr+1)

            bytes_in_flight += len(chunk)
            current_attempt_ptr += len(chunk)

            # espera pela confirmação (ACK) 
            resp, _ = client.recvfrom(1032)
            _, ack_num, _, _ = struct.unpack('!HHHH', resp[:8])

            # se o ACK avançou, significa que os dados chegaram
            if ack_num > base_ptr:
                base_ptr = ack_num - 1
                
                # Lógica de crescimento da Janela (CWND) 
                if CWND < SSTHRESH:
                    # MODO SLOW START: crescimento exponencial (+1 MSS por ACK)
                    CWND += MSS
                    log("CWND_UPDATE", modo="SLOW_START", cwnd=CWND, ssthresh=SSTHRESH, ack=ack_num)
                    log_csv("CWND_UPDATE_SLOW_START", ack=ack_num)
                else:
                    # MODO CONGESTION AVOIDANCE: crescimento linear
                    CWND += (MSS * MSS) // CWND
                    log("CWND_UPDATE", modo="AVOIDANCE", cwnd=CWND, ssthresh=SSTHRESH, ack=ack_num)
                    log_csv("CWND_UPDATE_AVOIDANCE", ack=ack_num)

                log_csv("ACK", ack=ack_num)


    except socket.timeout:
        # DETECÇÃO DE PERDA: temporizador RTO estoura 
        log("TIMEOUT")
        
        SSTHRESH = CWND // 2 # reduz o limite pela metade
        CWND = MSS # reseta a janela para o início 
        log("CWND_RESET", cwnd=CWND, ssthresh=SSTHRESH)

        log_csv("CWND_RESET_TIMEOUT")

        # base_ptr NÃO avança, então o loop while vai tentar reenviar do mesmo ponto 

log("FIM")