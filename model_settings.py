"""Whisper model identity shared by runtime and replication checks."""

from __future__ import annotations

import os


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_SIZE = "large-v3"
MODEL_REPOSITORY = "Systran/faster-whisper-large-v3"
MODEL_REVISION = "edaa852ec7e145841d8ffdb056a99866b5f0a478"
MODEL_DIR = os.path.join(BASE_DIR, "models")
