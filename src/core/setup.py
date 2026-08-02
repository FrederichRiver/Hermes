from pathlib import Path

from setuptools import find_packages, setup


setup(
    name="hermes-core",
    version=(Path(__file__).parent / "VERSION").read_text(encoding="utf-8").strip(),
    description="Hermes core domain models",
    python_requires=">=3.10",
    package_dir={"": "src"},
    packages=find_packages("src", include=["core", "core.*"]),
)
