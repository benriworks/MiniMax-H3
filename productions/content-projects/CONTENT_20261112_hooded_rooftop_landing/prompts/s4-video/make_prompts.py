"""Write the scene-4 H3 prompts (start frame only, 5 s) next to this file."""
from pathlib import Path

HERE = Path(__file__).parent
HEAD = ("How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second "
        "mark of the target video.")
GRADE = ("Keep the dark blue-green industrial color grade; the only vivid color is the yellow-green gas and liquid. "
         "No text appears. No blood, no wounds.")

CUTS = {
    "4-1-fence": ("Continuous shot outside the chain-link fence of the water plant at dawn. Start exactly at Picture 1. The "
        "young woman in the gray half-face respirator unclips the last harness buckle, lets the harness drop onto the "
        "crumpled parachute, pulls her gloves tight, then ducks through the cut gap in the fence and moves toward the plant "
        "buildings in a low run. The camera pans slightly to follow. " + GRADE,
        "Cold dawn wind, nylon rustling, a plastic buckle clicking, wire fence scraping, her breathing through the respirator."),
    "4-2-corridor": ("Continuous low shot in a pipe-lined service corridor. Start exactly at Picture 1. The young woman in the "
        "respirator creeps forward along the wall in a crouch, glancing down at the unconscious soldier lying on the floor in "
        "the foreground; she steps carefully past him. Steam hisses from a pipe; the overhead light flickers. The soldier does "
        "not move. " + GRADE,
        "Humming pumps, dripping water, a hiss of steam, her careful footsteps, muffled respirator breathing."),
    "4-3-pumproom": ("Continuous high wide shot of the vast pump room. Start exactly at Picture 1. The old scientist in the white "
        "coat at the base of the giant tank keeps pouring the glowing yellow-green liquid from a drum into the main pipe, "
        "rocking slightly as if humming to himself; the liquid glows brighter as it flows down the transparent pipe section; "
        "vapor curls along the floor. The camera slowly pushes in. " + GRADE,
        "Deep rumbling pumps, gurgling liquid, an old man humming a cheerful tune, echoes in a huge room."),
    "4-4-doctor": ("Continuous tight close-up of the old scientist behind his goggles, lit from below by the green control "
        "panel. Start exactly at Picture 1. He watches the panel with delight; his grin widens and he lets out a soft, "
        "giddy chuckle, eyes crinkling, then taps a key with one gloved finger. The reflections in his goggles shift. " + GRADE,
        "A soft giddy chuckle, panel beeps, the hum of machinery."),
    "4-5-eyes": ("Continuous extreme close-up of the young woman's eyes above the respirator. Start exactly at Picture 1. Her "
        "wide shocked eyes flick from side to side, taking in the scene; then her brows slowly draw down and her stare hardens "
        "into anger. The green reflections in her eyes flicker. The camera does not move. " + GRADE,
        "Her heartbeat thudding, her breathing through the respirator getting faster, distant machine hum."),
    "4-6-turn": ("Continuous medium shot of the old scientist at the control desk. Start exactly at Picture 1. Startled, he "
        "turns his head toward the camera, his face twisting from surprise into a sly smile, and his gloved hand slides "
        "across the desk and closes around the small black remote device with the red button, lifting it. " + GRADE,
        "A startled gasp, a chair creaking, the device scraping on the metal desk, panel beeps."),
    "4-7-slide": ("Continuous low tracking shot at floor level. Start exactly at Picture 1. The young woman slides across the wet "
        "concrete floor, spray flying, grabs the black rifle off the floor in one motion, and rolls up onto one knee, bringing "
        "it up toward her shoulder. Fast, urgent movement. " + GRADE,
        "A wet slide and splash, the rifle scraping on concrete, a sharp exhale, pumps rumbling."),
    "4-8-fire": ("Continuous tight close-up of the young woman kneeling and aiming the rifle past the camera, cheek on the "
        "stock. Start exactly at Picture 1. Her eyes are wet and her hands tremble slightly; she steadies, and a single bright "
        "muzzle flash at the left edge of the frame lights her face orange for an instant; she flinches with the recoil and "
        "keeps staring ahead, frozen. The target is never shown. " + GRADE,
        "One loud gunshot echoing in the huge room, a shell casing tinkling on concrete, then ringing silence and her breath."),
    "4-9-slump": ("Continuous high wide shot of the pump room. Start exactly at Picture 1. The old scientist slowly slides down "
        "from the control desk and comes to rest on the floor, still; the small remote device lies apart from him. The "
        "machines keep running, the liquid keeps glowing, vapor drifts. Quiet and still. " + GRADE,
        "Only the indifferent hum and rumble of machinery, a slow drip, a faint electrical buzz."),
    "4-10-device": ("Continuous close-up over the young woman's shoulder. Start exactly at Picture 1. Her gloved hands hold the "
        "rugged black communication device; the small bright green screen flickers and refreshes as a new message arrives, "
        "with a short vibration. She tilts it toward herself. The screen shows only a plain glowing green panel with no "
        "readable letters. " + GRADE,
        "A short electronic chime and buzz from the device, her breathing, machinery hum."),
    "4-11-tears": ("Continuous tight close-up of the young woman in the respirator, her face lit by the faint green glow of the "
        "device. Start exactly at Picture 1. A tear runs down from her eye over the edge of the respirator; she clenches her "
        "jaw, blinks hard, and slips the device into the pocket of her hoodie without looking away from the distance. " + GRADE,
        "A shaky breath through the respirator, a quiet sniff, fabric rustling, machine hum fading."),
    "4-12-door": ("Continuous shot from inside the dark pump room toward the huge open door full of bright morning light. Start "
        "exactly at Picture 1. The young woman turns around and walks slowly out through the doorway into the light, her "
        "dark silhouette growing smaller, haze glowing around her. At the end the heavy steel door begins to slide shut from "
        "the side, darkening the frame. No text appears.",
        "Her footsteps echoing, morning birdsong from outside, then the heavy rumble of a steel door rolling shut and a deep "
        "metallic boom."),
}

for name, (desc, sound) in CUTS.items():
    (HERE / f"{name}.txt").write_text(
        f"{HEAD}\n\nintegrated_multimodal_description: [Shot 1] {desc}\n\noverall_soundscape: {sound}\n\nnon_diegetic_music: N/A\n",
        encoding="utf-8")
print(len(CUTS), "prompts")
