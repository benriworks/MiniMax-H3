"""Write the scene-3 H3 prompts (start frame only, 5 s) next to this file."""
from pathlib import Path

HERE = Path(__file__).parent
HEAD = ("How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second "
        "mark of the target video.")
GRADE = "Keep the muted, desaturated cool-gray color grade where only the yellow-green gas has color. No text appears."
NEWS = ("This is TV news footage shown as a horizontal picture in the middle of a vertical frame with blurred fill above and "
        "below; keep that layout fixed. No text, captions or logos appear.")

CUTS = {
    "3-1-street": ("Continuous handheld shot walking backward in front of the young woman in a covered shopping arcade, early "
        "evening. Start exactly at Picture 1. She walks toward the camera at an easy pace, the sports bag on her shoulder, "
        "earphones in, glancing at a shop window and adjusting the strap. Shoppers pass around her, lanterns sway slightly. "
        "An ordinary, peaceful evening; the air is completely clear. " + GRADE,
        "Busy arcade ambience, footsteps, distant shop announcements, a bicycle bell, muffled music leaking from her earphones."),
    "3-2-drain": ("Continuous static shot at ground level. Start exactly at Picture 1. Thick yellow-green gas keeps welling up "
        "out of the storm drain grate and the edges of the manhole cover, curling and spilling slowly across the pavement "
        "toward the camera, hugging the ground. In the background, people's feet walk past unaware, one pair stops. " + GRADE,
        "A low hissing rumble from under the street, faint gurgling, footsteps passing, arcade chatter."),
    "3-3-collapse": ("Continuous static wide shot down the covered shopping arcade. Start exactly at Picture 1. The knee-high "
        "yellow-green gas drifts. The coughing people double over; one man sinks slowly to his knees and topples onto his "
        "side; oranges keep rolling out of the overturned basket; figures in the distance stumble away. No blood. " + GRADE,
        "Coughing and gasping, a basket clattering, a dropped bag, distant screams, a low gas hiss."),
    "3-4-stairs": ("Continuous shot from the bottom of an outdoor steel emergency staircase, low angle, tilting up to follow "
        "her. Start exactly at Picture 1. The young woman with her hood up and a sleeve over her mouth keeps climbing fast, two "
        "steps at a time, the sports bag bouncing, glancing down once; the yellow-green gas rises and swirls around the "
        "lowest steps behind her. She reaches the landing above and turns up the next flight. " + GRADE,
        "Shoes clanging on steel steps, her muffled breathing through the sleeve, the stairs rattling, gas hissing below."),
    "3-5-rising": ("Continuous static shot looking straight down from a rooftop at a gas-filled street. Start exactly at "
        "Picture 1. The figures in the yellow-green gas slowly push themselves up with stiff, jerky, unnatural movements, one "
        "after another, and turn their heads; one begins to shuffle forward. Street lights flicker on. No blood. " + GRADE,
        "Eerie near-silence, a low droning wind, faint groans rising from below, a distant car alarm."),
    "3-6-silhouettes": ("Continuous shot on a long lens in a misty residential street. Start exactly at Picture 1. The man in "
        "the suit runs toward the camera in panic and out of frame past the lens; behind him the gray-skinned figures with "
        "clouded eyes lurch forward out of the yellow-green mist after him, stiff and relentless. No blood, no attack shown. "
        + GRADE, "Panicked running footsteps and breathing, a chorus of low groans, shuffling feet, wind."),
    "3-7-anchor": ("Static medium shot of the news anchor at the studio desk. Start exactly at Picture 1. She reads the news "
        "to camera with a serious, composed face, speaking calmly in Japanese, small natural head movements and blinks, "
        "glancing down at her papers once. The video wall behind her slowly drifts over the hazy city. " + NEWS,
        "A calm female news anchor's voice reading a breaking-news report in Japanese, quiet studio room tone."),
    "3-8-bridge": ("Telephoto news footage of the bridge being sealed. Start exactly at Picture 1. The masked soldiers hold "
        "their line behind the wire; one waves the stopped cars back; red warning lights flash; a second green truck pulls "
        "into place across the lanes. Slight handheld news-camera drift. " + NEWS,
        "Engines idling, car horns, a truck's air brakes, distant helicopter rotor, shouted orders muffled by masks."),
    "3-9-buses": ("News footage outside a quarantine facility. Start exactly at Picture 1. The line of ordinary residents "
        "shuffles forward and climbs onto the white bus, guarded by masked soldiers who gesture them on; the child looks back "
        "over her shoulder; floodlights glare. Slight handheld news-camera drift. " + NEWS,
        "Bus engine idling, footsteps on gravel, murmuring crowd, a child's voice, muffled orders through gas masks."),
    "3-10-phone": ("Continuous tight close-up in a dark storage shed at night. Start exactly at Picture 1. The young woman "
        "stares at the phone screen, its cold glow on her face. Her breathing quickens, her hands start to tremble, her eyes "
        "fill with tears; she bites her lip, then slowly turns the phone face down against her knees and the light on her "
        "face goes out, leaving her in near darkness. " + GRADE,
        "Muffled news audio from the phone, her shaky breathing, a sniff, then the soft thud of the phone laid down and silence."),
    "3-11-searchlight": ("Continuous shot over the hidden young woman's shoulder on a dark rooftop at night. Start exactly at "
        "Picture 1. On the street below, the masked soldiers push the frightened residents along at gunpoint, hands raised. "
        "A white searchlight beam sweeps slowly across the rooftop toward her; she ducks lower behind the rusty water tank "
        "just as the beam slides over the tank and away. " + GRADE,
        "A searchlight's electric hum, muffled shouted orders, frightened voices, boots on asphalt, her held breath."),
    "3-12-plant": ("Continuous shot over the young woman's right shoulder on a rooftop at dawn. Start exactly at Picture 1. "
        "The thin column of yellow-green smoke keeps rising from the distant water purification plant. The camera pushes in "
        "slowly past her shoulder toward the plant; she lifts her chin, her hands close into fists, and her gaze sets. " + GRADE,
        "Cold dawn wind, distant crows, a faraway low industrial hum, one slow determined breath."),
}

for name, (desc, sound) in CUTS.items():
    (HERE / f"{name}.txt").write_text(
        f"{HEAD}\n\nintegrated_multimodal_description: [Shot 1] {desc}\n\noverall_soundscape: {sound}\n\nnon_diegetic_music: N/A\n",
        encoding="utf-8")
print(len(CUTS), "prompts")
