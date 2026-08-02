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


_PACKAGE_DIRECTORIES = {
    "agents": Path("src/agents"),
    "backtest": Path("src/backtest"),
    "config": Path("src/config"),
    "core": Path("src/core"),
    "data_engine": Path("src/data_engine"),
    "event": Path("src/event"),
    "event_engine": Path("src/event_engine"),
    "execution": Path("src/execution"),
    "market": Path("src/market"),
    "utils": Path("src/utils"),
}
_PRERELEASE_VERSION_PATTERN = re.compile(r"^0\.5\.(\d+)$")


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
        if not separator or package_name not in _PACKAGE_DIRECTORIES:
            raise ValueError(
                f"Invalid version entry on line {line_number}: {normalized_line!r}"
            )
        if not _PRERELEASE_VERSION_PATTERN.fullmatch(version):
            raise ValueError(
                f"Version for {package_name} must use the format 0.5.z; "
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
    output_directory = Path("dist")
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
        choices=sorted(_PACKAGE_DIRECTORIES),
        help="Packages to build; builds every package when omitted.",
    )
    parser.add_argument(
        "--versions-file",
        default="package_versions.txt",
        type=Path,
        help="Manually maintained package version-control file.",
    )
    arguments = parser.parse_args()
    package_names = arguments.packages or list(_PACKAGE_DIRECTORIES)
    package_versions = _load_package_versions(arguments.versions_file)

    for package_name in package_names:
        _build_package(
            package_name,
            _PACKAGE_DIRECTORIES[package_name],
            package_versions[package_name],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
