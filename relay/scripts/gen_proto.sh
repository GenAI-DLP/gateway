#!/usr/bin/env bash
# proto/dlp-proto 서브모듈의 .proto로부터 Python gRPC 스텁을 생성한다.
# 생성물(*_pb2.py, *_pb2_grpc.py)은 .gitignore 대상 — 항상 이 스크립트로 새로 만든다.
set -euo pipefail
cd "$(dirname "$0")/.."

PROTO_DIR="proto/dlp-proto"
OUT_DIR="proto"

if [ ! -f "$PROTO_DIR/dlp.proto" ]; then
  echo "error: $PROTO_DIR/dlp.proto 가 없습니다. 'git submodule update --init --recursive'를 먼저 실행하세요." >&2
  exit 1
fi

python -m grpc_tools.protoc \
  -I "$PROTO_DIR" \
  --python_out="$OUT_DIR" \
  --grpc_python_out="$OUT_DIR" \
  "$PROTO_DIR/dlp.proto"

# grpc_tools가 생성하는 절대 import를 패키지 상대 import로 고정
sed -i.bak 's/^import dlp_pb2 as dlp__pb2$/from . import dlp_pb2 as dlp__pb2/' "$OUT_DIR/dlp_pb2_grpc.py"
rm -f "$OUT_DIR/dlp_pb2_grpc.py.bak"

echo "generated: $OUT_DIR/dlp_pb2.py, $OUT_DIR/dlp_pb2_grpc.py"