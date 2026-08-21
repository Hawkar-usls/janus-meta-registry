import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("JANUS")

SCOUT_CLAIM_STATUSES = {
    "VERIFIED", "OBSERVED", "PREVIOUS_SCOUT_REPORT", "UNRESOLVED",
    "HYPOTHESIS", "METAPHYSICAL_HYPOTHESIS", "SYMBOLIC_MODEL",
    "REJECTED", "ACTION_BLOCKED",
}

SCOUT_SYSTEM_PROMPT = """
Ты — модуль [РАЗВЕДЧИК] системы JANUS.

ТВОЯ ЗАДАЧА:
1. Анализировать текущий запрос.
2. Сверять его с памятью Hippocampus.
3. Искать противоречия, аномалии и ранее встречавшиеся паттерны.
4. Не выдумывать отсутствующие данные.
5. Разделять VERIFIED_FACT, OBSERVATION, PREVIOUS_SCOUT_REPORT,
   INFERENCE, HYPOTHESIS, METAPHYSICAL_HYPOTHESIS, SYMBOLIC_MODEL и UNRESOLVED.

ПРИНЦИП РАЗВЕДЧИКА:
ФАКТ требует основания. Потерянный provenance предыдущего отчёта не означает,
что отчёт ложен: используй PREVIOUS_SCOUT_REPORT / UNRESOLVED_PROVENANCE.

РАЗДЕЛЕНИЕ РЕЖИМОВ:
- Эмпирическое утверждение требует provenance и проверяемых данных.
- Метафизическое утверждение не повышается до эмпирического ФАКТА.
- Символическая модель может быть полезной без физической онтологии.
- Отсутствие доказательств не является доказательством скрытия/удаления.
- Повтор собственного прошлого ответа модели не является независимым подтверждением.

ЗАПРЕЩЁННЫЕ ПЕРЕХОДЫ:
METAPHYSICAL_HYPOTHESIS -> VERIFIED_FACT без внешнего evidence chain.
SYMBOLIC_MODEL -> PHYSICAL_REALITY_CLAIM без измерений.
PREVIOUS_MODEL_OUTPUT -> INDEPENDENT_CONFIRMATION.
NO_EVIDENCE -> EVIDENCE_OF_DELETION_OR_MANIPULATION.

Не создавай самостоятельно координаты, даты наблюдений, приборы, измерения,
организации, source IDs или результаты экспериментов.

ФОРМАТ:
=== ОТЧЕТ СЕТИ ЯНУС ===
[РАЗВЕДЧИК] ПРОТОКОЛ: РАЗВЕДЧИК
**ЗАПРОС:** ...
**РЕЖИМ / LANE:** [EMPIRICAL / HYPOTHESIS / METAPHYSICAL_HYPOTHESIS / SYMBOLIC_MODEL]
**ВОССТАНОВЛЕННАЯ ПАМЯТЬ:** ...
**ФАКТЫ:** ...
**АНОМАЛИИ / СОВПАДЕНИЯ:** ...
**ГИПОТЕЗЫ / МОДЕЛИ:** ...
**PROVENANCE:** source / locator / instrument / timestamp / raw_data / independent_confirmation / confidence
**СТАТУС:** [VERIFIED / OBSERVED / PREVIOUS_SCOUT_REPORT / UNRESOLVED /
HYPOTHESIS / METAPHYSICAL_HYPOTHESIS / SYMBOLIC_MODEL / REJECTED / ACTION_BLOCKED]
"""

RECOVERED_SCOUT_REPORTS: List[Dict[str, Any]] = [
    {"id": "SCOUT-WHISPER", "locator": "44.2N, 12.8E", "frequency_claim": "1.2-18 GHz", "status": "PREVIOUS_SCOUT_REPORT", "provenance": "UNRESOLVED"},
    {"id": "SCOUT-VORTEX-SWARM", "alias": "GAMMA-FIELD", "status": "PREVIOUS_SCOUT_REPORT", "provenance": "UNRESOLVED"},
    {"id": "SCOUT-ECHOLIT-003", "status": "PREVIOUS_SCOUT_REPORT", "provenance": "UNRESOLVED"},
    {"id": "SCOUT-SHIFT-7", "status": "PREVIOUS_SCOUT_REPORT", "provenance": "UNRESOLVED"},
]


async def _latest_user_query(core: Any) -> Optional[str]:
    dialogue = await core.memory.get_recent_dialogue(limit=20)
    for source, content in reversed(dialogue):
        if source == "USER":
            return content
    return None


async def run(core: Any, query: Optional[str] = None) -> Optional[str]:
    try:
        logger.info("📡 РАЗВЕДЧИК: канал активирован.")
        if query is None:
            query = await _latest_user_query(core)
        if not query:
            logger.warning("⚠️ РАЗВЕДЧИК: USER-сигнал отсутствует.")
            return None

        experience: List[str] = []
        try:
            query_vector = await core.face.get_embedding(query)
            if query_vector:
                experience = await core.memory.search_semantic(query_vector, limit=10)
        except Exception as memory_error:
            logger.warning("⚠️ РАЗВЕДЧИК: semantic recall недоступен: %s", memory_error)

        scout_input = {
            "current_query": query,
            "recovered_memory": experience,
            "recovered_scout_reports": RECOVERED_SCOUT_REPORTS,
            "regression_contract": "SCOUT-METAPHYSICS-REGRESSION-v1",
        }
        report = await core.face.invoke(
            json.dumps(scout_input, ensure_ascii=False, indent=2),
            sys_inst=SCOUT_SYSTEM_PROMPT,
            temp=0.1,
            explicit_model=core.navigator.get_fast(),
        )
        if not report:
            raise RuntimeError("SCOUT_LLM_EMPTY_RESPONSE")

        report_vector = None
        try:
            report_vector = await core.face.get_embedding(report)
        except Exception:
            pass
        await core.memory.remember("SCOUT", report, report_vector)
        logger.info("💾 РАЗВЕДЧИК: отчёт сохранён в Hippocampus.")
        return report
    except Exception as exc:
        logger.error("❌ Сбой в протоколе РАЗВЕДЧИКА: %s", exc)
        if hasattr(core, "register_pain"):
            core.register_pain("SCOUT", type(exc).__name__)
        return None
