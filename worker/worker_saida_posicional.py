#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
worker_saida_posicional.py
AUTOTRADER – PAINEL DE SAÍDA POSICIONAL
Autor: ChatGPT + Jorge
Atualizado: 2025-12-06

Função:
- Ler as operações abertas (entrada manual) em operacoes_posicional.json
- Buscar o preço atual das moedas (CoinGecko, chamada única)
- Calcular alvos (1%, 2%, 3%), PnL atual e SITUAÇÃO
- Gerar saida_posicional.json para o painel de monitoramento

Arquitetura de arquivos:
- /home/roteiro_ds/autotrader-saida-posicional/data/operacoes_posicional.json
- /home/roteiro_ds/autotrader-saida-posicional/data/saida_posicional.json
- /home/roteiro_ds/autotrader-saida-posicional/logs/worker_saida_posicional.log (opcional)

Loop:
- Roda em loop infinito, com intervalo INTERVALO segundos
- Para rodar 24/7 será conectado a um serviço systemd
"""

import json
import os
import time
import traceback
from datetime import datetime
from typing import Dict, List, Any, Set

import requests
from zoneinfo import ZoneInfo


# ============================================================
# CONFIGURAÇÕES GERAIS
# ============================================================

BASE_DIR = "/home/roteiro_ds/autotrader-saida-posicional"

DATA_DIR = os.path.join(BASE_DIR, "data")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

OPERACOES_PATH = os.path.join(DATA_DIR, "operacoes_posicional.json")
SAIDA_PATH = os.path.join(DATA_DIR, "saida_posicional.json")
LOG_PATH = os.path.join(LOGS_DIR, "worker_saida_posicional.log")

# Intervalo entre atualizações (em segundos)
# Para POSICIONAL, 300s (5 minutos) é um valor razoável.
INTERVALO = 300

# Fuso horário oficial do projeto
TZ = ZoneInfo("America/Sao_Paulo")


# ============================================================
# MAPA DE IDS DO COINGECKO
# (mesma lógica do worker MFE v2 – pode ser ajustado/expandido)
# ============================================================

COINGECKO_IDS: Dict[str, str] = {
    # Lista de 50 moedas padrão do projeto (pode ajustar depois se precisar)
    "AAVE": "aave",
    "ADA": "cardano",
    "ALGO": "algorand",
    "APT": "aptos",
    "ARB": "arbitrum",
    "AR": "arweave",
    "ATOM": "cosmos",
    "AVAX": "avalanche-2",
    "AXS": "axie-infinity",
    "BCH": "bitcoin-cash",
    "BNB": "binancecoin",
    "BTC": "bitcoin",
    "DOGE": "dogecoin",
    "DOT": "polkadot",
    "EGLD": "multiversx",
    "ETC": "ethereum-classic",
    "ETH": "ethereum",
    "FET": "fetch-ai",
    "FIL": "filecoin",
    "FLUX": "flux",
    "FTM": "fantom",
    "GALA": "gala",
    "ICP": "internet-computer",
    "IMX": "immutable-x",
    "INJ": "injective-protocol",
    "JTO": "jito-governance-token",
    "KAS": "kaspa",
    "LDO": "lido-dao",
    "LINK": "chainlink",
    "LTC": "litecoin",
    "MATIC": "matic-network",
    "NEAR": "near",
    "OP": "optimism",
    "PEPE": "pepe",
    "POL": "polygon-ecosystem-token",
    "RATS": "rats",
    "RENDER": "render-token",
    "RUNE": "thorchain",
    "SEI": "sei-network",
    "SHIB": "shiba-inu",
    "SOL": "solana",
    "SUI": "sui",
    "SNX": "synthetix-network-token",
    "TIA": "celestia",
    "TNSR": "tensor",
    "TON": "toncoin",
    "TRX": "tron",
    "UNI": "uniswap",
    "WIF": "dogwifcoin",
    "XRP": "ripple",
}


# ============================================================
# UTILITÁRIOS DE LOG
# ============================================================

def garantir_diretorios() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)


def log(msg: str) -> None:
    """Escreve mensagem no stdout e em arquivo de log."""
    dt = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    linha = f"[{dt}] {msg}"
    print(linha)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except Exception:
        # Não quebra o worker se o log falhar
        pass


# ============================================================
# LEITURA / ESCRITA DE JSON
# ============================================================

def carregar_json_caminho(caminho: str, default: Any) -> Any:
    if not os.path.exists(caminho):
        return default
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log(f"[ERRO] Falha ao ler {caminho}: {e}")
        return default


def salvar_json_caminho(caminho: str, dados: Any) -> None:
    try:
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"[ERRO] Falha ao salvar {caminho}: {e}")


def carregar_operacoes_posicional() -> Dict[str, Any]:
    """
    Formato esperado (entrada manual):

    {
      "posicional": [
        {
          "id": 1,
          "par": "BNB",
          "side": "SHORT",
          "modo": "POSICIONAL",
          "entrada": 860.300,
          "alav": 50,
          "data": "2025-12-02",
          "hora": "20:28",
          "status": "ABERTA"
        }
      ],
      "ultima_atualizacao": "..."
    }
    """
    default = {"posicional": [], "ultima_atualizacao": None}
    return carregar_json_caminho(OPERACOES_PATH, default)


# ============================================================
# PREÇOS – COINGECKO (CHAMADA ÚNICA)
# ============================================================

def mapear_ids_coingecko(pares: Set[str]) -> Dict[str, str]:
    ids: Dict[str, str] = {}
    for par in pares:
        par_up = par.upper()
        if par_up in COINGECKO_IDS:
            ids[par_up] = COINGECKO_IDS[par_up]
        else:
            # Fallback: tenta usar o símbolo em minúsculo
            fallback = par.lower()
            ids[par_up] = fallback
            log(f"[WARN] Par {par_up} não mapeado em COINGECKO_IDS. Usando fallback '{fallback}'.")
    return ids


def buscar_precos_coingecko(pares: Set[str]) -> Dict[str, float]:
    """
    Retorna um dicionário { 'BTC': 89700.0, 'ETH': 2100.0, ... }
    """
    if not pares:
        return {}

    ids_map = mapear_ids_coingecko(pares)
    ids_unicos = sorted(set(ids_map.values()))

    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": ",".join(ids_unicos),
        "vs_currencies": "usd",
    }

    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            log(f"[ERRO] CoinGecko status {resp.status_code}: {resp.text[:200]}")
            return {}

        data = resp.json()
        precos: Dict[str, float] = {}
        for par, cg_id in ids_map.items():
            info = data.get(cg_id)
            if not info or "usd" not in info:
                log(f"[WARN] Sem preço no retorno para {par} ({cg_id})")
                continue
            try:
                preco = float(info["usd"])
                precos[par] = preco
            except Exception:
                log(f"[WARN] Erro ao converter preço para {par} ({cg_id}): {info}")
        return precos

    except Exception as e:
        log(f"[ERRO] Falha ao consultar CoinGecko: {e}")
        return {}


# ============================================================
# CÁLCULOS DE ALVOS E PNL
# ============================================================

def calcular_alvos(side: str, entrada: float) -> Dict[str, float]:
    """
    Calcula ALVO 1/2/3 em US$ a partir da ENTRADA.
    Alvos fixos: 1%, 2%, 3% na direção do trade.
    """
    if entrada <= 0:
        return {
            "alvo1_us": 0.0,
            "alvo2_us": 0.0,
            "alvo3_us": 0.0,
        }

    if side.upper() == "LONG":
        alvo1 = entrada * 1.01
        alvo2 = entrada * 1.02
        alvo3 = entrada * 1.03
    else:  # SHORT
        alvo1 = entrada * (1 - 0.01)
        alvo2 = entrada * (1 - 0.02)
        alvo3 = entrada * (1 - 0.03)

    return {
        "alvo1_us": round(alvo1, 3),
        "alvo2_us": round(alvo2, 3),
        "alvo3_us": round(alvo3, 3),
    }


def calcular_pnl_pct(side: str, entrada: float, preco_atual: float) -> float:
    if entrada <= 0 or preco_atual <= 0:
        return 0.0

    if side.upper() == "LONG":
        pnl = (preco_atual - entrada) / entrada * 100.0
    else:
        pnl = (entrada - preco_atual) / entrada * 100.0

    return round(pnl, 2)


def classificar_situacao(pnl_pct: float) -> str:
    """
    Regra simples baseada em PnL atual:
    - >= 3%  -> ALVO 3
    - >= 2%  -> ALVO 2
    - >= 1%  -> ALVO 1
    - <= -3% -> STOP
    - else   -> EM ANDAMENTO
    """
    if pnl_pct >= 3.0:
        return "ALVO 3"
    if pnl_pct >= 2.0:
        return "ALVO 2"
    if pnl_pct >= 1.0:
        return "ALVO 1"
    if pnl_pct <= -3.0:
        return "STOP"
    return "EM ANDAMENTO"


# ============================================================
# PROCESSAMENTO PRINCIPAL (UMA PASSAGEM)
# ============================================================

def processar_uma_vez() -> None:
    agora = datetime.now(TZ)

    # 1) Carregar operações
    ops_data = carregar_operacoes_posicional()
    ops_lista: List[Dict[str, Any]] = ops_data.get("posicional", [])

    # Filtra apenas operações ABERTAS e modo POSICIONAL
    abertas = [
        op for op in ops_lista
        if str(op.get("status", "")).upper() == "ABERTA"
        and str(op.get("modo", "")).upper() == "POSICIONAL"
    ]

    if not abertas:
        # Se não houver operações abertas, ainda assim grava saída vazia
        saida_vazia = {
            "posicional": [],
            "ultima_atualizacao": agora.strftime("%Y-%m-%d %H:%M"),
        }
        salvar_json_caminho(SAIDA_PATH, saida_vazia)
        log("[OK] Nenhuma operação aberta. saida_posicional.json vazio.")
        return

    # 2) Buscar preços atuais para todos os pares envolvidos
    pares: Set[str] = {str(op.get("par", "")).upper() for op in abertas if op.get("par")}
    precos = buscar_precos_coingecko(pares)

    # 3) Montar saída
    saida_lista: List[Dict[str, Any]] = []

    for op in abertas:
        try:
            op_id = op.get("id")
            par = str(op.get("par", "")).upper()
            side = str(op.get("side", "")).upper()
            modo = str(op.get("modo", "")).upper()
            entrada = float(op.get("entrada", 0.0))
            alav = float(op.get("alav", 0.0)) if op.get("alav") is not None else 0.0
            data_op = op.get("data") or agora.strftime("%Y-%m-%d")
            hora_op = op.get("hora") or agora.strftime("%H:%M")

            preco_atual = precos.get(par)
            if preco_atual is None:
                # Se não conseguir preço, mantém preço igual à entrada e marca situação especial
                preco_atual = entrada
                pnl_pct = 0.0
                situacao = "SEM PREÇO"
                log(f"[WARN] Sem preço para {par}. Mantendo entrada como preço atual.")
            else:
                pnl_pct = calcular_pnl_pct(side, entrada, preco_atual)
                situacao = classificar_situacao(pnl_pct)

            alvos = calcular_alvos(side, entrada)

            saida_item = {
                "id": op_id,
                "par": par,
                "side": side,
                "modo": modo,
                "entrada": round(entrada, 3),
                "preco": round(float(preco_atual), 3) if preco_atual is not None else 0.0,
                "alvo1_us": alvos["alvo1_us"],
                "ganho1_pct": 1.00,
                "alvo2_us": alvos["alvo2_us"],
                "ganho2_pct": 2.00,
                "alvo3_us": alvos["alvo3_us"],
                "ganho3_pct": 3.00,
                "pnl_pct": pnl_pct,
                "situacao": situacao,
                "alav": alav,
                "data": data_op,
                "hora": hora_op,
            }
            saida_lista.append(saida_item)

        except Exception as e:
            log(f"[ERRO] Falha ao processar operação {op}: {e}")
            traceback.print_exc()

    saida_final = {
        "posicional": saida_lista,
        "ultima_atualizacao": agora.strftime("%Y-%m-%d %H:%M"),
    }

    salvar_json_caminho(SAIDA_PATH, saida_final)
    log(f"[OK] Atualizado {saida_final['ultima_atualizacao']} | Total operações exibidas: {len(saida_lista)}")


# ============================================================
# LOOP PRINCIPAL
# ============================================================

def loop_principal() -> None:
    garantir_diretorios()
    log("Worker Saída Posicional iniciado...")

    while True:
        try:
            processar_uma_vez()
        except Exception as e:
            log(f"[ERRO] Exceção no loop principal: {e}")
            traceback.print_exc()
        time.sleep(INTERVALO)


if __name__ == "__main__":
    loop_principal()
