extends RefCounted
## Collect and describe results from the add-on declared by the demo.

const NAMES := ["Temporary", "Application Support", "Application Cache", "Documents", "Downloads"]
const PURPOSES := ["Short-lived disposable files", "Persistent application-managed data", "Recreatable disposable data", "User-generated or non-recreatable documents", "Downloaded files"]
const STATUSES := ["OK", "Unavailable", "Integration unavailable", "Error"]
const SCOPES := ["None", "Application location", "User directory (subject to operating system sandboxing)", "Temporary location (may be shared)"]

static func collect() -> Array[PlatformPathResult]:
	var results: Array[PlatformPathResult] = []
	var resolver := PlatformPaths.new()
	for category in range(5):
		results.append(resolver.resolve(category))
	return results

static func is_valid(result: PlatformPathResult) -> bool:
	if result.status == PlatformPathResult.OK:
		return result.path.is_absolute_path() and not result.path.is_empty() and result.message.is_empty() and result.scope in [PlatformPathResult.APPLICATION, PlatformPathResult.USER_DOMAIN, PlatformPathResult.TEMPORARY]
	return result.status in [PlatformPathResult.UNAVAILABLE, PlatformPathResult.INTEGRATION_UNAVAILABLE, PlatformPathResult.ERROR] and result.path.is_empty() and not result.message.is_empty() and result.scope == PlatformPathResult.NONE

static func describe(result: PlatformPathResult) -> String:
	return "%s — %s\n%s\n%s: %s" % [NAMES[result.category], PURPOSES[result.category], SCOPES[result.scope], STATUSES[result.status], result.path if result.status == PlatformPathResult.OK else result.message]
