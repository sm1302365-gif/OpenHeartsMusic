# ==============================================================================
# __init__.py - Plugin Auto-Discovery
# ==============================================================================
# Automatically discovers all plugin files so __main__.py can load them.
# Eliminates the need to manually register new command files.
# ==============================================================================

from pathlib import Path


def _list_modules():
    mod_dir = Path(__file__).resolve().parent
    modules: list[str] = []

    for file in sorted(mod_dir.rglob("*.py")):
        if not file.is_file():
            continue
        if file.name == "__init__.py":
            continue
        if "__pycache__" in file.parts:
            continue

        relative_path = file.relative_to(mod_dir)
        module_path = relative_path.with_suffix("").as_posix().replace("/", ".")
        if module_path.startswith("."):
            continue

        modules.append(module_path)

    return sorted(set(modules))


all_modules = tuple(_list_modules())
__all__ = list(all_modules)
