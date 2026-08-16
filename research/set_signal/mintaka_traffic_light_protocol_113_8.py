"""
Module: Mintaka (Orion Belt Traffic Light Signaling Protocol)
Project: JANUS 113.8
"""

import asyncio
import logging

logger = logging.getLogger("JANUS")


async def run(core) -> None:
    """Sequences Alnitak -> Alnilam -> Mintaka, establishing Mintaka

    as the final green-light destination for data telemetry dispatch.
    """
    try:
        logger.info(
            "\U0001F6A6 Initializing Mintaka Orion Belt traffic light protocol..."
        )

        belt_nodes = [
            ("Alnitak", "\U0001F534"),
            ("Alnilam", "\U0001F7E1"),
            ("Mintaka", "\U0001F7E2"),
        ]

        for node, signal in belt_nodes:
            logger.info(
                f"\U0001F4E1 Transmitting telemetry signal to {node} [State:"
                f" {signal}]"
            )
            await asyncio.sleep(0.5)

        if hasattr(core, "memory") and core.memory:
            await core.memory.log_event(
                "MINTAKA_SIGNAL_SUCCESS",
                "Orion Belt traffic light sequence completed successfully.",
            )

        logger.info(
            "\U0001F7E2 Mintaka reached. Green light active for data dispatch."
        )

    except Exception as e:
        logger.error(
            "\U0001F6A8 Error in Mintaka signaling module execution: %s", e
        )
