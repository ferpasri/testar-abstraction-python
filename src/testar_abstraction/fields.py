"""Select captured properties and normalize comparison values."""

import re
from urllib.parse import urlsplit, urlunsplit, unquote, parse_qsl, quote_plus, quote
from .common import AbstractionError, canonical

WHITESPACE = "\u0009\u000a\u000b\u000c\u000d\u0020\u00a0\u1680" + "".join(map(chr, range(0x2000, 0x200b))) + "\u2028\u2029\u202f\u205f\u3000\ufeff"
SPACE_PATTERN = re.compile("[" + WHITESPACE + "]+")
MISSING = object()


def select(properties, keys):
    for key in keys:
        if key in properties:
            return properties[key]
    return MISSING


def normalize_url(value, transform):
    try:
        address = urlsplit(value.strip(WHITESPACE))
        if not address.scheme or (address.scheme in ("http", "https", "ftp") and not address.hostname):
            raise ValueError("Expected absolute URL")
        path = []
        for segment in address.path.split("/"):
            pieces = segment.split(";")
            kept = [pieces[0]]
            for parameter in pieces[1:]:
                encoded = parameter.split("=", 1)[0]
                try:
                    if re.search(r"%(?![0-9a-fA-F]{2})", encoded):
                        raise ValueError("Malformed escape")
                    name = unquote(encoded, errors="strict")
                except (ValueError, UnicodeError):
                    name = None
                if name not in transform.get("remove_path_parameters", []):
                    kept.append(parameter)
            path.append(";".join(kept))
        pathname = "/".join(path)
        authority = address.netloc
        if address.hostname:
            host = address.hostname.encode("idna").decode("ascii").lower()
            if ":" in host:
                host = "[" + host + "]"
            port = address.port
            if port and port != {"http": 80, "https": 443, "ftp": 21}.get(address.scheme):
                host += ":" + str(port)
            credentials = authority.rsplit("@", 1)[0] + "@" if "@" in authority else ""
            authority = credentials + host
        if authority and not pathname:
            pathname = "/"
        query = address.query
        if transform.get("remove_query"):
            def encode(component):
                return quote_plus(component, safe="*").replace("~", "%7E")
            query = "&".join(encode(k) + "=" + encode(v)
                             for k, v in parse_qsl(query, keep_blank_values=True)
                             if k not in transform["remove_query"])
        fragment = "" if transform.get("remove_fragment") else address.fragment
        return urlunsplit((address.scheme.lower(), authority,
                           quote(pathname, safe="/%:@!$&'()*+,;=-._~"), query, fragment))
    except (ValueError, UnicodeError) as error:
        raise AbstractionError("The selected value is not an absolute URL") from error


def apply_transform(value, transform):
    if not isinstance(value, str):
        raise AbstractionError("String transforms require a captured string")
    operation = transform["op"]
    if operation == "trim":
        return value.strip(WHITESPACE)
    if operation == "collapse_whitespace":
        return SPACE_PATTERN.sub(" ", value)
    if operation == "lowercase":
        return value.lower()
    if operation == "replace":
        count = value.count(transform["find"])
        if len(value) + count * (len(transform["with"]) - len(transform["find"])) > 1048576:
            raise AbstractionError("Replacement exceeds 1 MiB")
        return value.replace(transform["find"], transform["with"])
    if operation == "map":
        return transform["values"].get(value, value)
    return normalize_url(value, transform)


def project_fields(properties, fields):
    projected = []
    informative = False
    for field in fields:
        value = select(properties, field["keys"])
        for segment in field.get("path", []):
            if isinstance(value, dict):
                value = value.get(segment, MISSING)
            elif isinstance(value, list) and segment.isdigit() and str(int(segment)) == segment and int(segment) < len(value):
                value = value[int(segment)]
            else:
                value = MISSING
        if value is MISSING:
            if field.get("required"):
                raise AbstractionError("Required field '" + field["name"] + "' has no captured property")
            reading = {"kind": "missing"}
        else:
            for transform in [None] + field.get("transforms", []):
                if transform is not None:
                    value = apply_transform(value, transform)
                if len(canonical(value).encode("utf-8")) > 1048576:
                    raise AbstractionError("Selected value exceeds 1 MiB")
            reading = {"kind": "value", "value": value}
            informative = True
        projected.append({"name": field["name"], "reading": reading})
    return projected, informative


def matches(properties, predicate):
    value = select(properties, predicate["keys"])
    if value is MISSING:
        return False
    if predicate["op"] == "present":
        return True
    if predicate["op"] == "contains":
        return isinstance(value, str) and predicate["value"] in value
    return canonical(value) == canonical(predicate["value"])
