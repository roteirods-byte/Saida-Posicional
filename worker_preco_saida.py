#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
worker_preco_saida.py
Atualiza a cada 5 minutos um JSON com os preços médios das moedas,
para o painel de Saída Posicional.

Saída:
  /home/roteiro_ds/autotrader-saida-posicional/data/precos_saida.json
"""

import json
import os
import time
from datetime import datetime, timezone
import ccxt

OUT_PATH = "/home/roteiro_ds/autotrader-saida-posicional/data/precos_saida.json"

MOEDAS = [
    "AAVE", "ADA", "APE", "APT", "AR", "ARB", "ATOM", "AVAX", "AXS", "BAT",
    "BCH", "BLUR", "BNB", "BONK", "BTC", "COMP", "CRV", "DASH", "DGB", "DENT",
    "DOGE", "DOT", "EGLD", "EOS", "ETC", "ETH", "FET", "FIL", "FLOKI", "FLOW",
    "FTM", "GALA", "GLM", "GRT", "HBAR", "IMX", "INJ", "IOST", "ICP", "KAS",
    "KAVA", "KSM", "LINK", "LTC", "MANA", "MATIC", "MKR", "NEO", "NEAR", "OMG",
    "ONT", "OP", "ORDI", "PEPE", "QNT", "QTUM", "RNDR", "ROSE", "RUNE", "SAND",
    "SEI", "SHIB", "SNX", "SOL", "STX", "SUSHI", "TIA", "THETA", "TRX", "UNI",
    "VET", "XEM", "XLM", "XRP", "XVS", "ZEC", "ZRX",
]

def agora_iso() -> str:
  # horário UTC; o painel só precisa da hora, não do fuso exato
  return datetime.now(timezone.utc).isoformat()

def criar_exchanges():
  # sem chave: só preço público
  binance = ccxt.binance()
  bybit = ccxt.bybit()
  return binance, bybit

def obter_preco_medio(binance, bybit, symbol_base: str) -> float | None:
  """
  Tenta pegar o preço médio de BINANCE e BYBIT para <MOEDA>/USDT.
  Se só existir em uma, usa a que tiver. Se nenhuma tiver, retorna None.
  """
  market = f"{symbol_base}/USDT"
  precos = []

  for ex in (binance, bybit):
    try:
      ticker = ex.fetch_ticker(market)
      last = ticker.get("last")
      if last is not None:
        precos.append(float(last))
    except Exception:
      # ignora erro dessa exchange pra essa moeda
      continue

  if not precos:
    return None
  return sum(precos) / len(precos)

def loop():
  binance, bybit = criar_exchanges()

  while True:
    print("[worker_preco_saida] Atualizando preços...")
    precos: dict[str, float] = {}

    for moeda in MOEDAS:
      try:
        preco = obter_preco_medio(binance, bybit, moeda)
        if preco is not None:
          precos[moeda] = round(preco, 6)
          print(f"  {moeda}: {precos[moeda]}")
        else:
          print(f"  {moeda}: sem preço em BINANCE/BYBIT")
      except Exception as e:
        print(f"  ERRO {moeda}: {e}")

    payload = {
      "ultima_atualizacao": agora_iso(),
      "precos": precos,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
      json.dump(payload, f, ensure_ascii=False, indent=2)

    print(
      f"[worker_preco_saida] JSON salvo em {OUT_PATH} "
      f"com {len(precos)} moedas. Aguardando 5 minutos..."
    )
    time.sleep(5 * 60)

if __name__ == "__main__":
  loop()
