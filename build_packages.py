"""Build versioned Hermes package distributions.

Run ``python build_packages.py utils event_engine`` to build selected packages,
or omit package names to build every installable package. Package versions are
read from the manually maintained ``package_versions.txt`` file.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parent
_SRC_ROOT = _ROOT / "src"
_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


def _discover_package_directories() -> dict[str, Path]:
    """Discover installable package directories under src/.

    Only directories containing both a setup.py and VERSION file are treated as
    buildable packages. This keeps the build script aligned with the current
    folder layout after structural refactors.
    """
    packages: dict[str, Path] = {}
    if not _SRC_ROOT.exists():
        return packages

    for child in sorted(_SRC_ROOT.iterdir()):
        if not child.is_dir():
            continue
        if (child / "setup.py").exists() and (child / "VERSION").exists():
            packages[child.name] = child
    return packages


_PACKAGE_DIRECTORIES = _discover_package_directories()


def _load_package_versions(version_file: Path) -> dict[str, str]:
    """Load manually maintained package versions from a text file.

    Args:
        version_file: Root package version-control file.

    Returns:
        Package versions keyed by package directory name.

    Raises:
        ValueError: If a version entry is malformed or has an invalid version.
    """
    versions: dict[str, str] = {}
    for line_number, line in enumerate(
        version_file.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        normalized_line = line.strip()
        if not normalized_line or normalized_line.startswith("#"):
            continue
        package_name, separator, version = normalized_line.partition("=")
        package_name = package_name.strip()
        version = version.strip()
        if not separator:
            raise ValueError(
                f"Invalid version entry on line {line_number}: {normalized_line!r}"
            )
        if package_name not in _PACKAGE_DIRECTORIES:
            print(
                f"Skipping version entry for undiscovered package {package_name!r} "
                f"on line {line_number}.",
                file=sys.stderr,
            )
            continue
        if not _VERSION_PATTERN.fullmatch(version):
            raise ValueError(
                f"Version for {package_name} must use the format X.Y.Z; "
                f"found {version!r}."
            )
        versions[package_name] = version

    missing_packages = set(_PACKAGE_DIRECTORIES) - set(versions)
    if missing_packages:
        raise ValueError(
            "Missing package versions: " + ", ".join(sorted(missing_packages))
    )
    return versions


def _build_package(
    package_name: str,
    package_directory: Path,
    version: str,
) -> None:
    """Create wheel and source distributions using a declared package version."""
    version_file = package_directory / "VERSION"
    output_directory = _ROOT / "dist"
    output_directory.mkdir(parents=True, exist_ok=True)

    version_file.write_text(f"{version}\n", encoding="utf-8")
    for command in ("sdist", "bdist_wheel"):
        subprocess.run(
            [
                sys.executable,
                "setup.py",
                command,
                "--dist-dir",
                str(output_directory.resolve()),
            ],
            cwd=package_directory,
            check=True,
        )
    print(f"Built {package_name} version {version} in {output_directory}")


def main() -> int:
    """Parse requested packages and build their distribution artifacts."""
    parser = argparse.ArgumentParser(
        description="Build versioned Hermes package distributions."
    )
    parser.add_argument(
        "packages",
        nargs="*",
        help="Packages to build; builds every package when omitted.",
    )
    parser.add_argument(
        "--versions-file",
        default="package_versions.txt",
        type=Path,
        help="Manually maintained package version-control file.",
    )
    arguments = parser.parse_args()

    if not _PACKAGE_DIRECTORIES:
        raise RuntimeError("No installable package directories were found under src/.")

    requested_packages = arguments.packages or sorted(_PACKAGE_DIRECTORIES)
    invalid_packages = sorted(set(requested_packages) - set(_PACKAGE_DIRECTORIES))
    if invalid_packages:
        raise SystemExit(
            "Unknown package(s): " + ", ".join(invalid_packages)
            + "\nAvailable packages: " + ", ".join(sorted(_PACKAGE_DIRECTORIES))
        )

    package_versions = _load_package_versions(_ROOT / arguments.versions_file)

    for package_name in requested_packages:
        _build_package(
            package_name,
            _PACKAGE_DIRECTORIES[package_name],
            package_versions[package_name],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
