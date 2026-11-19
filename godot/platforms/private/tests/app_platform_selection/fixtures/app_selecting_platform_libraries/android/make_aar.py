"""Assemble an AAR from a manifest and a class jar, as Gradle publishes one."""

import sys
import zipfile

manifest, classes, output = sys.argv[1:]
with zipfile.ZipFile(output, "w") as aar:
    for name, source in (("AndroidManifest.xml", manifest), ("classes.jar", classes)):
        info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
        with open(source, "rb") as data:
            aar.writestr(info, data.read())
    aar.writestr(zipfile.ZipInfo("R.txt", date_time=(1980, 1, 1, 0, 0, 0)), "")
