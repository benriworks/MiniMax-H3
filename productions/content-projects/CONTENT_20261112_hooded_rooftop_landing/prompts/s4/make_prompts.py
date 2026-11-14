"""Write the scene-4 prompts: three design sheets (sheet-*.txt) and twelve storyboard stills (4-*.txt)."""
from pathlib import Path

HERE = Path(__file__).parent
LOOK = ("Photoreal cinematic film still, 9:16 portrait. Dark blue-green industrial color grade, cold instrument-panel light, "
        "the only vivid color is the sickly pale yellow-green of the gas and the toxic liquid. No text, no logos, no readable "
        "letters anywhere, no watermark.")
NAGI = ("the heroine Nagi from the character sheets: a fictional Japanese woman about 20 years old, short shaggy black hair "
        "with choppy bangs, a faint scar through her left eyebrow, a small streak of dried mud on her LEFT cheek, charcoal-gray "
        "hooded sweatshirt with the hood down, black jogger pants, black running shoes with thin white soles, black fingerless "
        "gloves, a simple gray half-face respirator mask covering only her nose and mouth so her eyes stay fully visible")
DOC = ("the scientist from the design sheet: a fictional Japanese man in his sixties, wild messy white hair, a stained and "
       "scorched white lab coat over a gray sweater, clear safety goggles pushed up or worn, a small half-face respirator")
R_NAGI = "Picture 1 is the heroine's face sheet, Picture 2 her outfit and mask sheet. "
R_DOC = "Picture 1 is the scientist's design sheet. "
R_ROOM = "Picture 2 is the pump room location. "

SHEETS = {
    "sheet-scientist": "Generate an image. Photoreal character reference sheet on a plain light gray studio background, soft even "
        "light: one fictional Japanese man in his sixties shown full-body in three views side by side, front, three-quarter and "
        "back, plus a close-up of his face at the right. Wild messy white hair, deep wrinkles, a gleeful unsettling half-smile, a "
        "stained and slightly scorched white lab coat over a gray sweater and dark trousers, rubber boots, clear safety goggles "
        "on his forehead, a small half-face respirator hanging at his neck, thick rubber gloves. No text, no logos, no watermark.",
    "sheet-nagi-mask": "Picture 1 is the heroine's face sheet, Picture 2 her outfit sheet. Generate a photoreal character "
        "reference sheet of the same woman on a plain light gray studio background: front, three-quarter and back full-body "
        "views plus a close-up of her face. Same face, hair, outfit, hood down, black fingerless gloves, a small streak of dried "
        "mud on her LEFT cheek. New item: a simple gray half-face respirator mask with two small round filters, covering only "
        "her nose and mouth, so her eyes and eyebrows stay fully visible. No text, no logos, no watermark.",
    "sheet-pumproom": "Create a photoreal establishing film still, 9:16 portrait, wide angle from a high catwalk: the vast pump "
        "room of a municipal water purification plant at night. Huge blue-green painted pipes and valves, rows of large pumps, "
        "steel catwalks and railings, a giant cylindrical steel tank in the center with an open hatch, and at its base a "
        "makeshift rig of plastic drums and hoses feeding a glowing yellow-green liquid into a main water pipe. A wall of old "
        "control panels with gauges and a large backlit map of the city's water network glowing green on one side. Thin "
        "yellow-green vapor drifts at floor level. Nobody in the room. " + LOOK,
}

