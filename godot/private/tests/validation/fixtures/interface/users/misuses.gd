extends InterfaceBase
## Misuses the base's declarations; each line fails as it does against the base's source.


func misuse() -> void:
	var settled: int = settle() + 1
	var at: String = origin
	var width: String = Icon.get_width()
	var beep: Texture2D = Beep
	var step: String = InterfaceBase.Counter.Step.new().size()
	print(settled, at, width, beep, step)
