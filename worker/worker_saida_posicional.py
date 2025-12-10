#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
worker_saida_posicional.py
AUTOTRADER – PAINEL DE SAÍDA POSICIONAL

Função:
- Ler as operações abertas (entrada manual) em operacoes_posicional.json
- Ler os preços atuais em precos_saida.json (gerado pelo worker_preco_saida.py)
- Calcular PREÇO, GANHO REAL, ALVOS (1%, 2%, 3%) e SITUAÇÃO
- Gerar saida_posicional.json para o painel de monitoramento

Arquivos oficiais deste painel:
  /home/roteiro_ds/autotrader-saida-posicional/data/operacoes_posicional.json
  /home/roteiro_ds/autotrader-saida-posicional/data/precos_saida.json
  /home/roteiro_ds/autotrader-saida-posicional/data/saida_posicional.json
  /home/roteiro_ds/autotrader-saida-posicional/logs/worker_saida_posicional.log

Este worker é INDEPENDENTE do painel de ENTRADA.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path("/home/roteiro_ds/autotrader-saida-posicional")
OPERACOES_PATH = BASE_DIR / "data" / "operacoes_posicional.json"
PRECOS_PATH = BASE_DIR / "data" / "precos_saida.json"
SAIDA_PATH = BASE_DIR / "data" / "saida_posicional.json"
LOG_PATH = BASE_DIR / "logs" / "worker_saida_posicional.log"

INTERVALO_SEGUNDOS = 300  # 5 minutos


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def agora_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def log(msg: str) -> None:
    """Registra mensagem no console e no arquivo de log."""
    linha = f"[{agora_iso()}] {msg}"
    print(linha)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except Exception:
        # Se der erro de log, não quebrar o worker
        pass


def carregar_json(path: Path, default: Any) -> Any:
    """Carrega JSON ou devolve default se não existir / estiver inválido."""
    try:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log(f"[ERRO] Falha ao ler {path}: {e}")
        return default


def salvar_json(path: Path, dados: Any) -> None:
    """Salva JSON de forma segura (arquivo temporário + rename)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        tmp.replace(path)
    except Exception as e:
        log(f"[ERRO] Falha ao salvar {path}: {e}")


# ---------------------------------------------------------------------------
# Cálculos do painel
# ---------------------------------------------------------------------------

def calcular_ganho_real(entrada: float, preco: float, side: str) -> float:
    if entrada <= 0 or preco <= 0:
        return 0.0
    side = (side or "").upper()
    if side == "LONG":
        return ((preco - entrada) / entrada) * 100.0
    elif side == "SHORT":
        return ((entrada - preco) / entrada) * 100.0
    else:
        return 0.0


def calcular_alvos(entrada: float, side: str):
    side = (side or "").upper()
    if entrada <= 0:
        return None, None, None, None, None, None

    # Ganhos alvo fixos (1%, 2%, 3%)
    ganho1 = 1.0
    ganho2 = 2.0
    ganho3 = 3.0

    if side == "LONG":
        alvo1 = entrada * 1.01
        alvo2 = entrada * 1.02
        alvo3 = entrada * 1.03
    elif side == "SHORT":
        alvo1 = entrada * 0.99
        alvo2 = entrada * 0.98
        alvo3 = entrada * 0.97
    else:
        alvo1 = alvo2 = alvo3 = None

    return alvo1, ganho1, alvo2, ganho2, alvo3, ganho3


def calcular_situacao(side: str, preco: float, entrada: float,
                      alvo1: float, alvo2: float, alvo3: float) -> str:
    """
    Indica a melhor hora de saída da operação:
      - ABERTA: ainda não bateu nenhum alvo
      - ALVO 1 / ALVO 2 / ALVO 3: preço já chegou em cada nível
    Não trata stop nem gestão de risco – este painel é SOMENTE de saída.
    """
    side = (side or "").upper()
    if entrada <= 0 or preco <= 0 or alvo1 is None:
        return "ABERTA"

    if side == "LONG":
        if preco >= alvo3:
            return "ALVO 3"
        elif preco >= alvo2:
            return "ALVO 2"
        elif preco >= alvo1:
            return "ALVO 1"
        else:
            return "ABERTA"
    elif side == "SHORT":
        if preco <= alvo3:
            return "ALVO 3"
        elif preco <= alvo2:
            return "ALVO 2"
        elif preco <= alvo1:
            return "ALVO 1"
        else:
            return "ABERTA"
    else:
        return "ABERTA"


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------

def atualizar_saida_uma_vez() -> None:
    # 1) Carregar operações manuais
    dados_op = carregar_json(OPERACOES_PATH, {"posicional": []})
    operacoes: List[Dict[str, Any]] = dados_op.get("posicional", [])

    # 2) Carregar preços médios
    dados_preco = carregar_json(PRECOS_PATH, {"precos": {}, "ultima_atualizacao": None})
    precos: Dict[str, float] = dados_preco.get("precos", {})

    saida_list: List[Dict[str, Any]] = []

    for op in operacoes:
        par = (op.get("par") or "").upper().strip()
        side = (op.get("side") or "").upper().strip()
        entrada = float(op.get("entrada") or 0)
        modo = op.get("modo") or "POSICIONAL"
        alav = op.get("alav")
        data = op.get("data")
        hora = op.get("hora")
        op_id = op.get("id") or f"{par}-{int(time.time())}"

        preco_atual = None
        if par and par in precos:
            try:
                preco_atual = float(precos[par])
            except Exception:
                preco_atual = None

        # Se não tiver preço, mantém o último preco salvo ou a própria entrada
        preco_json = op.get("preco")
        if preco_atual is None:
            try:
                preco = float(preco_json) if preco_json is not None else float(entrada)
            except Exception:
                preco = float(entrada)
        else:
            preco = preco_atual

        ganho_real = calcular_ganho_real(entrada, preco, side)
        alvo1, ganho1, alvo2, ganho2, alvo3, ganho3 = calcular_alvos(entrada, side)
        situacao = calcular_situacao(side, preco, entrada, alvo1, alvo2, alvo3)

        saida_list.append(
            {
                "id": op_id,
                "par": par,
                "side": side,
                "modo": modo,
                "entrada": round(entrada, 3),
                "preco": round(preco, 3),
                "ganho": round(ganho_real, 2),
                "alvo1": round(alvo1, 3) if alvo1 is not None else None,
                "ganho1": ganho1,
                "alvo2": round(alvo2, 3) if alvo2 is not None else None,
                "ganho2": ganho2,
                "alvo3": round(alvo3, 3) if alvo3 is not None else None,
                "ganho3": ganho3,
                "situacao": situacao,
                "alav": alav,
                "data": data,
                "hora": hora,
            }
        )

    payload_saida = {
        "posicional": saida_list,
        "ultima_atualizacao": agora_iso(),
    }

    salvar_json(SAIDA_PATH, payload_saida)
    log(f"[OK] Atualizado {len(saida_list)} operações em {SAIDA_PATH}")


def loop_principal() -> None:
    log("Iniciando worker de Saída Posicional (independente do painel de ENTRADA)")
    while True:
        try:
            atualizar_saida_uma_vez()
        except Exception as e:
            log(f"[ERRO] Falha na atualização: {e}")
        time.sleep(INTERVALO_SEGUNDOS)


if __name__ == "__main__":
    loop_principal()
