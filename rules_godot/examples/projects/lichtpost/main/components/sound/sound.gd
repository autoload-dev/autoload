extends Node
## Small original synthesized cues. No audio service or generator at build time.

var muted := false
var cues := {}
var voices: Array[AudioStreamPlayer] = []
var next_voice := 0


func _ready() -> void:
	for player in get_children():
		voices.append(player)
	cues = {
		"jump": _tone(420, 760, 0.12),
		"land": _tone(160, 80, 0.09),
		"light": _tone(920, 1380, 0.09),
		"group": _tone(1040, 2080, 0.25),
		"lost": _tone(300, 65, 0.38),
		"delivered": _tone(660, 1320, 0.6),
	}


func set_muted(value: bool) -> void:
	muted = value
	if muted:
		for voice in voices:
			voice.stop()


func play(cue: String) -> void:
	if muted or not cues.has(cue) or voices.is_empty():
		return
	var voice := voices[next_voice]
	next_voice = (next_voice + 1) % voices.size()
	voice.stream = cues[cue]
	voice.play()


func _tone(start: float, finish: float, duration: float) -> AudioStreamWAV:
	var sample_rate := 22050
	var count := int(duration * sample_rate)
	var samples := PackedByteArray()
	samples.resize(count * 2)
	var phase := 0.0
	for index in range(count):
		var progress := float(index) / count
		phase += TAU * lerpf(start, finish, progress) / sample_rate
		var envelope := minf(progress * 25, 1.0) * pow(1.0 - progress, 2)
		var value := int((sin(phase) + 0.18 * sin(phase * 2)) * envelope * 16000)
		samples.encode_s16(index * 2, value)
	var stream := AudioStreamWAV.new()
	stream.format = AudioStreamWAV.FORMAT_16_BITS
	stream.mix_rate = sample_rate
	stream.data = samples
	return stream
