from pathlib import Path


def test_pipecat_installs_google_runtime_for_gemini_workers() -> None:
    requirements = Path("requirements.txt").read_text(encoding="utf-8").splitlines()
    pipecat = next(line for line in requirements if line.startswith("pipecat-ai["))
    extras = set(pipecat.split("[", 1)[1].split("]", 1)[0].split(","))

    assert "google" in extras
