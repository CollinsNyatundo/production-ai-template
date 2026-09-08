import json


def extract_file_content(file_name: str, raw_bytes: bytes) -> str:
    ext = file_name.split(".")[-1].lower() if "." in file_name else ""

    if ext in ["txt", "md"]:
        return raw_bytes.decode("utf-8")
    elif ext == "json":
        try:
            data = json.loads(raw_bytes.decode("utf-8"))
            return json.dumps(data, indent=2)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid JSON upload.") from exc
    raise ValueError("Unsupported file type. Allowed: .txt, .md, .json")
