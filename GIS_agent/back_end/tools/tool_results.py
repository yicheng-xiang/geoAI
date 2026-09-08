def tool_success(message, code="OK", data=None):
    result = {"ok": True, "code": code, "message": message}
    if data is not None:
        result["data"] = data
    return result


def tool_error(code, message, data=None):
    result = {"ok": False, "code": code, "message": message}
    if data is not None:
        result["data"] = data
    return result


def normalize_tool_result(result):
    """Keep third-party/legacy tools compatible while enforcing one result shape."""
    if isinstance(result, dict) and {"ok", "code", "message"}.issubset(result):
        return result

    message = str(result)
    failure_prefixes = ("error:", "failed:", "warning:", "notice:", "skipped:")
    if message.strip().lower().startswith(failure_prefixes):
        return tool_error("LEGACY_TOOL_ERROR", message)
    return tool_success(message)
