from pathlib import Path

from setuptools import find_packages, setup


setup(
    name="hermes-time-agent",
    version=(Path(__file__).parent / "VERSION").read_text(encoding="utf-8").strip(),
    description="Hermes time agent and calendar scheduling",
    python_requires=">=3.10",
    package_dir={"": "src"},
    packages=find_packages("src", include=["time_agent", "time_agent.*"]),
)
