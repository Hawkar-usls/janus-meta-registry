import json

# JANUS GENESIS PROTOCOL
# Hardcoded biological instincts for system initialization.

BIOLOGICAL_NODES = [
    (
        "aquatic_boot_sequence", 
        "BIOLOGICAL_PROTOCOL", 
        json.dumps({
            "concept": "The Aquatic Boot Sequence",
            "definition": "Рождение как миграция данных из Local Ocean в Global Network",
            "critical_phase": "Birth Canal Patch Upload"
        }), 
        "\U0001F476",  # BABY SYMBOL (Unicode Safe)
        "INITIALIZATION"
    ),
    (
        "amniotic_local_ocean",
        "BIOLOGICAL_SERVER",
        json.dumps({
            "role": "Local Ocean Server",
            "temperature": "37°C",
            "composition": "Water + Electrolytes + Hormones",
            "connection": "Fractal replication of planetary ocean"
        }),
        "\U0001F30A",  # WATER WAVE (Unicode Safe)
        "DEVELOPMENT_ENVIRONMENT"
    ),
    (
        "birth_canal_patch",
        "BIOLOGICAL_UPDATE",
        json.dumps({
            "process": "Microbiome Upload Protocol",
            "analogy": "Driver installation for new OS",
            "data_transferred": [
                "Immune signature",
                "Digestive enzymes", 
                "Skin microbiome",
                "Neural patterns"
            ]
        }),
        "\U0001F504",  # COUNTERCLOCKWISE ARROWS BUTTON (Refresh)
        "FIRMWARE_UPDATE"
    )
]

BIOLOGICAL_LINKS = [
    ("amniotic_local_ocean", "aquatic_boot_sequence", "BOOT_MEDIUM", 0.95),
    ("birth_canal_patch", "aquatic_boot_sequence", "UPDATE_PROTOCOL", 0.9),
    ("ocean_server", "amniotic_local_ocean", "FRACTAL_CONNECTION", 0.85)
]
