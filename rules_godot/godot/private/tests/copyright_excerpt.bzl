"""A real excerpt of Godot 4.7.2's COPYRIGHT.txt, its paragraphs unchanged and in order."""

visibility("//godot/...")

# The header, Godot's own Files paragraph, two paragraphs of one library (Bullet), one
# without a Comment, a choice of licenses, a thirdparty/ library, and the License paragraphs
# they name.
COPYRIGHT_EXCERPT = """\
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Comment:
 Exhaustive licensing information for files in the Godot Engine repository
 =========================================================================
 .
 This file aims at documenting the copyright and license for every source
 file in the Godot Engine repository, and especially outline the files
 whose license differs from the MIT/Expat license used by Godot Engine.
 .
 It is written as a machine-readable format following the debian/copyright
 specification. Globbing patterns (e.g. "Files: *") mean that they affect
 all corresponding files (also recursively in subfolders), apart from those
 with a more explicit copyright statement.
 .
 Licenses are given with their debian/copyright short name (or SPDX identifier
 if no standard short name exists) and are all included in plain text at the
 end of this file (in alphabetical order).
 .
 Disclaimer for thirdparty libraries:
 ------------------------------------
 .
 Licensing details for thirdparty libraries in the 'thirdparty/' directory
 are given in summarized form, i.e. with only the "main" license described
 in the library's license statement. Different licenses of single files or
 code snippets in thirdparty libraries are not documented here.
 For example:
   Files: thirdparty/zlib/*
   Copyright: 1995-2017, Jean-loup Gailly and Mark Adler
   License: Zlib
 The exact copyright for each file in that library *may* differ, and some
 files or code snippets might be distributed under other compatible licenses
 (e.g. a public domain dedication), but as far as Godot Engine is concerned
 the library is considered as a whole under the Zlib license.
 .
 Note: When linking dynamically against thirdparty libraries instead of
 building them into the Godot binary, you may remove the corresponding
 license details from this file.
Upstream-Name: Godot Engine
Upstream-Contact: Rémi Verschelde <contact@godotengine.org>
Source: https://github.com/godotengine/godot

Files: *
Comment: Godot Engine
Copyright: 2014-present, Godot Engine contributors
 2007-2014, Juan Linietsky, Ariel Manzur
License: Expat

Files: core/math/convex_hull.cpp
 core/math/convex_hull.h
Comment: Bullet Continuous Collision Detection and Physics Library
Copyright: 2011, Ole Kniemeyer, MAXON, www.maxon.net
 2014-present, Godot Engine contributors
 2007-2014, Juan Linietsky, Ariel Manzur
License: Expat and Zlib

Files: modules/godot_physics_3d/gjk_epa.cpp
 modules/godot_physics_3d/joints/godot_generic_6dof_joint_3d.cpp
 modules/godot_physics_3d/joints/godot_generic_6dof_joint_3d.h
 modules/godot_physics_3d/joints/godot_hinge_joint_3d.cpp
 modules/godot_physics_3d/joints/godot_hinge_joint_3d.h
 modules/godot_physics_3d/joints/godot_jacobian_entry_3d.h
 modules/godot_physics_3d/joints/godot_pin_joint_3d.cpp
 modules/godot_physics_3d/joints/godot_pin_joint_3d.h
 modules/godot_physics_3d/joints/godot_slider_joint_3d.cpp
 modules/godot_physics_3d/joints/godot_slider_joint_3d.h
 modules/godot_physics_3d/godot_soft_body_3d.cpp
 modules/godot_physics_3d/godot_soft_body_3d.h
 modules/godot_physics_3d/godot_shape_3d.cpp
 modules/godot_physics_3d/godot_shape_3d.h
Comment: Bullet Continuous Collision Detection and Physics Library
Copyright: 2003-2008, Erwin Coumans
 2014-present, Godot Engine contributors
 2007-2014, Juan Linietsky, Ariel Manzur
License: Expat and Zlib

Files: servers/audio/effects/audio_effect_pitch_shift.cpp
Copyright: 2014-present Godot Engine contributors
 2007-2014 Juan Linietsky, Ariel Manzur
 1999-2015 Stephan M. Bernsee <s.bernsee [AT] zynaptiq [DOT] com>
License: Expat and WOL

Files: thirdparty/misc/smolv.cpp
 thirdparty/misc/smolv.h
Comment: SMOL-V
Copyright: 2016-2024, Aras Pranckevicius
License: Unlicense or Expat

Files: thirdparty/zlib/*
Comment: zlib
Copyright: 1995-2026, Jean-loup Gailly and Mark Adler
License: Zlib

License: Expat
 Permission is hereby granted, free of charge, to any person obtaining
 a copy of this software and associated documentation files (the
 "Software"), to deal in the Software without restriction, including
 without limitation the rights to use, copy, modify, merge, publish,
 distribute, sublicense, and/or sell copies of the Software, and to
 permit persons to whom the Software is furnished to do so, subject to
 the following conditions:
 .
 The above copyright notice and this permission notice shall be
 included in all copies or substantial portions of the Software.
 .
 THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
 EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
 MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
 IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
 CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
 TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
 SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

License: Unlicense
 This is free and unencumbered software released into the public domain.
 .
 Anyone is free to copy, modify, publish, use, compile, sell, or
 distribute this software, either in source code form or as a compiled
 binary, for any purpose, commercial or non-commercial, and by any
 means.
 .
 In jurisdictions that recognize copyright laws, the author or authors
 of this software dedicate any and all copyright interest in the
 software to the public domain. We make this dedication for the benefit
 of the public at large and to the detriment of our heirs and
 successors. We intend this dedication to be an overt act of
 relinquishment in perpetuity of all present and future rights to this
 software under copyright law.
 .
 THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
 EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
 MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
 IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
 OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
 ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
 OTHER DEALINGS IN THE SOFTWARE.
 .
 For more information, please refer to <https://unlicense.org/>

License: WOL
                          The Wide Open License (WOL)
 .
 Permission to use, copy, modify, distribute and sell this software and its
 documentation for any purpose is hereby granted without fee, provided that
 the above copyright notice and this license appear in all source copies.
 THIS SOFTWARE IS PROVIDED "AS IS" WITHOUT EXPRESS OR IMPLIED WARRANTY OF
 ANY KIND. See https://dspguru.com/wide-open-license/ for more information.

License: Zlib
 This software is provided 'as-is', without any express or implied
 warranty.  In no event will the authors be held liable for any damages
 arising from the use of this software.
 .
 Permission is granted to anyone to use this software for any purpose,
 including commercial applications, and to alter it and redistribute it
 freely, subject to the following restrictions:
 .
 1. The origin of this software must not be misrepresented; you must not
    claim that you wrote the original software. If you use this software
    in a product, an acknowledgment in the product documentation would be
    appreciated but is not required.
 2. Altered source versions must be plainly marked as such, and must not be
    misrepresented as being the original software.
 3. This notice may not be removed or altered from any source distribution.

"""
