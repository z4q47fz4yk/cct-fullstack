"""Generate requirements.txt from uv.lock for the production dependency group."""

import tomllib
from packaging.markers import Marker
from packaging.version import Version

with open("uv.lock", "rb") as f:
    lock = tomllib.load(f)

packages = {p["name"]: p for p in lock["package"]}

root = packages["cct"]

# Evaluate markers for the target environment: CPython 3.14 on Windows
env = {
    "python_version": "3.14",
    "python_full_version": "3.14.0",
    "sys_platform": "win32",
    "platform_system": "Windows",
    "os_name": "nt",
    "implementation_name": "cpython",
}


def marker_applies(dep) -> bool:
    m = dep.get("marker")
    if not m:
        return True
    return Marker(m).evaluate(environment=env)


resolved = {}
stack = [d["name"] for d in root["dependencies"] if marker_applies(d)]

while stack:
    name = stack.pop()
    if name in resolved:
        continue
    pkg = packages[name]
    resolved[name] = pkg["version"]
    for dep in pkg.get("dependencies", []):
        if marker_applies(dep) and dep["name"] not in resolved:
            stack.append(dep["name"])

lines = [f"{n}=={v}" for n, v in sorted(resolved.items(), key=lambda kv: kv[0].lower())]

header = [
    "# Generated from uv.lock (production dependencies of project 'cct')",
    "# Python >=3.14",
    "# Install: pip install -r requirements.txt",
    "",
]

with open("requirements.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(header + lines) + "\n")

print(f"{len(lines)} packages written")
