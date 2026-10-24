from pathlib import Path

from setuptools import setup


setup(
    name="hermes-time-agent",
    version=(Path(__file__).parent / "VERSION").read_text(encoding="utf-8").strip(),
    description="Hermes time agent and calendar scheduling",
    python_requires=">=3.10",
    package_dir={"time_agent": "."},
    packages=["time_agent"],
)
