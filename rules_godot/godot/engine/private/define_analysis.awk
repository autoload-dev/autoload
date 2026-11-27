# Reads a preprocessing's diagnostics and prints the wrapper's definitions the compiler
# does not name unused: the lines between the canary on line 1 and the #include on the
# last. Clang writes `<wrapper>:<line>:<column>: warning: macro is not used`, GCC
# `... warning: macro "NAME" is not used`; Apple's compiler wrapper colours them whatever
# the options say, and GCC on Linux follows each colour with an erase to the end of the
# line. An unused-macro warning in another form, or a canary the compiler does not name,
# fails.
#
# Usage: awk -v wrapper=<wrapper> -f define_analysis.awk < diagnostics > header
{
    gsub(/\033\[[0-9;]*[mK]/, "")
    if (index($0, wrapper ":") == 1 && $0 ~ /: warning: macro .*is not used/) {
        split(substr($0, length(wrapper) + 2), position, ":")
        unused[position[1]] = 1
    } else if (index($0, "-Wunused-macros") > 0) {
        print "Unexpected unused-macro warning: " $0 > "/dev/stderr"
        failed = 1
    }
}
END {
    if (failed) exit 1
    if (!(1 in unused)) {
        print wrapper ": the compiler named no unused definition, not even the canary" > "/dev/stderr"
        exit 1
    }
    while ((getline line < wrapper) > 0) lines[++count] = line
    for (n = 2; n < count; n++) if (!(n in unused)) print lines[n]
}
