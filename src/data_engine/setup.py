from pathlib import Path

from setuptools import find_packages, setup


setup(
    name="hermes-data-engine",
    version=(Path(__file__).parent / "VERSION").read_text(encoding="utf-8").strip(),
    description="Hermes data storage components",
    python_requires=">=3.10",
    package_dir={"": "src"},
    packages=find_packages("src", include=["data_engine", "data_engine.*"]),
    install_requires=["PyMySQL>=1.0.3"],
)
