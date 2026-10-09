from argparse import ArgumentParser
from pathlib import Path
from .server import serve

parser = ArgumentParser(description="Local fictional portal process")
parser.add_argument("--db", required=True, type=Path)
args = parser.parse_args()
serve(args.db)
