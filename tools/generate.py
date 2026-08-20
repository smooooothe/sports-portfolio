#!/usr/bin/env python3
"""Batch image generation via Recraft API (stdlib only).

Usage:
  python3 tools/generate.py --dry-run          # print prompts, no API calls
  python3 tools/generate.py --only <name>      # generate one plate
  python3 tools/generate.py --all              # generate full manifest
"""
import argparse
import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "assets" / "img" / "works"
ENV_FILE = ROOT / ".env"
API_URL = "https://external.api.recraft.ai/v1/images/generations"
MODEL = "recraftv3"
MAX_ATTEMPTS = 3  # 1 try + 2 retries, bounded
BACKOFF = (5, 15)

NO_TEXT = "no text, no letters, no typography, no logos, no watermarks"

SIZE_WIDE = "1820x1024"   # ~16:9
SIZE_SQUARE = "1024x1024"

MANIFEST = {
    "pack-cinematic-epl-16x9": {
        "size": SIZE_WIDE,
        "prompt": (
            "Premium cinematic football matchday scene, cinematic dark design trend, "
            "obsidian black background, night stadium atmosphere with volumetric haze, "
            "a single emerald green accent light beam, anonymous soccer player silhouette "
            "mid-stride with a ball, dramatic rim lighting, shallow depth of field, "
            "high-end sports editorial photography, moody chiaroscuro, "
            "large empty dark negative space on the left third of the frame for headline overlay, "
            "wide 16:9 composition, " + NO_TEXT
        ),
    },
    "pack-hud-cs2-16x9": {
        "size": SIZE_WIDE,
        "prompt": (
            "Esports arena tactical shooter atmosphere, technical HUD design trend, "
            "dark blue-grey base, glowing cyan and orange holographic interface glow, "
            "thin precise grid lines, crosshair motifs, abstract data visualization panels made "
            "of pure geometric shapes, dots, bars and lines only, futuristic esports broadcast "
            "aesthetic, subtle depth of field, large clean empty copy space in the top-left area, "
            "wide 16:9 composition, no digits, no numbers, no alphanumeric characters, "
            "no pseudo-text, no fake words, geometric glyphs only, " + NO_TEXT
        ),
    },
    "pack-dopamine-deadline-1x1": {
        "size": SIZE_SQUARE,
        "prompt": (
            "Explosive football transfer deadline energy, dopamine brights design trend, "
            "electric blue, toxic lime green and hot pink palette, glossy liquid motion 3D shapes, "
            "dynamic diagonal composition, abstract football energy burst, vibrant maximalist "
            "render, smooth lighting, clean empty copy space at the center-bottom, "
            "square 1:1 composition, " + NO_TEXT
        ),
    },
    "pack-heritage-spain-1x1": {
        "size": SIZE_SQUARE,
        "prompt": (
            "Premium neo-heritage editorial champion card artwork, deep burgundy, antique gold "
            "and cream palette, subtle paper and fabric texture, generic laurel wreath and "
            "a plain blank shield crest motif without any monogram or letterforms, decorative "
            "floral ornaments only, timeless sports heritage mood, elegant engraved illustration "
            "style, warm vignette, empty lower third of the frame for copy, "
            "no real federation emblems, square 1:1 composition, " + NO_TEXT
        ),
    },
    "pack-grunge-boxing-16x9": {
        "size": SIZE_WIDE,
        "prompt": (
            "Punk grunge boxing fight-night poster artwork, torn paper texture edges, "
            "halftone dot patterns, charcoal black, off-white and hot red palette, "
            "two anonymous boxer silhouettes facing off in aggressive stances, "
            "distressed analog screen-print feel, photocopy noise, raw xerox collage aesthetic, "
            "empty center area for copy, wide 16:9 composition, " + NO_TEXT
        ),
    },
    "pack-glass-f1-16x9": {
        "size": SIZE_WIDE,
        "prompt": (
            "Glassmorphism 2.0 style Formula 1 title race infographic plate, abstract 3D frosted "
            "glass shapes with iridescent light refraction floating over a blurred night racing "
            "circuit background, neon speed trails and motion blur, premium tech aesthetic, "
            "a sharp frosted glass panel area on the right third of the frame for data overlay, "
            "wide 16:9 composition, " + NO_TEXT
        ),
    },
}

