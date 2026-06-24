"""CLI/REPL para conversar con FRIDAY desde la terminal."""

from __future__ import annotations

import sys

from friday.config import settings
from friday.core.brain_factory import build_brain
from friday.core.tools_registry import build_registry
from friday.storage.db import get_connection
from friday.storage.metrics_repo import MetricsRepository


def main() -> None:
    conn = get_connection(settings.db_path)
    repo = MetricsRepository(conn)
    registry = build_registry(repo)
    brain = build_brain(registry=registry)

    if brain is None:
        print(f"Error: no hay cerebro disponible (llm_provider={settings.llm_provider}).")
        print("Configurá Ollama (local) o GEMINI_API_KEY en .env.")
        sys.exit(1)

    print("FRIDAY CLI — escribí tu mensaje (Ctrl+C para salir)")
    print(f"Modelo: {brain.model}")
    print(f"Tools: {', '.join(registry.names)}")
    print("-" * 50)

    try:
        while True:
            try:
                user_input = input("\nVos > ").strip()
            except EOFError:
                break

            if not user_input:
                continue
            if user_input.lower() in ("/quit", "/exit", "/q"):
                break
            if user_input.lower() == "/reset":
                brain.reset()
                print("[Conversación reseteada]")
                continue

            response = brain.chat(user_input)
            print(f"\nFRIDAY > {response.text}")
    except KeyboardInterrupt:
        pass

    print("\nChau!")
    conn.close()


if __name__ == "__main__":
    main()
