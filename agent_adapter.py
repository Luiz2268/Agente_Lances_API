import asyncio
import random
from typing import Optional, Dict, Any
from storage import Storage

DEFAULT_CONFIG = {
    "initial_value": 10000.0,
    "floor_value": 8000.0,
    "decrement": 100.0,
    "interval_seconds": 2.0,
    "competitors": [
        {"name": "Concorrente A", "min_value": 8600.0},
        {"name": "Concorrente B", "min_value": 8400.0},
    ],
}

DEFAULT_STATE = {
    "status": "desligado",
    "authorized": False,
    "mode": "simulacao",
    "current_value": None,
    "last_bid": None,
    "last_bidder": None,
    "round": 0,
    "winner": None,
    "final_price": None,
    "message": "API iniciada em modo simulação."
}

class SimulationAgentAdapter:
    """
    Camada de adaptação entre a API e o agente.

    Nesta primeira versão, usa um simulador interno.
    Depois, este adapter pode ser substituído por um wrapper do
    C:\\AGENTES\\Agente_Lances_S2GPR\\src\\simulador.py
    sem alterar os endpoints usados pela Lovable.
    """
    def __init__(self, storage: Storage):
        self.storage = storage
        self.task: Optional[asyncio.Task] = None
        if not self.storage.get_json("config"):
            self.storage.set_json("config", DEFAULT_CONFIG)
        if not self.storage.get_json("state"):
            self.storage.set_json("state", DEFAULT_STATE)

    def get_config(self) -> Dict[str, Any]:
        return self.storage.get_json("config", DEFAULT_CONFIG.copy())

    def set_config(self, config: Dict[str, Any]):
        if config["floor_value"] >= config["initial_value"]:
            raise ValueError("O piso mínimo deve ser menor que o valor inicial.")
        for c in config.get("competitors", []):
            if c["min_value"] <= 0:
                raise ValueError("O valor mínimo de concorrente deve ser positivo.")
        self.storage.set_json("config", config)
        self.storage.add_log("INFO", "config_updated", "Configuração atualizada.", config)
        return self.get_config()

    def get_state(self) -> Dict[str, Any]:
        return self.storage.get_json("state", DEFAULT_STATE.copy())

    def _save_state(self, state: Dict[str, Any]):
        self.storage.set_json("state", state)

    def authorize(self):
        state = self.get_state()
        state.update({
            "authorized": True,
            "status": "pronto",
            "message": "Agente autorizado para simulação."
        })
        self._save_state(state)
        self.storage.add_log("INFO", "authorized", "Execução em modo simulação autorizada.")
        return state

    async def start(self):
        state = self.get_state()
        if not state.get("authorized"):
            raise RuntimeError("Autorize o agente antes de iniciar.")
        if state["status"] == "executando":
            return state

        cfg = self.get_config()
        state.update({
            "status": "executando",
            "current_value": cfg["initial_value"],
            "last_bid": None,
            "last_bidder": None,
            "round": 0,
            "winner": None,
            "final_price": None,
            "message": "Simulação em execução."
        })
        self._save_state(state)
        self.storage.add_log("INFO", "started", "Simulação iniciada.", cfg)

        if self.task and not self.task.done():
            self.task.cancel()
        self.task = asyncio.create_task(self._run_loop())
        return self.get_state()

    async def pause(self):
        state = self.get_state()
        if state["status"] != "executando":
            raise RuntimeError("O agente não está em execução.")
        state["status"] = "pausado"
        state["message"] = "Simulação pausada."
        self._save_state(state)
        self.storage.add_log("INFO", "paused", "Simulação pausada.")
        return state

    async def resume(self):
        state = self.get_state()
        if state["status"] != "pausado":
            raise RuntimeError("O agente não está pausado.")
        state["status"] = "executando"
        state["message"] = "Simulação retomada."
        self._save_state(state)
        self.storage.add_log("INFO", "resumed", "Simulação retomada.")
        if not self.task or self.task.done():
            self.task = asyncio.create_task(self._run_loop())
        return state

    async def stop(self):
        state = self.get_state()
        if state["status"] not in ("executando", "pausado", "pronto"):
            return state
        state["status"] = "concluido"
        state["final_price"] = state.get("current_value")
        state["winner"] = state.get("last_bidder") or "Sem vencedor"
        state["message"] = "Simulação encerrada manualmente."
        self._save_state(state)
        self.storage.add_log("INFO", "stopped", "Simulação encerrada manualmente.")
        if self.task and not self.task.done():
            self.task.cancel()
        return state

    async def _run_loop(self):
        cfg = self.get_config()
        try:
            while True:
                state = self.get_state()
                if state["status"] == "pausado":
                    await asyncio.sleep(0.5)
                    continue
                if state["status"] != "executando":
                    break

                current = float(state["current_value"])
                floor = float(cfg["floor_value"])
                decrement = float(cfg["decrement"])

                candidates = []
                next_our_bid = current - decrement
                if next_our_bid >= floor:
                    candidates.append(("Nossa Empresa", next_our_bid))

                for comp in cfg.get("competitors", []):
                    comp_floor = float(comp["min_value"])
                    # comportamento fictício: às vezes o concorrente participa
                    if current - decrement >= comp_floor and random.random() < 0.7:
                        candidates.append((comp["name"], current - decrement))

                if not candidates:
                    state["status"] = "concluido"
                    state["winner"] = state.get("last_bidder") or "Nossa Empresa"
                    state["final_price"] = state["current_value"]
                    state["message"] = "Simulação concluída."
                    self._save_state(state)
                    self.storage.add_log(
                        "INFO", "completed", "Simulação concluída.",
                        {"winner": state["winner"], "final_price": state["final_price"]}
                    )
                    break

                bidder, value = random.choice(candidates)
                value = max(value, floor if bidder == "Nossa Empresa" else value)

                state["round"] += 1
                state["current_value"] = round(value, 2)
                state["last_bid"] = round(value, 2)
                state["last_bidder"] = bidder
                state["message"] = f"Rodada {state['round']}: {bidder} ofertou {value:.2f}."
                self._save_state(state)
                self.storage.add_log(
                    "INFO", "bid",
                    state["message"],
                    {"round": state["round"], "bidder": bidder, "value": value}
                )

                await asyncio.sleep(float(cfg["interval_seconds"]))
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            state = self.get_state()
            state["status"] = "erro"
            state["message"] = str(exc)
            self._save_state(state)
            self.storage.add_log("ERROR", "engine_error", str(exc))
