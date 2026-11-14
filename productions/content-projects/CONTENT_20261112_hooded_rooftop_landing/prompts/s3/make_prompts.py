"""Write the scene-3 storyboard prompts (one .txt per cut) next to this file."""
from pathlib import Path

HERE = Path(__file__).parent
LOOK = ("Photoreal cinematic film still, 9:16 portrait. Muted, heavily desaturated cool-gray color grade; the only vivid color "
        "is the sickly pale yellow-green of the gas. No text, no logos, no signs with readable letters, no watermark.")
NEWS = ("Photoreal still from a Japanese TV news broadcast, 9:16 portrait, slightly flat broadcast video look, static camera. "
        "No on-screen text, no captions, no channel logo, no graphics; keep the lower quarter of the frame calm and uncluttered "
        "for captions added later. No readable letters anywhere.")
NAGI = ("the heroine Nagi from the character sheets: a fictional Japanese woman about 20 years old, short shaggy black hair with "
        "choppy bangs, a faint scar through her left eyebrow, charcoal-gray hooded sweatshirt, black jogger pants, black running "
        "shoes with thin white soles")
REFS_NAGI = "Picture 1 is the heroine's face sheet, Picture 2 her outfit sheet. "
GAS = "a low, heavy layer of pale yellow-green toxic gas, denser than air, creeping along the ground"
INFECTED = ("ordinary townspeople who have changed: ashen gray skin, clouded milky eyes, stiff jerky movements, ordinary clothes; "
            "no blood, no wounds, no gore")

CUTS = {
    "3-1-street": REFS_NAGI + f"Three days earlier, early evening. Create a film still in a covered Japanese shopping arcade (shotengai) "
        f"with small shops, hanging paper lanterns and shoppers. Handheld camera walking backward in front of her, 35mm lens, medium "
        f"shot. {NAGI}, with a clean face, no mud, hood down, walking toward the camera after gymnastics practice, a navy sports bag "
        f"slung over one shoulder, earphones in, relaxed and a little tired. Ordinary evening crowd around her, warm shop lights. {LOOK}",
    "3-2-drain": "Create a film still: extreme low angle at ground level on the paved floor of a covered Japanese shopping arcade "
        f"in the early evening, 24mm lens. In the foreground a metal storm-drain grate and a round manhole cover; from the gaps "
        f"{GAS} is seeping out in slow, thick curls and spreading across the pavement. Out of focus in the background, the feet and "
        f"shopping bags of passers-by who have not noticed yet. {LOOK}",
    "3-3-collapse": "Create a film still: wide shot down a covered Japanese shopping arcade in the early evening, 28mm lens, eye "
        f"level. {GAS}, knee-high and filling the whole street. Shoppers are coughing into their hands, doubling over, some have "
        f"sunk to their knees or lie still on the ground; a shopping basket lies on its side with oranges rolling out. Panic, "
        f"people stumbling away in the distance. No blood, no gore. {LOOK}",
    "3-4-stairs": REFS_NAGI + f"Create a film still in a narrow back alley behind the shopping arcade, dusk: a steep outdoor steel "
        f"emergency staircase zigzags up the side of a four-story building. Low angle from the bottom of the stairs, 24mm lens. "
        f"{NAGI}, with a clean face, hood pulled UP over her head, the navy sports bag on her shoulder, is running up the stairs two "
        f"steps at a time, one sleeve pressed over her nose and mouth, looking back down in fear. Below her, {GAS} fills the alley "
        f"floor and laps at the lowest steps. {LOOK}",
    "3-5-rising": "Create a film still: high angle looking straight down from a rooftop edge onto a narrow Japanese town street "
        f"at dusk, 50mm lens. The whole street floor is drowned in {GAS}, like a shallow murky sea. In the gas, several people "
        f"who had collapsed are slowly getting back up in unnatural, stiff, jerky poses, small figures seen from above: {INFECTED}. "
        f"Street lights are coming on. Eerie and still. {LOOK}",
    "3-6-silhouettes": "Create a film still: a residential street at dusk thick with pale yellow-green mist. Long lens, 85mm, "
        f"compressed perspective. In the foreground a lone man in a business suit runs toward the camera in panic, blurred. Behind "
        f"him, emerging from the mist, a crowd of dark silhouettes of {INFECTED}, lurching after him with arms hanging; only "
        f"their clouded pale eyes catch the light. Horror mood, no blood. {LOOK}",
    "3-7-anchor": "Create an image: a fictional Japanese female news anchor in her forties, short neat dark hair, navy suit, sitting "
        "at a modern TV studio news desk, facing the camera, serious and composed, medium shot from the chest up. Behind her a "
        "large video wall shows an aerial view of a low-rise city at dusk covered in a pale yellow-green haze. Cool studio "
        "lighting. " + NEWS,
    "3-8-bridge": "Create an image: telephoto news footage of a river bridge at the city limits at dusk being sealed off. Fictional "
        "soldiers in black full-face gas masks, green helmets and woodland camouflage with rifles stand in a line behind "
        "concertina wire and steel barricades; two dark green military trucks block the lanes; a long line of stopped civilian "
        "cars with headlights on waits on the bridge. Flashing red warning lights. No insignia, no flags, no unit patches. " + NEWS,
    "3-9-buses": "Create an image: news footage, slightly high angle, outside a quarantine facility at dusk: rows of white "
        "emergency tents behind a tall fence, floodlights. Local residents of all ages, ordinary people who look healthy, carrying "
        "bags, are being lined up and herded onto plain white buses by fictional soldiers in black full-face gas masks and "
        "camouflage with rifles. A child holds her mother's hand. No insignia, no flags, no unit patches. " + NEWS,
    "3-10-phone": REFS_NAGI + f"Night. Create a film still inside a cramped, dark rooftop storage shed full of old boxes and a "
        f"folded tarp. Tight close-up, 85mm lens. {NAGI}, hood down, a faint smudge of dirt on her LEFT cheek, sits hugging her "
        f"knees and staring at a smartphone held in both hands; the cold blue-white glow of the screen is the only light on her "
        f"face. Her eyes are wet and wide, her lips pressed together, her hands trembling slightly. The screen faces away from the "
        f"camera. {LOOK}",
    "3-11-searchlight": REFS_NAGI + "Picture 3 is a soldier design sheet. Night. Create a film still on a dark rooftop: "
        f"{NAGI}, hood UP, crouches hidden behind a rusty rooftop water tank in the right foreground, seen from behind and the "
        f"side, peering over the edge. Below, on the street two floors down, harsh white searchlight beams cut through drifting "
        f"pale yellow-green mist; small figures of soldiers in gas masks exactly like Picture 3 are pushing a group of frightened "
        f"healthy residents in ordinary clothes along at gunpoint, hands raised. A searchlight beam sweeps across the rooftop "
        f"just past her. {LOOK}",
    "3-12-plant": REFS_NAGI + f"Early morning, cold blue light with the first pale sunrise. Create a film still on a rooftop: "
        f"{NAGI}, hood down, a smudge of dried mud on her LEFT cheek, standing at the rooftop edge seen from behind over her right "
        f"shoulder, 50mm lens. Far away across the hazy low-rise town stands a large water purification plant with round settling "
        f"tanks and a tall concrete building; a thin column of pale yellow-green smoke rises from it into the morning sky. Her "
        f"gaze is fixed on it. {LOOK}",
}

for name, text in CUTS.items():
    (HERE / f"{name}.txt").write_text(text + "\n", encoding="utf-8")
print(len(CUTS), "prompts")
