# tests/test_cli_zotero.py
import pytest
from click.testing import CliRunner
import argparse
from scifi.cli import create_parser, main

def test_cli_zotero_parser_registration():
    parser = create_parser()
    # Check if zotero, scaffold, adapt, and doctor are in subcommands
    subparsers_actions = [
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    ]
    assert len(subparsers_actions) > 0
    choices = subparsers_actions[0].choices
    assert "zotero" in choices
    assert "scaffold" in choices
    assert "adapt" in choices
    assert "init" in choices

def test_cli_zotero_status_invocation(capsys):
    ret = main(["zotero", "status"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Zotero Status" in captured.out or "Zotero" in captured.out

def test_cli_doctor_env_invocation(capsys):
    ret = main(["doctor", "--env"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Environment Health" in captured.out or "Python" in captured.out
