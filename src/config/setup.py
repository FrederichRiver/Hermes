from pathlib import Path

from setuptools import find_packages, setup


setup(
    name="hermes-config",
    version=(Path(__file__).parent / "VERSION").read_text(encoding="utf-8").strip(),
    description="Hermes runtime configuration",
    python_requires=">=3.10",
    package_dir={"": "src"},
    packages=find_packages("src", include=["config", "config.*"]),
    package_data={"config": ["*.json"]},
)