# Probe batch (batch-02): reality-grounded creatives with baked-in typography.
# Unlike the pack plates above, these MUST render text inside the image.
PROBES = {
    "probe-1-mbappe": {
        "size": SIZE_WIDE,
        "subdir": "probes",
        "style": "realistic_image",
        "prompt": (
            "Broadcast-quality sports photograph of Kylian Mbappé, famous French football "
            "superstar, seen from a back three-quarter angle with his face turned toward the "
            "camera in profile, wearing the Real Madrid 2026/27 home kit: all-white Adidas "
            "jersey with black Adidas shoulder stripes and subtle gold trim, the name \"MBAPPÉ\" "
            "and the number 9 printed in black on the back of the jersey, arms spread wide in a "
            "goal celebration at the Santiago Bernabéu stadium at night, packed white-clad "
            "stands, dramatic floodlights, shallow depth of field, shot on a 400mm telephoto "
            "lens, Getty Images match photography look. The photo is designed as a Bleacher "
            "Report style social card: a bold condensed uppercase italic sans-serif headline in "
            "Russian language reads \"МБАППЕ. НОВАЯ ЭРА\" in large white letters with a thin "
            "gold underline, placed in the lower-left third of the frame. "
            "Wide 16:9 composition."
        ),
    },
    "probe-2-spain": {
        "size": SIZE_WIDE,
        "subdir": "probes",
        "style": "realistic_image",
        "prompt": (
            "Premium editorial sports photograph: Spain national football team players in red "
            "Adidas home jerseys with thin yellow stripes and blue shorts celebrate winning the "
            "FIFA World Cup 2026 final at MetLife Stadium, the team captain lifts the golden "
            "FIFA World Cup trophy with its malachite base high above his head, golden confetti "
            "raining down, fireworks over the grey stands, green pitch, night floodlights, "
            "euphoric crowd, professional sports photography, high-end editorial retouching, "
            "rich cinematic contrast. Typography is part of the design: a large elegant bold "
            "uppercase sans-serif headline in Russian language reads \"ИСПАНИЯ — ЧЕМПИОН МИРА\" "
            "in white letters across the top of the frame, and a smaller gold line beneath it "
            "reads \"ФИНАЛ 2:1\". Wide 16:9 composition."
        ),
    },
    "probe-3-navi": {
        "size": SIZE_WIDE,
        "subdir": "probes",
        "style": "realistic_image",
        "prompt": (
            "Esports championship broadcast photograph: Natus Vincere (NAVI) Counter-Strike 2 "
            "players in black jerseys with bright yellow Puma accents lift the golden faceted "
            "Esports World Cup trophy on a huge arena stage in Riyadh, golden confetti and "
            "pyrotechnics, giant LED screens glowing with NAVI black-and-yellow branding behind "
            "them, dramatic arena spotlights, professional esports broadcast photography with "
            "subtle HUD-style graphic overlays. A heavy condensed uppercase sans-serif headline "
            "in English reads \"NAVI WIN ESPORTS WORLD CUP\" in bright yellow letters with a "
            "black outline across the lower third of the frame, esports broadcast graphics "
            "style. Wide 16:9 composition."
        ),
    },
}

MANIFEST.update(PROBES)

# Probe batch v4 (batch-02 regeneration): same 3 subjects on recraftv4_1_pro (2K),
# with strengthened typography instructions vs the v1 probes above.
SIZE_WIDE_2K = "2688x1536"  # 16:9 @ 2K, recraftv4_1_pro only
MODEL_V4_PRO = "recraftv4_1_pro"

