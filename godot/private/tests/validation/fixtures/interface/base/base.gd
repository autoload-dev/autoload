class_name InterfaceBase
extends Node
## What a dependent's validation reads from a unit: every declaration and the coroutine
## flag of each function, none of the bodies.

signal scored(points: int)

enum Mode { CALM, BUSY }

const LIMIT := 4
const Badge = preload("res://interface/base/badge.tscn")
const Icon = preload("res://interface/base/badge.png")
const Beep = preload("res://interface/base/beep.wav")

static var created := 0

var origin := make_origin()
var _points := 0
var points: int:
	get:
		return _points
	set(value):
		_points = value
var doubled := func(value: int) -> int: return value * 2


func make_origin() -> Vector2:
	var origin_value := Vector2.ONE
	origin_value.x += LIMIT
	return origin_value


func settle() -> int:
	await get_tree().process_frame
	scored.emit(_points)
	return _points


func mode_of(busy: bool) -> Mode:
	return Mode.BUSY if busy else Mode.CALM


static func create(name_hint := "base") -> InterfaceBase:
	created += 1
	var base := InterfaceBase.new()
	base.name = name_hint
	return base


class Counter:
	extends RefCounted

	var count := 0

	func next() -> int:
		count += 1
		return count

	class Step:
		func size() -> float:
			return 0.5
