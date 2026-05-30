import socket
import struct # bib que trabalha com bytes binários compactados
import random # pra simular perda aleatória
import time
import csv
import numpy as np

"""
Função para montar o cabeçalho

- seq: 16 bits (2 bytes)
- ack_num: 16 bits (2 bytes)
- buffer: 16 bits (2 bytes)
- data_len: 13 bits
- flags (A|S|F): 3 bits 

Total: 8 bytes
"""

MAX_RWND = 15360 # 15 KB (tam max do buffer)

def create_header(seq, ack_num, rwnd, data_len, flags):
    # o último campo de 16 bits (2 bytes) combina: 13 bits (tamanho) + 3 bits (flags A|S|F) 
    last_16 = (data_len << 3) | flags
    # o shift cria "espaço" para as flags e a operação or concatena seus bits
    
    return struct.pack('!HHHH', seq, ack_num, rwnd, last_16) 
    # !HHHH: 
    # - !: big-endian (padrão para prodtocolos de rede)
    # - HHHH: 4 inteiros de 16 bits (2 bytes cada, 8 bytes no total) 

"""
Função para desmontar o cabeçalho recebido
"""
def decode_header(header):
    seq, ack_num, rwnd, last_16 = struct.unpack('!HHHH', header)
    data_len = last_16 >> 3 # extrai os 13 bits de tamanho
    flags = last_16 & 0x7 # extrai os 3 bits de flags (A, S, F) 
    # 0x7 = 0b0111
    return seq, ack_num, data_len, flags


"""
Logs
"""
def log(evento, **dados):
    tempo = f"{time.time():.3f}"
    info = " | ".join(f"{k}={v}" for k, v in dados.items())
    print(f"[{tempo}] {evento:<18} | {info}")


"""
Inicialização do socket UDP 
"""
# criando socket UDP
server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # AF_INET = IPv4, SOCK_DGRAM = UDP
server.bind(('localhost', 6789))
log("SERVER_START")

expected_seq = 0  # próximo número de sequência que o servidor espera receber 
out_of_order_buffer = {} # buffer pra pacotes recebidos fora de ordem 

while True: # sempre na escuta
    # recebe até 1032 bytes (1024 de dados + 8 de header) 
    packet, addr = server.recvfrom(1032)
    seq, ack_num, data_len, flags = decode_header(packet[:8])
    data = packet[8:] # extrai os dados com base no tamanho indicado no header
    
    # SIMULAÇÃO DE PERDA ALEATÓRIA 
    if random.random() < 0.05: # 5% dos pacotes serão "perdidos"
        log("PERDA_SIMULADA", seq=seq)
        continue

    # calc a mem ocupada pelos pacotes fora de ordem
    buffer_ocupado = sum(len(payload) for payload in out_of_order_buffer.values())
    rwnd = max(0, MAX_RWND - buffer_ocupado) # só pra evitar nums negativos

    # THREE-WAY HANDSHAKE 
    if flags & 2: # 2 = 0b010
        expected_seq = seq + 1  # def próx esperado como ISN (num seq ini) + 1
        # responde com ACK e SYN (4 + 2 = 6) 
        ack_packet = create_header(100, expected_seq, rwnd, 0, 6) 
        server.sendto(ack_packet, addr)
        log("HANDSHAKE", ack=expected_seq)
    
    # PACOTE PADRÃO (não é SYN e contém dados)
    if data_len > 0:
        if seq == expected_seq: # se for o pacote correto na ordem, faz a confirmação
            expected_seq += data_len
            log("RECEBIDO_ORDEM", seq=seq, bytes=data_len, prox_ack=expected_seq)

            while expected_seq in out_of_order_buffer: # checa se tem pacotes fora de ordem que agora podem ser processados
                log("PROCESSA_BUFFER", seq=expected_seq)
                next_data_len = len(out_of_order_buffer.pop(expected_seq))
                expected_seq += next_data_len
            
        elif seq > expected_seq: # se for um pacote futuro, armazena no buffer de fora de ordem
            if seq not in out_of_order_buffer:
                log("FORA_ORDEM", seq=seq, bytes=data_len, prox_esperado=expected_seq)
                out_of_order_buffer[seq] = data # armazena só os dados (sem o header)
        
        # sempre envia ack do que ainda tá esperando (gera acks duplicados es tiver gaps)
        ack_packet = create_header(0, expected_seq, rwnd, 0, 4) 
        server.sendto(ack_packet, addr)
        log("ACK_ENVIADO", ack=expected_seq)