PROBES_V4 = {
    "probe-v4-mbappe": {
        "size": SIZE_WIDE_2K,
        "subdir": "probes",
        # recraftv4_1_pro rejects style="realistic_image" (HTTP 400); default is photoreal
        "model": MODEL_V4_PRO,
        "prompt": (
            "Premium broadcast sports card photograph of Kylian Mbappé, famous French "
            "football superstar, seen from behind at a three-quarter angle with his face "
            "turned toward the camera in profile, wearing the Real Madrid 2026/27 home "
            "kit: all-white Adidas jersey with black Adidas shoulder stripes, subtle gold "
            "trim and the \"Emirates Fly Better\" chest sponsor, the name \"MBAPPÉ\" and "
            "the number 9 printed in black on the back of the jersey, arms spread wide in "
            "a goal celebration at the Santiago Bernabéu stadium at night, packed "
            "white-clad stands, dramatic floodlights, shallow depth of field, shot on a "
            "400mm telephoto lens, Getty Images match photography look, ultra-detailed "
            "fabric texture. The image is designed as a premium broadcast card: the exact "
            "headline text \"МБАППЕ. НОВАЯ ЭРА\" set in a bold condensed uppercase "
            "sans-serif font, large white letters with a thin gold underline, placed in "
            "the lower-left third of the frame, crisp legible typography, correct "
            "spelling, professional graphic design. Wide 16:9 composition."
        ),
    },
    "probe-v4-spain": {
        "size": SIZE_WIDE_2K,
        "subdir": "probes",
        "model": MODEL_V4_PRO,
        "prompt": (
            "Premium editorial sports photograph: Spain national football team players in "
            "red Adidas home jerseys with thin yellow stripes and blue shorts celebrate "
            "winning the FIFA World Cup 2026 final at MetLife Stadium, the team captain "
            "lifts the golden FIFA World Cup trophy with its malachite base high above "
            "his head, golden confetti raining down, fireworks over the grey stands, "
            "green pitch, night floodlights, euphoric crowd, professional sports "
            "photography, high-end editorial retouching, rich cinematic contrast, "
            "ultra-detailed. Typography is part of the design: the exact headline text "
            "\"ИСПАНИЯ — ЧЕМПИОН МИРА\" set in a large elegant bold uppercase editorial "
            "sans-serif font in white letters across the top of the frame, and a smaller "
            "gold line beneath it with the exact text \"ФИНАЛ 2:1\", crisp legible "
            "typography, correct spelling, professional graphic design. "
            "Wide 16:9 composition."
        ),
    },
    "probe-v4-navi": {
        "size": SIZE_WIDE_2K,
        "subdir": "probes",
        "model": MODEL_V4_PRO,
        "prompt": (
            "Esports championship broadcast photograph: Natus Vincere (NAVI) "
            "Counter-Strike 2 players in black jerseys with bright yellow accents lift "
            "the golden faceted Esports World Cup trophy on a huge arena stage in "
            "Riyadh, golden confetti and pyrotechnics, giant LED screens glowing with "
            "NAVI black-and-yellow branding behind them, dramatic arena spotlights, "
            "professional esports broadcast photography with subtle HUD-style graphic "
            "overlays, ultra-detailed. The exact headline text \"NAVI WIN ESPORTS WORLD "
            "CUP\" set in a heavy condensed uppercase sans-serif font, bright yellow "
            "letters with a black outline across the lower third of the frame, esports "
            "broadcast graphics style, crisp legible typography, correct spelling. "
            "Wide 16:9 composition."
        ),
    },
}

MANIFEST.update(PROBES_V4)

# Final batch (batch-03): 17 reality-grounded event cards on recraftv4_1 (plain, 1K).
# 16:9 for plain V4.1 is 1344x768 (Pro tiers use 2688x1536). V4.1 may reject
# style="realistic_image" like the Pro tier did — generate_one() auto-retries
# without style on HTTP 400. Each card carries a 2026 design-trend treatment.
SIZE_WIDE_V4 = "1344x768"  # 16:9 @ 1K, recraftv4_1 / recraftv4
MODEL_V4 = "recraftv4_1"

