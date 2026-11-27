package godot

import (
	"reflect"
	"testing"
)

func TestScanScript(t *testing.T) {
	source := `class_name Courier
extends "res://main/shared/body.gd"
## Docs mention Ignored and preload("res://not/a/reference.gd").

const Palette = preload("res://main/shared/palette/palette.gd")
const Sound := preload("../sound/sound.tscn")
var level: LevelDefinition
var helper = load('uid://b2wq1ptv0ylpy')
var text := "res://tests/data.json"
var name := &"StringName"
var raw := r"res://raw/path.gd"
var long := """multi
line "Inner" preload("res://not/either.gd")"""
enum Mode { Walk, Fly }
class Inner:
	var x: Mode

func _ready() -> void:
	$Label.text = %Unique.name
	var route := RouteModel.new()
	var other = self.Ignored
	@warning_ignore("unused") var c: Courier
	route.load("res://main/route.tres")
`
	got := scan("res://main/components/courier/courier.gd", []byte(source))
	want := scanned{
		classes: []string{"Courier"},
		extends: "res://main/shared/body.gd",
		refs: []reference{
			{kindRes, "res://main/components/sound/sound.tscn"},
			{kindRes, "res://main/route.tres"},
			{kindRes, "res://main/shared/body.gd"},
			{kindRes, "res://main/shared/palette/palette.gd"},
			{kindUID, "uid://b2wq1ptv0ylpy"},
			{kindClass, "LevelDefinition"},
			{kindClass, "RouteModel"},
		},
		literals: []string{"res://raw/path.gd", "res://tests/data.json"},
	}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("scan() =\n%+v\nwant\n%+v", got, want)
	}
}

func TestScanScriptExtendsClass(t *testing.T) {
	got := scan("res://tests/RouteTest.gd", []byte("extends GdUnitTestSuite\n\nfunc test() -> void:\n\tassert_int(1)\n"))
	if got.extends != "GdUnitTestSuite" {
		t.Errorf("extends = %q, want GdUnitTestSuite", got.extends)
	}
	want := []reference{{kindClass, "GdUnitTestSuite"}}
	if !reflect.DeepEqual(got.refs, want) {
		t.Errorf("refs = %v, want %v", got.refs, want)
	}
}

func TestScanTextScene(t *testing.T) {
	source := `[gd_scene load_steps=3 format=3 uid="uid://c4f1abq8l2x0m"]

[ext_resource type="Script" uid="uid://b2wq1ptv0ylpy" path="res://main/game.gd" id="1_a"]
[ext_resource type="PackedScene" path="res://main/run/run.tscn" id="2_b"]

[node name="Game" type="Node2D"]
script = ExtResource("1_a")
text = "[ext_resource path=\"res://not/a/header.gd\"]"
next_scene = "res://main/next.tscn"
`
	got := scan("res://main/game.tscn", []byte(source))
	want := scanned{
		uid: "uid://c4f1abq8l2x0m",
		refs: []reference{
			{kindRes, "res://main/game.gd"},
			{kindRes, "res://main/run/run.tscn"},
			{kindUID, "uid://b2wq1ptv0ylpy"},
		},
		literals: []string{"res://main/next.tscn"},
	}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("scan() =\n%+v\nwant\n%+v", got, want)
	}
}

func TestScanTextResource(t *testing.T) {
	source := "[gd_resource type=\"Theme\" load_steps=2 format=3 uid=\"uid://dq1\"]\n\n" +
		"[ext_resource type=\"FontFile\" uid=\"uid://font1\" path=\"res://main/shared/ui/Font.ttf\" id=\"1\"]\n"
	got := scan("res://main/shared/ui/theme.tres", []byte(source))
	if got.uid != "uid://dq1" {
		t.Errorf("uid = %q, want uid://dq1", got.uid)
	}
	want := []reference{{kindRes, "res://main/shared/ui/Font.ttf"}, {kindUID, "uid://font1"}}
	if !reflect.DeepEqual(got.refs, want) {
		t.Errorf("refs = %v, want %v", got.refs, want)
	}
}

func TestScanShader(t *testing.T) {
	source := "shader_type canvas_item;\n#include \"res://shaders/common.gdshaderinc\"\n  #include \"noise.gdshaderinc\"\n"
	got := scan("res://effects/glow.gdshader", []byte(source))
	want := []reference{
		{kindRes, "res://effects/noise.gdshaderinc"},
		{kindRes, "res://shaders/common.gdshaderinc"},
	}
	if !reflect.DeepEqual(got.refs, want) {
		t.Errorf("refs = %v, want %v", got.refs, want)
	}
}

func TestScanSidecars(t *testing.T) {
	if got := scan("res://main/game.gd.uid", []byte("uid://b2wq1ptv0ylpy\n")); got.uid != "uid://b2wq1ptv0ylpy" {
		t.Errorf(".uid file: uid = %q", got.uid)
	}
	importFile := "[remap]\n\nimporter=\"texture\"\ntype=\"CompressedTexture2D\"\nuid=\"uid://bsky\"\npath=\"res://.godot/imported/sky.png-x.ctex\"\n"
	if got := scan("res://levels/sky.png.import", []byte(importFile)); got.uid != "uid://bsky" {
		t.Errorf(".import file: uid = %q", got.uid)
	}
}

func TestScanGLTF(t *testing.T) {
	source := `{"buffers": [{"uri": "ship.bin"}, {"uri": "data:application/octet-stream;base64,AA=="}],
	"images": [{"uri": "textures/hull%20paint.png"}, {"bufferView": 3}]}`
	got := scan("res://models/ship.gltf", []byte(source))
	want := []string{"res://models/ship.bin", "res://models/textures/hull paint.png"}
	if !reflect.DeepEqual(got.members, want) {
		t.Errorf("members = %v, want %v", got.members, want)
	}
}

func TestResourcePath(t *testing.T) {
	for _, test := range []struct {
		value, source, want string
		ok                  bool
	}{
		{"res://a/b.gd", "res://x/y.gd", "res://a/b.gd", true},
		{"b.gd", "res://x/y.gd", "res://x/b.gd", true},
		{"../b.gd", "res://x/y.gd", "res://b.gd", true},
		{"../../b.gd", "res://x/y.gd", "", false},
		{"user://save.cfg", "res://x/y.gd", "", false},
		{"res://", "res://x/y.gd", "", false},
	} {
		got, ok := resourcePath(test.value, test.source)
		if got != test.want || ok != test.ok {
			t.Errorf("resourcePath(%q, %q) = %q, %v; want %q, %v", test.value, test.source, got, ok, test.want, test.ok)
		}
	}
}

func TestNativeClasses(t *testing.T) {
	source := `void initialize(ModuleInitializationLevel level) {
    godot::ClassDB::register_class<NativeCounter>();
    ClassDB::register_abstract_class< Shape >();
    GDREGISTER_RUNTIME_CLASS(Field);
    // ClassDB::register_class<Commented>(); is still a registration a scan cannot tell apart.
}
`
	got := nativeClasses([]byte(source))
	want := []string{"Commented", "Field", "NativeCounter", "Shape"}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("nativeClasses() = %v, want %v", got, want)
	}
}
