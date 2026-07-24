import json


def extract_file_content(file_name: str, raw_bytes: bytes) -> str:
    ext = file_name.split(".")[-1].lower() if "." in file_name else ""

    if ext in ["txt", "md", "py", "js", "ts", "html", "css", "yaml", "yml", "sh"]:
        return raw_bytes.decode("utf-8", errors="ignore")
    elif ext == "json":
        try:
            data = json.loads(raw_bytes.decode("utf-8", errors="ignore"))
            return json.dumps(data, indent=2)
        except Exception:
            return raw_bytes.decode("utf-8", errors="ignore")
    elif ext == "csv":
        return raw_bytes.decode("utf-8", errors="ignore")
    else:
        return raw_bytes.decode("utf-8", errors="ignore")
