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
client.setblocking(False) # config o timeout pra config manual (não-bloqueante)
addr = ('localhost', 6789)

"""
Logs
"""
def log(evento, **dados):
    tempo = f"{time.time():.3f}"
    info = " | ".join(f"{k}={v}" for k, v in dados.items())
    print(f"[{tempo}] {evento:<18} | {info}")


inicio_absoluto = time.time()
in_fast_recovery = False

log_file = open("client_log.csv", "w", newline="")
writer = csv.writer(log_file)
writer.writerow(["tempo_relativo", "evento", "seq", "ack", "cwnd", "ssthresh", "fase"])

def log_csv(evento, seq=None, ack=None):
    # calc o tempo relativo ao início para facilitar a análise (montagem de gráficos)
    tempo_relativo = time.time() - inicio_absoluto
    
    # det em qual fase o alg está pro gráfico
    fase = "SLOW_START" if CWND < SSTHRESH else "CONGESTION_AVOIDANCE"
    
    if in_fast_recovery:
        fase = "FAST_RECOVERY"
        
    if evento == "TIMEOUT":
        fase = "LOSS"
    
    writer.writerow([
        f"{tempo_relativo:.6f}", 
        evento, 
        seq if seq is not None else "", 
        ack if ack is not None else "", 
        CWND, 
        SSTHRESH,
        fase
    ])


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
start_handshake = time.time()
handshake_success = False

while time.time() - start_handshake < RTO:
    try:
        resp, _ = client.recvfrom(1032)
        _, server_isn, rwnd, _ = struct.unpack('!HHHH', resp[:8])
        log("HANDSHAKE_OK")
        log_csv("HANDSHAKE_OK")
        handshake_success = True
        break
    except (BlockingIOError, socket.error):
        continue # Continua tentando até estourar o tempo manual

if not handshake_success:
    log("HANDSHAKE_FAIL")
    log_csv("HANDSHAKE_FAIL")
    exit()

# TRANSMISSÃO 
data_to_send = b"A"*50000 # 50KB de dados simulados
base_ptr = 0 # menor num de seq enviado mas não confirmado (ACK) pelo servidor
next_seq_ptr = 0 # o prox num de seq a ser enviado pela primeira vez
timer_start = None # cronometro pro pacote mais antigo in flight
dup_ack_count = 0 
last_ack_received = -1
unacked_packets = {} # buffer para os pacotes enviados e não confirmados

log("INICIO_TRANSMISSAO", total_bytes=len(data_to_send))
log_csv("INICIO_TRANSMISSAO", seq=0) 

while base_ptr < len(data_to_send): 
    # --- 1. FASE DE ENVIO (evia o max da cwnd) ---

    janela = min(CWND, rwnd)
    while (next_seq_ptr - base_ptr) < janela and next_seq_ptr < len(data_to_send):
        chunk = data_to_send[next_seq_ptr : next_seq_ptr + MSS] # payload
        num_seq = next_seq_ptr + 1 # o número de sequência do pacote é o byte inicial + 1 (porque o bit SYN "consome" o primeiro número)
        packet = create_packet(num_seq, chunk) 
        unacked_packets[num_seq] = packet # salva no buffer
        client.sendto(packet, addr)
        
        log("ENVIO", seq=num_seq, cwnd=CWND, base=base_ptr)
        log_csv("ENVIO", seq=num_seq) # Registra cada pacote saindo
        
        # ini cronometro pro primeiro pacote da janela
        if base_ptr == next_seq_ptr:
            timer_start = time.time()
            
        next_seq_ptr += len(chunk)

    # --- 2. FASE DE ESCUTA (processa ACKs recebidos) ---
    try:
        resp, _ = client.recvfrom(1032)
        _, ack_num, rwnd, _ = struct.unpack('!HHHH', resp[:8])

        if ack_num == last_ack_received:
            dup_ack_count += 1
            log("ACK_DUPLICADO", ack=ack_num, count=dup_ack_count)
            log_csv("ACK_DUPLICADO", ack=ack_num)

            if dup_ack_count == 3:
                log("FAST_RETRANSMIT", ack=ack_num)
                log_csv("FAST_RETRANSMIT", ack=ack_num)

                # retransmite o pacote perdido direto do buffer
                if ack_num in unacked_packets:
                    client.sendto(unacked_packets[ack_num], addr)
                
                # FAST RECOVERY
                SSTHRESH = max(CWND // 2, MSS * 2)
                CWND = SSTHRESH + (3 * MSS)
                in_fast_recovery = True

                log("FAST_RECOVERY_START", cwnd=CWND, ssthresh=SSTHRESH)
                log_csv("FAST_RECOVERY_START", ack=ack_num)

            elif in_fast_recovery:
                # cada ACK duplicado extra infla temporariamente a janela
                CWND += MSS

                log("FAST_RECOVERY_DUP_ACK", ack=ack_num, cwnd=CWND)
                log_csv("FAST_RECOVERY_DUP_ACK", ack=ack_num)

        elif ack_num > last_ack_received:
            # limpa os pacotes já confirmados do buffer
            for seq_key in list(unacked_packets.keys()):
                if seq_key < ack_num:
                    del unacked_packets[seq_key]

            if in_fast_recovery:
                # saida do fast recovery (full ack recebido)
                CWND = SSTHRESH
                in_fast_recovery = False
                log("FAST_RECOVERY_EXIT", ack=ack_num, cwnd=CWND)
                log_csv("FAST_RECOVERY_EXIT", ack=ack_num)
            
            dup_ack_count = 0
            last_ack_received = ack_num
            base_ptr = ack_num - 1 # deslisa base (ack_num é o próximo esperado, então base é ack_num-1)
        
            # CONTROLE DE CONGESTIONAMENTO: 
            if CWND < SSTHRESH:
                CWND += MSS # SLOW START
                log("ACK_SLOW_START", ack=ack_num, cwnd=CWND)
                log_csv("ACK_SLOW_START", ack=ack_num)
            else:
                CWND += (MSS * MSS) // CWND # CONGESTION AVOIDANCE
                log("ACK_CONG_AVOID", ack=ack_num, cwnd=CWND)
                log_csv("ACK_CONG_AVOID", ack=ack_num)
            
            # se ainda tiver pacotes em trânsito, reinicia o timer
            if base_ptr < next_seq_ptr:
                timer_start = time.time()
            else:
                timer_start = None # nada em trânsito
                
    except (BlockingIOError, socket.error):
        # nenhum pacote recebido no momento, segue para checar timeout
        pass

    # --- 3. FASE DE TIMEOUT (checa se o tempo expirou) ---
    if timer_start and (time.time()-timer_start > RTO):
        log("TIMEOUT", retransmitindo_de=base_ptr+1)
        log_csv("TIMEOUT", seq=base_ptr+1)

        # volta o ponteiro de envio pra base pra retransmitir tudo
        SSTHRESH = max(CWND // 2, MSS * 2)
        CWND = MSS
        next_seq_ptr = base_ptr 
        timer_start = None 
        dup_ack_count = 0
        in_fast_recovery = False

        log_csv("CWND_RESET", seq=base_ptr+1)

log("FIM_TRANSMISSAO")