FINAL = {
    "evt-yamal-ballon": {
        "size": SIZE_WIDE_V4,
        "subdir": "final",
        "group": "final",
        "model": MODEL_V4,
        "style": "realistic_image",
        "trend": "neo-heritage editorial",
        "prompt": (
            "Premium neo-heritage editorial sports card photograph of Lamine Yamal, "
            "FC Barcelona superstar, seen from behind at a three-quarter angle, wearing "
            "the Barcelona 2026/27 home kit: classic blue and garnet vertical striped "
            "Nike jersey with the Spotify chest logo and the number 19 on the back, "
            "standing on the pitch of the Spotify Camp Nou at golden hour, holding a "
            "golden football under his arm, deep burgundy and antique gold color grade, "
            "subtle film grain, elegant engraved editorial retouching, warm vignette, "
            "timeless heritage mood. Typography is part of the design: the exact "
            "headline text \"ЯМАЛЬ. ЗОЛОТОЙ ФАВОРИТ\" set in an elegant bold uppercase "
            "serif font in antique gold letters across the top of the frame, and a "
            "smaller cream line beneath it with the exact text \"БАРСЕЛОНА · СЕЗОН "
            "2026/27\", crisp legible typography, correct spelling, professional "
            "graphic design. Wide 16:9 composition."
        ),
    },
    "evt-rodri-barca": {
        "size": SIZE_WIDE_V4,
        "subdir": "final",
        "group": "final",
        "model": MODEL_V4,
        "style": "realistic_image",
        "trend": "dopamine brights",
        "prompt": (
            "Explosive football transfer announcement card, dopamine brights design "
            "trend: Rodrigo Hernandez (Rodri), Spanish midfielder, seen from behind "
            "wearing the FC Barcelona 2026/27 home kit — blue and garnet vertical "
            "striped Nike jersey with Spotify sponsor and the number 16 on the back — "
            "holding a Barcelona scarf above his head with both hands on the Camp Nou "
            "pitch, electric blue and hot pink stadium light flares, glossy vibrant "
            "maximalist color grade, dynamic diagonal composition, confetti in the "
            "air, premium sports photography with bold graphic energy. Typography is "
            "part of the design: the exact headline text \"РОДРИ ТЕПЕРЬ В БАРСЕЛОНЕ\" "
            "set in a heavy uppercase sans-serif font, white letters with a hot pink "
            "drop shadow across the lower third of the frame, and a smaller "
            "monospaced line with the exact text \"ТРАНСФЕР · 115 МЛН ЕВРО\", crisp "
            "legible typography, correct spelling, professional graphic design. "
            "Wide 16:9 composition."
        ),
    },
    "evt-rogers-chelsea": {
        "size": SIZE_WIDE_V4,
        "subdir": "final",
        "group": "final",
        "model": MODEL_V4,
        "style": "realistic_image",
        "trend": "dopamine brights",
        "prompt": (
            "Dopamine brights football transfer card: Morgan Rogers, English "
            "midfielder, seen from behind at a three-quarter angle wearing the "
            "Chelsea 2026/27 home kit — royal blue Nike jersey with white and gold "
            "details, the Infinite Athletic chest sponsor and the number 27 on the "
            "back — raising his arms to the Stamford Bridge stands, electric lime "
            "green and vivid blue graphic energy bursts around him, glossy vibrant "
            "maximalist color grade, dynamic diagonal composition, premium sports "
            "photography. Typography is part of the design: the exact headline text "
            "\"РОДЖЕРС — ИГРОК ЧЕЛСИ\" set in a heavy uppercase sans-serif font, "
            "white letters with an electric blue outline in the lower left of the "
            "frame, and a smaller monospaced line with the exact text \"ТРАНСФЕР · "
            "65 МЛН ФУНТОВ\", crisp legible typography, correct spelling, "
            "professional graphic design. Wide 16:9 composition."
        ),
    },
    "evt-ederson-city": {
        "size": SIZE_WIDE_V4,
        "subdir": "final",
        "group": "final",
        "model": MODEL_V4,
        "style": "realistic_image",
        "trend": "glassmorphism",
        "prompt": (
            "Glassmorphism football transfer card: Ederson Silva, Brazilian "
            "midfielder, seen from behind wearing the Manchester City 2026/27 home "
            "kit — sky blue Puma jersey with the Etihad Airways chest sponsor and "
            "the number 13 on the back — on the Etihad Stadium pitch at dusk, "
            "frosted glass panels with iridescent light refraction floating in the "
            "foreground, soft blurred stadium lights, premium tech aesthetic, cool "
            "blue palette. Typography is part of the design: the exact headline "
            "text \"ЭДЕРСОН ТЕПЕРЬ В СИТИ\" set in a clean modern uppercase "
            "sans-serif font, white letters on a frosted glass panel in the lower "
            "third of the frame, and a smaller line with the exact text "
            "\"МАНЧЕСТЕР СИТИ · 60 МЛН ЕВРО\", crisp legible typography, correct "
            "spelling, professional graphic design. Wide 16:9 composition."
        ),
    },
    "evt-epl-start": {
        "size": SIZE_WIDE_V4,
        "subdir": "final",
        "group": "final",
        "model": MODEL_V4,
        "style": "realistic_image",
        "trend": "cinematic dark",
        "prompt": (
            "Cinematic dark matchday card: Manchester United players in classic red "
            "Adidas home jerseys with the Snapdragon chest sponsor celebrate a goal "
            "at Old Trafford at night, the number 10 visible on one player's back, "
            "packed Stretford End stands, dramatic floodlights cutting through light "
            "rain and haze, obsidian black shadows with a single emerald accent "
            "light beam, moody chiaroscuro, high-end editorial sports photography. "
            "Typography is part of the design: the exact headline text \"АПЛ "
            "СТАРТОВАЛА\" set in a bold condensed uppercase sans-serif font, large "
            "white letters in the left third of the frame, and a smaller gold "
            "monospaced line with the exact text \"МЮ 2:0 ЛЕСТЕР · ОЛД ТРАФФОРД\", "
            "crisp legible typography, correct spelling, professional graphic "
            "design. Wide 16:9 composition."
        ),
    },
    "evt-zenit-supercup": {
        "size": SIZE_WIDE_V4,
        "subdir": "final",
        "group": "final",
        "model": MODEL_V4,
        "style": "realistic_image",
        "trend": "cinematic dark",
        "prompt": (
            "Cinematic dark trophy card: Zenit Saint Petersburg players in azure "
            "blue Joma jerseys with the Gazprom sponsor and two gold stars above "
            "the club crest lift the Russian Super Cup trophy at Gazprom Arena "
            "under the closed roof at night, silver confetti raining down, dramatic "
            "spotlights through haze, deep blue and silver palette, moody premium "
            "sports photography. Typography is part of the design: the exact "
            "headline text \"ЗЕНИТ ВЗЯЛ СУПЕРКУБОК\" set in a bold condensed "
            "uppercase sans-serif font, white letters across the top of the frame, "
            "and a smaller azure line with the exact text \"ЗЕНИТ 3:1 СПАРТАК · "
            "ГАЗПРОМ АРЕНА\", crisp legible typography, correct spelling, "
            "professional graphic design. Wide 16:9 composition."
        ),
    },
    "evt-usopen-2026": {
        "size": SIZE_WIDE_V4,
        "subdir": "final",
        "group": "final",
        "model": MODEL_V4,
        "style": "realistic_image",
        "trend": "neo-heritage editorial",
        "prompt": (
            "Neo-heritage editorial tennis card: a tennis player seen from behind "
            "serving on the blue hard court of Arthur Ashe Stadium at dusk, green "
            "out-of-bounds areas, packed stands, a yellow tennis ball tossed high "
            "into the lights, elegant deep navy and cream color grade with antique "
            "gold accents, subtle film grain, timeless Grand Slam heritage mood, "
            "premium editorial sports photography. Typography is part of the "
            "design: the exact headline text \"US OPEN 2026\" set in an elegant "
            "bold uppercase serif font in cream letters across the top of the "
            "frame, and a smaller gold line with the exact text \"НЬЮ-ЙОРК · 31 "
            "АВГУСТА — 13 СЕНТЯБРЯ\", crisp legible typography, correct spelling, "
            "professional graphic design. Wide 16:9 composition."
        ),
    },
    "evt-f1-title": {
        "size": SIZE_WIDE_V4,
        "subdir": "final",
        "group": "final",
        "model": MODEL_V4,
        "style": "realistic_image",
        "trend": "glassmorphism",
        "prompt": (
            "Glassmorphism Formula 1 title race card: two Formula 1 cars wheel to "
            "wheel at night under floodlights — a silver-black Mercedes with "
            "turquoise Petronas accents and the number 12 alongside a bright red "
            "Ferrari with HP sponsor logos and the number 44 — sparks and neon "
            "speed trails, frosted glass graphic panels with iridescent refraction "
            "floating over the scene, blurred night circuit background, premium "
            "tech aesthetic. Typography is part of the design: the exact headline "
            "text \"АНТОНЕЛЛИ ПРОТИВ ХЭМИЛТОНА\" set in a sharp italic uppercase "
            "sans-serif font, white letters on a frosted glass band across the "
            "lower third of the frame, and a smaller line with the exact text "
            "\"ФОРМУЛА 1 · БИТВА ЗА ТИТУЛ\", crisp legible typography, correct "
            "spelling, professional graphic design. Wide 16:9 composition."
        ),
    },
    "evt-nba-murray": {
        "size": SIZE_WIDE_V4,
        "subdir": "final",
        "group": "final",
        "model": MODEL_V4,
        "style": "realistic_image",
        "trend": "dopamine brights",
        "prompt": (
            "Dopamine brights NBA trade card: Dejounte Murray, American basketball "
            "guard, seen from behind wearing the Cleveland Cavaliers 2026/27 wine "
            "red and gold Nike jersey with the number 5 on the back, holding a "
            "basketball on his hip on the court of Rocket Mortgage FieldHouse, "
            "electric pink and gold graphic energy bursts, glossy maximalist color "
            "grade, dynamic diagonal composition, premium sports photography. "
            "Typography is part of the design: the exact headline text \"МЮРРЕЙ — "
            "В КЛИВЛЕНДЕ\" set in a heavy uppercase sans-serif font, gold letters "
            "with a wine red outline across the lower third of the frame, and a "
            "smaller monospaced line with the exact text \"НБА · ОБМЕН ИЗ "
            "НЬЮ-ОРЛЕАНА\", crisp legible typography, correct spelling, "
            "professional graphic design. Wide 16:9 composition."
        ),
    },
    "evt-romero-cruz": {
        "size": SIZE_WIDE_V4,
        "subdir": "final",
        "group": "final",
        "model": MODEL_V4,
        "style": "realistic_image",
        "trend": "punk-grunge",
        "prompt": (
            "Punk grunge boxing fight-night card: two boxers facing off under neon "
            "lights at T-Mobile Arena in Las Vegas — one in gold and black shorts, "
            "the other in green, white and red shorts — torn paper texture edges, "
            "halftone dot patterns, charcoal black, off-white and hot red palette, "
            "distressed analog screen-print feel, photocopy noise, raw xerox "
            "collage aesthetic over the packed arena crowd. Typography is part of "
            "the design: the exact headline text \"РОМЕРО — КРУС II\" set in a "
            "distressed heavy uppercase sans-serif font, off-white letters across "
            "the center of the frame, and a smaller red monospaced line with the "
            "exact text \"ЛАС-ВЕГАС · ПОБЕДА КРУСА РЕШЕНИЕМ СУДЕЙ\", crisp legible "
            "typography, correct spelling, professional graphic design. "
            "Wide 16:9 composition."
        ),
    },
    "evt-ti2026-playoffs": {
        "size": SIZE_WIDE_V4,
        "subdir": "final",
        "group": "final",
        "model": MODEL_V4,
        "style": "realistic_image",
        "trend": "HUD/technical",
        "prompt": (
            "HUD technical esports card for The International 2026 Dota 2 playoffs: "
            "a dark arena stage with five players at glowing computers seen from "
            "behind, the bronze Aegis of Champions shield trophy with silver inlay "
            "on a pedestal in the foreground, golden-green neon stage lighting, "
            "holographic interface panels with thin grid lines and data bars "
            "floating in the air, cyan and orange glow, futuristic esports "
            "broadcast aesthetic. Typography is part of the design: the exact "
            "headline text \"THE INTERNATIONAL 2026\" set in a geometric uppercase "
            "sans-serif font, glowing gold letters across the top of the frame, "
            "and a smaller cyan monospaced line with the exact text \"ПЛЕЙ-ОФФ · "
            "SPIRIT · LIQUID\", crisp legible typography, correct spelling, "
            "professional graphic design. Wide 16:9 composition."
        ),
    },
    "evt-lck-final": {
        "size": SIZE_WIDE_V4,
        "subdir": "final",
        "group": "final",
        "model": MODEL_V4,
        "style": "realistic_image",
        "trend": "HUD/technical",
        "prompt": (
            "HUD technical esports card: Gen.G League of Legends players in black "
            "and gold jerseys lift the LCK Summer split trophy on stage at LoL "
            "Park in Seoul, golden confetti, defeated T1 players in red and black "
            "Nike jerseys visible in the background, holographic gold star and "
            "eagle-wing graphics, thin grid lines and data panels floating in the "
            "air, dark arena with gold and cyan glow, futuristic Korean esports "
            "broadcast aesthetic. Typography is part of the design: the exact "
            "headline text \"GEN.G — ЧЕМПИОН LCK\" set in a heavy uppercase "
            "sans-serif font, gold letters with a black outline across the lower "
            "third of the frame, and a smaller cyan monospaced line with the exact "
            "text \"ФИНАЛ 3:1 ПРОТИВ T1 · WORLDS 2026\", crisp legible typography, "
            "correct spelling, professional graphic design. Wide 16:9 composition."
        ),
    },
    "evt-valorant-champions": {
        "size": SIZE_WIDE_V4,
        "subdir": "final",
        "group": "final",
        "model": MODEL_V4,
        "style": "realistic_image",
        "trend": "glassmorphism",
        "prompt": (
            "Glassmorphism esports card for Valorant Champions 2026 in Seoul: "
            "players at glowing gaming stations on a vast stage seen from behind, "
            "a giant golden V-shaped crystal trophy glowing center stage, frosted "
            "glass panels with iridescent red and violet refraction floating over "
            "the scene, blurred Seoul night skyline visible through arena glass, "
            "neon haze, premium tech aesthetic. Typography is part of the design: "
            "the exact headline text \"VALORANT CHAMPIONS 2026\" set in a sharp "
            "futuristic uppercase sans-serif font, white letters on a frosted "
            "glass band across the top of the frame, and a smaller line with the "
            "exact text \"СЕУЛ · FNATIC · SENTINELS\", crisp legible typography, "
            "correct spelling, professional graphic design. Wide 16:9 composition."
        ),
    },
    "evt-evo-2026": {
        "size": SIZE_WIDE_V4,
        "subdir": "final",
        "group": "final",
        "model": MODEL_V4,
        "style": "realistic_image",
        "trend": "punk-grunge",
        "prompt": (
            "Punk grunge fighting-game card for EVO 2026 in Las Vegas: a Japanese "
            "player raising an arcade fightstick above his head in victory on the "
            "Mandalay Bay stage, seen from behind, huge screens with Street "
            "Fighter 6 gameplay glowing behind him, torn paper texture edges, "
            "halftone dot patterns, charcoal black, off-white, orange, violet and "
            "blue palette, distressed analog screen-print feel, photocopy noise, "
            "raw xerox collage aesthetic. Typography is part of the design: the "
            "exact headline text \"KAKERU ВЗЯЛ EVO 2026\" set in a distressed "
            "heavy uppercase sans-serif font, off-white letters across the top of "
            "the frame, and a smaller orange monospaced line with the exact text "
            "\"STREET FIGHTER 6 · ЛАС-ВЕГАС\", crisp legible typography, correct "
            "spelling, professional graphic design. Wide 16:9 composition."
        ),
    },
    "evt-pubg-pgs": {
        "size": SIZE_WIDE_V4,
        "subdir": "final",
        "group": "final",
        "model": MODEL_V4,
        "style": "realistic_image",
        "trend": "HUD/technical",
        "prompt": (
            "HUD technical esports card: Petrichor Road PUBG players celebrate "
            "victory at their gaming stations seen from behind, a golden shield "
            "trophy with a star and a level-3 helmet motif on the stage, "
            "holographic interface overlays with thin grid lines and data bars, a "
            "blurred green Erangel battlefield on the giant screen behind them, "
            "dark arena with gold and cyan glow, futuristic esports broadcast "
            "aesthetic. Typography is part of the design: the exact headline text "
            "\"PETRICHOR ROAD — ЧЕМПИОН PGS\" set in a geometric uppercase "
            "sans-serif font, glowing gold letters across the lower third of the "
            "frame, and a smaller cyan monospaced line with the exact text \"PUBG "
            "GLOBAL SERIES 2026\", crisp legible typography, correct spelling, "
            "professional graphic design. Wide 16:9 composition."
        ),
    },
    "evt-apex-algs": {
        "size": SIZE_WIDE_V4,
        "subdir": "final",
        "group": "final",
        "model": MODEL_V4,
        "style": "realistic_image",
        "trend": "cinematic dark",
        "prompt": (
            "Cinematic dark esports championship card: Team Falcons players in "
            "black and green jerseys lift the ALGS Year 6 championship trophy — a "
            "stylized red Apex crown with golden wings — on a Tokyo arena stage at "
            "night, green confetti raining down, dramatic spotlights cutting "
            "through haze, obsidian black shadows with an emerald accent light, "
            "moody premium esports photography. Typography is part of the design: "
            "the exact headline text \"TEAM FALCONS — ЧЕМПИОН ALGS\" set in a bold "
            "condensed uppercase sans-serif font, white letters across the top of "
            "the frame, and a smaller green monospaced line with the exact text "
            "\"ТОКИО · ФИНАЛ ПРОТИВ ALLIANCE\", crisp legible typography, correct "
            "spelling, professional graphic design. Wide 16:9 composition."
        ),
    },
    "evt-brawl-zeta": {
        "size": SIZE_WIDE_V4,
        "subdir": "final",
        "group": "final",
        "model": MODEL_V4,
        "style": "realistic_image",
        "trend": "dopamine brights",
        "prompt": (
            "Dopamine brights mobile esports card: Zeta Division players holding "
            "gaming smartphones celebrate victory on a championship stage, "
            "colorful cartoonish Brawl Stars characters on giant screens behind "
            "them, electric blue, toxic lime green and hot pink palette, glossy "
            "liquid motion 3D shapes floating around, confetti in the air, vibrant "
            "maximalist color grade, dynamic composition. Typography is part of "
            "the design: the exact headline text \"ZETA DIVISION — ЧЕМПИОН EMEA\" "
            "set in a heavy rounded uppercase sans-serif font, white letters with "
            "a hot pink outline across the lower third of the frame, and a smaller "
            "monospaced line with the exact text \"BRAWL STARS CHAMPIONSHIP "
            "2026\", crisp legible typography, correct spelling, professional "
            "graphic design. Wide 16:9 composition."
        ),
    },
}

