extends InterfaceBase
## Uses every declaration of the base as the base declares it.


func _ready() -> void:
	var at: Vector2 = origin
	var settled: int = await settle()
	var mode: Mode = mode_of(true)
	var counter := InterfaceBase.Counter.new()
	var next: int = counter.next()
	var step: float = InterfaceBase.Counter.Step.new().size()
	var badge: Node = Badge.instantiate()
	var width: int = Icon.get_width()
	var beep: AudioStreamWAV = Beep
	var created_base: InterfaceBase = InterfaceBase.create()
	var twice: int = doubled.call(LIMIT)
	scored.emit(points)
	print(at, settled, mode, next, step, badge, width, beep, created_base, twice)
