from pathlib import Path

from setuptools import find_packages, setup


setup(
    name="hermes-agents",
    version=(Path(__file__).parent / "VERSION").read_text(encoding="utf-8").strip(),
    description="Hermes trading agents",
    python_requires=">=3.10",
    package_dir={"": "src"},
    packages=find_packages("src", include=["agents", "agents.*"]),
    install_requires=[
        "beautifulsoup4>=4.12.0",
        "hermes-utils>=0.1.0",
        "requests>=2.28.0",
    ],
)
