"""
서버 실행 스크립트

사용법:
  python run.py           # 일반 실행
  python run.py debug     # STT 입력 오디오 저장 (tests/debug_audio/)
"""

import os
import subprocess
import sys

if "debug" in sys.argv:
    os.environ["STT_DEBUG"] = "1"
    print("[run] STT 디버그 녹음 ON → tests/debug_audio/ 에 저장됩니다")

subprocess.run(["uvicorn", "api.main:app", "--reload"])
