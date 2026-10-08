from configparser import ConfigParser
from pathlib import Path


def test_deployment_directory_is_inside_project() -> None:
    """PySide6 refuses to clean deployment files outside the project directory."""
    repo_dir = Path(__file__).resolve().parent.parent
    config = ConfigParser()
    config.read(repo_dir / "pysidedeploy.spec")

    project_dir = (repo_dir / config["app"]["project_dir"]).resolve()
    source_file = (repo_dir / config["app"]["input_file"]).resolve()
    deployment_dir = source_file.parent / "deployment"

    assert source_file.is_file()
    assert source_file.is_relative_to(project_dir)
    assert deployment_dir.is_relative_to(project_dir)


def test_deployment_uses_single_file_mode() -> None:
    """Release pipelines expect a single .exe or .bin, not a .dist directory."""
    repo_dir = Path(__file__).resolve().parent.parent
    config = ConfigParser()
    config.read(repo_dir / "pysidedeploy.spec")

    assert config["nuitka"].get("mode") == "onefile"
