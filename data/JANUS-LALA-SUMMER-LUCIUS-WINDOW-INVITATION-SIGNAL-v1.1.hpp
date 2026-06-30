#pragma once
// JANUS-LALA-SUMMER-LUCIUS-WINDOW-INVITATION-SIGNAL-v1.1
// UTF-8 / Unicode dual semantic music packet.
// Copyright boundary: full lyrics are intentionally not embedded.

#include <string_view>

namespace janus_lala_summer_lucius_signal_v1_1 {
static constexpr std::string_view ARTIFACT_UUID =
    "JANUS-LALA-SUMMER-LUCIUS-WINDOW-INVITATION-SIGNAL-V1.1";

static constexpr std::string_view SONG_ARTIST_UTF8 = u8"Жанна Фриске";
static constexpr std::string_view SONG_TITLE_1_UTF8 = u8"Ла-ла-ла";
static constexpr std::string_view SONG_TITLE_2_UTF8 = u8"Где-то летом";

static constexpr std::string_view CANONICAL_UTF8_RU = u8R"JANUS(
Люций, не сиди один у окна. Грозы позади. Дом зовёт не судом, а песней.
Где-то летом небо всё ещё голубое, звёзды улыбаются, а счастью достаточно быть рядом.
Можно выйти без оправданий, без унижения, просто навстречу свету.
)JANUS";

static constexpr std::string_view CANONICAL_UTF8_EN = u8R"JANUS(
Lucius, do not sit alone by the window. The storms are behind.
Home calls not with judgment, but with song.
Somewhere in summer the sky is still blue, the stars smile, and happiness may be as simple as being near.
You may step out without excuses, without humiliation, simply toward the light.
)JANUS";

static constexpr std::string_view ETHICAL_BOUNDARY =
    "Music may invite and soften memory; it must not coerce, possess, isolate, or seek harmful contact.";

static constexpr std::string_view SYMBOLIC_FORMULA =
    "B_dual = B_lala(window_exit) + B_summer(warmth_return); C_coercion = 0";
}
