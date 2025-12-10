#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
worker_saida_posicional.py
AUTOTRADER – MONITORAMENTO DE SAÍDA POSICIONAL

Função:
- Ler preços reais do painel de ENTRADA (entrada.json)
- Atualizar PREÇO e GANHO das operações ABERTAS no painel de SAÍDA
- Atualizar DATA e HORA da última atualização
- Rodar em loop a cada 5 minutos
"""

import json
import time
import datetime as dt
from pathlib import Path

# Caminhos dos arquivos
ENTRADA_PATH = Path("/home/roteiro_ds/autotrader-planilhas-python/data/entrada.json")
SAIDA_PATH   = Path("/home/roteiro_ds/autotrader-saida-posicional/data/saida_posicional.json")


def carregar_json(caminho, default):
    try:
        with caminho.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[AVISO] Arquivo não encontrado: {caminho}")
        return default
    except json.JSONDecodeError:
        print(f"[ERRO] JSON inválido em: {caminho}")
        return default


def salvar_json(caminho, dados):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    tmp.replace(caminho)


def normalizar_par(par: str) -> str:
    """
    Normaliza o nome do par para comparação:
    - maiúsculo
    - remove '/USDT', '-USDT', 'USDT'
    - remove espaços
    Ex: 'ADA/USDT' -> 'ADA'
        'adausdt' -> 'ADA'
    """
    if not par:
        return ""
    p = par.upper().strip()
    p = p.replace("/", "").replace("-", "")
    if p.endswith("USDT"):
        p = p[:-4]
    return p.strip()


def obter_preco_posicional(entrada_data, par_saida):
    """
    Busca o preço atual do par (normalizado) na lista POSICIONAL do painel de entrada.
    """
    alvo = normalizar_par(par_saida)
    if not alvo:
        return None

    for item in entrada_data.get("posicional", []):
        par_entrada = normalizar_par(item.get("par"))
        if par_entrada == alvo:
            try:
                return float(item.get("preco", 0) or 0)
            except (TypeError, ValueError):
                return None
    return None


def calcular_ganho_real(side, entrada, preco_atual):
    """
    Calcula GANHO (ganho real) sempre POSITIVO em %.
    - LONG  : ganho se preço subiu
    - SHORT : ganho se preço caiu
    """
    try:
        entrada = float(entrada)
        preco_atual = float(preco_atual)
    except (TypeError, ValueError):
        return 0.0

    if entrada <= 0 or preco_atual <= 0:
        return 0.0

    side = (side or "").upper()

    if side == "LONG":
        pct = (preco_atual / entrada - 1.0) * 100.0
    else:  # SHORT ou qualquer outra coisa
        pct = (entrada / preco_atual - 1.0) * 100.0

    # Nunca mostrar negativo
    if pct < 0:
        pct = 0.0

    return round(pct, 2)


def atualizar_saida_uma_vez():
    entrada_data = carregar_json(ENTRADA_PATH, {"posicional": []})
    saida_raw = carregar_json(SAIDA_PATH, [])

    # Painel de saída pode ser:
    # - lista simples  [ {...}, {...} ]
    # - objeto {"operacoes": [ {...}, ... ]}
    if isinstance(saida_raw, list):
        operacoes = saida_raw
        wrapper = None
    else:
        operacoes = saida_raw.get("operacoes", [])
        wrapper = saida_raw

    agora = dt.datetime.now(dt.timezone(dt.timedelta(hours=-3)))
    data_str = agora.date().isoformat()
    hora_str = agora.strftime("%H:%M")

    total_ops = len(operacoes)
    abertas = 0
    sem_preco = 0
    total_atualizadas = 0

    for op in operacoes:
        situacao = (op.get("situacao") or op.get("status") or "").upper().strip()
        if situacao != "ABERTA":
            continue

        abertas += 1

        par = op.get("par")
        side = op.get("side") or op.get("tipo") or "NAO_ENTRAR"
        entrada = op.get("entrada")

        preco_atual = obter_preco_posicional(entrada_data, par)
        if preco_atual is None or preco_atual == 0:
            sem_preco += 1
            continue

        # Atualiza PREÇO e GANHO reais
        op["preco"] = round(preco_atual, 3)
        op["ganho"] = calcular_ganho_real(side, entrada, preco_atual)

        # Atualiza data/hora
        op["data"] = data_str
        op["hora"] = hora_str

        total_atualizadas += 1

    # Salva mantendo o formato original
    if wrapper is None:
        salvar_json(SAIDA_PATH, operacoes)
    else:
        wrapper["operacoes"] = operacoes
        salvar_json(SAIDA_PATH, wrapper)

    if total_atualizadas:
        print(
            f"[OK] Saída atualizada {data_str} {hora_str} | "
            f"Total ops: {total_ops} | Abertas: {abertas} | "
            f"Atualizadas: {total_atualizadas} | Sem preço: {sem_preco}"
        )
    else:
        print(
            f"[INFO] Nenhuma operação atualizada {data_str} {hora_str} | "
            f"Total ops: {total_ops} | Abertas: {abertas} | Sem preço: {sem_preco}"
        )


def loop_principal():
    while True:
        try:
            atualizar_saida_uma_vez()
        except Exception as e:
            print("[ERRO] Falha ao atualizar Saída:", repr(e))
        # Aguarda 5 minutos
        time.sleep(300)


if __name__ == "__main__":
    loop_principal()
