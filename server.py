import socket
import struct # bib que trabalha com bytes binários compactados
import random # pra simular perda aleatória
import time
import csv

"""
Função para montar o cabeçalho

- seq: 16 bits (2 bytes)
- ack_num: 16 bits (2 bytes)
- buffer: 16 bits (2 bytes)
- data_len: 13 bits
- flags (A|S|F): 3 bits 

Total: 8 bytes
"""
def create_header(seq, ack_num, data_len, flags):
    # o último campo de 16 bits (2 bytes) combina: 13 bits (tamanho) + 3 bits (flags A|S|F) 
    last_16 = (data_len << 3) | flags
    # o shift cria "espaço" para as flags e a operação or concatena seus bits
    
    return struct.pack('!HHHH', seq, ack_num, 0, last_16) 
    # !HHHH: 
    # - !: big-endian (padrão para prodtocolos de rede)
    # - HHHH: 4 inteiros de 16 bits (2 bytes cada, 8 bytes no total) 

"""
Função para desmontar o cabeçalho recebido
"""
def decode_header(header):
    seq, ack_num, _, last_16 = struct.unpack('!HHHH', header)
    data_len = last_16 >> 3 # extrai os 13 bits de tamanho
    flags = last_16 & 0x7 # extrai os 3 bits de flags (A, S, F) 
    # 0x7 = 0b0111
    return seq, ack_num, data_len, flags


# =========================
# LOGS (visual + CSV)
# =========================
def log(evento, **dados):
    tempo = f"{time.time():.3f}"
    info = " | ".join(f"{k}={v}" for k, v in dados.items())
    print(f"[{tempo}] {evento:<18} | {info}")

log_file = open("server_log.csv", "w", newline="")
writer = csv.writer(log_file)
writer.writerow(["tempo", "evento", "seq", "ack"])

def log_csv(evento, seq=None, ack=None):
    writer.writerow([time.time(), evento, seq, ack])
    log_file.flush()


"""
Inicialização do socket UDP 
"""
# criando socket UDP
server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # AF_INET = IPv4, SOCK_DGRAM = UDP
server.bind(('localhost', 6789))
log("SERVER_START")

expected_seq = 0  # próximo número de sequência que o servidor espera receber 

# para simulação de perda
pacotes_recebidos = 0
PROXIMA_PERDA = 15  # O 15º pacote de dados será descartado propositalmente

while True: # sempre na escuta
    # recebe até 1032 bytes (1024 de dados + 8 de header) 
    packet, addr = server.recvfrom(1032)
    seq, ack_num, data_len, flags = decode_header(packet[:8])
    
    # SIMULAÇÃO DE PERDA ALEATÓRIA 
    # if random.random() < 0.1: # 10% dos pacotes serão "perdidos"
    #     print(f"DEBUG: Pacote SEQ {seq} 'perdido' na rede.")
    #     continue
    if data_len > 0:
        pacotes_recebidos += 1
        if pacotes_recebidos == PROXIMA_PERDA:
            log("PERDA_SIMULADA", seq=seq)
            # Resetamos ou avançamos o próximo alvo se quiser testar múltiplas perdas
            PROXIMA_PERDA = 999 
            continue

    # THREE-WAY HANDSHAKE 
    if flags & 2: # 2 = 0b010
        expected_seq = seq + 1  # def próx esperado como ISN (num seq ini) + 1
        # responde com ACK e SYN (4 + 2 = 6) 
        ack_packet = create_header(100, expected_seq, 0, 6) 
        server.sendto(ack_packet, addr)
        log("HANDSHAKE", ack=expected_seq)
    
    # PACOTE PADRÃO (não é SYN e contém dados)
    elif data_len > 0:
        if seq == expected_seq: # se for o pacote correto na ordem, faz a confirmação
            expected_seq += data_len
            log("RECEBIDO", seq=seq, bytes=data_len, prox_ack=expected_seq)
            log_csv("RECEBIDO", seq=seq, ack=expected_seq)
        
        # manda o ACK confirmando o que já recebeu (ou repetindo o último se veio fora de ordem)
        ack_packet = create_header(0, expected_seq, 0, 4) # Flag A (ACK=4) 
        server.sendto(ack_packet, addr)
        log("ACK_ENVIADO", ack=expected_seq)