"""Script to generate Python protobuf code from .proto files."""

import subprocess
import sys
from pathlib import Path


def generate():
    proto_dir = Path(__file__).parent.parent / "proto"
    output_dir = Path(__file__).parent / "proto"
    output_dir.mkdir(exist_ok=True)

    proto_file = proto_dir / "movie_events.proto"

    if not proto_file.exists():
        print(f"Proto file not found: {proto_file}")
        sys.exit(1)

    cmd = [
        sys.executable, "-m", "grpc_tools.protoc",
        f"--proto_path={proto_dir}",
        f"--python_out={output_dir}",
        str(proto_file),
    ]

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        sys.exit(1)

    print(f"Generated protobuf code in {output_dir}")

    # Fix imports in generated file
    generated_file = output_dir / "movie_events_pb2.py"
    if generated_file.exists():
        content = generated_file.read_text()
        # No fixes needed for standard protobuf imports
        generated_file.write_text(content)
        print(f"Protobuf code ready: {generated_file}")


if __name__ == "__main__":
    generate()