CUTS = {
    "4-1-fence": R_NAGI + f"Early morning, cold blue light. Create a film still outside the chain-link fence of a water "
        f"purification plant, 35mm lens, medium-wide. {NAGI}. She has just landed: a dark gray parachute canopy lies crumpled "
        f"on the grass behind her, and she is unbuckling the harness straps from her chest, the mask already on her face, eyes "
        f"fixed on the plant buildings beyond the fence; a gap is cut in the fence near her. Thin yellow-green vapor drifts out "
        f"of the plant. {LOOK}",
    "4-2-corridor": R_NAGI + f"Create a film still in a long, dim service corridor of a water plant lined with thick "
        f"blue-green pipes, low angle near the floor, 28mm lens. {NAGI} moves along the wall in a crouch toward the camera, "
        f"tense. On the floor in the foreground lies an unconscious fictional soldier in woodland camouflage and a green helmet, "
        f"his gas mask pulled off and lying beside him, face turned away from the camera, his black rifle on the floor next to "
        f"his hand. No blood, no wounds. Thin yellow-green vapor along the floor. {LOOK}",
    "4-3-pumproom": R_DOC + R_ROOM + "Create a film still of the pump room in Picture 2 "
        f"from floor level, wide shot, 24mm lens. Small in the frame at the base of the giant tank stands {DOC}, his back half "
        f"turned to the camera, happily pouring a glowing yellow-green liquid from a plastic drum through a funnel into the main "
        f"water pipe. Vapor curls around his boots. {LOOK}",
    "4-4-doctor": R_DOC + R_ROOM + "Create a tight close-up film still of " + DOC +
        ", goggles on, lit from below by the green glow of a control panel, 85mm lens. Behind the goggles his eyes crinkle "
        "with a gleeful, unhinged smile; his reflection shows a backlit green map of the city's water network. " + LOOK,
    "4-5-eyes": R_NAGI + f"Create an extreme close-up film still of {NAGI}: only her eyes, eyebrows and the top edge of the "
        f"respirator fill the frame, 100mm macro lens. Her eyes are wide with shocked realization, the green glow of the room "
        f"reflected in them, brows drawing together into anger. {LOOK}",
    "4-6-turn": R_DOC + R_ROOM + "Create a film still, medium shot, 50mm lens: " + DOC +
        " has just spun around toward the camera, startled, goggles on, and is reaching with one gloved hand toward a small "
        "black handheld remote device with a single red button lying on the control desk beside him. Gauges and the green "
        "water-network map glow behind him. " + LOOK,
    "4-7-slide": R_NAGI + f"Create a film still, low tracking shot at floor level, 24mm lens, motion blur: {NAGI} slides "
        f"feet-first across the wet concrete floor of the pump room, spray kicking up, her right hand grabbing a black rifle "
        f"lying on the floor. Pipes and the giant tank blur behind her. {LOOK}",
    "4-8-fire": R_NAGI + f"Create a tight close-up film still of {NAGI} kneeling on one knee and aiming a black rifle past the "
        f"camera, cheek against the stock, both eyes open, 85mm lens. A bright orange muzzle flash just off the left edge of the "
        f"frame lights her face and eyes in a hard warm glare against the cold blue-green room. Her eyes are wet but steady. "
        f"Nobody else in the frame. {LOOK}",
    "4-9-slump": R_DOC + R_ROOM + "Create a film still, medium-wide, 35mm lens: " + DOC +
        " slumped sideways against the control desk, sliding down toward the floor, eyes closed, one arm hanging; the small "
        "black remote device has fallen and lies on the floor in the foreground. No blood, no wound visible. The machines keep "
        "running. " + LOOK,
    "4-10-device": R_NAGI + f"Create a close-up film still, over-the-shoulder, 50mm lens: the gloved hands of {NAGI} hold a "
        f"rugged black handheld communication device. Its small screen glows with a plain bright green panel and a blinking "
        f"cursor, with no readable letters (text will be added later). Her masked face is softly out of focus at the edge of the "
        f"frame, looking down at it. {LOOK}",
    "4-11-tears": R_NAGI + f"Create a tight close-up film still of {NAGI}, 85mm lens, face lit by the faint green glow of a "
        f"device in her hands. Tears well up and one runs down from her eye over the edge of the respirator; her jaw is "
        f"clenched, her eyes hard. {LOOK}",
    "4-12-door": R_NAGI + "Create a film still: from inside the dark pump room looking out through a huge open steel sliding "
        f"door into bright cold morning light, strong backlight and haze, 35mm lens. Small in the center of the frame, {NAGI}, "
        f"seen from behind as a dark silhouette, walks out into the light, the mask pulled down around her neck. The edges of "
        f"the frame are dark pipes and machinery. Photoreal cinematic film still, 9:16 portrait, the only warm color is the "
        f"pale gold morning light. No text, no logos, no watermark.",
}

for name, text in {**SHEETS, **CUTS}.items():
    (HERE / f"{name}.txt").write_text(text + "\n", encoding="utf-8")
print(len(SHEETS), "sheets,", len(CUTS), "cuts")