MANIFEST.update(FINAL)


def load_api_key() -> str:
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line.startswith("IMAGE_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("ERROR: IMAGE_API_KEY not found in .env")


def api_post(key: str, entry: dict) -> dict:
    payload = {
        "prompt": entry["prompt"],
        "model": entry.get("model", MODEL),
        "size": entry["size"],
        "n": 1,
    }
    if entry.get("style"):
        payload["style"] = entry["style"]
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        API_URL, data=body, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read())


PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def download(url: str, dest: Path) -> int:
    with urllib.request.urlopen(url, timeout=180) as resp:
        data = resp.read()
    if data.startswith(PNG_MAGIC) or data.startswith(b"\xff\xd8\xff"):
        dest.write_bytes(data)
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        # CDN force-serves WebP; convert via macOS built-in sips
        with tempfile.NamedTemporaryFile(suffix=".webp", delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            subprocess.run(
                ["sips", "-s", "format", "png", tmp_path, "--out", str(dest)],
                check=True, capture_output=True,
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    else:
        raise ValueError("downloaded file is not PNG/JPEG/WebP (bad magic bytes)")
    out = dest.read_bytes()
    if not out.startswith(PNG_MAGIC):
        raise ValueError("final file is not a valid PNG")
    return len(out)


def generate_one(key: str, name: str, entry: dict) -> dict:
    dest_dir = OUT_DIR / entry["subdir"] if entry.get("subdir") else OUT_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{name}.png"
    entry = dict(entry)
    last_err = None
    attempt = 0
    while attempt < MAX_ATTEMPTS:
        attempt += 1
        try:
            result = api_post(key, entry)
            url = result["data"][0]["url"]
            credits = result.get("credits")
            size = download(url, dest)
            return {"status": "ok", "bytes": size, "credits": credits,
                    "attempts": attempt, "style": entry.get("style"),
                    "path": str(dest)}
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            last_err = f"HTTP {e.code}: {detail}"
            # V4.x tiers may reject the style param (HTTP 400): drop it and retry
            # immediately without consuming an attempt (400s are not billed).
            if e.code == 400 and entry.get("style") and "style" in detail.lower():
                entry.pop("style")
                attempt -= 1
                continue
            if e.code in (401, 402, 403, 422):  # auth/billing/bad-request: no retry
                break
        except Exception as e:  # noqa: BLE001 - log and retry
            last_err = f"{type(e).__name__}: {e}"
        if attempt < MAX_ATTEMPTS:
            time.sleep(BACKOFF[min(attempt - 1, len(BACKOFF) - 1)])
    return {"status": "failed", "error": last_err, "attempts": MAX_ATTEMPTS}


def main() -> None:
    ap = argparse.ArgumentParser(description="Recraft batch image generation")
    ap.add_argument("--only", metavar="NAME", help="generate a single plate")
    ap.add_argument("--all", action="store_true", help="generate all plates")
    ap.add_argument("--group", metavar="GROUP", help="generate one manifest group")
    ap.add_argument("--dry-run", action="store_true", help="print prompts only")
    args = ap.parse_args()

    if sum([bool(args.only), args.all, bool(args.group)]) != 1:
        sys.exit("ERROR: specify exactly one of --only / --all / --group")

    if args.only:
        if args.only not in MANIFEST:
            sys.exit(f"ERROR: unknown plate '{args.only}'. Known: {', '.join(MANIFEST)}")
        selected = [args.only]
    elif args.group:
        selected = [n for n, e in MANIFEST.items() if e.get("group") == args.group]
        if not selected:
            sys.exit(f"ERROR: unknown group '{args.group}'")
    else:
        selected = list(MANIFEST)

    if args.dry_run:
        for name in selected:
            e = MANIFEST[name]
            print(f"--- {name} [{e.get('model', MODEL)} {e['size']}] "
                  f"trend={e.get('trend', '-')} style={e.get('style', '-')}\n"
                  f"{e['prompt']}\n")
        return

    key = load_api_key()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = {}
    for name in selected:
        print(f"[gen] {name} ...", flush=True)
        report[name] = generate_one(key, name, MANIFEST[name])
        r = report[name]
        if r["status"] == "ok":
            print(f"  ok: {r['bytes']} bytes, credits={r['credits']}, attempts={r['attempts']}")
        else:
            print(f"  FAILED after {r['attempts']} attempts: {r['error']}")

    log_path = OUT_DIR / "_last_run_report.json"
    log_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    failed = [n for n, r in report.items() if r["status"] != "ok"]
    print(f"\nDone: {len(selected) - len(failed)}/{len(selected)} ok. Report: {log_path}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
